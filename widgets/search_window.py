"""Окно поиска по заметкам.

Отдельное окно, а не панель внутри заметки: искать нужно по ВСЕМ заметкам, а
панель в одной заметке намекала бы на поиск только по ней. Окно немодальное —
полезно держать его открытым рядом и кликать по результатам, оставаясь в
исходной заметке.
"""
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from services import i18n, search

logger = logging.getLogger(__name__)

# Подсветка найденного: жёлтый на тёмном тексте. Свой цвет, а не системный
# «выделение»: выделение синее с белым текстом, и на цветных стикерах
# найденное сливалось бы с остальным текстом.
HIGHLIGHT_COLOR = "#ffe36e"

# Стиль списка результатов. Системное выделение — синий фон с белым текстом,
# но подписи строк у нас тёмные, и выбранная строка становится нечитаемой.
# Свой светлый фон с тёмным текстом решает это без угадывания палитры.
LIST_STYLE = (
    "QListWidget { background: #ffffff; border: 1px solid #bfbfbf;"
    " border-radius: 4px; }"
    "QListWidget::item { padding: 4px 6px; color: #1f1f1f; }"
    "QListWidget::item:selected { background: #ffe9a8; color: #000000; }"
    "QListWidget::item:selected:active { background: #ffe9a8; color: #000000; }"
)


def highlight_cursor_format(color: str = HIGHLIGHT_COLOR) -> QTextCharFormat:
    """Формат подсветки совпадения в редакторе заметки."""
    fmt = QTextCharFormat()
    fmt.setBackground(QBrush(QColor(color)))
    return fmt


