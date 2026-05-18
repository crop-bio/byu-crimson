#!/bin/bash
# Automatically set the default PulseAudio sink to the first USB device

# Get the first sink name containing "usb"
usb_sink=$(pactl list short sinks | awk '/usb/ {print $2; exit}')

if [ -n "$usb_sink" ]; then
    echo "Setting default sink to: $usb_sink"
    pactl set-default-sink "$usb_sink"
else
    echo "No USB audio sink found."
    exit 1
fi