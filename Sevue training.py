import cv2
import mediapipe as mp
import numpy as np
import threading, time, os
from PIL import Image
from imutils.video import WebcamVideoStream
import tensorflow as tf
from sklearn.preprocessing import LabelEncoder
from collections import deque, Counter

# Use PySide6 instead of tkinter
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTextEdit,
)
from PySide6.QtCore import QTimer, Signal, Slot, Qt
from PySide6.QtGui import QImage, QPixmap

# ========== CONFIGURATION ==========
IP_CAM_URL = "http://192.168.1.72:8080/video"
CAM_INDEX = 0

# ========== GLOBAL STATE ==========
data, labels = [], []
current_label = None
capturing = False
capture_start_time = 0
capture_duration = 3
countdown = 0

model = None
classes = None
pred_queue = deque(maxlen=5)
conf_queue = deque(maxlen=5)
frame_counter = 0
PRED_EVERY_N_FRAMES = 2
PRED_THRESHOLD = 0.55
realtime_enabled = False

# ========== TKINTER UI SETUP ==========
app = QApplication([])


class Communicator(QtCore.QObject):
    status_update = Signal(str)
    realtime_update = Signal(bool)
    show_message = Signal(str, str)
    pause_worker = Signal()
    resume_worker = Signal()
    import_done = Signal()
    image_update = Signal(QImage)
    prediction_update = Signal(str)

    @Slot(str)
    def forward_prediction(self, text: str):
        """Slot that runs in the communicator's (main) thread and re-emits prediction_update.
        This ensures the worker's prediction signal is handled on the UI thread and
        avoids cross-thread widget access or missed queued deliveries.
        """
        self.prediction_update.emit(text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gesture Recognition with Holistic")
        self.resize(960, 540)

        # central widget and layouts
        central = QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # video display
        self.video_label = QLabel()
        self.video_label.setStyleSheet("background: black")
        self.video_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.video_label, stretch=1)

        # control row
        ctrl = QtWidgets.QHBoxLayout()
        layout.addLayout(ctrl)

        ctrl.addWidget(QLabel("Gesture Label:"))
        self.label_entry = QLineEdit()
        self.label_entry.setFixedWidth(200)
        ctrl.addWidget(self.label_entry)

        self.capture_btn = QPushButton("Capture")
        ctrl.addWidget(self.capture_btn)

        self.import_btn = QPushButton("Import Folder")
        ctrl.addWidget(self.import_btn)

        self.train_btn = QPushButton("Train")
        ctrl.addWidget(self.train_btn)

        self.show_labels_btn = QPushButton("Show Labels")
        ctrl.addWidget(self.show_labels_btn)

        self.realtime_btn = QPushButton("Realtime: OFF")
        ctrl.addWidget(self.realtime_btn)

        # status label
        self.status_label = QLabel("Status: Idle")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.status_label)

        # prediction text box for accessibility / screen readers
        self.prediction_box = QTextEdit()
        self.prediction_box.setReadOnly(True)
        self.prediction_box.setFixedHeight(48)
        self.prediction_box.setPlaceholderText("Nothing so far")
        # improve accessibility
        self.prediction_box.setAccessibleName("Gesture prediction")
        self.prediction_box.setAccessibleDescription(
            "Latest predicted gesture and confidence"
        )
        layout.addWidget(self.prediction_box)


win = MainWindow()

# communicator for cross-thread UI updates
comm = Communicator()


def get_max_16by9_size(w, h):
    # Returns (width, height) of the largest 16:9 area fitting inside w x h
    aspect_w, aspect_h = 16, 9
    if w / aspect_w < h / aspect_h:
        return w, int(w * aspect_h / aspect_w)
    else:
        return int(h * aspect_w / aspect_h), h


video_canvas = win.video_label
label_entry = win.label_entry
realtime_btn = win.realtime_btn
status_label = win.status_label

