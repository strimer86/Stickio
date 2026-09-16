import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QMenu, QSystemTrayIcon, QVBoxLayout,
    QLabel, QWidget,
)

from database.database import Database, DatabaseClosedError
from services.hotkeys import GlobalHotkeys
from services.note_manager import NoteManager
from services.settings import Settings

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


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget = None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Настройки")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Stickio"))

        self.autostart = QCheckBox("Запускать вместе с Windows")
        self.autostart.setChecked(settings.autostart_enabled())
        # clicked срабатывает только при реальном действии пользователя:
        # программное setChecked при открытии диалога больше не трогает реестр
        self.autostart.clicked.connect(settings.set_autostart)
        layout.addWidget(self.autostart)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


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
        self._setup_shortcuts()
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

    def _setup_shortcuts(self):
        """Настройка глобальных горячих клавиш"""
        self.hotkeys.install(self.app)
        # Создание новой заметки: Ctrl+Shift+N
        self._add_app_shortcut('new_note', "Ctrl+Shift+N", self.manager.create_note)
        # Показать/скрыть все заметки: Ctrl+Shift+H
        self._add_app_shortcut(
            'toggle_visibility', "Ctrl+Shift+H", self._toggle_all_notes_visibility
        )
        if self.hotkeys.failed:
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

        action_new = menu.addAction("+ Новая заметка\tCtrl+Shift+N")
        action_new.triggered.connect(self.manager.create_note)

        action_show_one = menu.addAction("Показать одну")
        action_show_one.triggered.connect(self.manager.show_one)

        menu.addSeparator()

        action_show = menu.addAction("Показать/скрыть все\tCtrl+Shift+H")
        action_show.triggered.connect(self._toggle_all_notes_visibility)

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
        SettingsDialog(self.settings).exec()

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
