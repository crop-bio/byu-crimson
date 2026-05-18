#!/usr/bin/env python3
"""
Multi-RealSense D415 capture with farm-ng GPS integration.

- One thread per camera for capture (blocking RealSense SDK calls).
- One thread for saving image bytes to disk.
- One thread for CSV metadata writes.
- One background asyncio task (in its own thread) subscribing to farm-ng GPS messages.
- Terminal controls: p (pause), r (resume), s (stop). Press Enter after the key.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import argparse
import os
import threading
import queue
import subprocess
import time
import csv
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import cv2
import pyrealsense2 as rs
import playsound

# farm-ng imports (assumes installed on Amiga)
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from farm_ng.gps import gps_pb2
from farm_ng.core.stamp import get_stamp_by_semantics_and_clock_type
from farm_ng.core.stamp import StampSemantics
from farm_ng.filter.filter_pb2 import DivergenceCriteria
from farm_ng_core_pybind import Pose3F64

import logging
logging.getLogger("grpc").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
# # Save original stderr
# original_stderr = sys.stderr
# sys.stderr = open(os.devnull, "w")  # suppress all stderr

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
latest_filter_lock = threading.Lock()
latest_filter: Dict[str, Optional[float]] = {
    "orientation": None,
    "uncertainty": None,
}

# ---------------------------
# Helper: Filter subscriber
def run_filter_subscriber_in_thread(filter_config_path: str):
    """
    Starts an asyncio loop in a separate thread that subscribes to the farm-ng filter EventClient
    and updates the shared latest_filter dict.
    """
    async def filter_task():
        nonlocal filter_config_path
        try:
            config: EventServiceConfig = proto_from_json_file(filter_config_path, EventServiceConfig())

            async for event, message in EventClient(config).subscribe(config.subscriptions[0], decode=True):
                # Find the monotonic service send timestamp (this is the time the filter calculated the state),
                # or the first timestamp if not available.
                stamp = (
                    get_stamp_by_semantics_and_clock_type(event, StampSemantics.SERVICE_SEND, "monotonic")
                    or event.timestamps[0].stamp
                )

                # Unpack the filter state message
                
                pose: Pose3F64 = Pose3F64.from_proto(message.pose)
                orientation: float = message.heading
                uncertainties: list[float] = [message.uncertainty_diagonal.data[i] for i in range(3)]
                divergence_criteria: list[DivergenceCriteria] = [
                    DivergenceCriteria.Name(criteria) for criteria in message.divergence_criteria
                ]
                with latest_filter_lock:
                    latest_filter["filt_x"] = pose.translation[0]
                    latest_filter["filt_y"] = pose.translation[1]
                    latest_filter["filt_x_unc"] = uncertainties[0]
                    latest_filter["filt_y_unc"] = uncertainties[1]
                    latest_filter["filt_orient"] = orientation
                    latest_filter["filt_orient_unc"] = uncertainties[2]
                # Print some key details about the filter state
                # print("\n###################")
                # print(f"[Filter] Timestamp: {stamp}")
                # print("Filter state received with pose:")
                # print(f"x: {pose.translation[0]:.3f} m, y: {pose.translation[1]:.3f} m, orientation: {orientation:.3f} rad")
                # print(f"Parent frame: {pose.frame_a} -> Child frame: {pose.frame_b}")
                # print(f"Filter has converged: {message.has_converged}")
                # print("Pose uncertainties:")
                # print(f"x: {uncertainties[0]:.3f} m, y: {uncertainties[1]:.3f} m, orientation: {uncertainties[2]:.3f} rad")
                if not message.has_converged:
                    # print(f"Filter diverged due to: {divergence_criteria}")
                    pass
        except Exception as e:
            print(f"[Filter] Exception in filter_subscriber: {e}", file=sys.stderr)

    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(filter_task())
        loop.close()

    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    return th
# ---------------------------
# Helper: GPS subscriber (async) running in its own thread
# ---------------------------
def run_gps_subscriber_in_thread(gps_config_path: str):
    """
    Starts an asyncio loop in a separate thread that subscribes to the farm-ng GPS EventClient
    and updates the shared latest_gps dict.
    """

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
# Camera capture thread
# ---------------------------
RealSenseStreamProfile = Tuple[Tuple[int, int, int], Tuple[int, int, int]]

REAL_SENSE_D415_HIGH_RES_LOW_FPS_PROFILE: RealSenseStreamProfile = (
    (1920, 1080, 6),
    (1280, 720, 6),
)

REAL_SENSE_D405_HIGH_RES_LOW_FPS_PROFILE: RealSenseStreamProfile = (
    (1280, 720, 5),
    (1280, 720, 5),
)

realsense_start_lock = threading.Lock()


def get_realsense_stream_profile(device_name: str) -> RealSenseStreamProfile:
    if "D405" in device_name:
        return REAL_SENSE_D405_HIGH_RES_LOW_FPS_PROFILE
    return REAL_SENSE_D415_HIGH_RES_LOW_FPS_PROFILE


def start_realsense_rgbd_pipeline(
    serial: str,
    cam_name: str,
    stream_profile: RealSenseStreamProfile,
) -> Tuple[rs.pipeline, rs.pipeline_profile, Optional[float]]:
    """
    Start a RealSense color+depth pipeline at the required high-resolution,
    low-FPS profile. Do not fall back to lower resolutions silently.
    """
    color_profile, depth_profile = stream_profile
    color_width, color_height, color_fps = color_profile
    depth_width, depth_height, depth_fps = depth_profile

    with realsense_start_lock:
        pipeline = rs.pipeline()
        config = rs.config()
        config.enable_device(serial)
        config.enable_stream(rs.stream.color, color_width, color_height, rs.format.bgr8, color_fps)
        config.enable_stream(rs.stream.depth, depth_width, depth_height, rs.format.z16, depth_fps)

        try:
            profile = pipeline.start(config)
        except Exception as e:
            print(
                f"[{cam_name}] ERROR: Failed to start required high-resolution RealSense profile "
                f"for serial {serial}: color {color_width}x{color_height}@{color_fps}, "
                f"depth {depth_width}x{depth_height}@{depth_fps}. Error: {e}",
                file=sys.stderr,
            )
            try:
                pipeline.stop()
            except Exception:
                pass
            raise

    try:
        depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
    except Exception:
        depth_scale = None
    print(
        f"[{cam_name}] Started required high-resolution pipeline for serial {serial} "
        f"color {color_width}x{color_height}@{color_fps}, "
        f"depth {depth_width}x{depth_height}@{depth_fps}"
    )
    return pipeline, profile, depth_scale


def get_realsense_timestamp_domain(frame: rs.frame) -> str:
    try:
        return str(frame.get_frame_timestamp_domain())
    except Exception:
        return ""


def realsense_capture_thread(
    serial: str,
    cam_name: str,
    img_queue: queue.Queue,
    meta_queue: queue.Queue,
    stop_event: threading.Event,
    pause_event: threading.Event,
    fps: float,
    speed: float,
    notes: str,
    stream_profile: RealSenseStreamProfile,
    capture_phase_seconds: float,
):
    """
    Capture loop for a single RealSense camera. Places (color_bytes, depth_bytes, timestamp, cam_name) 
    onto img_queue for saving, and metadata onto meta_queue.
    """

    frame_count = 0                  #  Number of frames captured
    last_print_time = time.time()    #  Last time we printed status
    last_print_count = 0             #  Frames count at last print
    last_frame_error_time = 0.0

    try:
        pipeline, profile, depth_scale = start_realsense_rgbd_pipeline(serial, cam_name, stream_profile)
    except Exception as e:
        print(f"[{cam_name}] Failed to start RealSense pipeline for serial {serial}: {e}", file=sys.stderr)
        return

    # target period to achieve target fps
    period = 1.0 / fps if fps > 0 else 0.1
    next_capture_time = time.monotonic() + capture_phase_seconds

    try:
        while not stop_event.is_set():
            if pause_event.is_set():
                time.sleep(0.1)
                continue

            now_monotonic = time.monotonic()
            if now_monotonic < next_capture_time:
                time.sleep(min(0.05, next_capture_time - now_monotonic))
                continue

            start_capture = time.time()
            try:
                frames = pipeline.wait_for_frames(timeout_ms=3000)  # blocking call
                host_capture_dt = datetime.now(timezone.utc)
                host_capture_unix = host_capture_dt.timestamp()
                host_capture_monotonic_ns = time.monotonic_ns()
            except Exception as e:
                now = time.time()
                if now - last_frame_error_time >= 5.0:
                    print(f"[{cam_name}] wait_for_frames failed: {e}", file=sys.stderr)
                    last_frame_error_time = now
                time.sleep(0.1)
                continue
            next_capture_time += period
            if next_capture_time < time.monotonic():
                next_capture_time = time.monotonic() + period
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()

            if not color_frame or not depth_frame:
                # frame missing - skip
                continue

            ts = host_capture_dt.strftime("%Y%m%d_%H%M%S_%fZ")  # UTC timestamp, taken before encoding
            host_capture_time_utc = host_capture_dt.isoformat().replace("+00:00", "Z")
            color_realsense_timestamp_ms = color_frame.get_timestamp()
            depth_realsense_timestamp_ms = depth_frame.get_timestamp()
            color_frame_number = color_frame.get_frame_number()
            depth_frame_number = depth_frame.get_frame_number()
            color_timestamp_domain = get_realsense_timestamp_domain(color_frame)
            depth_timestamp_domain = get_realsense_timestamp_domain(depth_frame)

            # Convert once
            color = np.asanyarray(color_frame.get_data())  # dtype=uint8, shape (H,W,3)
            depth = np.asanyarray(depth_frame.get_data())  # dtype=uint16

            # Compress to bytes (non-blocking in Python; heavy encode might be CPU-bound but in C++)
            # JPEG for color, PNG for depth (keeps 16-bit)
            ok_c, color_buf = cv2.imencode(".jpg", color, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            ok_d, depth_buf = cv2.imencode(".png", depth)  # PNG preserves uint16 depth units

            if not ok_c or not ok_d:
                print(f"[{cam_name}] Failed to encode frames; skipping", file=sys.stderr)
                continue

            color_bytes = color_buf.tobytes()
            depth_bytes = depth_buf.tobytes()

            # Put image into disk-writing queue (non-blocking if full: skip frame to avoid blocking camera)
            try:
                img_queue.put_nowait((cam_name, ts, color_bytes, depth_bytes))
            except queue.Full:
                # if queue is full, drop the frame (prefer capturing new frames)
                print(f"[{cam_name}] Image queue full - dropping frame", file=sys.stderr)

            # Prepare metadata (gps snapshot) and put into meta queue
            with latest_gps_lock:
                lg = latest_gps.copy()
            with latest_filter_lock:
                lf = latest_filter.copy()
            # Normalize missing GPS values to empty string
            meta = {
                "serial": serial,
                "camera": cam_name,
                "timestamp": ts,
                "color_filename": f"{cam_name}_color_{ts}.jpg",
                "depth_filename": f"{cam_name}_depth_{ts}.png",
                "depth_scale_meters": depth_scale if depth_scale is not None else "",
                "host_capture_time_utc": host_capture_time_utc,
                "host_capture_unix": host_capture_unix,
                "host_capture_monotonic_ns": host_capture_monotonic_ns,
                "realsense_timestamp_ms": color_realsense_timestamp_ms,
                "color_realsense_timestamp_ms": color_realsense_timestamp_ms,
                "depth_realsense_timestamp_ms": depth_realsense_timestamp_ms,
                "color_frame_number": color_frame_number,
                "depth_frame_number": depth_frame_number,
                "color_timestamp_domain": color_timestamp_domain,
                "depth_timestamp_domain": depth_timestamp_domain,
                "latitude": np.round(lg.get("latitude"),7) if lg.get("latitude") is not None else "",
                "longitude": np.round(lg.get("longitude"),7) if lg.get("longitude") is not None else "",
                "horizontal_accuracy": np.round(lg.get("horizontal_accuracy"),4) if lg.get("horizontal_accuracy") is not None else "",
                "gps_last_update_unix": lg.get("last_update_ts") if lg.get("last_update_ts") is not None else "",
                "filt_x": lf.get("filt_x") if lf.get("filt_x") is not None else "",
                "filt_y": lf.get("filt_y") if lf.get("filt_y") is not None else "",
                "filt_x_unc": lf.get("filt_x_unc") if lf.get("filt_x_unc") is not None else "",
                "filt_y_unc": lf.get("filt_y_unc") if lf.get("filt_y_unc") is not None else "",
                "heading": lf.get("filt_orient") if lf.get("filt_orient") is not None else "",
                "heading_unc": lf.get("filt_orient_unc") if lf.get("filt_orient_unc") is not None else "",
                "speed": speed,
                "notes": notes,
            }
            try:
                meta_queue.put_nowait(meta)
            except queue.Full:
                print(f"[{cam_name}] Meta queue full - dropping metadata", file=sys.stderr)
            
            # ... after putting meta into meta_queue ...
            frame_count += 1  # <-- increment frame count

            # Print live status once per second
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
    except Exception as e:
        print(f"[{cam_name}] Exception: {e}", file=sys.stderr)
        # playsound.playsound('machine-error.mp3')
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass
        print(f"[{cam_name}] Stopped capture thread")


def oak_capture_thread(
    cam_name: str,
    config: EventServiceConfig,
    img_queue: queue.Queue,
    meta_queue: queue.Queue,
    stop_event: threading.Event,
    pause_event: threading.Event,
    fps: float,
    speed: float,
    notes: str,
):
    """
    Capture loop for a single OAK camera via farm-ng Amiga EventService.
    Mirrors realsense_capture_thread behavior.
    """
    async def oak_capture_async():
        nonlocal cam_name, config, img_queue, meta_queue, stop_event, pause_event, fps, speed, notes
        frame_count = 0
        last_print_time = time.time()
        last_print_count = 0

        period = 1.0 / fps if fps > 0 else 0.1

        client = EventClient(config)

        try:
            async for event, message in client.subscribe(config.subscriptions[0], decode=True):
                if stop_event.is_set():
                    break

                if pause_event.is_set():
                    time.sleep(0.1)
                    continue

                start_capture = time.time()

                # Timestamp (prefer driver receive, fallback to first event timestamp)
                stamp = (
                    get_stamp_by_semantics_and_clock_type(
                        event,
                        StampSemantics.DRIVER_RECEIVE,
                        "monotonic",
                    )
                    or event.timestamps[0].stamp
                )

                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")

                # Decode image from OAK message
                try:
                    image = cv2.imdecode(
                        np.frombuffer(message.image_data, dtype=np.uint8),
                        cv2.IMREAD_COLOR,
                    )
                except Exception as e:
                    print(f"[{cam_name}] Failed to decode image: {e}", file=sys.stderr)
                    continue

                if image is None:
                    continue

                # Encode to JPEG (same as RealSense)
                ok, color_buf = cv2.imencode(
                    ".jpg",
                    image,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 90],
                )
                if not ok:
                    print(f"[{cam_name}] JPEG encode failed", file=sys.stderr)
                    continue

                color_bytes = color_buf.tobytes()

                # Push image to queue
                try:
                    img_queue.put_nowait((cam_name, ts, color_bytes))
                except queue.Full:
                    print(f"[{cam_name}] Image queue full - dropping frame", file=sys.stderr)

                # Metadata
                with latest_gps_lock:
                    lg = latest_gps.copy()
                with latest_filter_lock:
                    lf = latest_filter.copy()

                meta = {
                    "serial": "",  # OAKs usually don’t expose serial the same way
                    "camera": cam_name,
                    "timestamp": ts,
                    "color_filename": f"{cam_name}_color_{ts}.jpg",
                    "depth_filename": "",
                    "depth_scale_meters": "",
                    "host_capture_time_utc": "",
                    "host_capture_unix": "",
                    "host_capture_monotonic_ns": "",
                    "realsense_timestamp_ms": "",
                    "color_realsense_timestamp_ms": "",
                    "depth_realsense_timestamp_ms": "",
                    "color_frame_number": "",
                    "depth_frame_number": "",
                    "color_timestamp_domain": "",
                    "depth_timestamp_domain": "",
                    "latitude": np.round(lg.get("latitude"), 7) if lg.get("latitude") is not None else "",
                    "longitude": np.round(lg.get("longitude"), 7) if lg.get("longitude") is not None else "",
                    "horizontal_accuracy": np.round(lg.get("horizontal_accuracy"), 4) if lg.get("horizontal_accuracy") is not None else "",
                    "gps_last_update_unix": lg.get("last_update_ts") if lg.get("last_update_ts") is not None else "",
                    "filt_x": lf.get("filt_x") if lf.get("filt_x") is not None else "",
                    "filt_y": lf.get("filt_y") if lf.get("filt_y") is not None else "",
                    "filt_x_unc": lf.get("filt_x_unc") if lf.get("filt_x_unc") is not None else "",
                    "filt_y_unc": lf.get("filt_y_unc") if lf.get("filt_y_unc") is not None else "",
                    "heading": lf.get("filt_orient") if lf.get("filt_orient") is not None else "",
                    "heading_unc": lf.get("filt_orient_unc") if lf.get("filt_orient_unc") is not None else "",
                    "speed": speed,
                    "notes": notes,
                }

                try:
                    meta_queue.put_nowait(meta)
                except queue.Full:
                    print(f"[{cam_name}] Meta queue full - dropping metadata", file=sys.stderr)

                frame_count += 1

                # Status print (same style as RealSense)
                now = time.time()
                if now - last_print_time >= 1.0:
                    frames_this_second = frame_count - last_print_count
                    rate = frames_this_second / (now - last_print_time)
                    with latest_gps_lock:
                        last_ts = latest_gps.get("last_update_ts")
                    gps_status = "OK" if last_ts and (time.time() - last_ts) < 5 else "Missing"
                    print(
                        f"\r[{cam_name}] Image #{frame_count:05d} | Rate: {rate:5.2f} Hz | GPS: {gps_status}",
                        end="",
                        flush=True,
                    )
                    last_print_time = now
                    last_print_count = frame_count

                # FPS throttle
                elapsed = time.time() - start_capture
                to_sleep = period - elapsed
                if to_sleep > 0:
                    time.sleep(to_sleep)

        except Exception as e:
            print(f"[{cam_name}] Exception: {e}", file=sys.stderr)
            # playsound.playsound("machine-error.mp3")

        finally:
            print(f"[{cam_name}] Stopped capture thread")


    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(oak_capture_async())
        loop.close()

    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    return th

# ---------------------------
# Disk saver thread (writes image bytes)
# ---------------------------
def disk_saver_thread(img_queue: queue.Queue, save_root: str, stop_event: threading.Event):
    """
    Writes image bytes placed on img_queue to appropriate directories.
    RealSense items: (cam_name, ts, color_bytes, depth_bytes)
    OAK items: (cam_name, ts, color_bytes)
    """
    while not stop_event.is_set() or not img_queue.empty():
        try:
            item = img_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        if len(item) == 3:
            cam_name, ts, color_bytes = item
            depth_bytes = None
        elif len(item) == 4:
            cam_name, ts, color_bytes, depth_bytes = item
        else:
            print(f"[saver] Unexpected image queue item with {len(item)} values", file=sys.stderr)
            img_queue.task_done()
            continue

        cam_dir = os.path.join(save_root, cam_name)
        os.makedirs(cam_dir, exist_ok=True)
        color_path = os.path.join(cam_dir, f"{cam_name}_color_{ts}.jpg")
        depth_path = os.path.join(cam_dir, f"{cam_name}_depth_{ts}.png")

        try:
            # write bytes directly
            with open(color_path, "wb") as f:
                f.write(color_bytes)
            if depth_bytes is not None:
                with open(depth_path, "wb") as f:
                    f.write(depth_bytes)
        except Exception as e:
            print(f"[saver] Error writing files for {cam_name} {ts}: {e}", file=sys.stderr)
            # playsound.playsound('machine-error.mp3')

        img_queue.task_done()

    print("[saver] Exiting disk saver thread")

# ---------------------------
# CSV metadata writer thread
# ---------------------------
def ensure_csv_header(csv_path: str, header: List[str]) -> bool:
    """
    Returns True when the caller needs to write a header. If an existing CSV has
    an older header, rewrite it with the current columns and preserve a backup.
    """
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return True

    with open(csv_path, "r", newline="") as f:
        existing_header = next(csv.reader(f), [])

    if existing_header == header:
        return False

    backup_path = f"{csv_path}.bak_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    os.replace(csv_path, backup_path)

    with open(backup_path, "r", newline="") as src, open(csv_path, "w", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=header)
        writer.writeheader()
        for row in reader:
            writer.writerow({field: row.get(field, "") for field in header})

    print(f"[csv_writer] Updated CSV header; previous file backed up to {backup_path}")
    return False


def csv_writer_thread(meta_queue: queue.Queue, save_root: str, stop_event: threading.Event, csv_name="captures.csv"):
    """
    Appends metadata rows to a CSV file located at save_root/<csv_name>.
    Expects meta dict keys: timestamp, camera, latitude, longitude, horizontal_accuracy, gps_last_update_unix
    """
    csv_path = os.path.join(save_root, csv_name)
    print('SAVING FILE TO :', csv_path)
    header = [
        "speed",
        "serial",
        "camera",
        "timestamp",
        "color_filename",
        "depth_filename",
        "depth_scale_meters",
        "host_capture_time_utc",
        "host_capture_unix",
        "host_capture_monotonic_ns",
        "realsense_timestamp_ms",
        "color_realsense_timestamp_ms",
        "depth_realsense_timestamp_ms",
        "color_frame_number",
        "depth_frame_number",
        "color_timestamp_domain",
        "depth_timestamp_domain",
        "latitude",
        "longitude",
        "horizontal_accuracy",
        "filt_x",
        "filt_x_unc",
        "filt_y",
        "filt_y_unc",
        "heading",
        "heading_uncertainty",
        "gps_last_update_unix",
        "notes",
    ]

    # Ensure directory exists
    os.makedirs(save_root, exist_ok=True)

    # If file doesn't exist, create and write header
    need_header = ensure_csv_header(csv_path, header)
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
                    "color_filename": meta.get("color_filename", ""),
                    "depth_filename": meta.get("depth_filename", ""),
                    "depth_scale_meters": meta.get("depth_scale_meters", ""),
                    "host_capture_time_utc": meta.get("host_capture_time_utc", ""),
                    "host_capture_unix": meta.get("host_capture_unix", ""),
                    "host_capture_monotonic_ns": meta.get("host_capture_monotonic_ns", ""),
                    "realsense_timestamp_ms": meta.get("realsense_timestamp_ms", ""),
                    "color_realsense_timestamp_ms": meta.get("color_realsense_timestamp_ms", ""),
                    "depth_realsense_timestamp_ms": meta.get("depth_realsense_timestamp_ms", ""),
                    "color_frame_number": meta.get("color_frame_number", ""),
                    "depth_frame_number": meta.get("depth_frame_number", ""),
                    "color_timestamp_domain": meta.get("color_timestamp_domain", ""),
                    "depth_timestamp_domain": meta.get("depth_timestamp_domain", ""),
                    "latitude": meta["latitude"],
                    "longitude": meta["longitude"],
                    "horizontal_accuracy": meta["horizontal_accuracy"],
                    "filt_x": meta["filt_x"],
                    "filt_x_unc": meta["filt_x_unc"],
                    "filt_y": meta["filt_y"],
                    "filt_y_unc": meta["filt_y_unc"],
                    "heading": meta["heading"],
                    "heading_uncertainty": meta["heading_unc"],
                    "gps_last_update_unix": meta["gps_last_update_unix"],
                    "notes": meta["notes"],
                })
                f.flush()
            except Exception as e:
                print(f"[csv_writer] Error writing meta: {e}", file=sys.stderr)
                # playsound.playsound('machine-error.mp3')

            meta_queue.task_done()
    finally:
        f.close()
        print("[csv_writer] Exiting CSV writer thread")

# ---------------------------
# Utility: find connected RealSense devices
# ---------------------------
def get_connected_realsense_devices() -> List[Tuple[str, str]]:
    ctx = rs.context()
    devices = []
    for dev in ctx.query_devices():
        serial = dev.get_info(rs.camera_info.serial_number)
        name = dev.get_info(rs.camera_info.name)
        devices.append((serial, name))
    return devices


def get_connected_serials() -> List[str]:
    return [serial for serial, _ in get_connected_realsense_devices()]

def test_oak_connection(config_path: str, timeout_sec: float = 3.0) -> bool:
    """
    Returns True if an OAK service publishes at least one image within timeout.
    """

    async def _probe():
        config = proto_from_json_file(config_path, EventServiceConfig())
        client = EventClient(config)
        try:
            async for _, message in client.subscribe(
                config.subscriptions[0], decode=True
            ):
                # We got one message — OAK is alive
                print('OAK connection successful for', config.name)
                return True
        except Exception:
            return False

    try:
        return asyncio.run(asyncio.wait_for(_probe(), timeout=timeout_sec))
    except asyncio.TimeoutError:
        return False


# ---------------------------
# Main: argparse, start threads, control loop
# ---------------------------
def main(args=None):
    
    ### ---- Parse arguments ---- ###
    
    gps_config_path = "configs/gps_config.json"
    filter_config_path = "configs/filter_config.json"
    oak0_config_path = "configs/oak0_config.json"
    oak1_config_path = "configs/oak1_config.json"
    duration = args.duration
    save_root = args.save_root
    queue_size = args.queue_size
    fps = args.fps
    speed = args.speed
    notes = args.notes

    ### ---- Check if USB drive is mounted ---- ###
    if save_root.startswith("/media/adminfarmng/crimson"):
        if not os.path.ismount("/media/adminfarmng/crimson"):
            print("USB drive not mounted. Attempting to mount...")
            subprocess.run(["mountusb.sh"])
            if not os.path.ismount("/media/adminfarmng/crimson"):
                print("Failed to mount USB drive. Exiting.")
                return
    else:
        print(f"WARNING: Saving to local path: {save_root}")
        
    # subprocess.run(["source speaker.sh"])

    ### ---- Start Services & Threads ---- ###

    # Start GPS and filter subscribers (async) in background threads
    # OAK service has to use asyncio and not just threading. Not sure why
    
    gps_thread = run_gps_subscriber_in_thread(gps_config_path) # Starts an asyncio loop in a separate thread
    print("Started GPS subscriber")
    filter_thread = run_filter_subscriber_in_thread(filter_config_path)
    print("Started Filter subscriber")

    # Start GPS staleness monitor
    stop_event = threading.Event()
    gps_monitor_thread = threading.Thread(target=gps_staleness_monitor, args=(stop_event,), daemon=True)
    gps_monitor_thread.start()

    # Determine serial numbers of realsense cameras
    realsense_devices = get_connected_realsense_devices()
    serials = [serial for serial, _ in realsense_devices]
    device_names = {serial: name for serial, name in realsense_devices}
    if not serials:
        print("No RealSense devices found. Exiting.", file=sys.stderr)
        return
    print(f"[main] Using devices: {realsense_devices}")

    # Determine oaks
    oak_configs = [oak0_config_path, oak1_config_path]
    online_oaks = []
    for config_path in oak_configs:
        if test_oak_connection(config_path):
            online_oaks.append(config_path)
    print(f"[main] Using OAK cameras: {online_oaks}")
    # Create queues 
    img_queue = queue.Queue(maxsize=queue_size * (len(serials) + len(online_oaks)))
    meta_queue = queue.Queue(maxsize=queue_size * (len(serials) + len(online_oaks)))
    realsense_capture_period = 1.0 / fps if fps > 0 else 0.1
    realsense_stagger_interval = (
        realsense_capture_period / len(serials)
        if len(serials) > 1
        else 0.0
    )

    # Create events for control
    pause_event = threading.Event()  # when set -> paused
    stop_capture_event = threading.Event()

    # Start file saver & CSV writer threads
    saver_thread = threading.Thread(target=disk_saver_thread, args=(img_queue, save_root, stop_capture_event), daemon=True)
    saver_thread.start()
    csv_thread = threading.Thread(target=csv_writer_thread, args=(meta_queue, save_root, stop_capture_event), daemon=True)
    csv_thread.start()

    # Start OAK camera capture threads
    for cfg_path in online_oaks:
        config = proto_from_json_file(cfg_path, EventServiceConfig())
        print('Starting OAK camera:', config.name)
        oak_capture_thread(config.name, config, img_queue, meta_queue, stop_capture_event, pause_event, fps, speed, notes)

    # Start real sense camera capture threads
    # cam_dict = {'217222062474':"RS1", '319522065401':"RS2", '211622067750':"RS3", '335122272680': "RS405_1"}
    # cam_dict = {'217222062474':"RS1", '319522065401':"RS2", '211622067750':"RS3"}
    # Newest dict updated with 5 RS cams
    cam_dict = {'217222062474':"RS415_1", '319522065401':"RS415_3", '211622067750':"RS415_2", '335122272680': "RS405_2", '323622273314': "RS405_1", '323622273079': "RS405_3"}
    for cam_index, serial in enumerate(serials):

        cam = cam_dict.get(serial)
        print('serial: ', serial, 'cam: ', cam)
        if cam is None:
            print('Unknown camera with serial', serial)
            cam = "unknown_camera"
        device_name = device_names.get(serial, "")
        realsense_stream_profile = get_realsense_stream_profile(device_name)
        capture_phase_seconds = cam_index * realsense_stagger_interval
        color_profile, depth_profile = realsense_stream_profile
        print(
            f"[main] {cam} ({device_name}) phase offset {capture_phase_seconds:.3f}s, "
            f"required RGBD profile: color {color_profile[0]}x{color_profile[1]}@{color_profile[2]} / "
            f"depth {depth_profile[0]}x{depth_profile[1]}@{depth_profile[2]}"
        )
        args = (
            serial,
            cam,
            img_queue,
            meta_queue,
            stop_capture_event,
            pause_event,
            fps,
            speed,
            notes,
            realsense_stream_profile,
            capture_phase_seconds,
        )
        t = threading.Thread(target=realsense_capture_thread, args=args, daemon=True,)
        t.start()


    ##########################
    # ---- Control loop ---- #
    ##########################
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
    finally: # To do on exit
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
        # Restore stderr when done
        # sys.stderr.close()
        # sys.stderr = original_stderr

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Multi-RealSense capture with farm-ng GPS metadata")
    ap.add_argument("--duration", type=float, default=0.0, help="Optional: run duration in seconds. 0 means run until stopped manually.")
    ap.add_argument("--save-root", type=str, default="/media/adminfarmng/crimson/current", help="Base directory to save images & CSV")
    ap.add_argument("--queue-size", type=int, default=50, help="Max size for image queue per camera")
    ap.add_argument("--fps", type=float, default=3.0, help="Capture frequency (Hz) per camera")
    ap.add_argument("--speed", type=float, default = 20, help="The speed in ft/min of the amiga")
    ap.add_argument("--notes", type=str, default=None, help="Optional: Any notes you want to add")
    args = ap.parse_args()
    main(args)

# sudo -E env PATH=$PATH python -u full_service.py --speed 30 --fps 1 --notes '5 RS 2 OAK  Dead Grasses' |& tee -a ~/farmng_log.log 
