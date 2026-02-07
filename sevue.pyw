#               KEYBINDS
# -----------------SEVUE-----------------
#   Flip subtitles  -   O
#   Flip camera     -   C
#   hide to tray -   Esc
# enable debug lines - d
from subtitle_renderer import render_youtube_cc_prediction
import os
import cv2
import mediapipe as mp
import numpy as np
import pyvirtualcam
from pyvirtualcam import PixelFormat
import threading
import time
from PySide6.QtWidgets import (
    QMainWindow,
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSystemTrayIcon,
    QMenu,
    QHBoxLayout,
    QCheckBox,
    QStackedWidget,
    QFrame,
    QListWidget,
    QLineEdit,
)
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QIcon,
    QShortcut,
    QKeySequence,
    QCloseEvent,
    QGuiApplication,
    QPainter,
    QColor,
)
from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QObject,
    Property,
    QPropertyAnimation,
    QEasingCurve,
)
from functools import partial
import sys
import json

import platform
import glob
import subprocess

def get_virtual_cam_device(preferred_name="SevueCam"):
    system = platform.system().lower()

    # Windows: device name works
    if system == "windows":
        return preferred_name

    # Linux: find /dev/video* with matching card_label
    if system == "linux":
        for dev in sorted(glob.glob("/dev/video*")):
            try:
                out = subprocess.check_output(
                    ["v4l2-ctl", "--device", dev, "--all"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                if preferred_name in out:
                    return dev
            except Exception:
                pass

        # fallback: let pyvirtualcam auto-pick
        return None

    return None

mp_hands = mp.tasks.vision.HandLandmarksConnections
mp_drawing = mp.tasks.vision.drawing_utils
mp_drawing_styles = mp.tasks.vision.drawing_styles
CONF_THRESHOLD = 0.89
# Camera Configuration
COMMON_RESOLUTIONS = [
    (3840, 2160),  # 4K
    (2560, 1440),  # QHD
    (1920, 1080),  # Full HD
    (1280, 720),  # HD
    (640, 480),  # VGA
]
DEFAULT_FPS = 30
AI_FRAME_SIZE = (640, 480)
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


class State(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.FLIP_VIDEO = True
        self.FLIP_TEXT = False
        self.FLIP_HANDS = False
        self._word_buffer = []
        self._last_appended_word = None
        self._last_word = None
        self._last_word_time = 0.0
        self._text = ""
        self._hand_labels = []
        self._confidence = 0.0
        self.SHOW_HAND_DEBUG = False
        self.SHOW_PREVIEW = True
        self.BASE_DIR = self.resource_path("")
        self._lock = threading.Lock()
        self._hand_landmarks = None
        self._subtitle = {
            "text": "",
            "start": 0.0,
            "duration": 2.5,
        }
        self.FEATURES = {
            "toggle_camera": {
                "type": "action",
                "shortcut": "S",
            },
            "flip_camera": {
                "type": "state",
                "state": "FLIP_VIDEO",
                "label": "Flip Camera",
                "shortcut": "C",
            },
            "flip_subtitles": {
                "type": "state",
                "state": "FLIP_TEXT",
                "label": "Flip Subtitles",
                "shortcut": "O",
            },
            "flip_hands": {
                "type": "state",
                "state": "FLIP_HANDS",
                "label": "Flip Hands",
                "shortcut": "H",
            },
            "toggle_debug": {
                "type": "state",
                "state": "SHOW_HAND_DEBUG",
                "label": "hand Debug",
                "shortcut": "D",
            },
            "hide": {
                "type": "action",
                "shortcut": "Esc",
            },
        }
        DEFAULT_CONFIG = {
            "conf": {
                "flip_video": True,
                "flip_subtitles": False,
                "flip_hands": False,
                "toggle_debug": False,
            },
            "shortcuts": {
                "flip_video": "C",
                "flip_subtitles": "O",
                "flip_hands": "H",
                "toggle_debug": "D",
            },
        }
        self.config = {
            "conf": {
                "flip_video": self.FLIP_VIDEO,
                "flip_subtitles": self.FLIP_TEXT,
                "flip_hands": self.FLIP_HANDS,
                "toggle_debug": self.SHOW_HAND_DEBUG,
            },
            "shortcuts": {
                "flip_video": self.FEATURES["flip_camera"]["shortcut"],
                "flip_subtitles": self.FEATURES["flip_subtitles"]["shortcut"],
                "flip_hands": self.FEATURES["flip_hands"]["shortcut"],
                "toggle_debug": self.FEATURES["toggle_debug"]["shortcut"],
            },
        }

    def resource_path(self, relative):
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, relative)
        return os.path.join(os.path.abspath("."), relative)

    def set_subtitle(self, text, duration=2.5):
        with self._lock:
            self._subtitle["text"] = text
            self._subtitle["start"] = time.time()
            self._subtitle["duration"] = duration

    def get_subtitle(self):
        with self._lock:
            return self._subtitle.copy()

    def set_hand_labels(self, labels):
        with self._lock:
            self._hand_labels = labels

    def get_hand_labels(self):
        with self._lock:
            return list(self._hand_labels)

    def set_hand_landmarks(self, landmarks):
        with self._lock:
            self._hand_landmarks = landmarks

    def set_flag(self, name, value):
        with self._lock:
            setattr(self, name, value)
        self.changed.emit(name)

    def append_word(self, word):
        with self._lock:
            self._word_buffer.append(word)

    def get_buffer_text(self):
        with self._lock:
            return " ".join(self._word_buffer)

    def clear_buffer(self):
        with self._lock:
            self._word_buffer.clear()

    def get_hand_landmarks(self):
        with self._lock:
            return self._hand_landmarks

    def save_config(self):
        with open(config_path, "w") as f:
            json.dump(self.config, f, indent=4)

        # def load_config(self):
        #     # If config doesn't exist → create it
        #     if not os.path.exists(config_path):
        #         self.config = json.loads(json.dumps(self.DEFAULT_CONFIG))
        #         self.apply_config()
        #         self.save_config()
        #         return

        #     # Load existing config
        #     with open(config_path, "r") as f:
        #         self.config = json.load(f)

        #     self.apply_config()


class WorkerThread(QThread):
    def __init__(self, stop_event=None):
        super().__init__()
        self.stop_event = stop_event or threading.Event()

    def should_stop(self):
        return (
            self.stop_event.is_set()
            or QThread.currentThread().isInterruptionRequested()
        )


class AIThread(WorkerThread):
    ai_ready = Signal()

    def __init__(self, stop_event):
        super().__init__(stop_event)

    def run(self):
        try:
            BaseOptions = mp.tasks.BaseOptions
            GestureRecognizer = mp.tasks.vision.GestureRecognizer
            GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode
            model_path = os.path.join(
                STATE.BASE_DIR, "model", "gesture_recognizer.task"
            )
            with open(model_path, "rb") as f:
                data = f.read()
            options = GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_buffer=data),
                num_hands=2,
                min_hand_detection_confidence=0.65,
                min_hand_presence_confidence=0.65,
                min_tracking_confidence=0.65,
                running_mode=VisionRunningMode.IMAGE,
            )
            recognizer = GestureRecognizer.create_from_options(options)
        except Exception as e:
            print(f"ERROR in AI Thread: {e}")
            return
        try:
            self.ai_ready.emit()
            while not self.should_stop():
                width, height = Frame.get_size()
                rgb = Frame.get_ai()
                if rgb is None:
                    time.sleep(0.01)
                    continue
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = recognizer.recognize(mp_image)
                hand_labels = []
                if result.hand_landmarks and result.handedness:
                    for i, handedness_list in enumerate(result.handedness):
                        if not handedness_list:
                            continue
                        hand = handedness_list[0]
                        label = hand.category_name
                        wrist = result.hand_landmarks[i][0]
                        x = int(wrist.x * AI_FRAME_SIZE[0])
                        y = int(wrist.y * AI_FRAME_SIZE[1])
                        hand_labels.append((label, x, y))
                else:
                    hand_labels = []
                STATE.set_hand_labels(hand_labels)
                if result.hand_landmarks:
                    STATE.set_hand_landmarks(result.hand_landmarks)
                else:
                    STATE.set_hand_landmarks(None)
                if result.gestures:
                    gesture = result.gestures[0][0]
                    if gesture.score >= CONF_THRESHOLD:
                        word = gesture.category_name
                        now = time.time()
                        if word != STATE._last_word:
                            STATE._last_word = word
                            STATE._last_word_time = now
                        elif (
                            word == STATE._last_word
                            and word != STATE._last_appended_word
                            and (now - STATE._last_word_time) > 0.2
                        ):
                            STATE.append_word(word)
                            STATE._last_appended_word = word
                        sentence = STATE.get_buffer_text()
                        if sentence:
                            STATE.set_subtitle(sentence, duration=3.0)
                else:
                    if time.time() - STATE._last_word_time > 2.0:
                        STATE.clear_buffer()
                        STATE._last_word = None
                        STATE._last_appended_word = None
        finally:
            recognizer.close()
            return


