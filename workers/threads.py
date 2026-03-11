import threading
import time
from copy import deepcopy

import cv2
import mediapipe as mp
import numpy as np
import pyvirtualcam
from pyvirtualcam import PixelFormat
from PySide6.QtCore import QThread, Signal

from constants import (
    AI_FRAME_SIZE,
    CONF_THRESHOLD,
    DEFAULT_FPS,
)
from workers.camera_utils import open_camera_capture
from workers.device_utils import get_virtual_cam_device

mp_hands = mp.tasks.vision.HandLandmarksConnections
mp_drawing = mp.tasks.vision.drawing_utils
mp_drawing_styles = mp.tasks.vision.drawing_styles


class WorkerThread(QThread):
    error_reported = Signal(str, str)

    def __init__(self, stop_event=None):
        super().__init__()
        self.stop_event = stop_event or threading.Event()

    def should_stop(self):
        return (
            self.stop_event.is_set()
            or QThread.currentThread().isInterruptionRequested()
        )

    def report_error(self, title, message):
        self.error_reported.emit(str(title), str(message))


class AIThread(WorkerThread):
    ai_ready = Signal()

    def __init__(self, stop_event, state, frame_buffer):
        super().__init__(stop_event)
        self.state = state
        self.frame_buffer = frame_buffer

    def run(self):
        try:
            base_options = mp.tasks.BaseOptions
            gesture_recognizer = mp.tasks.vision.GestureRecognizer
            gesture_options = mp.tasks.vision.GestureRecognizerOptions
            vision_running_mode = mp.tasks.vision.RunningMode
            model_path = self.state.model_path
            with open(model_path, "rb") as file_obj:
                data = file_obj.read()
            options = gesture_options(
                base_options=base_options(model_asset_buffer=data),
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                running_mode = vision_running_mode.VIDEO
            )
            recognizer = gesture_recognizer.create_from_options(options)
        except Exception as error:
            self.report_error("AI Error", f"Could not start AI processing.\n{error}")
            return

        try:
            self.ai_ready.emit()
            while not self.should_stop():
                rgb = self.frame_buffer.get_ai()
                if rgb is None:
                    time.sleep(0.005)
                    continue

                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp = int(time.monotonic() * 1000)
                result = recognizer.recognize_for_video(mp_image, timestamp)

                hand_labels = []
                if result.hand_landmarks and result.handedness:
                    for index, handedness_list in enumerate(result.handedness):
                        if not handedness_list:
                            continue
                        hand = handedness_list[0]
                        label = hand.category_name
                        wrist = result.hand_landmarks[index][0]
                        x = int(wrist.x * AI_FRAME_SIZE[0])
                        y = int(wrist.y * AI_FRAME_SIZE[1])
                        hand_labels.append((label, x, y))

                self.state.set_hand_labels(hand_labels)
                self.state.set_hand_landmarks(result.hand_landmarks or None)

                if result.gestures:
                    gesture = result.gestures[0][0]
                    if gesture.score >= CONF_THRESHOLD:
                        word = gesture.category_name
                        now = time.time()

                        if word != self.state._last_word:
                            self.state._last_word = word
                            self.state._last_word_time = now
                        elif (now - self.state._last_word_time) > 0.25:
                            if word != self.state._last_appended_word:
                                self.state.append_word(word)
                                self.state._last_appended_word = word
                        sentence = self.state.get_buffer_text()
                        if sentence:
                            self.state.set_subtitle(sentence, duration=3.0)
                elif time.time() - self.state._last_word_time > 2.0:
                    self.state.clear_buffer()
                    self.state._last_word = None
                    self.state._last_appended_word = None
        finally:
            recognizer.close()


