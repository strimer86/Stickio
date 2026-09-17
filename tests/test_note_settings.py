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
from models.note import DEFAULT_HEIGHT, DEFAULT_WIDTH
from services.note_manager import NoteManager
from services.settings import (
    DEFAULT_NOTE_SETTINGS, FONT_SIZE_RANGE, NOTE_SIZE_RANGE, Settings,
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

    def test_size_defaults_come_from_model(self):
        """Умолчание берём из модели, а не второй копией числа."""
        saved = self.settings.note_defaults()
        self.assertEqual(saved["width"], DEFAULT_WIDTH)
        self.assertEqual(saved["height"], DEFAULT_HEIGHT)

    def test_size_roundtrip(self):
        self.settings.set_note_defaults({"width": 640, "height": 480})
        saved = self.settings.note_defaults()
        self.assertEqual((saved["width"], saved["height"]), (640, 480))

    def test_size_corrupt_values_fall_back(self):
        self.settings.settings.setValue("note/width", "широкая")
        self.settings.settings.setValue("note/height", "высокая")
        saved = self.settings.note_defaults()
        self.assertEqual(saved["width"], DEFAULT_WIDTH)
        self.assertEqual(saved["height"], DEFAULT_HEIGHT)

    def test_size_out_of_range_falls_back(self):
        low, high = NOTE_SIZE_RANGE
        for bad in (high + 1, low - 1, 0, -100):
            self.settings.set_note_defaults({"width": bad, "height": bad})
            saved = self.settings.note_defaults()
            self.assertEqual(saved["width"], DEFAULT_WIDTH, "width=%r" % bad)
            self.assertEqual(saved["height"], DEFAULT_HEIGHT, "height=%r" % bad)

    def test_bool_is_not_acceptable_as_size(self):
        """`bool` — подкласс `int`, и `True` прошёл бы проверку диапазона.

        Размер заметки в 1 пиксель — заведомая поломка, поэтому True/False
        должны откатываться к умолчанию, а не подставляться как 1 и 0.
        """
        self.settings.settings.setValue("note/width", True)
        self.settings.settings.setValue("note/height", False)
        saved = self.settings.note_defaults()
        self.assertEqual(saved["width"], DEFAULT_WIDTH)
        self.assertEqual(saved["height"], DEFAULT_HEIGHT)


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

    def test_new_note_gets_configured_size(self):
        self.settings.set_note_defaults({"width": 520, "height": 420})
        manager = NoteManager(self.db, settings=self.settings)
        try:
            window = manager.create_note()
            self.assertEqual(
                (window.note.width, window.note.height), (520, 420)
            )
        finally:
            manager.close_all()

    def test_size_change_applies_to_next_note_only(self):
        """Уже созданная заметка при смене настройки не должна менять размер."""
        manager = NoteManager(self.db, settings=self.settings)
        try:
            self.settings.set_note_defaults({"width": 300, "height": 250})
            first = manager.create_note()
            self.settings.set_note_defaults({"width": 600, "height": 500})
            second = manager.create_note()
            self.assertEqual((first.note.width, first.note.height), (300, 250))
            self.assertEqual((second.note.width, second.note.height), (600, 500))
        finally:
            manager.close_all()

    def test_position_matches_configured_size(self):
        """Место ищется под ТОТ ЖЕ прямоугольник, что пишется в базу.

        Если считать позицию по константам модели, а записывать размер из
        настроек, увеличенная заметка налезет на соседнюю.

        Экран подменяем: в offscreen Qt даёт фиксированные 800x800, и две
        заметки 700x600 туда не помещаются физически — каскад честно вернёт
        последнюю проверенную позицию, и заметки перекроются независимо от
        логики. Проверять это на 800x800 бессмысленно.
        """
        from unittest.mock import patch

        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QApplication

        class FakeScreen:
            def availableGeometry(self):
                return QRect(0, 0, 1920, 1080)

        self.settings.set_note_defaults({"width": 700, "height": 600})
        manager = NoteManager(self.db, settings=self.settings)
        try:
            with patch.object(QApplication, "screenAt", return_value=FakeScreen()):
                first = manager.create_note()
                second = manager.create_note()
            for window in (first, second):
                self.assertEqual(
                    (window.note.width, window.note.height), (700, 600)
                )
            overlap = not (
                second.note.x + second.note.width <= first.note.x
                or first.note.x + first.note.width <= second.note.x
                or second.note.y + second.note.height <= first.note.y
                or first.note.y + first.note.height <= second.note.y
            )
            self.assertFalse(overlap, "заметки перекрылись при новом размере")
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
        dialog.width_spin.setValue(640)
        dialog.height_spin.setValue(480)
        dialog._accept()
        saved = self.settings.note_defaults()
        self.assertEqual(saved["background_color"], "#123456")
        self.assertEqual(saved["text_color"], "#654321")
        self.assertEqual(saved["font_size"], 41)
        self.assertEqual((saved["width"], saved["height"]), (640, 480))

    def test_size_controls_show_saved_values(self):
        self.settings.set_note_defaults({"width": 640, "height": 480})
        dialog = self._dialog()
        self.assertEqual(dialog.width_spin.value(), 640)
        self.assertEqual(dialog.height_spin.value(), 480)

    def test_size_controls_use_declared_range(self):
        dialog = self._dialog()
        low, high = NOTE_SIZE_RANGE
        for spin in (dialog.width_spin, dialog.height_spin):
            self.assertEqual((spin.minimum(), spin.maximum()), (low, high))

    def test_size_spinboxes_are_wide_enough_for_their_values(self):
        """В строке «ширина × высота» должно быть видно само значение.

        Раньше поля вписывались в колонку значений (110 px), а спинбоксу
        с надписью « пт» нужно около 106 px: два таких поля со знаком «×»
        в колонку не влезали, поле ввода сжималось до нуля, и от строки
        оставались одни кнопки со стрелками. Проверяем замером: у спинбокса
        своя ширина по sizeHint, а внутри — непустое поле ввода.
        """
        from PySide6.QtWidgets import QLineEdit

        dialog = self._dialog()
        dialog.adjustSize()
        for spin in (dialog.width_spin, dialog.height_spin):
            field = spin.findChild(QLineEdit)
            self.assertIsNotNone(field, "у спинбокса нет поля ввода")
            self.assertGreaterEqual(spin.width(), spin.sizeHint().width())
            self.assertGreater(field.width(), 0, "поле ввода сжато до нуля")

    def test_size_row_stays_inside_the_dialog(self):
        """Строка размера не должна вылезать за правый край диалога.

        Диалог расширяется под эту строку сам, поэтому проверяем не
        попадание в колонку значений, а то, что он вырос достаточно.
        """
        from PySide6.QtCore import QPoint

        dialog = self._dialog()
        dialog.adjustSize()
        row_right = (
            dialog.height_spin.mapTo(dialog, QPoint(0, 0)).x()
            + dialog.height_spin.width()
        )
        self.assertLessEqual(row_right, dialog.width())

    def test_size_row_keeps_the_value_column_edge(self):
        """Первое поле пары стоит в общей колонке, а не смещено."""
        from PySide6.QtCore import QPoint

        dialog = self._dialog()
        dialog.adjustSize()
        column_left = dialog.font_size_spin.mapTo(dialog, QPoint(0, 0)).x()
        self.assertEqual(
            dialog.width_spin.mapTo(dialog, QPoint(0, 0)).x(), column_left
        )

    def test_restore_defaults_resets_everything(self):
        dialog = self._dialog()
        dialog.font_size_spin.setValue(41)
        dialog.width_spin.setValue(999)
        dialog.height_spin.setValue(999)
        dialog.confirm_delete.setChecked(False)
        dialog.background_button.set_color(QColor("#123456"))
        dialog._restore_defaults()
        self.assertEqual(
            dialog.font_size_spin.value(), DEFAULT_NOTE_SETTINGS["font_size"]
        )
        self.assertEqual(dialog.width_spin.value(), DEFAULT_WIDTH)
        self.assertEqual(dialog.height_spin.value(), DEFAULT_HEIGHT)
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
