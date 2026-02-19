import os

import cv2

try:
    from PySide6.QtMultimedia import QMediaDevices
except Exception:
    QMediaDevices = None


def _open_capture(index):
    if os.name == "nt":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


def list_available_cameras(max_devices=8):
    cameras = []
    openable_indices = []
    for index in range(max_devices):
        cap = _open_capture(index)
        try:
            if cap is not None and cap.isOpened():
                openable_indices.append(index)
        finally:
            if cap is not None:
                cap.release()

    friendly_names = []
    if QMediaDevices is not None:
        try:
            for device in QMediaDevices.videoInputs():
                name = str(device.description() or "").strip()
                if name:
                    friendly_names.append(name)
        except Exception:
            friendly_names = []

    for position, index in enumerate(openable_indices):
        if position < len(friendly_names):
            label = friendly_names[position]
        else:
            label = f"Camera {index}"
        cameras.append({"index": index, "label": label})

    return cameras
