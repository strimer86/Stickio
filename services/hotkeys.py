"""Глобальные горячие клавиши Windows через RegisterHotKey.

QShortcut работает только внутри приложения, поэтому Ctrl+Shift+H не
срабатывал, когда фокус был в другом окне — а именно этот сценарий
и нужен стикерам. Здесь используется системный механизм: Windows
присылает WM_HOTKEY в очередь потока, мы перехватываем его нативным
фильтром событий Qt.

Использование:
    hotkeys = GlobalHotkeys()
    hotkeys.register("new_note", "Ctrl+Shift+N", callback)
    hotkeys.install(app)   # после создания QApplication
    ...
    hotkeys.unregister_all()
"""
import ctypes
import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject

from services import i18n

logger = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# ID горячих клавиш: RegisterHotKey принимает 0x0000..0xBFFF
_HOTKEY_ID_BASE = 0xB000

_MODIFIER_NAMES = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
    "super": MOD_WIN,
}

# Виртуальные коды клавиш, которые нельзя вывести из имени одним символом
_VK_SPECIAL = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "insert": 0x2D, "delete": 0x2E, "home": 0x24,
    "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}


# Обратное отображение vk -> подпись для канонического вида комбинации.
# Порядок подписей здесь же задаёт порядок следования модификаторов.
_MODIFIER_ORDER = (
    (MOD_CONTROL, "Ctrl"),
    (MOD_ALT, "Alt"),
    (MOD_SHIFT, "Shift"),
    (MOD_WIN, "Win"),
)

_VK_DISPLAY = {
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4",
    0x74: "F5", 0x75: "F6", 0x76: "F7", 0x77: "F8",
    0x78: "F9", 0x79: "F10", 0x7A: "F11", 0x7B: "F12",
    0x20: "Space", 0x2D: "Insert", 0x2E: "Delete",
    0x24: "Home", 0x23: "End", 0x21: "PageUp", 0x22: "PageDown",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
}


class HotkeyError(RuntimeError):
    """Горячую клавишу не удалось зарегистрировать."""


def parse_shortcut(shortcut: str) -> tuple[int, int]:
    """Разбирает "Ctrl+Shift+N" в пару (fsModifiers, vk).

    Raises:
        HotkeyError: строка не соответствует ожидаемому формату.
    """
    parts = [p.strip().lower() for p in shortcut.split("+") if p.strip()]
    if len(parts) < 2:
        raise HotkeyError(
            i18n.tr("Горячая клавиша должна содержать модификатор и клавишу: %r")
            % shortcut
        )

    modifiers = 0
    for part in parts[:-1]:
        if part not in _MODIFIER_NAMES:
            raise HotkeyError(
                i18n.tr("Неизвестный модификатор %r в %r") % (part, shortcut)
            )
        modifiers |= _MODIFIER_NAMES[part]

    key = parts[-1]
    if key in _VK_SPECIAL:
        vk = _VK_SPECIAL[key]
    elif len(key) == 1 and key.isascii() and (key.isalpha() or key.isdigit()):
        # Только латиница: isalpha() пропускает и кириллицу, а её ord()
        # даёт Unicode-код (Ф → 1060), который не является виртуальным
        # кодом клавиши и молча зарегистрировал бы не ту комбинацию.
        vk = ord(key.upper())
    else:
        raise HotkeyError(
            i18n.tr("Неизвестная клавиша %r в %r") % (key, shortcut)
        )

    if not modifiers:
        raise HotkeyError(
            i18n.tr("Нужен хотя бы один модификатор: %r") % shortcut
        )
    return modifiers | MOD_NOREPEAT, vk


def key_name(vk: int) -> str:
    """Подпись клавиши по её виртуальному коду."""
    if vk in _VK_DISPLAY:
        return _VK_DISPLAY[vk]
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:  # цифры и латиница
        return chr(vk)
    raise HotkeyError(
            i18n.tr("Нет подписи для виртуального кода 0x%X") % vk
        )


