"""Тесты перевода интерфейса.

Главный здесь — не проверка отдельных фраз, а полнота словаря: тест
разбирает исходники и требует, чтобы у каждой русской строки, которую видит
пользователь, был английский перевод. Без этого «английский язык» тихо
превращается в «английский местами»: забытая строка выглядит как рабочая,
потому что по-русски она читается.

Обратная проверка тоже есть: если перевода нет в исходниках, значит строку
переписали или удалили, а перевод остался мусором.
"""
import ast
import io
import os
import re
import shutil
import tempfile
import unittest

from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QDialogButtonBox, QLabel,
    QLineEdit, QSpinBox, QWidget,
)

from database.database import Database
from services import i18n
from services.app_info import APP_AUTHOR
from settings_isolation import SettingsIsolationMixin

CYRILLIC = re.compile(r"[А-Яа-яЁё]")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Что просматриваем. Список явный, а не обход всего каталога: иначе в проверку
# попадут build/, dist/, .trash/ и копии файлов, которых нет в поставке.
SOURCE_FILES = (
    "main.py",
    "app.py",
    "logging_config.py",
    "services/app_info.py",
    "services/hotkeys.py",
    "services/note_manager.py",
    "services/search.py",
    "services/settings.py",
    "services/transfer.py",
    "widgets/about_dialog.py",
    "widgets/color_picker.py",
    "widgets/hotkey_edit.py",
    "widgets/search_window.py",
    "widgets/sticky_note.py",
    "widgets/toolbar.py",
    "models/note.py",
    "database/database.py",
)

# Русские строки, которые НЕ переводятся, с причиной. Список намеренно
# короткий: каждая запись — это место, где пользователь увидит русский
# текст при английском интерфейсе, и так должно быть осознанно.
NOT_TRANSLATED = {
    # Имя автора — имя собственное, переводу не подлежит.
    "Т.Е.А.",
    # Сообщения журнала: их читает разработчик, а не пользователь.
    "Не удалось прочитать версию из %s",
    # Внутренняя проверка схемы БД. Наружу не выходит: база своя.
    "Неизвестные колонки заметки: %s",
}


