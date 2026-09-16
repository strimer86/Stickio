"""Настройки Stickio (QSettings) и автозапуск через HKCU Run."""
import logging
import os
import sys

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

ORG_NAME = "Stickio"
APP_NAME = "Stickio"
RUN_KEY = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"

# Действия, на которые можно назначить системную комбинацию. Порядок в этом
# словаре задаёт порядок строк в диалоге настроек.
HOTKEY_LABELS = {
    "new_note": "Новая заметка",
    "toggle_visibility": "Показать/скрыть все",
}

DEFAULT_HOTKEYS = {
    "new_note": "Ctrl+Shift+N",
    "toggle_visibility": "Ctrl+Shift+H",
}


def app_command() -> str:
    if getattr(sys, "frozen", False):
        return '"{}"'.format(sys.executable)
    script = os.path.abspath(sys.argv[0])
    return '"{}" "{}"'.format(sys.executable, script)


class Settings:
    def __init__(self):
        self.settings = QSettings(ORG_NAME, APP_NAME)

    def hotkeys(self) -> dict:
        """Текущие комбинации: сохранённые, иначе默认值.

        Различаются три состояния, и путать их нельзя:
          * записи нет — действие добавлено в новой версии, берём дефолт;
          * запись есть и пустая — пользователь снял комбинацию намеренно,
            действие отключается (иначе «отключить» было бы невозможно);
          * запись есть и непустая — обычное переназначение.

        Неизвестные действия игнорируются: мусор от удалённых действий не
        должен попадать в настройки.
        """
        self.settings.beginGroup("hotkeys")
        try:
            result = {}
            for name, default in DEFAULT_HOTKEYS.items():
                if self.settings.contains(name):
                    value = self.settings.value(name, "", type=str)
                else:
                    value = default
                value = (value or "").strip()
                if value:
                    result[name] = value
            return result
        finally:
            self.settings.endGroup()

    def set_hotkeys(self, mapping: dict):
        """Сохраняет комбинации. Пустое значение = комбинация снята.

        Пишется пустая строка, а не `remove`: по наличию записи `hotkeys()`
        отличает «пользователь снял комбинацию» от «действие новое, взять
        дефолт» (подробнее там же). Неизвестные имена игнорируются.
        """
        self.settings.beginGroup("hotkeys")
        try:
            for name, value in mapping.items():
                if name not in DEFAULT_HOTKEYS:
                    continue
                self.settings.setValue(name, (value or "").strip())
        finally:
            self.settings.endGroup()

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
