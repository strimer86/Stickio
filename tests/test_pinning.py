"""Тесты закрепления заметки поверх всех окон.

Разделены на две части намеренно:

* расчёт стилей — чистые функции, окно не нужно;
* работа с базой — флаг должен переживать перезапуск.

Вызовы Win32 отдельно не проверяются: они требуют настоящего окна и
меняют состояние системы. Проверено пробой вручную (см. traps.md), а
здесь проверяется вся логика вокруг, чтобы ошибиться было негде.
"""
import os
import shutil
import sqlite3
import tempfile
import unittest

from database.database import Database
from models.note import Note
from services import pinning


class ExstyleCalculationTests(unittest.TestCase):
    """Расчёт расширенных стилей: числа на входе, числа на выходе."""

    def test_pinned_adds_both_flags(self):
        """Закрепление — это всегда два флага, а не один.

        TOPMOST без NOACTIVATE дал бы окно поверх всех, но клик по нему
        отобрал бы фокус у активной программы. Именно ради второго флага
        и затевался весь модуль.
        """
        style = pinning.pinned_exstyle(0)
        self.assertTrue(style & pinning.WS_EX_TOPMOST)
        self.assertTrue(style & pinning.WS_EX_NOACTIVATE)

    def test_unpinned_removes_both_flags(self):
        style = pinning.unpinned_exstyle(
            pinning.WS_EX_TOPMOST | pinning.WS_EX_NOACTIVATE | 0x40000
        )
        self.assertFalse(style & pinning.WS_EX_TOPMOST)
        self.assertFalse(style & pinning.WS_EX_NOACTIVATE)
        # чужие флаги трогать нельзя — окно может быть, например, всплывающим
        self.assertTrue(style & 0x40000)

    def test_editable_keeps_topmost_but_allows_activation(self):
        """Во время набора окно остаётся поверх всех, но его можно активировать.

        Иначе клавиатура не дойдёт до редактора: окно с NOACTIVATE не
        получает WM_KEYDOWN — это проверено пробой, а не взятo из документации.
        """
        style = pinning.editable_exstyle(pinning.WS_EX_NOACTIVATE)
        self.assertTrue(style & pinning.WS_EX_TOPMOST)
        self.assertFalse(style & pinning.WS_EX_NOACTIVATE)

    def test_pinned_is_not_activatable(self):
        self.assertFalse(pinning.is_activatable(pinning.pinned_exstyle(0)))

    def test_unpinned_is_activatable(self):
        self.assertTrue(pinning.is_activatable(pinning.unpinned_exstyle(0)))

    def test_is_pinned_detects_flag(self):
        self.assertTrue(pinning.is_pinned(pinning.WS_EX_TOPMOST))
        self.assertFalse(pinning.is_pinned(pinning.WS_EX_NOACTIVATE))

    def test_roundtrip_leaves_no_residue(self):
        """Закрепили — открепили: от исходного стиля ничего не осталось."""
        original = 0x40000 | 0x80
        self.assertEqual(
            pinning.unpinned_exstyle(pinning.pinned_exstyle(original)),
            original,
        )

    def test_editable_after_unpinned_stays_pinnable(self):
        """Из состояния «набираю» можно вернуться в закреплённое."""
        style = pinning.pinned_exstyle(pinning.editable_exstyle(0))
        self.assertTrue(pinning.is_pinned(style))
        self.assertFalse(pinning.is_activatable(style))


class PersistenceTests(unittest.TestCase):
    """Флаг закрепления должен переживать перезапуск приложения."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stickio_pin_")
        self.path = os.path.join(self.tmp, "notes.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_is_not_pinned(self):
        """Новая заметка не закреплена.

        Иначе после обновления все стикеры разом полезли бы поверх чужих
        окон — это сломало бы привычное поведение без спроса.
        """
        db = Database(self.path)
        try:
            note_id = db.create_note()
            self.assertFalse(db.get_note(note_id).always_on_top)
        finally:
            db.close()

    def test_flag_survives_reopen(self):
        db = Database(self.path)
        try:
            note_id = db.create_note()
            note = db.get_note(note_id)
            note.always_on_top = True
            db.save_note(note)
        finally:
            db.close()

        reopened = Database(self.path)
        try:
            self.assertTrue(reopened.get_note(note_id).always_on_top)
        finally:
            reopened.close()

    def test_flag_can_be_cleared(self):
        db = Database(self.path)
        try:
            note_id = db.create_note()
            note = db.get_note(note_id)
            note.always_on_top = True
            db.save_note(note)

            note.always_on_top = False
            db.save_note(note)
            self.assertFalse(db.get_note(note_id).always_on_top)
        finally:
            db.close()

    def test_column_is_added_to_old_database(self):
        """Старая база без колонки должна её получить, а не упасть."""
        conn = sqlite3.connect(self.path)
        conn.execute(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " content TEXT DEFAULT '')"
        )
        conn.commit()
        conn.close()

        db = Database(self.path)
        try:
            note_id = db.create_note()
            note = db.get_note(note_id)
            note.always_on_top = True
            db.save_note(note)
            self.assertTrue(db.get_note(note_id).always_on_top)
        finally:
            db.close()

    def test_migration_is_idempotent(self):
        """Второй запуск по той же базе не должен ломать данные."""
        db = Database(self.path)
        try:
            note_id = db.create_note()
            note = db.get_note(note_id)
            note.always_on_top = True
            db.save_note(note)
        finally:
            db.close()

        for _ in range(3):
            again = Database(self.path)
            try:
                self.assertTrue(again.get_note(note_id).always_on_top)
            finally:
                again.close()

    def test_model_default_matches_database(self):
        """Расхождение дефолтов модели и базы даёт «фантомное» закрепление."""
        self.assertFalse(Note().always_on_top)
        db = Database(self.path)
        try:
            self.assertFalse(db.get_note(db.create_note()).always_on_top)
        finally:
            db.close()


class UnsupportedPlatformTests(unittest.TestCase):
    """На не-Windows модуль не должен падать при импорте и вызовах."""

    def test_get_exstyle_without_hwnd_is_safe(self):
        """Нет hwnd — нет и стиля, вместо обращения к Win32."""
        self.assertEqual(pinning.get_exstyle(0), 0)

    def test_set_exstyle_without_hwnd_is_safe(self):
        self.assertFalse(pinning.set_exstyle(0, pinning.WS_EX_TOPMOST))


if __name__ == "__main__":
    unittest.main()