def normalize_shortcut(shortcut: str) -> str:
    """Приводит комбинацию к виду «Ctrl+Shift+N».

    Нужна, чтобы пользовательский ввод из разных источников (поле захвата
    клавиш, ручная правка в QSettings, старые значения) хранился и
    сравнивался одинаково: ``ctrl+shift+n`` и ``Shift+Ctrl+N`` — одна
    комбинация, а строковое сравнение так не считает.

    Raises:
        HotkeyError: комбинация не разобралась.
    """
    modifiers, vk = parse_shortcut(shortcut)
    parts = [
        name for bit, name in _MODIFIER_ORDER if modifiers & bit
    ]
    parts.append(key_name(vk))
    return "+".join(parts)


class _NativeFilter(QAbstractNativeEventFilter):
    """Ловит WM_HOTKEY и передаёт управление владельцу реестра хоткеев."""

    def __init__(self, owner: "GlobalHotkeys"):
        super().__init__()
        self._owner = owner
        # Ссылка на структуру должна жить: Qt отдаёт указатель на MSG,
        # читаем поля сразу и не сохраняем указатель.
        self._msg = ctypes.c_void_p()

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        try:
            msg = ctypes.cast(
                int(message), ctypes.POINTER(_MSG)
            ).contents
        except (TypeError, ValueError):
            return False, 0
        if msg.message == WM_HOTKEY:
            if self._owner.dispatch(int(msg.wParam)):
                # Событие поглощено: дальше по цепочке не идёт
                return True, 0
        return False, 0


class _MSG(ctypes.Structure):
    """Подмножество Win32 MSG — нужны только message и wParam."""

    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_void_p),
        ("lParam", ctypes.c_void_p),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


class GlobalHotkeys(QObject):
    """Реестр системных горячих клавиш приложения."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._registry: dict[int, tuple[str, object]] = {}
        self._by_name: dict[str, int] = {}
        self._filter = None
        self._user32 = None
        self._next_id = _HOTKEY_ID_BASE
        self._installed = False
        self.failed: list[str] = []

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def install(self, app) -> None:
        """Ставит нативный фильтр. Вызывать после создания QApplication."""
        if self._installed or not self.supported:
            return
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = (
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
        )
        self._user32.RegisterHotKey.restype = ctypes.c_bool
        self._user32.UnregisterHotKey.argtypes = (ctypes.c_void_p, ctypes.c_int)
        self._user32.UnregisterHotKey.restype = ctypes.c_bool

        self._filter = _NativeFilter(self)
        app.installNativeEventFilter(self._filter)
        self._installed = True

    def register(self, name: str, shortcut: str, callback) -> bool:
        """Регистрирует комбинацию.

        Возвращает False, если комбинацию уже заняла другая программа,
        но не бросает исключение: приложение обязано запуститься и без
        горячей клавиши.
        """
        if not self.supported or not self._installed:
            logger.warning("Hotkeys unavailable on this platform: %s", name)
            if shortcut not in self.failed:
                self.failed.append(shortcut)
            return False
        if name in self._by_name:
            self.unregister(name)

        try:
            modifiers, vk = parse_shortcut(shortcut)
        except HotkeyError:
            logger.exception("Invalid shortcut for %r: %r", name, shortcut)
            if shortcut not in self.failed:
                self.failed.append(shortcut)
            return False

        hotkey_id = self._next_id
        self._next_id += 1

        if not self._user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            err = ctypes.get_last_error()
            # 1409 = ERROR_HOTKEY_ALREADY_REGISTERED
            logger.warning(
                "RegisterHotKey failed for %s (%s): error %s",
                name, shortcut, err,
            )
            if shortcut not in self.failed:
                self.failed.append(shortcut)
            return False

        self._registry[hotkey_id] = (name, callback)
        self._by_name[name] = hotkey_id
        logger.info("Global hotkey registered: %s -> %s", shortcut, name)
        return True

    def unregister(self, name: str) -> None:
        hotkey_id = self._by_name.pop(name, None)
        if hotkey_id is None:
            return
        self._registry.pop(hotkey_id, None)
        if self._user32 is not None:
            self._user32.UnregisterHotKey(None, hotkey_id)

    def unregister_all(self) -> None:
        for name in list(self._by_name):
            self.unregister(name)

    def dispatch(self, hotkey_id: int) -> bool:
        """Вызывает обработчик комбинации. True — сообщение обработано."""
        entry = self._registry.get(hotkey_id)
        if entry is None:
            return False
        name, callback = entry
        try:
            callback()
        except Exception:
            logger.exception("Hotkey callback failed: %s", name)
        return True
