from __future__ import annotations

import argparse
from datetime import datetime
import asyncio
from pathlib import Path
import os
import subprocess
import time

import cv2
import numpy as np
import pyrealsense2 as rs

from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from farm_ng.core.stamp import get_stamp_by_semantics_and_clock_type, StampSemantics

from farm_ng.gps import gps_pb2

# ===================== GLOBALS =====================
latest_gps = {"latitude": None, "longitude": None, "horizontal_accuracy": None}

# ===================== REALSENSE CAMERA CLASS =====================
class RealSenseCamera:
    def __init__(self, serial=None, output_dir=None):
        self.pipeline = rs.pipeline()
        self.output_dir = Path(output_dir)
        self.serial = serial
        self.isBad = False

        config = rs.config()
        config.enable_device(serial)
        config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 15)
        config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 15)

        try:
            self.pipeline.start(config)
        except Exception as e:
            print(f"Warning: pipeline start failed: {e}")
            config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 6)
            config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 6)
            try:
                self.pipeline.start(config)
            except Exception as e:
                print(f"Warning: pipeline start failed totally: {e}")
                self.isBad = True

        # warm up
        self.take_picture()
        time.sleep(0.5)

    def take_picture(self, file_name='firstpic.png', picType="color"):
        try:
            while True:
                frames = self.pipeline.wait_for_frames(timeout_ms=2500)
                frame_dict = {"color": frames.get_color_frame(), "depth": frames.get_depth_frame()}
                pict_frame = frame_dict.get(picType)
                if pict_frame:
                    break

            if pict_frame is None:
                raise RuntimeError("No frame received from RealSense camera.")

            color_image = np.asanyarray(pict_frame.get_data())
            out_path = self.output_dir / file_name
            cv2.imwrite(str(out_path), color_image)

        except Exception as e:
            print(f"RealSense capture failed: {e}")

    def end_pipeline(self):
        try:
            self.pipeline.stop()
        except Exception:
            pass

# ===================== ASYNC QUEUE =====================
class FrameQueue(asyncio.Queue):
    def __init__(self, output_dir: Path):
        super().__init__()
        self.output_dir = output_dir

async def save_worker(frame_queue: FrameQueue):
    while True:
        frame_data = await frame_queue.get()
        if frame_data is None:  # sentinel to stop
            break
        try:
            cv2.imwrite(str(frame_data["path"]), frame_data["data"], [cv2.IMWRITE_JPEG_QUALITY, 90])
        except Exception as e:
            print(f"Error saving frame: {e}")
        frame_queue.task_done()

# ===================== OAK CAPTURE =====================
async def capture_single_oak_async(config: EventServiceConfig, frame_queue: FrameQueue, picType="color"):
    client = EventClient(config)
    async for event, message in client.subscribe(config.subscriptions[0], decode=True):
        stamp = get_stamp_by_semantics_and_clock_type(event, StampSemantics.DRIVER_RECEIVE, "monotonic") \
                or event.timestamps[0].stamp
        stamp = np.round(stamp, 3)
        pic_types = picType.split(",")

        lat = np.round(latest_gps["latitude"], 7) if latest_gps["latitude"] else 0
        lon = np.round(latest_gps["longitude"], 7) if latest_gps["longitude"] else 0
        gps_stamp = f"lat{lat}_lon{lon}"

        if "color" in pic_types:
            image = cv2.imdecode(np.frombuffer(message.image_data, dtype="uint8"), cv2.IMREAD_UNCHANGED)
            filename = f"{config.name}_{picType}_{stamp}_{gps_stamp}.jpg"
            out_path = frame_queue.output_dir / filename
            await frame_queue.put({"path": out_path, "data": image})

# ===================== REALSENSE CAPTURE =====================
async def capture_realsense_async(cam: RealSenseCamera, frame_queue: FrameQueue, pic_types=["color","depth"]):
    serial_map = {
        "217222062474": "RS1",  # ends with 74
        "211622067750": "RS2",  # ends with 50
    }
    cam_name = serial_map.get(cam.serial, cam.serial)
    
    while True:
        frames = cam.pipeline.wait_for_frames(timeout_ms=2500)
        color_frame = frames.get_color_frame()
        depth_frame = frames.get_depth_frame()

        timestamp = datetime.now().strftime("%Y.%m.%d_%H%M_%S.%f")
        lat = np.round(latest_gps["latitude"], 7) if latest_gps["latitude"] else 0
        lon = np.round(latest_gps["longitude"], 7) if latest_gps["longitude"] else 0
        gps_stamp = f"lat{lat}_lon{lon}"

        if "color" in pic_types and color_frame:
            color_image = np.asanyarray(color_frame.get_data())
            filename = f"{cam_name}_color_{timestamp}_{gps_stamp}.jpg"
            out_path = frame_queue.output_dir / filename
            await frame_queue.put({"path": out_path, "data": color_image})

        if "depth" in pic_types and depth_frame:
            depth_image = np.asanyarray(depth_frame.get_data())
            filename = f"{cam_name}_depth_{timestamp}_{gps_stamp}.png"
            out_path = frame_queue.output_dir / filename
            await frame_queue.put({"path": out_path, "data": depth_image})

