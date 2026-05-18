#!/bin/bash
# usb-tegra-reset.sh
# Resets Tegra USB controller (Jetson Xavier)

set -euo pipefail

echo "⚡ Resetting Tegra XHCI (USB) controller..."

# Make sure no critical USB devices (e.g. rootfs) are mounted from USB
mount | grep /dev/sd

echo "→ Unloading xhci-tegra module..."
sudo modprobe -r xhci-tegra

sleep 1

echo "→ Reloading xhci-tegra module..."
sudo modprobe xhci-tegra

sleep 2

echo "→ Triggering udev refresh..."
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "✅ Done. Current USB devices:"
lsusb
