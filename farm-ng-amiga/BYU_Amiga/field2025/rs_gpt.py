#!/usr/bin/env python3
"""
Multi-RealSense D415 capture with farm-ng GPS integration.

- One thread per camera for capture (blocking RealSense SDK calls).
- One thread for saving image bytes to disk.
- One thread for CSV metadata writes.
- One background asyncio task (in its own thread) subscribing to farm-ng GPS messages.
- Terminal controls: p (pause), r (resume), s (stop). Press Enter after the key.
"""

import argparse
import os
import threading
import queue
import subprocess
import time
import csv
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import numpy as np
import cv2
import pyrealsense2 as rs
import playsound

# farm-ng imports (assumes installed on Amiga)
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from farm_ng.gps import gps_pb2

# ---------------------------
# Global shared state
# ---------------------------
latest_gps_lock = threading.Lock()
latest_gps: Dict[str, Optional[float]] = {
    "latitude": None,
    "longitude": None,
    "horizontal_accuracy": None,
    "last_update_ts": None,
}

# ---------------------------
# Helper: GPS subscriber (async) running in its own thread
# ---------------------------
def run_gps_subscriber_in_thread(gps_config_path: str):
    """
    Starts an asyncio loop in a separate thread that subscribes to the farm-ng GPS EventClient
    and updates the shared latest_gps dict.
    """
    import asyncio

    async def gps_task():
        nonlocal gps_config_path
        try:
            config: EventServiceConfig = proto_from_json_file(gps_config_path, EventServiceConfig())
            # subscribe to the first configured subscription
            async for event, msg in EventClient(config).subscribe(config.subscriptions[0]):
                if isinstance(msg, gps_pb2.GpsFrame):
                    with latest_gps_lock:
                        latest_gps["latitude"] = msg.latitude
                        latest_gps["longitude"] = msg.longitude
                        latest_gps["horizontal_accuracy"] = msg.horizontal_accuracy
                        latest_gps["last_update_ts"] = time.time()
        except Exception as e:
            print(f"[GPS] Exception in gps_task: {e}", file=sys.stderr)

    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(gps_task())
        loop.close()

    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    return th