win.capture_btn.clicked.connect(lambda: start_capture())
win.import_btn.clicked.connect(lambda: start_import())
win.train_btn.clicked.connect(lambda: start_training())
win.show_labels_btn.clicked.connect(lambda: show_labels())
realtime_btn.clicked.connect(lambda: toggle_realtime())


# connect communicator signals
comm.status_update.connect(lambda s: status_label.setText(s))
comm.realtime_update.connect(
    lambda on: realtime_btn.setText(f"Realtime: {'ON' if on else 'OFF'}")
)
comm.show_message.connect(lambda title, text: QMessageBox.information(win, title, text))

# ========== MEDIA PIPE SETUP ==========
mp_holistic = mp.solutions.holistic
mp_drawing = mp.solutions.drawing_utils
holistic = mp_holistic.Holistic(
    static_image_mode=False,
    model_complexity=0,
    smooth_landmarks=True,
    min_detection_confidence=0.85,
    min_tracking_confidence=0.85,
)

vs = WebcamVideoStream(src=CAM_INDEX).start()
time.sleep(1.0)
if vs.read() is None:
    raise IOError("No working camera stream found.")
cap = vs


# ========== UI BEHAVIOR ==========
def toggle_realtime():
    global realtime_enabled
    realtime_enabled = not realtime_enabled
    comm.realtime_update.emit(realtime_enabled)
    comm.status_update.emit(f"Realtime {'ON' if realtime_enabled else 'OFF'}")


# already connected above


# ========== LANDMARK UTILITIES ==========
def extract_all_landmarks(results):
    features = []

    # Pose (33 landmarks * 4 values)
    if results.pose_landmarks:
        for lm in results.pose_landmarks.landmark:
            features.extend([lm.x, lm.y, lm.z, lm.visibility])
    else:
        features.extend([0] * 33 * 4)

    # Left + Right Hands (21 landmarks * 3 values each)
    for hand in [results.left_hand_landmarks, results.right_hand_landmarks]:
        if hand:
            for lm in hand.landmark:
                features.extend([lm.x, lm.y, lm.z])
        else:
            features.extend([0] * 21 * 3)

    return features


def draw_all_landmarks(frame, results):
    if results.pose_landmarks:
        mp_drawing.draw_landmarks(
            frame,
            results.pose_landmarks,
            mp_holistic.POSE_CONNECTIONS,
            mp_drawing.DrawingSpec(color=(255, 0, 0), thickness=2, circle_radius=2),
            mp_drawing.DrawingSpec(color=(255, 0, 0), thickness=2, circle_radius=2),
        )

    if results.left_hand_landmarks:
        mp_drawing.draw_landmarks(
            frame, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS
        )

    if results.right_hand_landmarks:
        mp_drawing.draw_landmarks(
            frame, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS
        )


