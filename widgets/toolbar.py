"""Панель инструментов заметки.

Два ряда: верхний — оформление, нижний — прозрачность. Кнопки одной высоты
с текстом, содержимое центрировано. «Удалить» — компактная кнопка с иконкой
корзины, а не крупная надпись (раньше она доминировала и провоцировала промахи).
"""

from PySide6.QtCore import Qt, QPoint, QSize, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QPushButton, QSlider, QSpinBox, QWidget,
)

from widgets.color_picker import ColorPopup

# Высота одной кнопки. Меньше 24 — у B/A/«14» текст уезжает вверх из-за
# центровки относительно обрезанного sizeHint, больше — панель становится
# выше, чем нужно для такого количества элементов.
BTN_H = 24


def trash_icon(color: str = "#ffffff") -> QIcon:
    """Иконка корзины 16×16 — вместо надписи «Удалить»."""
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(2, 3, 12, 2, 1, 1)  # крышка
    p.drawRoundedRect(5, 1, 6, 2, 1, 1)   # ручка
    p.drawRoundedRect(3, 6, 10, 9, 1, 1)  # корпус
    p.end()
    return QIcon(pm)


class Toolbar(QWidget):
    """Панель инструментов для настройки внешнего вида заметки."""

    background_color_selected = Signal(QColor)
    text_color_selected = Signal(QColor)
    font_size_changed = Signal(int)
    bold_toggled = Signal(bool)
    opacity_changed = Signal(int)
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint,
        )
        self._popup = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        self.setStyleSheet(
            "Toolbar { background: #fafafa;"
            " border: 1px solid rgba(0,0,0,110); border-radius: 8px;"
            " color: #1f1f1f; }"
            "QPushButton { color: #1f1f1f; background: #ffffff;"
            " border: 1px solid rgba(0,0,0,95); border-radius: 5px;"
            " padding: 0 6px;"
            " font-size: 12px; }"
            "QPushButton:hover { background: #f0f0f2; border-color: #1a1a1a; }"
            "QPushButton:pressed { background: #e2e2e6; }"
            "QPushButton:checked { background: #ffe07a;"
            " border: 1px solid #a97c00; }"
            "QPushButton#boldButton { font-weight: 700; font-size: 13px;"
            " padding: 0; }"
            "QPushButton#stepButton { font-size: 14px; font-weight: 700;"
            " padding: 0; }"
            "QPushButton#deleteButton { background: #c0392b;"
            " border: 1px solid #8e2a1e; padding: 0; }"
            "QPushButton#deleteButton:hover { background: #d64534;"
            " border-color: #6f2117; }"
            "QPushButton#deleteButton:pressed { background: #a52f23; }"
            "QPushButton#swatchBackdrop { padding: 2px;"
            " border: 1px solid rgba(0,0,0,110); border-radius: 6px;"
            " background: #ffffff; }"
            "QPushButton#swatchBackdrop:hover { border-color: #1a1a1a; }"
            "QSpinBox, QLabel { color: #1f1f1f; font-size: 12px; }"
            "QSpinBox { background: #ffffff;"
            " border: 1px solid rgba(0,0,0,95); border-radius: 5px;"
            " padding: 0 4px;"
            " min-width: 36px; }"
            "QSlider::groove:horizontal { height: 4px; background: #d6d6d9;"
            " border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 12px; margin: -4px 0;"
            " background: #ffffff; border: 1px solid #6f6f6f;"
            " border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: #c99a00;"
            " border-radius: 2px; }"
        )

        # --- верхняя строка: оформление -------------------------------
        # Образец фона — кнопка внутри белой рамки: иначе на жёлтой/голубой
        # заметке образец сливается с фоном (тот же цвет, нет визуального
        # различия). Контейнер имеет подложку, а внутренняя кнопка — цвет.
        self.background_button = QPushButton()
        self.background_button.setProperty("swatch", "true")
        self.background_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.background_button.setToolTip("Цвет фона")
        self.background_button.setFixedSize(28, 16)
        self.background_button.clicked.connect(self._choose_background)
        self.background_backdrop = QPushButton()
        self.background_backdrop.setObjectName("swatchBackdrop")
        self.background_backdrop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.background_backdrop.setFixedSize(40, BTN_H)
        self.background_backdrop.setToolTip("Цвет фона")
        self.background_backdrop.clicked.connect(self._choose_background)
        backdrop_layout = QGridLayout(self.background_backdrop)
        backdrop_layout.setContentsMargins(0, 0, 0, 0)
        backdrop_layout.addWidget(self.background_button, 0, 0,
                                   Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.background_backdrop, 0, 0)

        self.text_color_button = QPushButton("A")
        self.text_color_button.setObjectName("textColorButton")
        self.text_color_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.text_color_button.setToolTip("Цвет текста")
        self.text_color_button.setFixedSize(BTN_H, BTN_H)
        self.text_color_button.clicked.connect(self._choose_text_color)
        grid.addWidget(self.text_color_button, 0, 1)

        self.font_minus = QPushButton("\u2212")
        self.font_minus.setObjectName("stepButton")
        self.font_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.font_minus.setToolTip("Уменьшить текст")
        self.font_minus.setFixedSize(BTN_H, BTN_H)
        grid.addWidget(self.font_minus, 0, 2)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 72)
        self.font_size_spin.setValue(18)
        self.font_size_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.font_size_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.font_size_spin.setToolTip("Размер шрифта")
        self.font_size_spin.setContentsMargins(0, 0, 0, 0)
        # Внутренний lineEdit у QSpinBox центрирует текст относительно своих
        # 20 пикселей, а QPushButton — относительно своих 24. Подгоняем
        # padding-top так, чтобы «14» сидел на той же линии, что «B»/«A».
        self.font_size_spin.setStyleSheet(
            "QSpinBox { background: #ffffff;"
            " border: 1px solid rgba(0,0,0,95); border-radius: 5px;"
            " padding: 2px 4px 0 4px;"
            " min-width: 36px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 0; height: 0; }"
        )
        self.font_size_spin.valueChanged.connect(self.font_size_changed)
        self.font_size_spin.setFixedHeight(BTN_H)
        self.font_size_spin.setFixedWidth(40)
        grid.addWidget(self.font_size_spin, 0, 3)
        # ± подключаем после создания спинбокса
        self.font_minus.clicked.connect(self.font_size_spin.stepDown)

        self.font_plus = QPushButton("+")
        self.font_plus.setObjectName("stepButton")
        self.font_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.font_plus.setToolTip("Увеличить текст")
        self.font_plus.setFixedSize(BTN_H, BTN_H)
        self.font_plus.clicked.connect(self.font_size_spin.stepUp)
        grid.addWidget(self.font_plus, 0, 4)

        self.bold_button = QPushButton("B")
        self.bold_button.setObjectName("boldButton")
        self.bold_button.setCheckable(True)
        self.bold_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bold_button.setFixedSize(BTN_H, BTN_H)
        self.bold_button.setToolTip("Жирный")
        self.bold_button.toggled.connect(self.bold_toggled)
        grid.addWidget(self.bold_button, 0, 5)

        self.delete_button = QPushButton()
        self.delete_button.setObjectName("deleteButton")
        self.delete_button.setIcon(trash_icon("#ffffff"))
        self.delete_button.setIconSize(QSize(12, 12))
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setToolTip("Удалить заметку")
        self.delete_button.setFixedSize(BTN_H + 4, BTN_H)
        self.delete_button.clicked.connect(self.delete_requested)
        grid.addWidget(self.delete_button, 0, 6)

        # --- нижняя строка: прозрачность ------------------------------
        self.opacity_title = QLabel("Прозрачность")
        self.opacity_title.setToolTip("Прозрачность заметки")
        self.opacity_title.setMinimumWidth(82)
        grid.addWidget(self.opacity_title, 1, 0, 1, 2)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setMinimumWidth(60)
        self.opacity_slider.setMaximumWidth(110)
        self.opacity_slider.setFixedHeight(BTN_H)
        self.opacity_slider.setToolTip("Прозрачность")
        self.opacity_slider.valueChanged.connect(self._update_opacity_label)
        self.opacity_slider.valueChanged.connect(self.opacity_changed)
        grid.addWidget(self.opacity_slider, 1, 2, 1, 3)

        self.opacity_label = QLabel("100%")
        self.opacity_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.opacity_label.setMinimumWidth(34)
        grid.addWidget(self.opacity_label, 1, 5, 1, 2)

        for column in range(7):
            grid.setColumnStretch(column, 0)

        self.set_background_color(QColor("#FFF4A8"))
        self.set_text_color(QColor("#222222"))
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    # --- синхронизация состояния --------------------------------------
    def set_background_color(self, color: QColor):
        name = color.name()
        self.background_button.setStyleSheet(
            "background: %s; border: none; border-radius: 3px;" % name
        )
        self.background_button.setToolTip("Цвет фона — %s" % name.upper())
        self.background_backdrop.setToolTip("Цвет фона — %s" % name.upper())

    def set_text_color(self, color: QColor):
        name = color.name()
        self.text_color_button.setStyleSheet(
            "color: %s; font-weight: 700; font-size: 13px; padding: 0;"
            " background: #ffffff; border: 1px solid rgba(0,0,0,95);"
            " border-radius: 5px;" % name
        )
        self.text_color_button.setToolTip("Цвет текста — %s" % name.upper())

    def set_bold_checked(self, checked: bool):
        self.bold_button.blockSignals(True)
        self.bold_button.setChecked(checked)
        self.bold_button.blockSignals(False)

    def _update_opacity_label(self, value: int):
        self.opacity_label.setText("{}%".format(value))

    def set_opacity_value(self, value: int):
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(value)
        self.opacity_slider.blockSignals(False)
        self.opacity_label.setText("{}%".format(value))

    def set_current_colors(self, background: QColor, text: QColor):
        self._current_background = QColor(background)
        self._current_text = QColor(text)
        self.set_background_color(self._current_background)
        self.set_text_color(self._current_text)

    # --- всплывающие палитры -------------------------------------------
    def _choose_background(self):
        self._open_popup(
            self.background_button,
            self.background_color_selected,
            for_text=False,
            current=getattr(self, "_current_background", None),
        )

    def _choose_text_color(self):
        self._open_popup(
            self.text_color_button,
            self.text_color_selected,
            for_text=True,
            current=getattr(self, "_current_text", None),
        )

    def _open_popup(self, anchor: QWidget, signal, for_text: bool, current=None):
        self._close_popup()
        popup = ColorPopup(self, for_text=for_text)
        if current is not None:
            popup.set_current(current)
        popup.color_selected.connect(signal)
        popup.destroyed.connect(self._forget_popup)
        self._popup = popup
        self._place_popup(popup, anchor)

    def _close_popup(self):
        popup = getattr(self, "_popup", None)
        if popup is not None:
            self._popup = None
            popup.close()

    def _forget_popup(self, *_args):
        self._popup = None

    def hideEvent(self, event):
        self._close_popup()
        super().hideEvent(event)

    @staticmethod
    def _place_popup(popup: ColorPopup, anchor: QWidget):
        """Ставит попап сбоку от панели, не перекрывая её."""
        from PySide6.QtWidgets import QApplication

        popup.adjustSize()
        panel = anchor.window()
        screen = QApplication.screenAt(
            panel.mapToGlobal(QPoint(panel.width() // 2, 0))
        ) or QApplication.primaryScreen()
        area = screen.availableGeometry()

        popup.resize(
            popup.width(), min(popup.height(), max(160, area.height() - 16))
        )

        anchor_top = anchor.mapToGlobal(QPoint(0, 0))
        gap = 6
        right_x = panel.mapToGlobal(QPoint(panel.width(), 0)).x() + gap
        left_x = panel.mapToGlobal(QPoint(0, 0)).x() - popup.width() - gap

        if right_x + popup.width() <= area.right() + 1:
            x = right_x
        elif left_x >= area.left():
            x = left_x
        else:
            x = min(
                max(right_x, area.left()),
                area.right() - popup.width() + 1,
            )

        y = anchor_top.y()
        if y + popup.height() > area.bottom() + 1:
            y = max(area.top(), area.bottom() - popup.height() + 1)
        popup.move(QPoint(x, y))
        popup.show()