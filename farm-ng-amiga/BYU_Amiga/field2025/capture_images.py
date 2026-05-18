from __future__ import annotations

import pyrealsense2 as rs
import argparse
from datetime import datetime
import asyncio
from pathlib import Path
import os 

import cv2
import numpy as np
import time
import subprocess

from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from farm_ng.core.stamp import get_stamp_by_semantics_and_clock_type, StampSemantics

# ===================== REALSENSE CAMERA CLASS =====================
class RealSenseCamera():
    """A class defining a real sense camera"""
    def __init__(self, res = [1280, 720], serial=None, Path = None):
        # Configure color stream
        self.pipeline = rs.pipeline()
        self.path = Path
        config = rs.config()
        if serial: 
            config.enable_device(serial)

        # Enable streams
        config.enable_stream(rs.stream.color, res[0], res[1], rs.format.bgr8, framerate=30) # color stream
        config.enable_stream(rs.stream.depth, res[0], res[1], rs.format.z16, framerate=30) # depth stream

        # Start streaming
        self.pipeline.start(config)
        self.take_picture() # warm up camera
        time.sleep(0.5)


    def take_picture(self, file_name = 'firstpic.png', picType="color"): #"/media/adminfarmng/firstpic.png"
        
        try:
        # Wait a few frames so auto-exposure can settle
            while True:
                frames = self.pipeline.wait_for_frames()
                frame_dict = {"color":frames.get_color_frame(), "depth":frames.get_depth_frame()}
                pict_frame = frame_dict.get(picType)
                if pict_frame:
                    break
            # Convert to numpy (16-bit depth)
            color_image = np.asanyarray(pict_frame.get_data())
            # Save raw depth as 16-bit PNG
            out_path = self.path / file_name
            cv2.imwrite(str(out_path), color_image)

        except Exception as e:
            print(f"RealSense capture failed: {e}")

    def end_pipeline(self):
        self.pipeline.stop()

# ===================== MULTI-OAK CAPTURE =====================
async def capture_single_oak(config: EventServiceConfig, output_dir: Path):
    """Capture a single frame from one OAK service."""
    client = EventClient(config)
    async for event, message in client.subscribe(config.subscriptions[0], decode=True):
        stamp = (
            get_stamp_by_semantics_and_clock_type(event, StampSemantics.DRIVER_RECEIVE, "monotonic")
            or event.timestamps[0].stamp
        )

        # Decode image
        image = cv2.imdecode(np.frombuffer(message.image_data, dtype="uint8"), cv2.IMREAD_UNCHANGED)

        # Save frame
        out_path = output_dir / f"{config.name}_OAKpic_{stamp}.png"
        cv2.imwrite(str(out_path), image) # save OAK image
        break


async def capture_oak(config_paths: list[Path], output_dir: Path):
    """Capture frames from multiple OAK cameras simultaneously."""
    tasks = []
    for cfg_path in config_paths:
        config = proto_from_json_file(cfg_path, EventServiceConfig())
        tasks.append(asyncio.create_task(capture_single_oak(config, output_dir)))
    
    await asyncio.gather(*tasks)

   

async def capture_rs(output_dir: Path, cam1=None, cam2=None):
    
    ### Capture RealSense image ###
    timestamp = datetime.now().strftime("%Y.%m.%d_%H%M_%S.%f")
    filename1 = f"RS1_pic_{timestamp}.png"
    filename2 = f"RS2_pic_{timestamp}.png"
    cam1.take_picture(file_name=filename1, picType="color")
    cam2.take_picture(file_name=filename2, picType="color")
        
async def capture_images(oak0_config_path: Path, oak1_config_path: Path, output_dir: Path, duration: float):
    # CHECK MOUNT POINT
    if not os.path.ismount("/media/adminfarmng/TOSHIBA"):
        print("USB drive not mounted. Attempting to mount...")
        subprocess.run(["mountusb.sh"])
        if not os.path.ismount("/media/adminfarmng/TOSHIBA"):
            raise RuntimeError("USB drive could not mount")
    skip_rs = False
    # Initialize RealSense cameras
    try:
        cam1 = RealSenseCamera(serial="217222062474", Path = output_dir)
        cam2 = RealSenseCamera(serial="211622067750", Path = output_dir)
    except Exception as e:
            print(f"RealSense initialization failed: {e}")
            skip_rs = True

    config_paths = [oak0_config_path]
    print(config_paths)
    if oak1_config_path:
        config_paths.append(oak1_config_path)

    start_time = time.time()
    count = 0
    while True:
        await capture_oak(config_paths, output_dir)
        if not skip_rs:
            await capture_rs(output_dir, cam1, cam2)
        # await asyncio.gather(
        #     capture_oak(config_paths, output_dir),
        #     capture_rs(output_dir, cam1, cam2)
        # )
        count += 1
        if time.time() - start_time > duration or cv2.waitKey(1) & 0xFF == ord('q'):
            print(f"Captured {count} images in {duration} seconds.")
            if not skip_rs:
                cam1.end_pipeline()
                cam2.end_pipeline()
            break

def main():
    parser = argparse.ArgumentParser(description="Capture still images from Amiga OAK + RealSense cameras")
    parser.add_argument("--oak0-config", type=Path, required=True, help="Path to  first OAK camera service config JSON")
    parser.add_argument("--oak1-config", type=Path, required=False, help="Path to second OAK camera service config JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("/media/adminfarmng/TOSHIBA"), help="Directory to save images")
    parser.add_argument("--duration", type=float, default=1.5, help="How long to capture (seconds)")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(capture_images(args.oak0_config, args.oak1_config, args.output_dir, args.duration))

if __name__ == "__main__":
    main()

# python camera_headless.py --service-config service_config.json --duration 3
# ls /mnt/managed_home/farm-ng-user-byu-crimson/farm-ng-amiga/usbdrive