"""Тесты геометрии заметки: определение краёв для ресайза.

Проверяются чистые функции hit_test_dirs/cursor_for_dirs — без создания
окна Qt, поэтому QApplication и дисплей не нужны.

Запуск:  python -m unittest discover -s tests -v
"""
import unittest

from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt

from widgets.sticky_note import (
    EDGE, hit_test_dirs, cursor_for_dirs,
    _NORTH, _SOUTH, _WEST, _EAST,
)

W, H = 400, 300


class HitTestTests(unittest.TestCase):
    def test_center_is_not_an_edge(self):
        self.assertEqual(hit_test_dirs(QPoint(W // 2, H // 2), W, H), 0)

    def test_four_sides(self):
        self.assertEqual(hit_test_dirs(QPoint(W // 2, 0), W, H), _NORTH)
        self.assertEqual(hit_test_dirs(QPoint(W // 2, H - 1), W, H), _SOUTH)
        self.assertEqual(hit_test_dirs(QPoint(0, H // 2), W, H), _WEST)
        self.assertEqual(hit_test_dirs(QPoint(W - 1, H // 2), W, H), _EAST)

    def test_four_corners_diagonal(self):
        self.assertEqual(hit_test_dirs(QPoint(0, 0), W, H), _NORTH | _WEST)
        self.assertEqual(hit_test_dirs(QPoint(W - 1, 0), W, H), _NORTH | _EAST)
        self.assertEqual(hit_test_dirs(QPoint(0, H - 1), W, H), _SOUTH | _WEST)
        self.assertEqual(hit_test_dirs(QPoint(W - 1, H - 1), W, H), _SOUTH | _EAST)

    def test_edge_boundary_is_inclusive(self):
        """Сам пиксель EDGE ещё считается краем — иначе полоса «не липнет»."""
        self.assertEqual(hit_test_dirs(QPoint(W // 2, EDGE), W, H), _NORTH)
        self.assertEqual(hit_test_dirs(QPoint(EDGE, H // 2), W, H), _WEST)

    def test_just_past_edge_is_interior(self):
        self.assertEqual(hit_test_dirs(QPoint(W // 2, EDGE + 1), W, H), 0)
        self.assertEqual(hit_test_dirs(QPoint(EDGE + 1, H // 2), W, H), 0)

    def test_small_window_does_not_crash(self):
        """Окно на минимуме: зоны краёв перекрываются — главное без ошибок."""
        for x, y in ((0, 0), (60, 40), (30, 20)):
            hit_test_dirs(QPoint(x, y), 60, 40)


class CursorTests(unittest.TestCase):
    def test_cursors_mapped_for_all_edges(self):
        for dirs in (
            _NORTH, _SOUTH, _WEST, _EAST,
            _NORTH | _WEST, _NORTH | _EAST,
            _SOUTH | _WEST, _SOUTH | _EAST,
        ):
            self.assertIsNotNone(
                cursor_for_dirs(dirs), "нет курсора для направлений %s" % dirs
            )

    def test_horizontal_and_vertical_cursors(self):
        self.assertEqual(cursor_for_dirs(_WEST), Qt.CursorShape.SizeHorCursor)
        self.assertEqual(cursor_for_dirs(_EAST), Qt.CursorShape.SizeHorCursor)
        self.assertEqual(cursor_for_dirs(_NORTH), Qt.CursorShape.SizeVerCursor)
        self.assertEqual(cursor_for_dirs(_SOUTH), Qt.CursorShape.SizeVerCursor)

    def test_diagonal_cursors(self):
        self.assertEqual(
            cursor_for_dirs(_SOUTH | _EAST), Qt.CursorShape.SizeFDiagCursor
        )
        self.assertEqual(
            cursor_for_dirs(_NORTH | _WEST), Qt.CursorShape.SizeFDiagCursor
        )
        self.assertEqual(
            cursor_for_dirs(_NORTH | _EAST), Qt.CursorShape.SizeBDiagCursor
        )
        self.assertEqual(
            cursor_for_dirs(_SOUTH | _WEST), Qt.CursorShape.SizeBDiagCursor
        )

    def test_no_edge_has_no_cursor(self):
        self.assertIsNone(cursor_for_dirs(0))


class ResizeMathTests(unittest.TestCase):
    """Арифметика ресайза: минимальный размер не должен «убегать» от курсора."""

    def apply(self, start, origin, dirs, delta, min_w=180, min_h=120):
        """Повторяет алгоритм StickyNote.apply_resize на чистом QRect-подобном виде."""
        dx, dy = delta
        left, top = start[0], start[1]
        width, height = start[2], start[3]

        if dirs & _SOUTH:
            height = start[3] + dy
        if dirs & _NORTH:
            top = start[1] + dy
            height = start[3] - dy
        if dirs & _EAST:
            width = start[2] + dx
        if dirs & _WEST:
            left = start[0] + dx
            width = start[2] - dx

        if width < min_w:
            if dirs & _WEST:
                left = start[0] + start[2] - min_w
            width = min_w
        if height < min_h:
            if dirs & _NORTH:
                top = start[1] + start[3] - min_h
            height = min_h
        return left, top, width, height

    def test_east_and_south_grow(self):
        self.assertEqual(
            self.apply((100, 100, 400, 300), (0, 0), _EAST | _SOUTH, (50, 30)),
            (100, 100, 450, 330),
        )

    def test_west_does_not_move_right_edge(self):
        left, _, width, _ = self.apply(
            (100, 100, 400, 300), (0, 0), _WEST, (-50, 0)
        )
        self.assertEqual(left, 50)
        self.assertEqual(left + width, 500)

    def test_min_width_keeps_right_edge_anchored_when_dragging_west(self):
        left, _, width, _ = self.apply(
            (100, 100, 400, 300), (0, 0), _WEST, (1000, 0)
        )
        self.assertEqual(width, 180)
        self.assertEqual(left + width, 500)

    def test_min_height_keeps_bottom_edge_anchored_when_dragging_north(self):
        _, top, _, height = self.apply(
            (100, 100, 400, 300), (0, 0), _NORTH, (0, 1000)
        )
        self.assertEqual(height, 120)
        self.assertEqual(top + height, 400)

    def test_north_does_not_move_bottom_edge(self):
        _, top, _, height = self.apply(
            (100, 100, 400, 300), (0, 0), _NORTH, (0, -40)
        )
        self.assertEqual(top, 60)
        self.assertEqual(top + height, 400)


if __name__ == "__main__":
    unittest.main()
