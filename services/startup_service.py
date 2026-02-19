import os
import sys
from pathlib import Path


class StartupService:
    def __init__(self, app_name="Sevue"):
        self.app_name = app_name

    def startup_command(self):
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        script = str(Path(sys.argv[0]).resolve()) if sys.argv else ""
        return f'"{sys.executable}" "{script}"'

    def _set_windows(self, enabled):
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as reg_key:
            if enabled:
                winreg.SetValueEx(
                    reg_key,
                    self.app_name,
                    0,
                    winreg.REG_SZ,
                    self.startup_command(),
                )
                return
            try:
                winreg.DeleteValue(reg_key, self.app_name)
            except FileNotFoundError:
                pass

    def _set_linux(self, enabled):
        autostart_dir = Path.home() / ".config" / "autostart"
        desktop_file = autostart_dir / f"{self.app_name.lower()}.desktop"
        if enabled:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            desktop_file.write_text(
                "\n".join(
                    [
                        "[Desktop Entry]",
                        "Type=Application",
                        "Version=1.0",
                        f"Name={self.app_name}",
                        f"Comment=Start {self.app_name} on login",
                        f"Exec={self.startup_command()}",
                        "X-GNOME-Autostart-enabled=true",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            return

        if desktop_file.exists():
            desktop_file.unlink()

    def sync(self, enabled, installed_build):
        if not installed_build:
            return
        if os.name == "nt":
            self._set_windows(enabled)
        elif sys.platform.startswith("linux"):
            self._set_linux(enabled)
