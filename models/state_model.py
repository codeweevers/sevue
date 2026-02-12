import json
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence


class StateModel(QObject):
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
        self._hand_labels = []
        self.SHOW_HAND_DEBUG = False
        self.SHOW_PREVIEW = True
        self.AUTO_START_CAMERA = False
        self.BASE_DIR = self.resource_path("")
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
        self.config_path = os.path.join(self.BASE_DIR, "data", "config.json")
        self.config = self.default_config()
        self.load_config()

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

    def get_hand_landmarks(self):
        with self._lock:
            return self._hand_landmarks

    def set_flag(self, name, value):
        with self._lock:
            setattr(self, name, value)
        self.save_config_for_state(name)
        self.changed.emit(name)

    def set_state_feature(self, action, value):
        cfg = self.FEATURES.get(action)
        if not cfg or cfg.get("type") != "state":
            return False
        self.set_flag(cfg["state"], bool(value))
        return True

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
        return {"features": features}

    def apply_config(self):
        feature_data = self.config.get("features", {})
        for action, data in feature_data.items():
            cfg = self.FEATURES.get(action)
            if not cfg or not cfg.get("configurable"):
                continue
            if cfg["type"] == "state" and "state" in data:
                setattr(self, cfg["state"], bool(data["state"]))
            shortcut = data.get("shortcut")
            if isinstance(shortcut, str) and shortcut.strip():
                shortcut = self.normalize_shortcut(shortcut)
                if self.is_valid_shortcut(shortcut):
                    cfg["shortcut"] = shortcut

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