# ========== CAPTURE & FRAME PROCESSING THREAD ==========
class FrameWorker(QtCore.QObject):
    """Background worker that reads frames, runs MediaPipe, handles capture/predict, and emits QImage frames."""

    image_ready = Signal(QImage)
    status = Signal(str)
    prediction_ready = Signal(str)
    finished = Signal()

    def __init__(self, cap, parent=None):
        super().__init__(parent)
        self.cap = cap
        self.running = False
        self.paused = False

    @Slot()
    def start(self):
        self.running = True
        # small delay to let camera warm up
        time.sleep(0.05)
        global capturing, frame_counter
        while self.running:
            # honor pause flag to reduce CPU contention during long tasks (e.g., training)
            if getattr(self, "paused", False):
                time.sleep(0.05)
                continue
            try:
                frame = self.cap.read()
                if frame is None:
                    self.status.emit("Camera frame is None")
                    time.sleep(0.05)
                    continue

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = holistic.process(rgb)

                draw_all_landmarks(frame, results)

                if capturing:
                    elapsed = time.time() - capture_start_time
                    if elapsed <= capture_duration:
                        vec = extract_all_landmarks(results)
                        data.append(vec)
                        labels.append(current_label)
                        cv2.putText(
                            frame,
                            f"Capturing {capture_duration-elapsed:.1f}s",
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (0, 255, 0),
                            2,
                        )
                    else:
                        capturing = False
                        self.status.emit(
                            f"Captured {current_label} | Total samples: {len(data)}"
                        )

                display_text = None
                if realtime_enabled and model:
                    frame_counter += 1
                    if frame_counter % PRED_EVERY_N_FRAMES == 0:
                        vec = extract_all_landmarks(results)
                        X = np.array(vec).reshape(1, -1)
                        pred = model.predict(X, verbose=0)[0]
                        idx = int(np.argmax(pred))
                        conf = float(pred[idx])
                        label = str(classes[idx]) if classes is not None else str(idx)
                        pred_queue.append(label)
                        conf_queue.append(conf)
                    if pred_queue:
                        vals, counts = np.unique(pred_queue, return_counts=True)
                        best = vals[np.argmax(counts)]
                        avg_conf = np.mean(
                            [c for p, c in zip(pred_queue, conf_queue) if p == best]
                        )
                        if avg_conf >= PRED_THRESHOLD:
                            display_text = f"{best} ({avg_conf:.2f})"

                if display_text:
                    cv2.putText(
                        frame,
                        display_text,
                        (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 255, 255),
                        2,
                    )

                # emit prediction (empty string when no valid prediction)
                try:
                    self.prediction_ready.emit(display_text or "")
                except RuntimeError:
                    # widget may have been torn down; ignore
                    pass

                # compute target size based on label size
                canvas_w = video_canvas.width()
                canvas_h = video_canvas.height()
                target_w, target_h = get_max_16by9_size(canvas_w, canvas_h)

                if target_w > 0 and target_h > 0:
                    frame = cv2.resize(frame, (target_w, target_h))
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame_rgb.shape
                    bytes_per_line = ch * w
                    qt_img = QImage(
                        frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888
                    )
                    # emit the image
                    self.image_ready.emit(qt_img)

            except Exception as e:
                print(f"[Worker Frame Error] {e}")
                self.status.emit("Camera failed or not ready")
                time.sleep(0.05)

        self.finished.emit()


def countdown_tick():
    global countdown, capturing, capture_start_time
    if countdown > 0:
        comm.status_update.emit(f"Starting in {countdown}...")
        countdown -= 1
        QTimer.singleShot(1000, countdown_tick)
    else:
        comm.status_update.emit("Capturing gesture...")
        capturing = True
        capture_start_time = time.time()


def start_capture():
    global current_label, countdown
    if capturing:
        return
    gesture = label_entry.text().strip()
    if not gesture:
        comm.status_update.emit("Enter gesture name.")
        return
    current_label = gesture
    countdown = 3
    countdown_tick()


def frame_loop():
    global capturing, frame_counter
    try:
        frame = cap.read()
        if frame is None:
            raise ValueError("Frame is None")

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = holistic.process(rgb)

        draw_all_landmarks(frame, results)

        if capturing:
            elapsed = time.time() - capture_start_time
            if elapsed <= capture_duration:
                vec = extract_all_landmarks(results)
                data.append(vec)
                labels.append(current_label)
                cv2.putText(
                    frame,
                    f"Capturing {capture_duration-elapsed:.1f}s",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
            else:
                capturing = False
                comm.status_update.emit(
                    f"Captured {current_label} | Total samples: {len(data)}"
                )

        display_text = None
        if realtime_enabled and model:
            frame_counter += 1
            if frame_counter % PRED_EVERY_N_FRAMES == 0:
                vec = extract_all_landmarks(results)
                X = np.array(vec).reshape(1, -1)
                pred = model.predict(X, verbose=0)[0]
                idx = int(np.argmax(pred))
                conf = float(pred[idx])
                label = str(classes[idx]) if classes is not None else str(idx)
                pred_queue.append(label)
                conf_queue.append(conf)
            if pred_queue:
                vals, counts = np.unique(pred_queue, return_counts=True)
                best = vals[np.argmax(counts)]
                avg_conf = np.mean(
                    [c for p, c in zip(pred_queue, conf_queue) if p == best]
                )
                if avg_conf >= PRED_THRESHOLD:
                    display_text = f"{best} ({avg_conf:.2f})"

        if display_text:
            cv2.putText(
                frame,
                display_text,
                (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 255),
                2,
            )

        # compute target size based on label size
        canvas_w = video_canvas.width()
        canvas_h = video_canvas.height()
        target_w, target_h = get_max_16by9_size(canvas_w, canvas_h)

        if target_w > 0 and target_h > 0:
            frame = cv2.resize(frame, (target_w, target_h))
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            qt_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qt_img)
            video_canvas.setPixmap(pix.scaled(canvas_w, canvas_h, Qt.KeepAspectRatio))

    except Exception as e:
        print(f"[Frame Error] {e}")
        comm.status_update.emit("Camera failed or not ready")

    # schedule is handled by QTimer externally


