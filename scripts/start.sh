#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${CRIMSON_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

source "$SCRIPT_DIR/code.sh"

sudo -E env PATH="$PATH" python -u rs_gpt.py --gps-config configs/gps_config.json |& tee -a "$ROOT_DIR/farmng_log.log"
# sudo -E env PATH="$PATH" python -u capture_images_gps.py --oak0-config configs/oak0_config.json --oak1-config configs/oak1_config.json --gps-config configs/gps_config.json |& tee -a "$ROOT_DIR/farmng_log.log"
