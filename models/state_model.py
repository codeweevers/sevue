import json
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence
from platformdirs import PlatformDirs
from pathlib import Path
from services.model_registry_service import ModelRegistryService


class StateModel(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.FLIP_VIDEO = True
        self.FLIP_TEXT = False
        self.FLIP_HANDS = False
        self.CAMERA_INDEX = None
        self._word_buffer = []
        self._last_appended_word = None
        self._last_word = None
        self._last_word_time = 0.0
        self._hand_labels = []
        self.SHOW_HAND_DEBUG = False
        self.SHOW_PREVIEW = True
        self.AUTO_START_CAMERA = False
        self.MINIMIZE_TO_TRAY_WHEN_MINIMIZED = True
        self.CLOSE_TO_TRAY = False
        self.START_MINIMIZED = False
        self.START_ON_BOOT = False
        self.BASE_DIR = self.resource_path("")
        self.model_registry_service = ModelRegistryService(self.BASE_DIR)
        self.selected_model_name = "Default"
        self.model_registry = {}
        self._lock = threading.Lock()
        self._hand_landmarks = None
        self._subtitle = {
            "text": "",
            "start": 0.0,
            "duration": 2.5,
        }
        self.FEATURES = {
            "auto_start_camera": {
                "type": "state",
                "state": "AUTO_START_CAMERA",
                "label": "Start Camera on Launch",
                "category": "General",
                "configurable": True,
            },
            "minimize_to_tray": {
                "type": "state",
                "state": "MINIMIZE_TO_TRAY_WHEN_MINIMIZED",
                "label": "Minimize to Tray when Minimized",
                "category": "General",
                "configurable": True,
            },
            "close_to_tray": {
                "type": "state",
                "state": "CLOSE_TO_TRAY",
                "label": "Close to Tray",
                "category": "General",
                "configurable": True,
            },
            "start_minimized": {
                "type": "state",
                "state": "START_MINIMIZED",
                "label": "Start Minimized",
                "category": "General",
                "configurable": True,
            },
            "start_on_boot": {
                "type": "state",
                "state": "START_ON_BOOT",
                "label": "Start Sevue at System Boot",
                "category": "General",
                "configurable": True,
                "requires_installed_build": True,
            },
            "toggle_camera": {
                "type": "action",
                "label": "Start/Stop Camera",
                "shortcut": "Ctrl+Shift+S",
                "category": "General",
                "configurable": True,
            },
            "hide_close": {
                "type": "action",
                "label": "Hide/Show Window",
                "shortcut": "Ctrl+Shift+M",
                "configurable": True,
            },
            "flip_camera": {
                "type": "state",
                "state": "FLIP_VIDEO",
                "label": "Flip Camera",
                "shortcut": "Ctrl+Shift+C",
                "category": "Video",
                "configurable": True,
            },
            "flip_subtitles": {
                "type": "state",
                "state": "FLIP_TEXT",
                "label": "Flip Subtitles",
                "shortcut": "Ctrl+Shift+O",
                "category": "Video",
                "configurable": True,
            },
            "flip_hands": {
                "type": "state",
                "state": "FLIP_HANDS",
                "label": "Flip Hands",
                "shortcut": "Ctrl+Shift+H",
                "category": "Video",
                "configurable": True,
            },
            "toggle_debug": {
                "type": "state",
                "state": "SHOW_HAND_DEBUG",
                "label": "hand Debug",
                "shortcut": "Ctrl+Shift+D",
                "category": "Video",
                "configurable": True,
            },
            "hide": {
                "type": "action",
                "label": "Hide/Show Window",
                "shortcut": "Esc",
            },
        }
        self.config_path = self.resolve_config_path()
        self.model_path = self.resolve_model_path()
        self.config = self.default_config()
        self.load_config()

    def resource_path(self, relative):
        base_path = Path(
            getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
        )
        return base_path / relative

    def is_installed_build(self):
        return bool(getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"))

    def resolve_config_dir(self):
        dirs = PlatformDirs(appname="Sevue",roaming=True,ensure_exists=True)
        if self.is_installed_build():
            return Path(dirs.user_config_dir)
        return Path(self.BASE_DIR) / "data"

    def resolve_config_path(self):
        return Path(self.resolve_config_dir(), "config.json")

    def resolve_model_path(self):
        selected_name, registry, model_path = (
            self.model_registry_service.resolve_initial_model(self.resolve_config_dir())
        )
        self.selected_model_name = selected_name
        self.model_registry = registry
        return model_path

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

    def get_hand_landmarks(self):
        with self._lock:
            return self._hand_landmarks

    def set_flag(self, name, value):
        with self._lock:
            setattr(self, name, value)
        self.save_config_for_state(name)
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

    def iter_configurable_features(self):
        for action, cfg in self.FEATURES.items():
            if cfg.get("configurable"):
                yield action, cfg

    def iter_setting_features(self):
        for action, cfg in self.FEATURES.items():
            if cfg.get("type") == "state":
                if cfg.get("requires_installed_build") and not self.is_installed_build():
                    continue
                yield action, cfg

    def iter_shortcut_features(self):
        for action, cfg in self.FEATURES.items():
            if cfg.get("configurable") and "shortcut" in cfg:
                yield action, cfg

    def default_config(self):
        features = {}
        for action, cfg in self.iter_configurable_features():
            item = {}
            if cfg["type"] == "state":
                item["state"] = bool(getattr(self, cfg["state"]))
            if "shortcut" in cfg:
                item["shortcut"] = cfg["shortcut"]
            features[action] = item
        return {
            "features": features,
            "camera": {
                "index": self.CAMERA_INDEX,
            },
            "model": {
                "selected": self.selected_model_name,
                "registry": dict(self.model_registry),
            },
        }

    def apply_config(self):
        feature_data = self.config.get("features", {})
        for action, data in feature_data.items():
            cfg = self.FEATURES.get(action)
            if not cfg or not cfg.get("configurable"):
                continue
            if cfg.get("requires_installed_build") and not self.is_installed_build():
                continue
            if cfg["type"] == "state" and "state" in data:
                setattr(self, cfg["state"], bool(data["state"]))
            shortcut = data.get("shortcut")
            if isinstance(shortcut, str) and shortcut.strip():
                shortcut = self.normalize_shortcut(shortcut)
                if self.is_valid_shortcut(shortcut):
                    cfg["shortcut"] = shortcut

        camera_data = self.config.get("camera", {})
        if isinstance(camera_data, dict):
            camera_index = camera_data.get("index")
            if isinstance(camera_index, int) and camera_index >= 0:
                self.CAMERA_INDEX = camera_index
            else:
                self.CAMERA_INDEX = None

        model_data = self.config.get("model", {})
        if isinstance(model_data, dict):
            selected_name, registry, model_path = self.model_registry_service.load_registry(
                config_dir=self.resolve_config_dir(),
                loaded_registry=model_data.get("registry", {}),
                selected_name=model_data.get("selected"),
            )
            self.selected_model_name = selected_name
            self.model_registry = registry
            self.model_path = model_path

    def refresh_config_from_state(self):
        self.config = self.default_config()

    def save_config(self):
        self.refresh_config_from_state()
        with open(self.config_path, "w", encoding="utf-8") as file_obj:
            json.dump(self.config, file_obj, indent=4)

    def load_config(self):
        if not os.path.exists(self.config_path):
            self.save_config()
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as file_obj:
                loaded = json.load(file_obj)
            if not isinstance(loaded, dict):
                raise ValueError("invalid config root")
        except Exception:
            self.save_config()
            return

        self.config = self.default_config()
        loaded_features = loaded.get("features", {})
        if isinstance(loaded_features, dict):
            for action, values in loaded_features.items():
                if action in self.config["features"] and isinstance(values, dict):
                    self.config["features"][action].update(values)
        loaded_camera = loaded.get("camera", {})
        if (
            isinstance(loaded_camera, dict)
            and "camera" in self.config
            and isinstance(self.config["camera"], dict)
        ):
            self.config["camera"].update(loaded_camera)
        loaded_model = loaded.get("model", {})
        if (
            isinstance(loaded_model, dict)
            and "model" in self.config
            and isinstance(self.config["model"], dict)
        ):
            self.config["model"].update(loaded_model)
        self.apply_config()
        self.save_config()

    def save_config_for_state(self, state_name):
        for _, cfg in self.iter_configurable_features():
            if cfg.get("type") == "state" and cfg.get("state") == state_name:
                self.save_config()
                return

    def normalize_shortcut(self, shortcut):
        if not isinstance(shortcut, str):
            return ""
        return QKeySequence(shortcut).toString(QKeySequence.PortableText).strip()

    def is_valid_shortcut(self, shortcut):
        normalized = self.normalize_shortcut(shortcut)
        if not normalized or "," in normalized:
            return False
        parts = [part.strip() for part in normalized.split("+") if part.strip()]
        if len(parts) < 2:
            return False
        modifiers = {"Ctrl", "Alt", "Shift", "Meta"}
        has_modifier = any(part in modifiers for part in parts)
        non_modifiers = [part for part in parts if part not in modifiers]
        return has_modifier and len(non_modifiers) == 1

    def set_shortcut(self, action, shortcut):
        cfg = self.FEATURES.get(action)
        if not cfg or "shortcut" not in cfg:
            return False
        normalized = self.normalize_shortcut(shortcut)
        if not self.is_valid_shortcut(normalized):
            return False
        cfg["shortcut"] = normalized
        self.save_config()
        self.changed.emit(f"shortcut:{action}")
        return True

    def validate_shortcut_update(self, action, new_value):
        if not self.is_valid_shortcut(new_value):
            return False, "Shortcut must be modifier + key (example: Ctrl+Shift+S)."

        normalized = self.normalize_shortcut(new_value)
        for other_action, other_cfg in self.iter_shortcut_features():
            if other_action == action:
                continue
            if self.normalize_shortcut(other_cfg["shortcut"]) == normalized:
                return False, "This shortcut is already in use by another action."

        if not self.set_shortcut(action, normalized):
            return False, "Invalid shortcut."
        return True, ""

    def set_camera_index(self, index, notify=True):
        if index is None:
            new_index = None
        elif isinstance(index, int) and index >= 0:
            new_index = index
        else:
            return False

        if self.CAMERA_INDEX == new_index:
            return True

        self.CAMERA_INDEX = new_index
        self.save_config()
        if notify:
            self.changed.emit("camera:selected")
        return True

    def list_models(self):
        return list(self.model_registry.keys())

    def set_selected_model(self, name, notify=True):
        normalized = str(name or "").strip()
        if normalized not in self.model_registry:
            return False
        if normalized == self.selected_model_name:
            return True

        self.selected_model_name = normalized
        self.model_path = Path(self.model_registry[normalized])
        self.save_config()
        if notify:
            self.changed.emit("model:selected")
        return True

    def import_model(self, source_path, name):
        success, message, model_name, destination = self.model_registry_service.import_model(
            config_dir=self.resolve_config_dir(),
            source_path=source_path,
            name=name,
            existing_names=self.model_registry.keys(),
        )
        if not success:
            return False, message

        self.model_registry[model_name] = str(destination)
        self.save_config()
        return True, ""
