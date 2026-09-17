"""Изоляция настроек: тесты пишут в ini во временном каталоге, не в реестр.

Повод. В тестах был такой приём:

    QCoreApplication.setOrganizationName("StickioTest")
    QCoreApplication.setApplicationName("HotkeySettingsTests")
    self.settings = Settings()
    self.settings.settings.clear()

Задумано это было верно — «свой файл настроек, чтобы не трогать
пользовательские». Но не работало: QSettings в `Settings` создаётся
с зашитыми именами («Stickio», «Stickio»), а на явно созданный QSettings
имена из QCoreApplication не влияют вовсе. То есть тест обращался
к настоящей ветке `HKCU\\Software\\Stickio\\Stickio` и в setUp/tearDown
её очищал.

Снаружи это выглядело так: прогнал тесты — и в Stickio сбросились
комбинации клавиш, вид новой заметки, интервал автосохранения, язык
и галочка автозапуска. Причём незаметно: тесты-то проходили.

Как правильно — `Settings(storage)`, где storage указывает на ini-файл
в отдельном временном каталоге. Готовый миксин ниже делает это сам.
"""
import os
import shutil
import tempfile

from PySide6.QtCore import QSettings

from services.settings import Settings


def isolated_settings(directory) -> Settings:
    """Settings, который пишет в settings.ini внутри указанного каталога.

    Каталог должен существовать; убирать его — забота вызывающего.
    """
    return Settings(QSettings(
        os.path.join(directory, "settings.ini"), QSettings.Format.IniFormat
    ))


class SettingsIsolationMixin:
    """Даёт тесту `self.settings` в отдельном каталоге и убирает за собой.

    Подмешивается перед unittest.TestCase:

        class SomeTests(SettingsIsolationMixin, unittest.TestCase):

    Свой setUp в классе-наследнике, если он нужен, обязан звать
    `super().setUp()` — иначе изоляции не будет. Если своего setUp нет,
    ничего писать не надо: всё делает миксин.
    """

    def setUp(self):
        super().setUp()
        self._settings_dir = tempfile.mkdtemp(prefix="stickio-settings-")
        self.settings = isolated_settings(self._settings_dir)

    def tearDown(self):
        # Каталог свой у каждого теста, поэтому чистить значения не нужно —
        # достаточно убрать файл целиком.
        shutil.rmtree(self._settings_dir, ignore_errors=True)
        super().tearDown()
