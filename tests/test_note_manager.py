"""Тесты логики показа заметок в NoteManager.

Окна Qt здесь заменены заглушками: проверяется только алгоритм видимости,
поэтому QApplication и дисплей не нужны.

Запуск:  python -m unittest discover -s tests -v
"""
import unittest

from services.note_manager import NoteManager


class FakeNote:
    def __init__(self, note_id):
        self.id = note_id


class FakeWindow:
    """Минимальная замена StickyNote: хранит флаг видимости и порядок вызовов."""

    def __init__(self, note_id):
        self.note = FakeNote(note_id)
        self._visible = True
        self.raise_count = 0
        self.activated = False

    def isVisible(self):
        return self._visible

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False

    def raise_(self):
        self.raise_count += 1
        self._visible = True

    def activateWindow(self):
        self.activated = True
        self._visible = True

    def close(self):
        self._visible = False


class ShowOneTests(unittest.TestCase):
    """Регрессия: клик по трею с заметки #N открывал первую из списка."""

    def setUp(self):
        self.manager = NoteManager(database=None)
        for note_id in (1, 2, 3, 4, 5):
            self.manager.windows[note_id] = FakeWindow(note_id)

    def visible(self):
        return [i for i in self.manager.windows if self.manager.windows[i].isVisible()]

    def show_only(self, note_id):
        """Приводит состояние к «видна только одна заметка» — обычная ситуация."""
        for wid, window in self.manager.windows.items():
            if wid != note_id:
                window.hide()

    def test_cycles_to_next_visible_note(self):
        self.show_only(1)
        self.manager.show_one()  # #1 -> #2
        self.assertEqual(self.visible(), [2])

    def test_cycle_from_middle_note_goes_to_next_not_first(self):
        """Раньше индекс считался от начала списка: с #5 клик открывал #1."""
        self.show_only(3)
        self.manager.show_one()
        self.assertEqual(self.visible(), [4])

    def test_wraps_around_from_last_to_first(self):
        self.show_only(5)
        self.manager.show_one()  # #5 -> #1
        self.assertEqual(self.visible(), [1])

    def test_all_hidden_shows_first(self):
        for window in self.manager.windows.values():
            window.hide()
        self.manager.show_one()
        self.assertEqual(self.visible(), [1])

    def test_single_note_toggles_visibility(self):
        self.manager.windows = {7: FakeWindow(7)}
        self.manager.show_one()
        self.assertEqual(self.visible(), [])
        self.manager.show_one()
        self.assertEqual(self.visible(), [7])

    def test_multiple_visible_collapses_to_first(self):
        # частый случай: всё открыто после старта приложения
        self.manager.show_one()
        self.assertEqual(self.visible(), [1])


    def test_no_notes_does_not_crash(self):
        self.manager.windows = {}
        self.manager.show_one()


class HideShowAllTests(unittest.TestCase):
    def setUp(self):
        self.manager = NoteManager(database=None)
        for note_id in (1, 2, 3):
            self.manager.windows[note_id] = FakeWindow(note_id)

    def visible(self):
        return [i for i in self.manager.windows if self.manager.windows[i].isVisible()]

    def test_show_all_restores_only_previously_visible(self):
        """Была видна только #2 → скрыли все → показать должно вернуть только #2."""
        self.manager.windows[1].hide()
        self.manager.windows[3].hide()

        self.manager.hide_all()
        self.assertEqual(self.visible(), [])

        self.manager.show_all()
        self.assertEqual(self.visible(), [2])

    def test_show_all_after_full_hide_restores_everything(self):
        self.manager.hide_all()
        self.manager.show_all()
        self.assertEqual(self.visible(), [1, 2, 3])

    def test_show_all_falls_back_when_nothing_was_recorded(self):
        """Заметки гасили по одной, hide_all не звали — хоткей всё равно показывает."""
        for window in self.manager.windows.values():
            window.hide()
        self.manager.show_all()
        self.assertEqual(self.visible(), [1, 2, 3])

    def test_show_all_ignores_deleted_notes(self):
        self.manager.hide_all()
        del self.manager.windows[2]
        self.manager.show_all()
        self.assertEqual(self.visible(), [1, 3])


if __name__ == "__main__":
    unittest.main()
