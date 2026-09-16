"""Палитра выбора цвета для заметки.

Два режима: фон (мягкие пастельные тона, на них должен читаться текст) и
текст (насыщенные тёмные цвета, которые видно на любом фоне заметки).
Один список на оба случая не годился: светло-жёлтый текст нечитаем.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QFrame, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

# Фон заметки: пастель. Заметки должны быть спокойными и не «съедать» текст.
BACKGROUND_SWATCHES = [
    "#FFF4A8", "#FDE66C", "#FFD55E", "#FFC49B",
    "#FF9F9F", "#FFB3D9", "#E4B3FF", "#C9B3FF",
    "#A8E6CF", "#A8D8FF", "#FFFFFF", "#E8E8E8",
]

# Цвет текста: контрастный. Светлых оттенков здесь нет намеренно.
TEXT_SWATCHES = [
    "#000000", "#222222", "#3B3B3B", "#5A2E00",
    "#8A1C1C", "#B03000", "#8A6A00", "#1F5F2E",
    "#0F5132", "#123E7A", "#2A1E6B", "#6B1E5A",
]

SWATCH_SIZE = 26

PICKER_STYLE = (
    "QWidget#picker { background: #fbfbfc; }"
    "QLabel#pickerTitle { color: #333333; font-size: 11px;"
    " font-weight: 600; padding: 0 0 2px 0; }"
    "QPushButton#swatch { border: 1px solid rgba(0,0,0,90);"
    " border-radius: 6px; padding: 0; }"
    "QPushButton#swatch:hover { border: 2px solid #1a1a1a; }"
    "QPushButton#swatch[current=\"true\"] { border: 2px solid #1a1a1a; }"
    "QPushButton#customButton { color: #222222; background: #ffffff;"
    " border: 1px solid rgba(0,0,0,110); border-radius: 6px;"
    " min-height: 28px; font-weight: 600; }"
    "QPushButton#customButton:hover { background: #f0f0f2;"
    " border-color: #1a1a1a; }"
    "QPushButton#customButton:pressed { background: #e4e4e8; }"
)


class ColorPicker(QWidget):
    """Сетка образцов цвета + кнопка произвольного цвета."""

    color_selected = Signal(QColor)

    def __init__(self, parent=None, title="Цвет", swatches=None):
        super().__init__(parent)
        self.setObjectName("picker")
        self.setStyleSheet(PICKER_STYLE)
        self._swatches = list(swatches if swatches is not None else BACKGROUND_SWATCHES)
        self._buttons = {}
        self._current = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("pickerTitle")
        layout.addWidget(self.title_label)

        grid = QGridLayout()
        grid.setSpacing(5)
        for index, hex_color in enumerate(self._swatches):
            swatch = make_swatch(hex_color)
            swatch.clicked.connect(lambda _=False, c=hex_color: self._select(c))
            grid.addWidget(swatch, index // 4, index % 4)
            self._buttons[hex_color.lower()] = swatch
        layout.addLayout(grid)

        self.custom_button = QPushButton("Свой цвет…")
        self.custom_button.setObjectName("customButton")
        self.custom_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_button.setToolTip("Выбрать произвольный цвет")
        self.custom_button.clicked.connect(self._choose_custom)
        layout.addWidget(self.custom_button)

    def set_current(self, color):
        """Подсвечивает образец, совпадающий с текущим цветом заметки.

        Без этого нельзя понять, какой цвет стоит сейчас: попап открывался
        каждый раз «с нуля».
        """
        self._current = color
        target = color.name().lower() if isinstance(color, QColor) else str(color).lower()
        for hex_color, button in self._buttons.items():
            button.setProperty("current", "true" if hex_color == target else "false")
            # setProperty сам по себе не перечитывает QSS — нужен repolish
            button.style().unpolish(button)
            button.style().polish(button)

    def _select(self, hex_color: str):
        self.set_current(QColor(hex_color))
        self.color_selected.emit(QColor(hex_color))

    def _choose_custom(self):
        start = self._current if isinstance(self._current, QColor) else QColor("#FFFFFF")
        color = QColorDialog.getColor(start, self, "Выбор цвета")
        if color.isValid():
            self.set_current(color)
            self.color_selected.emit(color)


def make_swatch(hex_color: str) -> QPushButton:
    """Квадратный образец цвета.

    Отдельная фабрика — чтобы не плодить одинаковый код для двух палитр.
    """
    button = QPushButton()
    button.setObjectName("swatch")
    button.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(hex_color.upper())
    button.setStyleSheet("background: {};".format(hex_color))
    return button


class ColorPopup(QDialog):
    """Всплывающее окно с палитрой.

    Своя рамка (QFrame#popupFrame): у FramelessWindowHint без неё окно
    сливалось с фоном заметки и палитра выглядела «приклеенной» без границ.
    """

    color_selected = Signal(QColor)

    def __init__(self, parent=None, for_text=False):
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.for_text = for_text
        self.setStyleSheet(
            "QDialog { background: transparent; }"
            "QFrame#popupFrame { background: #fbfbfc;"
            " border: 1px solid rgba(0,0,0,120); border-radius: 10px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("popupFrame")
        outer.addWidget(frame)

        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        if for_text:
            title, swatches = "Цвет текста", TEXT_SWATCHES
        else:
            title, swatches = "Цвет фона", BACKGROUND_SWATCHES
        self.picker = ColorPicker(frame, title=title, swatches=swatches)
        self.picker.color_selected.connect(self._on_color)
        frame_layout.addWidget(self.picker)

    def set_current(self, color):
        self.picker.set_current(color)

    def _on_color(self, color: QColor):
        self.color_selected.emit(color)
        self.close()
