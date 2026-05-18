#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import cv2
import numpy as np


APP_SERVICE = "full-calibration.service"
ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "calibration_data"
SAMPLE_DATA_DIR = ROOT_DIR / "sample_data" / "calibration"
OAK_CONFIG_CANDIDATES = [
    ROOT_DIR / "farm-ng-amiga" / "BYU_Amiga" / "field2025" / "configs" / "oak0_config.json",
    ROOT_DIR / "farm-ng-amiga" / "BYU_Amiga" / "field2025" / "configs" / "oak1_config.json",
    ROOT_DIR / "farm-ng-amiga" / "BYU_Amiga" / "utils" / "configs" / "oak0_config.json",
    ROOT_DIR / "farm-ng-amiga" / "BYU_Amiga" / "utils" / "configs" / "oak1_config.json",
]


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Full Calibration</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef2ed;
      --panel: #fbfcf8;
      --ink: #172018;
      --muted: #5d6d60;
      --line: #ced9cf;
      --accent: #245d42;
      --accent-2: #2d5870;
      --accent-3: #7b3d24;
      --good: #1d6b42;
      --bad: #98342b;
      --shadow: rgba(23, 32, 24, 0.13);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      color: var(--ink);
      background:
        linear-gradient(140deg, rgba(36, 93, 66, 0.12), transparent 36%),
        linear-gradient(315deg, rgba(45, 88, 112, 0.12), transparent 34%),
        var(--bg);
      padding: 22px;
    }
    main {
      width: min(1120px, 100%);
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 18px 54px var(--shadow);
      padding: 26px;
    }
    .top {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0;
      font-size: 34px;
      letter-spacing: 0;
    }
    .sub {
      margin-top: 6px;
      color: var(--muted);
      font-size: 15px;
      max-width: 720px;
      line-height: 1.4;
    }
    .status {
      min-width: 240px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f5f8f2;
      padding: 14px 16px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }
    .grid {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .stack {
      display: grid;
      gap: 16px;
      align-items: start;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .panel-head {
      padding: 13px 15px;
      background: #f1f5ee;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
      color: var(--muted);
      font-weight: 700;
    }
    .body {
      padding: 15px;
    }
    label {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    input, select {
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 11px;
      font-size: 16px;
      background: #fbfcf8;
      color: var(--ink);
    }
    .form-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 14px;
    }
    .field-wide {
      grid-column: 1 / -1;
    }
    .buttons {
      display: grid;
      gap: 10px;
    }
    button {
      min-height: 50px;
      border: 0;
      border-radius: 8px;
      color: white;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      padding: 0 14px;
    }
    button:disabled {
      cursor: default;
      opacity: 0.58;
    }
    .primary { background: var(--accent); }
    .secondary { background: var(--accent-2); }
    .warn { background: var(--accent-3); }
    .exit { background: #4f5964; }
    .notice {
      min-height: 24px;
      margin: 14px 0;
      color: var(--muted);
      font-size: 15px;
    }
    .notice.good { color: var(--good); }
    .notice.bad { color: var(--bad); }
    .help {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
      margin: 0;
    }
    .camera-list {
      display: grid;
      gap: 10px;
    }
    .camera-empty {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }
    .camera-row {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px 12px;
      background: #fbfcf8;
    }
    .camera-head {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
      flex-wrap: wrap;
    }
    .camera-id {
      font-size: 14px;
      font-weight: 700;
      color: var(--ink);
      word-break: break-word;
    }
    .camera-meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .pill.good {
      background: rgba(29, 107, 66, 0.12);
      color: var(--good);
    }
    .pill.warn {
      background: rgba(123, 61, 36, 0.12);
      color: var(--accent-3);
    }
    .pill.bad {
      background: rgba(152, 52, 43, 0.12);
      color: var(--bad);
    }
    pre {
      margin: 0;
      min-height: 520px;
      max-height: 680px;
      overflow: auto;
      padding: 16px;
      background: #172018;
      color: #eef4ed;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    @media (max-width: 820px) {
      body { padding: 12px; }
      main { padding: 18px; }
      .grid { grid-template-columns: 1fr; }
      .form-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <div class="top">
      <div>
        <h1>Full Calibration</h1>
        <div class="sub">
          Pull factory intrinsics from OAK and RealSense cameras, then capture checkerboard detections for extrinsic measurements.
          Keep the board still during each capture sample so every detected camera sees the same board pose.
        </div>
      </div>
      <div class="status" id="status">Loading calibration status...</div>
    </div>

    <div class="grid">
      <div class="stack">
        <div class="panel">
          <div class="panel-head">Controls</div>
          <div class="body">
            <div class="form-grid">
              <div>
                <label for="cols">Inner corners across</label>
                <input id="cols" type="number" min="2" step="1" value="7">
              </div>
              <div>
                <label for="rows">Inner corners down</label>
                <input id="rows" type="number" min="2" step="1" value="5">
              </div>
              <div class="field-wide">
                <label for="square">Square size in meters</label>
                <input id="square" type="number" min="0.001" step="0.001" value="0.031">
              </div>
            </div>
            <div class="buttons">
              <button class="secondary" id="scan">Scan Cameras</button>
              <button class="primary" id="intrinsics">Pull Factory Intrinsics</button>
              <button class="primary" id="sample">Capture Checkerboard Sample</button>
              <button class="warn" id="exit">Return to Apps</button>
            </div>
            <div class="notice" id="notice"></div>
            <p class="help">
              Factory intrinsics are profile-specific. The app records all reported RealSense video profiles and the OAK calibration payload.
              Checkerboard samples use the live color image profile selected by each camera at capture time.
              Inner corners are one fewer than the number of printed squares in each direction.
            </p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">Stitch Session</div>
          <div class="body">
            <div class="form-grid">
              <div class="field-wide">
                <label for="session-gap">Session gap in minutes</label>
                <input id="session-gap" type="number" min="1" step="1" value="15">
              </div>
              <div class="field-wide">
                <label for="root-camera">Root camera for stitched output</label>
                <select id="root-camera">
                  <option value="">Auto select</option>
                </select>
              </div>
            </div>
            <div class="buttons">
              <button class="secondary" id="stitch">Stitch Fresh Session</button>
            </div>
            <p class="help">
              Uses the newest contiguous block of checkerboard samples. If the gap between runs exceeds the session gap,
              older runs are excluded so stale pre-move calibrations do not get mixed into the current rig.
            </p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">Robot Frame Anchor</div>
          <div class="body">
            <div class="form-grid">
              <div class="field-wide">
                <label for="anchor-camera">Reference camera</label>
                <select id="anchor-camera">
                  <option value="">Select camera</option>
                </select>
              </div>
              <div>
                <label for="anchor-x">Camera X from robot origin (m)</label>
                <input id="anchor-x" type="number" step="0.001" value="0">
              </div>
              <div>
                <label for="anchor-y">Camera Y from robot origin (m)</label>
                <input id="anchor-y" type="number" step="0.001" value="0">
              </div>
              <div>
                <label for="anchor-z">Camera Z from robot origin (m)</label>
                <input id="anchor-z" type="number" step="0.001" value="0">
              </div>
              <div>
                <label for="anchor-roll">Roll (deg)</label>
                <input id="anchor-roll" type="number" step="0.1" value="0">
              </div>
              <div>
                <label for="anchor-pitch">Pitch (deg)</label>
                <input id="anchor-pitch" type="number" step="0.1" value="0">
              </div>
              <div>
                <label for="anchor-yaw">Yaw (deg)</label>
                <input id="anchor-yaw" type="number" step="0.1" value="0">
              </div>
            </div>
            <div class="buttons">
              <button class="secondary" id="anchor">Anchor To Robot Frame</button>
            </div>
            <p class="help">
              Enter the selected camera pose in robot coordinates. Leave roll, pitch, and yaw at 0 only if that camera's axes
              already align with the robot frame.
            </p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">Per-Camera Status</div>
          <div class="body">
            <div class="camera-list" id="camera-status">
              <div class="camera-empty">Loading camera history...</div>
            </div>
            <p class="help" style="margin-top: 12px;">
              Partial samples stay on disk. A missed checkerboard in the latest capture does not erase an earlier successful solve for that camera.
              After any camera move, only samples taken after that move should be treated as valid.
            </p>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">Report</div>
        <pre id="output">Waiting for a command...</pre>
      </div>
    </div>
  </main>

  <script>
    const output = document.getElementById("output");
    const notice = document.getElementById("notice");
    const status = document.getElementById("status");
    const cameraStatus = document.getElementById("camera-status");
    const buttons = [...document.querySelectorAll("button")];

    function settings() {
      return {
        pattern_cols: Number(document.getElementById("cols").value),
        pattern_rows: Number(document.getElementById("rows").value),
        square_size_m: Number(document.getElementById("square").value)
      };
    }

    function stitchSettings() {
      return {
        session_gap_minutes: Number(document.getElementById("session-gap").value),
        root_camera_id: document.getElementById("root-camera").value || ""
      };
    }

    function anchorSettings() {
      return {
        anchor_camera_id: document.getElementById("anchor-camera").value || "",
        camera_x_m: Number(document.getElementById("anchor-x").value),
        camera_y_m: Number(document.getElementById("anchor-y").value),
        camera_z_m: Number(document.getElementById("anchor-z").value),
        roll_deg: Number(document.getElementById("anchor-roll").value),
        pitch_deg: Number(document.getElementById("anchor-pitch").value),
        yaw_deg: Number(document.getElementById("anchor-yaw").value)
      };
    }

    function setBusy(busy) {
      buttons.forEach((button) => button.disabled = busy);
    }

    function render(data) {
      output.textContent = JSON.stringify(data, null, 2);
      output.scrollTop = 0;
    }

    function setNotice(message, level) {
      notice.textContent = message || "";
      notice.className = "notice" + (level ? " " + level : "");
    }

    function escapeHtml(value) {
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function formatTimestamp(value) {
      if (!value) {
        return "never";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      return `${date.toLocaleString()} UTC`;
    }

    function resultPill(result) {
      if (result === "solved") {
        return { label: "Solved", className: "good" };
      }
      if (result === "not_found") {
        return { label: "Board Not Found", className: "warn" };
      }
      if (result === "solve_failed" || result === "capture_error") {
        return { label: "Needs Attention", className: "bad" };
      }
      return { label: "No History", className: "warn" };
    }

    function renderCameraStatus(cameras) {
      if (!cameras || cameras.length === 0) {
        cameraStatus.innerHTML = '<div class="camera-empty">No saved checkerboard history yet.</div>';
        return;
      }
      cameraStatus.innerHTML = cameras.map((camera) => {
        const pill = resultPill(camera.last_attempt_result);
        const successText = camera.last_success_at ? formatTimestamp(camera.last_success_at) : "never";
        const attemptText = camera.last_attempt_at ? formatTimestamp(camera.last_attempt_at) : "never";
        const message = camera.last_attempt_message || "No captures recorded yet.";
        return `
          <div class="camera-row">
            <div class="camera-head">
              <div class="camera-id">${escapeHtml(camera.camera_id)}</div>
              <div class="pill ${pill.className}">${pill.label}</div>
            </div>
            <div class="camera-meta">Last success: ${escapeHtml(successText)}</div>
            <div class="camera-meta">Latest attempt: ${escapeHtml(attemptText)}</div>
            <div class="camera-meta">${escapeHtml(message)}</div>
          </div>
        `;
      }).join("");
    }

    function populateCameraSelect(selectId, cameras, emptyLabel) {
      const select = document.getElementById(selectId);
      const currentValue = select.value;
      const options = [`<option value="">${escapeHtml(emptyLabel)}</option>`];
      (cameras || []).forEach((camera) => {
        options.push(`<option value="${escapeHtml(camera.camera_id)}">${escapeHtml(camera.camera_id)}</option>`);
      });
      select.innerHTML = options.join("");
      if ((cameras || []).some((camera) => camera.camera_id === currentValue)) {
        select.value = currentValue;
      }
    }

    async function getJson(path) {
      const response = await fetch(path);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }
      return data;
    }

    async function postJson(path, body) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }
      return data;
    }

    async function refreshStatus() {
      try {
        const data = await getJson("/api/status");
        const latest = data.latest_sample_summary || {};
        const latestLine = latest.created_at
          ? `Latest sample result: ${latest.solved_count}/${latest.capture_count} solved, ${latest.error_count} capture errors`
          : "Latest sample result: none";
        status.textContent =
          `Output: ${data.output_dir}\\n` +
          `Latest intrinsics: ${data.latest_intrinsics || "none"}\\n` +
          `Latest sample: ${data.latest_sample || "none"}\\n` +
          `Latest stitched: ${data.latest_stitched || "none"}\\n` +
          `Latest robot frame: ${data.latest_robot_frame || "none"}\\n` +
          latestLine;
        renderCameraStatus(data.camera_status || []);
        populateCameraSelect("root-camera", data.camera_status || [], "Auto select");
        populateCameraSelect("anchor-camera", data.camera_status || [], "Select camera");
      } catch (error) {
        status.textContent = "Status unavailable.";
        cameraStatus.innerHTML = '<div class="camera-empty">Camera history unavailable.</div>';
      }
    }

    async function run(path, message, body) {
      setBusy(true);
      setNotice(message, "");
      try {
        const data = await postJson(path, body);
        render(data);
        setNotice("Complete.", "good");
      } catch (error) {
        setNotice(error.message || "Command failed.", "bad");
      } finally {
        await refreshStatus();
        setBusy(false);
      }
    }

    document.getElementById("scan").addEventListener("click", () => {
      run("/api/scan", "Scanning connected cameras...");
    });

    document.getElementById("intrinsics").addEventListener("click", () => {
      run("/api/intrinsics", "Pulling factory intrinsics...");
    });

    document.getElementById("sample").addEventListener("click", () => {
      run("/api/capture-sample", "Capturing checkerboard sample...", settings());
    });

    document.getElementById("stitch").addEventListener("click", () => {
      run("/api/stitch-session", "Stitching the newest calibration session...", stitchSettings());
    });

    document.getElementById("anchor").addEventListener("click", () => {
      run("/api/anchor-robot-frame", "Anchoring stitched calibration to the robot frame...", anchorSettings());
    });

    document.getElementById("exit").addEventListener("click", async () => {
      try {
        await postJson("/api/exit");
      } catch (error) {
      }
      window.location.href = `${window.location.protocol}//${window.location.hostname}/apps/launcher`;
    });

    refreshStatus();
  </script>
</body>
</html>
"""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def sorted_matching_paths(base_dir: Path, pattern: str) -> list[Path]:
    if not base_dir.exists():
        return []
    return sorted(base_dir.glob(pattern), key=lambda path: path.stat().st_mtime_ns, reverse=True)


def read_paths(pattern: str) -> list[Path]:
    live_paths = sorted_matching_paths(OUTPUT_DIR, pattern)
    if live_paths:
        return live_paths
    return sorted_matching_paths(SAMPLE_DATA_DIR, pattern)


def latest_path(pattern: str) -> Path | None:
    files = read_paths(pattern)
    return files[0] if files else None


def latest_file(pattern: str) -> str:
    path = latest_path(pattern)
    return path.name if path else ""


def sample_report_paths() -> list[Path]:
    return read_paths("checkerboard_sample_*/sample_report.json")


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_report(prefix: str, data: dict[str, Any]) -> Path:
    ensure_output_dir()
    path = OUTPUT_DIR / f"{prefix}_{utc_stamp()}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def normalize_camera_id(camera_id: str) -> str:
    value = camera_id.strip()
    if value.startswith("oak:") and value.endswith("_config"):
        return f"oak:{value.split(':', 1)[1][:-7]}"
    return value


def parse_report_datetime(value: str, fallback_path: Path | None = None) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        if fallback_path is not None:
            return datetime.fromtimestamp(fallback_path.stat().st_mtime, tz=timezone.utc)
        return datetime.now(timezone.utc)


def validate_session_gap(data: dict[str, Any]) -> float:
    gap_minutes = float(data.get("session_gap_minutes", 15.0))
    if not math.isfinite(gap_minutes) or gap_minutes <= 0:
        raise RuntimeError("Session gap must be a positive number of minutes.")
    return gap_minutes


def load_sample_report_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for report_path in sample_report_paths():
        try:
            report = load_json_file(report_path)
        except (OSError, json.JSONDecodeError):
            continue
        created_at = str(report.get("created_at", ""))
        created_at_dt = parse_report_datetime(created_at, report_path)
        entries.append(
            {
                "report": report,
                "report_path": report_path,
                "sample_name": report_path.parent.name,
                "created_at": created_at,
                "created_at_dt": created_at_dt,
            }
        )
    entries.sort(key=lambda entry: entry["created_at_dt"], reverse=True)
    return entries


def current_session_entries(session_gap_minutes: float) -> list[dict[str, Any]]:
    entries = load_sample_report_entries()
    if not entries:
        return []
    session = [entries[0]]
    previous_dt = entries[0]["created_at_dt"]
    for entry in entries[1:]:
        gap_minutes = (previous_dt - entry["created_at_dt"]).total_seconds() / 60.0
        if gap_minutes > session_gap_minutes:
            break
        session.append(entry)
        previous_dt = entry["created_at_dt"]
    session.reverse()
    return session


def latest_sample_summary() -> dict[str, Any]:
    for report_path in sample_report_paths():
        try:
            report = load_json_file(report_path)
        except (OSError, json.JSONDecodeError):
            continue
        captures = report.get("captures", [])
        errors = report.get("errors", [])
        solved_ids = [capture["camera_id"] for capture in captures if capture.get("detection", {}).get("solve_pnp_ok")]
        found_ids = [capture["camera_id"] for capture in captures if capture.get("detection", {}).get("found")]
        return {
            "created_at": report.get("created_at", ""),
            "sample_dir": report.get("sample_dir", str(report_path.parent)),
            "capture_count": len(captures),
            "found_count": len(found_ids),
            "solved_count": len(solved_ids),
            "error_count": len(errors),
            "solved_camera_ids": solved_ids,
            "found_camera_ids": found_ids,
            "error_camera_ids": [error.get("camera_id", "") for error in errors],
        }
    return {}


def attempt_result_from_detection(detection: dict[str, Any]) -> tuple[str, str]:
    if detection.get("solve_pnp_ok"):
        return "solved", str(detection.get("message", "Checkerboard pose solved."))
    if detection.get("found"):
        return "solve_failed", str(detection.get("message", "Checkerboard detected, but pose solve failed."))
    return "not_found", str(detection.get("message", "Checkerboard was not detected."))


def camera_history_status() -> list[dict[str, Any]]:
    history: dict[str, dict[str, Any]] = {}
    for report_path in sample_report_paths():
        try:
            report = load_json_file(report_path)
        except (OSError, json.JSONDecodeError):
            continue
        created_at = str(report.get("created_at", ""))
        sample_dir = Path(str(report.get("sample_dir", report_path.parent)))
        sample_name = sample_dir.name

        for capture in report.get("captures", []):
            camera_id = normalize_camera_id(str(capture.get("camera_id", "")))
            if not camera_id:
                continue
            entry = history.setdefault(
                camera_id,
                {
                    "camera_id": camera_id,
                    "kind": str(capture.get("kind", "")),
                    "label": str(capture.get("serial") or capture.get("name") or camera_id),
                    "last_attempt_at": "",
                    "last_attempt_sample": "",
                    "last_attempt_result": "",
                    "last_attempt_message": "",
                    "last_success_at": "",
                    "last_success_sample": "",
                },
            )
            result, message = attempt_result_from_detection(capture.get("detection", {}))
            if not entry["last_attempt_at"]:
                entry["last_attempt_at"] = created_at
                entry["last_attempt_sample"] = sample_name
                entry["last_attempt_result"] = result
                entry["last_attempt_message"] = message
            if capture.get("detection", {}).get("solve_pnp_ok") and not entry["last_success_at"]:
                entry["last_success_at"] = created_at
                entry["last_success_sample"] = sample_name

        for error in report.get("errors", []):
            camera_id = normalize_camera_id(str(error.get("camera_id", "")))
            if not camera_id:
                continue
            kind = camera_id.split(":", 1)[0] if ":" in camera_id else ""
            entry = history.setdefault(
                camera_id,
                {
                    "camera_id": camera_id,
                    "kind": kind,
                    "label": camera_id.split(":", 1)[-1],
                    "last_attempt_at": "",
                    "last_attempt_sample": "",
                    "last_attempt_result": "",
                    "last_attempt_message": "",
                    "last_success_at": "",
                    "last_success_sample": "",
                },
            )
            if not entry["last_attempt_at"]:
                entry["last_attempt_at"] = created_at
                entry["last_attempt_sample"] = sample_name
                entry["last_attempt_result"] = "capture_error"
                entry["last_attempt_message"] = str(error.get("error", "Capture failed."))

    return sorted(history.values(), key=lambda entry: (entry["kind"], entry["label"], entry["camera_id"]))


def solved_camera_board_transforms(report: dict[str, Any]) -> dict[str, np.ndarray]:
    solved: dict[str, np.ndarray] = {}
    for capture in report.get("captures", []):
        camera_id = normalize_camera_id(str(capture.get("camera_id", "")))
        if not camera_id:
            continue
        detection = capture.get("detection", {})
        if not detection.get("solve_pnp_ok"):
            continue
        matrix = detection.get("camera_T_board", {}).get("matrix_4x4")
        if matrix is None:
            continue
        solved[camera_id] = np.array(matrix, dtype=np.float64)
    return solved


def choose_stitch_root_camera_id(requested_camera_id: str, solved_counts: dict[str, int], adjacency: dict[str, dict[str, Any]]) -> str:
    requested = normalize_camera_id(requested_camera_id)
    if requested:
        if requested not in solved_counts:
            raise RuntimeError(f"Requested root camera {requested} does not have a fresh successful solve in the current session.")
        return requested
    if not solved_counts:
        raise RuntimeError("No successful checkerboard solves are available in the current session.")
    return sorted(
        solved_counts,
        key=lambda camera_id: (solved_counts[camera_id], len(adjacency.get(camera_id, {})), camera_id),
        reverse=True,
    )[0]


def stitch_calibration_session(settings: dict[str, Any]) -> dict[str, Any]:
    session_gap_minutes = validate_session_gap(settings)
    session_entries = current_session_entries(session_gap_minutes)
    if not session_entries:
        raise RuntimeError("No saved checkerboard samples are available to stitch.")

    adjacency: dict[str, dict[str, dict[str, Any]]] = {}
    solved_counts: dict[str, int] = {}
    fresh_camera_ids: set[str] = set()
    sample_summaries: list[dict[str, Any]] = []
    for entry in session_entries:
        report = entry["report"]
        transforms = solved_camera_board_transforms(report)
        solved_ids = sorted(transforms)
        sample_summaries.append(
            {
                "sample_name": entry["sample_name"],
                "created_at": entry["created_at"],
                "report_path": str(entry["report_path"]),
                "solved_camera_ids": solved_ids,
            }
        )
        for camera_id in solved_ids:
            fresh_camera_ids.add(camera_id)
            solved_counts[camera_id] = solved_counts.get(camera_id, 0) + 1
        for from_camera_id, from_transform in transforms.items():
            neighbors = adjacency.setdefault(from_camera_id, {})
            for to_camera_id, to_transform in transforms.items():
                if from_camera_id == to_camera_id:
                    continue
                neighbors[to_camera_id] = {
                    "transform": from_transform @ invert_transform(to_transform),
                    "sample_name": entry["sample_name"],
                    "created_at": entry["created_at"],
                }

    root_camera_id = choose_stitch_root_camera_id(str(settings.get("root_camera_id", "")), solved_counts, adjacency)
    root_T_cameras: dict[str, np.ndarray] = {root_camera_id: np.eye(4, dtype=np.float64)}
    parent_edges: dict[str, dict[str, str]] = {}
    queue: deque[str] = deque([root_camera_id])
    while queue:
        current_camera_id = queue.popleft()
        for neighbor_camera_id, edge in adjacency.get(current_camera_id, {}).items():
            if neighbor_camera_id in root_T_cameras:
                continue
            root_T_cameras[neighbor_camera_id] = root_T_cameras[current_camera_id] @ edge["transform"]
            parent_edges[neighbor_camera_id] = {
                "from_camera_id": current_camera_id,
                "sample_name": str(edge["sample_name"]),
                "created_at": str(edge["created_at"]),
            }
            queue.append(neighbor_camera_id)

    expected_camera_ids = sorted(entry["camera_id"] for entry in camera_history_status()) or sorted(fresh_camera_ids)
    reachable_camera_ids = sorted(root_T_cameras)
    missing_fresh_camera_ids = sorted(set(expected_camera_ids) - fresh_camera_ids)
    unstitched_fresh_camera_ids = sorted(fresh_camera_ids - set(reachable_camera_ids))
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root_camera_id": root_camera_id,
        "session": {
            "session_gap_minutes": session_gap_minutes,
            "sample_count": len(session_entries),
            "sample_names": [entry["sample_name"] for entry in session_entries],
            "sample_report_paths": [str(entry["report_path"]) for entry in session_entries],
            "oldest_sample_at": session_entries[0]["created_at"],
            "newest_sample_at": session_entries[-1]["created_at"],
            "expected_camera_ids": expected_camera_ids,
            "fresh_camera_ids": sorted(fresh_camera_ids),
            "missing_fresh_camera_ids": missing_fresh_camera_ids,
            "unstitched_fresh_camera_ids": unstitched_fresh_camera_ids,
        },
        "sample_summaries": sample_summaries,
        "root_T_cameras": {
            camera_id: transform_to_dict(transform)
            for camera_id, transform in sorted(root_T_cameras.items())
        },
        "graph_edges_used": parent_edges,
        "notes": [
            "root_T_cameras maps each camera frame into the selected root camera frame.",
            "Only sample reports from the newest contiguous session are stitched together.",
            "Missing fresh cameras were not solved successfully in the current session.",
            "Unstitched fresh cameras had successful solves but no overlap path into the selected root camera graph.",
        ],
    }
    path = write_json_report("stitched_calibration", report)
    report["saved_to"] = str(path)
    return report


def rotation_matrix_from_rpy_deg(roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    yaw = math.radians(yaw_deg)
    cx, sx = math.cos(roll), math.sin(roll)
    cy, sy = math.cos(pitch), math.sin(pitch)
    cz, sz = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float64)
    ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float64)
    rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return rz @ ry @ rx


def validate_anchor_settings(data: dict[str, Any]) -> tuple[str, float, float, float, float, float, float]:
    anchor_camera_id = normalize_camera_id(str(data.get("anchor_camera_id", "")))
    if not anchor_camera_id:
        raise RuntimeError("Select a reference camera before anchoring to the robot frame.")
    values = []
    for key in ["camera_x_m", "camera_y_m", "camera_z_m", "roll_deg", "pitch_deg", "yaw_deg"]:
        value = float(data.get(key, 0.0))
        if not math.isfinite(value):
            raise RuntimeError(f"{key} must be a finite numeric value.")
        values.append(value)
    return (anchor_camera_id, *values)


def anchor_stitched_calibration_to_robot_frame(settings: dict[str, Any]) -> dict[str, Any]:
    anchor_camera_id, camera_x_m, camera_y_m, camera_z_m, roll_deg, pitch_deg, yaw_deg = validate_anchor_settings(settings)
    stitched_path = latest_path("stitched_calibration_*.json")
    if stitched_path is None:
        raise RuntimeError("No stitched calibration report exists yet. Run Stitch Fresh Session first.")
    stitched_report = load_json_file(stitched_path)
    root_T_cameras_raw = stitched_report.get("root_T_cameras", {})
    if anchor_camera_id not in root_T_cameras_raw:
        raise RuntimeError(f"Reference camera {anchor_camera_id} was not present in the latest stitched calibration.")

    robot_T_anchor = np.eye(4, dtype=np.float64)
    robot_T_anchor[:3, :3] = rotation_matrix_from_rpy_deg(roll_deg, pitch_deg, yaw_deg)
    robot_T_anchor[:3, 3] = np.array([camera_x_m, camera_y_m, camera_z_m], dtype=np.float64)

    root_T_anchor = np.array(root_T_cameras_raw[anchor_camera_id]["matrix_4x4"], dtype=np.float64)
    anchor_T_root = invert_transform(root_T_anchor)
    robot_T_cameras: dict[str, dict[str, Any]] = {}
    for camera_id, transform_dict in sorted(root_T_cameras_raw.items()):
        root_T_camera = np.array(transform_dict["matrix_4x4"], dtype=np.float64)
        anchor_T_camera = anchor_T_root @ root_T_camera
        robot_T_camera = robot_T_anchor @ anchor_T_camera
        robot_T_cameras[camera_id] = transform_to_dict(robot_T_camera)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_stitched_calibration": str(stitched_path),
        "root_camera_id": stitched_report.get("root_camera_id", ""),
        "anchor_camera_id": anchor_camera_id,
        "robot_T_anchor_camera": transform_to_dict(robot_T_anchor),
        "robot_T_cameras": robot_T_cameras,
        "notes": [
            "robot_T_anchor_camera maps the selected anchor camera frame into the robot frame.",
            "robot_T_cameras maps every stitched camera frame into the robot frame.",
            "If roll, pitch, and yaw were left at zero, the camera frame was assumed to align with the robot frame axes.",
        ],
    }
    path = write_json_report("robot_frame_calibration", report)
    report["saved_to"] = str(path)
    return report


def oak_config_paths() -> list[Path]:
    by_name: dict[str, Path] = {}
    for path in OAK_CONFIG_CANDIDATES:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = str(data.get("name", path.stem))
        except (OSError, json.JSONDecodeError):
            name = path.stem
        by_name.setdefault(name, path)
    return list(by_name.values())


def transform_to_dict(transform: np.ndarray) -> dict[str, Any]:
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    rvec, _ = cv2.Rodrigues(rotation)
    return {
        "matrix_4x4": transform.tolist(),
        "rotation_matrix": rotation.tolist(),
        "rotation_vector": rvec.reshape(-1).tolist(),
        "translation_m": translation.reshape(-1).tolist(),
    }


def invert_transform(transform: np.ndarray) -> np.ndarray:
    inv = np.eye(4, dtype=np.float64)
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    inv[:3, :3] = rotation.T
    inv[:3, 3] = -rotation.T @ translation
    return inv


def camera_matrix_from_intrinsics(intrinsics: dict[str, Any]) -> np.ndarray:
    return np.array(
        [
            [float(intrinsics["fx"]), 0.0, float(intrinsics["cx"])],
            [0.0, float(intrinsics["fy"]), float(intrinsics["cy"])],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def validate_board_settings(data: dict[str, Any]) -> tuple[int, int, float]:
    cols = int(data.get("pattern_cols", 0))
    rows = int(data.get("pattern_rows", 0))
    square_size_m = float(data.get("square_size_m", 0.0))
    if cols < 2 or rows < 2:
        raise RuntimeError("Checkerboard inner corner counts must both be at least 2.")
    if not math.isfinite(square_size_m) or square_size_m <= 0:
        raise RuntimeError("Checkerboard square size must be a positive number of meters.")
    return cols, rows, square_size_m


def detect_checkerboard_pose(
    image_bgr: np.ndarray,
    intrinsics: dict[str, Any],
    pattern_cols: int,
    pattern_rows: int,
    square_size_m: float,
    annotated_path: Path,
) -> dict[str, Any]:
    pattern_size = (pattern_cols, pattern_rows)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    found = False
    corners = None
    if hasattr(cv2, "findChessboardCornersSB"):
        found, corners = cv2.findChessboardCornersSB(gray, pattern_size)
    if not found:
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
        found, corners = cv2.findChessboardCorners(gray, pattern_size, flags)
        if found:
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001)
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

    annotated = image_bgr.copy()
    if corners is not None:
        cv2.drawChessboardCorners(annotated, pattern_size, corners, found)
    cv2.imwrite(str(annotated_path), annotated)

    detection: dict[str, Any] = {
        "found": bool(found),
        "pattern_cols": pattern_cols,
        "pattern_rows": pattern_rows,
        "square_size_m": square_size_m,
        "annotated_image": str(annotated_path),
    }
    if not found or corners is None:
        detection["message"] = "Checkerboard was not detected."
        return detection

    object_points = np.zeros((pattern_rows * pattern_cols, 3), np.float32)
    object_points[:, :2] = np.mgrid[0:pattern_cols, 0:pattern_rows].T.reshape(-1, 2)
    object_points *= square_size_m

    camera_matrix = camera_matrix_from_intrinsics(intrinsics)
    distortion = np.array(intrinsics.get("distortion_coeffs", []), dtype=np.float64).reshape(-1, 1)
    ok, rvec, tvec = cv2.solvePnP(object_points, corners, camera_matrix, distortion, flags=cv2.SOLVEPNP_ITERATIVE)
    detection["solve_pnp_ok"] = bool(ok)
    if not ok:
        detection["message"] = "Checkerboard was detected, but solvePnP failed."
        return detection

    rotation, _ = cv2.Rodrigues(rvec)
    camera_t_board = np.eye(4, dtype=np.float64)
    camera_t_board[:3, :3] = rotation
    camera_t_board[:3, 3] = tvec.reshape(3)
    detection["camera_T_board"] = transform_to_dict(camera_t_board)
    detection["message"] = "Checkerboard pose solved."

    try:
        cv2.drawFrameAxes(annotated, camera_matrix, distortion, rvec, tvec, square_size_m * 2.0)
        cv2.imwrite(str(annotated_path), annotated)
    except cv2.error:
        pass
    return detection


def serialize_rs_intrinsics(intr: Any) -> dict[str, Any]:
    return {
        "width": int(intr.width),
        "height": int(intr.height),
        "fx": float(intr.fx),
        "fy": float(intr.fy),
        "cx": float(intr.ppx),
        "cy": float(intr.ppy),
        "model": str(intr.model),
        "distortion_coeffs": [float(value) for value in intr.coeffs],
    }


def scan_realsense_devices() -> list[dict[str, Any]]:
    import pyrealsense2 as rs

    devices = []
    ctx = rs.context()
    for dev in ctx.query_devices():
        serial = dev.get_info(rs.camera_info.serial_number)
        name = dev.get_info(rs.camera_info.name)
        info: dict[str, Any] = {"name": name, "serial": serial}
        for field, key in [
            (rs.camera_info.firmware_version, "firmware_version"),
            (rs.camera_info.usb_type_descriptor, "usb_type"),
        ]:
            try:
                info[key] = dev.get_info(field)
            except RuntimeError:
                info[key] = ""
        devices.append(info)
    return devices


def collect_realsense_intrinsics() -> list[dict[str, Any]]:
    import pyrealsense2 as rs

    reports = []
    ctx = rs.context()
    for dev in ctx.query_devices():
        serial = dev.get_info(rs.camera_info.serial_number)
        name = dev.get_info(rs.camera_info.name)
        device_report: dict[str, Any] = {
            "name": name,
            "serial": serial,
            "profiles": [],
        }
        for sensor in dev.query_sensors():
            sensor_name = sensor.get_info(rs.camera_info.name) if sensor.supports(rs.camera_info.name) else "sensor"
            for profile in sensor.get_stream_profiles():
                try:
                    video_profile = profile.as_video_stream_profile()
                    intrinsics = video_profile.get_intrinsics()
                except RuntimeError:
                    continue
                device_report["profiles"].append(
                    {
                        "sensor": sensor_name,
                        "stream": str(video_profile.stream_type()),
                        "format": str(video_profile.format()),
                        "fps": int(video_profile.fps()),
                        "intrinsics": serialize_rs_intrinsics(intrinsics),
                    }
                )
        reports.append(device_report)
    return reports


def pick_realsense_color_profile(serial: str) -> tuple[int, int, Any, int]:
    import pyrealsense2 as rs

    ctx = rs.context()
    selected: tuple[int, int, Any, int] | None = None
    for dev in ctx.query_devices():
        if dev.get_info(rs.camera_info.serial_number) != serial:
            continue
        candidates: list[dict[str, Any]] = []
        for sensor in dev.query_sensors():
            for profile in sensor.get_stream_profiles():
                try:
                    video_profile = profile.as_video_stream_profile()
                except RuntimeError:
                    continue
                if video_profile.stream_type() != rs.stream.color:
                    continue
                if video_profile.format() not in {rs.format.bgr8, rs.format.rgb8}:
                    continue
                candidates.append(
                    {
                        "area": video_profile.width() * video_profile.height(),
                        "fps_score": -abs(video_profile.fps() - 15),
                        "width": int(video_profile.width()),
                        "height": int(video_profile.height()),
                        "format": video_profile.format(),
                        "fps": int(video_profile.fps()),
                    }
                )
        if candidates:
            profile = sorted(
                candidates,
                key=lambda candidate: (candidate["area"], candidate["fps_score"], candidate["width"], candidate["height"]),
                reverse=True,
            )[0]
            selected = (profile["width"], profile["height"], profile["format"], profile["fps"])
        break
    if selected is None:
        raise RuntimeError(f"No usable color profile found for RealSense serial {serial}.")
    return selected


def capture_realsense_checkerboard(
    serial: str,
    output_dir: Path,
    pattern_cols: int,
    pattern_rows: int,
    square_size_m: float,
) -> dict[str, Any]:
    import pyrealsense2 as rs

    width, height, fmt, fps = pick_realsense_color_profile(serial)
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(serial)
    config.enable_stream(rs.stream.color, width, height, fmt, fps)

    profile = pipeline.start(config)
    try:
        for _ in range(5):
            pipeline.wait_for_frames(timeout_ms=1500)
        frames = pipeline.wait_for_frames(timeout_ms=2500)
        color_frame = frames.get_color_frame()
        if not color_frame:
            raise RuntimeError(f"No color frame received from RealSense {serial}.")
        image = np.asanyarray(color_frame.get_data())
        if fmt == rs.format.rgb8:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        stream_profile = color_frame.profile.as_video_stream_profile()
        intrinsics = serialize_rs_intrinsics(stream_profile.get_intrinsics())
        raw_path = output_dir / f"realsense_{serial}_raw.jpg"
        annotated_path = output_dir / f"realsense_{serial}_checkerboard.jpg"
        cv2.imwrite(str(raw_path), image)
        detection = detect_checkerboard_pose(image, intrinsics, pattern_cols, pattern_rows, square_size_m, annotated_path)
        return {
            "camera_id": f"realsense:{serial}",
            "kind": "realsense",
            "serial": serial,
            "capture_profile": {"width": width, "height": height, "format": str(fmt), "fps": fps},
            "intrinsics": intrinsics,
            "raw_image": str(raw_path),
            "detection": detection,
        }
    finally:
        pipeline.stop()


def oak_camera_data_to_dict(camera_data: Any) -> dict[str, Any]:
    return {
        "camera_number": int(camera_data.camera_number),
        "camera_type": int(camera_data.camera_type),
        "width": int(camera_data.width),
        "height": int(camera_data.height),
        "intrinsic_matrix": [float(value) for value in camera_data.intrinsic_matrix],
        "distortion_coeffs": [float(value) for value in camera_data.distortion_coeff],
        "lens_position": int(camera_data.lens_position),
        "spec_hfov_deg": float(camera_data.spec_hfov_deg),
        "extrinsics": {
            "rotation_matrix": [float(value) for value in camera_data.extrinsics.rotation_matrix],
            "translation": [
                float(camera_data.extrinsics.translation.x),
                float(camera_data.extrinsics.translation.y),
                float(camera_data.extrinsics.translation.z),
            ],
            "to_camera_socket": int(camera_data.extrinsics.to_camera_socket),
        },
    }


def oak_intrinsics_from_camera_data(camera_data: Any) -> dict[str, Any]:
    matrix = [float(value) for value in camera_data.intrinsic_matrix]
    return {
        "width": int(camera_data.width),
        "height": int(camera_data.height),
        "fx": matrix[0],
        "fy": matrix[4],
        "cx": matrix[2],
        "cy": matrix[5],
        "model": "oak_factory",
        "distortion_coeffs": [float(value) for value in camera_data.distortion_coeff],
    }


async def request_oak_calibration(config_path: Path) -> tuple[str, Any]:
    from farm_ng.core.event_client import EventClient
    from farm_ng.core.event_service_pb2 import EventServiceConfig
    from farm_ng.core.events_file_reader import proto_from_json_file
    from google.protobuf.empty_pb2 import Empty

    config = proto_from_json_file(config_path, EventServiceConfig())
    calibration = await asyncio.wait_for(
        EventClient(config).request_reply("/calibration", Empty(), decode=True),
        timeout=5.0,
    )
    return config.name, calibration


async def request_oak_frame(config_path: Path) -> tuple[str, Any]:
    from farm_ng.core.event_client import EventClient
    from farm_ng.core.event_service_pb2 import EventServiceConfig
    from farm_ng.core.events_file_reader import proto_from_json_file

    config = proto_from_json_file(config_path, EventServiceConfig())

    async def next_frame() -> Any:
        async for _, message in EventClient(config).subscribe(config.subscriptions[0], decode=True):
            return message
        raise RuntimeError(f"No frame received from {config.name}.")

    frame = await asyncio.wait_for(next_frame(), timeout=6.0)
    return config.name, frame


def collect_oak_intrinsics() -> list[dict[str, Any]]:
    reports = []
    for path in oak_config_paths():
        try:
            name, calibration = asyncio.run(request_oak_calibration(path))
            reports.append(
                {
                    "name": name,
                    "config_path": str(path),
                    "online": True,
                    "batch_name": calibration.batch_name,
                    "board_name": calibration.board_name,
                    "board_rev": calibration.board_rev,
                    "camera_data": [oak_camera_data_to_dict(camera_data) for camera_data in calibration.camera_data],
                }
            )
        except Exception as exc:
            reports.append({"name": path.stem, "config_path": str(path), "online": False, "error": str(exc)})
    return reports


def select_oak_camera_data(calibration: Any, frame: Any) -> Any:
    frame_width = int(frame.meta.resolution.width)
    frame_height = int(frame.meta.resolution.height)
    for camera_data in calibration.camera_data:
        if int(camera_data.width) == frame_width and int(camera_data.height) == frame_height:
            return camera_data
    if not calibration.camera_data:
        raise RuntimeError("OAK calibration message did not include camera_data.")
    return calibration.camera_data[0]


def capture_oak_checkerboard(
    config_path: Path,
    output_dir: Path,
    pattern_cols: int,
    pattern_rows: int,
    square_size_m: float,
) -> dict[str, Any]:
    name, calibration = asyncio.run(request_oak_calibration(config_path))
    _, frame = asyncio.run(request_oak_frame(config_path))
    image = cv2.imdecode(np.frombuffer(frame.image_data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to decode OAK frame from {name}.")
    camera_data = select_oak_camera_data(calibration, frame)
    intrinsics = oak_intrinsics_from_camera_data(camera_data)
    safe_name = safe_filename(name)
    raw_path = output_dir / f"oak_{safe_name}_raw.jpg"
    annotated_path = output_dir / f"oak_{safe_name}_checkerboard.jpg"
    cv2.imwrite(str(raw_path), image)
    detection = detect_checkerboard_pose(image, intrinsics, pattern_cols, pattern_rows, square_size_m, annotated_path)
    return {
        "camera_id": f"oak:{name}",
        "kind": "oak",
        "name": name,
        "config_path": str(config_path),
        "frame_resolution": {"width": int(frame.meta.resolution.width), "height": int(frame.meta.resolution.height)},
        "camera_data": oak_camera_data_to_dict(camera_data),
        "intrinsics": intrinsics,
        "raw_image": str(raw_path),
        "detection": detection,
    }


def scan_cameras() -> dict[str, Any]:
    oak_status = []
    for path in oak_config_paths():
        try:
            name, calibration = asyncio.run(request_oak_calibration(path))
            oak_status.append(
                {
                    "name": name,
                    "config_path": str(path),
                    "online": True,
                    "camera_data_count": len(calibration.camera_data),
                }
            )
        except Exception as exc:
            oak_status.append({"name": path.stem, "config_path": str(path), "online": False, "error": str(exc)})

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "realsense": scan_realsense_devices(),
        "oak": oak_status,
    }


def pull_factory_intrinsics() -> dict[str, Any]:
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "realsense": collect_realsense_intrinsics(),
        "oak": collect_oak_intrinsics(),
    }
    path = write_json_report("factory_intrinsics", report)
    report["saved_to"] = str(path)
    return report


def capture_checkerboard_sample(settings: dict[str, Any]) -> dict[str, Any]:
    pattern_cols, pattern_rows, square_size_m = validate_board_settings(settings)
    sample_dir = OUTPUT_DIR / f"checkerboard_sample_{utc_stamp()}"
    sample_dir.mkdir(parents=True, exist_ok=True)

    captures: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for device in scan_realsense_devices():
        serial = str(device["serial"])
        try:
            captures.append(capture_realsense_checkerboard(serial, sample_dir, pattern_cols, pattern_rows, square_size_m))
        except Exception as exc:
            errors.append({"camera_id": f"realsense:{serial}", "error": str(exc)})

    for config_path in oak_config_paths():
        try:
            captures.append(capture_oak_checkerboard(config_path, sample_dir, pattern_cols, pattern_rows, square_size_m))
        except Exception as exc:
            errors.append({"camera_id": normalize_camera_id(f"oak:{config_path.stem}"), "error": str(exc)})

    solved = [capture for capture in captures if capture.get("detection", {}).get("solve_pnp_ok")]
    extrinsics: dict[str, Any] = {}
    if solved:
        reference = solved[0]
        reference_transform = np.array(reference["detection"]["camera_T_board"]["matrix_4x4"], dtype=np.float64)
        extrinsics["reference_camera_id"] = reference["camera_id"]
        extrinsics["camera_transforms_to_reference"] = {}
        for capture in solved:
            camera_transform = np.array(capture["detection"]["camera_T_board"]["matrix_4x4"], dtype=np.float64)
            reference_t_camera = reference_transform @ invert_transform(camera_transform)
            extrinsics["camera_transforms_to_reference"][capture["camera_id"]] = transform_to_dict(reference_t_camera)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sample_dir": str(sample_dir),
        "board": {
            "inner_corners_across": pattern_cols,
            "inner_corners_down": pattern_rows,
            "square_size_m": square_size_m,
        },
        "captures": captures,
        "errors": errors,
        "summary": {
            "capture_count": len(captures),
            "found_count": sum(1 for capture in captures if capture.get("detection", {}).get("found")),
            "solved_count": len(solved),
            "error_count": len(errors),
            "solved_camera_ids": [capture["camera_id"] for capture in solved],
            "missing_checkerboard_camera_ids": [
                capture["camera_id"]
                for capture in captures
                if not capture.get("detection", {}).get("found")
            ],
            "capture_error_camera_ids": [error.get("camera_id", "") for error in errors],
        },
        "extrinsics": extrinsics,
        "notes": [
            "camera_T_board maps checkerboard object coordinates into each camera frame.",
            "camera_transforms_to_reference are valid for cameras that detected the board in this same capture sample.",
            "For better final extrinsics, capture multiple samples and compare repeatability before trusting one measurement.",
        ],
    }
    report_path = sample_dir / "sample_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest_path = write_json_report("latest_checkerboard_sample", report)
    report["saved_to"] = str(report_path)
    report["latest_copy"] = str(latest_path)
    return report


def request_app_shutdown() -> None:
    print("full-calibration: exit requested", flush=True)
    timer = threading.Timer(
        0.75,
        lambda: subprocess.run(
            ["systemctl", "--user", "stop", APP_SERVICE],
            check=False,
            capture_output=True,
            text=True,
        ),
    )
    timer.daemon = True
    timer.start()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._send_json(
                {
                    "output_dir": str(OUTPUT_DIR),
                    "latest_intrinsics": latest_file("factory_intrinsics_*.json"),
                    "latest_sample": latest_file("latest_checkerboard_sample_*.json"),
                    "latest_stitched": latest_file("stitched_calibration_*.json"),
                    "latest_robot_frame": latest_file("robot_frame_calibration_*.json"),
                    "latest_sample_summary": latest_sample_summary(),
                    "camera_status": camera_history_status(),
                }
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/scan":
            self._handle_action(scan_cameras)
            return
        if path == "/api/intrinsics":
            self._handle_action(pull_factory_intrinsics)
            return
        if path == "/api/capture-sample":
            body = self._read_json()
            self._handle_action(lambda: capture_checkerboard_sample(body))
            return
        if path == "/api/stitch-session":
            body = self._read_json()
            self._handle_action(lambda: stitch_calibration_session(body))
            return
        if path == "/api/anchor-robot-frame":
            body = self._read_json()
            self._handle_action(lambda: anchor_stitched_calibration_to_robot_frame(body))
            return
        if path == "/api/exit":
            request_app_shutdown()
            self._send_json({"message": "Shutdown requested."})
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_common_headers("text/plain")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            return
        print("full-calibration-http:", format % args, flush=True)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _handle_action(self, action) -> None:
        try:
            self._send_json(action())
        except Exception as exc:
            print(f"full-calibration error: {exc}", flush=True)
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        self._send(status, json.dumps(data), "application/json")

    def _send(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self._send_common_headers(content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_common_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")


def main() -> None:
    parser = argparse.ArgumentParser(description="Full camera calibration app.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8057)
    args = parser.parse_args()

    ensure_output_dir()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"full-calibration: serving on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
