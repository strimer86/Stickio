"""Палитра цвета: два набора образцов, подсветка текущего, геометрия попапа."""

import unittest

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from widgets.color_picker import (
    BACKGROUND_SWATCHES, TEXT_SWATCHES, ColorPicker, ColorPopup,
)

_app = QApplication.instance() or QApplication([])


class SwatchListTest(unittest.TestCase):
    def test_both_palettes_have_twelve_valid_colors(self):
        for palette in (BACKGROUND_SWATCHES, TEXT_SWATCHES):
            self.assertEqual(len(palette), 12)
            for value in palette:
                self.assertTrue(QColor(value).isValid(), value)

    def test_palettes_do_not_overlap(self):
        # Список был один на оба случая — светло-жёлтый текст на жёлтой
        # заметке был нечитаем. Наборы обязаны различаться.
        self.assertEqual(set(BACKGROUND_SWATCHES) & set(TEXT_SWATCHES), set())

    def test_text_palette_is_dark(self):
        for value in TEXT_SWATCHES:
            color = QColor(value)
            self.assertLess(color.lightness(), 130, value)

    def test_background_palette_is_light(self):
        for value in BACKGROUND_SWATCHES:
            color = QColor(value)
            self.assertGreater(color.lightness(), 150, value)


class PickerTest(unittest.TestCase):
    def setUp(self):
        # держим виджеты живыми: иначе C++ объекты удаляются сборщиком мусора
        self.widgets = []

    def _picker(self, **kwargs):
        picker = ColorPicker(**kwargs)
        self.widgets.append(picker)
        return picker

    def test_background_picker_uses_background_palette(self):
        picker = self._picker()
        self.assertEqual(len(picker._buttons), len(BACKGROUND_SWATCHES))

    def test_custom_palette_is_honoured(self):
        picker = self._picker(title="Цвет текста", swatches=TEXT_SWATCHES)
        for value in TEXT_SWATCHES:
            self.assertIn(value.lower(), picker._buttons)

    def test_set_current_marks_matching_swatch(self):
        picker = self._picker()
        picker.set_current(QColor("#FF9F9F"))
        marked = [
            hex_color for hex_color, b in picker._buttons.items()
            if b.property("current") == "true"
        ]
        self.assertEqual(marked, ["#ff9f9f"])

    def test_set_current_is_case_insensitive(self):
        picker = self._picker(swatches=TEXT_SWATCHES)
        picker.set_current(QColor("#abcdef"))
        # нет такого образца — ни один не подсвечен, и это не падение
        marked = [b for b in picker._buttons.values() if b.property("current") == "true"]
        self.assertEqual(marked, [])
        picker.set_current(QColor("#000000"))
        self.assertEqual(picker._buttons["#000000"].property("current"), "true")

    def test_select_emits_and_marks(self):
        picker = self._picker()
        got = []
        picker.color_selected.connect(got.append)
        picker._select("#C9B3FF")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].name(), "#c9b3ff")
        self.assertEqual(picker._buttons["#c9b3ff"].property("current"), "true")

    def test_swatches_are_square_and_clickable(self):
        picker = self._picker()
        for button in picker._buttons.values():
            self.assertEqual(button.width(), button.height())
            self.assertTrue(button.isEnabled())


class PopupTest(unittest.TestCase):
    def setUp(self):
        self.widgets = []

    def _popup(self, for_text=False):
        popup = ColorPopup(None, for_text=for_text)
        self.widgets.append(popup)
        return popup

    def test_for_text_flag_selects_palette(self):
        popup = self._popup(for_text=True)
        self.assertTrue(popup.for_text)
        self.assertIn("#000000", popup.picker._buttons)
        self.assertNotIn("#FFF4A8", popup.picker._buttons)

    def test_popup_titles_differ(self):
        self.assertEqual(self._popup(False).picker.title_label.text(), "Цвет фона")
        self.assertEqual(self._popup(True).picker.title_label.text(), "Цвет текста")

    def test_set_current_delegates_to_picker(self):
        popup = self._popup()
        popup.set_current(QColor("#A8D8FF"))
        self.assertEqual(popup.picker._buttons["#a8d8ff"].property("current"), "true")

    def test_selection_closes_popup(self):
        popup = self._popup()
        popup.show()
        got = []
        popup.color_selected.connect(got.append)
        popup.picker._select("#FFFFFF")
        self.assertEqual(len(got), 1)
        self.assertFalse(popup.isVisible())


class PlacePopupTest(unittest.TestCase):
    """Попап не должен уезжать за границу экрана и не должен крыть панель."""

    def _place(self, anchor_pos: QPoint, panel_rect=None):
        from PySide6.QtCore import QRect
        from widgets.toolbar import Toolbar

        toolbar = Toolbar(None)
        popup = ColorPopup(toolbar)
        self.widgets = [toolbar, popup]

        rect = panel_rect or QRect(
            anchor_pos.x(), anchor_pos.y(), 300, 70
        )
        # реальная ширина Toolbar нужна снаружи — её считает self._real_panel_width
        self._real_panel_width = toolbar.width()

        class Anchor:
            """Заглушка кнопки: настоящей Qt-кнопке нужно окно-родитель."""

            def mapToGlobal(self, _point):
                return anchor_pos

            def width(self):
                return 34

            def height(self):
                return 26

            def window(self):
                class Panel:
                    def mapToGlobal(_self, point):
                        return QPoint(rect.x() + point.x(), rect.y() + point.y())

                    def width(_self):
                        return rect.width()

                    def height(_self):
                        return rect.height()

                return Panel()

        Toolbar._place_popup(popup, Anchor())
        return popup.pos()

    def test_popup_stays_inside_available_geometry(self):
        screen = QApplication.primaryScreen().availableGeometry()
        pos = self._place(QPoint(screen.right() - 5, screen.bottom() - 60))
        popup = self.widgets[-1]
        self.assertLessEqual(pos.x() + popup.width(), screen.right() + 1)
        self.assertLessEqual(pos.y() + popup.height(), screen.bottom() + 1)
        self.assertGreaterEqual(pos.x(), screen.left())
        self.assertGreaterEqual(pos.y(), screen.top())

    def test_popup_does_not_cover_panel_when_room_on_right(self):
        from PySide6.QtCore import QRect

        screen = QApplication.primaryScreen().availableGeometry()
        panel_x = screen.left() + 100
        panel_y = screen.top() + 100
        self._place(
            QPoint(panel_x, panel_y),
            panel_rect=QRect(panel_x, panel_y, 200, 70),
        )
        # попап не должен пересекаться по X с панелью: ни накладываться,
        # ни касаться — между ними gap=6. Сверяем с шириной фейковой панели.
        fake_panel_width = 200
        pos = self.widgets[-1].pos()
        self.assertGreaterEqual(pos.x(), panel_x + fake_panel_width + 6)

    def test_popup_flips_left_when_no_room_on_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        from PySide6.QtCore import QRect
        # панель у самого правого края
        panel_x = screen.right() - 200
        pos = self._place(
            QPoint(panel_x, screen.top() + 100),
            panel_rect=QRect(panel_x, screen.top() + 100, 200, 70),
        )
        self.assertLess(pos.x(), panel_x)


if __name__ == "__main__":
    unittest.main()