# ---------------------------
# Camera capture thread
# ---------------------------
def camera_capture_thread(
    serial: str,
    cam_name: str,
    img_queue: queue.Queue,
    meta_queue: queue.Queue,
    stop_event: threading.Event,
    pause_event: threading.Event,
    fps: float,
    speed: float,
    notes: str,
):
    """
    Capture loop for a single RealSense camera. Places (color_bytes, depth_bytes, timestamp, cam_name) 
    onto img_queue for saving, and metadata onto meta_queue.
    """

    frame_count = 0                  #  Number of frames captured
    last_print_time = time.time()    #  Last time we printed status
    last_print_count = 0             #  Frames count at last print

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(serial)
    # Depth stream and color stream - keep width,height consistent
    width, height = 1920, 1080
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, 15)
    # config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 15)

    # Start streaming
    profile = pipeline.start(config)
    print(f"[{cam_name}] Started pipeline for serial {serial}")

    # Attempt to get depth scale
    # try:
    #     dev = profile.get_device()
    #     depth_sensor = dev.first_depth_sensor()
    #     depth_scale = depth_sensor.get_depth_scale()
    # except Exception:
    #     depth_scale = None

    # target period to achieve target fps
    period = 1.0 / fps if fps > 0 else 0.1

    try:
        while not stop_event.is_set():
            if pause_event.is_set():
                time.sleep(0.1)
                continue

            start_capture = time.time()
            frames = pipeline.wait_for_frames(timeout_ms=1500)  # blocking call
            color_frame = frames.get_color_frame()
            # depth_frame = frames.get_depth_frame()

            if not color_frame: # or not depth_frame:
                # frame missing - skip
                continue

            # Convert once
            color = np.asanyarray(color_frame.get_data())  # dtype=uint8, shape (H,W,3)
            # depth = np.asanyarray(depth_frame.get_data())  # dtype=uint16

            # Compress to bytes (non-blocking in Python; heavy encode might be CPU-bound but in C++)
            # JPEG for color, PNG for depth (keeps 16-bit)
            ok_c, color_buf = cv2.imencode(".jpg", color, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            # ok_d, depth_buf = cv2.imencode(".png", depth)  # PNG will preserve uint16

            if not ok_c: # or not ok_d:
                print(f"[{cam_name}] Failed to encode frames; skipping", file=sys.stderr)
                continue

            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")  # UTC timestamp
            color_bytes = color_buf.tobytes()
            # depth_bytes = depth_buf.tobytes()

            # Put into disk-writing queue (non-blocking if full: skip frame to avoid blocking camera)
            try:
                img_queue.put_nowait((cam_name, ts, color_bytes)) #, depth_bytes))
            except queue.Full:
                # if queue is full, drop the frame (prefer capturing new frames)
                print(f"[{cam_name}] Image queue full - dropping frame", file=sys.stderr)

            # Prepare metadata (gps snapshot) and put into meta queue
            with latest_gps_lock:
                lg = latest_gps.copy()
            # Normalize missing GPS values to empty string
            meta = {
                "serial": serial,
                "camera": cam_name,
                "timestamp": ts,
                "color_filename": f"{cam_name}_color_{ts}.jpg",
                "depth_filename": f"{cam_name}_depth_{ts}.png",
                "latitude": np.round(lg.get("latitude"),7) if lg.get("latitude") is not None else "",
                "longitude": np.round(lg.get("longitude"),7) if lg.get("longitude") is not None else "",
                "horizontal_accuracy": np.round(lg.get("horizontal_accuracy"),4) if lg.get("horizontal_accuracy") is not None else "",
                "gps_last_update_unix": lg.get("last_update_ts") if lg.get("last_update_ts") is not None else "",
                "speed": speed,
                "notes": notes,
            }
            try:
                meta_queue.put_nowait(meta)
            except queue.Full:
                print(f"[{cam_name}] Meta queue full - dropping metadata", file=sys.stderr)
            
            # ... after putting meta into meta_queue ...
            frame_count += 1  # <-- increment frame count

            # 🆕 Print live status once per second
            now = time.time()
            if now - last_print_time >= 1.0:
                frames_this_second = frame_count - last_print_count
                rate = frames_this_second / (now - last_print_time)
                with latest_gps_lock:
                    last_ts = latest_gps.get("last_update_ts")
                gps_status = "OK" if last_ts is not None and (time.time() - last_ts) < 5 else "Missing"
                print(f"\r[{cam_name}] Image #{frame_count:05d} | Rate: {rate:5.2f} Hz | GPS: {gps_status}", end='', flush=True)
                last_print_time = now
                last_print_count = frame_count

            

            # throttle to requested fps
            elapsed = time.time() - start_capture
            to_sleep = period - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)
    except Exception as ex:
        print(f"[{cam_name}] Exception: {ex}", file=sys.stderr)
        playsound.playsound('machine-error.mp3')
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass
        print(f"[{cam_name}] Stopped capture thread")

# ---------------------------
# Disk saver thread (writes image bytes)
# ---------------------------
def disk_saver_thread(img_queue: queue.Queue, save_root: str, stop_event: threading.Event):
    """
    Writes image bytes placed on img_queue to appropriate directories.
    Each item: (cam_name, ts, color_bytes, depth_bytes)
    """
    while not stop_event.is_set() or not img_queue.empty():
        try:
            cam_name, ts, color_bytes = img_queue.get(timeout=0.5)
            # cam_name, ts, color_bytes, depth_bytes = img_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        cam_dir = os.path.join(save_root, cam_name)
        os.makedirs(cam_dir, exist_ok=True)
        color_path = os.path.join(cam_dir, f"{cam_name}_color_{ts}.jpg")
        # depth_path = os.path.join(cam_dir, f"{cam_name}_depth_{ts}.png")

        try:
            # write bytes directly
            with open(color_path, "wb") as f:
                f.write(color_bytes)
            # with open(depth_path, "wb") as f:
            #     f.write(depth_bytes)
        except Exception as e:
            print(f"[saver] Error writing files for {cam_name} {ts}: {e}", file=sys.stderr)
            playsound.playsound('machine-error.mp3')

        img_queue.task_done()

    print("[saver] Exiting disk saver thread")

