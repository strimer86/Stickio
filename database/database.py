import logging
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime

from models.note import (
    Note, DEFAULT_BACKGROUND, DEFAULT_TEXT_COLOR, DEFAULT_FONT_SIZE,
    DEFAULT_OPACITY, DEFAULT_WIDTH, DEFAULT_HEIGHT,
)

logger = logging.getLogger(__name__)

BACKUP_INTERVAL_HOURS = 6
# Глубина истории: .bak.1 — свежий, .bak.N — самый старый.
BACKUP_GENERATIONS = 5
BACKUP_SUFFIX = ".bak"


class DatabaseClosedError(RuntimeError):
    """Соединение уже закрыто — вызов после Database.close().

    Отдельный тип нужен, чтобы вызывающий код мог отличить «база закрыта»
    от настоящей ошибки SQLite: такие вызовы безопасно игнорировать при
    завершении приложения.
    """


def _default_db_path() -> str:
    """Возвращает путь к файлу базы данных."""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Stickio")
    else:
        base = os.path.join(os.path.dirname(__file__), "..", "data")
    return os.path.join(base, "notes.db")


DB_PATH = _default_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT DEFAULT '',
    background_color TEXT DEFAULT '#FFF4A8',
    text_color TEXT DEFAULT '#222222',
    font_size INTEGER DEFAULT 18,
    bold INTEGER DEFAULT 0,
    opacity REAL DEFAULT 1.0,
    x INTEGER DEFAULT 120,
    y INTEGER DEFAULT 120,
    width INTEGER DEFAULT 380,
    height INTEGER DEFAULT 300
)
"""

# Миграции для старых БД: колонка добавляется, только если отсутствует.
_MIGRATIONS = {
    "opacity": "ALTER TABLE notes ADD COLUMN opacity REAL DEFAULT 1.0",
    "x": "ALTER TABLE notes ADD COLUMN x INTEGER DEFAULT 120",
    "y": "ALTER TABLE notes ADD COLUMN y INTEGER DEFAULT 120",
    "width": "ALTER TABLE notes ADD COLUMN width INTEGER DEFAULT 380",
    "height": "ALTER TABLE notes ADD COLUMN height INTEGER DEFAULT 300",
    "background_color": "ALTER TABLE notes ADD COLUMN background_color TEXT DEFAULT '#FFF4A8'",
    "text_color": "ALTER TABLE notes ADD COLUMN text_color TEXT DEFAULT '#222222'",
    "font_size": "ALTER TABLE notes ADD COLUMN font_size INTEGER DEFAULT 18",
    "bold": "ALTER TABLE notes ADD COLUMN bold INTEGER DEFAULT 0",
    "content": "ALTER TABLE notes ADD COLUMN content TEXT DEFAULT ''",
}

# Колонки, которые можно задать при создании заметки. Список берётся из
# миграций, а не дублируется: добавили колонку — она сразу доступна и в
# INSERT, и в миграции, и расхождение между ними невозможно.
NOTE_COLUMNS = frozenset(_MIGRATIONS)


class Database:
    """Класс для работы с базой данных заметок.

    Использует одно долгоживущее соединение; блокировка остаётся на случай,
    если методы когда-нибудь позовут из другого потока.
    """

    def __init__(self, path=None):
        """Инициализирует соединение с базой данных.

        Args:
            path: Путь к файлу базы данных (по умолчанию — DB_PATH на момент
                вызова; параметр оставлен переопределяемым для тестов)
        """
        self.path = path if path is not None else DB_PATH
        self._lock = threading.Lock()
        self._conn = None
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except OSError as e:
            logger.error("Failed to create database directory: %s", e)
            raise
        try:
            self._conn = self._connect()
            self._init_db()
        except sqlite3.Error:
            # Критично: без рабочей БД приложение запускать нельзя.
            self.close()
            raise
        self._maybe_backup()

    def _connect(self) -> sqlite3.Connection:
        """Создает соединение с базой данных."""
        try:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # WAL: запись не блокирует чтение, коммиты заметно дешевле —
            # autosave на каждый чих больше не подтормаживает UI.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            return conn
        except sqlite3.Error as e:
            logger.error("Failed to connect to database: %s", e)
            raise

    def _ensure_conn(self) -> sqlite3.Connection:
        """Возвращает живое соединение или падает понятной ошибкой.

        Раньше после close() каждый метод падал с AttributeError
        ('NoneType' has no attribute 'execute'), который не ловился
        блоками `except sqlite3.Error` и утекал в UI как загадочный сбой.
        """
        if self._conn is None:
            raise DatabaseClosedError(
                "Database connection is closed (path=%s)" % self.path
            )
        return self._conn

    def _init_db(self):
        """Инициализирует структуру базы данных одной транзакцией.

        CREATE TABLE и все миграции либо применяются целиком, либо
        откатываются — пустая «полузаписанная» база на диске не останется.
        """
        with self._lock, self._ensure_conn() as conn:
            conn.execute(SCHEMA)
            cols = {
                row[1] for row in
                conn.execute("PRAGMA table_info(notes)").fetchall()
            }
            for col, sql in _MIGRATIONS.items():
                if col not in cols:
                    logger.info("Migrating database: adding column '%s'", col)
                    conn.execute(sql)

    def _maybe_backup(self, force: bool = False):
        """Сохраняет резервную копию notes.db → notes.db.bak.N.

        Интервал — BACKUP_INTERVAL_HOURS, история — BACKUP_GENERATIONS
        поколений. Используется sqlite3-backup API, корректный при активном
        журнале. Ошибка бэкапа не критична и не мешает работе приложения.

        Args:
            force: сделать копию немедленно, не глядя на возраст последней
                (нужно при выходе, когда интервал ещё не истёк, а данные
                с момента прошлого бэкапа уже накопились).
        """
        backup_path = self.path + BACKUP_SUFFIX + ".1"
        try:
            if not os.path.exists(self.path):
                return
            if not force and os.path.exists(backup_path):
                age = time.time() - os.path.getmtime(backup_path)
                if age < BACKUP_INTERVAL_HOURS * 3600:
                    return
            with self._lock:
                self._rotate_backups()
                # Пишем во временный файл и заменяем атомарно: sqlite backup API
                # не перезаписывает файл с идентичным содержимым, а прямой
                # записи в существующий .bak недостаточно для ротации.
                tmp_path = backup_path + ".tmp"
                dst = sqlite3.connect(tmp_path)
                try:
                    with dst:
                        self._ensure_conn().backup(dst)
                finally:
                    dst.close()
                os.replace(tmp_path, backup_path)
            logger.info(
                "Database backup created: %s (%s)",
                backup_path, datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        except (sqlite3.Error, OSError):
            logger.exception("Database backup failed (non-fatal)")

    def _rotate_backups(self):
        """Сдвигает .bak.1 → .bak.2 → … → .bak.N, самый старый удаляется.

        Раньше было только одно поколение (.old), поэтому история не
        простиралась дальше суток — при порче данных откатываться было некуда.
        """
        # Файлы от старой схемы (.bak без номера, .bak.old) больше не нужны:
        # их не читает ни один код, а место они занимают.
        for legacy in (self.path + BACKUP_SUFFIX, self.path + BACKUP_SUFFIX + ".old"):
            if os.path.exists(legacy):
                try:
                    os.remove(legacy)
                    logger.info("Removed legacy backup %s", legacy)
                except OSError:
                    logger.warning("Failed to remove legacy backup %s", legacy)

        oldest = "%s.%d" % (self.path + BACKUP_SUFFIX, BACKUP_GENERATIONS)
        if os.path.exists(oldest):
            try:
                os.remove(oldest)
            except OSError:
                logger.warning("Failed to remove oldest backup %s", oldest)

        for gen in range(BACKUP_GENERATIONS - 1, 0, -1):
            src = "%s.%d" % (self.path + BACKUP_SUFFIX, gen)
            dst = "%s.%d" % (self.path + BACKUP_SUFFIX, gen + 1)
            if os.path.exists(src):
                os.replace(src, dst)

    def close(self):
        """Сохраняет свежий бэкап и закрывает соединение. Идемпотентно.

        При завершении приложения close() приходит из нескольких мест
        (quit(), aboutToQuit, commitDataRequest) — падать на втором вызове
        или писать в мёртвое соединение нельзя.
        """
        with self._lock:
            if self._conn is None:
                return
        # Бэкап до закрытия: если приложение работало дольше интервала,
        # последние правки иначе не попали бы ни в одну копию.
        try:
            self._maybe_backup(force=True)
        except Exception:
            logger.exception("Final backup before close failed (non-fatal)")

        with self._lock:
            if self._conn is None:
                return
            conn, self._conn = self._conn, None
        try:
            conn.close()
        except sqlite3.Error:
            logger.exception("Failed to close database connection")

    def create_note(self, **fields) -> int:
        """Создает новую заметку в базе данных.

        Args:
            **fields: значения колонок для новой заметки (цвет фона, размер
                шрифта и т.д.). Без аргументов работает как раньше —
                `INSERT DEFAULT VALUES`, и SQLite подставит свои умолчания.

        Returns:
            ID созданной заметки
        """
        unknown = set(fields) - NOTE_COLUMNS
        if unknown:
            raise ValueError("Неизвестные колонки заметки: %s" % ", ".join(sorted(unknown)))

        if fields:
            # Порядок колонок фиксируем сортировкой: иначе SQL и кортеж
            # параметров собирались бы в произвольном порядке словаря.
            columns = sorted(fields)
            sql = "INSERT INTO notes (%s) VALUES (%s)" % (
                ", ".join(columns),
                ", ".join("?" for _ in columns),
            )
            params = tuple(fields[name] for name in columns)
        else:
            sql = "INSERT INTO notes DEFAULT VALUES"
            params = ()

        with self._lock:
            try:
                conn = self._ensure_conn()
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.lastrowid
            except sqlite3.Error as e:
                logger.error("Failed to create note: %s", e)
                raise

    def save_note(self, note: Note):
        """Сохраняет изменения заметки в базе данных.

        Args:
            note: Объект заметки для сохранения
        """
        with self._lock:
            try:
                conn = self._ensure_conn()
                conn.execute(
                    """UPDATE notes SET
                           content = ?, background_color = ?, text_color = ?,
                           font_size = ?, bold = ?, opacity = ?,
                           x = ?, y = ?, width = ?, height = ?
                       WHERE id = ?""",
                    (
                        note.content, note.background_color, note.text_color,
                        note.font_size, int(note.bold), note.opacity,
                        note.x, note.y, note.width, note.height,
                        note.id,
                    ),
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error("Failed to save note %s: %s", note.id, e)
                raise

    def get_note(self, note_id: int) -> Note | None:
        """Получает заметку по ID.

        Args:
            note_id: ID заметки

        Returns:
            Объект заметки или None, если не найдена
        """
        with self._lock:
            try:
                row = self._ensure_conn().execute(
                    "SELECT * FROM notes WHERE id = ?", (note_id,)
                ).fetchone()
            except sqlite3.Error as e:
                logger.error("Failed to get note %s: %s", note_id, e)
                raise
        return self._row_to_note(row) if row else None

    def get_all_notes(self) -> list[Note]:
        """Получает все заметки из базы данных (в стабильном порядке).

        Returns:
            Список всех заметок
        """
        with self._lock:
            try:
                rows = self._ensure_conn().execute(
                    "SELECT * FROM notes ORDER BY id"
                ).fetchall()
            except sqlite3.Error as e:
                logger.error("Failed to get all notes: %s", e)
                raise
        return [self._row_to_note(r) for r in rows]

    def delete_note(self, note_id: int):
        """Удаляет заметку из базы данных.

        Args:
            note_id: ID заметки для удаления
        """
        with self._lock:
            try:
                conn = self._ensure_conn()
                conn.execute(
                    "DELETE FROM notes WHERE id = ?", (note_id,)
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error("Failed to delete note %s: %s", note_id, e)
                raise

    @staticmethod
    def _row_to_note(row) -> Note:
        """Преобразует строку базы данных в объект Note."""
        keys = row.keys()
        return Note(
            id=row["id"] if "id" in keys else None,
            content=row["content"] if "content" in keys else "",
            background_color=(
                row["background_color"] if "background_color" in keys
                else DEFAULT_BACKGROUND
            ),
            text_color=(
                row["text_color"] if "text_color" in keys
                else DEFAULT_TEXT_COLOR
            ),
            font_size=(
                row["font_size"] if "font_size" in keys and row["font_size"] is not None
                else DEFAULT_FONT_SIZE
            ),
            bold=bool(row["bold"]) if "bold" in keys and row["bold"] is not None else False,
            opacity=(
                float(row["opacity"]) if "opacity" in keys and row["opacity"] is not None
                else DEFAULT_OPACITY
            ),
            x=int(row["x"]) if "x" in keys and row["x"] is not None else 120,
            y=int(row["y"]) if "y" in keys and row["y"] is not None else 120,
            width=(
                int(row["width"]) if "width" in keys and row["width"] is not None
                else DEFAULT_WIDTH
            ),
            height=(
                int(row["height"]) if "height" in keys and row["height"] is not None
                else DEFAULT_HEIGHT
            ),
        )
