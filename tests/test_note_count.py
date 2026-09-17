"""Тесты счётчика заметок в трее и склонения слова «заметка»."""
import os
import shutil
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from database.database import Database
from services.note_manager import (
    NoteManager, notes_count_label, plural_notes,
)

_app = QApplication.instance() or QApplication([])


class PluralNotesTests(unittest.TestCase):
    """Русское склонение — не «1 и остальное», у него есть исключения."""

    def test_singular(self):
        for count in (1, 21, 31, 101):
            self.assertEqual(plural_notes(count), "заметка", "count=%d" % count)

    def test_few(self):
        for count in (2, 3, 4, 22, 33, 44):
            self.assertEqual(plural_notes(count), "заметки", "count=%d" % count)

    def test_many(self):
        for count in (0, 5, 6, 9, 10, 20, 25, 100):
            self.assertEqual(plural_notes(count), "заметок", "count=%d" % count)

    def test_second_ten_is_an_exception(self):
        """11..14 ведут себя как «много», хотя кончаются на 1..4."""
        for count in (11, 12, 13, 14):
            self.assertEqual(plural_notes(count), "заметок", "count=%d" % count)

    def test_beyond_single_hundred_same_exception(self):
        for count in (111, 112, 113, 114):
            self.assertEqual(plural_notes(count), "заметок", "count=%d" % count)

    def test_negative_is_treated_by_absolute_value(self):
        self.assertEqual(plural_notes(-3), "заметки")


class NotesCountLabelTests(unittest.TestCase):
    def test_label_contains_number_and_word(self):
        self.assertEqual(notes_count_label(1), "Stickio — 1 заметка")
        self.assertEqual(notes_count_label(3), "Stickio — 3 заметки")
        self.assertEqual(notes_count_label(12), "Stickio — 12 заметок")

    def test_zero_notes(self):
        self.assertEqual(notes_count_label(0), "Stickio — 0 заметок")


class NotesChangedSignalTests(unittest.TestCase):
    """Сигнал должен приходить на создание, удаление и импорт.

    Без него подпись трея оставалась бы с устаревшим числом: обновлять её
    вручную из каждого места легко забыть.
    """

    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("NotesChangedTests")
        self.tmp = tempfile.mkdtemp(prefix="stickio_count_")
        self.db = Database(os.path.join(self.tmp, "notes.db"))
        self.manager = NoteManager(self.db)
        self.calls = []
        self.manager.notes_changed.connect(lambda: self.calls.append(1))

    def tearDown(self):
        self.manager.close_all()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_emits(self):
        self.manager.create_note()
        self.assertEqual(len(self.calls), 1)

    def test_delete_emits(self):
        window = self.manager.create_note()
        self.calls.clear()
        self.manager.delete_window(window)
        self.assertEqual(len(self.calls), 1)

    def test_load_all_emits_once(self):
        for _ in range(3):
            self.db.create_note()
        self.manager.load_all()
        self.assertEqual(len(self.calls), 1)

    def test_load_all_without_notes_does_not_emit(self):
        self.manager.load_all()
        self.assertEqual(self.calls, [])

    def test_import_emits_only_when_something_arrived(self):
        self.manager.import_notes([])
        self.assertEqual(self.calls, [])
        self.manager.import_notes([{"content": "", "font_size": 18}])
        self.assertEqual(len(self.calls), 1)


class TrayTooltipTests(unittest.TestCase):
    """Сквозная проверка: подпись трея показывает реальное число заметок."""

    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("TrayTooltipTests")
        self.tmp = tempfile.mkdtemp(prefix="stickio_tray_")
        self.db = Database(os.path.join(self.tmp, "notes.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _app_stub(self):
        """Заглушка App: нужен только manager и tray-подсказка."""
        from app import App

        stub = App.__new__(App)
        stub.tray = type("Tray", (), {
            "tooltip": "",
            "setToolTip": lambda self, text: setattr(self, "tooltip", text),
        })()
        stub.manager = NoteManager(self.db)
        stub._refresh_note_count()
        return stub

    def test_tooltip_counts_notes_and_visible_ones(self):
        stub = self._app_stub()
        try:
            self.assertEqual(stub.tray.tooltip, "Stickio — 0 заметок\nВидимых: 0")
            stub.manager.create_note()
            stub._refresh_note_count()
            self.assertEqual(stub.tray.tooltip, "Stickio — 1 заметка\nВидимых: 1")
            stub.manager.create_note()
            stub._refresh_note_count()
            self.assertEqual(stub.tray.tooltip, "Stickio — 2 заметки\nВидимых: 2")
            stub.manager.hide_all()
            stub._refresh_note_count()
            self.assertEqual(stub.tray.tooltip, "Stickio — 2 заметки\nВидимых: 0")
        finally:
            stub.manager.close_all()

    def test_signal_updates_tooltip_without_manual_call(self):
        """Подпись должна меняться сама по сигналу, а не по вызову из места."""
        stub = self._app_stub()
        try:
            stub.manager.notes_changed.connect(stub._refresh_note_count)
            stub.manager.create_note()
            self.assertEqual(stub.tray.tooltip, "Stickio — 1 заметка\nВидимых: 1")
            window = list(stub.manager.windows.values())[0]
            stub.manager.delete_window(window)
            self.assertEqual(stub.tray.tooltip, "Stickio — 0 заметок\nВидимых: 0")
        finally:
            stub.manager.close_all()


if __name__ == "__main__":
    unittest.main()