# ===================== GPS WATCH =====================
async def watch_gps(gps_config: Path):
    global latest_gps
    config = proto_from_json_file(gps_config, EventServiceConfig())
    async for event, msg in EventClient(config).subscribe(config.subscriptions[0]):
        if isinstance(msg, gps_pb2.GpsFrame):
            latest_gps["latitude"] = msg.latitude
            latest_gps["longitude"] = msg.longitude
            latest_gps["horizontal_accuracy"] = msg.horizontal_accuracy
# ===================== USER COMMANDS =====================
async def user_command_listener(state: dict):
    print("Type 'p' (pause), 'r' (resume), or 's' (stop) to control the capture.")
    loop = asyncio.get_event_loop()
    while True:
        try:
            cmd = await loop.run_in_executor(None, input, ">>> ")
            cmd = cmd.strip().lower()

            if cmd == "p":
                state["paused"] = True
                print("📷 Capture paused.")
            elif cmd == "r":
                state["paused"] = False
                print("▶️ Capture resumed.")
            elif cmd == "s":
                state["stop"] = True
                print("🛑 Stop command received.")
                break
            else:
                print("Unknown command. Use 'p', 'r', or 's'.")
        except Exception as e:
            print(f"Command listener error: {e}")
            break

# ===================== MAIN CAPTURE LOOP =====================
async def capture_images(oak0_config_path: Path, oak1_config_path: Path, output_dir: Path, duration: float, gps_config: Path):
    if not os.path.ismount("/media/adminfarmng/crimson"):
        print("USB drive not mounted. Attempting to mount...")
        subprocess.run(["mountusb.sh"])
        if not os.path.ismount("/media/adminfarmng/crimson"):
            print("Failed to mount USB drive. Exiting.")
            return

    # Initialize RealSense cameras
    cam1 = RealSenseCamera(serial="211622067750", output_dir=output_dir)
    cam2 = RealSenseCamera(serial="217222062474", output_dir=output_dir)

    if cam1.isBad:
        print("RealSense 1 failed")
    else:
        print("RealSense 1 initialized.")
    if cam2.isBad:
        print("RealSense 2 failed")
    else:
        print("RealSense 2 initialized.")

    config_paths = [oak0_config_path, oak1_config_path] if oak1_config_path else [oak0_config_path]

    # Frame queue
    frame_queue = FrameQueue(output_dir)
    save_task = asyncio.create_task(save_worker(frame_queue))

    # GPS task
    gps_task = asyncio.create_task(watch_gps(gps_config))

    # User command task
    state = {"paused": False, "stop": False}
    command_task = asyncio.create_task(user_command_listener(state))

    # Start camera tasks
    # oak_tasks = []
    # for cfg_path in config_paths:
    #     config = proto_from_json_file(cfg_path, EventServiceConfig())
    #     oak_tasks.append(asyncio.create_task(capture_single_oak_async(config, frame_queue, "color")))

    rs_tasks = []
    for cam in [cam1, cam2]:
        rs_tasks.append(asyncio.create_task(capture_realsense_async(cam, frame_queue, ["color","depth"])))

    print("Capture loop started. Type commands to control it.")
    count = 0
    init_time = time.time()

    try:
        while not state["stop"]:
            start_time = time.time()
            if not state["paused"]:
                await asyncio.sleep(0.05)  # small sleep to yield control
                count += 1
                elapsed = time.time() - start_time
                total_time = time.time() - init_time
                rate = 1 / elapsed if elapsed > 0 else float('inf')
                print(f"Captured image set {count} at {rate:.2f} Hz", end='\r')
            else:
                await asyncio.sleep(0.1)

    finally:
        # Cancel tasks
        # for task in oak_tasks + rs_tasks + [gps_task, command_task]:
        for task in rs_tasks + [gps_task, command_task]:
            task.cancel()
        await frame_queue.put(None)  # stop save worker
        await save_task

        # Stop RealSense
        cam1.end_pipeline()
        cam2.end_pipeline()
        total_time = time.time() - init_time
        print(f"\n✅ Capture stopped after taking {count} images in {total_time:.2f}s for an overall rate of {count/total_time:.2f} Hz.")
        # subprocess.run(["unmountusb.sh"])

# ===================== CLI ENTRY =====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture still images from Amiga OAK + RealSense cameras")
    parser.add_argument("--oak0-config", type=Path, required=True, help="Path to  first OAK camera service config JSON")
    parser.add_argument("--oak1-config", type=Path, required=True, help="Path to second OAK camera service config JSON")
    parser.add_argument("--gps-config", type=Path, required=True, help="Path to GPS camera service config JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("/media/adminfarmng/crimson/current"), help="Directory to save images")
    parser.add_argument("--duration", type=float, default=60, help="How long to capture (seconds)")
    args = parser.parse_args()

    asyncio.run(capture_images(args.oak0_config, args.oak1_config, args.output_dir, args.duration, args.gps_config))
