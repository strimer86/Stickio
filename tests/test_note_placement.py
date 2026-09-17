"""Тесты каскадного размещения новых заметок.

Без каскада все новые заметки получают x/y из умолчаний схемы БД и встают
точкой в точку друг поверх друга: создаёшь вторую — видишь одну.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from database.database import Database
from services.note_manager import (
    CASCADE_STEP, NoteManager, cascade_position, rects_overlap,
)
from settings_isolation import SettingsIsolationMixin

_app = QApplication.instance() or QApplication([])

# Экран, на котором заметки гарантированно помещаются в несколько рядов.
SCREEN = QRect(0, 0, 1920, 1080)
NOTE = (380, 300)


class RectsOverlapTests(unittest.TestCase):
    def test_intersecting(self):
        self.assertTrue(rects_overlap(QRect(0, 0, 10, 10), QRect(5, 5, 10, 10)))

    def test_touching_edges_is_not_overlap(self):
        self.assertFalse(rects_overlap(QRect(0, 0, 10, 10), QRect(10, 0, 10, 10)))
        self.assertFalse(rects_overlap(QRect(0, 0, 10, 10), QRect(0, 10, 10, 10)))

    def test_apart(self):
        self.assertFalse(rects_overlap(QRect(0, 0, 10, 10), QRect(50, 50, 10, 10)))


class CascadePositionTests(unittest.TestCase):
    def _free(self, occupied, area=SCREEN):
        return cascade_position(list(occupied), NOTE[0], NOTE[1], area)

    def test_first_note_stays_at_start(self):
        self.assertEqual(self._free([]), (120, 120))

    def test_second_note_does_not_cover_first(self):
        first = QRect(120, 120, *NOTE)
        x, y = self._free([first])
        self.assertFalse(rects_overlap(QRect(x, y, *NOTE), first))

    def test_three_notes_are_all_visible(self):
        """Ни одна не должна быть полностью перекрыта другой."""
        placed = []
        for _ in range(3):
            x, y = self._free([QRect(*p, *NOTE) for p in placed])
            placed.append((x, y))
        self.assertEqual(len(set(placed)), 3)
        for i, (x, y) in enumerate(placed):
            for j, (ox, oy) in enumerate(placed):
                if i != j:
                    self.assertFalse(
                        rects_overlap(QRect(x, y, *NOTE), QRect(ox, oy, *NOTE)),
                        "заметки %d и %d перекрылись" % (i, j),
                    )

    def test_cascade_moves_by_step(self):
        """Сдвиг заметный глазом: не меньше CASCADE_STEP по одной из осей."""
        first = QRect(120, 120, *NOTE)
        x, y = self._free([first])
        self.assertTrue(
            abs(x - 120) >= CASCADE_STEP or abs(y - 120) >= CASCADE_STEP
        )

    def test_stays_inside_screen(self):
        occupied = [QRect(120, 120, *NOTE)]
        for _ in range(12):
            x, y = self._free(occupied)
            self.assertGreaterEqual(x, SCREEN.left())
            self.assertGreaterEqual(y, SCREEN.top())
            self.assertLessEqual(x + NOTE[0], SCREEN.right())
            self.assertLessEqual(y + NOTE[1], SCREEN.bottom())
            occupied.append(QRect(x, y, *NOTE))

    def test_wraps_instead_of_leaving_screen(self):
        small = QRect(0, 0, 800, 400)
        occupied = [QRect(120, 120, *NOTE)]
        x, y = cascade_position(occupied, *NOTE, small)
        self.assertLessEqual(x + NOTE[0], 800)
        self.assertLessEqual(y + NOTE[1], 400)

    def test_second_monitor_offset_area(self):
        """У второго монитора своё начало координат — каскад внутри него."""
        area = QRect(1920, 0, 1920, 1080)
        x, y = cascade_position([], *NOTE, area)
        self.assertGreaterEqual(x, 1920)
        self.assertLessEqual(x + NOTE[0], area.right())

    def test_fully_occupied_gives_shifted_position(self):
        """Нет свободного места — но и точь-в-точь поверх первой не ставим."""
        occupied = [
            QRect(px, py, *NOTE)
            for px in range(0, 1920, 380)
            for py in range(0, 1080, 300)
        ]
        x, y = cascade_position(occupied, *NOTE, SCREEN)
        self.assertNotEqual((x, y), (120, 120))

    def test_hidden_notes_do_not_block(self):
        """Вызов с пустым occupied (все скрыты) — место со старта."""
        self.assertEqual(cascade_position([], *NOTE, SCREEN), (120, 120))


class FakeScreen:
    """Экран нужного размера: в offscreen Qt даёт фиксированные 800×800,
    куда больше одной заметки не влезает."""

    def __init__(self, rect=SCREEN):
        self._rect = rect

    def availableGeometry(self):
        return QRect(self._rect)


class FreePositionTests(SettingsIsolationMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="stickio_placement_")
        self.db = Database(os.path.join(self.tmp, "notes.db"))
        # Свои настройки: иначе заметки создаются с видом из настоящего
        # профиля, и размеры в проверках зависят от выбранного пользователем.
        self.manager = NoteManager(self.db, settings=self.settings)

    def tearDown(self):
        self.manager.close_all()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _create_many(self, count):
        with patch.object(QApplication, "screenAt", return_value=FakeScreen()):
            return [self.manager.create_note() for _ in range(count)]

    def test_new_notes_do_not_stack(self):
        """Главная проверка: вторая заметка не должна крыть первую."""
        windows = self._create_many(4)
        positions = [(w.note.x, w.note.y) for w in windows]
        self.assertEqual(len(set(positions)), len(positions), positions)

    def test_position_is_saved_to_database(self):
        """Иначе после перезапуска каскад начнётся заново."""
        window = self._create_many(1)[0]
        loaded = self.db.get_note(window.note.id)
        self.assertEqual((loaded.x, loaded.y), (window.note.x, window.note.y))

    def test_falls_back_to_primary_when_screen_unknown(self):
        with patch.object(QApplication, "screenAt", return_value=None):
            window = self.manager.create_note()
        self.assertIsNotNone(window)


if __name__ == "__main__":
    unittest.main()