# ========== MODEL TRAINING (UPGRADED WITH 2-HAND + HOLISTIC SUPPORT) ==========
def train_model():
    global model, classes, pred_queue, conf_queue

    if len(data) < 10:
        comm.status_update.emit("Not enough samples to train.")
        return
    # pause the frame worker to free CPU for training
    comm.pause_worker.emit()
    comm.status_update.emit("Training model...")

    # limit TF threads to reduce contention
    try:
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
    except Exception:
        pass

    X = np.array(data, dtype=np.float32)
    y_raw = np.array(labels)

    encoder = LabelEncoder()
    y = encoder.fit_transform(y_raw)
    classes = encoder.classes_

    print(f"Training on {len(X)} samples with input size {X.shape[1]}")

    model_local = tf.keras.Sequential(
        [
            tf.keras.Input(shape=(X.shape[1],)),
            tf.keras.layers.Dense(256, activation="relu"),
            tf.keras.layers.Dense(128, activation="relu"),
            tf.keras.layers.Dense(len(classes), activation="softmax"),
        ]
    )

    model_local.compile(
        optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"]
    )

    model_local.fit(X, y, epochs=40, batch_size=16, validation_split=0.2, verbose=1)

    loss, acc = model_local.evaluate(X, y, verbose=0)
    print(f"✅ Training Accuracy: {acc * 100:.2f}%")

    model_local.save("gesture_model.h5")
    np.save("classes.npy", classes)
    # export CSV data set
    export_csv_auto("gesture_dataset.csv")
    # Convert to TFLite for Flutter
    converter = tf.lite.TFLiteConverter.from_keras_model(model_local)
    tflite_model = converter.convert()
    with open("gesture_model.tflite", "wb") as f:
        f.write(tflite_model)
    print("✅ gesture_model.tflite exported for Flutter")
    model = model_local
    pred_queue.clear()
    conf_queue.clear()
    comm.status_update.emit(f"Model Trained ✅ Accuracy: {acc*100:.1f}%")
    # resume the worker now that training is done
    comm.resume_worker.emit()


def start_training():
    threading.Thread(target=train_model, daemon=True).start()


def show_labels():
    if not labels:
        comm.show_message.emit("Trained Labels", "No labels have been captured yet.")
        return

    counts = Counter(labels)
    formatted = "\n".join(f"{lbl}: {counts[lbl]} samples" for lbl in sorted(counts))
    comm.show_message.emit("Trained Labels", formatted)


# ========== LOAD EXISTING MODEL ==========
if os.path.exists("gesture_model.h5") and os.path.exists("classes.npy"):
    try:
        model = tf.keras.models.load_model("gesture_model.h5")
        classes = np.load("classes.npy", allow_pickle=True)
        print("Model and classes loaded.")
    except:
        model = None


