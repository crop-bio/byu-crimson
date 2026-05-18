#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${CRIMSON_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

cd "$ROOT_DIR/farm-ng-amiga" || exit 1
source amiga-env/bin/activate
cd py/examples/vehicle_twist
