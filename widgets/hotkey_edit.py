"""Поле ввода системной горячей клавиши.

Захватывает нажатие и собирает строку вида «Ctrl+Shift+N» — тот же формат,
который понимает `services.hotkeys.parse_shortcut`. Собственный виджет, а не
`QKeySequenceEdit`: тот принимает последовательности до четырёх нажатий и
комбинации без модификаторов, ни то ни другое сюда не годится.

Функции `qt_key_name` / `qt_modifiers_names` / `qt_key_to_shortcut` — чистые,
чтобы их можно было проверить тестами, не поднимая окно Qt.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLineEdit

from services import i18n

# Служебные клавиши: их нажатие не должно превращаться в комбинацию.
_IGNORED_KEYS = frozenset({
    Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
    Qt.Key.Key_Return, Qt.Key.Key_Enter,
    Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock,
    Qt.Key.Key_Print, Qt.Key.Key_Pause,
})

# Qt-код клавиши -> подпись из services/hotkeys._VK_SPECIAL
_SPECIAL_KEYS = {
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Down: "Down",
}
for _index in range(1, 13):
    _SPECIAL_KEYS[getattr(Qt.Key, "Key_F%d" % _index)] = "F%d" % _index
del _index

_MODIFIER_BITS = (
    (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
    (Qt.KeyboardModifier.AltModifier, "Alt"),
    (Qt.KeyboardModifier.ShiftModifier, "Shift"),
    (Qt.KeyboardModifier.MetaModifier, "Win"),
)


def qt_modifiers_names(modifiers) -> list:
    """Имена нажатых модификаторов в порядке Ctrl, Alt, Shift, Win."""
    return [
        name for bit, name in _MODIFIER_BITS if modifiers & bit
    ]


def qt_key_name(key: int):
    """Подпись основной клавиши.

    Возвращает None, если клавишу нельзя использовать: служебные, а также
    всё, что не латиница и не цифра. Кириллица отвергается не из вредности:
    её код (Ф -> 1060) не является виртуальным кодом клавиши, и RegisterHotKey
    зарегистрировал бы не то, что нажал пользователь.
    """
    if key in _IGNORED_KEYS:
        return None
    if key in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key]
    if 0x30 <= key <= 0x39 or 0x41 <= key <= 0x5A:
        return chr(key)
    return None


def qt_key_to_shortcut(key: int, modifiers) -> tuple:
    """Собирает комбинацию из Qt-события.

    Returns:
        (комбинация, причина_отказа). Ровно одно из двух непустое.
    """
    mods = qt_modifiers_names(modifiers)
    name = qt_key_name(key)
    if name is None:
        return "", i18n.tr("Эту клавишу назначить нельзя")
    if not mods:
        return "", i18n.tr("Нужен модификатор: Ctrl, Alt, Shift или Win")
    return "+".join(mods + [name]), ""


class HotkeyEdit(QLineEdit):
    """Поле для назначения одной системной комбинации."""

    shortcut_changed = Signal(str)
    # Пустая строка означает «комбинация снята» — действие становится
    # доступным только через меню в трее.
    rejected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shortcut = ""
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._restore_text)
        # readOnly, а не disabled: поле должно принимать фокус и клавиатуру,
        # иначе захватывать будет нечего.
        self.setReadOnly(True)
        self.retranslate()

    def retranslate(self):
        """Переставляет подсказки поля под текущий язык интерфейса."""
        self.setPlaceholderText(i18n.tr("Нажмите сочетание"))
        self.setToolTip(
            i18n.tr(
                "Нажмите нужное сочетание. Backspace — снять комбинацию. "
                "Только латиница и цифры."
            )
        )

    def shortcut(self) -> str:
        return self._shortcut

    def set_shortcut(self, value: str):
        self._shortcut = (value or "").strip()
        self._notice_timer.stop()
        self.setText(self._shortcut)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._apply("")
            return
        if key == Qt.Key.Key_Escape:
            self.clearFocus()
            return

        modifiers = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        shortcut, reason = qt_key_to_shortcut(key, modifiers)
        if reason:
            self.rejected.emit(reason)
            self._notice(reason)
            return
        self._apply(shortcut)

    def _apply(self, shortcut: str):
        changed = shortcut != self._shortcut
        self._shortcut = shortcut
        self._notice_timer.stop()
        self.setText(shortcut)
        if changed:
            self.shortcut_changed.emit(shortcut)

    def _notice(self, message: str):
        """Показывает причину отказа прямо в поле, потом возвращает значение."""
        self.setText(message)
        self.setStyleSheet("color: #b00020;")
        self._notice_timer.start(1600)

    def _restore_text(self):
        self.setStyleSheet("")
        self.setText(self._shortcut)