# ========== IMPORT / EXPORT HELPERS ==========
def import_dataset(folder: str):
    """Import dataset from `folder`. Runs in a background thread.

    Args:
        folder: path to the root folder containing subfolders for each gesture.
    """
    global data, labels

    if not folder:
        comm.import_done.emit()
        return

    comm.status_update.emit("Importing images from folder...")

    added = 0

    for gesture_name in os.listdir(folder):
        gesture_path = os.path.join(folder, gesture_name)
        if not os.path.isdir(gesture_path):
            continue

        for file in os.listdir(gesture_path):
            img_path = os.path.join(gesture_path, file)

            if not img_path.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue

            try:
                img = cv2.imread(img_path)
                if img is None:
                    continue

                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                results = holistic.process(rgb)

                vec = extract_all_landmarks(results)

                data.append(vec)
                labels.append(gesture_name)
                added += 1

            except Exception as e:
                print(f"Failed to process {img_path}: {e}")

    comm.status_update.emit(f"Imported {added} samples from folder ✅")
    comm.import_done.emit()


def export_csv_auto(filename="gesture_dataset.csv"):
    if not data or not labels:
        return

    try:
        with open(filename, "w") as f:
            feature_count = len(data[0])
            header = "label," + ",".join([f"f{i}" for i in range(feature_count)])
            f.write(header + "\n")

            for vec, label in zip(data, labels):
                row = label + "," + ",".join(map(str, vec))
                f.write(row + "\n")

        print(f"✅ Dataset auto-exported to {filename}")

    except Exception as e:
        print(f"CSV Auto Export Failed: {e}")


# ========== RUN ==========
# start FrameWorker in a dedicated QThread
frame_thread = QtCore.QThread()
worker = FrameWorker(cap)
worker.moveToThread(frame_thread)
frame_thread.started.connect(worker.start)
worker.finished.connect(frame_thread.quit)
worker.finished.connect(worker.deleteLater)
frame_thread.finished.connect(frame_thread.deleteLater)

# route worker signals through communicator (ensures handlers run in main thread)
worker.image_ready.connect(comm.image_update.emit)
worker.status.connect(comm.status_update.emit)
# route prediction through communicator slot to ensure main-thread handling
worker.prediction_ready.connect(comm.forward_prediction)

# update UI in main thread via communicator signals (image only here)
comm.image_update.connect(
    lambda qimg: video_canvas.setPixmap(
        QPixmap.fromImage(qimg).scaled(
            video_canvas.width(), video_canvas.height(), Qt.KeepAspectRatio
        )
    )
)

frame_thread.start()

# prediction text updater (avoid repeated identical updates)
last_prediction = ""


def _update_prediction(text: str):
    global last_prediction
    # normalize empty -> show placeholder; handle None safely
    normalized = (text or "").strip()
    if normalized == last_prediction:
        return
    last_prediction = normalized
    # update the text box (main thread) and force a UI refresh
    if not normalized:
        win.prediction_box.setPlainText("Nothing so far")
    else:
        win.prediction_box.setPlainText(normalized)
    # give Qt a chance to process the update immediately
    QtCore.QCoreApplication.processEvents()


# connect prediction update via communicator (ensures main-thread execution)
comm.prediction_update.connect(_update_prediction)

# connect pause/resume signals to worker
comm.pause_worker.connect(lambda: setattr(worker, "paused", True))
comm.resume_worker.connect(lambda: setattr(worker, "paused", False))

# re-enable import button when import completes
comm.import_done.connect(lambda: win.import_btn.setEnabled(True))


def start_import():
    """Prompt for folder on the main thread, then start background import."""
    folder = QFileDialog.getExistingDirectory(win, "Select Gesture Dataset Folder")
    if not folder:
        return
    # disable button while importing
    win.import_btn.setEnabled(False)
    threading.Thread(target=import_dataset, args=(folder,), daemon=True).start()


def _shutdown():
    try:
        # stop worker loop
        worker.running = False
        # stop camera
        cap.stop()
    except Exception:
        pass


app.aboutToQuit.connect(_shutdown)

win.show()
app.exec()
