"""Настройки Stickio (QSettings) и автозапуск через HKCU Run."""
import logging
import os
import sys

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

ORG_NAME = "Stickio"
APP_NAME = "Stickio"
RUN_KEY = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"


def app_command() -> str:
    if getattr(sys, "frozen", False):
        return '"{}"'.format(sys.executable)
    script = os.path.abspath(sys.argv[0])
    return '"{}" "{}"'.format(sys.executable, script)


class Settings:
    def __init__(self):
        self.settings = QSettings(ORG_NAME, APP_NAME)

    def autostart_enabled(self) -> bool:
        return self.settings.value("autostart", False, type=bool)

    def set_autostart(self, enabled: bool):
        self.settings.setValue("autostart", enabled)
        try:
            run = QSettings(RUN_KEY, QSettings.Format.NativeFormat)
            if enabled:
                run.setValue(APP_NAME, app_command())
            else:
                run.remove(APP_NAME)
            logger.info("Autostart %s", "enabled" if enabled else "disabled")
        except Exception:
            # Реестр может быть недоступен (политика, права) — не роняем UI,
            # но состояние галки не сохраняем, чтобы не расходилось с фактом.
            logger.exception("Failed to update autostart registry key")
            self.settings.remove("autostart")
            raise
