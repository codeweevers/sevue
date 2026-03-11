import threading

class FrameBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None

    def push_latest(self, frame):
        with self.lock:
            self.frame = frame

    def get_ai(self):
        with self.lock:
            frame = self.frame
            self.frame = None
            return frame

    def has_frame(self):
        with self.lock:
            return self.frame is not None