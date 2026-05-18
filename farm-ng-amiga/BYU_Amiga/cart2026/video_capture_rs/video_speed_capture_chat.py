"""
Multi-Camera RealSense Video + Motor RPM Recorder (USB Safe)
------------------------------------------------------------

Records color video from all connected RealSense cameras and
simultaneously logs motor RPMs to a separate CSV.

Robust against motor listener failures and slow USB mounting.

Requirements:
pip install pyrealsense2 opencv-python
"""

import pyrealsense2 as rs
import numpy as np
import cv2
import threading
import queue
import time
import os
from datetime import datetime
import subprocess
import csv
import argparse
import asyncio
from pathlib import Path

from farm_ng.canbus.packet import MotorState
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file

# ============================================================
# USER CONFIGURATION
# ============================================================

WIDTH = 640
HEIGHT = 480
FPS = 30
QUEUE_SIZE = 400
VIDEO_CODEC = 'mp4v'

# ============================================================
# STOP LISTENER
# ============================================================

def stop_listener():
    global running
    input("Press ENTER to stop recording\n")
    print("Stopping recording...")
    running = False

# ============================================================
# MOTOR LISTENER (ASYNC, PATCHED)
# ============================================================

async def motor_listener(service_config_path: Path, writer: csv.writer):
    try:
        config: EventServiceConfig = proto_from_json_file(service_config_path, EventServiceConfig())
        async for event, message in EventClient(config).subscribe(config.subscriptions[0], decode=True):
            motors = [MotorState.from_proto(m) for m in message.motors]
            sys_time = time.time()
            for motor in sorted(motors, key=lambda m: m.id):
                writer.writerow([motor.id, motor.rpm, sys_time])
    except Exception as e:
        print("Motor listener error:", e)

def start_motor_thread(service_config_path, writer):
    asyncio.run(motor_listener(service_config_path, writer))

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # ------------------------
    # ARGUMENT PARSING
    # ------------------------
    parser = argparse.ArgumentParser(description="Stream motor states from the canbus service.")
    parser.add_argument("--service-config", type=Path, required=True, help="The service config JSON file")
    args = parser.parse_args()

    # ------------------------
    # WAIT FOR USB DRIVE (ROBUST)
    # ------------------------
    drive_path = "/media/adminfarmng/CROPBIO2"

if not os.path.ismount(drive_path):
    print("USB drive not mounted. Attempting to mount...")
    subprocess.run(["mountusb.sh"])
    if not os.path.ismount(drive_path):
        print("Failed to mount USB drive. Exiting.")
        exit(1)

print("USB drive mounted, proceeding...")


# ------------------------
# PARTICIPANT ID / OUTPUT FOLDER
# ------------------------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
part_id = input("Enter Participant ID or enter 'time' to use timestamp: ")
if part_id.lower() == 'time':
    part_id = timestamp

folder = f"{part_id}_realsense_recording"
output_dir = os.path.join(drive_path, folder)
os.makedirs(output_dir, exist_ok=True)
print("Saving videos to:", output_dir)

# ------------------------
# FIND CONNECTED CAMERAS
# ------------------------
ctx = rs.context()
devices = ctx.query_devices()
if len(devices) == 0:
    raise RuntimeError("No RealSense cameras detected.")

serial_numbers = []
print("\nDetected Cameras:")
for dev in devices:
    serial = dev.get_info(rs.camera_info.serial_number)
    name = dev.get_info(rs.camera_info.name)
    print(f"  {name} | Serial: {serial}")
    serial_numbers.append(serial)

num_cameras = len(serial_numbers)
print(f"\nTotal Cameras: {num_cameras}")

# ------------------------
# CREATE PIPELINES AND CONFIGS
# ------------------------
pipelines = []
configs = []
for serial in serial_numbers:
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(serial)
    config.enable_stream(rs.stream.color, WIDTH, HEIGHT, rs.format.bgr8, FPS)
    pipelines.append(pipeline)
    configs.append(config)

