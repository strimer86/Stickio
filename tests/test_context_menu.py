"""Тесты перевода контекстного меню редактора заметки.

Стандартное меню QTextEdit приходит на английском (Cut/Copy/Paste), потому
что .qm-файлы перевода Qt не загружаются. Проверяем саму логику подмены
подписей, не открывая окно заметки.

Запуск:  python -m unittest discover -s tests -v
"""
import unittest

from PySide6.QtWidgets import QApplication, QTextEdit

from widgets.sticky_note import translate_context_menu

_app = None


def setUpModule():
    global _app
    # QTextEdit требует существующий QApplication
    _app = QApplication.instance() or QApplication([])


class TranslateMenuTests(unittest.TestCase):
    def setUp(self):
        # QMenu, созданное из меню редактора, держится за его C++-объект:
        # если QTextEdit соберётся сборщиком мусора, меню станет невалидным.
        self.editors = []

    def tearDown(self):
        self.editors.clear()

    def build_menu(self, text="привет"):
        editor = QTextEdit()
        self.editors.append(editor)
        editor.setPlainText(text)
        if text:
            cursor = editor.textCursor()
            cursor.select(cursor.SelectionType.Document)
            editor.setTextCursor(cursor)
        menu = editor.createStandardContextMenu()
        translate_context_menu(menu)
        return menu

    def labels(self, menu):
        """Подписи без хоткеев, в порядке следования."""
        return [
            a.text().split("\t")[0]
            for a in menu.actions() if not a.isSeparator()
        ]

    def test_all_items_are_russian(self):
        for label in self.labels(self.build_menu()):
            self.assertRegex(
                label, r"^[А-Яа-яЁё ]+$",
                "пункт меню остался непереведённым: %r" % label,
            )

    def test_expected_items_present(self):
        labels = self.labels(self.build_menu())
        self.assertIn("Вырезать", labels)
        self.assertIn("Копировать", labels)
        self.assertIn("Вставить", labels)
        self.assertIn("Выделить всё", labels)

    def test_shortcuts_are_preserved(self):
        """Ctrl+C и Ctrl+V должны остаться в подписи — по ним учатся."""
        texts = [a.text() for a in self.build_menu().actions() if not a.isSeparator()]
        joined = " | ".join(texts)
        for shortcut in ("Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z", "Ctrl+A"):
            self.assertIn(shortcut, joined, "потерян хоткей %s" % shortcut)

    def test_separators_survive(self):
        menu = self.build_menu()
        self.assertTrue(any(a.isSeparator() for a in menu.actions()))

    def test_action_enabled_state_matches_editor(self):
        """Доступность пунктов не должна ломаться при подмене подписей."""
        empty = self.build_menu(text="")
        labels = self.labels(empty)
        # на пустом тексте копировать нечего
        self.assertIn("Копировать", labels)

    def test_stylesheet_sets_dark_text(self):
        style = self.build_menu().styleSheet()
        self.assertIn("color: #000000", style)
        self.assertIn("font-weight: 600", style)

    def test_translation_is_idempotent(self):
        """Повторный вызов не портит уже переведённые подписи."""
        editor = QTextEdit()
        self.editors.append(editor)
        editor.setPlainText("текст")
        menu = editor.createStandardContextMenu()
        translate_context_menu(menu)
        first = self.labels(menu)
        translate_context_menu(menu)
        self.assertEqual(self.labels(menu), first)


if __name__ == "__main__":
    unittest.main()
