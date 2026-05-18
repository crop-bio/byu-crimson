#!/bin/bash
# mountusb.sh — Automatically mount the TOSHIBA USB drive

set -euo pipefail

LABEL="${CRIMSON_USB_LABEL:-crimson}"
MOUNT_POINT="${CRIMSON_USB_MOUNT:-/media/adminfarmng/crimson}"
OLD_MOUNT="${CRIMSON_OLD_USB_MOUNT:-/media/adminfarmng/crimson1}"
USER_NAME="${CRIMSON_USER:-$(id -un)}"

echo "=== Checking connected drives ==="

# Find the device by label
DEVICE=$(lsblk -l -o NAME,LABEL -p | grep "$LABEL" | awk '{print $1}' | sed 's/^[├─└─]*//')

if [ -z "$DEVICE" ]; then
    echo "❌ Error: Could not find a drive labeled '$LABEL'."
    echo "Make sure the drive is connected and labeled correctly."
    exit 1
fi

echo "Found drive labeled '$LABEL' at $DEVICE."

# Unmount old location if mounted
if mount | grep -q "$OLD_MOUNT"; then
    echo "Unmounting from old location: $OLD_MOUNT"
    sudo umount "$OLD_MOUNT"
fi

# Unmount previous mount at MOUNT_POINT if mounted
if mount | grep -q "$MOUNT_POINT"; then
    echo "Unmounting previous mount at $MOUNT_POINT"
    sudo umount "$MOUNT_POINT"
fi

# Create mount point if it doesn't exist
if [ ! -d "$MOUNT_POINT" ]; then
    echo "Creating mount point at $MOUNT_POINT..."
    sudo mkdir -p "$MOUNT_POINT"
fi

# Mount the device
echo "Mounting $DEVICE to $MOUNT_POINT..."
sudo mount -o uid=$(id -u "$USER_NAME"),gid=$(id -g "$USER_NAME") "$DEVICE" "$MOUNT_POINT"

# Verify mount
if mount | grep -q "$MOUNT_POINT"; then
    echo "✅ Drive '$LABEL' successfully mounted at $MOUNT_POINT."
else
    echo "❌ Mount failed."
    exit 1
fi
