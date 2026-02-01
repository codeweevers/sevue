import cv2
import mediapipe as mp
import numpy as np
import os
import shutil
import threading
import time
import tkinter as tk
from tkinter import simpledialog, ttk, messagebox, filedialog
from PIL import Image, ImageTk

# ---------------- CONFIG ----------------
DATA_ROOT = "data"
os.makedirs(DATA_ROOT, exist_ok=True)

TARGET_FPS = 25
WEBCAM_MP_FPS = 20
mp_last_time = 0
video_fps = None

AUTO_RECORD_DURATION = 1.5
SEQ_LEN = 30

STATIC_FRAMES = 5
STATIC_STRIDE = 5      # frames per static sample
STATIC_COOLDOWN = 0.3 # seconds between samples (optional but recommended)

last_static_sample_time = 0

FRAME_W, FRAME_H = 640, 480

# ---------------- STATE ----------------
capture_ready = False   # True when a recording (webcam or video) is finalized
current_gesture = None
recording = False
buffer = []
record_start_time = None

source_mode = "webcam"
running = True

latest_frame = None
frame_lock = threading.Lock()
buffer_lock = threading.Lock()

last_detected_hands = None
last_hands_lock = threading.Lock()

last_hand_time = 0
HAND_TIMEOUT = 0.3  # seconds (300ms)

cap = None
video_cap = None

# ---------------- MEDIAPIPE (LAZY INIT) ----------------
mp_hands = None
mp_draw = mp.solutions.drawing_utils
# ---------------- HELPERS ----------------
def list_gestures():
    return sorted(d for d in os.listdir(DATA_ROOT)
                if os.path.isdir(os.path.join(DATA_ROOT, d)))

def refresh_gesture_list():
    gesture_list.delete(0, tk.END)
    for g in list_gestures():
        gesture_list.insert(tk.END, g)

def reset_buffer():
    global capture_ready, record_start_time
    with buffer_lock:
        buffer.clear()
        capture_ready = False
    record_start_time = None

def select_gesture(event=None):
    global current_gesture
    if recording:
        messagebox.showwarning(
            "Busy",
            "Stop recording before changing gesture."
        )
        return
    sel = gesture_list.curselection()
    if not sel:
        return
    current_gesture = gesture_list.get(sel[0])
    gesture_var.set(current_gesture)
    status_var.set(f"Selected: {current_gesture}")
    update_sample_count()
    update_ui_state()

def save_static_sample(sample):
    if not current_gesture:
        return

    path = os.path.join(DATA_ROOT, current_gesture)
    idx = len(os.listdir(path)) + 1
    gesture = current_gesture
    fname = f"{gesture}_{idx:03d}.npy"
    out = os.path.join(path, fname)

    np.save(out, np.array(sample))
    update_sample_count()

def extract_landmarks(frame, draw=True):
    global mp_hands, last_detected_hands, last_hand_time

    if mp_hands is None:
        return [0.0] * 126
    results = mp_hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    current_time = time.time()

    if results.multi_hand_landmarks and results.multi_handedness:
        with last_hands_lock:
            last_detected_hands = (
                results.multi_hand_landmarks,
                results.multi_handedness
            )
            last_hand_time = current_time

    with last_hands_lock:
        if last_detected_hands and (time.time() - last_hand_time) < HAND_TIMEOUT:
            cached = last_detected_hands
        else:
            last_detected_hands = None
            return [0.0] * 126

    hand_landmarks_list, handedness_list = cached

    # --- NORMALIZE ORDER ---
    left_hand = None
    right_hand = None

    for lm, handedness in zip(hand_landmarks_list, handedness_list):
        label = handedness.classification[0].label
        if label == "Left":
            left_hand = lm
        elif label == "Right":
            right_hand = lm

    lm_out = []

    # --- LEFT HAND (63 values) ---
    if left_hand:
        if draw:
            mp_draw.draw_landmarks(
                frame, left_hand,
                mp.solutions.hands.HAND_CONNECTIONS
            )
            
            # ---- DRAW "L" ABOVE LEFT HAND ----
            wrist = left_hand.landmark[0]
            h, w, _ = frame.shape
            x = int(wrist.x * w)
            y = int(wrist.y * h) - 15

            cv2.putText(
                frame, "L",
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 0, 0),  # Blue for Left
                2
            )
        for p in left_hand.landmark:
            lm_out.extend([p.x, p.y, p.z])
    else:
        lm_out.extend([0.0] * 63)  # PAD

    # --- RIGHT HAND (63 values) ---
    if right_hand:
        if draw:
            mp_draw.draw_landmarks(
                frame, right_hand,
                mp.solutions.hands.HAND_CONNECTIONS
            )
            # ---- DRAW "R" ABOVE RIGHT HAND ----
            wrist = right_hand.landmark[0]
            h, w, _ = frame.shape
            x = int(wrist.x * w)
            y = int(wrist.y * h) - 15

            cv2.putText(
                frame, "R",
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),  # Green for Right
                2
            )
        for p in right_hand.landmark:
            lm_out.extend([p.x, p.y, p.z])
    else:
        lm_out.extend([0.0] * 63)  # PAD

    return lm_out

