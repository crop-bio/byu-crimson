#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${CRIMSON_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
APP_DIR="$ROOT_DIR/full_service_app"

cd "$APP_DIR"
exec /usr/bin/python3 main.py --host 0.0.0.0 --port 8056
