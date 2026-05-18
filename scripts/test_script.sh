#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${CRIMSON_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
APP_DIR="$ROOT_DIR/farm-ng-amiga/BYU_Amiga/field2025"
VENV_DIR="$ROOT_DIR/farm-ng-amiga/BYU_Amiga/amiga-env"
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
source "$VENV_DIR/bin/activate"
export PATH="$ROOT_DIR/scripts:$PATH"
exec 3<>"$CONTROL_PIPE"

echo "[test_script] Control pipe ready at $CONTROL_PIPE"
sudo -E env PATH="$PATH" python -u full_service.py --speed 30 --fps 4 --notes "3 RS 2 OAK Grasses" <&3 2>&1 | tee -a "$LOG_FILE"
