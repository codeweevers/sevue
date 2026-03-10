from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from views.widgets import EnterPushButton, Toggle, show_dialog


class SettingsPageView(QWidget):
    show_home_requested = Signal()
    state_toggle_requested = Signal(str, bool)
    camera_select_requested = Signal()
    model_select_requested = Signal()

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPageView")
        self.setAttribute(Qt.WA_StyledBackground, True)  # recommended
        self.state = state
        self.current_category = None
        self.nav_categories = []
        self.option_cards = {}
        self.card_categories = {}
        self.toggles = {}
        self.shortcut_inputs = {}
        self.shortcut_errors = {}
        self.selected_camera_label = "Not selected"

        self.setStyleSheet(
            """
            QWidget#SettingsPageView {
                background: #121214;
                font-family: "Segoe UI", sans-serif;
                color: #e0e0e0;
            }
            QWidget#contentPanel {
                background: #121214;
            }
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

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(24, 32, 24, 24)
        sidebar_layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        back_btn = EnterPushButton("Back")
        back_btn.setObjectName("backBtn")
        back_btn.setAccessibleName("back")
        icon = QIcon("icons/back.png")
        back_btn.setIcon(icon)
        # back_btn.setIconSize(QPixmap("icons/back.png").size())
        back_btn.setFixedSize(70, 30)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.show_home_requested.emit)

        self.nav = QListWidget()
        self.nav.setObjectName("navList")
        self.nav.setAccessibleName("Settings categories")
        self.nav.currentTextChanged.connect(self.on_category_changed)

        sidebar_layout.addWidget(back_btn, 0, Qt.AlignLeft)
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(self.nav)
        sidebar_layout.addStretch()
        sidebar.setLayout(sidebar_layout)
        sidebar.setFixedWidth(280)

        content_panel = QWidget()
        content_panel.setObjectName("contentPanel")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(40, 32, 40, 32)
        content_layout.setSpacing(24)

        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        self.section_title = QLabel("")
        self.section_title.setObjectName("sectionTitle")
        self.section_title.setAccessibleName("Selected category")

        header_row.addWidget(self.section_title)
        header_row.addStretch()

        preview_card = self.card_container()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(20, 20, 20, 20)
        preview_layout.setSpacing(12)

        p_title = QLabel("Device Preview")
        p_title.setObjectName("cardTitle")

        self.preview = QLabel("Waiting for camera...")
        self.preview.setObjectName("preview")
        self.preview.setAccessibleName("Camera preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(480, 270)

        preview_layout.addWidget(p_title)
        preview_layout.addWidget(self.preview)

        content_layout.addLayout(header_row)
        content_layout.addWidget(preview_card)

        self._build_settings_cards(content_layout)

        content_layout.addStretch()
        content_panel.setLayout(content_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFocusPolicy(Qt.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(content_panel)

        root.addWidget(sidebar)
        root.addWidget(scroll, 1)
        self.setLayout(root)

        self.build_nav_categories()
        self.set_initial_category()
        self.sync_from_state()

    def _build_settings_cards(self, content_layout):
        model_card, model_button, model_label = self.model_option()
        self.model_select_button = model_button
        self.model_label = model_label
        model_card_key = "model:select"
        self.option_cards[model_card_key] = model_card
        self.card_categories[model_card_key] = "General"
        content_layout.addWidget(model_card)

        camera_card, camera_button, camera_label = self.camera_option()
        self.camera_select_button = camera_button
        self.camera_label = camera_label
        camera_card_key = "camera:select"
        self.option_cards[camera_card_key] = camera_card
        self.card_categories[camera_card_key] = "Video"
        content_layout.addWidget(camera_card)

        for action, cfg in self.state.iter_setting_features():
            card, checkbox = self.option(cfg)
            self.toggles[action] = checkbox
            card_key = f"state:{action}"
            self.option_cards[card_key] = card
            self.card_categories[card_key] = cfg.get("category", "General")
            content_layout.addWidget(card)

        for action, cfg in self.state.iter_shortcut_features():
            card, input_box, error_label = self.shortcut_option(action, cfg)
            self.shortcut_inputs[action] = input_box
            self.shortcut_errors[action] = error_label
            card_key = f"shortcut:{action}"
            self.option_cards[card_key] = card
            self.card_categories[card_key] = "Shortcuts"
            content_layout.addWidget(card)

    def build_nav_categories(self):
        seen = set()
        self.nav_categories = []
        self.nav.clear()
        for _, cfg in self.state.iter_setting_features():
            category = cfg.get("category", "General")
            if category in seen:
                continue
            seen.add(category)
            self.nav_categories.append(category)
            self.nav.addItem(category)

        if any(True for _ in self.state.iter_shortcut_features()):
            self.nav_categories.append("Shortcuts")
            self.nav.addItem("Shortcuts")

    def set_initial_category(self):
        if not self.nav_categories:
            self.current_category = None
            self.section_title.setText("Settings")
            return
        self.current_category = self.nav_categories[0]
        self.nav.setCurrentRow(0)
        self.update_category_view()

    def on_category_changed(self, category):
        self.current_category = category or None
        self.update_category_view()

    def update_category_view(self):
        self.section_title.setText(self.current_category or "Settings")
        for card_key, card in self.option_cards.items():
            card_category = self.card_categories.get(card_key, "General")
            card.setVisible(card_category == self.current_category)

    def sync_from_state(self):
        for action, checkbox in self.toggles.items():
            state_attr = self.state.FEATURES[action]["state"]
            checkbox.blockSignals(True)
            checkbox.setChecked(getattr(self.state, state_attr))
            checkbox.blockSignals(False)

        for action, button in self.shortcut_inputs.items():
            shortcut_text = self.state.normalize_shortcut(
                self.state.FEATURES[action]["shortcut"]
            )
            button.setText(shortcut_text)

        self.update_shortcut_accessibility()
        self._sync_model_summary()
        self._sync_camera_summary()

    def update_shortcut_accessibility(self):
        for action, input_box in self.shortcut_inputs.items():
            shortcut_value = self.state.normalize_shortcut(
                self.state.FEATURES[action].get("shortcut", "")
            )
            label = self.state.FEATURES[action].get("label", action)
            input_box.setAccessibleName(
                f"{label}, {shortcut_value}. Activate to change this shortcut."
            )

    def _sync_camera_summary(self):
        if hasattr(self, "camera_label"):
            self.camera_label.setText(f"Selected: {self.selected_camera_label}")

    def _sync_model_summary(self):
        if hasattr(self, "model_label"):
            selected = self.state.selected_model_name or "Not selected"
            self.model_label.setText(f"Selected: {selected}")

    def set_camera_devices(self, devices, selected_uid=None, selected_index=None):
        camera_devices = list(devices or [])
        normalized_uid = str(selected_uid or "").strip().lower()
        selected = None
        if normalized_uid:
            selected = next(
                (d for d in camera_devices if d.get("uid") == normalized_uid), None
            )
        if selected is None and isinstance(selected_index, int):
            selected = next(
                (d for d in camera_devices if d["index"] == selected_index), None
            )
        if selected:
            self.selected_camera_label = selected["label"]
        elif len(camera_devices) == 1:
            self.selected_camera_label = camera_devices[0]["label"]
        else:
            self.selected_camera_label = "Not selected"
        self._sync_camera_summary()

    def on_frame(self, frame):
        if not self.state.SHOW_PREVIEW:
            self.reset_preview()
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

    def reset_preview(self, message="Waiting for camera..."):
        self.preview.clear()
        self.preview.setText(message)

    def option(self, cfg):
        card = self.card_container()
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 16, 20, 16)
        row.setSpacing(16)

        label_wrap = QVBoxLayout()
        label_wrap.setSpacing(4)

        label = QLabel(cfg["label"])
        label.setObjectName("cardTitle")

        subtitle = QLabel(cfg.get("description", ""))
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)

        label_wrap.addWidget(label)
        if subtitle.text():
            label_wrap.addWidget(subtitle)

        toggle = Toggle()
        label.setBuddy(toggle)
        state_attr = cfg["state"]
        toggle.setChecked(getattr(self.state, state_attr))
        toggle.setAccessibleName(cfg["label"])
        toggle.setAccessibleDescription(subtitle.text() or cfg["label"])
        toggle.stateChanged.connect(
            lambda value, action=cfg["state"]: self.state_toggle_requested.emit(
                action, bool(value)
            )
        )

        row.addLayout(label_wrap)
        row.addWidget(toggle)

        return card, toggle

    def camera_option(self):
        card = self.card_container()
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 16, 20, 16)
        row.setSpacing(16)

        label_wrap = QVBoxLayout()
        label_wrap.setSpacing(4)

        label = QLabel("Camera Device")
        label.setObjectName("cardTitle")

        subtitle = QLabel("Choose which physical camera Sevue should use for capture.")
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)

        current = QLabel("Selected: Not selected")
        current.setObjectName("cardSubtitle")
        current.setWordWrap(True)

        label_wrap.addWidget(label)
        label_wrap.addWidget(subtitle)
        label_wrap.addWidget(current)

        choose_btn = EnterPushButton("Choose Camera")
        choose_btn.setObjectName("settingsBtn")
        choose_btn.setFixedWidth(190)
        choose_btn.setCursor(Qt.PointingHandCursor)
        choose_btn.setFocusPolicy(Qt.StrongFocus)
        choose_btn.clicked.connect(self.camera_select_requested.emit)

        row.addLayout(label_wrap)
        row.addWidget(choose_btn)
        return card, choose_btn, current

    def model_option(self):
        card = self.card_container()
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 16, 20, 16)
        row.setSpacing(16)

        label_wrap = QVBoxLayout()
        label_wrap.setSpacing(4)

        label = QLabel("AI Model")
        label.setObjectName("cardTitle")

        subtitle = QLabel(
            "Choose an existing model or import a custom .task/.tasks model."
        )
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)

        current = QLabel("Selected: Not selected")
        current.setObjectName("cardSubtitle")
        current.setWordWrap(True)

        label_wrap.addWidget(label)
        label_wrap.addWidget(subtitle)
        label_wrap.addWidget(current)

        choose_btn = EnterPushButton("Choose Model")
        choose_btn.setObjectName("settingsBtn")
        choose_btn.setFixedWidth(190)
        choose_btn.setCursor(Qt.PointingHandCursor)
        choose_btn.setFocusPolicy(Qt.StrongFocus)
        choose_btn.clicked.connect(self.model_select_requested.emit)

        row.addLayout(label_wrap)
        row.addWidget(choose_btn)
        return card, choose_btn, current

    def shortcut_option(self, action, cfg):
        descriptions = {
            "Start/Stop Camera": "Toggle camera capture from anywhere using a global hotkey.",
            "Flip Camera": "Toggle camera mirroring.",
            "Flip Subtitles": "Toggle subtitle mirroring.",
            "Flip Hands": "Toggle hand landmark mirroring.",
            "hand Debug": "Toggle hand debug overlay.",
        }
        card = self.card_container()
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 16, 20, 16)
        row.setSpacing(16)

        label_wrap = QVBoxLayout()
        label_wrap.setSpacing(4)

        label = QLabel(f'{cfg.get("label", action)} Shortcut')
        label.setObjectName("cardTitle")

        subtitle = QLabel(
            f'{descriptions.get(cfg.get("label", action), "")} Use modifier + key only.'
        )
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)

        error = QLabel("")
        error.setObjectName("cardSubtitle")
        error.setStyleSheet("color: #ff6b6b;")
        error.setVisible(False)

        label_wrap.addWidget(label)
        label_wrap.addWidget(subtitle)
        label_wrap.addWidget(error)

        input_box = EnterPushButton(self.state.normalize_shortcut(cfg["shortcut"]))
        input_box.setObjectName("settingsBtn")
        input_box.setFixedWidth(190)
        input_box.setCursor(Qt.PointingHandCursor)
        input_box.setFocusPolicy(Qt.StrongFocus)
        label.setBuddy(input_box)
        input_box.clicked.connect(
            lambda _, key=action: self.on_shortcut_button_clicked(key)
        )

        row.addLayout(label_wrap)
        row.addWidget(input_box)
        return card, input_box, error

    def on_shortcut_button_clicked(self, action):
        dialog = QDialog(self)
        dialog.setWindowTitle(
            f'Set {self.state.FEATURES[action].get("label", action)} Shortcut'
        )
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        prompt = QLabel("Press a modifier + key, then click OK.")
        prompt.setWordWrap(True)
        editor = QKeySequenceEdit()
        editor.setMaximumSequenceLength(1)
        editor.setKeySequence(QKeySequence(self.state.FEATURES[action]["shortcut"]))
        editor.setFocusPolicy(Qt.StrongFocus)

        captured_label = QLabel("")
        captured_label.setObjectName("cardSubtitle")
        captured_label.setWordWrap(True)
        captured_label.setText(
            f"Captured shortcut: {self.state.normalize_shortcut(self.state.FEATURES[action]['shortcut'])}"
        )

        def on_capture_changed(seq):
            captured = seq.toString(QKeySequence.PortableText).strip() or "None"
            captured_label.setText(f"Captured shortcut: {captured}")

        editor.keySequenceChanged.connect(on_capture_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)
        accept_shortcut_return = QShortcut(QKeySequence("Return"), dialog)
        accept_shortcut_enter = QShortcut(QKeySequence("Enter"), dialog)
        cancel_shortcut = QShortcut(QKeySequence("Esc"), dialog)
        accept_shortcut_return.activated.connect(dialog.accept)
        accept_shortcut_enter.activated.connect(dialog.accept)
        cancel_shortcut.activated.connect(dialog.reject)

        layout.addWidget(prompt)
        layout.addWidget(editor)
        layout.addWidget(captured_label)
        layout.addWidget(buttons)
        editor.setFocus()

        if dialog.exec() != QDialog.Accepted:
            return

        new_value = editor.keySequence().toString(QKeySequence.PortableText).strip()
        if not new_value:
            return

        ok, message = self.state.validate_shortcut_update(action, new_value)
        if ok:
            self.clear_shortcut_error(action)
        else:
            self.show_shortcut_error(action, message)
            show_dialog("ok", message, "Invalid Shortcut", self)

    def prompt_camera_choice(self, devices, current_uid=None, reason_text=""):
        if not devices:
            show_dialog(
                "ok", "No camera devices were detected.", "Camera Selection", self
            )
            return None

        dialog = QDialog(self)
        dialog.setWindowTitle("Choose Camera")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        prompt_text = reason_text or "Choose a camera device for Sevue."
        prompt = QLabel(prompt_text)
        prompt.setWordWrap(True)

        combo = QComboBox()
        for camera in devices:
            combo.addItem(camera["label"], camera.get("uid"))

        normalized_uid = str(current_uid or "").strip().lower()
        if normalized_uid:
            for idx, camera in enumerate(devices):
                if str(camera.get("uid", "")).strip().lower() == normalized_uid:
                    combo.setCurrentIndex(idx)
                    break

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        layout.addWidget(prompt)
        layout.addWidget(combo)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None
        return combo.currentData()

    def prompt_model_choice(self, model_names, current_model_name):
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose Model")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        prompt = QLabel(
            "Choose a model, import with Browse, or delete the selected model."
        )
        prompt.setWordWrap(True)

        combo = QComboBox()
        for model_name in model_names:
            combo.addItem(model_name, model_name)
        if current_model_name:
            index = combo.findData(current_model_name)
            if index >= 0:
                combo.setCurrentIndex(index)

        browse_btn = EnterPushButton("Browse")
        browse_btn.setObjectName("settingsBtn")
        browse_btn.setFixedWidth(120)
        delete_btn = EnterPushButton("Delete")
        delete_btn.setObjectName("settingsBtn")
        delete_btn.setFixedWidth(120)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        pending_imports = []
        pending_deletes = []

        def has_name(name):
            target = str(name or "").strip().lower()
            if not target:
                return False
            for idx in range(combo.count()):
                if str(combo.itemData(idx) or "").strip().lower() == target:
                    return True
            return False

        def on_browse():
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Model",
                "",
                "Model files (*.task);;All files (*)",
            )
            if not file_path:
                return
            model_name = self.prompt_model_name()
            if model_name is None:
                return
            model_name = str(model_name).strip()
            if not model_name:
                return
            if has_name(model_name):
                show_dialog(
                    "ok",
                    "A model with this name already exists.",
                    "Invalid Model Name",
                    self,
                )
                return

            combo.addItem(model_name, model_name)
            combo.setCurrentIndex(combo.count() - 1)
            pending_imports.append({"model_name": model_name, "file_path": file_path})

        browse_btn.clicked.connect(on_browse)

        def on_delete():
            selected_name = str(combo.currentData() or "").strip()
            if not selected_name:
                return
            if selected_name == "Default":
                show_dialog(
                    "ok",
                    "The Default model cannot be deleted.",
                    "Delete Model",
                    self,
                )
                return

            should_delete = show_dialog(
                "yes_no",
                f"Delete '{selected_name}'?",
                "Confirm Delete",
                self,
            )
            if not should_delete:
                return

            index = combo.currentIndex()
            if index >= 0:
                combo.removeItem(index)
            previous_len = len(pending_imports)
            pending_imports[:] = [
                item for item in pending_imports if item["model_name"] != selected_name
            ]
            removed_pending_import = len(pending_imports) != previous_len
            if not removed_pending_import and selected_name not in pending_deletes:
                pending_deletes.append(selected_name)

        delete_btn.clicked.connect(on_delete)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(combo, 1)
        row.addWidget(browse_btn)
        row.addWidget(delete_btn)

        layout.addWidget(prompt)
        layout.addLayout(row)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None
        return {
            "action": "apply",
            "selected_model_name": combo.currentData(),
            "imports": list(pending_imports),
            "deletes": list(pending_deletes),
        }

    def prompt_model_name(self):
        name, ok = QInputDialog.getText(
            self,
            "Model Name",
            "Enter a name for this model:",
        )
        if not ok:
            return None
        return name

    def show_shortcut_error(self, action, message):
        label = self.shortcut_errors.get(action)
        button = self.shortcut_inputs.get(action)
        if label:
            label.setText(message)
            label.setVisible(bool(message))
        if button:
            button.setText(
                self.state.normalize_shortcut(self.state.FEATURES[action]["shortcut"])
            )

    def clear_shortcut_error(self, action):
        label = self.shortcut_errors.get(action)
        button = self.shortcut_inputs.get(action)
        if label:
            label.setVisible(False)
        if button:
            button.setText(
                self.state.normalize_shortcut(self.state.FEATURES[action]["shortcut"])
            )

    def card_container(self):
        card = QFrame()
        card.setObjectName("card")
        return card
