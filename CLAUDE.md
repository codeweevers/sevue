# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sevue is a desktop application that captures live camera input, performs real-time gesture recognition using MediaPipe, renders subtitles over the video, and outputs to a virtual camera device. Built with PySide6, OpenCV, MediaPipe, and pyvirtualcam.

## Development Commands

```bash
# Create and activate virtual environment (example with conda)
conda create -n sevue python=3.12
conda activate sevue

# Install dependencies
pip install -r requirements.txt

# Run the application
python sevue.pyw
```

## Build Commands

```bash
# Build with PyInstaller (from project root)
cd train_installer_gen
pyinstaller sevue.spec --noconfirm --clean
```

Releases are automated via GitHub Actions (`.github/workflows/release.yml`) triggered by version tags (`v*.*`). Builds Windows installers (Inno Setup) and Linux packages (deb/rpm).

## Architecture

**Entry Point:** `sevue.pyw` handles single-instance lock via `QLockFile`, splash screen, and activates existing instance via `QLocalServer`.

**Controller Pattern:** `controllers/main_window_controller.py` is the main orchestrator:
- Manages `CameraThread` and `AIThread` workers
- Handles system tray, global hotkeys (pynput), and UI navigation
- Coordinates camera selection, model registry, and state persistence

**State Management:** `models/state_model.py` (QObject) holds all app state:
- Toggles (flip video/text/hands, preview, debug, auto-start)
- Camera UID/index and selected model
- Keyboard shortcuts
- Emits `changed` signal for reactive updates
- Persists config to `data/config.json` (dev) or platformdirs (installed)

**Threading Model:**
- `CameraThread` (workers/threads.py): Captures frames from OpenCV, applies adaptive brightness, renders subtitles/hand landmarks, sends to virtual camera via pyvirtualcam
- `AIThread` (workers/threads.py): Pulls frames from shared `FrameBuffer`, runs MediaPipe gesture recognition, updates subtitle state
- Synchronization via `threading.Event` (`stop_event`) and `FrameBuffer` producer/consumer pattern

**Services:**
- `services/model_registry_service.py`: Manages custom `.task` model import, validation, and registry
- `services/startup_service.py`: Platform-specific boot-on-login integration

**Views:** `views/home_page.py` (camera preview), `views/settings_page.py` (settings/model management), `views/widgets.py` (reusable dialogs)

## Key Patterns

- Global hotkeys use `pynput` keyboard listener; actions are emitted to Qt main thread via `global_action` signal with `Qt.QueuedConnection`
- Config loading applies defaults then merges saved values; missing/invalid config falls back to defaults
- Model registry: bundled `data/models/default.task` is copied to user config on first run; imported models stored in `<config_dir>/models/`
- Camera discovery: `workers/camera_utils.py` provides cross-platform device enumeration with UID resolution

## Constants

`constants.py` defines:
- `AI_FRAME_SIZE = (480, 480)` - resolution for AI processing
- `CONF_THRESHOLD = 0.65` - gesture confidence threshold
- `DEFAULT_FPS = 30` - virtual camera frame rate
- `COMMON_RESOLUTIONS` - fallback resolution priority list

## Training Custom Models

Training requires Linux with Python 3.10-3.11 and `mediapipe-model-maker`. See `train_installer_gen/train.py` and `train_installer_gen/make_none.py`. Exported models (`.task` files) can be imported via Settings.