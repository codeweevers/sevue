import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from views.widgets import EnterPushButton


class HomePageView(QWidget):
    toggle_camera_requested = Signal()
    show_settings_requested = Signal()

    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir

        self.setStyleSheet(
            """
            HomePageView {
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
                outline: none;
            }
            QPushButton#mainBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2a67f5, stop:1 #00c6ff);
                color: white;
            }
            QPushButton#mainBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b7dff, stop:1 #33d1ff);
            }
            QPushButton#mainBtn:checked {
                background: #2a2a30;
                border: 2px solid #ff4b4b;
                color: #ff4b4b;
            }
            QPushButton#mainBtn:checked:hover {
                background: #33333a;
            }
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

        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setAlignment(Qt.AlignCenter)
        logo_layout.setSpacing(0)

        logo = QLabel()
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)

        logo_path = os.path.join(self.base_dir, "icons", "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            logo.setPixmap(
                pixmap.scaled(240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        title = QLabel("Sevue")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            """
            font-family:  roboto, "Segoe UI", sans-serif;
            font-size: 36px;
            font-weight: 700;
            color: white;
            letter-spacing: 1px;
        """
        )
        logo.setAccessibleName("SEVUE logo")

        logo_layout.addWidget(logo)
        logo_layout.addWidget(title)
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.setAlignment(Qt.AlignCenter)

        self.toggle_btn = EnterPushButton("Start Sevue")
        self.toggle_btn.setObjectName("mainBtn")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setFixedSize(260, 56)
        self.toggle_btn.setAutoRepeat(False)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self.toggle_camera_requested.emit)

        self.settings_btn = EnterPushButton("Settings")
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setFixedSize(260, 56)
        self.settings_btn.clicked.connect(self.show_settings_requested.emit)

        btn_layout.addWidget(self.toggle_btn)
        btn_layout.addWidget(self.settings_btn)

        layout.addStretch()
        layout.addWidget(logo_container)
        layout.addSpacing(20)
        layout.addLayout(btn_layout)
        layout.addStretch()

        self.setLayout(layout)

    def ensure_controls_visible(self):
        self.toggle_btn.setVisible(True)
        self.settings_btn.setVisible(True)
        self.toggle_btn.raise_()
        self.settings_btn.raise_()

    def set_camera_idle(self):
        self.toggle_btn.setText("Start Sevue")
        self.toggle_btn.setChecked(False)
        self.toggle_btn.setEnabled(True)

    def set_camera_starting(self):
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.setText("Sevue is Starting...")

    def set_camera_running(self):
        self.toggle_btn.setText("Stop Sevue")
        self.toggle_btn.setChecked(True)
        self.toggle_btn.setEnabled(True)

    def set_camera_stopping(self):
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.setText("Sevue is Stopping...")
