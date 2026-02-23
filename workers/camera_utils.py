import os
import platform
import re
import subprocess
from constants import COMMON_RESOLUTIONS, VIRTUAL_CAMERA_MARKERS, DEFAULT_FPS
import cv2


def _normalize_name(name):
    return re.sub(r"\s+", " ", str(name or "")).strip()


def _is_virtual_camera_name(name):
    normalized = _normalize_name(name).lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in VIRTUAL_CAMERA_MARKERS)


def _open_capture(index):
    if os.name == "nt":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


def _probe_openable_indices(max_devices):
    openable = []
    for index in range(max_devices):
        cap = _open_capture(index)
        try:
            if cap is not None and cap.isOpened():
                openable.append(index)
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
    return openable


def _windows_directshow_names():
    try:
        from pygrabber.dshow_graph import FilterGraph  # type: ignore

        graph = FilterGraph()
        devices = graph.get_input_devices() or []
        return [_normalize_name(name) for name in devices if _normalize_name(name)]
    except Exception:
        return []


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
            current_name = _normalize_name(line.rstrip(":"))
            continue
        if current_name and "/dev/video" in line:
            names.append(current_name)
    return names


def _candidate_camera_names(system_name, openable_indices):
    if system_name == "windows":
        return _windows_directshow_names()
    if system_name == "linux":
        return _linux_v4l2_names()
    if system_name == "darwin":
        return [f"Camera {index}" for index in openable_indices]
    return [f"Camera {index}" for index in openable_indices]


def _make_uid(system_name, device_name):
    return f"{system_name}:{device_name}".lower()


class CameraManager:
    def __init__(self, max_devices=8):
        self.max_devices = max_devices
        self.system_name = platform.system().lower()
        self._last_cameras = []

    def detect_capabilities(self, index):
        capabilities = {"resolutions": [], "fps": 0.0}
        cap = _open_capture(index)
        try:
            if cap is None or not cap.isOpened():
                return capabilities

            supported = []
            for width, height in COMMON_RESOLUTIONS:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if actual_w == width and actual_h == height:
                    supported.append({"width": width, "height": height})

            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            capabilities["resolutions"] = supported
            capabilities["fps"] = round(fps, 2) if fps > 0 else DEFAULT_FPS
            return capabilities
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def list_cameras(self):
        openable_indices = _probe_openable_indices(self.max_devices)
        names = _candidate_camera_names(self.system_name, openable_indices)

        cameras = []
        name_counts = {}
        for position, index in enumerate(openable_indices):
            raw_name = names[position] if position < len(names) else f"Camera {index}"
            device_name = _normalize_name(raw_name) or f"Camera {index}"
            if _is_virtual_camera_name(device_name):
                continue

            seen_count = name_counts.get(device_name.lower(), 0) + 1
            name_counts[device_name.lower()] = seen_count
            if seen_count > 1:
                device_name = f"{device_name} #{seen_count}"

            capabilities = self.detect_capabilities(index)
            label = f"{device_name}"
            cameras.append(
                {
                    "index": index,
                    "label": label,
                    "uid": _make_uid(self.system_name, device_name),
                    "resolutions": capabilities["resolutions"],
                    "fps": capabilities["fps"],
                }
            )

        self._last_cameras = cameras
        return list(cameras)

    def get_camera_by_uid(self, uid):
        normalized_uid = str(uid or "").strip().lower()
        if not normalized_uid:
            return None

        cameras = self.list_cameras()
        for camera in cameras:
            if camera.get("uid") == normalized_uid:
                return camera
        return None
