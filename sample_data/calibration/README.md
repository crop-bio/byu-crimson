# Calibration Sample Data

This directory contains a curated calibration example for local development and
UI inspection.

Included:

- one representative `checkerboard_sample_*` capture directory
- one `factory_intrinsics_*.json`
- one `latest_checkerboard_sample_*.json`
- one `stitched_calibration_*.json`

These files were copied from on-device output and had absolute
`/mnt/managed_home/...` paths normalized for repository portability.

Live Amiga runs still write new artifacts to `calibration_data/`.
