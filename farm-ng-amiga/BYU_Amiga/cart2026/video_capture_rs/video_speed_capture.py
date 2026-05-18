"""
Multi-Camera RealSense Video Recorder
-------------------------------------

This script records color video from all connected RealSense cameras.

Key Features
------------
- Detects all connected cameras automatically
- Non-blocking frame capture (poll_for_frames)
- Frame queues to prevent dropped frames
- Separate writer thread per camera
- Videos saved to a timestamped folder
- Clean shutdown with Ctrl+C

Requirements
------------
pip install pyrealsense2 opencv-python

# sudo -E env PATH=$PATH python -u video_speed_capture.py  |& tee -a ~/farmng_log.log
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
import keyboard
import csv




# ============================================================
# USER CONFIGURATION
# ============================================================

WIDTH = 640
HEIGHT = 480
FPS = 30

QUEUE_SIZE = 400

VIDEO_CODEC = 'mp4v'

# DEFINE LISTENER THREAD FUNCTION

def stop_listener():
    global running
    input("Press ENTER to stop recording\n")
    print("Stopping recording...")
    running = False


# ============================================================
# CREATE OUTPUT DIRECTORY
# ============================================================

if not os.path.ismount("/media/adminfarmng/CROPBIO2"):
    print("USB drive not mounted. Attempting to mount...")
    subprocess.run(["mountusb.sh"])
    if not os.path.ismount("/media/adminfarmng/CROPBIO2"):
        print("Failed to mount USB drive. Exiting.")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
part_id = input("Enter Participant ID or enter time to use timestamp:")
if part_id == 'time':
    part_id = timestamp
    
drive_path = "/media/adminfarmng/CROPBIO2"
folder = f"{part_id}_realsense_recording"
output_dir = os.path.join(drive_path, folder)

os.makedirs(output_dir, exist_ok=True)

print("Saving videos to:", output_dir)



# ============================================================
# FIND CONNECTED CAMERAS
# ============================================================

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


# ============================================================
# CREATE PIPELINES AND CONFIGS
# ============================================================

pipelines = []
configs = []

for serial in serial_numbers:

    pipeline = rs.pipeline()
    config = rs.config()

    # Attach pipeline to specific device
    config.enable_device(serial)

    # Enable color stream
    config.enable_stream(
        rs.stream.color,
        WIDTH,
        HEIGHT,
        rs.format.bgr8,  # Changed from .bgr8 3/13/26
        FPS
    )

    pipelines.append(pipeline)
    configs.append(config)


# ============================================================
# START CAMERAS
# ============================================================

print("\nStarting camera pipelines...")

for i in range(num_cameras):
    pipelines[i].start(configs[i])

print("All cameras started.\n")


# ============================================================
# FRAME QUEUES
# ============================================================

"""
Each camera gets its own queue.

The capture thread pushes frames into the queue.
The writer thread pulls frames from the queue.

This prevents frame drops if disk writing is slower
than camera capture.
"""

frame_queues = [
    queue.Queue(maxsize=QUEUE_SIZE)
    for _ in range(num_cameras)
]


# ============================================================
# FILE WRITERS
# ============================================================

video_writers = []

fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)



for i in range(num_cameras):

    filepath = os.path.join(output_dir, f"camera_{i}.mp4")

    writer = cv2.VideoWriter(
        filepath,
        fourcc,
        FPS,
        (WIDTH, HEIGHT)
    )

    video_writers.append(writer)

    print("Video writer created:", filepath)

timestamp_files = []
timestamp_writers = []

for i in range(num_cameras):

    path = os.path.join(output_dir, f"camera_{i}_timestamps.csv")

    f = open(path, 'w', newline='')
    writer = csv.writer(f)

    writer.writerow([
        "frame_number",
        "realsense_timestamp_ms",
        "system_time_seconds"
    ])

    timestamp_files.append(f)
    timestamp_writers.append(writer)


# ============================================================
# THREAD CONTROL FLAG
# ============================================================

running = True


# ============================================================
# WRITER THREAD FUNCTION
# ============================================================

def writer_thread_func(cam_index):
    """
    Continuously pulls frames from the queue
    and writes them to the video file.

    This runs in a separate thread so disk
    operations never slow down capture.
    """

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


# ============================================================
# START WRITER THREADS
# ============================================================

writer_threads = []

for i in range(num_cameras):

    t = threading.Thread(
        target=writer_thread_func,
        args=(i,),
        daemon=True
    )

    t.start()
    writer_threads.append(t)


# ============================================================
# CAPTURE LOOP (NON-BLOCKING)
# ============================================================

print("\nRecording...\n")

start_time = time.time()
running = True


listener_thread = threading.Thread(target=stop_listener, daemon=True)
listener_thread.start()

try:

    while running:

        # Capture frames from all cameras
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

            timestamp_writers[cam_index].writerow([
                frame_number,
                rs_time,
                sys_time
            ])


            q = frame_queues[cam_index]

            # If queue full, discard oldest frame
            if q.full():
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass

            q.put(image)

        

except KeyboardInterrupt:
    print("\nCtrl+C detected. Stopping recording...")
    running = False

finally:

    # ============================================================
    # CLEANUP
    # ============================================================

    print("Stopping pipelines...")

    for pipeline in pipelines:
        pipeline.stop()

    print("Waiting for writer threads...")

    for t in writer_threads:
        t.join()
    
    for f in timestamp_files:
        f.close()

    print("\nRecording complete.")
    print("Total time:", round(time.time() - start_time, 2), "seconds")
    print("Videos saved to:", output_dir)

    print('Unmounting usb drive')

    subprocess.run(["unmountusb.sh"])


# sudo -E env PATH=$PATH python -u video_speed_capture.py  |& tee -a ~/farmng_log.log