# ---------------------------
# CSV metadata writer thread
# ---------------------------
def csv_writer_thread(meta_queue: queue.Queue, save_root: str, stop_event: threading.Event, csv_name="captures.csv"):
    """
    Appends metadata rows to a CSV file located at save_root/<csv_name>.
    Expects meta dict keys: timestamp, camera, latitude, longitude, horizontal_accuracy, gps_last_update_unix
    """
    csv_path = os.path.join(save_root, csv_name)
    header = ["speed", "serial", "camera", "timestamp", "latitude", "longitude", "horizontal_accuracy", "gps_last_update_unix", "notes"]

    # Ensure directory exists
    os.makedirs(save_root, exist_ok=True)

    # If file doesn't exist, create and write header
    need_header = not os.path.exists(csv_path)
    f = open(csv_path, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=header)
    if need_header:
        writer.writeheader()
        f.flush()

    try:
        while not stop_event.is_set() or not meta_queue.empty():
            try:
                meta = meta_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Write row and flush for durability
            try:
                writer.writerow({
                    "speed": meta["speed"],
                    "serial": meta["serial"],
                    "camera": meta["camera"],
                    "timestamp": meta["timestamp"],
                    "latitude": meta["latitude"],
                    "longitude": meta["longitude"],
                    "horizontal_accuracy": meta["horizontal_accuracy"],
                    "gps_last_update_unix": meta["gps_last_update_unix"],
                    "notes": meta["notes"],
                })
                f.flush()
            except Exception as e:
                print(f"[csv_writer] Error writing meta: {e}", file=sys.stderr)
                playsound.playsound('machine-error.mp3')

            meta_queue.task_done()
    finally:
        f.close()
        print("[csv_writer] Exiting CSV writer thread")

# ---------------------------
# Utility: find connected RealSense devices
# ---------------------------
def get_connected_serials() -> List[str]:
    ctx = rs.context()
    serials = []
    for dev in ctx.query_devices():
        serials.append(dev.get_info(rs.camera_info.serial_number))
    return serials

# ---------------------------
# Simple monitor for GPS staleness
# ---------------------------
def gps_staleness_monitor(stop_event: threading.Event, warn_after_seconds=5.0):
    """
    Prints a warning when GPS hasn't updated in warn_after_seconds.
    """
    last_warned = False
    while not stop_event.is_set():
        with latest_gps_lock:
            last_ts = latest_gps.get("last_update_ts")
        if last_ts is None:
            if not last_warned:
                # print("[GPS monitor] No GPS fix yet.")
                last_warned = True
        else:
            age = time.time() - last_ts
            if age > warn_after_seconds:
                print(f"[GPS monitor] Warning: GPS last update {age:.1f}s ago.")
                last_warned = True
            else:
                last_warned = False
        time.sleep(1.0)
    print("[GPS monitor] Exiting monitor")