class SearchWindow(QWidget):
    """Окно поиска: запрос, список найденного, переход к заметке."""

    note_activated = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("Поиск по заметкам"))
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(420, 340)
        # Ширину фиксируем: QListWidget подстраивает размер под самую длинную
        # строку, и окно разъезжалось с 420 до 700+ пикселей на заметках с
        # длинными выдержками. Выдержки дополнительно ограничены по длине
        # в services/search.py, но полагаться только на это нельзя —
        # пользователь может сузить окно сам, а список снова его распрёт.
        self.setMinimumWidth(360)

        self._results = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        query_row = QHBoxLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText(i18n.tr("Что искать…"))
        self.query_edit.setClearButtonEnabled(True)
        self.query_edit.textChanged.connect(self.refresh)
        self.query_edit.returnPressed.connect(self._activate_current)
        query_row.addWidget(self.query_edit)

        self.regex_check = QCheckBox()
        self.regex_check.toggled.connect(self.refresh)
        query_row.addWidget(self.regex_check)
        layout.addLayout(query_row)

        self.summary = QLabel("")
        self.summary.setStyleSheet("color: #666666;")
        layout.addWidget(self.summary)

        self.results = QListWidget()
        self.results.setStyleSheet(LIST_STYLE)
        # Перенос строк включён, а горизонтальную прокрутку глушим: при
        # включённом переносе она бессмысленна, но Qt всё равно показывает
        # полосу на пару пикселей — вертикальная полоса съедает ширину, и
        # строка перестаёт влезать.
        self.results.setWordWrap(True)
        self.results.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.results.currentRowChanged.connect(self._on_row_changed)
        self.results.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.results, 1)

        buttons = QHBoxLayout()
        self.hint_label = QLabel()
        buttons.addWidget(self.hint_label)
        buttons.addStretch(1)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.hide)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.retranslate()

    def retranslate(self):
        """Переставляет подписи окна под текущий язык интерфейса.

        Список результатов пересобираем: его строки тоже текст, а не
        готовые виджеты, и без refresh() в нём остался бы прежний язык.
        """
        self.setWindowTitle(i18n.tr("Поиск по заметкам"))
        self.query_edit.setPlaceholderText(i18n.tr("Что искать…"))
        self.regex_check.setText(i18n.tr("Рег. выражение"))
        self.regex_check.setToolTip(
            i18n.tr(
                "Искать как регулярное выражение. Без галки запрос ищется "
                "буквально: скобки и звёздочки не имеют особого смысла."
            )
        )
        self.hint_label.setText(
            i18n.tr("Искать по всем заметкам. Enter — открыть найденную.")
        )
        self.close_button.setText(i18n.tr("Закрыть"))
        self.refresh()

    # --- поиск ---------------------------------------------------------

    def set_notes_provider(self, provider):
        """Задаёт источник заметок: функция без аргументов, возвращает список.

        Провайдер, а не список: заметки меняются всё время, и окно должно
        видеть актуальные, а не то, что было на момент открытия.
        """
        self._provider = provider
        if search.is_active(self.query_edit.text()):
            self.refresh()

    def refresh(self):
        """Пересчитывает результаты под текущий запрос."""
        provider = getattr(self, "_provider", None)
        query = self.query_edit.text()
        if provider is None or not search.is_active(query):
            self._results = []
            self.results.clear()
            self.summary.setText("")
            return

        try:
            self._results = search.match_notes(
                provider(), query, regex=self.regex_check.isChecked()
            )
        except search.SearchError as exc:
            # Некорректное выражение — обычная опечатка, а не сбой: говорим
            # словами и не трогаем прошлые результаты.
            self._results = []
            self.results.clear()
            self.summary.setText(str(exc))
            return

        self._fill_list()

    def _fill_list(self):
        self.results.clear()
        for result in self._results:
            item = QListWidgetItem(
                i18n.tr("Заметка %d — совпадений: %d\n%s")
                % (result["id"], result["count"], result["snippet"])
            )
            item.setData(Qt.ItemDataRole.UserRole, result["id"])
            self.results.addItem(item)

        if not self._results:
            self.summary.setText(i18n.tr("Ничего не найдено."))
            return
        total = sum(r["count"] for r in self._results)
        self.summary.setText(
            i18n.tr("Найдено заметок: %d, совпадений: %d")
            % (len(self._results), total)
        )
        # Первый результат сразу выделяем: чаще всего нужен именно он, и
        # лишний клик ни к чему.
        self.results.setCurrentRow(0)

    # --- переходы ------------------------------------------------------

    def current_note_id(self):
        item = self.results.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_row_changed(self, _row):
        note_id = self.current_note_id()
        if note_id is None:
            return
        # Подсвечиваем найденное сразу при выборе: пользователь должен
        # видеть, куда именно он попадёт, не открывая заметку дважды.
        self.note_activated.emit(note_id)

    def _on_item_activated(self, _item):
        note_id = self.current_note_id()
        if note_id is not None:
            self.note_activated.emit(note_id)

    def _activate_current(self):
        self._on_item_activated(self.results.currentItem())

    def current_query(self) -> str:
        return self.query_edit.text()

    def focus_query(self):
        self.query_edit.setFocus()
        self.query_edit.selectAll()

    def closeEvent(self, event):
        """Закрытие крестиком = скрытие.

        Окно переиспользуется: пересоздавать его на каждый Ctrl+Shift+F
        значит терять запрос и результаты.
        """
        event.ignore()
        self.hide()


def apply_highlight(editor, query: str, regex: bool = False) -> int:
    """Подсвечивает все вхождения запроса в редакторе заметки.

    Возвращает число подсвеченных совпадений. Подсветка — только оформление:
    она НЕ меняет форматирование документа (иначе сохранение заметки
    записало бы жёлтый фон в сам текст и он остался бы там навсегда).
    """
    editor.setExtraSelections([])
    if not search.is_active(query):
        return 0
    try:
        pattern = search.compile_query(query, regex=regex)
    except search.SearchError:
        return 0
    if pattern is None:
        return 0

    spans = search.find_matched_spans(editor.toPlainText(), pattern)
    if not spans:
        return 0

    fmt = highlight_cursor_format()
    selections = []
    document = editor.document()
    for start, end in spans:
        cursor = QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selection = editor.ExtraSelection()
        selection.cursor = cursor
        selection.format = fmt
        selections.append(selection)
    editor.setExtraSelections(selections)
    return len(selections)
