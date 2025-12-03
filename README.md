# Sevue

A real-time Indian Sign Language (ISL) to speech and text translator using computer vision and machine learning technologies.

## Features

- Real-time gesture recognition using MediaPipe and TensorFlow
- Converts ISL gestures to text and speech output
- Virtual camera integration for seamless video processing
- Cross-platform support (Windows, macOS, Linux)
- System tray integration for background operation

## Installation

### Prerequisites
- Python 3.7+
- Webcam or video input device

### Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/sevue.git
   cd sevue
   ```

2. Install dependencies:
   ```bash
   pip install opencv-python mediapipe tensorflow pyvirtualcam moderngl glfw pystray pillow numpy
   ```

3. Install the virtual camera (requires administrator privileges):
   ```bash
   Install_SevueCam.bat
   ```

## Usage

Run the main application:
```bash
python sevue.pyw
```

The application will start gesture recognition and provide real-time translation of ISL gestures to text and speech.

## Testing

Test your camera setup:
```bash
python -c "import cv2; print(cv2.VideoCapture(0).isOpened())"
```

## Building

To create an executable:
```bash
makeexe.bat
```

## Code Quality

Format code:
```bash
python -m black *.py
```

Type check:
```bash
python -m mypy *.py --ignore-missing-imports
```

## License

This project is licensed under the terms specified in the LICENSE file.

## Contributing

Contributions are welcome! Please follow the code style guidelines in AGENTS.md.