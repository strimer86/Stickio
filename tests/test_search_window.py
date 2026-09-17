"""Окно поиска и подсветка найденного в заметке."""
import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTextEdit

_app = QApplication.instance() or QApplication([])

from database.database import Database
from services.note_manager import NoteManager
from settings_isolation import SettingsIsolationMixin
from widgets.search_window import SearchWindow, apply_highlight


class HighlightTests(unittest.TestCase):
    def setUp(self):
        self.editor = QTextEdit()

    def test_all_occurrences_highlighted(self):
        self.editor.setPlainText("иголка и ещё иголка, и снова иголка")
        self.assertEqual(apply_highlight(self.editor, "иголка"), 3)

    def test_case_insensitive(self):
        self.editor.setPlainText("Привет и привет")
        self.assertEqual(apply_highlight(self.editor, "ПРИВЕТ"), 2)

    def test_empty_query_clears_highlight(self):
        self.editor.setPlainText("текст")
        apply_highlight(self.editor, "текст")
        self.assertEqual(len(self.editor.extraSelections()), 1)
        self.assertEqual(apply_highlight(self.editor, ""), 0)
        self.assertEqual(self.editor.extraSelections(), [])

    def test_no_match_clears_previous_highlight(self):
        """Иначе на экране осталась бы подсветка от прошлого запроса."""
        self.editor.setPlainText("текст")
        apply_highlight(self.editor, "текст")
        self.assertEqual(apply_highlight(self.editor, "неттакого"), 0)
        self.assertEqual(self.editor.extraSelections(), [])

    def test_highlight_does_not_touch_document(self):
        """Главное: подсветка не должна попадать в сохраняемый текст."""
        self.editor.setPlainText("важное слово")
        before = self.editor.toHtml()
        apply_highlight(self.editor, "слово")
        self.assertEqual(self.editor.toHtml(), before)

    def test_highlight_survives_save_roundtrip(self):
        """Проверяем то же самое, но через реальное сохранение в базу."""
        self.editor.setPlainText("важное слово")
        clean = self.editor.toHtml()
        apply_highlight(self.editor, "слово")
        self.assertNotIn("ffe36e", self.editor.toHtml().lower())
        self.assertEqual(self.editor.toHtml(), clean)

    def test_broken_regex_does_not_crash(self):
        self.editor.setPlainText("текст")
        self.assertEqual(apply_highlight(self.editor, "[битое", regex=True), 0)

    def test_spans_point_at_right_fragments(self):
        self.editor.setPlainText("первое слово тут")
        apply_highlight(self.editor, "слово")
        (selection,) = self.editor.extraSelections()
        self.assertEqual(selection.cursor.selectedText(), "слово")


class SearchWindowTests(unittest.TestCase):
    def setUp(self):
        self.notes = [
            type("N", (), {"id": 1, "content": "купить хлеб и молоко"})(),
            type("N", (), {"id": 2, "content": "позвонить маме"})(),
            type("N", (), {"id": 3, "content": "хлеб свежий"})(),
        ]
        self.window = SearchWindow()
        self.window.set_notes_provider(lambda: self.notes)

    def tearDown(self):
        self.window.close()

    def test_empty_query_shows_nothing(self):
        self.window.query_edit.setText("")
        self.assertEqual(self.window.results.count(), 0)
        self.assertEqual(self.window.summary.text(), "")

    def test_query_fills_results(self):
        self.window.query_edit.setText("хлеб")
        self.assertEqual(self.window.results.count(), 2)
        self.assertIn("2", self.window.summary.text())

    def test_no_match_message(self):
        self.window.query_edit.setText("нетакогослова")
        self.assertEqual(self.window.results.count(), 0)
        self.assertIn("Ничего не найдено", self.window.summary.text())

    def test_current_note_id(self):
        self.window.query_edit.setText("маме")
        self.assertEqual(self.window.current_note_id(), 2)

    def test_activation_emits_note_id(self):
        received = []
        self.window.note_activated.connect(received.append)
        self.window.query_edit.setText("маме")
        self.window._activate_current()
        self.assertIn(2, received)

    def test_broken_regex_reports_instead_of_crashing(self):
        self.window.regex_check.setChecked(True)
        self.window.query_edit.setText("[битое")
        self.assertEqual(self.window.results.count(), 0)
        self.assertIn("Некорректное выражение", self.window.summary.text())

    def test_regex_mode_works(self):
        self.window.regex_check.setChecked(True)
        self.window.query_edit.setText("хлеб\\w*")
        self.assertEqual(self.window.results.count(), 2)

    def test_provider_is_read_live(self):
        """Провайдер, а не снимок: новая заметка должна попадать в поиск."""
        self.window.query_edit.setText("хлеб")
        self.assertEqual(self.window.results.count(), 2)
        self.notes.append(
            type("N", (), {"id": 4, "content": "ещё хлеб"})()
        )
        self.window.refresh()
        self.assertEqual(self.window.results.count(), 3)

    def test_plain_text_search_ignores_html(self):
        self.notes.append(
            type("N", (), {"id": 5, "content": '<p style="font-size:18pt;">рыба</p>'})()
        )
        self.window.query_edit.setText("font-size")
        self.assertEqual(self.window.results.count(), 0)
        self.window.query_edit.setText("рыба")
        self.assertEqual(self.window.results.count(), 1)


