"""Интервал автосохранения: настройка, валидация, применение к открытым заметкам."""
import os
import shutil
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from database.database import Database
from services.note_manager import NoteManager
from services.settings import (
    DEFAULT_SAVE_DELAY_MS, SAVE_DELAY_RANGE, Settings,
)

_app = QApplication.instance() or QApplication([])


class SaveDelaySettingTests(unittest.TestCase):
    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("SaveDelaySettingTests")
        self.settings = Settings()
        self.settings.settings.clear()

    def tearDown(self):
        self.settings.settings.clear()

    def test_default_when_nothing_saved(self):
        self.assertEqual(self.settings.save_delay_ms(), DEFAULT_SAVE_DELAY_MS)

    def test_roundtrip(self):
        self.settings.set_save_delay_ms(1500)
        self.assertEqual(self.settings.save_delay_ms(), 1500)

    def test_value_stays_int(self):
        """Строка из реестра сломала бы QTimer.setInterval."""
        self.settings.settings.setValue("save_delay_ms", "800")
        self.assertIsInstance(self.settings.save_delay_ms(), int)
        self.assertEqual(self.settings.save_delay_ms(), 800)

    def test_out_of_range_falls_back(self):
        low, high = SAVE_DELAY_RANGE
        for bad in (0, low - 1, high + 1, 999999, -500):
            self.settings.set_save_delay_ms(bad)
            self.assertEqual(
                self.settings.save_delay_ms(),
                DEFAULT_SAVE_DELAY_MS,
                "значение %r должно было откатиться к умолчанию" % bad,
            )

    def test_garbage_falls_back(self):
        self.settings.settings.setValue("save_delay_ms", "не число")
        self.assertEqual(self.settings.save_delay_ms(), DEFAULT_SAVE_DELAY_MS)


class NoteUsesSaveDelayTests(unittest.TestCase):
    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("NoteUsesSaveDelayTests")
        self.settings = Settings()
        self.settings.settings.clear()
        self.tmp = tempfile.mkdtemp(prefix="stickio_savedelay_")
        self.db = Database(os.path.join(self.tmp, "notes.db"))

    def tearDown(self):
        self.settings.settings.clear()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_window_takes_saved_delay(self):
        self.settings.set_save_delay_ms(1200)
        manager = NoteManager(self.db, settings=self.settings)
        try:
            window = manager.create_note()
            self.assertEqual(window._save_timer.interval(), 1200)
            self.assertTrue(window._save_timer.isSingleShot())
        finally:
            manager.close_all()

    def test_delay_can_be_changed_on_live_window(self):
        manager = NoteManager(self.db, settings=self.settings)
        try:
            window = manager.create_note()
            window.set_save_delay(2000)
            self.assertEqual(window._save_timer.interval(), 2000)
        finally:
            manager.close_all()


class SettingsDialogSaveDelayTests(unittest.TestCase):
    def setUp(self):
        QCoreApplication.setOrganizationName("StickioTest")
        QCoreApplication.setApplicationName("SettingsDialogSaveDelayTests")
        self.settings = Settings()
        self.settings.settings.clear()
        self._orig_warning = QMessageBox.warning
        QMessageBox.warning = staticmethod(lambda *args, **kwargs: None)

    def tearDown(self):
        QMessageBox.warning = self._orig_warning
        self.settings.settings.clear()

    def _dialog(self):
        from app import SettingsDialog

        return SettingsDialog(self.settings)

    def test_dialog_shows_saved_value(self):
        self.settings.set_save_delay_ms(1500)
        # Диалог держим в переменной: без ссылки он собирается сборщиком
        # мусора, и обращение к вложенному QSpinBox падает с
        # "Internal C++ object already deleted".
        dialog = self._dialog()
        self.assertEqual(dialog.save_delay_spin.value(), 1500)

    def test_spin_range_matches_settings_range(self):
        dialog = self._dialog()
        self.assertEqual(
            (dialog.save_delay_spin.minimum(), dialog.save_delay_spin.maximum()),
            SAVE_DELAY_RANGE,
        )

    def test_accept_stores_value(self):
        dialog = self._dialog()
        dialog.save_delay_spin.setValue(2500)
        dialog._accept()
        self.assertEqual(self.settings.save_delay_ms(), 2500)

    def test_restore_defaults_resets_value(self):
        dialog = self._dialog()
        dialog.save_delay_spin.setValue(2500)
        dialog._restore_defaults()
        self.assertEqual(dialog.save_delay_spin.value(), DEFAULT_SAVE_DELAY_MS)

    def test_cancel_does_not_change_value(self):
        """«Отмена» не должна применять интервал, как и остальные настройки."""
        self.settings.set_save_delay_ms(900)
        dialog = self._dialog()
        dialog.save_delay_spin.setValue(3000)
        dialog.reject()
        self.assertEqual(self.settings.save_delay_ms(), 900)


if __name__ == "__main__":
    unittest.main()
