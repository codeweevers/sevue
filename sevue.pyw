import os
import sys

from PySide6.QtCore import QDir, QLockFile, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from controllers.main_window_controller import MainWindowController
from models.frame_buffer import FrameBuffer
from models.state_model import StateModel

SERVER_NAME = "sevue_single_instance_server"


def acquire_single_instance_lock():
    lock_path = QDir.temp().filePath("sevue_single_instance.lock")
    lock = QLockFile(lock_path)
    if not lock.tryLock(100):
        return None
    return lock


def notify_running_instance():
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def setup_activation_server(window, parent=None):
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer(parent)
    if not server.listen(SERVER_NAME):
        QLocalServer.removeServer(SERVER_NAME)
        if not server.listen(SERVER_NAME):
            return None

    def on_new_connection():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket:
                window.restore_window()
                window.update_tray_action()
                socket.disconnectFromServer()

    server.newConnection.connect(on_new_connection)
    return server


def _build_splash():
    logo_path = os.path.join(os.path.dirname(__file__), "icons", "logo.png")
    pixmap = QPixmap(logo_path)
    if pixmap.isNull():
        pixmap = QPixmap(480, 270)
        pixmap.fill(Qt.black)
    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    splash.showMessage(
        "Starting Sevue...",
        Qt.AlignBottom | Qt.AlignHCenter,
        Qt.white,
    )
    return splash


def _update_splash(app, splash, message):
    if splash is None:
        return
    splash.showMessage(
        message,
        Qt.AlignBottom | Qt.AlignHCenter,
        Qt.white,
    )
    app.processEvents()


def main():
    instance_lock = acquire_single_instance_lock()
    if instance_lock is None:
        notify_running_instance()
        return 0

    app = QApplication(sys.argv)
    splash = _build_splash()
    splash.show()
    app.processEvents()

    _update_splash(app, splash, "Loading settings...")
    state = StateModel()
    frame_buffer = FrameBuffer()

    _update_splash(app, splash, "Initializing window...")
    window = MainWindowController(state=state, frame_buffer=frame_buffer)

    _update_splash(app, splash, "Preparing app...")
    activation_server = setup_activation_server(window, app)
    window.show()
    splash.finish(window)
    exit_code = app.exec()
    if activation_server:
        activation_server.close()
        QLocalServer.removeServer(SERVER_NAME)
    instance_lock.unlock()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
