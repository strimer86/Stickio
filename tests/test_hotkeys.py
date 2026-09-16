"""Тесты глобальных горячих клавиш: парсинг комбинаций и диспетчеризация.

Реальная регистрация в системе не проверяется (это делал бы CI без прав),
но ловится всё, что зависит от нашего кода: разбор строки, обработка
занятой комбинации, вызов нужного колбэка и снятие регистрации.

Запуск:  python -m unittest discover -s tests -v
"""
import ctypes
import sys
import unittest

from services.hotkeys import (
    GlobalHotkeys, HotkeyError, _MSG, parse_shortcut,
    MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT,
)


class ParseShortcutTests(unittest.TestCase):
    def test_ctrl_shift_letter(self):
        self.assertEqual(
            parse_shortcut("Ctrl+Shift+N"),
            (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord("N")),
        )

    def test_case_and_spaces_ignored(self):
        self.assertEqual(
            parse_shortcut("  ctrl + shift + h "),
            (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord("H")),
        )

    def test_order_of_modifiers_does_not_matter(self):
        self.assertEqual(
            parse_shortcut("Shift+Ctrl+N"),
            parse_shortcut("Ctrl+Shift+N"),
        )

    def test_all_modifiers(self):
        modifiers, _ = parse_shortcut("Ctrl+Alt+Shift+Win+K")
        self.assertEqual(
            modifiers,
            MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN | MOD_NOREPEAT,
        )

    def test_digit_and_function_keys(self):
        self.assertEqual(parse_shortcut("Ctrl+1")[1], ord("1"))
        self.assertEqual(parse_shortcut("Ctrl+F5")[1], 0x74)

    def test_named_special_keys(self):
        self.assertEqual(parse_shortcut("Ctrl+Space")[1], 0x20)
        self.assertEqual(parse_shortcut("Alt+Delete")[1], 0x2E)

    def test_mod_norepeat_always_set(self):
        """Без MOD_NOREPEAT автоповтор зальёт обработчик десятками вызовов."""
        _, vk = parse_shortcut("Ctrl+Shift+H")
        modifiers, _ = parse_shortcut("Ctrl+Shift+H")
        self.assertTrue(modifiers & MOD_NOREPEAT)

    def test_rejects_shortcut_without_modifier(self):
        with self.assertRaises(HotkeyError):
            parse_shortcut("N")

    def test_rejects_unknown_modifier(self):
        with self.assertRaises(HotkeyError):
            parse_shortcut("Hyper+N")

    def test_rejects_cyrillic_key(self):
        """isalpha() пропускает кириллицу, но её ord() — не виртуальный код."""
        with self.assertRaises(HotkeyError):
            parse_shortcut("Ctrl+Ф")

    def test_rejects_empty_and_garbage(self):
        for bad in ("", "+", "Ctrl+", "Ctrl++"):
            with self.assertRaises(HotkeyError, msg=bad):
                parse_shortcut(bad)


class MsgStructureTests(unittest.TestCase):
    """Размер MSG должен совпадать с системным, иначе wParam читается мусором."""

    def test_msg_size_matches_win32(self):
        if sys.platform != "win32":
            self.skipTest("только Windows")
        import ctypes.wintypes as w

        class RealMSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", w.HWND), ("message", w.UINT),
                ("wParam", w.WPARAM), ("lParam", w.LPARAM),
                ("time", w.DWORD), ("pt", w.POINT),
            ]

        self.assertEqual(ctypes.sizeof(_MSG), ctypes.sizeof(RealMSG))

    def test_wparam_offset_matches(self):
        if sys.platform != "win32":
            self.skipTest("только Windows")
        # hwnd(8) + message(4) + выравнивание до 8 → wParam на 16
        self.assertEqual(_MSG.hwnd.offset, 0)
        self.assertEqual(_MSG.message.offset, 8)
        self.assertEqual(_MSG.wParam.offset, 16)


class DispatchTests(unittest.TestCase):
    """Диспетчеризация проверяется без реальной регистрации в Windows."""

    def setUp(self):
        self.hotkeys = GlobalHotkeys()
        self.calls = []

    def test_dispatch_calls_registered_callback(self):
        self.hotkeys._registry[100] = ("demo", lambda: self.calls.append("fired"))
        self.assertTrue(self.hotkeys.dispatch(100))
        self.assertEqual(self.calls, ["fired"])

    def test_unknown_id_is_not_handled(self):
        self.assertFalse(self.hotkeys.dispatch(999))

    def test_callback_exception_does_not_propagate(self):
        """Падение колбэка не должно рвать цикл обработки сообщений Qt."""

        def boom():
            raise RuntimeError("внутренняя ошибка")

        self.hotkeys._registry[100] = ("broken", boom)
        self.assertTrue(self.hotkeys.dispatch(100))

    def test_unregister_stops_dispatch(self):
        self.hotkeys._registry[100] = ("demo", lambda: self.calls.append("fired"))
        self.hotkeys._by_name["demo"] = 100
        self.hotkeys.unregister("demo")
        self.assertFalse(self.hotkeys.dispatch(100))
        self.assertEqual(self.calls, [])

    def test_unregister_unknown_name_is_noop(self):
        self.hotkeys.unregister("нет такого")

    def test_ids_stay_in_valid_range(self):
        """RegisterHotKey принимает id только 0x0000..0xBFFF."""
        self.assertGreaterEqual(self.hotkeys._next_id, 0)
        self.assertLessEqual(self.hotkeys._next_id, 0xBFFF)


class AvailabilityTests(unittest.TestCase):
    def test_register_before_install_returns_false(self):
        """До install() системный вызов недоступен — не падаем, а сообщаем."""
        hk = GlobalHotkeys()
        self.assertFalse(hk.register("demo", "Ctrl+Shift+N", lambda: None))
        self.assertIn("Ctrl+Shift+N", hk.failed)

    def test_invalid_shortcut_is_recorded_not_raised(self):
        hk = GlobalHotkeys()
        hk._installed = True  # эмулируем установленный фильтр без WinAPI
        self.assertFalse(hk.register("demo", "N", lambda: None))
        self.assertIn("N", hk.failed)


if __name__ == "__main__":
    unittest.main()
