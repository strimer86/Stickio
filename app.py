import json
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout,
    QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QSpinBox,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from database.database import Database, DatabaseClosedError
from services import i18n, transfer
from services.hotkeys import GlobalHotkeys, HotkeyError, normalize_shortcut
from services.note_manager import NoteManager, notes_count_label
from services.settings import (
    DEFAULT_HOTKEYS, DEFAULT_NOTE_SETTINGS, DEFAULT_SAVE_DELAY_MS,
    FONT_SIZE_RANGE, HOTKEY_LABELS, NOTE_SIZE_RANGE, SAVE_DELAY_RANGE, Settings,
)
from widgets.about_dialog import AboutDialog
from widgets.color_picker import ColorPopup
from widgets.hotkey_edit import HotkeyEdit
from widgets.search_window import SearchWindow
from widgets.sticky_note import create_app_icon
from widgets.toolbar import place_popup

logger = logging.getLogger(__name__)

# Ширина колонки подписей в диалоге настроек. Значение подобрано по самой
# длинной подписи («Сохранять текст через:»): если задавать ширину каждому
# QLabel отдельно, поля встают в разные колонки — у сетки своя, у строки
# интервала своя. Общая константа держит все поля на одной вертикали.
LABEL_COLUMN_WIDTH = 168
# Ширина колонки значений. Одна на все поля: образец цвета — кнопка 64 px,
# спинбокс — 90, и разная ширина читается как «элементы разъехались».
FIELD_COLUMN_WIDTH = 110


def menu_label(text: str, shortcut: str) -> str:
    """Подпись пункта меню с комбинацией через табуляцию (правая колонка)."""
    return "%s\t%s" % (text, shortcut) if shortcut else text


class _ColorButton(QPushButton):
    """Образец цвета: показывает текущий и открывает палитру по клику."""

    color_changed = Signal(QColor)

    def __init__(self, for_text: bool = False, parent: QWidget = None):
        super().__init__(parent)
        self._for_text = for_text
        self._color = QColor("#FFFFFF")
        self._popup = None
        self.setFixedSize(64, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._choose)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.setStyleSheet(
            "QPushButton { background: %s;"
            " border: 1px solid rgba(0,0,0,110); border-radius: 5px; }"
            % self._color.name()
        )
        self.setToolTip(self._color.name().upper())

    def _choose(self):
        popup = ColorPopup(self, for_text=self._for_text)
        popup.set_current(self._color)
        popup.color_selected.connect(self._on_selected)
        popup.destroyed.connect(self._forget)
        self._popup = popup
        place_popup(popup, self)

    def _on_selected(self, color: QColor):
        self.set_color(color)
        self.color_changed.emit(QColor(color))
        if self._popup is not None:
            self._popup.close()

    def _forget(self, *_args):
        self._popup = None


