import cv2
import mediapipe as mp
import numpy as np
import moderngl
import glfw
import pyvirtualcam
from pyvirtualcam import PixelFormat
import threading
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import time

predict_lock = threading.Lock()
text = ""
running = True
latest_frame = None
frame_lock = threading.Lock()
toggle = False


def ai():
    global text, latest_frame
    BaseOptions = mp.tasks.BaseOptions
    GestureRecognizer = mp.tasks.vision.GestureRecognizer
    GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
    GestureRecognizerResult = mp.tasks.vision.GestureRecognizerResult
    VisionRunningMode = mp.tasks.vision.RunningMode

    model_path = "gesture_recognizer.task"
    last_time = 0
    frame_timestamp = 0

    def print_result(result, output_image, timestamp_ms):
        global text
        if result.gestures:
            top = result.gestures[0][0].category_name
            with predict_lock:
                text = top
        else:
            with predict_lock:
                text = ""

    options = GestureRecognizerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.LIVE_STREAM,
        result_callback=print_result,
    )

    with GestureRecognizer.create_from_options(options) as recognizer:
        while running:
            with frame_lock:
                frame = latest_frame.copy() if latest_frame is not None else None
            if frame is None:
                time.sleep(0.01)
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            now = time.time()
            if now - last_time < 0.05:  # send max 20 FPS to AI
                continue
            last_time = now
            frame_timestamp += 1
            recognizer.recognize_async(mp_image, frame_timestamp)
            time.sleep(0.01)


def compose_subtitled_frame(frame, subtitle_text):
    h, w, _ = frame.shape
    bar_height = 80
    bar = np.zeros((bar_height, w, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 2
    padding = 20

    font_scale = 1.0
    while True:
        (tw, th), _ = cv2.getTextSize(subtitle_text, font, font_scale, thickness)
        if tw <= (w - padding * 2) or font_scale < 0.3:
            break
        font_scale -= 0.05

    x = (w - tw) // 2
    y = (bar_height + th) // 2
    cv2.putText(
        bar,
        subtitle_text,
        (x, y),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )
    bar = cv2.flip(bar, 1)
    combined = np.vstack((frame, bar))
    return combined


def virtual_cam():
    global running, text, latest_frame
    glfw.init()
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    window = glfw.create_window(640, 480, "GL", None, None)
    glfw.make_context_current(window)
    ctx = moderngl.create_context()
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    texture = ctx.texture((width, height), 3)
    with pyvirtualcam.Camera(
        width=width,
        height=height + 80,
        fps=fps,
        fmt=PixelFormat.BGR,
        device="Sevue-VirtualCam",
    ) as cam:
        while running:
            ret, frame = cap.read()
            if not ret:
                continue
            with frame_lock:
                latest_frame = frame.copy()
            texture.write(frame.tobytes())
            with predict_lock:
                sub = text
            final_frame = compose_subtitled_frame(frame, sub)
            cam.send(final_frame)
            cam.sleep_until_next_frame()
    cap.release()
    glfw.terminate()


def create_icon_image():
    image = Image.new("RGB", (64, 64), color=(30, 30, 30))
    draw = ImageDraw.Draw(image)
    draw.text((12, 22), "CAM", fill="lime")
    return image


def on_exit(icon, item):
    global running
    running = False
    icon.stop()


def toggle_sevue(state):
    global toggel
    if state == True:
        toggel = False
    else:
        toggle = True


def tray():
    menu = (item("Exit", on_exit),)
    icon = pystray.Icon("Sevue", create_icon_image(), "Sevue", menu)
    icon.run()


ai_thread = threading.Thread(target=ai, daemon=True)
cam_thread = threading.Thread(target=virtual_cam, daemon=True)
ai_thread.start()
cam_thread.start()
tray()
