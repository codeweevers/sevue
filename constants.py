import os

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
CONF_THRESHOLD = 0.89
COMMON_RESOLUTIONS = [
    (3840, 2160),
    (2560, 1440),
    (1920, 1080),
    (1280, 720),
    (640, 480),
]
DEFAULT_FPS = 30
AI_FRAME_SIZE = (640, 480)
CONFIG_PATH = os.path.join(APP_ROOT, "config.cfg")
