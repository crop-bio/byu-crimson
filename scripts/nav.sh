#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

ROOT_DIR="$(crimson_root_dir)"

cd "$ROOT_DIR/farm-ng-amiga/BYU_Amiga" || exit 1
crimson_activate_venv
cd "$ROOT_DIR/farm-ng-amiga/py/examples/vehicle_twist"
