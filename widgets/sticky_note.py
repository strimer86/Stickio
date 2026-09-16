import logging
import os
import sys

from PySide6.QtCore import (
    Qt, QEvent, QPoint, QRectF, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPainterPath, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QHBoxLayout, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from database.database import DatabaseClosedError
from models.note import Note
from services.settings import Settings
from widgets.toolbar import Toolbar

APP_ICON = QIcon()

def load_app_icon():
    """Загружает иконку приложения.

    В замороженном exe PyInstaller распаковывает ресурсы в sys._MEIPASS —
    путь относительно __file__ там не работает.
    """
    global APP_ICON
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.getcwd()
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base, "Noteit.ico")
    if os.path.exists(icon_path):
        APP_ICON = QIcon(icon_path)

EDGE = 10
MIN_WIDTH = 180
MIN_HEIGHT = 120

# Минимум заметки, который должен попасть на экран, чтобы за неё можно было
# взяться мышью. Раньше хватало 60x40, из-за чего окно с срезанной шапкой
# считалось «видимым» и оставалось недосягаемым.
MIN_VISIBLE_WIDTH = 60
MIN_VISIBLE_HEIGHT = 100

CONTENT_MARGIN = 12
# Тонкая нижняя полоса: отступ под ручкой ресайза вдвое меньше боковых
BOTTOM_MARGIN = CONTENT_MARGIN // 2
_NORTH = 4
_SOUTH = 8
_WEST = 1
_EAST = 2

CURSORS = {
    0: None,
    _WEST | _EAST: Qt.CursorShape.SizeHorCursor,
    _NORTH | _SOUTH: Qt.CursorShape.SizeVerCursor,
    _NORTH | _WEST: Qt.CursorShape.SizeFDiagCursor,
    _SOUTH | _EAST: Qt.CursorShape.SizeFDiagCursor,
    _NORTH | _EAST: Qt.CursorShape.SizeBDiagCursor,
    _SOUTH | _WEST: Qt.CursorShape.SizeBDiagCursor,
    _WEST: Qt.CursorShape.SizeHorCursor,
    _EAST: Qt.CursorShape.SizeHorCursor,
    _NORTH: Qt.CursorShape.SizeVerCursor,
    _SOUTH: Qt.CursorShape.SizeVerCursor,
}

# Интервал автосохранения по умолчанию. Константа осталась ради тестов и
# совместимости, но живое значение берётся из настроек (Settings.save_delay_ms):
# пауза в 400 мс удобна не всем — кому-то нужна запись почти сразу, кому-то
# важно, чтобы диск не дёргался на каждый абзац.
SAVE_DELAY_MS = 400
MIN_OPACITY = 0.2  # нижняя граница слайдера прозрачности
logger = logging.getLogger(__name__)


def hit_test_dirs(pos, width: int, height: int) -> int:
    """Определяет, за какую сторону/угол окна схватились.

    Вынесено из StickyNote как чистая функция: логику краёв легко
    протестировать без создания окна Qt.
    """
    x, y = pos.x(), pos.y()
    dirs = 0
    if y <= EDGE:
        dirs |= _NORTH
    if y >= height - EDGE:
        dirs |= _SOUTH
    if x <= EDGE:
        dirs |= _WEST
    if x >= width - EDGE:
        dirs |= _EAST
    return dirs


def cursor_for_dirs(dirs: int):
    """Курсор для набора направлений ресайза (None — обычная стрелка)."""
    return CURSORS.get(dirs)


# Стандартное меню QTextEdit приходит на английском: Qt не переводит его сам,
# если не загружены .qm-файлы. Ключ — подпись без ускорителя и хоткея.
CONTEXT_MENU_TITLES = {
    "undo": "Отменить",
    "redo": "Вернуть",
    "cut": "Вырезать",
    "copy": "Копировать",
    "paste": "Вставить",
    "delete": "Удалить",
    "select all": "Выделить всё",
}

CONTEXT_MENU_STYLE = (
    "QMenu { background: #ffffff; color: #000000;"
    " border: 1px solid #9a9a9a; padding: 4px; }"
    "QMenu::item { padding: 6px 24px 6px 14px; border-radius: 4px;"
    " color: #000000; font-weight: 600; }"
    "QMenu::item:selected { background: #ffe98a; color: #000000; }"
    "QMenu::item:disabled { color: #767676; font-weight: 500; }"
    "QMenu::separator { height: 1px; background: #cfcfcf; margin: 4px 8px; }"
)


