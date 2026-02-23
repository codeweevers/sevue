import threading

import cv2

from constants import AI_FRAME_SIZE


class FrameBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.width = 0
        self.height = 0
        self.ai_w, self.ai_h = AI_FRAME_SIZE

    def push(self, frame):
        with self.lock:
            self.frame = frame.copy()
            self.height, self.width = frame.shape[:2]

    def get_ai(self):
        with self.lock:
            if self.frame is None:
                return None
            return cv2.cvtColor(
                cv2.resize(self.frame, (self.ai_w, self.ai_h)), cv2.COLOR_BGR2RGB
            )