# ---------------- CAMERA THREAD ----------------
def is_static_gesture():
    return current_gesture is not None and current_gesture.endswith("_STATIC")

def init_mediapipe():
    global mp_hands
    mp_hands = mp.solutions.hands.Hands(
        max_num_hands=2,
        model_complexity=0,
        min_detection_confidence=0.8,
        min_tracking_confidence=0.7
    )

def get_sample_count():
    if not current_gesture:
        return 0
    path = os.path.join(DATA_ROOT, current_gesture)
    if not os.path.exists(path):
        return 0
    return len([f for f in os.listdir(path) if f.endswith(".npy")])

def update_sample_count():
    sample_count_var.set(f"Samples: {get_sample_count()}")

def camera_loop():
    global cap, video_cap, latest_frame, mp_last_time, recording
    global last_static_sample_time, capture_ready, source_mode, record_start_time

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    root.after(0, lambda: status_var.set("Initializing hand tracker..."))
    init_mediapipe()
    root.after(0, lambda: status_var.set("Camera ready"))

    while running:
        start = time.time()
        if source_mode == "video" and video_cap:
            ret, frame = video_cap.read()
            if not ret:
                video_cap.release()
                video_cap = None
                with buffer_lock:
                    if buffer:
                        buffer[:] = normalize_sequence(buffer)
                        capture_ready = True
                    else:
                        capture_ready = False
                recording = False
                source_mode = "webcam"
                record_start_time = None
                root.after(0, update_ui_state)
                root.after(0, lambda: progress_var.set(100))
                root.after(0, lambda: status_var.set("Video processed ✔ — click Save"))
                continue
        else:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)

        # FPS Control for MediaPipe
        lm = None
        now = time.time()
        if source_mode == "video":
            lm = extract_landmarks(frame)
        elif now - mp_last_time >= 1 / WEBCAM_MP_FPS:
            lm = extract_landmarks(frame)
            mp_last_time = now

        if lm:
            valid_landmarks = sum(1 for i in range(0, len(lm), 3) if lm[i] != 0.0)
            
            if recording and valid_landmarks >= 10:
                with buffer_lock:
                    if len(buffer) < SEQ_LEN:
                        buffer.append(lm)
                
                # Update progress
                if recording and not is_static_gesture():
                    if source_mode == "webcam":
                        elapsed = time.time() - record_start_time
                        progress = min(100, (elapsed / AUTO_RECORD_DURATION) * 100)
                    else:  # video
                        progress = min(100, (len(buffer) / SEQ_LEN) * 100)
                    root.after(0, lambda p=progress: progress_var.set(p))

                # Handle Static
                if is_static_gesture():
                    if len(buffer) >= STATIC_FRAMES:
                        if now - last_static_sample_time >= STATIC_COOLDOWN:
                            sample = np.mean(buffer[-STATIC_STRIDE:], axis=0)
                            save_static_sample(sample)
                            last_static_sample_time = now
                            reset_buffer()
                            root.after(0, lambda: status_var.set(f"Static saved ({get_sample_count()})"))

                # Handle Dynamic Webcam Auto-Stop
                elif recording and source_mode == "webcam" and (time.time() - record_start_time) >= AUTO_RECORD_DURATION:
                    with buffer_lock:
                        buffer[:] = normalize_sequence(buffer)
                        capture_ready = True
                    recording = False
                    record_start_time = None
                    root.after(0, lambda: start_btn.config(
                        text="Start",
                        bg="SystemButtonFace",
                        fg="black"
                    ))
                    root.after(0, lambda: progress_var.set(100))
                    root.after(0, update_ui_state)
                    root.after(0, lambda: status_var.set("Recording complete — click Save"))


        # UI Overlays
        if current_gesture:
            cv2.putText(frame, f"{current_gesture} | Samples: {get_sample_count()}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        if recording and int(time.time() * 2) % 2 == 0:
            cv2.putText(frame, "● REC", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # Update global frame for UI thread
        with frame_lock:
            latest_frame = frame.copy()

        # Timing
        if source_mode == "video":
            time.sleep(1 / max(video_fps, 1))
        else:
            elapsed = time.time() - start
            time.sleep(max(0, (1 / TARGET_FPS) - elapsed))

    if cap: cap.release()
    if video_cap: video_cap.release()

# ---------------- UI ACTIONS ----------------
def set_source(mode):
    global source_mode, video_cap, video_fps
    global recording, mp_last_time

    if mode == "video":
        if not current_gesture:
            messagebox.showwarning("Select Gesture", "Please select a gesture before loading a video.")
            return
        path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.avi *.mov")]
        )
        if not path:
            return

        video_cap = cv2.VideoCapture(path)
        video_fps = video_cap.get(cv2.CAP_PROP_FPS) #Remember to add a fallback FPS value later

        if not video_fps or video_fps < 5:
            video_fps = 25  

        source_mode = "video"
        # AUTO-START RECORDING FOR VIDEO
        reset_buffer()
        recording = True
        progress_var.set(0)
        status_var.set(f"Recording video ({int(video_fps)} FPS)...")
        root.after(0, update_ui_state)
        mp_last_time = 0

    else:
        if video_cap:
            video_cap.release()
            video_cap = None
        video_fps = None
        source_mode = "webcam"
        status_var.set("Source: Webcam")
        mp_last_time = 0
        update_ui_state()

def add_gesture():
    win = tk.Toplevel(root)
    win.title("Add Gesture")
    win.grab_set()

    tk.Label(win, text="Gesture name").pack(pady=5)
    name_entry = tk.Entry(win)
    name_entry.pack()

    gtype = tk.StringVar(value="STATIC")

    tk.Label(win, text="Gesture type").pack(pady=5)
    tk.Radiobutton(win, text="STATIC", variable=gtype, value="STATIC").pack(anchor="w")
    tk.Radiobutton(win, text="DYNAMIC", variable=gtype, value="DYNAMIC").pack(anchor="w")

    if recording:
        messagebox.showwarning("Busy", "Stop recording first.")
        return

    def confirm():
        name = name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Name required")
            return

        gesture = f"{name.upper()}_{gtype.get()}"
        os.makedirs(os.path.join(DATA_ROOT, gesture), exist_ok=True)
        
        global current_gesture
        current_gesture = gesture
        gesture_var.set(gesture)
        status_var.set(f"Gesture set: {gesture}")
        refresh_gesture_list()
        win.destroy()

    tk.Button(win, text="Create", command=confirm).pack(pady=10)

def rename_gesture():
    if recording:
        messagebox.showwarning("Busy", "Stop recording first.")
        return

    gestures = list_gestures()
    if not gestures:
        messagebox.showinfo("Info", "No gestures found")
        return

    win = tk.Toplevel(root)
    win.title("Rename Gesture")
    win.grab_set()

    lb = tk.Listbox(win)
    for g in gestures:
        lb.insert(tk.END, g)
    lb.pack(padx=10, pady=10)

    tk.Label(win, text="New name").pack()
    entry = tk.Entry(win)
    entry.pack()

    def confirm():
        sel = lb.curselection()
        if not sel:
            return
        old = lb.get(sel[0])
        new = entry.get().strip()
        if not new:
            return

        shutil.move(
            os.path.join(DATA_ROOT, old),
            os.path.join(DATA_ROOT, new)
        )
        global current_gesture
        current_gesture = new
        status_var.set(f"Renamed → {new}")
        refresh_gesture_list()
        win.destroy()
    tk.Button(win, text="Rename", command=confirm).pack(pady=10)

def delete_gesture():
    if recording:
        messagebox.showwarning("Busy", "Stop recording first.")
        return

    gestures = list_gestures()
    if not gestures:
        return

    win = tk.Toplevel(root)
    win.title("Delete Gesture")
    win.grab_set()

    lb = tk.Listbox(win)
    for g in gestures:
        lb.insert(tk.END, g)
    lb.pack(padx=10, pady=10)

    def confirm():
        global current_gesture
        sel = lb.curselection()
        if not sel:
            return
        g = lb.get(sel[0])
        shutil.rmtree(os.path.join(DATA_ROOT, g))
        status_var.set(f"Deleted {g}")
        refresh_gesture_list()
        win.destroy()
        if current_gesture == g:
            current_gesture = None
            gesture_var.set("None")
        update_ui_state()
    tk.Button(win, text="Delete", command=confirm).pack(pady=10)

def normalize_sequence(seq, target_len=SEQ_LEN):
    if len(seq) >= target_len:
        return seq[:target_len]
    last = seq[-1]
    while len(seq) < target_len:
        seq.append(last)
    return seq

def save_sample():
    global recording, capture_ready

    if not capture_ready:
        messagebox.showwarning("Save", "Nothing to save.")
        return

    if recording:
        messagebox.showwarning("Save", "Stop recording first.")
        return

    if not current_gesture:
        messagebox.showwarning("Save", "No gesture selected.")
        return

    elif current_gesture.endswith("_STATIC"):
        messagebox.showinfo(
            "Info",
            "Static gestures auto-save.\nNo manual saving needed."
        )
        return
    
    gesture = current_gesture
    path = os.path.join(DATA_ROOT, gesture)
    idx = len(os.listdir(path)) + 1
    fname = f"{gesture}_{idx:03d}.npy"
    out = os.path.join(path, fname)
    with buffer_lock:
        data = buffer.copy()
    np.save(out, np.array(data))
    reset_buffer()
    status_var.set(f"Saved → {out}")
    update_sample_count()
    # 🔓 Ensure UI is unlocked after save
    start_btn.config(text="Start", bg="SystemButtonFace", fg="black")
    update_ui_state()
    progress_var.set(0)

def start_record():
    global recording, buffer, capture_ready

    if not current_gesture:
        return

    if source_mode == "video":      #Disable button if VIDEO
        return

    if recording:                   # Prevent double-start
        return
    progress_var.set(0)             #RESET progress bar to 0

    def begin_recording():
        global recording, record_start_time, mp_last_time
        reset_buffer()
        recording = True
        record_start_time = time.time()
        mp_last_time = 0
        start_btn.config(text="Recording…", bg="#c0392b", fg="white") #Visual State Indicator
        status_var.set("Recording...")
        update_ui_state()

    # Webcam Countdown
    if source_mode == "webcam" and AUTO_COUNTDOWN.get():
        def countdown(n):
            if n <= 0:
                begin_recording()
                return
            status_var.set(f"Starting in {n}...")
            root.after(1000, lambda: countdown(n - 1))
        countdown(COUNTDOWN_SECONDS.get())
    else:
        begin_recording()

def stop_record():
    global recording, record_start_time
    if recording and len(buffer) >= 5:
        with buffer_lock:
            buffer[:] = normalize_sequence(buffer)
            capture_ready = True
    else:
        reset_buffer()
    recording = False
    record_start_time = None
    progress_var.set(0)
    start_btn.config(text="Start", bg="SystemButtonFace", fg="black")
    status_var.set("Recording stopped")
    update_ui_state()

def exit_app():
    global running
    running = False
    root.destroy()

# ---------------- TKINTER UI ----------------
root = tk.Tk()

AUTO_COUNTDOWN = tk.BooleanVar(value=True)
COUNTDOWN_SECONDS = tk.IntVar(value=3)  # default = 3 seconds

gesture_var = tk.StringVar(value="None")
root.title("Sevue Gesture Data Collector")

VIDEO_W, VIDEO_H = 640, 480  # UI size, not camera size
video_frame = tk.Frame(root, width=VIDEO_W, height=VIDEO_H, bg="black")
video_frame.pack()
video_frame.pack_propagate(False)  #Prevent UI resizing
video_label = tk.Label(video_frame, bg="black")
video_label.place(relx=0.5, rely=0.5, anchor="center")

# -------- Scrollable UI Container --------
ui_canvas = tk.Canvas(root, highlightthickness=0)
ui_scroll = tk.Scrollbar(root, orient="vertical", command=ui_canvas.yview)

ui_canvas.configure(yscrollcommand=ui_scroll.set)

ui_scroll.pack(side="right", fill="y")
ui_canvas.pack(side="left", fill="both", expand=True)

controls_frame = tk.Frame(ui_canvas)
ui_canvas.create_window((0, 0), window=controls_frame, anchor="nw")
def _on_canvas_resize(event):
    ui_canvas.itemconfig(1, width=event.width)

ui_canvas.bind("<Configure>", _on_canvas_resize)

def _on_frame_configure(event):
    ui_canvas.configure(scrollregion=ui_canvas.bbox("all"))
controls_frame.bind("<Configure>", _on_frame_configure)

def _on_mousewheel(event):
    ui_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
ui_canvas.bind("<Enter>", lambda e: ui_canvas.bind_all("<MouseWheel>", _on_mousewheel))
ui_canvas.bind("<Leave>", lambda e: ui_canvas.unbind_all("<MouseWheel>"))

tk.Label(controls_frame, text="Current Gesture").pack()
tk.Label(controls_frame, textvariable=gesture_var, fg="blue").pack()
#Sample count badge
sample_count_var = tk.StringVar(value="Samples: 0")

sample_badge = tk.Label(
    controls_frame,
    textvariable=sample_count_var,
    fg="white",
    bg="#34495e",
    padx=10,
    pady=3,
    font=("Segoe UI", 9, "bold")
)
sample_badge.pack(pady=(2, 8))

gesture_list = tk.Listbox(controls_frame, height=5)
gesture_list.pack(padx=10, pady=5)
gesture_list.bind("<<ListboxSelect>>", select_gesture)

refresh_gesture_list()

btn_frame = tk.Frame(controls_frame)
btn_frame.pack(pady=5)

def resize_with_aspect(frame, target_w, target_h):
    h, w = frame.shape[:2]
    scale = min(target_w / w, target_h / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (nw, nh))
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    x = (target_w - nw) // 2
    y = (target_h - nh) // 2
    canvas[y:y+nh, x:x+nw] = resized
    return canvas

def btn(txt, cmd):
    return tk.Button(btn_frame, text=txt, width=12, command=cmd)

add_btn    = btn("Add", add_gesture)
rename_btn = btn("Rename", rename_gesture)
delete_btn = btn("Delete", delete_gesture)

add_btn.grid(row=0, column=0)
rename_btn.grid(row=0, column=1)
delete_btn.grid(row=0, column=2)

start_btn = btn("Start", start_record)
stop_btn  = btn("Stop", stop_record)
save_btn  = btn("Save", save_sample)

start_btn.grid(row=1, column=0)
stop_btn.grid(row=1, column=1)
save_btn.grid(row=1, column=2)

webcam_btn = btn("Webcam", lambda: set_source("webcam"))
video_btn  = btn("Video", lambda: set_source("video"))

webcam_btn.grid(row=2, column=0)
video_btn.grid(row=2, column=1)

tk.Checkbutton(
    controls_frame,
    text="Auto countdown (webcam)",
    variable=AUTO_COUNTDOWN
).pack()

countdown_frame = tk.Frame(controls_frame)
countdown_frame.pack(pady=2)

tk.Label(countdown_frame, text="Countdown (sec):").pack(side="left")

tk.Spinbox(
    countdown_frame,
    from_=1,
    to=10,
    width=5,
    textvariable=COUNTDOWN_SECONDS
).pack(side="left")

exit_btn = tk.Button(controls_frame, text="Exit", width=12, command=exit_app)
exit_btn.pack(pady=10)

status_var = tk.StringVar(value="Ready")
tk.Label(controls_frame, textvariable=status_var).pack(pady=5)

progress_var = tk.DoubleVar(value=0)

progress_bar = ttk.Progressbar(
    controls_frame,
    variable=progress_var,
    maximum=100,
    length=300
)
progress_bar.pack(pady=5)

# ---------------- UI STATE MACHINE ----------------
def update_ui_state():
    has_gesture = current_gesture is not None
    is_recording = recording
    is_webcam = source_mode == "webcam"

    can_save = (
        capture_ready
        and not recording
        and not (current_gesture and current_gesture.endswith("_STATIC"))
    )

    # Start
    start_btn.config(
        state="normal" if (has_gesture and is_webcam and not is_recording) else "disabled"
    )

    # Stop
    stop_btn.config(
        state="normal" if is_recording else "disabled"
    )

    # Save
    save_btn.config(
        state="normal" if can_save else "disabled"
    )

    # Gesture controls
    gesture_state = "disabled" if is_recording else "normal"
    gesture_list.config(state=gesture_state)
    add_btn.config(state=gesture_state)
    rename_btn.config(state=gesture_state)
    delete_btn.config(state=gesture_state)

    # Source buttons
    webcam_btn.config(state="normal")
    video_btn.config(
        state="normal" if (has_gesture and not is_recording)
        else "disabled"
    )

# ---------------- UI UPDATE LOOP ----------------
def update_ui():
    if not running:
        return
    with frame_lock:
        frame = latest_frame.copy() if latest_frame is not None else None
    if frame is not None:
        frame = resize_with_aspect(frame, VIDEO_W, VIDEO_H)
        img = ImageTk.PhotoImage(
            Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        )
        video_label.imgtk = img
        video_label.configure(image=img)
    root.after(50, update_ui)

# ---------------- START THREADS ----------------
status_var.set("Starting camera...")
threading.Thread(target=camera_loop, daemon=True).start()

update_ui_state()   
update_ui()
root.mainloop()