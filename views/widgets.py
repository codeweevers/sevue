from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox, QPushButton


class EnterPushButton(QPushButton):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.isEnabled():
                self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class Toggle(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 28)
        self.setCursor(Qt.PointingHandCursor)
        self._circle_position = 3

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
        self.animation.setEndValue(self.width() - 25 if value else 3)
        self.animation.start()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QColor("#2a67f5") if self.isChecked() else QColor("#33333a"))
        painter.setPen(Qt.NoPen)
        rect = self.rect()
        painter.drawRoundedRect(0, 0, rect.width(), rect.height(), 14, 14)

        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(self._circle_position), 3, 22, 22)
