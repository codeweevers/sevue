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


def open_camera_capture(index):
    if os.name == "nt":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


def _windows_directshow_names():
    try:
        from pygrabber.dshow_graph import FilterGraph

        graph = FilterGraph()
        devices = graph.get_input_devices() or []
        names = {}
        for index, raw_name in enumerate(devices):
            normalized = _normalize_name(raw_name)
            if normalized:
                names[index] = normalized
        return names
    except Exception:
        return {}


def _linux_v4l2_names():
    names = {}
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
            match = re.search(r"/dev/video(\d+)", line)
            if not match:
                continue
            index = int(match.group(1))
            names.setdefault(index, current_name)
    return names


def _candidate_camera_names(system_name):
    if system_name == "windows":
        return _windows_directshow_names()
    if system_name == "linux":
        return _linux_v4l2_names()
    return {}


def _make_uid(system_name, device_name):
    return f"{system_name}:{device_name}".lower()


class CameraManager:
    def __init__(self, max_devices=8):
        self.max_devices = max_devices
        self.system_name = platform.system().lower()
        self._last_cameras = []

    def _detect_capabilities(self, index):
        capabilities = {"openable": False, "resolutions": [], "fps": DEFAULT_FPS}
        cap = None
        try:
            cap = open_camera_capture(index)
        except Exception:
            return capabilities
        try:
            if cap is None or not cap.isOpened():
                return capabilities
            capabilities["openable"] = True

            supported = []
            for width, height in COMMON_RESOLUTIONS:
                try:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                except Exception:
                    # Some drivers/backends throw native exceptions on property
                    # probing; skip the rest of probing for this device.
                    break
                if actual_w == width and actual_h == height:
                    supported.append({"width": width, "height": height})

            try:
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            except Exception:
                fps = 0.0
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
        # Name-only discovery for background refresh. We intentionally avoid
        # opening/probing devices here because probing can contend with active
        # camera usage and cause instability.
        names = _candidate_camera_names(self.system_name)

        cameras = []
        name_counts = {}
        for index in sorted(names.keys()):
            raw_name = names.get(index, f"Camera {index}")
            device_name = _normalize_name(raw_name) or f"Camera {index}"
            if _is_virtual_camera_name(device_name):
                continue

            seen_count = name_counts.get(device_name.lower(), 0) + 1
            name_counts[device_name.lower()] = seen_count
            if seen_count > 1:
                device_name = f"{device_name} #{seen_count}"

            label = f"{device_name}"
            cameras.append(
                {
                    "index": index,
                    "label": label,
                    "uid": _make_uid(self.system_name, device_name),
                    "resolutions": [],
                    "fps": DEFAULT_FPS,
                }
            )

        self._last_cameras = cameras
        return list(cameras)

    def probe_camera(self, camera):
        if not isinstance(camera, dict):
            return None

        try:
            index = int(camera.get("index"))
        except Exception:
            return None

        capabilities = self._detect_capabilities(index)
        if not capabilities["openable"]:
            return None

        probed = dict(camera)
        probed["resolutions"] = list(capabilities["resolutions"])
        probed["fps"] = capabilities["fps"]
        return probed

    def get_camera_by_uid(self, uid):
        normalized_uid = str(uid or "").strip().lower()
        if not normalized_uid:
            return None

        cameras = self._last_cameras or self.list_cameras()
        for camera in cameras:
            if camera.get("uid") == normalized_uid:
                return camera
        cameras = self.list_cameras()
        for camera in cameras:
            if camera.get("uid") == normalized_uid:
                return camera
        return None