class FocusNoteTests(SettingsIsolationMixin, unittest.TestCase):
    """Сквозная проверка: результат поиска -> открытая заметка с подсветкой."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="stickio_search_")
        self.db = Database(os.path.join(self.tmp, "notes.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _app_stub(self):
        """Минимальный App без трея и хоткеев — только поиск и менеджер."""
        from app import App

        stub = App.__new__(App)
        stub.app = _app
        stub.settings = self.settings
        stub.database = self.db
        stub.manager = NoteManager(self.db, settings=self.settings)
        stub.tray = None
        stub._tray_action_new = None
        stub._tray_action_toggle = None
        stub._tray_action_search = None
        stub._search_window = None
        return stub

    def test_focusing_highlights_in_open_window(self):
        note_id = self.db.create_note(content="<p>найти иголку тут</p>")
        stub = self._app_stub()
        try:
            stub.manager.load_all()
            stub.open_search()
            stub._search_window.query_edit.setText("иголку")
            stub._focus_note(note_id)

            window = stub.manager.windows[note_id]
            selections = window.editor.extraSelections()
            self.assertEqual(len(selections), 1)
            self.assertEqual(selections[0].cursor.selectedText(), "иголку")
            self.assertTrue(window.isVisible())
        finally:
            stub.manager.close_all()
            if stub._search_window is not None:
                stub._search_window.close()

    def test_focusing_saves_nothing_extra(self):
        """Подсветка не должна попасть в сохранённый текст."""
        note_id = self.db.create_note(content="<p>слово в заметке</p>")
        stub = self._app_stub()
        try:
            stub.manager.load_all()
            window = stub.manager.windows[note_id]
            window.save_note()
            stub.open_search()
            stub._search_window.query_edit.setText("слово")
            stub._focus_note(note_id)
            window.save_note()
            self.assertNotIn(
                "ffe36e", (self.db.get_note(note_id).content or "").lower()
            )
        finally:
            stub.manager.close_all()
            if stub._search_window is not None:
                stub._search_window.close()

    def test_deleted_note_does_not_crash(self):
        """Заметку могли удалить, пока окно поиска было открыто."""
        note_id = self.db.create_note(content="<p>временная</p>")
        stub = self._app_stub()
        try:
            stub.manager.load_all()
            stub.open_search()
            stub._search_window.query_edit.setText("временная")
            self.db.delete_note(note_id)
            stub.manager.windows[note_id].close()
            stub.manager.windows.pop(note_id, None)
            stub._focus_note(note_id)  # не должно бросать
        finally:
            stub.manager.close_all()
            if stub._search_window is not None:
                stub._search_window.close()

    def test_search_window_is_reused(self):
        """Повторный вызов не должен терять запрос."""
        stub = self._app_stub()
        try:
            stub.open_search()
            stub._search_window.query_edit.setText("запрос")
            stub.open_search()
            self.assertEqual(stub._search_window.current_query(), "запрос")
        finally:
            stub.manager.close_all()
            if stub._search_window is not None:
                stub._search_window.close()


if __name__ == "__main__":
    unittest.main()
