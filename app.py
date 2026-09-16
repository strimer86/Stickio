import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QLabel, QMenu,
    QMessageBox, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from database.database import Database, DatabaseClosedError
from services.hotkeys import GlobalHotkeys, HotkeyError, normalize_shortcut
from services.note_manager import NoteManager
from services.settings import (
    DEFAULT_HOTKEYS, HOTKEY_LABELS, Settings,
)
from widgets.hotkey_edit import HotkeyEdit

logger = logging.getLogger(__name__)


def create_app_icon() -> QIcon:
    from widgets.sticky_note import APP_ICON
    if not APP_ICON.isNull():
        return APP_ICON

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#FFD55E"))
    painter.setPen(QColor("#E0B23A"))
    painter.drawRoundedRect(4, 4, 56, 56, 10, 10)

    painter.setPen(QColor("#222222"))
    for y in (24, 32, 40):
        painter.drawLine(18, y, 46, y)
    painter.setPen(QColor("#222222"))
    painter.drawLine(18, 52, 36, 52)
    painter.end()

    return QIcon(pixmap)


def menu_label(text: str, shortcut: str) -> str:
    """Подпись пункта меню с комбинацией через табуляцию (правая колонка)."""
    return "%s\t%s" % (text, shortcut) if shortcut else text


class SettingsDialog(QDialog):
    """Настройки: автозапуск и системные горячие клавиши."""

    def __init__(self, settings: Settings, parent: QWidget = None):
        super().__init__(parent)
        self._settings = settings
        self._edits = {}
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Stickio"))

        self.autostart = QCheckBox("Запускать вместе с Windows")
        self.autostart.setChecked(settings.autostart_enabled())
        # clicked срабатывает только при реальном действии пользователя:
        # программное setChecked при открытии диалога больше не трогает реестр
        self.autostart.clicked.connect(settings.set_autostart)
        layout.addWidget(self.autostart)

        layout.addWidget(self._separator())
        layout.addWidget(QLabel("Горячие клавиши"))

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        saved = settings.hotkeys()
        for row, name in enumerate(HOTKEY_LABELS):
            grid.addWidget(QLabel(HOTKEY_LABELS[name] + ":"), row, 0)
            edit = HotkeyEdit()
            edit.set_shortcut(saved.get(name, ""))
            grid.addWidget(edit, row, 1)
            self._edits[name] = edit
        layout.addLayout(grid)

        self.hint = QLabel(
            "Клавиша назначается при фокусе в поле. Backspace — снять. "
            "Нужен модификатор: Ctrl, Alt, Shift или Win."
        )
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #666666; font-size: 11px;")
        layout.addWidget(self.hint)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        # Qt не переводит стандартные кнопки, если не загружен .qm, а
        # приложение русскоязычное — подписи задаём сами.
        for standard, text in (
            (QDialogButtonBox.StandardButton.Ok, "ОК"),
            (QDialogButtonBox.StandardButton.Cancel, "Отмена"),
            (QDialogButtonBox.StandardButton.RestoreDefaults, "По умолчанию"),
        ):
            self.buttons.button(standard).setText(text)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(self._restore_defaults)
        layout.addWidget(self.buttons)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _restore_defaults(self):
        for name, edit in self._edits.items():
            edit.set_shortcut(DEFAULT_HOTKEYS[name])

    def shortcuts(self) -> dict:
        return {name: edit.shortcut() for name, edit in self._edits.items()}

    def _accept(self):
        """Проверяет комбинации и закрывает диалог, если всё сошлось."""
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
                QMessageBox.warning(self, "Настройки", str(exc))
                edit.setFocus()
                return

        used = {}
        for name, value in values.items():
            if not value:
                continue
            if value in used:
                QMessageBox.warning(
                    self,
                    "Настройки",
                    "Комбинация %s назначена дважды: «%s» и «%s»."
                    % (value, HOTKEY_LABELS[used[value]], HOTKEY_LABELS[name]),
                )
                self._edits[name].setFocus()
                return
            used[value] = name

        self._values = values
        self.accept()

    def result_shortcuts(self) -> dict:
        return getattr(self, "_values", self.shortcuts())


class App:
    """Основной класс приложения Stickio - менеджер заметок."""

    def __init__(self, app):
        """Инициализирует приложение.

        Args:
            app: Экземпляр QApplication
        """
        self.app = app
        self.settings = Settings()
        self.database = Database()
        self.manager = NoteManager(self.database)
        self.tray = None
        self._tray_action_new = None
        self._tray_action_toggle = None
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
    HOTKEY_ACTIONS = ("new_note", "toggle_visibility")

    def _callback_for(self, name: str):
        if name == "new_note":
            return self.manager.create_note
        if name == "toggle_visibility":
            return self._toggle_all_notes_visibility
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
                "Не удалось занять горячие клавиши: %s.\n"
                "Их перехватила другая программа."
                % ", ".join(self.hotkeys.failed),
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )

    def _refresh_hotkey_labels(self):
        """Обновляет подписи меню трея под текущие комбинации."""
        if self._tray_action_new is None:
            return
        saved = self.settings.hotkeys()
        self._tray_action_new.setText(
            menu_label("+ Новая заметка", saved.get("new_note", ""))
        )
        self._tray_action_toggle.setText(
            menu_label(
                "Показать/скрыть все", saved.get("toggle_visibility", "")
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

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(create_app_icon())
        self.tray.setToolTip("Stickio")

        menu = QMenu()

        # Подписи с комбинациями ставятся в _refresh_hotkey_labels: после
        # переназначения текст меню должен меняться вместе с ними.
        action_new = menu.addAction("+ Новая заметка")
        action_new.triggered.connect(self.manager.create_note)
        self._tray_action_new = action_new

        action_show_one = menu.addAction("Показать одну")
        action_show_one.triggered.connect(self.manager.show_one)

        menu.addSeparator()

        action_show = menu.addAction("Показать/скрыть все")
        action_show.triggered.connect(self._toggle_all_notes_visibility)
        self._tray_action_toggle = action_show

        action_hide = menu.addAction("Скрыть все")
        action_hide.triggered.connect(self.manager.hide_all)

        menu.addSeparator()

        action_settings = menu.addAction("Настройки")
        action_settings.triggered.connect(self._open_settings)

        menu.addSeparator()

        action_exit = menu.addAction("Выход")
        action_exit.triggered.connect(self.quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            # Клик по иконке: циклический показ заметок по одной.
            # (Ctrl+Shift+H остался за режимом «показать/скрыть все».)
            self.manager.show_one()

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
