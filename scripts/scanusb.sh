#!/bin/bash
# usb-rescan.sh
# Rescan USB devices on a Linux system (e.g., Jetson Xavier / Amiga Brain)

set -euo pipefail

echo "🔄 Rescanning USB devices..."

# 1. Trigger the kernel to rescan all USB buses
echo "→ Triggering USB bus rescan..."
for bus in /sys/bus/usb/drivers/usb; do
    if [ -w "$bus/bind" ] && [ -w "$bus/unbind" ]; then
        for dev in $(ls /sys/bus/usb/devices/ | grep -E '^[0-9]'); do
            echo "- Unbinding $dev"
            echo "$dev" | sudo tee "$bus/unbind" >/dev/null 2>&1 || true
            echo "$dev" | sudo tee "$bus/bind" >/dev/null 2>&1 || true
        done
    fi
done

# 2. Trigger a device rescan (some subsystems require this)
echo "→ Asking kernel to rescan all devices..."
echo "1" | sudo tee /sys/bus/pci/rescan >/dev/null 2>&1 || true
echo "1" | sudo tee /sys/bus/usb/rescan >/dev/null 2>&1 || true

# 3. Restart udevd to refresh device nodes
echo "→ Restarting udev to refresh device entries..."
sudo udevadm control --reload-rules
sudo udevadm trigger

# 4. Optionally, reload USB kernel modules (use with caution)
# Uncomment these lines if USB stops working entirely.
# echo "→ Reloading USB kernel modules..."
# sudo modprobe -r xhci_hcd
# sudo modprobe xhci_hcd

# 5. Show result
echo "✅ USB devices currently detected:"
lsusb || echo "⚠️  'lsusb' not found. Install via: sudo apt install usbutils"

echo "✅ Done. If devices still don't appear, try replugging or rebooting."