class SettingsDialog(QDialog):
    """Настройки: язык, автозапуск, вид новой заметки и горячие клавиши."""

    def __init__(self, settings: Settings, parent: QWidget = None):
        super().__init__(parent)
        self._settings = settings
        self._edits = {}
        # Что переставлять при смене языка: (виджет, что менять, исходная
        # строка, хвост). Готовые лямбды здесь не годятся: заведённые в
        # цикле, они все ссылались бы на последний виджет.
        self._tr_items = []
        # Язык на момент открытия. Смена применяется сразу (иначе выбор
        # выглядит неработающим), поэтому «Отмена» обязана вернуть прежний —
        # иначе она отменяла бы не всё.
        self._language_at_open = i18n.current_language()
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Stickio"))

        # Галки и строку с интервалом заворачиваем в тот же левый контейнер,
        # что и сетки: у диалога есть минимальная ширина, но окно шире её,
        # и «просто добавленные» виджеты растягиваются на всю ширину, уезжая
        # вправо относительно полей с фиксированной шириной. Тогда на одном
        # экране получается два разных левых края.
        toggles = QVBoxLayout()
        toggles.setContentsMargins(0, 0, 0, 0)

        # Язык — первой строкой: это единственная настройка, результат
        # которой виден прямо здесь, и искать её внизу списка незачем.
        language_row = QHBoxLayout()
        self.language_label = QLabel()
        self.language_label.setFixedWidth(LABEL_COLUMN_WIDTH)
        self._register(self.language_label, "text", "Язык интерфейса:")
        language_row.addWidget(self.language_label)

        self.language_combo = QComboBox()
        for code, name in i18n.LANGUAGES:
            # Код языка кладём данными, а не разбираем подпись обратно:
            # названия языков не переводятся и совпадать не обязаны.
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(
            i18n.LANGUAGE_CODES.index(self._language_at_open)
        )
        self.language_combo.setFixedWidth(FIELD_COLUMN_WIDTH)
        language_row.addWidget(self.language_combo)
        language_row.addStretch(1)
        toggles.addLayout(language_row)
        # Сигнал подключаем последним: addItem и setCurrentIndex выше уже
        # дёрнули бы обработчик, когда остальных виджетов ещё нет.
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        self.autostart = QCheckBox()
        self.autostart.setChecked(settings.autostart_enabled())
        self._register(self.autostart, "text", "Запускать вместе с Windows")
        toggles.addWidget(self.autostart)

        # Подпись держим короткой: QCheckBox не умеет переносить текст, и
        # длинный вариант («Спрашивать перед удалением заметки», 432 px)
        # распирал диалог с 380 до 478 — сетки с полями фиксированной ширины
        # оставались 264, и поля вставали не на одну вертикаль с галками.
        # Что именно спрашивается, сказано в подсказке.
        self.confirm_delete = QCheckBox()
        self.confirm_delete.setChecked(settings.confirm_delete())
        self._register(self.confirm_delete, "text", "Спрашивать при удалении")
        self._register(
            self.confirm_delete, "tooltip",
            "Показывать запрос перед удалением заметки.\n"
            "Удаление безвозвратное, поэтому по умолчанию запрос включён.",
        )
        toggles.addWidget(self.confirm_delete)

        delay_row = QHBoxLayout()
        self.delay_label = QLabel()
        # Ширину метки фиксируем по самой длинной подписи в колонке
        # («Сохранять текст через:», 264 px): тогда спинбокс встаёт ровно
        # под «Цвет фона»/«Размер шрифта», а не уезжает в отдельную колонку.
        self.delay_label.setFixedWidth(LABEL_COLUMN_WIDTH)
        self._register(self.delay_label, "text", "Сохранять текст через:")
        delay_row.addWidget(self.delay_label)
        self.save_delay_spin = QSpinBox()
        low, high = SAVE_DELAY_RANGE
        self.save_delay_spin.setRange(low, high)
        # Шаг 100 мс: точность до миллисекунды здесь бессмысленна, а крутить
        # колесом от 200 до 5000 с шагом 1 было бы мучением.
        self.save_delay_spin.setSingleStep(100)
        self.save_delay_spin.setValue(settings.save_delay_ms())
        self.save_delay_spin.setFixedWidth(FIELD_COLUMN_WIDTH)
        self._register(self.save_delay_spin, "suffix", " мс")
        self._register(
            self.save_delay_spin, "tooltip",
            "Пауза после последнего нажатия клавиши. Пока печатаешь без "
            "остановки, запись не идёт — она начинается, когда перестанешь "
            "печатать.",
        )
        delay_row.addWidget(self.save_delay_spin)
        delay_row.addStretch(1)
        toggles.addLayout(delay_row)

        # Общий левый контейнер для того, что не сетка. Растяжка снаружи
        # прижимает группу влево, а не растягивает её на всю ширину окна.
        toggles_row = QHBoxLayout()
        toggles_row.addLayout(toggles)
        toggles_row.addStretch(1)
        layout.addLayout(toggles_row)

        layout.addWidget(self._separator())
        self.note_section = QLabel()
        self._register(self.note_section, "text", "Новая заметка")
        layout.addWidget(self.note_section)

        saved_note = settings.note_defaults()
        note_grid = QGridLayout()
        # Подписи одной ширины — иначе поля встают лесенкой: «Цвет текста:»
        # короче «Размер шрифта:», и колонка значений гуляет вслед за самым
        # длинным текстом.
        for text in (
            "Цвет фона:", "Цвет текста:", "Размер шрифта:", "Ширина заметки:",
        ):
            label = QLabel()
            label.setFixedWidth(LABEL_COLUMN_WIDTH)
            self._register(label, "text", text)
            note_grid.addWidget(label, note_grid.rowCount(), 0)
        self.background_button = _ColorButton(for_text=False)
        self.background_button.set_color(QColor(saved_note["background_color"]))
        self.background_button.setFixedWidth(FIELD_COLUMN_WIDTH)
        note_grid.addWidget(self.background_button, 0, 1)

        self.text_button = _ColorButton(for_text=True)
        self.text_button.set_color(QColor(saved_note["text_color"]))
        self.text_button.setFixedWidth(FIELD_COLUMN_WIDTH)
        note_grid.addWidget(self.text_button, 1, 1)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(*FONT_SIZE_RANGE)
        self.font_size_spin.setValue(saved_note["font_size"])
        self.font_size_spin.setFixedWidth(FIELD_COLUMN_WIDTH)
        self._register(self.font_size_spin, "suffix", " пт")
        note_grid.addWidget(self.font_size_spin, 2, 1)

        # Ширину и высоту держим одной строкой: это две половины одного
        # параметра, и разнесённые по строкам они читаются как два разных
        # независимых числа.
        self.width_spin, self.height_spin = self._size_spins(saved_note)
        for spin in (self.width_spin, self.height_spin):
            self._register(spin, "suffix", " пт")
        self._register(
            self.width_spin, "tooltip", "Ширина новой заметки в пикселях."
        )
        self._register(
            self.height_spin, "tooltip", "Высота новой заметки в пикселях."
        )
        size_row = self._size_row(self.width_spin, self.height_spin)
        note_grid.addLayout(size_row, 3, 1)
        layout.addLayout(self._left_aligned(note_grid))

        self.note_hint = QLabel()
        self.note_hint.setStyleSheet("color: #666666; font-size: 11px;")
        self._register(self.note_hint, "text", "Относится только к новым заметкам.")
        layout.addWidget(self.note_hint)

        layout.addWidget(self._separator())
        self.hotkeys_section = QLabel()
        self._register(self.hotkeys_section, "text", "Горячие клавиши")
        layout.addWidget(self.hotkeys_section)

        grid = QGridLayout()
        saved = settings.hotkeys()
        for row, name in enumerate(HOTKEY_LABELS):
            label = QLabel()
            label.setFixedWidth(LABEL_COLUMN_WIDTH)
            # Двоеточие дописываем после перевода: ключом словаря служит
            # сама подпись действия, без знака препинания.
            self._register(label, "text", HOTKEY_LABELS[name], suffix=":")
            grid.addWidget(label, row, 0)
            edit = HotkeyEdit()
            edit.set_shortcut(saved.get(name, ""))
            grid.addWidget(edit, row, 1)
            self._edits[name] = edit
        layout.addLayout(self._left_aligned(grid))

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #666666; font-size: 11px;")
        self._register(
            self.hint, "text",
            "Клавиша назначается при фокусе в поле. Backspace — снять. "
            "Нужен модификатор: Ctrl, Alt, Shift или Win.",
        )
        layout.addWidget(self.hint)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        # Qt не переводит стандартные кнопки, если не загружен .qm, а
        # приложение русскоязычное — подписи задаём сами.
        self._standard_buttons = (
            (QDialogButtonBox.StandardButton.Ok, "ОК"),
            (QDialogButtonBox.StandardButton.Cancel, "Отмена"),
            (QDialogButtonBox.StandardButton.RestoreDefaults, "По умолчанию"),
        )
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(self._restore_defaults)
        layout.addWidget(self.buttons)

        self.retranslate()

    def _register(self, widget, attribute: str, source: str, suffix: str = ""):
        """Запоминает подпись, которую надо переставить при смене языка.

        Хранится пара «виджет + что именно менять», а не готовая лямбда:
        лямбда, заведённая в цикле, захватила бы последний виджет, и
        переводился бы он один.
        """
        self._tr_items.append((widget, attribute, source, suffix))

    def retranslate(self):
        """Ставит все подписи диалога под текущий язык.

        Диалог переводит себя сам: язык выбирают именно здесь, и до
        нажатия «ОК» пользователь должен видеть, что выбрал.
        """
        self.setWindowTitle(i18n.tr("Настройки"))
        for widget, attribute, source, suffix in self._tr_items:
            text = i18n.tr(source) + suffix
            if attribute == "text":
                widget.setText(text)
            elif attribute == "tooltip":
                widget.setToolTip(text)
            elif attribute == "suffix":
                widget.setSuffix(text)
        for standard, source in self._standard_buttons:
            self.buttons.button(standard).setText(i18n.tr(source))

    def _on_language_changed(self, _index):
        """Применяет язык сразу при выборе в списке.

        Не по «ОК»: иначе выбор выглядел бы неработающим до перезапуска, и
        проверить его было бы нечем. Откат — на «Отмене», см. reject().
        """
        if not i18n.set_language(self.language_combo.currentData()):
            return
        self.retranslate()

    def reject(self):
        """«Отмена» возвращает и язык: он применялся сразу при выборе.

        Диалог после этого закрывается, и подписи в нём уже никто не увидит,
        но оставлять их на отменённом языке — значит держать окно в
        состоянии, которого не бывает: следующий, кто откроет его повторно,
        получит новый объект, а вот код, читающий подписи (тесты), — нет.
        """
        if i18n.current_language() != self._language_at_open:
            i18n.set_language(self._language_at_open)
            self.retranslate()
        super().reject()

    @staticmethod
    def _left_aligned(layout) -> QHBoxLayout:
        """Прижимает содержимое к левому краю диалога.

        Растяжку держим снаружи, а не внутри: при `setColumnStretch` ячейка
        растёт, а поле уезжает к дальнему краю — между меткой и полем
        возникает разрыв в половину диалога. Принимается любая раскладка
        (сетка или вертикальная), поэтому параметр назван `layout`.
        """
        row = QHBoxLayout()
        row.addLayout(layout)
        row.addStretch(1)
        return row

    @staticmethod
    def _size_spins(saved_note: dict) -> tuple:
        """Пара спинбоксов «ширина × высота» для новой заметки.

        Ширину полей не задаём: её считает раскладка по sizeHint виджета,
        см. `_size_row`. Подписи « пт» и подсказки тоже не здесь: их ставит
        retranslate() по списку _tr_items, иначе одни и те же строки жили бы
        в двух местах и разошлись бы при первой же правке.
        """
        low, high = NOTE_SIZE_RANGE
        spins = []
        for key in ("width", "height"):
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(saved_note[key])
            spin.setSingleStep(10)
            spins.append(spin)
        return spins

    @staticmethod
    def _size_row(width_spin: QSpinBox, height_spin: QSpinBox) -> QHBoxLayout:
        """Строка «ширина × высота» для новой заметки.

        Ширину полей не задаём: спинбокс берёт её сам по sizeHint. Раньше
        он вписывался в колонку значений (110 px) — двум полям с надписью
        « пт» там места нет, поле ввода сжималось до нуля, и вместо
        «380 пт × 300 пт» оставались одни кнопки со стрелками. Колонка
        значений от этого стала шире, зато значение видно.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(width_spin)
        row.addWidget(QLabel("×"))
        row.addWidget(height_spin)
        row.addStretch(1)
        return row

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _restore_defaults(self):
        for name, edit in self._edits.items():
            edit.set_shortcut(DEFAULT_HOTKEYS[name])
        for name, value in DEFAULT_NOTE_SETTINGS.items():
            if name == "background_color":
                self.background_button.set_color(QColor(value))
            elif name == "text_color":
                self.text_button.set_color(QColor(value))
            elif name == "font_size":
                self.font_size_spin.setValue(value)
            elif name == "width":
                self.width_spin.setValue(value)
            elif name == "height":
                self.height_spin.setValue(value)
        self.confirm_delete.setChecked(True)
        self.save_delay_spin.setValue(DEFAULT_SAVE_DELAY_MS)

    def shortcuts(self) -> dict:
        return {name: edit.shortcut() for name, edit in self._edits.items()}

    def note_settings(self) -> dict:
        return {
            "background_color": self.background_button.color().name(),
            "text_color": self.text_button.color().name(),
            "font_size": self.font_size_spin.value(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
        }

    def _validated_hotkeys(self):
        """Проверяет комбинации. None — есть ошибка, диалог закрывать нельзя."""
        values = {}
        for name, edit in self._edits.items():
            raw = edit.shortcut()
            if not raw:
                # Пусто — значит действие отключено, это допустимо
                values[name] = ""
                continue
            try:
                values[name] = normalize_shortcut(raw)
            except HotkeyError as exc:
                QMessageBox.warning(self, i18n.tr("Настройки"), str(exc))
                edit.setFocus()
                return None

        used = {}
        for name, value in values.items():
            if not value:
                continue
            if value in used:
                QMessageBox.warning(
                    self,
                    i18n.tr("Настройки"),
                    i18n.tr("Комбинация %s назначена дважды: «%s» и «%s».")
                    % (
                        value,
                        i18n.tr(HOTKEY_LABELS[used[value]]),
                        i18n.tr(HOTKEY_LABELS[name]),
                    ),
                )
                self._edits[name].setFocus()
                return None
            used[value] = name
        return values

    def _accept(self):
        """Применяет всё разом: ни одна правка не должна жить после «Отмены»."""
        values = self._validated_hotkeys()
        if values is None:
            return

        # Автозапуск пишет в реестр и может упасть из-за политик — применяем
        # первым, чтобы при неудаче не сохранить половину настроек.
        if self.autostart.isChecked() != self._settings.autostart_enabled():
            try:
                self._settings.set_autostart(self.autostart.isChecked())
            except Exception:
                logger.exception("Failed to change autostart")
                QMessageBox.warning(
                    self,
                    i18n.tr("Настройки"),
                    i18n.tr("Не удалось изменить автозапуск."),
                )
                return

        self._settings.set_confirm_delete(self.confirm_delete.isChecked())
        self._settings.set_save_delay_ms(self.save_delay_spin.value())
        self._settings.set_note_defaults(self.note_settings())
        # Язык применялся сразу при выборе в списке — здесь его только
        # сохраняем, чтобы он пережил перезапуск.
        self._settings.set_language(i18n.current_language())
        self._values = values
        self.accept()

    def save_delay_ms(self) -> int:
        return self.save_delay_spin.value()

    def result_shortcuts(self) -> dict:
        return getattr(self, "_values", self.shortcuts())


class App:
    """Основной класс приложения Stickio - менеджер заметок."""

    def __init__(self, app, qt_translation=None):
        """Инициализирует приложение.

        Args:
            app: Экземпляр QApplication
            qt_translation: перевод служебных строк Qt, уже подключённый
                в main.py. Передаётся, а не создаётся здесь, потому что
                язык ставится ДО появления первого окна: сообщение об
                ошибке запуска показывает ещё main.py.
        """
        self.app = app
        # Объект нужен на всю жизнь приложения: смена языка снимает старый
        # перевод и ставит новый, а без сохранённой ссылки снять его нельзя.
        self.qt_translation = qt_translation or i18n.QtTranslation(app)
        # Язык, под который собран текущий интерфейс. Нужен, чтобы не
        # пересобирать меню трея и не трогать окна, когда язык не менялся.
        self._language = i18n.current_language()
        self.settings = Settings()
        self.database = Database()
        # Настройки передаём менеджеру: из них берётся вид новой заметки и
        # то, спрашивать ли подтверждение удаления.
        self.manager = NoteManager(self.database, settings=self.settings)
        self.tray = None
        self._tray_action_new = None
        self._tray_action_toggle = None
        self._tray_action_search = None
        # Окно поиска создаём лениво: пока его не открывали, незачем держать
        # лишнее окно и список заметок.
        self._search_window = None
        # App не является QObject, поэтому родителя не передаём — владение
        # остаётся за этим атрибутом, время жизни совпадает с приложением.
        self.hotkeys = GlobalHotkeys()

    def _save_all(self, *args):
        """Сохраняет геометрию и контент всех заметок — вызывается при выходе/перезагрузке.

        Может прийти несколько раз подряд (commitDataRequest от Windows,
        aboutToQuit, quit()) — повторный вызов безвреден: заметки уже
        сохранены, а закрытая база отдаёт DatabaseClosedError.
        """
        for window in list(self.manager.windows.values()):
            try:
                window.save_note()
            except DatabaseClosedError:
                return
            except Exception:
                logger.exception("Failed to save note id=%s on quit", window.note.id)

    def start(self):
        """Запускает приложение, загружает заметки и настраивает системный трей."""
        # Трей создаём до хоткеев: если комбинацию заняла другая программа,
        # пользователю нужно показать уведомление, а показывать его нечем.
        self._setup_tray()
        self.apply_hotkeys()
        # гарантируем сохранение при завершении процесса Windows (перезагрузка/выключение)
        try:
            self.app.aboutToQuit.connect(self._save_all)
        except Exception:
            logger.exception("Failed to connect aboutToQuit")
        try:
            # commitDataRequest передаёт QSessionManager — принимаем *args
            self.app.commitDataRequest.connect(self._save_all)
        except Exception:
            logger.exception("Failed to connect commitDataRequest")
        self.manager.load_all()

        if not self.manager.windows:
            self.manager.create_note()

    def _add_app_shortcut(self, key: str, sequence: str, callback) -> bool:
        """Регистрирует системную горячую клавишу.

        Раньше здесь был QShortcut с родителем-QApplication: в этом случае
        Qt не привязывает комбинацию ни к одному окну, и она не срабатывала
        вообще — ни внутри приложения, ни тем более снаружи. Для стикеров
        нужен именно системный хоткей, работающий при любом фокусе.
        """
        ok = self.hotkeys.register(key, sequence, callback)
        if not ok:
            logger.warning("Hotkey %s (%s) is not available", key, sequence)
        return ok

    # Действия, доступные по системной комбинации. Порядок совпадает с
    # HOTKEY_LABELS — от него зависит порядок строк в настройках.
    HOTKEY_ACTIONS = ("new_note", "toggle_visibility", "search")

    def _callback_for(self, name: str):
        if name == "new_note":
            return self.manager.create_note
        if name == "toggle_visibility":
            return self._toggle_all_notes_visibility
        if name == "search":
            return self.open_search
        raise KeyError(name)

    def apply_hotkeys(self, mapping=None):
        """Перерегистрирует системные комбинации.

        mapping=None — взять сохранённые (перечитать после отмены диалога),
        иначе — сначала записать новые значения.
        """
        if mapping is not None:
            self.settings.set_hotkeys(mapping)

        self.hotkeys.install(self.app)
        self.hotkeys.unregister_all()
        self.hotkeys.failed.clear()

        saved = self.settings.hotkeys()
        for name in self.HOTKEY_ACTIONS:
            shortcut = saved.get(name, "")
            if not shortcut:
                # Пустая строка — пользователь снял комбинацию намеренно,
                # а не ошибся; молчим, действие остаётся в меню трея.
                logger.info("Hotkey %s is disabled", name)
                continue
            self._add_app_shortcut(name, shortcut, self._callback_for(name))

        self._refresh_hotkey_labels()
        self._warn_failed_hotkeys()

    def _warn_failed_hotkeys(self):
        if not self.hotkeys.failed:
            return
        logger.warning(
            "Some hotkeys are busy: %s", ", ".join(self.hotkeys.failed)
        )
        # Пользователь должен знать, почему привычная комбинация молчит
        if self.tray is not None and self.tray.isSystemTrayAvailable():
            self.tray.showMessage(
                "Stickio",
                i18n.tr(
                    "Не удалось занять горячие клавиши: %s.\n"
                    "Их перехватила другая программа."
                )
                % ", ".join(self.hotkeys.failed),
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )

    def _refresh_note_count(self):
        """Показывает число заметок в подсказке трея.

        Подсказка — единственное место, где счётчик виден, не открывая меню:
        наводишь курсор на иконку и сразу знаешь, сколько заметок заведено
        и сколько из них сейчас на экране.
        """
        if self.tray is None:
            return
        total = len(self.manager.windows)
        visible = len([w for w in self.manager.windows.values() if w.isVisible()])
        self.tray.setToolTip(
            i18n.tr("%s\nВидимых: %d") % (notes_count_label(total), visible)
        )

    def _refresh_hotkey_labels(self):
        """Обновляет подписи меню трея под текущие комбинации."""
        if self._tray_action_new is None:
            return
        saved = self.settings.hotkeys()
        self._tray_action_new.setText(
            menu_label(
                i18n.tr("+ Новая заметка"), saved.get("new_note", "")
            )
        )
        self._tray_action_toggle.setText(
            menu_label(
                i18n.tr("Показать/скрыть все"),
                saved.get("toggle_visibility", ""),
            )
        )
        if self._tray_action_search is not None:
            self._tray_action_search.setText(
                menu_label(
                    i18n.tr("Поиск по заметкам"), saved.get("search", "")
                )
            )

    def _toggle_all_notes_visibility(self):
        """Переключение видимости всех заметок"""
        # Проверяем, есть ли видимые заметки
        visible_windows = [w for w in self.manager.windows.values() if w.isVisible()]
        if visible_windows:
            # Скрываем все
            self.manager.hide_all()
        else:
            # Показываем все
            self.manager.show_all()
        # Число видимых изменилось — в подсказке трея оно отдельной строкой
        self._refresh_note_count()

    def _show_one_and_refresh(self):
        self.manager.show_one()
        self._refresh_note_count()

    def _hide_all_and_refresh(self):
        self.manager.hide_all()
        self._refresh_note_count()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(create_app_icon())
        self._refresh_note_count()
        # Счётчик обновляется по сигналу, а не вызовом из каждого места, где
        # заметка создаётся или удаляется: раньше такое обновление легко
        # забыть, и число в подсказке расходилось бы с реальностью.
        self.manager.notes_changed.connect(self._refresh_note_count)

        self.tray.setContextMenu(self._build_tray_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_tray_menu(self) -> QMenu:
        """Меню трея.

        Вынесено из _setup_tray отдельным методом, чтобы проверялось тестом:
        создать значок в трее в тестовой среде нельзя, а собрать меню и
        посмотреть его пункты — можно.
        """
        menu = QMenu()

        # Подписи с комбинациями ставятся в _refresh_hotkey_labels: после
        # переназначения текст меню должен меняться вместе с ними.
        action_new = menu.addAction(i18n.tr("+ Новая заметка"))
        action_new.triggered.connect(self.manager.create_note)
        self._tray_action_new = action_new

        action_show_one = menu.addAction(i18n.tr("Показать одну"))
        # Число ВИДИМЫХ меняется и этими действиями, поэтому каждое
        # оборачивается в свой обработчик: сигнала notes_changed здесь мало,
        # он говорит только о создании и удалении.
        action_show_one.triggered.connect(self._show_one_and_refresh)

        menu.addSeparator()

        action_show = menu.addAction(i18n.tr("Показать/скрыть все"))
        action_show.triggered.connect(self._toggle_all_notes_visibility)
        self._tray_action_toggle = action_show

        action_hide = menu.addAction(i18n.tr("Скрыть все"))
        action_hide.triggered.connect(self._hide_all_and_refresh)

        menu.addSeparator()

        self._tray_action_search = menu.addAction(
            i18n.tr("Поиск по заметкам")
        )
        self._tray_action_search.setShortcut("Ctrl+F")
        self._tray_action_search.triggered.connect(self.open_search)

        menu.addSeparator()

        action_settings = menu.addAction(i18n.tr("Настройки"))
        action_settings.triggered.connect(self._open_settings)

        menu.addSeparator()

        action_export_json = menu.addAction(
            i18n.tr("Экспорт заметок (JSON)…")
        )
        action_export_json.triggered.connect(self._export_json)

        action_export_html = menu.addAction(
            i18n.tr("Экспорт заметок (HTML)…")
        )
        action_export_html.triggered.connect(self._export_html)

        action_import = menu.addAction(
            i18n.tr("Импорт заметок из JSON…")
        )
        action_import.triggered.connect(self._import_json)

        action_backup = menu.addAction(i18n.tr("Копия базы данных…"))
        action_backup.triggered.connect(self._backup_database)

        menu.addSeparator()

        # «О программе» стоит рядом с «Выходом», а не в группе настроек:
        # это справка, а не параметр, и ищут её в самом низу меню.
        action_about = menu.addAction(i18n.tr("О программе"))
        action_about.triggered.connect(self._open_about)

        action_exit = menu.addAction(i18n.tr("Выход"))
        action_exit.triggered.connect(self.quit)

        return menu

    # --- Экспорт, импорт и копии базы ---------------------------------
    #
    # Всё это живёт в меню трея, а не в настройках: это действия «сделать
    # сейчас», а не параметры, которые сохраняются между запусками.

    def _notes_or_warn(self):
        """Все заметки из базы. None — заметок нет, показали предупреждение."""
        notes = self.database.get_all_notes()
        if notes:
            return notes
        QMessageBox.information(
            self.tray.parent() if self.tray else None,
            "Stickio",
            i18n.tr("Заметок нет — выгружать нечего."),
        )
        return None

    def _ask_save_path(self, caption: str, name: str, filters: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            None, caption, name, filters
        )
        return path

    def _export_json(self):
        notes = self._notes_or_warn()
        if not notes:
            return
        path = self._ask_save_path(
            i18n.tr("Экспорт заметок"),
            transfer.default_export_name("json"),
            i18n.tr("Файл заметок Stickio (*.json);;Все файлы (*)"),
        )
        if not path:
            return
        try:
            data = transfer.build_export(notes)
            transfer.write_text(
                path, json.dumps(data, ensure_ascii=False, indent=2)
            )
        except Exception as exc:
            logger.exception("Failed to export notes to %s", path)
            QMessageBox.warning(
                None,
                i18n.tr("Экспорт заметок"),
                i18n.tr("Не удалось сохранить файл:\n%s") % exc,
            )
            return
        self._notify(
            i18n.tr("Экспорт заметок"),
            i18n.tr("Сохранено заметок: %d\n%s") % (len(notes), path),
        )

    def _export_html(self):
        notes = self._notes_or_warn()
        if not notes:
            return
        path = self._ask_save_path(
            i18n.tr("Экспорт заметок в HTML"),
            transfer.default_export_name("html"),
            i18n.tr("Веб-страница (*.html);;Все файлы (*)"),
        )
        if not path:
            return
        try:
            transfer.write_text(path, transfer.build_html(notes))
        except Exception as exc:
            logger.exception("Failed to export notes to %s", path)
            QMessageBox.warning(
                None,
                i18n.tr("Экспорт заметок"),
                i18n.tr("Не удалось сохранить файл:\n%s") % exc,
            )
            return
        self._notify(
            i18n.tr("Экспорт заметок"),
            i18n.tr("Сохранено заметок: %d\n%s") % (len(notes), path),
        )

    def _import_json(self):
        path, _ = QFileDialog.getOpenFileName(
            None,
            i18n.tr("Импорт заметок"),
            "",
            i18n.tr("Файл заметок Stickio (*.json);;Все файлы (*)"),
        )
        if not path:
            return
        try:
            records = transfer.read_export_file(path)
        except transfer.TransferError as exc:
            logger.warning("Import rejected: %s", exc)
            QMessageBox.warning(None, i18n.tr("Импорт заметок"), str(exc))
            return

        # Импорт не удаляет текущие заметки — он к ним добавляет.
        answer = QMessageBox.question(
            None,
            i18n.tr("Импорт заметок"),
            i18n.tr(
                "Добавить заметок из файла: %d?\n"
                "Существующие заметки останутся на месте."
            )
            % len(records),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        created = self.manager.import_notes(records)
        if not created:
            QMessageBox.warning(
                None,
                i18n.tr("Импорт заметок"),
                i18n.tr("Не удалось добавить ни одной заметки."),
            )
            return
        self._notify(
            i18n.tr("Импорт заметок"),
            i18n.tr("Добавлено заметок: %d") % len(created),
        )

    def _backup_database(self):
        path = self._ask_save_path(
            i18n.tr("Копия базы данных"),
            transfer.default_export_name("db"),
            i18n.tr("База данных SQLite (*.db);;Все файлы (*)"),
        )
        if not path:
            return
        try:
            transfer.backup_database(self.database, path)
        except Exception as exc:
            logger.exception("Failed to back up database to %s", path)
            QMessageBox.warning(
                None,
                i18n.tr("Копия базы данных"),
                i18n.tr("Не удалось создать копию:\n%s") % exc,
            )
            return
        self._notify(
            i18n.tr("Копия базы данных"),
            i18n.tr("Сохранено:\n%s") % path,
        )

    def _notify(self, title: str, message: str):
        """Сообщение о результате: всплывающая подсказка трея, иначе диалог.

        Диалог показываем только в крайнем случае — из-за него приложение
        оказывается поверх остальных окон, а результат читается и в трее.
        """
        logger.info("%s: %s", title, message.replace("\n", " "))
        if self.tray is not None and self.tray.isSystemTrayAvailable():
            self.tray.showMessage(
                "Stickio — " + title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            return
        QMessageBox.information(None, title, message)

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            # Клик по иконке: циклический показ заметок по одной.
            # (Ctrl+Shift+H остался за режимом «показать/скрыть все».)
            self.manager.show_one()

    # --- поиск ---------------------------------------------------------

    def open_search(self):
        """Открывает окно поиска и ставит курсор в поле запроса."""
        window = self._ensure_search_window()
        window.show()
        window.raise_()
        window.activateWindow()
        window.focus_query()
        # Пересчитываем: пока окно было скрыто, заметки могли измениться.
        window.refresh()

    def _ensure_search_window(self):
        if self._search_window is None:
            window = SearchWindow()
            # Провайдер, а не снимок списка: заметки создаются и удаляются,
            # а окно поиска живёт между вызовами.
            window.set_notes_provider(self.database.get_all_notes)
            window.note_activated.connect(self._focus_note)
            self._search_window = window
        return self._search_window

    def _focus_note(self, note_id: int):
        """Показывает заметку с подсветкой найденного.

        Заметки может уже не быть: её удалили, пока окно поиска было
        открыто. Тогда просто ничего не делаем — падать из-за этого нельзя,
        поиск остаётся рабочим для остальных результатов.
        """
        window = self.manager.windows.get(note_id)
        if window is None:
            note = None
            try:
                note = self.database.get_note(note_id)
            except DatabaseClosedError:
                return
            if note is None:
                logger.info("Note %s from search results no longer exists", note_id)
                return
            window = self.manager._open_window(note, show=True)

        window.reveal()

        query = ""
        regex = False
        if self._search_window is not None:
            query = self._search_window.current_query()
            regex = self._search_window.regex_check.isChecked()
        hits = window.highlight(query, regex=regex)
        if not hits:
            # Заметку открыли, но подсветить нечего (текст изменили после
            # поиска) — окно всё равно всплыло бы, а курсор стоял бы не там.
            window.clear_highlight()

    def _open_about(self):
        """Окно «О программе».

        Комбинации клавиш на время показа не снимаем, как в настройках:
        вводить здесь нечего, а нажатая Ctrl+Shift+N просто создаст заметку
        за диалогом — ничего не сломается.
        """
        AboutDialog().exec()

    def _open_settings(self):
        # Пока открыт диалог, системные комбинации снимаем: иначе набор
        # Ctrl+Shift+N в поле захвата параллельно создал бы новую заметку.
        self.hotkeys.unregister_all()
        changed = None
        try:
            dialog = SettingsDialog(self.settings)
            if dialog.exec():
                changed = dialog.result_shortcuts()
        finally:
            # При отмене mapping=None — вернутся сохранённые значения; при
            # исключении комбинации тоже восстановятся, а не пропадут.
            self.apply_hotkeys(changed)
        # Язык переключается прямо в диалоге (иначе выбор не видно), а здесь
        # его разносим по уже открытым окнам и меню трея. При «Отмене»
        # диалог вернул прежний язык, и делать нечего.
        self._apply_language()
        self._apply_save_delay()

    def _apply_language(self):
        """Переносит текущий язык на то, что уже открыто.

        Окна заметок, панель оформления и окно поиска собирались на прежнем
        языке, поэтому их надо переставить — иначе до перезапуска осталась
        бы смесь языков. Пересоздавать окна нельзя: потерялись бы позиция,
        прокрутка и несохранённый набор в редакторе.
        """
        language = i18n.current_language()
        if language == self._language:
            return
        self._language = language
        logger.info("Applying interface language: %s", language)

        self.qt_translation.apply(language)

        if self.tray is not None:
            old_menu = self.tray.contextMenu()
            self.tray.setContextMenu(self._build_tray_menu())
            # Значок трея меню не удаляет — без этого старые меню копились бы
            # при каждом переключении языка.
            if old_menu is not None:
                old_menu.deleteLater()
            self._refresh_hotkey_labels()
            self._refresh_note_count()

        for window in list(self.manager.windows.values()):
            try:
                window.retranslate()
            except Exception:
                logger.exception(
                    "Failed to retranslate note id=%s", window.note.id
                )

        if self._search_window is not None:
            self._search_window.retranslate()

    def _apply_save_delay(self):
        """Разносит интервал автосохранения по уже открытым заметкам.

        Настройка читается окном один раз при создании, поэтому без этого
        шага новое значение подхватилось бы только у заметок, открытых после
        перезапуска — а пользователь ждёт эффекта сразу.
        """
        delay = self.settings.save_delay_ms()
        for window in list(self.manager.windows.values()):
            try:
                window.set_save_delay(delay)
            except Exception:
                logger.exception(
                    "Failed to apply save delay to note id=%s", window.note.id
                )

    def quit(self):
        # 1. Снимаем системные горячие клавиши — иначе они остаются
        #    занятыми за процессом до его полного завершения
        self.hotkeys.unregister_all()

        # 2. Сохраняем все заметки, пока соединение с БД ещё живо
        self._save_all()

        # 2. Закрываем все окна (их closeEvent тоже зовёт save_note)
        self.manager.close_all()

        # 3. Только теперь рвём соединение — иначе closeEvent писал бы в мёртвую БД
        self.database.close()

        # 4. Скрываем иконку в трее
        if self.tray is not None:
            self.tray.hide()

        # 5. Выходим из приложения
        self.app.quit()
