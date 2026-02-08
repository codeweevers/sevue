# Sevue

Sevue is a real-time, desktop-based sign language interpretation system focused on accessibility for deaf and hard-of-hearing users.

It captures live camera input, recognizes hand gestures locally using MediaPipe + ML, and renders readable subtitles directly into a virtual camera feed for use in conferencing and streaming apps. The full pipeline runs on-device to prioritize low latency and privacy.

## Features

- Real-time hand gesture recognition with MediaPipe Gesture Recognizer
- On-device inference (no cloud dependency)
- Live subtitle overlay rendered into output video
- Virtual camera output for compatibility with Zoom, OBS, Meet, and similar apps
- Desktop GUI built with PySide6
- Configurable display behavior (flip video/subtitles/hands, debug landmarks)
- System tray support for background operation

## Installation (Prebuilt Releases)

Download builds from the GitHub Releases page.

### Windows

1. Download `sevue_setup.exe` from the latest release.
2. Run installer normally.
3. The installer includes virtual camera setup (`Sevue-VirtualCam`).
4. Launch Sevue from Start Menu or desktop shortcut.

### Linux

1. Download the Linux release artifact from the latest release.
2. Extract it.
3. Run the app binary normally.
4. If needed, install/enable virtual camera support (`v4l2loopback`) before running.

Example virtual camera setup on Linux:

```bash
sudo apt update
sudo apt install -y v4l2loopback-dkms v4l2loopback-utils v4l-utils
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="Sevue-VirtualCam" exclusive_caps=1
```

## Build From Source

### 1. Prerequisites

- Python 3.10 or 3.11 recommended
- Camera/webcam device
- Git
- Platform notes:
  - Windows: administrator rights for virtual camera install scripts
  - Linux: `v4l-utils` and optional `v4l2loopback`

### 2. Clone

```bash
git clone https://github.com/codeweevers/sevue.git
cd sevue
```

### 3. Create Virtual Environment

Windows (PowerShell):

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Runtime Dependencies

```bash
pip install --upgrade pip
pip install opencv-python mediapipe numpy pyvirtualcam pyside6
```

### 5. Install Virtual Camera

Windows (from repo root, auto-elevates):

```powershell
.\Install_SevueCam.bat
```

Linux:

- Ensure a virtual camera device exists (example `v4l2loopback` command above).

### 6. Run

```bash
python sevue.pyw
```

## Training Model (Linux)

The training script (`train.py`) uses MediaPipe Model Maker and expects a folder dataset at `hands/<label>/*.jpg`.

### 1. Install training dependencies

```bash
pip install tensorflow mediapipe-model-maker matplotlib
```

### 2. Verify dataset layout

```text
hands/
  A/
  B/
  C/
  ...
```

### 3. Train and export

```bash
python train.py
```

The script writes model artifacts to `exported_model/` and exports a Gesture Recognizer task file.

### 4. Use trained model in app

Replace the runtime model with your exported file:

```bash
cp exported_model/gesture_recognizer.task model/gesture_recognizer.task
```

## Packaging / Distribution

Sevue already includes PyInstaller spec files.

### Windows

```powershell
pyinstaller sevue-win.spec
```

Then build installer (Inno Setup) using `installer scrypt.iss`.

### Linux

```bash
pyinstaller sevue-linux.spec
```

## Usage

1. Launch Sevue.
2. Click `Start Sevue`.
3. Select `Sevue-VirtualCam` in your conferencing/streaming app as camera source.
4. Use Settings page to adjust flips/debug/preview behavior.

### Keyboard Shortcuts

- `C`: Flip camera
- `O`: Flip subtitle text
- `H`: Flip hand label side
- `D`: Toggle hand landmark debug
- `Esc`: Hide/show behavior (window/tray interaction)

## Project Structure

- `sevue.pyw`: main desktop app, camera loop, inference loop, GUI
- `subtitle_renderer.py`: subtitle rendering overlay logic
- `train.py`: model training/evaluation/export
- `model/gesture_recognizer.task`: runtime model file
- `hands/`: training dataset
- `sevue-win.spec`, `sevue-linux.spec`: PyInstaller build specs
- `Install_SevueCam.bat`, `Uninstall_SevueCam.bat`: Windows virtual camera setup

## Troubleshooting

- Camera not opening:
  - Close other apps using camera, then restart Sevue.
- No virtual camera in other apps:
  - Windows: rerun `Install_SevueCam.bat` as admin.
  - Linux: verify `v4l2loopback` device exists (`v4l2-ctl --list-devices`).
- Model file missing:
  - Ensure `model/gesture_recognizer.task` exists.
- Linux device name mismatch:
  - Sevue tries `Sevue-VirtualCam`; if not found it falls back to pyvirtualcam auto-pick.

## Privacy

Sevue processes video locally on-device. No cloud service is required for inference in the default architecture.

## License

Licensed under the terms in `LICENSE`.
