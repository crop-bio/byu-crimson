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


# ===============================================================
# ================ REALSENSE CAMERA CLASS =======================
# ===============================================================
class RealSenseCamera:
    """A class defining a RealSense camera"""

    def __init__(self, serial=None, output_dir=None):
        self.pipeline = rs.pipeline()
        self.output_dir = Path(output_dir)
        self.isBad = False
        config = rs.config()
        config.enable_device(serial)

        try:
            # Enable higher fps / resolution
            config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 15)
            config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 15)
            self.pipeline.start(config)
        except Exception as e:
            print(f"⚠️ Pipeline start failed at full res: {e}")
            try:
                config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 6)
                config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 6)
                self.pipeline.start(config)
            except Exception as e:
                print(f"❌ Pipeline totally failed: {e}")
                self.isBad = True

        # warm up pipeline asynchronously
        asyncio.create_task(self._warmup())

    async def _warmup(self):
        await asyncio.sleep(0.3)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.take_picture, "warmup.png", "color")

    def take_picture(self, file_name='firstpic.png', picType="color"):
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=2500)
            frame = frames.get_color_frame() if picType == "color" else frames.get_depth_frame()
            if not frame:
                raise RuntimeError("No frame received from RealSense camera.")
            img = np.asanyarray(frame.get_data())
            cv2.imwrite(str(self.output_dir / file_name), img)
        except Exception as e:
            print(f"RealSense capture failed: {e}")

    def end_pipeline(self):
        try:
            self.pipeline.stop()
        except Exception:
            pass


