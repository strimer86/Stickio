"""Настройки Stickio (QSettings) и автозапуск через HKCU Run."""
import logging
import os
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor

from models.note import (
    DEFAULT_BACKGROUND, DEFAULT_FONT_SIZE, DEFAULT_HEIGHT, DEFAULT_TEXT_COLOR,
    DEFAULT_WIDTH,
)
from services import i18n

logger = logging.getLogger(__name__)

ORG_NAME = "Stickio"
APP_NAME = "Stickio"
RUN_KEY = "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"

# Действия, на которые можно назначить системную комбинацию. Порядок в этом
# словаре задаёт порядок строк в диалоге настроек.
HOTKEY_LABELS = {
    "new_note": "Новая заметка",
    "toggle_visibility": "Показать/скрыть все",
    "search": "Поиск по заметкам",
}

DEFAULT_HOTKEYS = {
    "new_note": "Ctrl+Shift+N",
    "toggle_visibility": "Ctrl+Shift+H",
    "search": "Ctrl+Shift+F",
}

# Чем настраивается новая заметка. Значения по умолчанию — из модели, чтобы
# не держать вторую копию констант: расхождение сразу дало бы разные цвета
# «по умолчанию» и при первом запуске.
DEFAULT_NOTE_SETTINGS = {
    "background_color": DEFAULT_BACKGROUND,
    "text_color": DEFAULT_TEXT_COLOR,
    "font_size": DEFAULT_FONT_SIZE,
    "width": DEFAULT_WIDTH,
    "height": DEFAULT_HEIGHT,
}

FONT_SIZE_RANGE = (8, 72)

# Размер новой заметки в пикселях. Нижняя граница совпадает с минимальным
# размером окна заметки: меньше него задавать бессмысленно — окно всё равно
# откроется в минимуме, и настройка выглядела бы «неприменившейся».
# Верхняя — чтобы заметку можно было утащить мышью на любом мониторе.
NOTE_SIZE_RANGE = (160, 2000)

# Интервал автосохранения, миллисекунды. Значение — пауза после последнего
# нажатия клавиши, а не период: таймер в заметке одиночный (singleShot),
# поэтому при непрерывном наборе запись вообще не идёт, пока не остановишься.
# Меньше 200 мс — запись на каждый символ, база «пищит» на диск; больше
# 5000 мс — при аварийном завершении теряется заметный кусок текста.
SAVE_DELAY_RANGE = (200, 5000)
DEFAULT_SAVE_DELAY_MS = 400


def app_command() -> str:
    if getattr(sys, "frozen", False):
        return '"{}"'.format(sys.executable)
    script = os.path.abspath(sys.argv[0])
    return '"{}" "{}"'.format(sys.executable, script)


class Settings:
    def __init__(self, storage=None):
        # storage — только для тестов: готовое хранилище вместо реестра,
        # обычно ini-файл во временном каталоге.
        #
        # Без него увести настройки в сторону нечем: имена организации
        # и приложения здесь зашиты, поэтому QCoreApplication
        # .setOrganizationName на них не влияет. Тесты, которые «заводили
        # свой файл настроек» этим способом, на самом деле читали и чистили
        # настоящую ветку HKCU\Software\Stickio\Stickio — то есть стирали
        # настройки пользователя: комбинации клавиш, вид заметки, автозапуск.
        self.settings = storage if storage is not None else QSettings(ORG_NAME, APP_NAME)

    def language(self) -> str:
        """Язык интерфейса.

        Записи нет — подстраиваемся под язык системы, но только один раз:
        дальше выбор уже сохранён, и подстраиваться снова нельзя — человек
        мог специально поставить другой язык. Битое значение (руками
        правленный реестр) обрабатывается так же, как отсутствующее.
        """
        saved = self.settings.value("language", "", type=str)
        if saved in i18n.LANGUAGE_CODES:
            return saved
        return i18n.system_language()

    def set_language(self, code: str):
        """Сохраняет выбор языка.

        Неизвестный код — ошибка, а не «молча ничего»: единственный
        вызывающий берёт значение из списка в настройках, и тихий отказ
        выглядел бы как «галка не работает».
        """
        if code not in i18n.LANGUAGE_CODES:
            raise ValueError("Unknown language: %r" % code)
        self.settings.setValue("language", code)

    def hotkeys(self) -> dict:
        """Текущие комбинации: сохранённые, иначе значения по умолчанию.

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

    def note_defaults(self) -> dict:
        """Параметры НОВОЙ заметки.

        Влияют только на создаваемые заметки — уже существующие не трогаем:
        пользователь мог специально перекрасить именно эту.
        """
        self.settings.beginGroup("note")
        try:
            result = {}
            for name, default in DEFAULT_NOTE_SETTINGS.items():
                value = self.settings.value(name, default, type=type(default))
                # Битое значение (вручную правленный реестр) не должно ломать
                # создание заметки — берём умолчание.
                if not self._is_valid_note_value(name, value):
                    value = default
                result[name] = value
            return result
        finally:
            self.settings.endGroup()

    @staticmethod
    def _is_valid_note_value(name: str, value) -> bool:
        if name == "font_size":
            low, high = FONT_SIZE_RANGE
            return isinstance(value, int) and low <= value <= high
        if name in ("width", "height"):
            low, high = NOTE_SIZE_RANGE
            # bool — подкласс int, и `True` прошёл бы проверку «1 в диапазоне»
            # ровно так же, как осмысленное число. Отсекаем явно.
            if isinstance(value, bool):
                return False
            return isinstance(value, int) and low <= value <= high
        # Цвет хранится строкой #RRGGBB; всё остальное — мусор
        return isinstance(value, str) and QColor(value).isValid()

    def set_note_defaults(self, mapping: dict):
        self.settings.beginGroup("note")
        try:
            for name, value in mapping.items():
                if name in DEFAULT_NOTE_SETTINGS:
                    self.settings.setValue(name, value)
        finally:
            self.settings.endGroup()

    def confirm_delete(self) -> bool:
        """Спрашивать ли подтверждение перед удалением заметки."""
        return self.settings.value("confirm_delete", True, type=bool)

    def set_confirm_delete(self, enabled: bool):
        self.settings.setValue("confirm_delete", bool(enabled))

    def save_delay_ms(self) -> int:
        """Пауза после последнего нажатия перед записью заметки в базу.

        Битое или выходящее за диапазон значение (в т.ч. следы ручной правки
        реестра) приводим к умолчанию: слишком маленькое залило бы диск
        записью на каждый символ, слишком большое — потеряло бы текст при
        аварийном завершении.
        """
        low, high = SAVE_DELAY_RANGE
        value = self.settings.value("save_delay_ms", DEFAULT_SAVE_DELAY_MS)
        try:
            value = int(value)
        except (TypeError, ValueError):
            return DEFAULT_SAVE_DELAY_MS
        if not low <= value <= high:
            return DEFAULT_SAVE_DELAY_MS
        return value

    def set_save_delay_ms(self, value: int):
        self.settings.setValue("save_delay_ms", int(value))

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
