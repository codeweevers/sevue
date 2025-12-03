# AGENTS.md

## Commands

- **Run main app**: `python sevue.pyw`
- **Build executable**: `makeexe.bat`
- **Install virtual camera**: `Install_SevueCam.bat` (requires admin)
- **Install dependencies**: `pip install opencv-python mediapipe tensorflow pyvirtualcam moderngl glfw pystray pillow numpy`
- **Test camera**: `python -c "import cv2; print(cv2.VideoCapture(0).isOpened())"`
- **Format code**: `python -m black *.py`
- **Type check**: `python -m mypy *.py --ignore-missing-imports`
- **Run tests**: No tests defined yet

## Code Style Guidelines

- **Imports**: Standard library first, then third-party, then local imports
- **Formatting**: Use Black formatter (88-character line length)
- **Types**: Use type hints for function signatures and class attributes
- **Naming**: snake_case for variables/functions, PascalCase for classes
- **Error handling**: Use try-except blocks with informative error messages
- **Threading**: Always use daemon threads for background tasks
- **MediaPipe**: Use holistic solution for pose + hand detection
- **TensorFlow**: Load models with error handling, use verbose=0 for predictions
- **OpenCV**: Check frame.isOpened() and handle None returns
- **Virtual camera**: Release resources in finally blocks
- **Constants**: Use UPPER_CASE for global configuration values</content>
  <parameter name="filePath">C:\Users\tech\Documents\sevue\AGENTS.md
