#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

ROOT_DIR="$(crimson_root_dir)"
APP_DIR="$ROOT_DIR/full_calibration_app"
PYTHON_BIN="$(crimson_python_bin)"

cd "$APP_DIR"
exec "$PYTHON_BIN" main.py --host 0.0.0.0 --port 8057