# ---------------------------
# Main: argparse, start threads, control loop
# ---------------------------
def main():
    ap = argparse.ArgumentParser(description="Multi-RealSense capture with farm-ng GPS metadata")
    ap.add_argument("--save-root", type=str, default="/media/adminfarmng/crimson/current", help="Base directory to save images & CSV")
    ap.add_argument("--gps-config", type=str, required=True, help="Path to farm-ng GPS EventServiceConfig JSON")
    ap.add_argument("--fps", type=float, default=3.0, help="Capture frequency (Hz) per camera")
    ap.add_argument("--serials", type=str, nargs="*", default=[], help="Optional: list of camera serial numbers to use. If omitted, auto-detects all connected RealSense devices.")
    ap.add_argument("--duration", type=float, default=0.0, help="Optional: run duration in seconds. 0 means run until stopped manually.")
    ap.add_argument("--queue-size", type=int, default=50, help="Max size for image queue per camera")
    ap.add_argument("--speed", type=float, default = 20, help="The speed in ft/min of the amiga")
    ap.add_argument("--notes", type=str, default=None, help="Optional: Any notes you want to add")
    args = ap.parse_args()

    save_root = args.save_root
    gps_config_path = args.gps_config
    fps = args.fps
    duration = args.duration
    queue_size = args.queue_size
    speed = args.speed
    notes = args.notes

    # # ---- Check if USB drive is mounted ---- #
    # if not os.path.ismount("/media/adminfarmng/crimson"):
    #     print("USB drive not mounted. Attempting to mount...")
    #     subprocess.run(["mountusb.sh"])
    #     if not os.path.ismount("/media/adminfarmng/crimson"):
    #         print("Failed to mount USB drive. Exiting.")
    #         return
        
    # subprocess.run(["source speaker.sh"])

    # Start GPS subscriber (async) in background thread
    print("[main] Starting GPS subscriber...")
    gps_thread = run_gps_subscriber_in_thread(gps_config_path)

    # Start GPS staleness monitor
    stop_event = threading.Event()
    gps_monitor_thread = threading.Thread(target=gps_staleness_monitor, args=(stop_event,), daemon=True)
    gps_monitor_thread.start()

    # Determine serials
    if args.serials:
        serials = args.serials
    else:
        serials = get_connected_serials()
    if not serials:
        print("No RealSense devices found. Exiting.", file=sys.stderr)
        return

    print(f"[main] Using devices: {serials}")

    # Create queues and threads
    img_queue = queue.Queue(maxsize=queue_size * len(serials))
    meta_queue = queue.Queue(maxsize=queue_size * len(serials))

    # Events for control
    pause_event = threading.Event()  # when set -> paused
    stop_capture_event = threading.Event()

    # Start disk saver & CSV writer
    saver_thread = threading.Thread(target=disk_saver_thread, args=(img_queue, save_root, stop_capture_event), daemon=True)
    saver_thread.start()

    csv_thread = threading.Thread(target=csv_writer_thread, args=(meta_queue, save_root, stop_capture_event), daemon=True)
    csv_thread.start()

     # Start camera capture threads
    cam_threads = []
    cam_dict = {'217222062474':"RS1", '319522065401':"RS2", '211622067750':"RS3"}
    for serial in serials:
        cam_name = cam_dict.get(serial)
        t = threading.Thread(
            target=camera_capture_thread,
            args=(serial, cam_name, img_queue, meta_queue, stop_capture_event, pause_event, fps, speed, notes),
            daemon=True,
        )
        t.start()
        cam_threads.append(t)

    # Control loop (stdin). Use simple blocking input - press p<Enter>, r<Enter>, s<Enter>
    print("[main] Controls: 'p' + Enter = pause, 'r' + Enter = resume, 's' + Enter = stop and exit.")
    start_time = time.time()
    try:
        while True:
            # Optional duration exit
            if duration > 0 and (time.time() - start_time) >= duration:
                print("[main] Duration elapsed; stopping.")
                break

            # Non-blocking wait for user input with timeout so duration can be enforced
            print("[main] Type control command (p/r/s) and press Enter:", end='\r', flush=True)
            # Use a small timeout on input() by checking availability with select if on Posix
            if sys.platform != "win32":
                import select
                dr, dw, de = select.select([sys.stdin], [], [], 3.0)
                if dr:
                    line = sys.stdin.readline().strip().lower()
                else:
                    line = ""
            else:
                # On Windows, fallback to blocking input with small timeout: we can't easily non-blocking without extra modules.
                # So just block for user input; user can rely on Ctrl+C to stop.
                try:
                    line = input().strip().lower()
                except EOFError:
                    line = ""

            if line == "p":
                if not pause_event.is_set():
                    pause_event.set()
                    print("[main] Paused capture.")
                else:
                    print("[main] Already paused.")
            elif line == "r":
                if pause_event.is_set():
                    pause_event.clear()
                    print("[main] Resumed capture.")
                else:
                    print("[main] Already running.")
            elif line == "s":
                print("[main] Stop requested.")
                break
            else:
                # no command entered (timeout) - continue
                pass

    except KeyboardInterrupt:
        print("[main] KeyboardInterrupt received - stopping.")
    finally:
        print("[main] Signalling threads to stop...")
        # request stop
        stop_capture_event.set()
        # clear pause so threads don't hang
        pause_event.clear()

        # Wait for queues to drain
        img_queue.join()
        meta_queue.join()

        # Allow saver/csv writer to exit
        time.sleep(0.5)

        # signal final stop
        stop_event.set()

        # unmount drive
        subprocess.run(["unmountusb.sh"])

        print("[main] Exiting.")

if __name__ == "__main__":
    main()
