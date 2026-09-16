"""Тесты настроек заметки: вид новой заметки и подтверждение удаления.

Ключевая проверка — сквозная: значение из настроек должно дойти до строки
в базе. Без неё легко сделать настройку, которая сохраняется, но ни на что
не влияет.
"""
import os
import shutil
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMessageBox

from database.database import Database, NOTE_COLUMNS
from services.note_manager import NoteManager
from services.settings import (
    DEFAULT_NOTE_SETTINGS, FONT_SIZE_RANGE, Settings,
)

_app = QApplication.instance() or QApplication([])


class CreateNoteWithFieldsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stickio_notefields_")
        self.db = Database(os.path.join(self.tmp, "notes.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_without_arguments_keeps_db_defaults(self):
        note = self.db.get_note(self.db.create_note())
        self.assertEqual(note.background_color, DEFAULT_NOTE_SETTINGS["background_color"])
        self.assertEqual(note.font_size, DEFAULT_NOTE_SETTINGS["font_size"])

    def test_fields_are_applied(self):
        note_id = self.db.create_note(
            background_color="#123456", text_color="#abcdef", font_size=42
        )
        note = self.db.get_note(note_id)
        self.assertEqual(note.background_color, "#123456")
        self.assertEqual(note.text_color, "#abcdef")
        self.assertEqual(note.font_size, 42)

    def test_unknown_column_refused(self):
        with self.assertRaises(ValueError):
            self.db.create_note(no_such_column=1)

    def test_every_allowed_column_really_exists(self):
        """NOTE_COLUMNS собраны из миграций — проверяем, что они в схеме."""
        row = self.db._ensure_conn().execute("PRAGMA table_info(notes)").fetchall()
        self.assertEqual(set(NOTE_COLUMNS), {r[1] for r in row} - {"id"})


class NoteDefaultsTests(unittest.TestCase):
    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("NoteDefaultsTests")
        self.settings = Settings()
        self.settings.settings.clear()

    def tearDown(self):
        self.settings.settings.clear()

    def test_defaults_when_nothing_saved(self):
        self.assertEqual(self.settings.note_defaults(), DEFAULT_NOTE_SETTINGS)

    def test_roundtrip(self):
        self.settings.set_note_defaults(
            {"background_color": "#123456", "text_color": "#111111", "font_size": 30}
        )
        saved = self.settings.note_defaults()
        self.assertEqual(saved["background_color"], "#123456")
        self.assertEqual(saved["font_size"], 30)

    def test_font_size_stays_int(self):
        """Иначе размер шрифта приходил бы строкой и ломался бы в QSpinBox."""
        self.settings.set_note_defaults({"font_size": 24})
        self.assertIsInstance(self.settings.note_defaults()["font_size"], int)

    def test_corrupt_values_fall_back_to_default(self):
        self.settings.settings.setValue("note/font_size", "не число")
        self.settings.settings.setValue("note/background_color", "не цвет")
        saved = self.settings.note_defaults()
        self.assertEqual(saved["font_size"], DEFAULT_NOTE_SETTINGS["font_size"])
        self.assertEqual(
            saved["background_color"], DEFAULT_NOTE_SETTINGS["background_color"]
        )

    def test_font_size_out_of_range_falls_back(self):
        low, high = FONT_SIZE_RANGE
        self.settings.set_note_defaults({"font_size": high + 100})
        self.assertEqual(
            self.settings.note_defaults()["font_size"],
            DEFAULT_NOTE_SETTINGS["font_size"],
        )
        self.settings.set_note_defaults({"font_size": low - 1})
        self.assertEqual(
            self.settings.note_defaults()["font_size"],
            DEFAULT_NOTE_SETTINGS["font_size"],
        )

    def test_confirm_delete_defaults_to_true(self):
        self.assertTrue(self.settings.confirm_delete())

    def test_confirm_delete_roundtrip(self):
        self.settings.set_confirm_delete(False)
        self.assertFalse(self.settings.confirm_delete())


class NewNoteUsesSettingsTests(unittest.TestCase):
    """Сквозная проверка: настройки -> база -> окно заметки."""

    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("NewNoteUsesSettingsTests")
        self.settings = Settings()
        self.settings.settings.clear()
        self.tmp = tempfile.mkdtemp(prefix="stickio_newnote_")
        self.db = Database(os.path.join(self.tmp, "notes.db"))

    def tearDown(self):
        self.settings.settings.clear()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_note_gets_settings(self):
        self.settings.set_note_defaults(
            {"background_color": "#AABBCC", "text_color": "#102030", "font_size": 27}
        )
        manager = NoteManager(self.db, settings=self.settings)
        try:
            window = manager.create_note()
            self.assertEqual(window.note.background_color, "#AABBCC")
            self.assertEqual(window.note.text_color, "#102030")
            self.assertEqual(window.note.font_size, 27)
        finally:
            manager.close_all()

    def test_existing_note_is_not_repainted(self):
        """Настройки не должны перекрашивать уже сохранённые заметки."""
        note_id = self.db.create_note(background_color="#111111")
        self.settings.set_note_defaults({"background_color": "#AABBCC"})
        manager = NoteManager(self.db, settings=self.settings)
        try:
            manager.load_all()
            self.assertEqual(
                manager.windows[note_id].note.background_color, "#111111"
            )
        finally:
            manager.close_all()

    def test_confirm_delete_reaches_window(self):
        self.settings.set_confirm_delete(False)
        manager = NoteManager(self.db, settings=self.settings)
        try:
            window = manager.create_note()
            self.assertFalse(window.settings.confirm_delete())
        finally:
            manager.close_all()


class SettingsDialogNoteTests(unittest.TestCase):
    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("SettingsDialogNoteTests")
        self.settings = Settings()
        self.settings.settings.clear()
        self._orig_warning = QMessageBox.warning
        QMessageBox.warning = staticmethod(lambda *args, **kwargs: None)

    def tearDown(self):
        QMessageBox.warning = self._orig_warning
        self.settings.settings.clear()

    def _dialog(self):
        from app import SettingsDialog

        return SettingsDialog(self.settings)

    def test_controls_show_saved_values(self):
        self.settings.set_note_defaults({"font_size": 33})
        dialog = self._dialog()
        self.assertEqual(dialog.font_size_spin.value(), 33)

    def test_accept_stores_note_settings(self):
        dialog = self._dialog()
        dialog.background_button.set_color(QColor("#123456"))
        dialog.text_button.set_color(QColor("#654321"))
        dialog.font_size_spin.setValue(41)
        dialog._accept()
        saved = self.settings.note_defaults()
        self.assertEqual(saved["background_color"], "#123456")
        self.assertEqual(saved["text_color"], "#654321")
        self.assertEqual(saved["font_size"], 41)

    def test_restore_defaults_resets_everything(self):
        dialog = self._dialog()
        dialog.font_size_spin.setValue(41)
        dialog.confirm_delete.setChecked(False)
        dialog.background_button.set_color(QColor("#123456"))
        dialog._restore_defaults()
        self.assertEqual(
            dialog.font_size_spin.value(), DEFAULT_NOTE_SETTINGS["font_size"]
        )
        self.assertTrue(dialog.confirm_delete.isChecked())
        self.assertEqual(
            dialog.background_button.color().name(),
            QColor(DEFAULT_NOTE_SETTINGS["background_color"]).name(),
        )

    def test_autostart_not_applied_until_ok(self):
        """«Отмена» обязана отменять и автозапуск, а не только хоткеи."""
        calls = []
        self.settings.set_autostart = lambda value: calls.append(value)
        dialog = self._dialog()
        dialog.autostart.setChecked(not dialog.autostart.isChecked())
        self.assertEqual(calls, [])
        dialog._accept()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