# ------------------------
# MOTOR CSV SETUP
# ------------------------
motor_csv_path = os.path.join(output_dir, "motor_rpm.csv")
motor_file = open(motor_csv_path, "w", newline="")
motor_writer = csv.writer(motor_file)
motor_writer.writerow(["motor_id", "rpm", "timestamp_seconds"])

# ------------------------
# START MOTOR THREAD (DAEMON)
# ------------------------
motor_thread = threading.Thread(
    target=start_motor_thread,
    args=(args.service_config, motor_writer),
    daemon=True
)
motor_thread.start()

# ------------------------
# START CAMERA PIPELINES
# ------------------------
print("\nStarting camera pipelines...")
for i in range(num_cameras):
    pipelines[i].start(configs[i])
print("All cameras started.\n")

# ------------------------
# FRAME QUEUES
# ------------------------
frame_queues = [queue.Queue(maxsize=QUEUE_SIZE) for _ in range(num_cameras)]

# ------------------------
# VIDEO WRITERS
# ------------------------
video_writers = []
fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)
for i in range(num_cameras):
    filepath = os.path.join(output_dir, f"camera_{i}.mp4")
    writer = cv2.VideoWriter(filepath, fourcc, FPS, (WIDTH, HEIGHT))
    video_writers.append(writer)
    print("Video writer created:", filepath)

# ------------------------
# TIMESTAMP CSVS
# ------------------------
timestamp_files = []
timestamp_writers = []
for i in range(num_cameras):
    path = os.path.join(output_dir, f"camera_{i}_timestamps.csv")
    f = open(path, 'w', newline='')
    writer = csv.writer(f)
    writer.writerow(["frame_number", "realsense_timestamp_ms", "system_time_seconds"])
    timestamp_files.append(f)
    timestamp_writers.append(writer)

# ------------------------
# THREAD CONTROL FLAG
# ------------------------
running = True

# ------------------------
# WRITER THREAD FUNCTION
# ------------------------
def writer_thread_func(cam_index):
    writer = video_writers[cam_index]
    q = frame_queues[cam_index]
    while running or not q.empty():
        try:
            frame = q.get(timeout=1)
            writer.write(frame)
        except queue.Empty:
            pass
    writer.release()
    print(f"Writer thread {cam_index} finished.")

# ------------------------
# START WRITER THREADS
# ------------------------
writer_threads = []
for i in range(num_cameras):
    t = threading.Thread(target=writer_thread_func, args=(i,), daemon=True)
    t.start()
    writer_threads.append(t)

# ------------------------
# START STOP LISTENER
# ------------------------
listener_thread = threading.Thread(target=stop_listener, daemon=True)
listener_thread.start()

# ------------------------
# CAPTURE LOOP
# ------------------------
print("\nRecording...\n")
start_time = time.time()

try:
    while running:
        for cam_index, pipeline in enumerate(pipelines):
            frames = pipeline.poll_for_frames()
            if not frames:
                continue
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue
            image = np.asanyarray(color_frame.get_data())
            frame_number = color_frame.get_frame_number()
            rs_time = color_frame.get_timestamp()
            sys_time = time.time()
            timestamp_writers[cam_index].writerow([frame_number, rs_time, sys_time])
            q = frame_queues[cam_index]
            if q.full():
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
            q.put(image)
            time.sleep(0.001)

except KeyboardInterrupt:
    print("\nCtrl+C detected. Stopping recording...")
    running = False

finally:
    # CLEANUP
    print("Stopping pipelines...")
    for pipeline in pipelines:
        pipeline.stop()
    print("Waiting for writer threads...")
    for t in writer_threads:
        t.join()
    for f in timestamp_files:
        f.close()
    motor_file.close()

    print("\nRecording complete.")
    print("Total time:", round(time.time() - start_time, 2), "seconds")
    print("Videos and motor CSV saved to:", output_dir)

    print('Unmounting usb drive')
    subprocess.run(["unmountusb.sh"])