class CameraThread(WorkerThread):
    frame_ready = Signal(object)
    cam_ready = Signal()

    def __init__(self, stop_event, state, frame_buffer, camera_profile=None):
        super().__init__(stop_event)
        self.state = state
        self.frame_buffer = frame_buffer
        self.camera_profile = dict(camera_profile or {})

    def wrap_text(self, text, font, font_scale, thickness, max_width):
        """Wrap text into multiple lines based on max pixel width."""
        words = text.split()
        lines = []
        current = ""

        for word in words:
            test = current + (" " if current else "") + word
            (w, _), _ = cv2.getTextSize(test, font, font_scale, thickness)

            if w <= max_width:
                current = test
            else:
                lines.append(current)
                current = word

        if current:
            lines.append(current)

        return lines

    def render_youtube_cc_prediction(
        self,
        frame: np.ndarray,
        text: str,
        start_time: float,
        duration: float,
        current_time: float,
        confidence: float | None = None,
        flip_text: bool = False,
        font_scale: float = 1.0,
        padding: int = 12,
        bottom_margin: int = 60,
        bg_opacity: float = 0.75,
        max_width_ratio: float = 0.8,
    ) -> np.ndarray:
        """
        Render YouTube-style multi-line CC subtitle with timed persistence.
        """

        # ---- Timing gate ----
        if not (start_time <= current_time <= start_time + duration):
            return frame

        if not text:
            return frame

        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = 2

        subtitle = f"{text} ({confidence:.2f})" if confidence is not None else text

        max_text_width = int(w * max_width_ratio)

        # ---- Wrap text ----
        lines = self.wrap_text(subtitle, font, font_scale, thickness, max_text_width)

        # ---- Measure block size ----
        line_sizes = [
            cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines
        ]

        text_width = max(w for w, _ in line_sizes)
        text_height = sum(h for _, h in line_sizes)
        line_spacing = int(font_scale * 10)

        box_w = text_width + padding * 2
        box_h = text_height + padding * 2 + line_spacing * (len(lines) - 1)

        box_x = (w - box_w) // 2
        box_y = h - bottom_margin - box_h

        # ---- Background ----
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (box_x, box_y),
            (box_x + box_w, box_y + box_h),
            (0, 0, 0),
            -1,
        )

        frame = cv2.addWeighted(overlay, bg_opacity, frame, 1 - bg_opacity, 0)

        # ---- Text layer ----
        text_layer = np.zeros_like(frame)

        y = box_y + padding
        for line, (lw, lh) in zip(lines, line_sizes):
            x = box_x + (box_w - lw) // 2
            y += lh
            cv2.putText(
                text_layer,
                line,
                (x, y),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
                cv2.LINE_AA,
            )
            y += line_spacing

        if flip_text:
            text_layer = cv2.flip(text_layer, 1)

        mask = cv2.cvtColor(text_layer, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)

        frame = cv2.bitwise_and(frame, frame, mask=cv2.bitwise_not(mask))
        frame = cv2.add(frame, text_layer)

        return frame

    def run(self):
        if not self.state.CAMERA_UID or not isinstance(self.state.CAMERA_INDEX, int):
            self.report_error(
                "Camera Error",
                "No camera is selected. Open Settings and choose a camera.",
            )
            return

        camera_index = self.state.CAMERA_INDEX

        cap = open_camera_capture(camera_index)
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
        if not cap.isOpened():
            cap.release()
            self.report_error(
                "Camera Error",
                "Could not open the selected camera.",
            )
            return

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        preferred_resolution = None
        resolutions = self.camera_profile.get("resolutions")
        if resolutions:
            top = resolutions[0]
            preferred_resolution = (int(top["width"]), int(top["height"]))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, preferred_resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, preferred_resolution[1])

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(self.camera_profile.get("fps") or DEFAULT_FPS)
        with pyvirtualcam.Camera(
            width=width,
            height=height,
            fps=fps,
            fmt=PixelFormat.RGB,
            device=get_virtual_cam_device("Sevue-VirtualCam"),
        ) as cam:
            self.cam_ready.emit()
            retry_count = 0
            max_retries = 5

            while not self.should_stop():
                ret, frame = cap.read()
                if not ret:
                    retry_count += 1
                    if retry_count > max_retries:
                        self.report_error(
                            "Camera Error",
                            "Camera read failed too many times. Try reselecting the camera in Settings.",
                        )
                        break
                    time.sleep(0.1)
                    continue

                retry_count = 0

                # ----- Adaptive brightness pipeline -----
                brightness = frame.mean()

                # Dark scene
                if brightness < 80:
                    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
                    l,a,b = cv2.split(lab)
                    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
                    l = clahe.apply(l)
                    lab = cv2.merge((l,a,b))
                    frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

                # Backlit / very bright
                elif brightness > 180:
                    frame = cv2.convertScaleAbs(frame, alpha=0.8, beta=-20)

                # Normal lighting
                else:
                    frame = cv2.GaussianBlur(frame,(3,3),0)

                # Edge enhancement for hand details
                frame = cv2.bilateralFilter(frame, 5, 50, 50)

                # Prepare frame for AI
                ai_frame = cv2.resize(frame, AI_FRAME_SIZE)
                ai_frame = cv2.cvtColor(ai_frame, cv2.COLOR_BGR2RGB)

                # Send to AI thread only if previous frame processed
                if not self.frame_buffer.has_frame():
                    self.frame_buffer.push_latest(ai_frame)
                subtitle = self.state.get_subtitle()
                now = time.time()

                if self.state.FLIP_VIDEO:
                    frame = cv2.flip(frame, 1)

                frame = self.render_youtube_cc_prediction(
                    frame=frame,
                    text=subtitle["text"],
                    start_time=subtitle["start"],
                    duration=subtitle["duration"],
                    current_time=now,
                    flip_text=self.state.FLIP_TEXT,
                )

                hand_landmarks = self.state.get_hand_landmarks()
                if hand_landmarks and self.state.SHOW_HAND_DEBUG:
                    h_labels = self.state.get_hand_labels()
                    ai_w, ai_h = AI_FRAME_SIZE
                    for label, x, y in h_labels:
                        draw_x = int(x * width / ai_w)
                        draw_y = int(y * height / ai_h)
                        if self.state.FLIP_HANDS:
                            draw_x = width - draw_x
                        cv2.putText(
                            frame,
                            label,
                            (draw_x, draw_y),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.0,
                            (0, 255, 0),
                            3,
                            cv2.LINE_AA,
                        )

                    for landmarks in hand_landmarks:
                        draw_landmarks = landmarks
                        if self.state.FLIP_HANDS:
                            draw_landmarks = deepcopy(landmarks)
                            for lm in draw_landmarks:
                                lm.x = 1.0 - lm.x
                        mp_drawing.draw_landmarks(
                            frame,
                            draw_landmarks,
                            mp_hands.HAND_CONNECTIONS,
                            mp_drawing_styles.get_default_hand_landmarks_style(),
                            mp_drawing_styles.get_default_hand_connections_style(),
                        )

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if self.state.SHOW_PREVIEW:
                    self.frame_ready.emit(frame)
                cam.send(frame)
                cam.sleep_until_next_frame()

        cap.release()
