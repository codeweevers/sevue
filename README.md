# Sevue

Sevue is a desktop application that turns live sign input into subtitle-like text over video and publishes the result to a virtual camera.

The app is built with PySide6, OpenCV, MediaPipe, and pyvirtualcam. It runs locally on your machine and is designed for low-latency, always-on desktop use.

## What the App Does

- Captures frames from a selected physical camera
- Runs MediaPipe gesture recognition in a worker thread
- Builds short text output from recognized gestures
- Renders text stream
- Sends the processed stream to a virtual camera device
- Provides a desktop UI for camera/model/settings/shortcuts
## installation

### quick install

1. Grab the proper  file for your OS  from the [Releases](https://github.com/codeweevers/sevue/releases/latest) page.
2. Install the file like normal for your OS. Usually just double-click on the file.
3. That's it, sevue will be installed to your system like normal and shows up on the doc / start menu

### Install From Source

#### Requirements

- Python 3.10 to Python 3.12
- A working physical camera or apps like DroidCam
- OS support:
  - Windows
  - Linux
  - macOS 

#### steps

clone the project:
```bash
git clone https://github.com/codeweevers/sevue.git
cd sevue
```

create and activate a virtual env. For example with conda:
``` bash
conda create -n sevue python=3.12
conda activate sevue
```

install requirements:
``` bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Run

```bash
python sevue.pyw
```

## Basic Usage

1. Launch Sevue.
2. Click `Start Sevue`.
3. In your conferencing/recording app, choose `Sevue-VirtualCam` (or your configured virtual cam target).

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

Training can only be done on **Linux** and must use **Python 3.10 or 3.11**. This process is separate from the runtime app and is intended for creating and exporting custom gesture models.

1. Set up a compatible environment (Linux, Python 3.10‑3.11) and install the required package:
   ```bash
   pip install mediapipe-model-maker
   ```
2. Use the training script located at `train_installer_gen/train.py` to start model training.
Note: edit the script to set the folder path of your dataset folder. The dataset should be structured as folders of images, where each folder name represents the gesture label (e.g., `thumbs_up/`, `wave/`, etc.).
3. Before or after training, run `make_none.py` to generate the required "none" files; you will need to edit that script to point the dataset folder path to your own data.
4. When the process completes the exported model will be written to `exported_model/gesture_recognizer.task`.
5. Import the resulting `.task` file using the **choose model** option in the app's settings.

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
