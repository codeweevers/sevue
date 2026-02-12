import sys

from PySide6.QtWidgets import QApplication

from controllers.main_window_controller import MainWindowController
from models.frame_buffer import FrameBuffer
from models.state_model import StateModel


def main():
    app = QApplication(sys.argv)
    state = StateModel()
    frame_buffer = FrameBuffer()
    window = MainWindowController(state=state, frame_buffer=frame_buffer)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