def translate_context_menu(menu) -> None:
    """Переводит пункты стандартного меню QTextEdit и делает шрифт тёмным.

    Действия не пересоздаются: подменяется только подпись, поэтому
    доступность пунктов и их обработчики остаются родными для Qt.
    """
    for action in menu.actions():
        if action.isSeparator():
            continue
        raw = action.text()
        parts = raw.split("\t")
        # ускоритель ("Cu&t") в подписи больше не нужен
        base = parts[0].replace("&", "").strip().lower()
        translated = CONTEXT_MENU_TITLES.get(base)
        if translated:
            action.setText(
                translated + ("\t" + parts[1] if len(parts) > 1 else "")
            )
        action.setIcon(QIcon())  # иконки Qt на цветных заметках лишние
    menu.setStyleSheet(CONTEXT_MENU_STYLE)


class _HeaderBar(QWidget):
    def __init__(self, note_window: "StickyNote"):
        super().__init__(note_window)
        self._window = note_window
        self.setFixedHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._window.begin_move(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._window.moving():
            self._window.move_to(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        self._window.finish_move()
        event.accept()


class _ResizeHandle(QWidget):
    def __init__(self, note_window: "StickyNote"):
        super().__init__(note_window)
        self._window = note_window
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._window.begin_resize(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._window.resizing():
            self._window.apply_resize(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._window.finish_resize():
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor(0, 0, 0, 90))
        # один ряд из трёх точек — под компактную ручку 14px
        for j in range(3):
            painter.drawPoint(3 + j * 3, 9)


class StickyNote(QWidget):
    delete_requested = Signal(object)
    new_note_requested = Signal()

    def __init__(self, note: Note, database, settings=None, parent=None):
        super().__init__(parent)
        self.note = note
        self.database = database
        # Settings создаём лениво и только если не передали: окно может
        # подниматься и в тестах, где хранилище настроек ни к чему.
        self.settings = settings or Settings()

        self._drag_offset = None
        self._resize = None
        self.animation = None  # Для анимации
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.setWindowOpacity(note.opacity)
        if not APP_ICON.isNull():
            self.setWindowIcon(APP_ICON)
        self._build_ui()
        self._load_note()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(self.settings.save_delay_ms())
        self._save_timer.timeout.connect(self.save_note)

    def set_save_delay(self, milliseconds: int):
        """Меняет паузу автосохранения на лету.

        Настройки применяются без перезапуска, поэтому уже открытые заметки
        должны подхватить новое значение, а не жить со старым до следующего
        запуска приложения.
        """
        self._save_timer.setInterval(int(milliseconds))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            CONTENT_MARGIN, CONTENT_MARGIN - 2, CONTENT_MARGIN, BOTTOM_MARGIN
        )
        layout.setSpacing(0)

        self.header = _HeaderBar(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(6, 2, 6, 2)
        header_layout.setSpacing(4)

        self.toggle_button = QPushButton("\u2022\u2022\u2022")
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setToolTip("Панель оформления")
        self.toggle_button.setStyleSheet(
            "QPushButton { color: #222222; border: none; background: transparent;"
            " font-size: 14px; padding: 0px 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,40); border-radius: 3px; }"
        )
        self.toggle_button.clicked.connect(self.toggle_toolbar)
        header_layout.addWidget(self.toggle_button)

        self.new_button = QPushButton("+")
        self.new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_button.setToolTip("Новая заметка")
        self.new_button.setStyleSheet(
            "QPushButton { color: #222222; border: none; background: transparent;"
            " font-size: 16px; font-weight: bold; padding: 0px 6px; }"
            "QPushButton:hover { background: rgba(0,0,0,40); border-radius: 3px; }"
        )
        self.new_button.clicked.connect(self.new_note_requested)
        header_layout.addWidget(self.new_button)

        header_layout.addStretch(1)

        self.close_button = QPushButton("\u00d7")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip("Скрыть")
        self.close_button.setStyleSheet(
            "QPushButton { color: #222222; border: none; background: transparent;"
            " font-size: 16px; padding: 0px 4px; }"
            "QPushButton:hover { background: rgba(0,0,0,40); border-radius: 3px; }"
        )
        self.close_button.clicked.connect(self.hide_note)
        header_layout.addWidget(self.close_button)

        layout.addWidget(self.header)

        self.toolbar = Toolbar(self)
        self.toolbar.adjustSize()
        self.toolbar.setFixedSize(self.toolbar.sizeHint())
        self.toolbar.setWindowOpacity(1.0)
        self.toolbar.setVisible(False)

        self.editor = QTextEdit(self)
        self.editor.setFrameShape(QTextEdit.Shape.NoFrame)
        # Заливку отключаем: иначе viewport закрасит углы заметки своим
        # палитровым цветом поверх скруглённого фона окна.
        self.editor.viewport().setAutoFillBackground(False)
        self._apply_editor_background(QColor(self.note.background_color))
        self.editor.setFontPointSize(self.note.font_size)
        # Своё контекстное меню вместо стандартного: у Qt оно английское
        # (Cut/Copy/Paste), а приложение русскоязычное.
        self.editor.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.editor.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.editor, 1)

        self._resize_handle = _ResizeHandle(self)
        layout.addWidget(self._resize_handle, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        # QTextEdit и его viewport съедают движения мыши почти на всей площади
        # заметки, поэтому собственные mouseMoveEvent окна там не срабатывают
        # и ресайз за края был недостижим. Перехватываем события фильтром.
        self.editor.setMouseTracking(True)
        self.editor.viewport().setMouseTracking(True)
        self.editor.installEventFilter(self)
        self.editor.viewport().installEventFilter(self)

        self.toolbar.background_color_selected.connect(self.set_background_color)
        self.toolbar.text_color_selected.connect(self.set_text_color)
        self.toolbar.font_size_changed.connect(self.set_font_size)
        self.toolbar.bold_toggled.connect(self.set_bold)
        self.toolbar.opacity_changed.connect(self.set_opacity)
        self.toolbar.delete_requested.connect(self.confirm_delete)

    def _load_note(self):
        # геометрию ставим первой, чтобы последующий save_note (если сигнал проскочит) сохранил правильные координаты
        self.setGeometry(self.note.x, self.note.y, self.note.width, self.note.height)
        self.editor.setHtml(self.note.content or "")
        self.toolbar.set_current_colors(
            QColor(self.note.background_color), QColor(self.note.text_color)
        )
        # слайдер ограничен 20..100 — приводим сохранённое значение к его
        # диапазону, иначе визуал и реальная прозрачность расходятся
        clamped_opacity = min(max(self.note.opacity, MIN_OPACITY), 1.0)
        self.note.opacity = clamped_opacity
        self.toolbar.set_opacity_value(round(clamped_opacity * 100))
        self.toolbar.font_size_spin.blockSignals(True)
        self.toolbar.font_size_spin.setValue(self.note.font_size)
        self.toolbar.font_size_spin.blockSignals(False)

        default_fmt = QTextCharFormat()
        default_fmt.setForeground(QColor(self.note.text_color))
        default_fmt.setFontPointSize(self.note.font_size)
        default_fmt.setFontWeight(700 if self.note.bold else 400)
        self.editor.mergeCurrentCharFormat(default_fmt)

        self.toolbar.set_bold_checked(self.note.bold)

        self.editor.textChanged.connect(self._schedule_save)

    def _schedule_save(self):
        self._save_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_on_screen()
        self._position_toolbar()

    def hideEvent(self, event):
        # Qt.Tool-окно с parent НЕ скрывается автоматически вместе с
        # родителем (проверено на Qt 6) — без этого панель «повисает»
        # в воздухе после скрытия заметки. Попап цвета тулбар закрывает
        # сам в своём hideEvent.
        self.toolbar.hide()
        super().hideEvent(event)

    def _ensure_on_screen(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QRect

        screens = QApplication.screens()
        if not screens:
            return

        # Валидный размер из модели (для проверки видимости используем его,
        # т.к. self.frameGeometry() до первого show() ещё 640x480)
        w = self.note.width if self.note.width and self.note.width >= MIN_WIDTH else 380
        h = self.note.height if self.note.height and self.note.height >= MIN_HEIGHT else 300
        note_rect = QRect(self.note.x, self.note.y, w, h)

        # Если заметка по модели пригодна к использованию — синхронизируем
        # виджет с моделью (до show() он может быть в 0,0).
        #
        # Порог проверки: должна быть видна шапка целиком. Раньше хватало
        # перекрытия 60x40, поэтому заметка, прилипшая к верхней кромке,
        # считалась «на экране» — а кнопки «···» и «×» в её шапке оставались
        # за границей, и зацепить окно мышью было почти нельзя.
        for scr in screens:
            avail = scr.availableGeometry()
            inter = avail.intersected(note_rect)
            if inter.width() < MIN_VISIBLE_WIDTH:
                continue
            # верх заметки не должен быть срезан: иначе недоступна шапка
            if self.note.y < avail.top():
                continue
            if inter.height() >= min(MIN_VISIBLE_HEIGHT, h):
                if self.x() != self.note.x or self.y() != self.note.y or self.width() != w or self.height() != h:
                    self.setGeometry(self.note.x, self.note.y, w, h)
                return

        # Заметка вне экранов или срезана по краю — переносим на ближайший
        # экран, подтягивая внутрь рабочей области.
        target = QApplication.screenAt(note_rect.center()) or QApplication.primaryScreen()
        if target is None:
            target = screens[0]
        avail = target.availableGeometry()
        x = self.note.x
        y = self.note.y
        # прижимаем к рабочей области по каждой стороне
        x = max(avail.left(), min(x, avail.right() - w + 1))
        y = max(avail.top(), min(y, avail.bottom() - h + 1))

        if x != self.note.x or y != self.note.y or w != self.note.width or h != self.note.height:
            self.setGeometry(x, y, w, h)
            self.note.x, self.note.y = x, y
            self.note.width, self.note.height = w, h
            try:
                self.database.save_note(self.note)
            except DatabaseClosedError:
                logger.debug("Reposition not saved, database closed id=%s", self.note.id)
            except Exception:
                logger.exception("Failed to save repositioned note id=%s", self.note.id)
        elif self.x() != x or self.y() != y:
            # модель в порядке, но виджет ещё не там
            self.setGeometry(x, y, w, h)

    def toggle_toolbar(self):
        if self.toolbar.isVisible():
            self.toolbar.hide()
            return

        self._position_toolbar()
        self.toolbar.show()
        self.toolbar.raise_()
        self.toolbar.update()

    def _position_toolbar(self):
        """Ставит панель снаружи заметки, справа или слева от неё.

        Раньше панель раскрывалась под кнопкой «...» прямо на содержимом:
        заметка на 300px скрывалась под панелью на 330px, а палитра поверх
        панели прятала ещё и её саму. Теперь панель стоит вне окна заметки —
        текст остаётся виден, а палитра открывается рядом с панелью.
        """
        from PySide6.QtWidgets import QApplication

        toolbar = self.toolbar
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        available = screen.availableGeometry()

        gap = 8
        right_x = self.x() + self.width() + gap
        left_x = self.x() - toolbar.width() - gap

        if right_x + toolbar.width() <= available.right() + 1:
            x = right_x
        elif left_x >= available.left():
            x = left_x
        else:
            # заметка шире рабочего стола — ставим панель внутрь, по правому краю
            x = min(
                max(available.left(), right_x),
                available.right() - toolbar.width() + 1,
            )

        y = self.y()
        if y + toolbar.height() > available.bottom() + 1:
            y = max(available.top(), available.bottom() - toolbar.height() + 1)
        toolbar.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toolbar") and self.toolbar.isVisible():
            self._position_toolbar()
            self.toolbar.raise_()

    def save_note(self):
        """Переносит состояние окна в модель и пишет её в базу.

        Модель обновляем всегда, даже если запись не пройдёт: иначе при
        закрытой базе (штатный выход из приложения) последние правки
        терялись бы не только на диске, но и в памяти.
        """
        self.note.content = self.editor.toHtml()
        self.note.x, self.note.y = self.x(), self.y()
        self.note.width, self.note.height = self.width(), self.height()
        try:
            self.database.save_note(self.note)
        except DatabaseClosedError:
            # База закрыта — приложение завершается, писать больше некуда
            # и это не ошибка: не засоряем журнал трассировкой.
            logger.debug("Save skipped, database closed (note id=%s)", self.note.id)
        except Exception:
            logger.exception("Failed to save note id=%s", self.note.id)

    def set_background_color(self, color: QColor):
        self.note.background_color = color.name()
        self._apply_editor_background(color)
        self.toolbar.set_background_color(color)
        self._refresh_picker_current()
        self._repaint_note()
        QTimer.singleShot(0, self._repaint_note)
        self.save_note()

    def _refresh_picker_current(self):
        """Подсвечивает в открытой палитре только что выбранный цвет.

        Вызывается из set_*_color: попап на момент выбора ещё жив и должен
        показать новую «галочку», если пользователь откроет его снова.
        """
        popup = getattr(self.toolbar, "_popup", None)
        if popup is None:
            return
        if getattr(popup, "for_text", False):
            popup.set_current(QColor(self.note.text_color))
        else:
            popup.set_current(QColor(self.note.background_color))

    def _repaint_note(self):
        """Немедленно перерисовывает все поверхности заметки одним цветом."""
        self.repaint(self.rect())
        self.header.repaint()
        self.editor.repaint()
        self.editor.viewport().repaint()
        self._restore_content_layers()

    def _apply_editor_background(self, color: QColor):
        """Красит текст редактора, но оставляет его фон прозрачным.

        Фон рисует сама заметка в paintEvent — скруглённым. Непрозрачный фон
        редактора перекрывал бы углы заметки прямыми углами, поэтому здесь
        задаётся только цвет текста.
        """
        self.editor.setStyleSheet(
            "QTextEdit { background-color: transparent; color: %s;"
            " border: none; }"
            "QTextEdit::viewport { background-color: transparent; }"
            % self.note.text_color
        )
        self.editor.viewport().setStyleSheet(
            "background-color: transparent;"
        )

    def _restore_content_layers(self):
        """Восстанавливает элементы поверх отрисованного фона окна."""
        for widget in (self.editor, self._resize_handle, self.header):
            widget.raise_()
            widget.update()
        if self.toolbar.isVisible():
            self._position_toolbar()
            self.toolbar.raise_()
            self.toolbar.update()
        self.editor.viewport().update()

    def _merge_format(self, fmt: QTextCharFormat, whole_note_when_empty=True):
        """Применяет формат к выделению, иначе — к тексту всей заметки.

        Без выделения формат не должен молча теряться: пользователь жмёт «B»
        и ожидает увидеть эффект. Раньше формат ложился только в позицию
        курсора, поэтому смена размера/жирности «ничего не делала» на уже
        набранном тексте.

        Второй параметр нужен там, где менять весь документ нельзя: например,
        переключение жирности должно оставить в покое текст, который
        пользователь до этого выделял и форматировал частично.
        """
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        elif whole_note_when_empty:
            select_all = QTextCursor(self.editor.document())
            select_all.select(QTextCursor.SelectionType.Document)
            select_all.mergeCharFormat(fmt)
        # формат для текста, который будет набран дальше
        self.editor.mergeCurrentCharFormat(fmt)

    def _show_context_menu(self, pos):
        """Русское контекстное меню редактора (см. translate_context_menu)."""
        menu = self.editor.createStandardContextMenu()
        translate_context_menu(menu)
        menu.exec(self.editor.mapToGlobal(pos))

    def set_text_color(self, color: QColor):
        self.note.text_color = color.name()
        self._apply_editor_background(QColor(self.note.background_color))
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        self._merge_format(fmt)
        self.toolbar.set_text_color(color)
        self._refresh_picker_current()
        self.save_note()

    def set_font_size(self, size: int):
        self.note.font_size = size
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self._merge_format(fmt)
        self.save_note()

    def set_bold(self, checked: bool):
        """Жирность.

        С выделением — на выделение. Без выделения документ не трогаем:
        кнопка «B» чаще всего нажимается перед вводом текста, а массовая
        перезапись веса затирала бы частичное форматирование, выставленное
        ранее вручную (одно слово жирным среди обычного текста).
        """
        self.note.bold = checked
        fmt = QTextCharFormat()
        fmt.setFontWeight(700 if checked else 400)
        self._merge_format(fmt, whole_note_when_empty=False)
        self.save_note()

    def set_opacity(self, value: int):
        opacity = value / 100.0
        self.note.opacity = opacity
        self.setWindowOpacity(opacity)
        self.toolbar.set_opacity_value(value)
        self.save_note()

    def confirm_delete(self):
        # Подтверждение отключаемо: заметки часто создаются на один день, и
        # лишний диалог на каждую утомляет. По умолчанию всё же спрашиваем —
        # удаление безвозвратное, а кнопка корзины рядом с «B».
        if not self.settings.confirm_delete():
            self.delete_requested.emit(self)
            return

        answer = QMessageBox.question(
            self,
            "Удалить заметку",
            "Удалить эту заметку безвозвратно?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self)

    def begin_move(self, global_pos):
        self._drag_offset = global_pos - self.pos()
        self._resize = None

    def moving(self) -> bool:
        return self._drag_offset is not None

    def move_to(self, global_pos):
        if self._drag_offset is not None:
            self.move(global_pos - self._drag_offset)
            if self.toolbar.isVisible():
                self._position_toolbar()

    def finish_move(self) -> bool:
        if self._drag_offset is not None:
            self._drag_offset = None
            self.note.x, self.note.y = self.x(), self.y()
            try:
                self.database.save_note(self.note)
            except Exception:
                logger.exception("Failed to save note position id=%s", self.note.id)
            return True
        return False

    def _hit_test(self, pos) -> int:
        return hit_test_dirs(pos, self.width(), self.height())

    def begin_resize(self, global_pos, dirs=None):
        if dirs is None:
            dirs = _SOUTH | _EAST
        self._resize = (
            self.geometry(),
            global_pos,
            dirs,
        )
        self._drag_offset = None

    def resizing(self) -> bool:
        return self._resize is not None

    def apply_resize(self, global_pos):
        if self._resize is None:
            return

        start, origin, dirs = self._resize

        dx = global_pos.x() - origin.x()
        dy = global_pos.y() - origin.y()

        left, top = start.x(), start.y()
        width, height = start.width(), start.height()

        if dirs & _SOUTH:
            height = start.height() + dy
        if dirs & _NORTH:
            top = start.y() + dy
            height = start.height() - dy
        if dirs & _EAST:
            width = start.width() + dx
        if dirs & _WEST:
            left = start.x() + dx
            width = start.width() - dx

        if width < MIN_WIDTH:
            if dirs & _WEST:
                left = start.x() + start.width() - MIN_WIDTH
            width = MIN_WIDTH
        if height < MIN_HEIGHT:
            if dirs & _NORTH:
                top = start.y() + start.height() - MIN_HEIGHT
            height = MIN_HEIGHT

        self.setGeometry(left, top, width, height)

    def finish_resize(self) -> bool:
        if self._resize is None:
            return False
        self._resize = None
        self.note.x, self.note.y = self.x(), self.y()
        self.note.width, self.note.height = self.width(), self.height()
        try:
            self.database.save_note(self.note)
        except Exception:
            logger.exception("Failed to save note size id=%s", self.note.id)
        return True

    def eventFilter(self, obj, event):
        """Ресайз и смена курсора поверх редактора.

        Координаты приходят в системе виджета-источника (editor или его
        viewport), поэтому переводим их в координаты окна заметки.
        """
        etype = event.type()
        if etype in (
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
        ):
            if etype == QEvent.Type.MouseMove:
                if self._resize is not None or self._drag_offset is not None:
                    # Перетаскивание уже начато — отдаём событие окну целиком
                    return False
                local = self._to_window_pos(obj, event.position().toPoint())
                dirs = self._hit_test(local)
                cursor = cursor_for_dirs(dirs)
                self.setCursor(cursor or Qt.CursorShape.IBeamCursor)
                return False

            if etype == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    local = self._to_window_pos(obj, event.position().toPoint())
                    dirs = self._hit_test(local)
                    if dirs:
                        # Край окна: начинаем ресайз и не пускаем событие
                        # дальше, иначе текст встанет на выделение.
                        self.begin_resize(event.globalPosition().toPoint(), dirs)
                        return True
                return False

            # MouseButtonRelease
            if self.finish_resize():
                return True
            return False

        return super().eventFilter(obj, event)

    def _to_window_pos(self, obj, pos: QPoint) -> QPoint:
        """Переводит координаты виджета-источника в координаты окна заметки."""
        if obj is self.editor:
            return self.editor.mapTo(self, pos)
        # viewport смещён относительно editor на величину рамки/отступа
        return self.editor.viewport().mapTo(self, pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            dirs = self._hit_test(event.position().toPoint())
            if dirs:
                self.begin_resize(event.globalPosition().toPoint(), dirs)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize is not None:
            self.apply_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self._drag_offset is not None:
            self.move_to(event.globalPosition().toPoint())
            event.accept()
            return

        cursor = CURSORS.get(self._hit_test(event.position().toPoint()))
        if cursor is not None:
            self.setCursor(cursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.finish_resize():
            event.accept()
            return
        self.finish_move()
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self.save_note()
        super().closeEvent(event)

    def hide_note(self):
        """Сохраняем заметку перед скрытием"""
        self.save_note()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = 10
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        painter.fillPath(path, QColor(self.note.background_color))

        border = QColor(self.note.background_color).darker(120)
        painter.setPen(border)
        painter.drawPath(path)

        # Углы остаются прозрачными за счёт WA_TranslucentBackground — тогда
        # скругление сглаженное. Раньше здесь ставилась setMask по тому же
        # контуру: она даёт жёсткую обрезку без сглаживания (ступеньки) и
        # срезает внешнюю половину рамки. Дочерние виджеты теперь ничего не
        # рисуют в углах — фон редактора и шапки прозрачный, см.
        # _apply_editor_background.
