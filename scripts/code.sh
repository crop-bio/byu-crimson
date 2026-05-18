#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${CRIMSON_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

if command -v ethtool >/dev/null 2>&1 && command -v ip >/dev/null 2>&1 && ip link show eth0 >/dev/null 2>&1; then
    sudo ethtool -s eth0 speed 100 duplex full autoneg off || true
fi

cd "$ROOT_DIR/farm-ng-amiga/BYU_Amiga" || exit 1
source amiga-env/bin/activate
