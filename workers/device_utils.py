import glob
import platform
import subprocess


def get_virtual_cam_device(preferred_name="SevueCam"):
    system = platform.system().lower()

    if system == "windows":
        return preferred_name

    if system == "linux":
        for dev in sorted(glob.glob("/dev/video*")):
            try:
                out = subprocess.check_output(
                    ["v4l2-ctl", "--device", dev, "--all"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                if preferred_name in out:
                    return dev
            except Exception:
                pass
        return None

    return None
