#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

ROOT_DIR="$(crimson_root_dir)"
APP_DIR="$ROOT_DIR/farm-ng-amiga/BYU_Amiga/field2025"
PYTHON_BIN="$(crimson_python_bin)"
LOG_FILE="$ROOT_DIR/farmng_log.log"
CONTROL_DIR="$ROOT_DIR/full_service_app/runtime"
CONTROL_PIPE="$CONTROL_DIR/full_service_control.fifo"

cleanup() {
  exec 3>&- || true
  rm -f "$CONTROL_PIPE"
}

mkdir -p "$CONTROL_DIR"
rm -f "$CONTROL_PIPE"
mkfifo "$CONTROL_PIPE"
trap cleanup EXIT

cd "$APP_DIR"
export PATH="$ROOT_DIR/scripts:$PATH"
exec 3<>"$CONTROL_PIPE"

echo "[test_script] Control pipe ready at $CONTROL_PIPE"
sudo -E env PATH="$PATH" "$PYTHON_BIN" -u full_service.py --speed 30 --fps 4 --notes "3 RS 2 OAK Grasses" <&3 2>&1 | tee -a "$LOG_FILE"
