#!/bin/bash
# unmountusb.sh — Safely unmount the TOSHIBA USB drive

set -euo pipefail

LABEL="${CRIMSON_USB_LABEL:-crimson}"
MOUNT_POINT="${CRIMSON_USB_MOUNT:-/media/adminfarmng/crimson}"

echo "=== Checking connected drives ==="

# Find the device by label
DEVICE=$(lsblk -l -o NAME,LABEL -p | grep "$LABEL" | awk '{print $1}' | sed 's/^[├─└─]*//')

if [ -z "$DEVICE" ]; then
    echo "❌ Error: Could not find a drive labeled '$LABEL'. Nothing to unmount."
    exit 1
fi

echo "Found drive labeled '$LABEL' at $DEVICE."

# Unmount from main mount point (if still mounted)
if mount | grep -q "$MOUNT_POINT"; then
    echo "Unmounting from main mount point: $MOUNT_POINT"
    sudo umount "$MOUNT_POINT"
    echo "✅ Drive successfully unmounted from $MOUNT_POINT"
else
    echo "Drive not mounted at $MOUNT_POINT. Nothing to do."
fi
