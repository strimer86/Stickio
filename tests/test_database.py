"""Юнит-тесты Database: CRUD, бэкапы, миграции старых схем.

Запуск:  python -m unittest discover -s tests -v
"""
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from database.database import Database, DatabaseClosedError
from models.note import DEFAULT_BACKGROUND


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stickio_test_")
        self.path = os.path.join(self.tmp, "notes.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_crud_roundtrip(self):
        db = Database(self.path)
        try:
            note_id = db.create_note()
            note = db.get_note(note_id)
            self.assertIsNotNone(note)

            note.content = "<p>привет</p>"
            note.x, note.y = 11, 22
            note.opacity = 0.5
            db.save_note(note)

            loaded = db.get_note(note_id)
            self.assertEqual(loaded.content, "<p>привет</p>")
            self.assertEqual((loaded.x, loaded.y), (11, 22))
            self.assertAlmostEqual(loaded.opacity, 0.5)

            db.delete_note(note_id)
            self.assertIsNone(db.get_note(note_id))
        finally:
            db.close()

    def test_load_order_is_stable(self):
        db = Database(self.path)
        try:
            ids = [db.create_note() for _ in range(3)]
            self.assertEqual([n.id for n in db.get_all_notes()], ids)
        finally:
            db.close()

    def test_backup_created_and_rotated(self):
        db = Database(self.path)
        db.close()  # первая инициализация: sqlite создаёт файл, .bak.1 появляется сразу
        first = self.path + ".bak.1"
        self.assertTrue(os.path.exists(first))
        first_mtime = os.path.getmtime(first)

        # «состариваем» бэкап — следующая инициализация делает ротацию
        stale = time.time() - 25 * 3600
        os.utime(first, (stale, stale))
        db = Database(self.path)
        db.close()

        self.assertTrue(os.path.exists(self.path + ".bak.1"))
        self.assertTrue(os.path.exists(self.path + ".bak.2"))
        # свежий .bak.1 новее того, что уехал в .bak.2
        self.assertGreater(os.path.getmtime(first), first_mtime)

    def test_backup_history_generations(self):
        """История копится до BACKUP_GENERATIONS, самый старый вытесняется."""
        from database.database import BACKUP_GENERATIONS

        for _ in range(BACKUP_GENERATIONS + 2):
            db = Database(self.path)
            db.close()
            # состариваем все копии, чтобы следующая инициализация не пропустила бэкап
            stale = time.time() - 25 * 3600
            for gen in range(1, BACKUP_GENERATIONS + 1):
                p = "%s.bak.%d" % (self.path, gen)
                if os.path.exists(p):
                    os.utime(p, (stale, stale))

        for gen in range(1, BACKUP_GENERATIONS + 1):
            self.assertTrue(
                os.path.exists("%s.bak.%d" % (self.path, gen)),
                "нет поколения .bak.%d" % gen,
            )
        self.assertFalse(
            os.path.exists("%s.bak.%d" % (self.path, BACKUP_GENERATIONS + 1)),
            "поколений больше, чем BACKUP_GENERATIONS",
        )

    def test_close_creates_fresh_backup(self):
        """close() форсирует бэкап: последние правки не должны потеряться."""
        db = Database(self.path)
        note_id = db.create_note()
        note = db.get_note(note_id)
        note.content = "<p>правка перед выходом</p>"
        db.save_note(note)

        # делаем свежий бэкап «старым», чтобы интервал точно истёк
        newest = self.path + ".bak.1"
        if os.path.exists(newest):
            stale = time.time() - 25 * 3600
            os.utime(newest, (stale, stale))

        db.close()

        self.assertTrue(os.path.exists(newest))
        # содержимое бэкапа содержит последнюю правку
        conn = sqlite3.connect(newest)
        try:
            content = conn.execute(
                "SELECT content FROM notes WHERE id = ?", (note_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertIn("правка перед выходом", content)

    def test_backup_skipped_within_interval(self):
        db = Database(self.path)
        db.close()
        newest = self.path + ".bak.1"
        # бэкапу 1 час (< 6ч) — повторная инициализация не должна его трогать
        fresh = time.time() - 3600
        os.utime(newest, (fresh, fresh))
        db = Database(self.path)
        # закрываем без форсированного бэкапа: проверяем именно _maybe_backup при старте
        with db._lock:
            conn, db._conn = db._conn, None
        conn.close()
        self.assertEqual(os.path.getmtime(newest), fresh)

    def test_migration_adds_missing_columns(self):
        # имитируем старую схему только с id/content
        conn = sqlite3.connect(self.path)
        conn.execute(
            "CREATE TABLE notes ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " content TEXT DEFAULT '')"
        )
        conn.execute("INSERT INTO notes (content) VALUES ('старая заметка')")
        conn.commit()
        conn.close()

        db = Database(self.path)
        try:
            notes = db.get_all_notes()
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0].content, "старая заметка")
            # отсутствовавшие колонки получают дефолты
            self.assertEqual(notes[0].background_color, DEFAULT_BACKGROUND)
            self.assertEqual(notes[0].x, 120)
            self.assertAlmostEqual(notes[0].opacity, 1.0)
        finally:
            db.close()

    def test_old_pinned_column_is_ignored(self):
        # БД из прошлой версии: колонка pinned есть, новый код её не читает
        conn = sqlite3.connect(self.path)
        conn.execute(
            "CREATE TABLE notes ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " content TEXT DEFAULT '',"
            " background_color TEXT DEFAULT '#FFF4A8',"
            " text_color TEXT DEFAULT '#222222',"
            " font_size INTEGER DEFAULT 18,"
            " bold INTEGER DEFAULT 0,"
            " pinned INTEGER DEFAULT 1,"
            " opacity REAL DEFAULT 1.0,"
            " x INTEGER DEFAULT 120, y INTEGER DEFAULT 120,"
            " width INTEGER DEFAULT 380, height INTEGER DEFAULT 300)"
        )
        conn.execute("INSERT INTO notes (content, pinned) VALUES ('с pinned', 0)")
        conn.commit()
        conn.close()

        db = Database(self.path)
        try:
            notes = db.get_all_notes()
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0].content, "с pinned")
            # save_note не должен падать из-за лишней колонки в таблице
            notes[0].content = "обновлено"
            db.save_note(notes[0])
            self.assertEqual(db.get_all_notes()[0].content, "обновлено")
        finally:
            db.close()


    def test_close_is_idempotent(self):
        db = Database(self.path)
        db.close()
        # повторные вызовы приходят из quit()/aboutToQuit/commitDataRequest
        db.close()
        db.close()

    def test_operations_after_close_raise_domain_error(self):
        """После close() методы дают DatabaseClosedError, а не AttributeError.

        Раньше это был AttributeError на None, который не ловился
        `except sqlite3.Error` и утекал в UI загадочным сбоем сохранения.
        """
        db = Database(self.path)
        note_id = db.create_note()
        note = db.get_note(note_id)
        db.close()

        with self.assertRaises(DatabaseClosedError):
            db.save_note(note)
        with self.assertRaises(DatabaseClosedError):
            db.get_note(note_id)
        with self.assertRaises(DatabaseClosedError):
            db.get_all_notes()
        with self.assertRaises(DatabaseClosedError):
            db.create_note()
        with self.assertRaises(DatabaseClosedError):
            db.delete_note(note_id)

    def test_close_does_not_lose_saved_data(self):
        """Acceptance: данные, сохранённые до close(), читаются после reopen."""
        db = Database(self.path)
        note_id = db.create_note()
        note = db.get_note(note_id)
        note.content = "<p>важное</p>"
        note.x, note.y = 42, 43
        db.save_note(note)
        db.close()

        db = Database(self.path)
        try:
            loaded = db.get_note(note_id)
            self.assertEqual(loaded.content, "<p>важное</p>")
            self.assertEqual((loaded.x, loaded.y), (42, 43))
        finally:
            db.close()

    def test_legacy_backups_removed(self):
        """Файлы старой схемы (.bak без номера, .bak.old) убираются при ротации."""
        for legacy in (".bak", ".bak.old"):
            with open(self.path + legacy, "w") as fh:
                fh.write("legacy")
            self.assertTrue(os.path.exists(self.path + legacy))

        db = Database(self.path)
        db.close()

        for legacy in (".bak", ".bak.old"):
            self.assertFalse(
                os.path.exists(self.path + legacy),
                "старый бэкап %s не удалён" % legacy,
            )
        self.assertTrue(os.path.exists(self.path + ".bak.1"))

    def test_wal_mode_enabled(self):
        """WAL нужен, чтобы autosave не блокировал UI-поток."""
        db = Database(self.path)
        try:
            mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
