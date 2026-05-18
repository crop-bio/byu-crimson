from __future__ import annotations

import argparse
from datetime import datetime
import asyncio
from pathlib import Path
import os
import subprocess
import time
import traceback

import cv2
import numpy as np
import pandas as pd
import pyrealsense2 as rs

from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from farm_ng.core.stamp import get_stamp_by_semantics_and_clock_type, StampSemantics

from farm_ng.gps import gps_pb2

latest_gps = {"latitude": None, "longitude": None, "horizontal_accuracy": None}

 # ===================== REALSENSE CAMERA CLASS =====================
class RealSenseCamera:
    """A class defining a RealSense camera"""
    def __init__(self, serial=None, output_dir=None):
        # Setup pipeline and output directory
        self.pipeline = rs.pipeline()
        self.output_dir = Path(output_dir)
        self.isBad = False

        config = rs.config()

        # Enable device by serial number
        config.enable_device(serial)

        # Enable color stream 
        ''' Add something to check for the highest available resolution & framerate? '''
        config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, framerate=15)

        # Enable depth stream
        config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, framerate=15)

        # Start streaming (non-fatal)
        try:
            self.pipeline.start(config)
        except Exception as e:
            print(f"Warning: pipeline start failed: {e}")
            config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, framerate=6)
            config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, framerate=6)
            try:
                self.pipeline.start(config)
            except Exception as e:
                print(f"Warning: pipeline start failed totally: {e}")
                self.isBad = True
        # warm up
        self.take_picture()
        time.sleep(0.5)

    def take_picture(self, file_name='firstpic.png', picType="color"):
        """Grab a frame and write it to self.output_dir / file_name"""
        try:
            # Wait a few frames so auto-exposure can settle (timeout to avoid blocking)
            while True:
                frames = self.pipeline.wait_for_frames(timeout_ms=2500)
                frame_dict = {"color": frames.get_color_frame(), "depth": frames.get_depth_frame()}
                pict_frame = frame_dict.get(picType)
                if pict_frame:
                    break

            if pict_frame is None:
                raise RuntimeError("No frame received from RealSense camera.")

            # Convert to numpy and save
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
        
def save_csv(filename, newdf):
    df = pd.read_csv(filename)
    df = pd.concat([df, newdf])
    df.to_csv(filename, index=False)
    

# ===================== ASYNC QUEUE =====================

async def capture_single_oak(config: EventServiceConfig, output_dir: Path, picType = None):
    """Capture a single frame from one OAK service."""
    client = EventClient(config)
    async for event, message in client.subscribe(config.subscriptions[0], decode=True):
        stamp = get_stamp_by_semantics_and_clock_type(event, StampSemantics.DRIVER_RECEIVE, "monotonic") \
                or event.timestamps[0].stamp
        stamp = np.round(stamp, 3)
        timestamp = datetime.now().strftime("%Y.%m.%d_%H%M_%S.%f")
        # Decode image
        pic_types = picType.split(",")

        lat = np.round(latest_gps["latitude"], 7) if latest_gps["latitude"] else 0
        lon = np.round(latest_gps["longitude"], 7) if latest_gps["longitude"] else 0
        acc = np.round(latest_gps["horizontal_accuracy"],7) if latest_gps["horizontal_accuracy"] else 0

        gps_stamp = f"lat{lat}_lon{lon}"

        if 'color' in pic_types: # Take and save image
            image = cv2.imdecode(np.frombuffer(message.image_data, dtype="uint8"), cv2.IMREAD_UNCHANGED)
            out_path = output_dir / f"{config.name}_{picType}_{timestamp}_{gps_stamp}.png"
            cv2.imwrite(str(out_path), image)
            try:
                newdf = pd.DataFrame({"camera":"oak","picType":"color", "dateTime":timestamp, "latitude":[lat],"longitude":[lon],"accuracy":[acc]})
                save_csv("outputfile24_2.csv", newdf)
            except Exception as e:
                print(f"failed {e}")


        if not any(pt in ['color', 'depth'] for pt in pic_types):
            print(f"Unknown picType '{picType}'")

        break

async def capture_oak(config_paths: list[Path], output_dir: Path, picType="color"):
    """Capture frames from multiple OAK cameras simultaneously."""
    tasks = []
    for cfg_path in config_paths:
        config = proto_from_json_file(cfg_path, EventServiceConfig())
        tasks.append(asyncio.create_task(capture_single_oak(config, output_dir, picType="color")))
    
    await asyncio.gather(*tasks)


async def capture_rs(output_dir: Path, picType='color', cam1=None, cam2=None):
    
    ### Generate filename with GPS data if available ###
    loop = asyncio.get_event_loop()
    timestamp = datetime.now().strftime("%Y.%m.%d_%H%M_%S.%f")
    
    lat = np.round(latest_gps["latitude"],7) if latest_gps["latitude"] else 0
    lon = np.round(latest_gps["longitude"],7) if latest_gps["longitude"] else 0
    acc = np.round(latest_gps["horizontal_accuracy"],7) if latest_gps["horizontal_accuracy"] else 0

    gps_stamp = f"lat{lat}_lon{lon}"

    filename1 = f"RS1_{picType}_{timestamp}_{gps_stamp}.png"
    filename2 = f"RS2_{picType}_{timestamp}_{gps_stamp}.png"
    
    try:
        newdf = pd.DataFrame({"camera":"realsense","picType":"color", "dateTime":timestamp, "latitude":[lat],"longitude":[lon],"accuracy":[acc]})
        save_csv("outputfile24_2.csv", newdf)
    except Exception as e:
        print(f"failed {e}")

    await asyncio.gather(
        loop.run_in_executor(None, cam1.take_picture, filename1, picType),
        loop.run_in_executor(None, cam2.take_picture, filename2, picType)
    )