# ===============================================================
# =============== UTILS AND I/O HANDLERS ========================
# ===============================================================
async def async_save_csv(filename: Path, newdf: pd.DataFrame):
    """Non-blocking CSV append"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _append_csv, filename, newdf)


def _append_csv(filename: Path, newdf: pd.DataFrame):
    if filename.exists():
        df = pd.read_csv(filename)
        df = pd.concat([df, newdf], ignore_index=True)
    else:
        df = newdf
    df.to_csv(filename, index=False)


# ===============================================================
# ================ ASYNC CAMERA CAPTURE =========================
# ===============================================================
async def capture_rs(output_dir: Path, cam1: RealSenseCamera, cam2: RealSenseCamera, picType="color"):
    """Parallel capture from both RealSense cameras"""
    timestamp = datetime.now().strftime("%Y.%m.%d_%H%M_%S.%f")

    lat = np.round(latest_gps.get("latitude") or 0, 7)
    lon = np.round(latest_gps.get("longitude") or 0, 7)
    acc = np.round(latest_gps.get("horizontal_accuracy") or 0, 7)

    gps_stamp = f"lat{lat}_lon{lon}"
    filename1 = f"RS1_{picType}_{timestamp}_{gps_stamp}.png"
    filename2 = f"RS2_{picType}_{timestamp}_{gps_stamp}.png"

    newdf = pd.DataFrame({
        "camera": ["realsense", "realsense"],
        "picType": [picType, picType],
        "dateTime": [timestamp, timestamp],
        "latitude": [lat, lat],
        "longitude": [lon, lon],
        "accuracy": [acc, acc]
    })

    ### OPTIMIZATION: Parallel execution in thread pool ###
    loop = asyncio.get_event_loop()
    await asyncio.gather(
        loop.run_in_executor(None, cam1.take_picture, filename1, picType),
        loop.run_in_executor(None, cam2.take_picture, filename2, picType),
        async_save_csv(output_dir / "outputfile.csv", newdf)
    )


async def capture_oak(config_paths: list[Path], output_dir: Path, picType="color"):
    """Parallel capture from multiple OAK cameras"""
    async def capture_one(cfg_path: Path):
        config = proto_from_json_file(cfg_path, EventServiceConfig())
        async for event, msg in EventClient(config).subscribe(config.subscriptions[0], decode=True):
            img = cv2.imdecode(np.frombuffer(msg.image_data, np.uint8), cv2.IMREAD_UNCHANGED)
            timestamp = datetime.now().strftime("%Y.%m.%d_%H%M_%S.%f")
            lat = latest_gps.get("latitude") or 0
            lon = latest_gps.get("longitude") or 0
            gps_stamp = f"lat{lat}_lon{lon}"
            out = output_dir / f"{config.name}_{picType}_{timestamp}_{gps_stamp}.png"
            cv2.imwrite(str(out), img)
            break

    ### OPTIMIZATION: Parallel OAK capture ###
    await asyncio.gather(*(capture_one(p) for p in config_paths))


# ===============================================================
# ===================== GPS WATCHER =============================
# ===============================================================
async def watch_gps(gps_config: Path):
    global latest_gps
    config = proto_from_json_file(gps_config, EventServiceConfig())
    async for event, msg in EventClient(config).subscribe(config.subscriptions[0]):
        if isinstance(msg, gps_pb2.GpsFrame):
            latest_gps.update({
                "latitude": msg.latitude,
                "longitude": msg.longitude,
                "horizontal_accuracy": msg.horizontal_accuracy
            })


# ===============================================================
# ================= USER COMMAND HANDLER ========================
# ===============================================================
async def user_command_listener(state: dict):
    print("Commands: [p] pause, [r] resume, [s] stop")
    loop = asyncio.get_event_loop()
    while not state["stop"]:
        cmd = await loop.run_in_executor(None, input, ">>> ")
        cmd = cmd.strip().lower()
        if cmd == "p":
            state["paused"] = True
            print("⏸️ Paused.")
        elif cmd == "r":
            state["paused"] = False
            print("▶️ Resumed.")
        elif cmd == "s":
            state["stop"] = True
            print("🛑 Stop command.")
        else:
            print("Unknown command.")


# ===============================================================
# ===================== MAIN CAPTURE LOOP =======================
# ===============================================================
async def capture_images(oak0_config_path: Path, oak1_config_path: Path, output_dir: Path, duration: float, gps_config: Path):
    """Main control loop."""
    # Mount check
    if not os.path.ismount("/media/adminfarmng/crimson"):
        print("Mounting USB...")
        subprocess.run(["mountusb.sh"])
        if not os.path.ismount("/media/adminfarmng/crimson"):
            print("Mount failed. Exiting.")
            return

    cam1 = RealSenseCamera(serial="211622067750", output_dir=output_dir)
    cam2 = RealSenseCamera(serial="217222062474", output_dir=output_dir)

    config_paths = [oak0_config_path, oak1_config_path] if oak1_config_path else [oak0_config_path]

    # Start tasks
    gps_task = asyncio.create_task(watch_gps(gps_config))
    state = {"paused": False, "stop": False}
    cmd_task = asyncio.create_task(user_command_listener(state))

    out_csv = output_dir / "outputfile.csv"
    if not out_csv.exists():
        pd.DataFrame(columns=["camera", "picType", "dateTime", "latitude", "longitude", "accuracy"]).to_csv(out_csv, index=False)

    print("🚀 Capture loop started.")
    count = 0
    init_time = time.time()

    try:
        while not state["stop"]:
            if state["paused"]:
                await asyncio.sleep(0.1)
                continue

            ### OPTIMIZATION: Parallel RealSense + OAK capture ###
            start = time.time()
            await asyncio.gather(
                capture_rs(output_dir, cam1, cam2, "color"),
                # capture_oak(config_paths, output_dir, "color")
            )
            elapsed = time.time() - start
            count += 1
            rate = 1 / elapsed if elapsed else 0
            print(f"Captured set {count} at {rate:.2f} Hz", end="\r")

            # Maintain consistent loop interval
            await asyncio.sleep(max(0, duration - elapsed))
    finally:
        gps_task.cancel()
        cmd_task.cancel()
        cam1.end_pipeline()
        cam2.end_pipeline()
        total_time = time.time() - init_time
        print(f"\n✅ Done: {count} captures in {total_time:.1f}s ({count/total_time:.2f} Hz).")
        subprocess.run(["unmountusb.sh"])


# ===============================================================
# ======================= ENTRY POINT ===========================
# ===============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture still images from Amiga OAK + RealSense cameras")
    parser.add_argument("--oak0-config", type=Path, required=True)
    parser.add_argument("--oak1-config", type=Path, required=True)
    parser.add_argument("--gps-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("/media/adminfarmng/crimson/current"))
    parser.add_argument("--duration", type=float, default=1.5)
    args = parser.parse_args()

    asyncio.run(capture_images(args.oak0_config, args.oak1_config, args.output_dir, args.duration, args.gps_config))
