"""Сведения о программе: автор, сайт, версия.

Версию берём из ресурса самого exe, а не из константы: тогда окно
«О программе» физически не может показать версию, отличную от той, что
записана в файл. У запуска из исходников ресурса нет, поэтому есть запасное
значение — тест сверяет его с version_info.txt.
"""
import ctypes
import datetime
import logging
import sys
from ctypes import c_void_p, wintypes

logger = logging.getLogger(__name__)

APP_NAME = "Stickio"
APP_TAGLINE = "Заметки на рабочем столе"
APP_AUTHOR = "Т.Е.А."
APP_SITE = "https://stickio.tumioai.ru"
# Без схемы: это подпись для человека, а не адрес для перехода.
APP_SITE_LABEL = "stickio.tumioai.ru"

# Версия для запуска из исходников. Совпадает с filevers в version_info.txt
# (проверяется тестом) и с APP_VERSION в build.bat.
VERSION_FALLBACK = "1.2.0"


def copyright_line() -> str:
    """Строка правообладателя для окна «О программе».

    Год берётся текущий, а не константа: в собранном exe ресурс версии
    застывает навсегда, и однажды он бы показывал прошлогоднюю дату.
    """
    return "© %d %s" % (datetime.date.today().year, APP_AUTHOR)


def _version_from_exe(path: str) -> str:
    """Версия из ресурса файла. Пустая строка, если ресурса нет."""
    try:
        ver = ctypes.WinDLL("version", use_last_error=True)
        ver.GetFileVersionInfoSizeW.argtypes = [
            wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, c_void_p
        ]
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = [
            c_void_p, wintypes.LPCWSTR, ctypes.POINTER(c_void_p),
            ctypes.POINTER(wintypes.UINT),
        ]
        ver.VerQueryValueW.restype = wintypes.BOOL

        ignored = wintypes.DWORD()
        size = ver.GetFileVersionInfoSizeW(path, ctypes.byref(ignored))
        if not size:
            return ""

        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return ""

        pointer = c_void_p()
        length = wintypes.UINT()
        # Длину VerQueryValue отдаёт в СИМВОЛАХ, поэтому строку читаем
        # через wstring_at (значение всё равно заканчивается нулём).
        if not ver.VerQueryValueW(
            buf, "\\", ctypes.byref(pointer), ctypes.byref(length)
        ):
            return ""

        # VS_FIXEDFILEINFO: подпись (4), структура версии (4), затем
        # две пары «старшее.младшее слово» — filevers и prodvers.
        raw = ctypes.string_at(pointer, length.value)
        if len(raw) < 16:
            return ""
        high, low = (
            int.from_bytes(raw[8:12], "little"),
            int.from_bytes(raw[12:16], "little"),
        )
        return "%d.%d.%d.%d" % (
            high >> 16, high & 0xFFFF, low >> 16, low & 0xFFFF
        )
    except (OSError, ValueError):
        # Отсутствие ресурса — не повод падать: покажем запасную версию.
        logger.exception("Не удалось прочитать версию из %s", path)
        return ""


def display_version(raw: str) -> str:
    """Версия для показа человеку.

    В ресурсе версия хранится четырьмя числами (1.0.1.0), а лишний нулевой
    хвост в окне «О программе» только мешает. Четвёртое число не ноль —
    значит оно осмысленное (сборка), и его оставляем.
    """
    return raw[:-2] if raw.endswith(".0") else raw


def app_version() -> str:
    """Версия приложения для показа человеку."""
    if getattr(sys, "frozen", False):
        version = _version_from_exe(sys.executable)
        if version:
            return display_version(version)
    return VERSION_FALLBACK
