#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_local_dev.sh [--with-live-hardware] [--with-dev-tools]

Creates the expected local virtual environment at:
  farm-ng-amiga/BYU_Amiga/amiga-env

Base install:
- editable local farm-ng-amiga package
- numpy
- opencv-python

Optional flags:
- --with-live-hardware  Also try to install pyrealsense2 and depthai.
- --with-dev-tools      Also install pytest, ruff, and black.
EOF
}

WITH_LIVE_HARDWARE=0
WITH_DEV_TOOLS=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --with-live-hardware)
      WITH_LIVE_HARDWARE=1
      ;;
    --with-dev-tools)
      WITH_DEV_TOOLS=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

ROOT_DIR="$(crimson_root_dir)"
VENV_DIR="${CRIMSON_VENV_DIR:-$(crimson_default_venv_dir)}"
PYTHON_BOOTSTRAP_BIN="${PYTHON_BOOTSTRAP_BIN:-python3}"

if ! command -v "$PYTHON_BOOTSTRAP_BIN" >/dev/null 2>&1; then
  echo "Bootstrap Python not found: $PYTHON_BOOTSTRAP_BIN" >&2
  exit 1
fi

echo "Creating virtual environment at $VENV_DIR"
"$PYTHON_BOOTSTRAP_BIN" -m venv "$VENV_DIR"

VENV_PYTHON="$VENV_DIR/bin/python"
echo "Installing pip tooling compatible with farm-ng-amiga"
"$VENV_PYTHON" -m pip install --upgrade pip "setuptools<81" wheel

echo "Installing farm-ng build dependencies"
"$VENV_PYTHON" -m pip install "protobuf<=5.27.5" farm-ng-package farm-ng-core

echo "Installing local development requirements"
"$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements-local-dev.txt"

echo "Installing editable farm-ng-amiga package"
"$VENV_PYTHON" -m pip install --no-build-isolation -e "$ROOT_DIR/farm-ng-amiga"

if [ "$WITH_LIVE_HARDWARE" -eq 1 ]; then
  echo "Installing optional live hardware packages"
  "$VENV_PYTHON" -m pip install pyrealsense2 depthai
fi

if [ "$WITH_DEV_TOOLS" -eq 1 ]; then
  echo "Installing optional dev tools"
  "$VENV_PYTHON" -m pip install pytest ruff black
fi

cat <<EOF

Local development environment is ready.

Python interpreter:
  $VENV_PYTHON

The launcher scripts will pick this environment up automatically because it
matches the expected amiga-env path.

Useful next steps:
  scripts/run_hangman_app.sh
  scripts/run_full_service_app.sh
  scripts/run_full_calibration_app.sh
EOF
