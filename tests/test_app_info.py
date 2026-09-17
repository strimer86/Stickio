"""Сведения о программе: версия, автор, окно «О программе»."""
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialogButtonBox

_app = QApplication.instance() or QApplication([])

from services import app_info
from widgets.about_dialog import AboutDialog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_INFO = os.path.join(ROOT, "version_info.txt")
BUILT_EXE = os.path.join(ROOT, "dist", "Stickio", "Stickio.exe")


def version_from_version_info() -> str:
    """Версия из filevers в version_info.txt: (1, 0, 1, 0) -> «1.0.1»."""
    with open(VERSION_INFO, encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(r"filevers=\(\s*(\d+),\s*(\d+),\s*(\d+)", text)
    if match is None:
        raise AssertionError("в version_info.txt не нашлось filevers")
    return ".".join(match.groups())


class VersionTests(unittest.TestCase):
    def test_fallback_matches_version_info(self):
        """Иначе из исходников и из exe показывались бы разные версии."""
        self.assertEqual(app_info.VERSION_FALLBACK, version_from_version_info())

    def test_fallback_looks_like_version(self):
        self.assertRegex(app_info.VERSION_FALLBACK, r"^\d+\.\d+\.\d+$")

    def test_source_run_uses_fallback(self):
        """Тесты идут из исходников, ресурса версии рядом нет."""
        self.assertFalse(getattr(app_info.sys, "frozen", False))
        self.assertEqual(app_info.app_version(), app_info.VERSION_FALLBACK)

    def test_display_version_drops_trailing_zero(self):
        self.assertEqual(app_info.display_version("1.0.1.0"), "1.0.1")

    def test_display_version_keeps_real_build_number(self):
        """Четвёртое число не ноль — значит осмысленное, терять его нельзя."""
        self.assertEqual(app_info.display_version("1.2.0.3"), "1.2.0.3")

    def test_display_version_leaves_short_string_alone(self):
        self.assertEqual(app_info.display_version("2.0.1"), "2.0.1")


class VersionFromExeTests(unittest.TestCase):
    """Чтение версии из ресурса — на настоящем файле, если он собран."""

    def setUp(self):
        if not os.path.exists(BUILT_EXE):
            self.skipTest("сборка не найдена: %s" % BUILT_EXE)

    def test_reads_four_number_version(self):
        self.assertRegex(
            app_info._version_from_exe(BUILT_EXE), r"^\d+\.\d+\.\d+\.\d+$"
        )

    def test_missing_resource_gives_empty_string(self):
        """Файл без ресурса не должен ронять приложение."""
        self.assertEqual(app_info._version_from_exe(__file__), "")

    def test_missing_file_gives_empty_string(self):
        self.assertEqual(
            app_info._version_from_exe(os.path.join(ROOT, "нет_такого.exe")), ""
        )


class AuthorTests(unittest.TestCase):
    def test_author_is_not_placeholder(self):
        self.assertTrue(app_info.APP_AUTHOR.strip())
        self.assertNotIn("Stickio", app_info.APP_AUTHOR)

    def test_site_is_https(self):
        self.assertTrue(app_info.APP_SITE.startswith("https://"))

    def test_site_label_has_no_scheme(self):
        """Подпись показывается человеку, а не копируется в адресную строку."""
        self.assertNotIn("://", app_info.APP_SITE_LABEL)
        self.assertIn(app_info.APP_SITE_LABEL, app_info.APP_SITE)

    def test_copyright_names_author(self):
        line = app_info.copyright_line()
        self.assertIn(app_info.APP_AUTHOR, line)
        self.assertTrue(line.startswith("©"))


class AboutDialogTests(unittest.TestCase):
    def setUp(self):
        self.dialog = AboutDialog()

    def tearDown(self):
        self.dialog.deleteLater()

    def test_title(self):
        self.assertEqual(self.dialog.windowTitle(), "О программе")

    def test_name_and_version_shown(self):
        text = self.dialog.name_label.text()
        self.assertIn(app_info.APP_NAME, text)
        self.assertIn(app_info.app_version(), text)

    def test_name_is_larger_than_body(self):
        """Название должно читаться как заголовок, а не как строка текста."""
        self.assertGreater(
            self.dialog.name_label.font().pointSize(),
            self.dialog.tagline_label.font().pointSize(),
        )

    def test_author_shown(self):
        self.assertIn(app_info.APP_AUTHOR, self.dialog.author_label.text())

    def test_site_is_a_link_to_the_real_address(self):
        html = self.dialog.site_label.text()
        self.assertIn(app_info.APP_SITE, html)
        self.assertIn(app_info.APP_SITE_LABEL, html)
        self.assertTrue(self.dialog.site_label.openExternalLinks())

    def test_copyright_shown(self):
        self.assertEqual(
            self.dialog.copyright_label.text(), app_info.copyright_line()
        )

    def test_icon_is_present(self):
        self.assertFalse(self.dialog.icon_label.pixmap().isNull())

    def test_close_button_is_russian(self):
        """Подпись задаём сами: без загруженного перевода Qt она английская."""
        buttons = self.dialog.findChild(QDialogButtonBox)
        button = buttons.button(QDialogButtonBox.StandardButton.Close)
        self.assertEqual(button.text(), "Закрыть")


class TrayMenuTests(unittest.TestCase):
    """Пункт «О программе» должен быть в меню трея и вести к диалогу."""

    def _app_stub(self):
        """Меню собирается без значка в трее — только manager нужен."""
        from app import App

        stub = App.__new__(App)
        stub.manager = type("Manager", (), {"create_note": lambda self: None})()
        return stub

    def _labels(self, menu):
        return [action.text() for action in menu.actions()]

    def test_menu_has_about_item(self):
        menu = self._app_stub()._build_tray_menu()
        try:
            self.assertIn("О программе", self._labels(menu))
        finally:
            menu.deleteLater()

    def test_about_item_sits_next_to_exit(self):
        menu = self._app_stub()._build_tray_menu()
        try:
            labels = self._labels(menu)
            self.assertEqual(labels[-1], "Выход")
            self.assertEqual(labels[-2], "О программе")
        finally:
            menu.deleteLater()

    def test_about_item_opens_the_dialog(self):
        """Проверяем действием, а не заглядыванием в соединения.

        Подменяем обработчик ДО сборки меню: соединение берёт ссылку в момент
        сборки, поэтому подмена после неё уже ни на что не повлияет.
        """
        stub = self._app_stub()
        calls = []
        stub._open_about = lambda: calls.append(True)

        menu = stub._build_tray_menu()
        try:
            action = [
                a for a in menu.actions() if a.text() == "О программе"
            ][0]
            action.trigger()
            self.assertEqual(calls, [True])
        finally:
            menu.deleteLater()


if __name__ == "__main__":
    unittest.main()
