# Sevue

Sevue is a desktop application that turns live sign input into subtitle-like text over video and publishes the result to a virtual camera.

The app is built with PySide6, OpenCV, MediaPipe, and pyvirtualcam. It runs locally on your machine and is designed for low-latency, always-on desktop use.

## What the App Does

- Captures frames from a selected physical camera
- Runs MediaPipe gesture recognition in a worker thread
- Builds short text output from recognized gestures
- Renders text and optional hand-debug overlays into the video stream
- Sends the processed stream to a virtual camera device
- Provides a desktop UI for camera/model/settings/shortcuts

## Runtime Architecture

- `sevue.pyw`: app entrypoint and single-instance lock/activation server
- `controllers/main_window_controller.py`: main orchestration (UI state, workers, tray, camera/model selection)
- `models/state_model.py`: persisted app state, settings, shortcuts, model registry, selected camera/model
- `models/frame_buffer.py`: shared frame buffer between camera and AI workers
- `workers/threads.py`:
  - `CameraThread`: capture, overlay rendering, virtual camera output
  - `AIThread`: gesture inference and subtitle text generation
- `workers/camera_utils.py`: cross-platform camera discovery and metadata
- `services/model_registry_service.py`: model import/validation/registry management
- `services/startup_service.py`: start-on-login integration (Windows/Linux)
- `views/`: Home/Settings pages and UI widgets

## Requirements

- Python 3.10+ (3.11/3.12 recommended)
- A working physical camera
- OS support:
  - Windows
  - Linux
  - macOS (camera discovery support is present; virtual camera behavior depends on platform setup)

## Install From Source

```bash
git clone https://github.com/codeweevers/sevue.git
cd sevue
```

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
python sevue.pyw
```

## Basic Usage

1. Launch Sevue.
2. Open Settings and confirm camera/model selection if needed.
3. Click `Start Sevue`.
4. In your conferencing/recording app, choose `Sevue-VirtualCam` (or your configured virtual cam target).

## Configuration and Persistence

Sevue saves:

- selected camera (UID + resolved index)
- selected model + model registry
- app toggles (preview, flips, tray behavior, auto-start camera, etc.)
- keyboard shortcuts

Config location:

- Installed/frozen build: platform user config directory (`platformdirs`)
- Source/dev run: `data/config.json` in project root

## Models

- Default runtime model is resolved via `services/model_registry_service.py`
- Additional `.task` models can be imported from Settings
- Imported models are copied into the app model storage directory and registered by name

## Keyboard Shortcuts

Default configurable shortcuts:

- `Ctrl+Shift+S` start/stop camera
- `Ctrl+Shift+M` hide/show window
- `Ctrl+Shift+C` flip camera
- `Ctrl+Shift+O` flip subtitles
- `Ctrl+Shift+H` flip hand labels
- `Ctrl+Shift+D` toggle hand debug

Also supported:

- `Esc` window hide/show behavior

## Packaging

PyInstaller spec is included at:

- `train_installer_gen/sevue.spec`

Windows installer-related assets/scripts are in:

- `train_installer_gen/Install_SevueCam.bat`
- `train_installer_gen/Uninstall_SevueCam.bat`
- `train_installer_gen/installer scrypt.iss`

## Training (Optional)

Training script:

- `train_installer_gen/train.py`

This is separate from the runtime app and intended for creating/exporting gesture models.

## Troubleshooting

- Camera cannot start:
  - Close other apps that may own the camera.
  - Re-open Settings and select the correct device.
- No virtual camera in external apps:
  - Verify your virtual camera driver/setup is installed and active.
- App already running:
  - Sevue is single-instance; launching again activates the existing window.

## License

See `LICENSE`.
