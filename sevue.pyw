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
)
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QIcon,
    QShortcut,
    QKeySequence,
    QCloseEvent,
    QGuiApplication,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from functools import partial
import sys
import json


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
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
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
            backend="unitycapture",
        ) as cam:
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
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo_path = os.path.join(STATE.BASE_DIR, "icons", "favicon.ico")
        pixmap = QPixmap(logo_path)
        logo.setPixmap(
            pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        logo.setAccessibleName("SEVUE logo")
        # Buttons
        self.toggle_btn = QPushButton("Start Sevue")
        self.toggle_btn.setAutoRepeat(False)
        self.toggle_btn.clicked.connect(self.main.toggle_camera)
        settings_btn = QPushButton("Settings")

        for btn in (self.toggle_btn, settings_btn):
            btn.setFixedHeight(40)
            btn.setStyleSheet(
                """
                QPushButton {
                    border: 2px solid black;
                    border-radius: 12px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #eee;
                }
            """
            )

        settings_btn.clicked.connect(self.main.show_settings)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        layout.addWidget(logo)
        layout.addWidget(self.toggle_btn)
        layout.addWidget(settings_btn)
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


class SettingsPage(QWidget):
    def __init__(self, main):
        super().__init__(main)
        STATE.changed.connect(self.on_state_changed)
        self.main = main
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(self.main.show_home)
        layout = QVBoxLayout()
        self.preview = QLabel("Live Preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 240)
        self.preview.setStyleSheet(
            """
            QLabel {
                border: 2px solid black;
                background: #111;
                color: white;
            }
        """
        )

        layout.addWidget(self.preview)
        self.toggles = {}
        for action, cfg in self.iter_setting_features():
            row, checkbox = self.option(cfg)
            self.toggles[action] = checkbox
            layout.addLayout(row)
        layout.addStretch()
        layout.addWidget(back_btn)
        self.setLayout(layout)

    def toggle_style(self):
        return """
        QCheckBox::indicator {
            width: 40px;
            height: 20px;
        }
        QCheckBox::indicator:unchecked {
            border: 1px solid black;
            border-radius: 10px;
            background: white;
        }
        QCheckBox::indicator:checked {
            border: 1px solid black;
            border-radius: 10px;
            background: black;
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
        row = QHBoxLayout()

        label = QLabel(cfg["label"])
        toggle = QCheckBox()
        toggle.setStyleSheet(self.toggle_style())
        label.setBuddy(toggle)
        state_attr = cfg["state"]
        toggle.setChecked(getattr(STATE, state_attr))

        toggle.stateChanged.connect(
            lambda v, attr=state_attr: STATE.set_flag(attr, bool(v))
        )

        row.addWidget(label)
        row.addStretch()
        row.addWidget(toggle)

        return row, toggle


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
