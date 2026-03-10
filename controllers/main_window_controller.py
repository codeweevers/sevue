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
from workers.camera_utils import CameraManager
from workers.threads import AIThread, CameraThread

try:
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_keyboard = None


class MainWindowController(QMainWindow):
    _instance = None
    global_action = Signal(str)
    camera_devices_refreshed = Signal(list)

    @staticmethod
    def instance():
        return MainWindowController._instance

    def __init__(self, state=None, frame_buffer=None):
        super().__init__()
        self.state = state or StateModel()
        self.frame_buffer = frame_buffer or FrameBuffer()
        self.startup_service = StartupService("Sevue")
        self.camera_manager = CameraManager()

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
        self._camera_refresh_in_progress = False
        self._camera_selection_prepared = False
        self._pending_auto_start_camera = bool(self.state.AUTO_START_CAMERA)
        self._selected_camera_profile = None
        self.camera_refresh_timer = QTimer(self)
        self.camera_refresh_timer.setInterval(15000)
        self.camera_refresh_timer.timeout.connect(self.refresh_camera_devices_async)

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
        self.camera_devices_refreshed.connect(self._on_camera_devices_refreshed)

        self.hide_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.hide_shortcut.activated.connect(
            partial(self.dispatch_action, "hide", True)
        )
        self.setup_shortcuts()
        self.update_tray_action()
        self.refresh_camera_devices_async()
        self.camera_refresh_timer.start()
        self.sync_start_on_boot(show_errors=False)

        if self.state.START_MINIMIZED:
            QTimer.singleShot(0, self.apply_start_minimized)

        if self.state.AUTO_START_CAMERA:
            self._pending_auto_start_camera = True

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

    def on_worker_error(self, title, message):
        show_dialog("ok", message, title, self)
        self.stop_camera_workers(update_ui=True)

    def stop_camera_workers(self, update_ui=False):
        workers_may_exist = bool(
            self.stop_event
            or (self.cam_thread and self.cam_thread.isRunning())
            or (self.ai_thread and self.ai_thread.isRunning())
            or self.camera_running
        )
        if not workers_may_exist:
            return

        if update_ui:
            self.home_page.set_camera_stopping()

        if self.stop_event:
            self.stop_event.set()
        if self.cam_thread:
            self.cam_thread.requestInterruption()
        if self.ai_thread:
            self.ai_thread.requestInterruption()

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
        self.settings_page.reset_preview()

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

    def ensure_camera_ready_for_capture(self):
        cameras = list(self.available_cameras)
        if not cameras:
            cameras = self.refresh_camera_devices()

        if not cameras:
            self.state.set_camera_uid(None, index=None, notify=False)
            self._selected_camera_profile = None
            show_dialog(
                "ok",
                "No camera devices were detected.",
                "Camera Error",
                self,
            )
            return False

        if self.state.CAMERA_UID:
            selected = next(
                (
                    camera
                    for camera in cameras
                    if camera.get("uid") == self.state.CAMERA_UID
                ),
                None,
            )
            if selected:
                self.state.set_camera_uid(
                    selected["uid"], index=selected["index"], notify=False
                )
                return self._probe_selected_camera(selected)

        if len(cameras) == 1:
            only_camera = cameras[0]
            self.state.set_camera_uid(
                only_camera["uid"], index=only_camera["index"], notify=False
            )
            return self._probe_selected_camera(only_camera)

        if isinstance(self.state.CAMERA_INDEX, int):
            by_index = next(
                (
                    camera
                    for camera in cameras
                    if camera["index"] == self.state.CAMERA_INDEX
                ),
                None,
            )
            if by_index:
                self.state.set_camera_uid(
                    by_index["uid"], index=by_index["index"], notify=False
                )
                return self._probe_selected_camera(by_index)

        show_dialog(
            "ok",
            "No camera is selected. Open Settings and choose a camera.",
            "Camera Error",
            self,
        )
        self._selected_camera_profile = None
        return False

    def _probe_selected_camera(self, camera):
        probed_camera = self.camera_manager.probe_camera(camera)
        if not probed_camera:
            self._selected_camera_profile = None
            show_dialog(
                "ok",
                "Could not open the selected camera.",
                "Camera Error",
                self,
            )
            return False

        self._selected_camera_profile = probed_camera
        return True

    def toggle_camera(self):
        cam_active = bool(self.cam_thread and self.cam_thread.isRunning())
        ai_active = bool(self.ai_thread and self.ai_thread.isRunning())
        workers_active = cam_active or ai_active

        if not workers_active and not self.camera_running:
            if not self.ensure_camera_ready_for_capture():
                self.home_page.set_camera_idle()
                return
            self.home_page.set_camera_starting()
            self.stop_event = threading.Event()
            self.cam_ready = False
            self.ai_ready = False

            self.cam_thread = CameraThread(
                self.stop_event,
                self.state,
                self.frame_buffer,
                camera_profile=self._selected_camera_profile,
            )
            self.ai_thread = AIThread(self.stop_event, self.state, self.frame_buffer)

            self.cam_thread.cam_ready.connect(self.on_cam_ready)
            self.ai_thread.ai_ready.connect(self.on_ai_ready)
            self.cam_thread.finished.connect(self.on_thread_finished)
            self.ai_thread.finished.connect(self.on_thread_finished)
            self.cam_thread.frame_ready.connect(self.settings_page.on_frame)
            self.cam_thread.error_reported.connect(self.on_worker_error)
            self.ai_thread.error_reported.connect(self.on_worker_error)

            self.cam_thread.start()
            self.ai_thread.start()
            return

        self.home_page.set_camera_stopping()
        self.stop_camera_workers(update_ui=False)

    def refresh_camera_devices(self):
        try:
            self.available_cameras = self.camera_manager.list_cameras()
        except Exception:
            self.available_cameras = []
        self.settings_page.set_camera_devices(
            self.available_cameras,
            selected_uid=self.state.CAMERA_UID,
            selected_index=self.state.CAMERA_INDEX,
        )
        return self.available_cameras

    def refresh_camera_devices_async(self):
        # Background refresh is name-only discovery (no probing/opening).
        if self.has_active_workers():
            return
        if self._camera_refresh_in_progress:
            return
        self._camera_refresh_in_progress = True

        def _refresh():
            try:
                cameras = self.camera_manager.list_cameras()
            except Exception:
                cameras = []
            self.camera_devices_refreshed.emit(cameras)

        threading.Thread(target=_refresh, daemon=True).start()

    def _on_camera_devices_refreshed(self, cameras):
        self._camera_refresh_in_progress = False
        self.available_cameras = list(cameras or [])
        self.settings_page.set_camera_devices(
            self.available_cameras,
            selected_uid=self.state.CAMERA_UID,
            selected_index=self.state.CAMERA_INDEX,
        )

        if not self._camera_selection_prepared:
            self.prepare_camera_selection(cameras=self.available_cameras)
            self._camera_selection_prepared = True

            if self._pending_auto_start_camera and self.state.CAMERA_UID:
                self._pending_auto_start_camera = False
                QTimer.singleShot(0, self.toggle_camera)
            return

        if self.state.CAMERA_UID:
            selected = next(
                (
                    camera
                    for camera in self.available_cameras
                    if camera.get("uid") == self.state.CAMERA_UID
                ),
                None,
            )
            if selected:
                self.state.set_camera_uid(
                    selected["uid"], index=selected["index"], notify=False
                )
                self._selected_camera_profile = dict(selected)

    def open_camera_selector(self, reason_text=""):
        cameras = list(self.available_cameras)
        if not cameras:
            if self.has_active_workers():
                show_dialog(
                    "ok",
                    "Camera list refresh is paused while capture is running. Stop camera or open Settings again in a moment.",
                    "Camera Selection",
                    self,
                )
                return
            cameras = self.refresh_camera_devices()
        if not cameras:
            show_dialog(
                "ok", "No camera devices were detected.", "Camera Selection", self
            )
            return

        chosen = self.settings_page.prompt_camera_choice(
            cameras, current_uid=self.state.CAMERA_UID, reason_text=reason_text
        )
        if chosen is None:
            return
        selected = next(
            (camera for camera in cameras if camera.get("uid") == chosen), None
        )
        if not selected:
            return
        self.state.set_camera_uid(chosen, index=selected["index"])
        self._selected_camera_profile = dict(selected)
        self.settings_page.set_camera_devices(
            cameras,
            selected_uid=self.state.CAMERA_UID,
            selected_index=self.state.CAMERA_INDEX,
        )

    def prepare_camera_selection(self, cameras=None):
        if cameras is None:
            cameras = self.refresh_camera_devices()
        else:
            cameras = list(cameras)
        if not cameras:
            self.state.set_camera_uid(None, index=None)
            return

        selected_camera = None
        if self.state.CAMERA_UID:
            selected_camera = next(
                (
                    camera
                    for camera in cameras
                    if camera.get("uid") == self.state.CAMERA_UID
                ),
                None,
            )
            if selected_camera:
                self.state.set_camera_index(selected_camera["index"], notify=False)
                return

        saved_index = self.state.CAMERA_INDEX
        if isinstance(saved_index, int):
            selected_camera = next(
                (camera for camera in cameras if camera["index"] == saved_index), None
            )
            if selected_camera:
                self.state.set_camera_uid(
                    selected_camera["uid"], index=selected_camera["index"], notify=False
                )
                return

        has_saved_uid = bool(self.state.CAMERA_UID)
        saved_missing = has_saved_uid

        if len(cameras) == 1:
            only_camera = cameras[0]
            self.state.set_camera_uid(only_camera["uid"], index=only_camera["index"])
            return

        if not has_saved_uid or saved_missing:
            self.show_settings()
            reason = (
                "Your saved camera is no longer available. Choose another camera."
                if saved_missing
                else "Multiple cameras detected. Choose which camera to use."
            )
            self.open_camera_selector(reason)
            if not self.state.CAMERA_UID and cameras:
                first_camera = cameras[0]
                self.state.set_camera_uid(
                    first_camera["uid"], index=first_camera["index"]
                )
            self.show_home()

    def open_model_selector(self):
        result = self.settings_page.prompt_model_choice(
            model_names=self.state.list_models(),
            current_model_name=self.state.selected_model_name,
        )
        if result is None:
            return

        action = result.get("action")
        if action != "apply":
            return

        for model_name in result.get("deletes", []):
            name = str(model_name or "").strip()
            if not name:
                continue
            success, message = self.state.remove_model(name)
            if not success:
                show_dialog("ok", message, "Delete Model", self)
                return

        for item in result.get("imports", []):
            file_path = str(item.get("file_path", "")).strip()
            model_name = str(item.get("model_name", "")).strip()
            if not file_path or not model_name:
                continue

            success, message = self.state.import_model(file_path, model_name)
            if not success:
                show_dialog("ok", message, "Invalid Model Name", self)
                return

        selected_name = str(result.get("selected_model_name", "")).strip()
        if selected_name:
            self.state.set_selected_model(selected_name)

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
        self.tray.activated.connect(
            lambda reason: (
                self.toggle_window_visibility()
                if reason == QSystemTrayIcon.Trigger
                else None
            )
        )

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
        self.stack.setCurrentWidget(self.settings_page)
        self.settings_page.set_camera_devices(
            self.available_cameras,
            selected_uid=self.state.CAMERA_UID,
            selected_index=self.state.CAMERA_INDEX,
        )
        if not self.has_active_workers():
            self.refresh_camera_devices_async()

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
        if name in {"camera:selected", "model:selected"}:
            self.restart_camera_for_selection_change()
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