async def watch_gps(gps_config: Path):
    """Watch GPS messages and update the latest_gps dictionary."""
    global latest_gps
    config: EventServiceConfig = proto_from_json_file(gps_config, EventServiceConfig())
    async for event, msg in EventClient(config).subscribe(config.subscriptions[0]):
        if isinstance(msg, gps_pb2.GpsFrame):
            latest_gps["latitude"] = msg.latitude
            latest_gps["longitude"] = msg.longitude
            latest_gps["horizontal_accuracy"] = msg.horizontal_accuracy
            
            """ Below is additonal GPS data if needed 
            # latest_gps["altitude"] = msg.altitude
            # latest_gps["ground_speed"] = msg.ground_speed
            # latest_gps["horizontal_accuracy"] = msg.horizontal_accuracy
            # latest_gps["vertical_accuracy"] = msg.vertical_accuracy"""
        
async def gps_main(service_config_path: Path) -> None:
    """Run the gps service client.

    Args:
        service_config_path (Path): The path to the gps service config.
    """
    # create a client to the camera service
    config: EventServiceConfig = proto_from_json_file(service_config_path, EventServiceConfig())
    async for event, msg in EventClient(config).subscribe(config.subscriptions[0]):
        if isinstance(msg, gps_pb2.RelativePositionFrame):
            print_relative_position_frame(msg)
        elif isinstance(msg, gps_pb2.GpsFrame):
            print_gps_frame(msg)
        elif isinstance(msg, gps_pb2.EcefCoordinates):
            print_ecef_frame(msg)   
            
# ===================== PERPETUAL CAPTURE WITH COMMAND CONTROL =====================

async def user_command_listener(state: dict):
    """Listen for user commands from stdin."""
    print("Type 'p' (pause), 'r' (resume), or 's' (stop) to control the capture.")
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Run input() in a background thread to avoid blocking
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


async def capture_images(oak0_config_path: Path, oak1_config_path: Path, output_dir: Path, duration: float, gps_config: Path):
    """
    Runs indefinitely, capturing images unless paused or stopped via user command.
    """

    # ---- Check if USB drive is mounted ---- #
    if not os.path.ismount("/media/adminfarmng/crimson"):
        print("USB drive not mounted. Attempting to mount...")
        subprocess.run(["mountusb.sh"])
        if not os.path.ismount("/media/adminfarmng/crimson"):
            print("Failed to mount USB drive. Exiting.")
            return

    # --- Initialize RealSense cameras --- #
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

    config_paths = [oak0_config_path]
    if oak1_config_path:
        config_paths.append(oak1_config_path)

    gps_task = asyncio.create_task(watch_gps(gps_config))
    state = {"paused": False, "stop": False}
    command_task = asyncio.create_task(user_command_listener(state))

    if not Path("outputfile24_2.csv").exists():
        df = pd.DataFrame(columns= ["camera","picType", "dateTime", "latitude", "longitude","accuracy"])
        df.to_csv("outputfile24_2.csv", index=False)

    print("Capture loop started. Type commands to control it.")

    count = 0
    init_time = time.time()
    try:
        while not state["stop"]:
            start_time = time.time()
            if not state["paused"]:
                await asyncio.gather(
                    # capture_oak(config_paths, output_dir, "color",),
                    capture_rs(output_dir, "depth", cam1, cam2),
                    capture_rs(output_dir, "color", cam1, cam2)
                )
                count += 1
                elapsed = time.time() - start_time
                total_time = time.time() - init_time
                rate = 1 / elapsed if elapsed > 0 else float('inf')
                print(f"Captured image set {count} at {rate:.2f} Hz", end='\r')
                # await asyncio.sleep(max(0, duration - elapsed))  # maintain consistent interval
            else:
                await asyncio.sleep(0.1)  # idle while paused

    finally:
        gps_task.cancel()
        command_task.cancel()
        cam1.end_pipeline()
        cam2.end_pipeline()
        print(f"✅ Capture stopped after taking {count} images in {total_time} for an overall rate of {count/total_time}.")
        subprocess.run(["unmountusb.sh"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture still images from Amiga OAK + RealSense cameras")
    parser.add_argument("--oak0-config", type=Path, required=True, help="Path to  first OAK camera service config JSON")
    parser.add_argument("--oak1-config", type=Path, required=True, help="Path to second OAK camera service config JSON")
    parser.add_argument("--gps-config", type=Path, required=True, help="Path to GPS camera service config JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("/media/adminfarmng/crimson/current"), help="Directory to save images")
    parser.add_argument("--duration", type=float, default=1.5, help="How long to capture (seconds)")

    args = parser.parse_args()

    asyncio.run(capture_images(args.oak0_config, args.oak1_config, args.output_dir, args.duration, args.gps_config))

# sudo -E env PATH=$PATH python -u capture_images_gps.py --oak0-config configs/oak0_config.json --oak1-config configs/oak1_config.json --gps-config configs/gps_config.json --duration 5 |& tee -a ~/farmng_log.log