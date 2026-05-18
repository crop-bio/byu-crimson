#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


APP_SERVICE = "Bash-test.service"
RUNNER_SERVICE = "full-service-runner.service"
LOG_LINES = 200
ROOT_DIR = Path(__file__).resolve().parent.parent
CONTROL_PIPE = Path(__file__).resolve().parent / "runtime" / "full_service_control.fifo"
RS_TEST_PATH = ROOT_DIR / "farm-ng-amiga" / "BYU_Amiga" / "utils" / "rs_test.py"
FULL_SERVICE_PATH = ROOT_DIR / "farm-ng-amiga" / "BYU_Amiga" / "field2025" / "full_service.py"
FULL_SERVICE_VENV_PYTHON = ROOT_DIR / "farm-ng-amiga" / "BYU_Amiga" / "amiga-env" / "bin" / "python"
TEST_SCRIPT_PATH = ROOT_DIR / "scripts" / "test_script.sh"
DEFAULT_SAVE_ROOT = Path("/media/adminfarmng/CROPBIO2/current")
STOP_WAIT_SECONDS = 16.0
IMAGE_CACHE_TTL_SECONDS = 2.0
LATEST_IMAGE_CACHE: dict[str, Any] = {
    "checked_at": 0.0,
    "save_root": "",
    "path": "",
    "mtime_ns": 0,
}
QUIET_LOG_PATHS = {
    "/api/status",
    "/api/logs",
    "/api/latest-image-info",
    "/api/latest-image",
}


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Full Service</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef1eb;
      --panel: #fbfcf9;
      --ink: #18211b;
      --muted: #607064;
      --line: #cfd8cf;
      --accent: #255c3f;
      --accent-2: #7b2f22;
      --accent-3: #394853;
      --good: #1d6b42;
      --warn: #8e6720;
      --bad: #9e3328;
      --shadow: rgba(24, 33, 27, 0.13);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(37, 92, 63, 0.12), transparent 30%),
        radial-gradient(circle at top right, rgba(123, 47, 34, 0.10), transparent 28%),
        linear-gradient(180deg, #f5f7f2 0%, var(--bg) 100%);
      padding: 24px;
    }
    main {
      width: min(980px, 100%);
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 18px 60px var(--shadow);
      padding: 28px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      margin-bottom: 24px;
      flex-wrap: wrap;
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
    }
    .status-card {
      min-width: 220px;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f7f9f5;
    }
    .status-label {
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
    }
    .status-value {
      margin-top: 8px;
      font-size: 22px;
      font-weight: 700;
    }
    .status-meta {
      margin-top: 6px;
      font-size: 14px;
      color: var(--muted);
    }
    .controls {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    button {
      min-height: 56px;
      border: 0;
      border-radius: 8px;
      color: white;
      font-size: 17px;
      font-weight: 600;
      cursor: pointer;
    }
    .start { background: var(--accent); }
    .pause { background: #8e6720; }
    .resume { background: #2b6f90; }
    .stop { background: var(--accent-2); }
    .inspect { background: #5e4b8b; }
    .exit { background: var(--accent-3); }
    button:disabled {
      cursor: default;
      opacity: 0.55;
    }
    .notice {
      min-height: 26px;
      margin-bottom: 16px;
      font-size: 15px;
      color: var(--muted);
    }
    .notice.good { color: var(--good); }
    .notice.warn { color: var(--warn); }
    .notice.bad { color: var(--bad); }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .panel-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: #f3f6f2;
      font-size: 15px;
      color: var(--muted);
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .preview-body {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #f9fbf8;
    }
    .image-frame {
      min-height: 320px;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #e8eee8;
      display: grid;
      place-items: center;
    }
    .image-frame img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #121916;
    }
    .image-empty {
      padding: 18px;
      text-align: center;
      color: var(--muted);
      font-size: 14px;
    }
    .image-meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }
    pre {
      margin: 0;
      min-height: 320px;
      max-height: 520px;
      overflow: auto;
      padding: 18px;
      background: #18211b;
      color: #edf2ec;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    @media (max-width: 760px) {
      body { padding: 14px; }
      main { padding: 20px; }
      .controls { grid-template-columns: 1fr; }
      .workspace { grid-template-columns: 1fr; }
      .status-card { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <div class="header">
      <div>
        <h1>Full Service</h1>
        <div class="sub">Control `full_service.py`, run utility checks, and watch recent output.</div>
      </div>
      <div class="status-card">
        <div class="status-label">Runner Status</div>
        <div class="status-value" id="status-value">Unknown</div>
        <div class="status-meta" id="status-meta">Checking service state...</div>
      </div>
    </div>

    <div class="controls">
      <button class="start" id="start-button">Start Full Service</button>
      <button class="pause" id="pause-button">Pause</button>
      <button class="resume" id="resume-button">Resume</button>
      <button class="stop" id="stop-button">Stop Full Service</button>
      <button class="inspect" id="rs-test-button">Run RS Test</button>
      <button class="inspect" id="mount-button">Check Drive Mount</button>
      <button class="exit" id="exit-button">Exit to Home</button>
    </div>

    <div class="notice" id="notice"></div>

    <div class="workspace">
      <div class="panel">
        <div class="panel-head">Latest saved image</div>
        <div class="preview-body">
          <div class="image-frame">
            <img id="latest-image" alt="Latest saved camera image" hidden>
            <div class="image-empty" id="image-empty">No saved image found yet.</div>
          </div>
          <div class="image-meta" id="image-meta">Watching the configured Full Service save root.</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">Recent logs</div>
        <pre id="logs">Loading logs...</pre>
      </div>
    </div>
  </main>

  <script>
    const statusValue = document.getElementById("status-value");
    const statusMeta = document.getElementById("status-meta");
    const logsEl = document.getElementById("logs");
    const noticeEl = document.getElementById("notice");
    const startButton = document.getElementById("start-button");
    const pauseButton = document.getElementById("pause-button");
    const resumeButton = document.getElementById("resume-button");
    const stopButton = document.getElementById("stop-button");
    const rsTestButton = document.getElementById("rs-test-button");
    const mountButton = document.getElementById("mount-button");
    const latestImageEl = document.getElementById("latest-image");
    const imageEmptyEl = document.getElementById("image-empty");
    const imageMetaEl = document.getElementById("image-meta");
    let latestImageToken = "";
    let controlsBusy = false;

    function setNotice(message, level) {
      noticeEl.textContent = message || "";
      noticeEl.className = "notice" + (level ? " " + level : "");
    }

    function setBusy(busy) {
      controlsBusy = busy;
      startButton.disabled = busy;
      pauseButton.disabled = busy;
      resumeButton.disabled = busy;
      stopButton.disabled = busy;
      rsTestButton.disabled = busy;
      mountButton.disabled = busy;
    }

    async function getJson(path) {
      const response = await fetch(path);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }
      return data;
    }

    async function postJson(path) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }
      return data;
    }

    function applyStatus(data) {
      statusValue.textContent = data.active_state;
      statusMeta.textContent = data.sub_state + " | " + data.unit_file_state;

      if (controlsBusy) {
        return;
      }

      const active = data.active_state === "active" || data.active_state === "activating";
      startButton.disabled = active;
      pauseButton.disabled = !active;
      resumeButton.disabled = !active;
      stopButton.disabled = !active;
      rsTestButton.disabled = active;
      mountButton.disabled = false;
    }

    async function refreshStatus() {
      try {
        applyStatus(await getJson("/api/status"));
      } catch (error) {
        setNotice("Failed to read service status.", "bad");
      }
    }

    async function refreshLogs() {
      try {
        const data = await getJson("/api/logs");
        logsEl.textContent = data.logs || "No logs yet.";
        logsEl.scrollTop = logsEl.scrollHeight;
      } catch (error) {
        logsEl.textContent = "Failed to load logs.";
      }
    }

    async function refreshLatestImage() {
      try {
        const data = await getJson("/api/latest-image-info");
        imageMetaEl.textContent = data.meta || "Watching the configured Full Service save root.";

        if (!data.available) {
          latestImageEl.hidden = true;
          imageEmptyEl.hidden = false;
          imageEmptyEl.textContent = data.message || "No saved image found yet.";
          latestImageToken = "";
          return;
        }

        const token = `${data.path}|${data.mtime_ns}`;
        imageEmptyEl.hidden = true;
        latestImageEl.hidden = false;
        if (latestImageToken !== token) {
          latestImageEl.src = `/api/latest-image?ts=${data.mtime_ns}`;
          latestImageToken = token;
        }
      } catch (error) {
        latestImageEl.hidden = true;
        imageEmptyEl.hidden = false;
        imageEmptyEl.textContent = "Failed to load the latest saved image.";
      }
    }

    async function runAction(path, successMessage) {
      setBusy(true);
      setNotice("", "");
      try {
        const data = await postJson(path);
        setNotice(successMessage + " " + data.message, "good");
      } catch (error) {
        setNotice(error.message || "Command failed.", "bad");
      } finally {
        await refreshStatus();
        await refreshLogs();
        setBusy(false);
      }
    }

    document.getElementById("start-button").addEventListener("click", async () => {
      await runAction("/api/start", "Start requested.");
    });

    document.getElementById("pause-button").addEventListener("click", async () => {
      await runAction("/api/pause", "Pause requested.");
    });

    document.getElementById("resume-button").addEventListener("click", async () => {
      await runAction("/api/resume", "Resume requested.");
    });

    document.getElementById("stop-button").addEventListener("click", async () => {
      await runAction("/api/stop", "Stop requested.");
    });

    document.getElementById("rs-test-button").addEventListener("click", async () => {
      await runAction("/api/rs-test", "RS test requested.");
    });

    document.getElementById("mount-button").addEventListener("click", async () => {
      await runAction("/api/mount-status", "Mount check requested.");
    });

    document.getElementById("exit-button").addEventListener("click", () => {
      window.location.href = `${window.location.protocol}//${window.location.hostname}/apps/launcher`;
    });

    async function refreshAll() {
      await refreshStatus();
      await refreshLogs();
      await refreshLatestImage();
    }

    refreshAll();
    setInterval(refreshAll, 2000);
  </script>
</body>
</html>
"""


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _run_command_bytes(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, capture_output=True, check=False)


def _run_sudo_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return _run_command(["sudo", "-n", *args])


def _run_sudo_command_bytes(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return _run_command_bytes(["sudo", "-n", *args])


def get_service_status() -> dict[str, str]:
    result = _run_command(
        [
            "systemctl",
            "--user",
            "show",
            RUNNER_SERVICE,
            "--property=ActiveState",
            "--property=SubState",
            "--property=UnitFileState",
            "--value",
        ]
    )
    lines = result.stdout.strip().splitlines()
    while len(lines) < 3:
        lines.append("unknown")
    return {
        "active_state": lines[0] or "unknown",
        "sub_state": lines[1] or "unknown",
        "unit_file_state": lines[2] or "unknown",
    }


def get_service_logs() -> str:
    result = _run_command(
        [
            "journalctl",
            "--user",
            "-u",
            APP_SERVICE,
            "-u",
            RUNNER_SERVICE,
            "-n",
            str(LOG_LINES),
            "--no-pager",
            "-o",
            "short-iso",
        ]
    )
    output = result.stdout.strip()
    return output if output else "No logs yet."


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def get_configured_save_root() -> Path:
    script_text = _read_text(TEST_SCRIPT_PATH)
    override_match = re.search(r"--save-root\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", script_text)
    if override_match:
        override_path = next(group for group in override_match.groups() if group)
        return Path(override_path)

    full_service_text = _read_text(FULL_SERVICE_PATH)
    default_match = re.search(r'--save-root".*?default="([^"]+)"', full_service_text)
    if default_match:
        return Path(default_match.group(1))

    return DEFAULT_SAVE_ROOT


def get_mount_root(save_root: Path) -> Path | None:
    media_root = Path("/media/adminfarmng")
    try:
        relative = save_root.relative_to(media_root)
    except ValueError:
        return None

    if not relative.parts:
        return media_root
    return media_root / relative.parts[0]


def _log_block(prefix: str, text: str) -> None:
    for line in text.splitlines():
        print(f"{prefix} {line}", flush=True)


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except PermissionError:
        return _run_sudo_command(["test", "-e", str(path)]).returncode == 0


def _is_mount(path: Path) -> bool:
    try:
        return os.path.ismount(path)
    except PermissionError:
        return _run_sudo_command(["mountpoint", "-q", str(path)]).returncode == 0


def run_rs_test() -> dict[str, str]:
    python_path = FULL_SERVICE_VENV_PYTHON if FULL_SERVICE_VENV_PYTHON.exists() else Path("/usr/bin/python3")
    command = [str(python_path), str(RS_TEST_PATH)]
    print(f"[rs-test] Running: {' '.join(command)}", flush=True)

    try:
        result = subprocess.run(
            command,
            cwd=str(RS_TEST_PATH.parent),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        _log_block("[rs-test][stdout]", stdout)
        _log_block("[rs-test][stderr]", stderr)
        raise RuntimeError("rs_test.py timed out after 30 seconds.")

    _log_block("[rs-test][stdout]", result.stdout)
    _log_block("[rs-test][stderr]", result.stderr)

    if result.returncode != 0:
        raise RuntimeError(f"rs_test.py exited with code {result.returncode}.")

    return {"message": "rs_test.py completed. See logs for output."}


def check_mount_status() -> dict[str, str]:
    save_root = get_configured_save_root()
    mount_root = get_mount_root(save_root)

    if mount_root is None:
        message = f"Configured save root is local: {save_root}"
        print(f"[mount-status] {message}", flush=True)
        return {"message": message}

    mounted = _is_mount(mount_root)
    mount_exists = _path_exists(mount_root)
    save_root_exists = _path_exists(save_root)
    if mounted:
        message = (
            f"Drive {mount_root} is mounted. "
            f"save_root={save_root} save_root_exists={save_root_exists}"
        )
    elif save_root_exists:
        message = (
            f"{mount_root} exists but is not a separate mount point. "
            f"Full Service is currently writing to {save_root} on local storage."
        )
    else:
        message = (
            f"Drive {mount_root} is not mounted and save_root={save_root} is not available yet."
        )
    print(f"[mount-status] {message}", flush=True)
    return {"message": message}


def _scan_latest_image(save_root: Path, suffixes: tuple[str, ...]) -> tuple[Path | None, int]:
    latest_path: Path | None = None
    latest_mtime_ns = 0

    if not _path_exists(save_root):
        return None, 0

    if str(save_root).startswith("/media/adminfarmng/"):
        find_args = ["find", str(save_root), "-type", "f", "("]
        for index, suffix in enumerate(suffixes):
            if index > 0:
                find_args.append("-o")
            find_args.extend(["-iname", f"*{suffix}"])
        find_args.extend([")", "-printf", "%T@ %p\n"])
        result = _run_sudo_command(find_args)
        if result.returncode != 0:
            return None, 0

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            try:
                mtime_ns = int(float(parts[0]) * 1_000_000_000)
            except ValueError:
                continue
            if mtime_ns > latest_mtime_ns:
                latest_path = Path(parts[1])
                latest_mtime_ns = mtime_ns
        return latest_path, latest_mtime_ns

    for root, _, files in os.walk(save_root):
        for filename in files:
            lowered = filename.lower()
            if not lowered.endswith(suffixes):
                continue
            path = Path(root) / filename
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                continue
            if mtime_ns > latest_mtime_ns:
                latest_path = path
                latest_mtime_ns = mtime_ns

    return latest_path, latest_mtime_ns


def get_latest_image_path() -> tuple[Path | None, Path, int]:
    save_root = get_configured_save_root()
    now = time.time()
    cached_save_root = Path(LATEST_IMAGE_CACHE["save_root"]) if LATEST_IMAGE_CACHE["save_root"] else None

    if (
        cached_save_root == save_root
        and (now - float(LATEST_IMAGE_CACHE["checked_at"])) < IMAGE_CACHE_TTL_SECONDS
    ):
        cached_path = Path(LATEST_IMAGE_CACHE["path"]) if LATEST_IMAGE_CACHE["path"] else None
        return cached_path, save_root, int(LATEST_IMAGE_CACHE["mtime_ns"])

    latest_path, latest_mtime_ns = _scan_latest_image(save_root, (".jpg", ".jpeg"))
    if latest_path is None:
        latest_path, latest_mtime_ns = _scan_latest_image(save_root, (".png",))

    LATEST_IMAGE_CACHE.update(
        {
            "checked_at": now,
            "save_root": str(save_root),
            "path": str(latest_path) if latest_path else "",
            "mtime_ns": latest_mtime_ns,
        }
    )
    return latest_path, save_root, latest_mtime_ns


def get_latest_image_info() -> dict[str, Any]:
    latest_path, save_root, latest_mtime_ns = get_latest_image_path()
    meta_lines = [f"Save root: {save_root}"]

    if latest_path is None:
        if not _path_exists(save_root):
            return {
                "available": False,
                "message": f"Save root is not available yet: {save_root}",
                "meta": "\n".join(meta_lines),
            }
        return {
            "available": False,
            "message": f"No saved images found under {save_root}",
            "meta": "\n".join(meta_lines),
        }

    modified = datetime.fromtimestamp(latest_mtime_ns / 1_000_000_000).strftime("%Y-%m-%d %H:%M:%S")
    try:
        relative_path = latest_path.relative_to(save_root)
    except ValueError:
        relative_path = latest_path

    meta_lines.append(f"Latest file: {relative_path}")
    meta_lines.append(f"Modified: {modified}")
    return {
        "available": True,
        "message": "",
        "meta": "\n".join(meta_lines),
        "path": str(latest_path),
        "mtime_ns": latest_mtime_ns,
    }


def get_latest_image_bytes() -> tuple[bytes, str]:
    latest_path, _, _ = get_latest_image_path()
    if latest_path is None:
        raise FileNotFoundError("No saved image found.")

    suffix = latest_path.suffix.lower()
    content_type = "image/png" if suffix == ".png" else "image/jpeg"
    try:
        return latest_path.read_bytes(), content_type
    except PermissionError:
        result = _run_sudo_command_bytes(["cat", str(latest_path)])
        if result.returncode != 0:
            raise FileNotFoundError("No saved image found.")
        return result.stdout, content_type


def _is_runner_active(status: dict[str, str] | None = None) -> bool:
    runner_status = status or get_service_status()
    return runner_status["active_state"] in {"active", "activating", "deactivating"}


def send_runner_command(command: str) -> None:
    if not CONTROL_PIPE.exists():
        raise RuntimeError(f"Runner control pipe is unavailable at {CONTROL_PIPE}.")

    try:
        fd = os.open(CONTROL_PIPE, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError(f"Unable to open runner control pipe: {exc.strerror}.") from exc

    with os.fdopen(fd, "w", encoding="utf-8", buffering=1) as pipe:
        pipe.write(f"{command}\n")
        pipe.flush()


def command_runner(command: str, action_name: str) -> dict[str, str]:
    status = get_service_status()
    if not _is_runner_active(status):
        raise RuntimeError(f"{RUNNER_SERVICE} is not running.")

    send_runner_command(command)
    return {"message": f"Sent '{command}' to full_service.py to {action_name} capture."}


def start_runner() -> dict[str, str]:
    status = get_service_status()
    if _is_runner_active(status):
        return {"message": f"{RUNNER_SERVICE} is already running."}

    result = _run_command(["systemctl", "--user", "start", RUNNER_SERVICE])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to start service.")
    return {"message": f"{RUNNER_SERVICE} start requested."}


def stop_runner() -> dict[str, str]:
    status = get_service_status()
    if not _is_runner_active(status):
        return {"message": f"{RUNNER_SERVICE} is not running."}

    command_error: str | None = None
    try:
        send_runner_command("s")
    except RuntimeError as exc:
        command_error = str(exc)

    deadline = time.time() + STOP_WAIT_SECONDS
    while time.time() < deadline:
        if not _is_runner_active():
            if command_error:
                return {"message": f"{command_error} Fallback stop not needed because the service exited."}
            return {"message": "Sent 's' to full_service.py and it exited cleanly."}
        time.sleep(0.25)

    result = _run_command(["systemctl", "--user", "stop", RUNNER_SERVICE])
    if result.returncode != 0:
        if command_error:
            raise RuntimeError(f"{command_error} {result.stderr.strip()}".strip())
        raise RuntimeError(result.stderr.strip() or "Failed to stop service.")

    if command_error:
        return {"message": f"{command_error} Requested fallback stop via systemctl."}
    return {"message": "Sent 's' to full_service.py, then requested fallback stop via systemctl."}


def pause_runner() -> dict[str, str]:
    return command_runner("p", "pause")


def resume_runner() -> dict[str, str]:
    return command_runner("r", "resume")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._send_json(get_service_status())
            return
        if path == "/api/logs":
            self._send_json({"logs": get_service_logs()})
            return
        if path == "/api/latest-image-info":
            self._send_json(get_latest_image_info())
            return
        if path == "/api/latest-image":
            try:
                image_bytes, content_type = get_latest_image_bytes()
            except FileNotFoundError:
                self.send_error(404, "No saved image found.")
                return
            self._send_bytes(200, image_bytes, content_type)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/start":
            self._handle_action(start_runner)
            return
        if path == "/api/pause":
            self._handle_action(pause_runner)
            return
        if path == "/api/resume":
            self._handle_action(resume_runner)
            return
        if path == "/api/stop":
            self._handle_action(stop_runner)
            return
        if path == "/api/rs-test":
            self._handle_action(run_rs_test)
            return
        if path == "/api/mount-status":
            self._handle_action(check_mount_status)
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_common_headers("text/plain")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        path = urlparse(self.path).path
        if path in QUIET_LOG_PATHS:
            return
        print("full-service-app:", format % args, flush=True)

    def _handle_action(self, action) -> None:
        try:
            self._send_json(action())
        except RuntimeError as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        self._send(status, json.dumps(data), "application/json")

    def _send(self, status: int, body: str, content_type: str) -> None:
        self._send_bytes(status, body.encode("utf-8"), content_type)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._send_common_headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")


def main() -> None:
    parser = argparse.ArgumentParser(description="Full Service control app.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8056)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"full-service-app: serving on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
