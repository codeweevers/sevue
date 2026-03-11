AI_FRAME_SIZE = (256, 256)
CONF_THRESHOLD = 0.65
DEFAULT_FPS = 30
VIRTUAL_CAMERA_MARKERS = (
    "virtual",
    "obs",
    "v4l2loopback",
)

# Highest to lowest, first supported resolution is selected.
COMMON_RESOLUTIONS = [
    (1920, 1080),
    (1280, 720),
    (960, 540),
    (640, 480),
    (320, 240),
]
