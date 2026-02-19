import os
import platform
import re
import subprocess

import cv2

def _is_virtual_camera_name(name):
    normalized = str(name or "").strip().lower()
    if not normalized:
        return False
    virtual_markers = (
        "virtual",
        "obs",
        "v4l2loopback",
        "manycam",
        "xsplit",
        "snap camera",
        "epoccam",
        "droidcam",
        "ndicam",
        "camo",
        "streamlabs",
        "sevue-virtualcam",
        "sevue virtualcam",
    )
    return any(marker in normalized for marker in virtual_markers)


def _open_capture(index):
    if os.name == "nt":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


def _linux_v4l2_names():
    names = []
    try:
        output = subprocess.check_output(
            ["v4l2-ctl", "--list-devices"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return names

    current_name = None
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line:
            current_name = None
            continue
        if line and not line.startswith("\t"):
            current_name = line.strip().rstrip(":")
            continue
        if current_name and "/dev/video" in line:
            names.append(current_name)
    return names


def _windows_pnp_names():
    names = []
    cmd = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.PNPClass -in @('Camera','Image') -and $_.Name } | "
        "Select-Object -ExpandProperty Name"
    )
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return names

    for line in output.splitlines():
        name = line.strip()
        if name:
            names.append(name)
    return names


def _candidate_camera_names():
    system = platform.system().lower()
    if system == "linux":
        return _linux_v4l2_names()
    if system == "windows":
        return _windows_pnp_names()
    return []


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

    friendly_names = _candidate_camera_names()

    for position, index in enumerate(openable_indices):
        friendly_name = ""
        if position < len(friendly_names):
            friendly_name = re.sub(r"\s+", " ", friendly_names[position]).strip()

        if _is_virtual_camera_name(friendly_name):
            continue

        if friendly_name:
            label = f"Camera {index} ({friendly_name})"
        else:
            label = f"Camera {index}"
        cameras.append({"index": index, "label": label})

    return cameras
