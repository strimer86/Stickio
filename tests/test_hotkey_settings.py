"""Тесты настраиваемых горячих клавиш.

Проверяется то, что решает корректность переназначения: канонический вид
комбинации (иначе «ctrl+shift+n» и «Shift+Ctrl+N» считались бы разными),
захват нажатия из Qt-события и чтение/запись настроек.
"""
import unittest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from services.hotkeys import HotkeyError, key_name, normalize_shortcut
from services.settings import DEFAULT_HOTKEYS
from settings_isolation import SettingsIsolationMixin
from widgets.hotkey_edit import (
    HotkeyEdit, qt_key_name, qt_key_to_shortcut, qt_modifiers_names,
)

# QApplication, а не QCoreApplication: часть тестов ниже создаёт виджеты.
_app = QApplication.instance() or QApplication([])


class NormalizeShortcutTests(unittest.TestCase):
    def test_canonical_order(self):
        self.assertEqual(normalize_shortcut("Shift+Ctrl+N"), "Ctrl+Shift+N")

    def test_lowercase_becomes_uppercase(self):
        self.assertEqual(normalize_shortcut("ctrl+shift+n"), "Ctrl+Shift+N")

    def test_all_modifiers_in_fixed_order(self):
        self.assertEqual(
            normalize_shortcut("Win+Alt+Shift+Ctrl+K"), "Ctrl+Alt+Shift+Win+K"
        )

    def test_special_key_keeps_readable_name(self):
        self.assertEqual(normalize_shortcut("Ctrl+Alt+PageDown"), "Ctrl+Alt+PageDown")
        self.assertEqual(normalize_shortcut("Ctrl+F5"), "Ctrl+F5")

    def test_invalid_input_raises(self):
        for bad in ("N", "Ctrl+", "Ctrl+Ф", "Ctrl+Shift+"):
            with self.assertRaises(HotkeyError):
                normalize_shortcut(bad)

    def test_normalize_is_idempotent(self):
        once = normalize_shortcut("shift+alt+j")
        self.assertEqual(normalize_shortcut(once), once)

    def test_key_name_rejects_garbage(self):
        self.assertEqual(key_name(ord("Q")), "Q")
        with self.assertRaises(HotkeyError):
            key_name(0x1000)


class QtCaptureTests(unittest.TestCase):
    """Чистые функции захвата — без создания виджетов."""

    def test_letter_with_modifiers(self):
        modifiers = (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        )
        shortcut, error = qt_key_to_shortcut(Qt.Key.Key_N, modifiers)
        self.assertEqual(shortcut, "Ctrl+Shift+N")
        self.assertEqual(error, "")

    def test_without_modifier_rejected(self):
        shortcut, error = qt_key_to_shortcut(
            Qt.Key.Key_N, Qt.KeyboardModifier.NoModifier
        )
        self.assertEqual(shortcut, "")
        self.assertTrue("модификатор" in error.lower())

    def test_service_keys_rejected(self):
        modifiers = Qt.KeyboardModifier.ControlModifier
        for key in (Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Return):
            shortcut, _ = qt_key_to_shortcut(key, modifiers)
            self.assertEqual(shortcut, "")

    def test_cyrillic_rejected(self):
        # ord('Ф') — не виртуальный код клавиши, RegisterHotKey принял бы мусор
        self.assertIsNone(qt_key_name(ord("Ф")))

    def test_digits_and_f_keys(self):
        ctrl = Qt.KeyboardModifier.ControlModifier
        self.assertEqual(qt_key_to_shortcut(Qt.Key.Key_1, ctrl)[0], "Ctrl+1")
        self.assertEqual(qt_key_to_shortcut(Qt.Key.Key_F12, ctrl)[0], "Ctrl+F12")

    def test_modifier_order_and_win_key(self):
        modifiers = (
            Qt.KeyboardModifier.MetaModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
        )
        self.assertEqual(
            qt_modifiers_names(modifiers), ["Ctrl", "Alt", "Win"]
        )


class HotkeySettingsTests(SettingsIsolationMixin, unittest.TestCase):
    # Настройки пишутся в ini во временном каталоге — см. settings_isolation.
    # Раньше здесь стоял setOrganizationName("StickioTest") «чтобы тесты
    # не трогали пользовательские», но на зашитые имена в Settings он не
    # влияет: тест чистил настоящую ветку реестра.

    def test_defaults_when_nothing_saved(self):
        self.assertEqual(self.settings.hotkeys(), DEFAULT_HOTKEYS)

    def test_roundtrip(self):
        self.settings.set_hotkeys(
            {"new_note": "Ctrl+Alt+Q", "toggle_visibility": "Ctrl+Shift+Space"}
        )
        self.assertEqual(self.settings.hotkeys()["new_note"], "Ctrl+Alt+Q")
        self.assertEqual(
            self.settings.hotkeys()["toggle_visibility"], "Ctrl+Shift+Space"
        )

    def test_empty_value_disables_hotkey(self):
        self.settings.set_hotkeys({"new_note": "", "toggle_visibility": "Ctrl+Alt+Z"})
        saved = self.settings.hotkeys()
        self.assertNotIn("new_note", saved)
        self.assertEqual(saved["toggle_visibility"], "Ctrl+Alt+Z")

    def test_unknown_action_is_dropped(self):
        """Старые записи удалённых действий не должны всплывать в UI."""
        self.settings.set_hotkeys(
            {"new_note": "Ctrl+Alt+Q", "toggle_visibility": "Ctrl+Alt+W"}
        )
        self.settings.settings.setValue("hotkeys/removed_action", "Ctrl+Alt+X")
        self.assertEqual(set(self.settings.hotkeys()), set(DEFAULT_HOTKEYS))

    def test_disabling_then_enabling_again(self):
        """Снятие комбинации обязано переживать перезапуск настроек."""
        self.settings.set_hotkeys({"new_note": ""})
        self.assertNotIn("new_note", self.settings.hotkeys())
        self.settings.set_hotkeys({"new_note": "Ctrl+Alt+Q"})
        self.assertEqual(self.settings.hotkeys()["new_note"], "Ctrl+Alt+Q")

    def test_values_are_stripped(self):
        self.settings.set_hotkeys({"new_note": "  Ctrl+Alt+Q  "})
        self.assertEqual(self.settings.hotkeys()["new_note"], "Ctrl+Alt+Q")


