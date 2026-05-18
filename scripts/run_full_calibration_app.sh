#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${CRIMSON_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
APP_DIR="$ROOT_DIR/full_calibration_app"
VENV_PYTHON="$ROOT_DIR/farm-ng-amiga/BYU_Amiga/amiga-env/bin/python"

cd "$APP_DIR"
exec "$VENV_PYTHON" main.py --host 0.0.0.0 --port 8057
