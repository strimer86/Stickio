import ctypes
import logging
import os
import sys

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication, QMessageBox

import logging_config

logger = logging.getLogger(__name__)


def translation_dirs() -> list:
    """Каталоги, где ищем qtbase_ru.qm.

    В собранном приложении `QLibraryInfo` обычно отдаёт путь, которого рядом
    с exe нет, поэтому вторым кандидатом идёт распакованная PySide6 — именно
    туда PyInstaller кладёт translations, если они добавлены в .spec.
    """
    dirs = []
    try:
        dirs.append(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    except Exception:
        logger.exception("Failed to locate Qt translations path")

    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.append(os.path.join(base, "PySide6", "translations"))
    return dirs


def install_translator(app: QApplication):
    """Подключает русский перевод служебных строк Qt.

    Без него английскими остаются диалог выбора цвета, кнопки QMessageBox
    и стандартное меню редактора — всё, чего нет в нашем коде. Перевод не
    обязателен для работы: если .qm не нашёлся (сборка без translations),
    приложение просто остаётся со строками Qt по умолчанию.
    """
    translator = QTranslator(app)
    for directory in translation_dirs():
        if translator.load("qtbase_ru", directory):
            app.installTranslator(translator)
            logger.info("Qt translation loaded from %s", directory)
            return translator
    logger.info("Qt translation not found in %s", translation_dirs())
    return None


def set_app_user_model_id():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Stickio.App"
        )
    except Exception:
        logger.exception("Failed to set AppUserModelID")


class SingleInstanceChecker:
    def __init__(self, app_key="stickio_app_unique_key"):
        self.app_key = app_key
        self._mutex_handle = None

        if sys.platform != "win32":
            self.is_running = False
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_bool
        self._kernel32 = kernel32

        # Именованный мьютекс создаётся Windows атомарно: два процесса не
        # смогут одновременно решить, что они первые.
        self._mutex_handle = kernel32.CreateMutexW(
            None, False, f"Local\\{app_key}"
        )
        if not self._mutex_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.is_running = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS

    def close(self):
        if self._mutex_handle:
            self._kernel32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None


def main():
    logging_config.setup_logging()

    app = QApplication(sys.argv)
    install_translator(app)

    try:
        app_checker = SingleInstanceChecker()
    except OSError:
        logger.exception("Failed to create single-instance mutex")
        QMessageBox.critical(
            None, "Stickio", "Не удалось запустить приложение (мьютекс)."
        )
        return 1

    try:
        if app_checker.is_running:
            logger.info("Stickio already running — second instance exits")
            return 0

        set_app_user_model_id()

        from widgets.sticky_note import load_app_icon
        load_app_icon()

        from app import App

        app.setApplicationName("Stickio")
        app.setOrganizationName("Stickio")
        app.setQuitOnLastWindowClosed(False)

        try:
            app_instance = App(app)
            app_instance.start()
        except Exception:
            logger.exception("Failed to initialize application")
            QMessageBox.critical(
                None, "Stickio",
                "Не удалось запустить приложение.\n"
                "Подробности — в журнале logs/stickio.log.",
            )
            return 1

        return app.exec()
    finally:
        app_checker.close()


if __name__ == "__main__":
    sys.exit(main())
