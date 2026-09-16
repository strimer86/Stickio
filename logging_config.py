"""Централизованная настройка логирования Stickio.

Логи пишутся в файл (и в консоль, если она есть — т.е. при запуске из IDE
или терминала). В замороженном exe журнал лежит рядом с базой:
%LOCALAPPDATA%\\Stickio\\logs\\stickio.log
"""
import logging
import logging.handlers
import os
import sys

LOG_FILE_NAME = "stickio.log"
MAX_LOG_BYTES = 512 * 1024
BACKUP_COUNT = 2


def logs_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "Stickio"
        )
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "logs")


def setup_logging(level=logging.INFO):
    """Настраивает корневой логгер: ротируемый файл + консоль (если есть)."""
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:  # защита от повторной инициализации
        return

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        os.makedirs(logs_dir(), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(logs_dir(), LOG_FILE_NAME),
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as e:
        # Журнал недоступен — приложение всё равно должно запуститься.
        print(f"Warning: cannot create log file: {e}", file=sys.stderr)

    # StreamHandler имеет смысл только когда stderr существует
    # (в windowed-exe PyInstaller он подменён заглушкой/None).
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