def _press(edit: HotkeyEdit, key, modifiers=Qt.KeyboardModifier.NoModifier):
    """Имитирует нажатие без событийного цикла."""
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
    edit.keyPressEvent(event)


class HotkeyEditTests(unittest.TestCase):
    def setUp(self):
        self.edit = HotkeyEdit()
        self.rejected = []
        self.edit.rejected.connect(self.rejected.append)

    def test_set_and_read(self):
        self.edit.set_shortcut("Ctrl+Alt+Q")
        self.assertEqual(self.edit.shortcut(), "Ctrl+Alt+Q")

    def test_captures_combination(self):
        _press(
            self.edit,
            Qt.Key.Key_N,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        self.assertEqual(self.edit.shortcut(), "Ctrl+Shift+N")

    def test_plain_letter_rejected_and_value_kept(self):
        self.edit.set_shortcut("Ctrl+Alt+Q")
        _press(self.edit, Qt.Key.Key_N)
        self.assertEqual(self.edit.shortcut(), "Ctrl+Alt+Q")
        self.assertEqual(len(self.rejected), 1)

    def test_backspace_clears(self):
        self.edit.set_shortcut("Ctrl+Alt+Q")
        _press(self.edit, Qt.Key.Key_Backspace)
        self.assertEqual(self.edit.shortcut(), "")


class SettingsDialogTests(SettingsIsolationMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.warnings = []
        # Модальный QMessageBox в тесте бы завис — подменяем статический метод
        self._orig_warning = QMessageBox.warning
        QMessageBox.warning = staticmethod(
            lambda *args, **kwargs: self.warnings.append(args[2])
        )

    def tearDown(self):
        QMessageBox.warning = self._orig_warning
        super().tearDown()

    def _dialog(self):
        from app import SettingsDialog

        return SettingsDialog(self.settings)

    def test_fields_show_saved_values(self):
        self.settings.set_hotkeys({"new_note": "Ctrl+Alt+Q"})
        dialog = self._dialog()
        self.assertEqual(
            dialog.shortcuts()["new_note"], "Ctrl+Alt+Q"
        )

    def test_accept_stores_normalized_values(self):
        dialog = self._dialog()
        dialog._edits["new_note"].set_shortcut("shift+alt+q")
        dialog._accept()
        self.assertEqual(dialog.result_shortcuts()["new_note"], "Alt+Shift+Q")
        self.assertEqual(self.warnings, [])

    def test_duplicate_is_refused(self):
        dialog = self._dialog()
        dialog._edits["new_note"].set_shortcut("Ctrl+Alt+Q")
        dialog._edits["toggle_visibility"].set_shortcut("Ctrl+Alt+Q")
        dialog._accept()
        self.assertEqual(len(self.warnings), 1)
        self.assertIn("дважды", self.warnings[0])
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_empty_is_allowed(self):
        dialog = self._dialog()
        dialog._edits["new_note"].set_shortcut("")
        dialog._accept()
        self.assertEqual(dialog.result_shortcuts()["new_note"], "")
        self.assertEqual(self.warnings, [])

    def test_buttons_are_russian(self):
        """Qt не переводит стандартные кнопки без .qm — подписи ставим сами."""
        dialog = self._dialog()
        texts = [button.text() for button in dialog.buttons.buttons()]
        self.assertIn("Отмена", texts)
        self.assertIn("По умолчанию", texts)
        for text in texts:
            self.assertTrue(
                any(ord(ch) > 127 for ch in text),
                "кнопка %r осталась английской" % text,
            )

    def test_restore_defaults(self):
        dialog = self._dialog()
        dialog._edits["new_note"].set_shortcut("Ctrl+Alt+Q")
        dialog._restore_defaults()
        self.assertEqual(
            dialog.shortcuts()["new_note"], DEFAULT_HOTKEYS["new_note"]
        )


class MenuLabelTests(unittest.TestCase):
    def test_with_shortcut(self):
        from app import menu_label

        self.assertEqual(menu_label("Новая", "Ctrl+N"), "Новая\tCtrl+N")

    def test_without_shortcut(self):
        from app import menu_label

        self.assertEqual(menu_label("Новая", ""), "Новая")


if __name__ == "__main__":
    unittest.main()
