#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

if command -v ethtool >/dev/null 2>&1 && command -v ip >/dev/null 2>&1 && ip link show eth0 >/dev/null 2>&1; then
    sudo ethtool -s eth0 speed 100 duplex full autoneg off || true
fi

ROOT_DIR="$(crimson_root_dir)"

cd "$ROOT_DIR/farm-ng-amiga/BYU_Amiga" || exit 1
crimson_activate_venv