class CameraThread(WorkerThread):
    frame_ready = Signal(object)  # emits np.ndarray
    cam_ready = Signal()

    def __init__(self, stop_event):
        super().__init__(stop_event)

    def run(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("ERROR: Could not open camera")
            return
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        l_text = ""
        for w, h in COMMON_RESOLUTIONS:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if actual_w == w and actual_h == h:
                break
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        if fps <= 0:
            fps = DEFAULT_FPS
        with pyvirtualcam.Camera(
            width=width,
            height=height,
            fps=fps,
            fmt=PixelFormat.RGB,
            device=get_virtual_cam_device("Sevue-VirtualCam")
        ) as cam:
            print("Using virtual cam:", cam.device)
            self.cam_ready.emit()
            retry_count = 0
            max_retries = 5
            while not self.should_stop():
                ret, frame = cap.read()
                if not ret:
                    retry_count += 1
                    if retry_count > max_retries:
                        print("ERROR: Camera read failed too many times")
                        break
                    time.sleep(0.1)
                    continue
                retry_count = 0
                Frame.push(frame)
                subtitle = STATE.get_subtitle()
                now = time.time()
                if STATE.FLIP_VIDEO:
                    frame = cv2.flip(frame, 1)
                frame = render_youtube_cc_prediction(
                    frame=frame,
                    text=subtitle["text"],
                    start_time=subtitle["start"],
                    duration=subtitle["duration"],
                    current_time=now,
                    flip_text=STATE.FLIP_TEXT,
                )
                h_labels = STATE.get_hand_labels()
                ai_w, ai_h = AI_FRAME_SIZE
                for label, x, y in h_labels:
                    draw_x = int(x * width / ai_w)
                    draw_y = int(y * height / ai_h)
                    if STATE.FLIP_HANDS:
                        draw_x = width - draw_x
                    cv2.putText(
                        frame,
                        label,
                        (draw_x, draw_y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 255, 0),
                        3,
                        cv2.LINE_AA,
                    )
                hand_landmarks = STATE.get_hand_landmarks()
                if hand_landmarks and STATE.SHOW_HAND_DEBUG:
                    for landmarks in hand_landmarks:
                        if STATE.FLIP_HANDS:
                            for lm in landmarks:
                                lm.x = 1.0 - lm.x
                        mp_drawing.draw_landmarks(
                            frame,
                            landmarks,
                            mp_hands.HAND_CONNECTIONS,
                            mp_drawing_styles.get_default_hand_landmarks_style(),
                            mp_drawing_styles.get_default_hand_connections_style(),
                        )
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if STATE.SHOW_PREVIEW:
                    self.frame_ready.emit(frame)
                cam.send(frame)
                cam.sleep_until_next_frame()
        cap.release()
        return


class HomePage(QWidget):
    def __init__(self, main):
        super().__init__(main)
        self.main = main

        self.setStyleSheet(
            """
            HomePage {
                background: #121214;
            }
            QLabel#logo {
                background: transparent;
            }
            QPushButton {
                font-family: "Segoe UI", sans-serif;
                font-size: 16px;
                font-weight: 600;
                border-radius: 14px;
                padding: 16px;
                border: none;
            }
            
            /* Primary Button (Start/Stop) */
            QPushButton#mainBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2a67f5, stop:1 #00c6ff);
                color: white;
            }
            QPushButton#mainBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b7dff, stop:1 #33d1ff);
            }
            QPushButton#mainBtn:checked {
                background: #2a2a30; /* Darker state for 'Stop' or active */
                border: 2px solid #ff4b4b;
                color: #ff4b4b;
            }
            QPushButton#mainBtn:checked:hover {
                background: #33333a;
            }
            
            /* Secondary Button (Settings) */
            QPushButton#settingsBtn {
                background: #1b1b1f;
                color: #e0e0e0;
                border: 1px solid #33333a;
            }
            QPushButton#settingsBtn:hover {
                background: #2a2a33;
                border: 1px solid #4a4a55;
            }
            """
        )

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(40)
        layout.setContentsMargins(40, 60, 40, 60)

        # Logo
        logo = QLabel()
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        logo_path = os.path.join(STATE.BASE_DIR, "icons", "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            logo.setPixmap(
                pixmap.scaled(240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            logo.setText("SEVUE")
            logo.setStyleSheet(
                "font-size: 64px; font-weight: 800; color: white; letter-spacing: 4px;"
            )

        logo.setAccessibleName("SEVUE logo")

        # Buttons Container
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.setAlignment(Qt.AlignCenter)

        self.toggle_btn = QPushButton("Start Sevue")
        self.toggle_btn.setObjectName("mainBtn")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setFixedSize(260, 56)
        self.toggle_btn.setAutoRepeat(False)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self.main.toggle_camera)

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("settingsBtn")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setFixedSize(260, 56)
        settings_btn.clicked.connect(self.main.show_settings)

        btn_layout.addWidget(self.toggle_btn)
        btn_layout.addWidget(settings_btn)

        layout.addStretch()
        layout.addWidget(logo)
        layout.addSpacing(20)
        layout.addLayout(btn_layout)
        layout.addStretch()

        self.setLayout(layout)


class MainWindow(QMainWindow):
    _instance = None

    @staticmethod
    def instance():
        return MainWindow._instance

    def __init__(self):
        super().__init__()
        self.stack = QStackedWidget(self)
        MainWindow._instance = self
        self.setWindowTitle("Sevue")
        self.home_page = HomePage(self)
        self.settings_page = SettingsPage(self)
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.settings_page)
        self.setCentralWidget(self.stack)
        self.stack.setCurrentIndex(0)
        self.stop_event = None
        self.cam_thread = None
        self.ai_thread = None
        self.camera_running = False
        self.cam_ready = False
        self.ai_ready = False
        self.setup_tray()
        self.setup_shortcuts()
        self.update_tray_action()

    def on_thread_finished(self):
        if (self.cam_thread and self.cam_thread.isRunning()) or (
            self.ai_thread and self.ai_thread.isRunning()
        ):
            return
        self.cam_thread = None
        self.ai_thread = None
        self.cam_ready = False
        self.ai_ready = False
        self.home_page.toggle_btn.setText("Start Sevue")
        self.home_page.toggle_btn.setChecked(False)
        self.home_page.toggle_btn.setEnabled(True)
        self.camera_running = False

    def on_cam_ready(self):
        self.cam_ready = True
        self._check_all_ready()

    def on_ai_ready(self):
        self.ai_ready = True
        self._check_all_ready()

    def _check_all_ready(self):
        if not (self.cam_ready and self.ai_ready):
            return
        self.camera_running = True
        self.home_page.toggle_btn.setText("stop Sevue")
        self.home_page.toggle_btn.setChecked(True)
        self.home_page.toggle_btn.setEnabled(True)

    def toggle_camera(self):
        if not self.camera_running:
            self.home_page.toggle_btn.setEnabled(False)
            self.home_page.toggle_btn.setText("Sevue is Starting…")
            self.stop_event = threading.Event()
            self.cam_ready = False
            self.ai_ready = False
            self.cam_thread = CameraThread(self.stop_event)
            self.ai_thread = AIThread(self.stop_event)
            self.cam_thread.cam_ready.connect(self.on_cam_ready)
            self.ai_thread.ai_ready.connect(self.on_ai_ready)
            self.cam_thread.finished.connect(self.on_thread_finished)
            self.ai_thread.finished.connect(self.on_thread_finished)
            self.cam_thread.frame_ready.connect(self.settings_page.on_frame)
            self.cam_thread.start()
            self.ai_thread.start()
        else:
            self.home_page.toggle_btn.setEnabled(False)
            self.home_page.toggle_btn.setText("Sevue is Stopping…")
            self.stop_event.set()
            if self.cam_thread:
                self.cam_thread.requestInterruption()
            if self.ai_thread:
                self.ai_thread.requestInterruption()

    def toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.restore_window()
        self.update_tray_action()

    def update_tray_action(self):
        if self.isVisible() and not self.isMinimized():
            self.toggle_window_action.setText("Hide")
        else:
            self.toggle_window_action.setText("Show")

    def setup_tray(self):
        icon_path = os.path.join(STATE.BASE_DIR, "icons", "favicon.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            print(f"Warning: Icon not found at {icon_path}, using default")
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.blue)
            icon = QIcon(pixmap)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Sevue")
        menu = QMenu()
        # add restore/hide action
        self.toggle_window_action = menu.addAction("Show")
        self.toggle_window_action.triggered.connect(self.toggle_window_visibility)
        menu.addAction("Exit", self.exit_app)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def closeEvent(self, event: QCloseEvent):
        print("Close event received")
        if self.stop_event:
            self.stop_event.set()
        if self.cam_thread and self.cam_thread.isRunning():
            self.cam_thread.requestInterruption()
            self.cam_thread.wait(2000)
        if self.ai_thread and self.ai_thread.isRunning():
            self.ai_thread.requestInterruption()
            self.ai_thread.wait(2000)
        QApplication.quit()

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event):
        if self.isMinimized():
            self.hide()
            self.update_tray_action()

    def show_settings(self):
        self.setWindowTitle("Settings")
        self.stack.setCurrentIndex(1)

    def show_home(self):
        self.setWindowTitle("Sevue")
        self.stack.setCurrentIndex(0)
        self.home_page.toggle_btn.setChecked(self.camera_running)

    def dispatch_action(self, action):
        if action == "hide":
            if self.stack.currentIndex() == 1:
                self.show_home()
            else:
                self.toggle_window_visibility()
            return
        cfg = STATE.FEATURES.get(action)
        if not cfg:
            return

        match cfg["type"]:
            case "state":
                attr = cfg["state"]
                new_value = not getattr(STATE, attr)
                STATE.set_flag(attr, new_value)

    def setup_shortcuts(self):
        for action, cfg in STATE.FEATURES.items():
            if "shortcut" not in cfg:
                continue
            shortcut = QShortcut(QKeySequence(cfg["shortcut"]), self)
            shortcut.activated.connect(partial(self.dispatch_action, action))

    def exit_app(self):
        self.close()


class Toggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 28)
        self.setCursor(Qt.PointingHandCursor)
        self._bg_color = QColor("#33333a")
        self._circle_position = 3
        self._radius = 11  # knob radius

        self.animation = QPropertyAnimation(self, b"circlePosition", self)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.setDuration(200)
        self.stateChanged.connect(self.start_transition)

    @Property(float)
    def circlePosition(self):
        return self._circle_position

    @circlePosition.setter
    def circlePosition(self, pos):
        self._circle_position = pos
        self.update()

    def start_transition(self, value):
        self.animation.stop()
        if value:
            self.animation.setEndValue(self.width() - 25)
        else:
            self.animation.setEndValue(3)
        self.animation.start()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Draw Background
        if self.isChecked():
            p.setBrush(QColor("#2a67f5"))
        else:
            p.setBrush(QColor("#33333a"))  # Dark grey for unchecked

        p.setPen(Qt.NoPen)
        rect = self.rect()
        p.drawRoundedRect(0, 0, rect.width(), rect.height(), 14, 14)

        # Draw Circle (Knob)
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(int(self._circle_position), 3, 22, 22)


class SettingsPage(QWidget):
    def __init__(self, main):
        super().__init__(main)
        STATE.changed.connect(self.on_state_changed)
        self.main = main
        self.setStyleSheet(
            """
            SettingsPage {
                background: #121214;
                font-family: "Segoe UI", sans-serif;
                color: #e0e0e0;
            }
            /* Sidebar styling */
            QWidget#sidebar {
                background: #1b1b1f;
                border-right: 1px solid #2a2a30;
            }
            QLabel#pageTitle {
                font-size: 26px;
                font-weight: 700;
                color: #ffffff;
                margin-left: 4px;
            }
            QLabel#sectionTitle {
                font-size: 20px;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 8px;
            }

            QListWidget#navList {
                background: transparent;
                border: none;
                padding: 4px 0;
                outline: 0;
            }
            QListWidget#navList::item {
                padding: 12px 16px;
                border-radius: 10px;
                margin-bottom: 4px;
                color: #90909a;
                font-weight: 500;
                font-size: 15px;
            }
            QListWidget#navList::item:hover {
                background: #2a2a33;
                color: #ffffff;
            }
            QListWidget#navList::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2a67f5, stop:1 #00c6ff);
                color: white;
                border: 1px solid #4ea4f6;
            }
            
            /* Content Area */
            QFrame#card {
                background: #1b1b1f;
                border: 1px solid #2a2a30;
                border-radius: 16px;
            }
            QLabel#cardTitle {
                font-size: 16px;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 2px;
            }
            QLabel#cardSubtitle {
                font-size: 13px;
                color: #888899;
                line-height: 1.3;
            }
            QPushButton#backBtn {
                padding: 4px 10px;
                border: 1px solid #33333a;
                border-radius: 8px;
                background: #232329;
                color: #e0e0e0;
                font-weight: 600;
                font-size: 11px;
                text-align: center;
            }
            QPushButton#backBtn:hover {
                background: #2a2a33;
                border-color: #555;
            }
            QLabel#preview {
                border: 1px solid #2a2a30;
                border-radius: 12px;
                background: #000;
                color: #555;
            }
            /* Scrollbar */
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #33333a;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #444455;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """
        )

        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(24, 32, 24, 24)
        sidebar_layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")

        # Back Button in Sidebar
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("backBtn")
        back_btn.setFixedSize(70, 26)  # Make it small and fixed
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.main.show_home)

        nav = QListWidget()
        nav.setObjectName("navList")
        nav_items = [
            ("General", "sliders"),
            ("Video", "camera"),
            ("Accessibility", "user"),
            ("Advanced", "cpu"),
        ]
        for name, icon in nav_items:
            nav.addItem(name)
        nav.setCurrentRow(0)

        sidebar_layout.addWidget(back_btn, 0, Qt.AlignLeft)
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(nav)
        sidebar_layout.addStretch()
        sidebar.setLayout(sidebar_layout)
        sidebar.setFixedWidth(280)

        # --- Content Area ---
        content_panel = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(40, 32, 40, 32)
        content_layout.setSpacing(24)

        # Header
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        section_title = QLabel("General")
        section_title.setObjectName("sectionTitle")

        header_row.addWidget(section_title)
        header_row.addStretch()

        # Preview Section
        preview_card = self.card_container()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(20, 20, 20, 20)
        preview_layout.setSpacing(12)

        p_title = QLabel("Device Preview")
        p_title.setObjectName("cardTitle")

        self.preview = QLabel("Waiting for camera...")
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(480, 270)
        self.preview.setSizePolicy(
            self.preview.sizePolicy().horizontalPolicy(),
            self.preview.sizePolicy().verticalPolicy(),
        )

        preview_layout.addWidget(p_title)
        preview_layout.addWidget(self.preview)

        content_layout.addLayout(header_row)
        content_layout.addWidget(preview_card)

        # Toggles Grid
        self.toggles = {}
        for action, cfg in self.iter_setting_features():
            card, checkbox = self.option(cfg)
            self.toggles[action] = checkbox
            content_layout.addWidget(card)

        content_layout.addStretch()
        content_panel.setLayout(content_layout)

        root.addWidget(sidebar)
        root.addWidget(content_panel, 1)
        self.setLayout(root)

    def toggle_style(self):
        return """
        QCheckBox {
            spacing: 0px;
        }
        QCheckBox::indicator {
            width: 50px;
            height: 28px;
        }
        QCheckBox::indicator:unchecked {
            border-radius: 14px;
            background: #2a2a30;
            image: url(none);
        }
        QCheckBox::indicator:checked {
            border-radius: 14px;
            background: #2a67f5;
        }
        """

    def on_state_changed(self, name):
        self.sync_from_state()

    def iter_setting_features(self):
        for action, cfg in STATE.FEATURES.items():
            if cfg["type"] == "state":
                yield action, cfg

    def sync_from_state(self):
        for action, checkbox in self.toggles.items():
            state_attr = STATE.FEATURES[action]["state"]
            checkbox.blockSignals(True)
            checkbox.setChecked(getattr(STATE, state_attr))
            checkbox.blockSignals(False)

    def on_frame(self, frame):
        if not STATE.SHOW_PREVIEW:
            return

        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888)
        self.preview.setPixmap(
            QPixmap.fromImage(img).scaled(
                self.preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def option(self, cfg):
        descriptions = {
            "Flip Camera": "Mirror the video feed horizontally for a natural reflection.",
            "Flip Subtitles": "Reverse text direction when looking into a mirror.",
            "Flip Hands": "Adjust hand tracking coordinates for mirrored display.",
            "hand Debug": "Visualize tracking landmarks and skeletal connections.",
        }
        card = self.card_container()
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 16, 20, 16)
        row.setSpacing(16)

        label_wrap = QVBoxLayout()
        label_wrap.setSpacing(4)

        label = QLabel(cfg["label"])
        label.setObjectName("cardTitle")

        subtitle = QLabel(descriptions.get(cfg["label"], ""))
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)

        label_wrap.addWidget(label)
        if subtitle.text():
            label_wrap.addWidget(subtitle)

        toggle = Toggle()
        # toggle.setCursor(Qt.PointingHandCursor) # Handled in class

        # CSS removed - using custom paint

        label.setBuddy(toggle)
        state_attr = cfg["state"]
        toggle.setChecked(getattr(STATE, state_attr))

        toggle.stateChanged.connect(
            lambda v, attr=state_attr: STATE.set_flag(attr, bool(v))
        )

        row.addLayout(label_wrap)
        row.addWidget(toggle)

        return card, toggle

    def card_container(self):
        card = QFrame()
        card.setObjectName("card")
        return card


class Frame:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.width = 0
        self.height = 0
        self.ai_w, self.ai_h = AI_FRAME_SIZE

    def push(self, frame):
        with self.lock:
            self.frame = frame.copy()
            self.height, self.width = frame.shape[:2]

    def get_native(self):
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def get_ai(self):
        with self.lock:
            if self.frame is None:
                return None
            return cv2.cvtColor(
                cv2.resize(self.frame, (self.ai_w, self.ai_h)), cv2.COLOR_BGR2RGB
            )

    def get_size(self):
        with self.lock:
            return self.width, self.height


def main():
    global Frame, STATE
    Frame = Frame()
    STATE = State()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
