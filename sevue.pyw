import sys

from PySide6.QtCore import QDir, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

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


def main():
    instance_lock = acquire_single_instance_lock()
    if instance_lock is None:
        notify_running_instance()
        return 0

    app = QApplication(sys.argv)
    state = StateModel()
    frame_buffer = FrameBuffer()
    window = MainWindowController(state=state, frame_buffer=frame_buffer)
    activation_server = setup_activation_server(window, app)
    window.show()
    exit_code = app.exec()
    if activation_server:
        activation_server.close()
        QLocalServer.removeServer(SERVER_NAME)
    instance_lock.unlock()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