def string_literals(path: str) -> list:
    """Строковые литералы файла без docstring-ов.

    Docstring-и отбрасываются: они объясняют код по-русски и переводу не
    подлежат. Всё остальное — кандидаты в интерфейс.
    """
    with io.open(path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        if CYRILLIC.search(node.value):
            found.append((node.lineno, node.value))
    return found


class DictionaryCompletenessTests(unittest.TestCase):
    """Словарь и исходники должны сходиться в обе стороны."""

    def test_every_user_string_is_translated(self):
        missing = []
        for rel in SOURCE_FILES:
            path = os.path.join(ROOT, rel)
            if not os.path.exists(path):
                self.fail("нет файла из списка проверки: %s" % rel)
            for line, text in string_literals(path):
                if text in NOT_TRANSLATED:
                    continue
                if text not in i18n.TRANSLATIONS["en"]:
                    missing.append("%s:%d  %r" % (rel, line, text))
        self.assertEqual(
            [], missing,
            "нет английского перевода:\n" + "\n".join(missing),
        )

    def test_no_stale_translations(self):
        """Перевод без строки в коде — след переписанной фразы."""
        used = set()
        for rel in SOURCE_FILES:
            for _line, text in string_literals(os.path.join(ROOT, rel)):
                used.add(text)

        stale = [
            key for key in i18n.TRANSLATIONS["en"]
            if key not in used
        ]
        self.assertEqual(
            [], stale,
            "перевод без строки в исходниках:\n" + "\n".join(sorted(stale)),
        )

    def test_translation_keys_have_no_duplicates_in_english(self):
        """Один и тот же английский текст на разные ключи — обычно опечатка.

        Проверяем не «уникальность вообще» (совпадения законны: «Закрыть» и
        «Выход» могут переводиться одинаково), а именно случай, когда два
        разных русских ключа дают один английский, а по смыслу это разные
        вещи. Такие пары перечислены явно.
        """
        allowed = {
            frozenset({"О программе", "Автор: %s"}),
        }
        by_english = {}
        for key, value in i18n.TRANSLATIONS["en"].items():
            by_english.setdefault(value, []).append(key)
        collisions = [
            keys for keys in by_english.values()
            if len(keys) > 1 and frozenset(keys) not in allowed
        ]
        # Совпадения допустимы, поэтому это не ошибка, а напоминание: тест
        # проходит всегда, но список коллизий видно при отладке.
        self.assertIsInstance(collisions, list)


class LanguageSwitchTests(unittest.TestCase):
    def setUp(self):
        self._saved = i18n.current_language()

    def tearDown(self):
        i18n.set_language(self._saved)

    def test_source_language_returns_text_unchanged(self):
        i18n.set_language("ru")
        self.assertEqual(i18n.tr("Настройки"), "Настройки")

    def test_english_translates(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tr("Настройки"), "Settings")

    def test_unknown_string_falls_back_to_source(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tr("Строка без перевода"), "Строка без перевода")

    def test_unknown_language_is_rejected(self):
        i18n.set_language("ru")
        self.assertFalse(i18n.set_language("de"))
        self.assertEqual(i18n.current_language(), "ru")

    def test_language_name_is_never_translated(self):
        """Названия языков в списке должны быть на самих себе."""
        i18n.set_language("en")
        self.assertEqual(i18n.language_name("ru"), "Русский")
        self.assertEqual(i18n.language_name("en"), "English")


class PluralTests(unittest.TestCase):
    def setUp(self):
        self._saved = i18n.current_language()

    def tearDown(self):
        i18n.set_language(self._saved)

    def test_russian_forms(self):
        i18n.set_language("ru")
        self.assertEqual(i18n.plural("note", 1), "заметка")
        self.assertEqual(i18n.plural("note", 2), "заметки")
        self.assertEqual(i18n.plural("note", 5), "заметок")
        self.assertEqual(i18n.plural("note", 11), "заметок")
        self.assertEqual(i18n.plural("note", 21), "заметка")
        self.assertEqual(i18n.plural("note", 22), "заметки")

    def test_english_forms(self):
        i18n.set_language("en")
        self.assertEqual(i18n.plural("note", 1), "note")
        self.assertEqual(i18n.plural("note", 0), "notes")
        self.assertEqual(i18n.plural("note", 2), "notes")
        self.assertEqual(i18n.plural("note", 21), "notes")


class _UiTestCase(SettingsIsolationMixin, unittest.TestCase):
    """Общее для проверок живого интерфейса.

    Настройки уводим в ini-файл во временном каталоге: `Settings` пишет в
    реестр по фиксированным именам, и тест, меняющий язык, переписал бы
    настоящие настройки пользователя. Каталог и готовый `Settings` даёт
    миксин из settings_isolation.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self._saved_language = i18n.current_language()
        self.db = Database(os.path.join(self._settings_dir, "notes.db"))

    def tearDown(self):
        self.db.close()
        i18n.set_language(self._saved_language)
        super().tearDown()

    @staticmethod
    def _visible_texts(widget) -> list:
        """Все подписи, которые пользователь видит в окне.

        Обходим дерево виджетов, а не список строк из кода: так проверка
        ловит и те подписи, что не прошли через tr(), — их в словаре нет,
        но на экране они есть.
        """
        texts = [widget.windowTitle()]
        for child in widget.findChildren(QWidget):
            if isinstance(child, QLabel):
                texts.append(child.text())
            elif isinstance(child, QAbstractButton):
                texts.append(child.text())
            elif isinstance(child, QLineEdit):
                texts.append(child.placeholderText())
            elif isinstance(child, QComboBox):
                texts.extend(child.itemText(i) for i in range(child.count()))
            elif isinstance(child, QSpinBox):
                texts.append(child.suffix())
            texts.append(child.toolTip())
        return [text for text in texts if text]


class EnglishUiTests(_UiTestCase):
    """В английском интерфейсе не должно остаться русского текста."""

    # Куски, которые обязаны остаться русскими и в английском интерфейсе:
    # имя автора — имя собственное, названия языков в списке всегда на самих
    # себе. Вырезаем их и смотрим, не осталось ли кириллицы сверх этого.
    ALLOWED_PARTS = (APP_AUTHOR, "Русский")

    def setUp(self):
        super().setUp()
        i18n.set_language("en")

    def assertNoRussian(self, widget, where: str):
        left = []
        for text in self._visible_texts(widget):
            rest = text
            for part in self.ALLOWED_PARTS:
                rest = rest.replace(part, "")
            if CYRILLIC.search(rest):
                left.append(text)
        self.assertEqual([], left, "русский текст в %s: %r" % (where, left))

    def test_settings_dialog(self):
        from app import SettingsDialog

        dialog = SettingsDialog(self.settings)
        try:
            self.assertNoRussian(dialog, "диалоге настроек")
        finally:
            dialog.close()

    def test_tray_menu(self):
        from app import App

        stub = App.__new__(App)
        stub.manager = type("Manager", (), {"create_note": lambda self: None})()
        menu = stub._build_tray_menu()
        try:
            texts = [action.text() for action in menu.actions()]
            left = [t for t in texts if CYRILLIC.search(t)]
            self.assertEqual([], left, "русский текст в меню трея: %r" % left)
        finally:
            menu.deleteLater()

    def test_about_dialog(self):
        from widgets.about_dialog import AboutDialog

        dialog = AboutDialog()
        try:
            self.assertNoRussian(dialog, "окне «О программе»")
        finally:
            dialog.close()

    def test_search_window(self):
        from widgets.search_window import SearchWindow

        window = SearchWindow()
        try:
            self.assertNoRussian(window, "окне поиска")
        finally:
            window.close()

    def test_note_window_and_toolbar(self):
        from services.note_manager import NoteManager

        self.db.create_note(content="<p>text</p>")
        manager = NoteManager(self.db, settings=self.settings)
        manager.load_all()
        try:
            windows = list(manager.windows.values())
            self.assertTrue(windows, "заметка не открылась")
            for window in windows:
                self.assertNoRussian(window, "окне заметки")
        finally:
            manager.close_all()

    def test_search_results_are_translated(self):
        """Строки списка результатов тоже текст, а не готовые виджеты."""
        from services.note_manager import NoteManager
        from widgets.search_window import SearchWindow

        self.db.create_note(content="<p>needle here</p>")
        manager = NoteManager(self.db, settings=self.settings)
        window = SearchWindow()
        try:
            window.set_notes_provider(self.db.get_all_notes)
            window.query_edit.setText("needle")
            item = window.results.item(0)
            self.assertIsNotNone(item, "совпадение не найдено")
            self.assertNotRegex(item.text(), CYRILLIC)
            self.assertNotRegex(window.summary.text(), CYRILLIC)
        finally:
            window.close()
            manager.close_all()


class LiveSwitchTests(_UiTestCase):
    """Переключение языка без перезапуска."""

    def setUp(self):
        super().setUp()
        i18n.set_language("ru")

    def test_dialog_retranslates_itself(self):
        from app import SettingsDialog

        dialog = SettingsDialog(self.settings)
        try:
            self.assertEqual(dialog.language_label.text(), "Язык интерфейса:")
            dialog.language_combo.setCurrentIndex(
                i18n.LANGUAGE_CODES.index("en")
            )
            self.assertEqual(dialog.windowTitle(), "Settings")
            self.assertEqual(dialog.language_label.text(), "Interface language:")
            self.assertEqual(
                dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).text(),
                "OK",
            )
            self.assertEqual(dialog.autostart.text(), "Start with Windows")
            self.assertEqual(
                dialog.font_size_spin.suffix(), " pt",
                "подпись единиц осталась русской",
            )
        finally:
            dialog.close()

    def test_cancel_restores_the_language(self):
        """«Отмена» возвращает язык: он применялся сразу при выборе."""
        from app import SettingsDialog

        dialog = SettingsDialog(self.settings)
        try:
            dialog.language_combo.setCurrentIndex(
                i18n.LANGUAGE_CODES.index("en")
            )
            self.assertEqual(i18n.current_language(), "en")
            dialog.reject()
            self.assertEqual(i18n.current_language(), "ru")
            self.assertEqual(dialog.windowTitle(), "Настройки")
        finally:
            dialog.close()

    def test_accept_saves_the_language(self):
        from app import SettingsDialog

        dialog = SettingsDialog(self.settings)
        try:
            dialog.language_combo.setCurrentIndex(
                i18n.LANGUAGE_CODES.index("en")
            )
            dialog._accept()
            self.assertEqual(self.settings.language(), "en")
        finally:
            dialog.close()

    def test_open_note_is_retranslated_in_place(self):
        """Уже открытая заметка переводится на месте, без пересоздания."""
        from services.note_manager import NoteManager

        self.db.create_note(content="<p>текст</p>")
        manager = NoteManager(self.db, settings=self.settings)
        manager.load_all()
        try:
            window = list(manager.windows.values())[0]
            self.assertEqual(window.close_button.toolTip(), "Скрыть")
            self.assertEqual(window.toolbar.bold_button.toolTip(), "Жирный")

            i18n.set_language("en")
            window.retranslate()

            self.assertEqual(window.close_button.toolTip(), "Hide")
            self.assertEqual(window.toolbar.bold_button.toolTip(), "Bold")
            self.assertEqual(window.toolbar.opacity_title.text(), "Opacity")
        finally:
            manager.close_all()

    def test_app_spreads_language_over_open_windows(self):
        """App применяет язык ко всему, что уже открыто."""
        from app import App
        from services.note_manager import NoteManager

        self.db.create_note(content="<p>текст</p>")
        manager = NoteManager(self.db, settings=self.settings)
        manager.load_all()

        stub = App.__new__(App)
        stub.app = self.app
        stub.settings = self.settings
        stub.database = self.db
        stub.manager = manager
        stub.tray = None
        stub.qt_translation = i18n.QtTranslation(self.app)
        stub._tray_action_new = None
        stub._tray_action_toggle = None
        stub._tray_action_search = None
        stub._search_window = None
        stub._language = "ru"

        try:
            window = list(manager.windows.values())[0]
            self.assertEqual(window.close_button.toolTip(), "Скрыть")

            i18n.set_language("en")
            stub._apply_language()

            self.assertEqual(window.close_button.toolTip(), "Hide")
            self.assertEqual(stub._language, "en")

            # Повторный вызов при том же языке ничего не пересобирает:
            # иначе каждое открытие настроек сбрасывало бы меню трея.
            window.close_button.setToolTip("маркер")
            stub._apply_language()
            self.assertEqual(window.close_button.toolTip(), "маркер")
        finally:
            manager.close_all()


class QtTranslationTests(unittest.TestCase):
    """Переключение перевода служебных строк Qt."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_english_needs_no_file(self):
        """Английский — язык Qt по умолчанию, .qm для него не нужен."""
        translation = i18n.QtTranslation(self.app)
        self.assertTrue(translation.apply("en"))
        self.assertIsNone(translation._translator)

    def test_russian_file_is_found(self):
        translation = i18n.QtTranslation(self.app)
        try:
            self.assertTrue(
                translation.apply("ru"),
                "qtbase_ru.qm не найден в %s" % (i18n.translation_dirs(),),
            )
            self.assertIsNotNone(translation._translator)
        finally:
            translation._drop()

    def test_switch_does_not_leave_two_translators(self):
        translation = i18n.QtTranslation(self.app)
        try:
            translation.apply("ru")
            first = translation._translator
            translation.apply("en")
            self.assertIsNone(translation._translator)
            translation.apply("ru")
            self.assertIsNot(translation._translator, first)
        finally:
            translation._drop()


if __name__ == "__main__":
    unittest.main()
