# byu-crimson

This repository is the curated workspace for BYU Crimson development on farm-ng
Amiga hardware and on local machines that need a similar layout.

## Repository Scope

Tracked content:

- `manifest.json`
- `scripts/`
- `full_service_app/`
- `full_calibration_app/`
- `hangman_app/`
- `farm-ng-amiga/`
- `sample_data/`

Excluded content:

- Amiga user-home state such as `.ssh/`, `.codex/`, `.local/`, `.vscode-server/`
- large runtime media and logs
- local virtual environments and build outputs
- archival vendor trees such as `depthai-core/` and `librealsense/`

## Local Development Layout

Most launcher scripts resolve the workspace root dynamically. They use:

- `CRIMSON_ROOT` if it is set
- otherwise the parent directory of the script location

That means a local clone does not need to live under
`/mnt/managed_home/farm-ng-user-byu-crimson` unless you are running it on the
Amiga launcher itself.

`manifest.json` remains device-oriented and may still use absolute paths because
the Amiga app launcher expects those commands on-device.

## Bootstrap

1. Clone this repository.
2. Create the expected local virtual environment with:

   ```bash
   ./scripts/bootstrap_local_dev.sh
   ```

3. If you need live camera access on a compatible machine, also try:

   ```bash
   ./scripts/bootstrap_local_dev.sh --with-live-hardware
   ```

4. Launch the apps with the wrapper scripts under `scripts/`.
5. If you need live hardware workflows, provide the same external services and
   devices that the Amiga has available.

The app wrappers expect the farm-ng Amiga virtual environment at:

`farm-ng-amiga/BYU_Amiga/amiga-env`

The bootstrap script creates that environment in the expected location so the
launchers can find it automatically. You can also override the interpreter with
`CRIMSON_PYTHON=/path/to/python`.

## Local App Modes

For quick UI work on a laptop:

- `scripts/run_hangman_app.sh` works with only the standard library.
- `scripts/run_full_service_app.sh` works locally, but its runner controls still
  expect a working `systemd --user` session and the Amiga service stack.
- `scripts/run_full_calibration_app.sh` can show the calibration UI and curated
  sample reports immediately. Checkerboard capture and calibration actions need
  the bootstrap environment because they use `numpy` and `opencv-python`.

For camera-backed local development:

- RealSense features need `pyrealsense2`.
- OAK / farm-ng features need the editable `farm-ng-amiga` package and any
  reachable farm-ng services described by the JSON configs.
- Full Service capture still expects the same privileges, devices, and external
  services that the Amiga workflow uses.

## Contributor Workflow

Do not work directly on `main`. Create a feature branch first:

```bash
git checkout -b your-branch-name
```

Then make your changes, push the branch, and open a pull request back into
`main`.

## Script Roles

Production launchers:

- `scripts/run_full_service_app.sh`
- `scripts/run_full_calibration_app.sh`
- `scripts/run_hangman_app.sh`
- `scripts/test_script.sh`

Runtime support utilities:

- `scripts/mountusb.sh`
- `scripts/unmountusb.sh`
- `scripts/speaker.sh`

Operator or recovery tools:

- `scripts/scanusb.sh`
- `scripts/resetusb.sh`

Developer convenience wrappers:

- `scripts/code.sh`
- `scripts/nav.sh`
- `scripts/start.sh`
- `scripts/video.sh`

## Calibration Sample Data

Curated calibration examples live under `sample_data/calibration/`.

`full_calibration_app` writes live output to `calibration_data/` on the Amiga.
For local clones with no live capture history, the app can fall back to the
curated sample set for inspection and UI development.
