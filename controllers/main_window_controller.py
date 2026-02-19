import os
import re
import sys
import threading
from functools import partial

from PySide6.QtCore import Qt, QTimer, Signal, QProcess
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QSystemTrayIcon,
)

from models.frame_buffer import FrameBuffer
from models.state_model import StateModel
from services.startup_service import StartupService
from views.home_page import HomePageView
from views.settings_page import SettingsPageView
from views.widgets import show_dialog
from workers.camera_utils import list_available_cameras
from workers.threads import AIThread, CameraThread

try:
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_keyboard = None


class MainWindowController(QMainWindow):
    _instance = None
    global_action = Signal(str)

    @staticmethod
    def instance():
        return MainWindowController._instance

    def __init__(self, state=None, frame_buffer=None):
        super().__init__()
        self.state = state or StateModel()
        self.frame_buffer = frame_buffer or FrameBuffer()
        self.startup_service = StartupService("Sevue")

        self.stack = QStackedWidget(self)
        self.shortcuts = []
        self.hide_shortcut = None
        self.global_hotkey_listener = None

        MainWindowController._instance = self
        self.setWindowTitle("Sevue")
        self.setWindowIcon(
            QIcon(os.path.join(self.state.BASE_DIR, "icons", "favicon.ico"))
        )
        self.home_page = HomePageView(self.state.BASE_DIR, self)
        self.settings_page = SettingsPageView(self.state, self)

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
        self.available_cameras = []
        self.restart_camera_on_stop = False
        self.is_restarting = False
        self.force_exit_requested = False

        self.toast_label = QLabel(self)
        self.toast_label.setObjectName("shortcutToast")
        self.toast_label.setStyleSheet(
            """
            QLabel#shortcutToast {
                background: rgba(20, 20, 24, 220);
                color: #f3f4f6;
                border: 1px solid #3d3d46;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            """
        )
        self.toast_label.setVisible(False)

        self.setup_tray()
        self._wire_events()

        self.hide_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.hide_shortcut.activated.connect(
            partial(self.dispatch_action, "hide", True)
        )
        self.setup_shortcuts()
        self.update_tray_action()
        self.prepare_camera_selection()
        self.sync_start_on_boot(show_errors=False)

        if self.state.START_MINIMIZED:
            QTimer.singleShot(0, self.apply_start_minimized)

        if self.state.AUTO_START_CAMERA:
            QTimer.singleShot(0, self.toggle_camera)

    def _wire_events(self):
        self.global_action.connect(self.on_global_action)
        self.state.changed.connect(self.on_state_changed)

        self.home_page.toggle_camera_requested.connect(self.toggle_camera)
        self.home_page.show_settings_requested.connect(self.show_settings)

        self.settings_page.show_home_requested.connect(self.show_home)
        self.settings_page.state_toggle_requested.connect(
            self.on_state_toggle_requested
        )
        self.settings_page.camera_select_requested.connect(self.open_camera_selector)
        self.settings_page.model_select_requested.connect(self.open_model_selector)

    def on_state_toggle_requested(self, state_attr, value):
        self.state.set_flag(state_attr, value)

    def on_thread_finished(self):
        if (self.cam_thread and self.cam_thread.isRunning()) or (
            self.ai_thread and self.ai_thread.isRunning()
        ):
            return

        self.cam_thread = None
        self.ai_thread = None
        self.cam_ready = False
        self.ai_ready = False
        self.home_page.set_camera_idle()
        self.camera_running = False

        if self.restart_camera_on_stop:
            self.restart_camera_on_stop = False
            QTimer.singleShot(0, self.toggle_camera)

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
        self.home_page.set_camera_running()

    def toggle_camera(self):
        cam_active = bool(self.cam_thread and self.cam_thread.isRunning())
        ai_active = bool(self.ai_thread and self.ai_thread.isRunning())
        workers_active = cam_active or ai_active

        if not workers_active and not self.camera_running:
            self.home_page.set_camera_starting()
            self.stop_event = threading.Event()
            self.cam_ready = False
            self.ai_ready = False

            self.cam_thread = CameraThread(
                self.stop_event, self.state, self.frame_buffer
            )
            self.ai_thread = AIThread(self.stop_event, self.state, self.frame_buffer)

            self.cam_thread.cam_ready.connect(self.on_cam_ready)
            self.ai_thread.ai_ready.connect(self.on_ai_ready)
            self.cam_thread.finished.connect(self.on_thread_finished)
            self.ai_thread.finished.connect(self.on_thread_finished)
            self.cam_thread.frame_ready.connect(self.settings_page.on_frame)

            self.cam_thread.start()
            self.ai_thread.start()
            return

        self.home_page.set_camera_stopping()
        if self.stop_event:
            self.stop_event.set()
        if self.cam_thread:
            self.cam_thread.requestInterruption()
        if self.ai_thread:
            self.ai_thread.requestInterruption()

    def refresh_camera_devices(self):
        self.available_cameras = list_available_cameras()
        self.settings_page.set_camera_devices(
            self.available_cameras, selected_index=self.state.CAMERA_INDEX
        )
        return self.available_cameras

    def open_camera_selector(self, reason_text=""):
        cameras = self.refresh_camera_devices()
        if not cameras:
            show_dialog("ok", "No camera devices were detected.", "Camera Selection", self)
            return

        chosen = self.settings_page.prompt_camera_choice(
            cameras, current_index=self.state.CAMERA_INDEX, reason_text=reason_text
        )
        if chosen is None:
            return
        self.state.set_camera_index(int(chosen))
        self.settings_page.set_camera_devices(
            cameras, selected_index=self.state.CAMERA_INDEX
        )

    def prepare_camera_selection(self):
        cameras = self.refresh_camera_devices()
        if not cameras:
            self.state.set_camera_index(None)
            return

        camera_indices = {camera["index"] for camera in cameras}
        saved_index = self.state.CAMERA_INDEX
        has_saved = isinstance(saved_index, int)
        saved_missing = has_saved and saved_index not in camera_indices

        if len(cameras) == 1:
            only_index = cameras[0]["index"]
            if saved_index != only_index:
                self.state.set_camera_index(only_index)
            return

        if not has_saved or saved_missing:
            self.show_settings()
            reason = (
                "Your saved camera is no longer available. Choose another camera."
                if saved_missing
                else "Multiple cameras detected. Choose which camera to use."
            )
            self.open_camera_selector(reason)
            if self.state.CAMERA_INDEX is None and cameras:
                self.state.set_camera_index(cameras[0]["index"])
            self.show_home()

    def open_model_selector(self):
        while True:
            result = self.settings_page.prompt_model_choice(
                model_names=self.state.list_models(),
                current_model_name=self.state.selected_model_name,
            )
            if result is None:
                return

            action = result.get("action")
            if action == "select":
                model_name = str(result.get("model_name", "")).strip()
                if model_name:
                    self.state.set_selected_model(model_name)
                return

            if action == "browse":
                file_path = str(result.get("file_path", "")).strip()
                if not file_path:
                    continue
                while True:
                    model_name = self.settings_page.prompt_model_name()
                    if model_name is None:
                        break

                    success, message = self.state.import_model(file_path, model_name)
                    if success:
                        self.state.set_selected_model(str(model_name).strip())
                        return

                    show_dialog("ok", message, "Invalid Model Name", self)

    def restart_camera_for_selection_change(self):
        cam_active = bool(self.cam_thread and self.cam_thread.isRunning())
        ai_active = bool(self.ai_thread and self.ai_thread.isRunning())
        workers_active = cam_active or ai_active or self.camera_running
        if not workers_active:
            return
        if self.restart_camera_on_stop:
            return

        self.restart_camera_on_stop = True
        self.home_page.set_camera_stopping()
        if self.stop_event:
            self.stop_event.set()
        if self.cam_thread:
            self.cam_thread.requestInterruption()
        if self.ai_thread:
            self.ai_thread.requestInterruption()

    def has_active_workers(self):
        cam_active = bool(self.cam_thread and self.cam_thread.isRunning())
        ai_active = bool(self.ai_thread and self.ai_thread.isRunning())
        return cam_active or ai_active or self.camera_running

    def restart_application(self):
        program = sys.executable
        if not program:
            show_dialog(
                "ok",
                "Unable to restart Sevue automatically.",
                "Restart Failed",
                self,
            )
            return

        arguments = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        if not QProcess.startDetached(program, arguments):
            show_dialog(
                "ok",
                "Unable to restart Sevue automatically.",
                "Restart Failed",
                self,
            )
            return

        self.is_restarting = True
        self.close()

    def apply_start_minimized(self):
        if not self.state.START_MINIMIZED:
            return
        if self.state.MINIMIZE_TO_TRAY_WHEN_MINIMIZED:
            self.hide()
            self.update_tray_action()
        else:
            self.showMinimized()
            self.update_tray_action()

    def sync_start_on_boot(self, show_errors=True):
        try:
            self.startup_service.sync(
                enabled=self.state.START_ON_BOOT,
                installed_build=self.state.is_installed_build(),
            )
        except Exception:
            if show_errors:
                show_dialog(
                    "ok",
                    "Could not update system boot startup setting.",
                    "Startup Setting Error",
                    self,
                )

    def toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.restore_window()
        self.update_tray_action()

    def update_tray_action(self):
        if not hasattr(self, "toggle_window_action"):
            return
        if self.isVisible() and not self.isMinimized():
            self.toggle_window_action.setText("Hide")
        else:
            self.toggle_window_action.setText("Show")

    def setup_tray(self):
        icon_path = os.path.join(self.state.BASE_DIR, "icons", "favicon.ico")
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
        self.toggle_window_action = menu.addAction("Show")
        self.toggle_window_action.triggered.connect(self.toggle_window_visibility)
        menu.addAction("Exit", self.exit_app)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def closeEvent(self, _event: QCloseEvent):
        if (
            self.state.CLOSE_TO_TRAY
            and not self.force_exit_requested
            and not self.is_restarting
        ):
            self.hide()
            self.update_tray_action()
            _event.ignore()
            return

        self.state.save_config()
        self.stop_shortcuts()

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

    def changeEvent(self, _event):
        if self.isMinimized() and self.state.MINIMIZE_TO_TRAY_WHEN_MINIMIZED:
            self.hide()
        self.update_tray_action()

    def show_settings(self):
        self.setWindowTitle("Settings")
        self.refresh_camera_devices()
        self.stack.setCurrentWidget(self.settings_page)

    def show_home(self):
        self.setWindowTitle("Sevue")
        self.stack.setCurrentWidget(self.home_page)
        self.home_page.ensure_controls_visible()
        self.home_page.updateGeometry()
        if self.home_page.layout():
            self.home_page.layout().activate()

    def dispatch_action(self, action, from_shortcut=False):
        if action == "hide":
            if self.stack.currentWidget() == self.settings_page:
                self.show_home()
                if from_shortcut:
                    self.show_toast("Switched to Home")
            else:
                self.toggle_window_visibility()
                if from_shortcut:
                    self.show_toast("Window hidden/shown")
            return

        cfg = self.state.FEATURES.get(action)
        if not cfg:
            return

        if cfg["type"] == "state":
            attr = cfg["state"]
            new_value = not getattr(self.state, attr)
            self.state.set_flag(attr, new_value)
            if from_shortcut:
                label = cfg.get("label", action)
                state_text = "On" if new_value else "Off"
                self.show_toast(f"{label}: {state_text}")
            return

        if action == "toggle_camera":
            self.toggle_camera()
            if from_shortcut:
                self.show_toast("Camera toggle requested")
        elif action == "hide_close":
            self.dispatch_action("hide", from_shortcut)

    def setup_shortcuts(self):
        self.stop_shortcuts()

        if pynput_keyboard is None:
            print(
                "Warning: pynput is not installed. Falling back to in-app shortcuts only."
            )
            for action, cfg in self.state.FEATURES.items():
                if action == "hide" or "shortcut" not in cfg:
                    continue
                shortcut = QShortcut(QKeySequence(cfg["shortcut"]), self)
                shortcut.activated.connect(partial(self.dispatch_action, action, True))
                self.shortcuts.append(shortcut)
            return

        hotkeys = {}
        for action, cfg in self.state.FEATURES.items():
            if action == "hide":
                continue
            shortcut = cfg.get("shortcut")
            if not isinstance(shortcut, str):
                continue

            normalized = self.state.normalize_shortcut(shortcut)
            if not self.state.is_valid_shortcut(normalized):
                continue

            pynput_shortcut = self.qt_shortcut_to_pynput(normalized)
            if not pynput_shortcut:
                continue

            if pynput_shortcut in hotkeys:
                print(f"Warning: Duplicate shortcut {normalized}; ignoring {action}.")
                continue

            hotkeys[pynput_shortcut] = partial(self.emit_global_action, action)

        if not hotkeys:
            return

        self.global_hotkey_listener = pynput_keyboard.GlobalHotKeys(hotkeys)
        self.global_hotkey_listener.start()

    def stop_shortcuts(self):
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts.clear()

        if self.global_hotkey_listener:
            self.global_hotkey_listener.stop()
            self.global_hotkey_listener = None

    def emit_global_action(self, action):
        self.global_action.emit(action)

    def on_global_action(self, action):
        self.dispatch_action(action, True)

    def qt_shortcut_to_pynput(self, shortcut):
        parts = [part.strip() for part in shortcut.split("+") if part.strip()]
        if not parts:
            return None

        modifiers = []
        key_part = None
        for part in parts:
            if part == "Ctrl":
                modifiers.append("<ctrl>")
            elif part == "Alt":
                modifiers.append("<alt>")
            elif part == "Shift":
                modifiers.append("<shift>")
            elif part == "Meta":
                modifiers.append("<cmd>")
            else:
                key_part = part

        if not modifiers or not key_part:
            return None

        special_map = {
            "Space": "<space>",
            "Tab": "<tab>",
            "Backspace": "<backspace>",
            "Delete": "<delete>",
            "Insert": "<insert>",
            "Home": "<home>",
            "End": "<end>",
            "PgUp": "<page_up>",
            "PgDown": "<page_down>",
            "Left": "<left>",
            "Right": "<right>",
            "Up": "<up>",
            "Down": "<down>",
            "Enter": "<enter>",
            "Return": "<enter>",
            "Escape": "<esc>",
            "Esc": "<esc>",
        }

        if re.fullmatch(r"F([1-9]|1[0-9]|2[0-4])", key_part):
            key_token = f"<{key_part.lower()}>"
        elif len(key_part) == 1:
            key_token = key_part.lower()
        else:
            key_token = special_map.get(key_part)

        if not key_token:
            return None
        return "+".join(modifiers + [key_token])

    def on_state_changed(self, name):
        self.settings_page.sync_from_state()
        if name.startswith("shortcut:"):
            self.setup_shortcuts()
        if name == "camera:selected":
            self.restart_camera_for_selection_change()
        if name == "model:selected":
            if self.has_active_workers():
                self.restart_application()
        if name == "START_ON_BOOT":
            self.sync_start_on_boot(show_errors=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toast_label.isVisible():
            self.position_toast()

    def position_toast(self):
        self.toast_label.adjustSize()
        margin = 16
        x = max(margin, self.width() - self.toast_label.width() - margin)
        y = max(margin, self.height() - self.toast_label.height() - margin)
        self.toast_label.move(x, y)

    def show_toast(self, message, duration_ms=1400):
        self.toast_label.setText(message)
        self.position_toast()
        self.toast_label.show()
        QTimer.singleShot(duration_ms, self.toast_label.hide)

    def exit_app(self):
        self.force_exit_requested = True
        self.close()
