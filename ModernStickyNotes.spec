# -*- mode: python ; coding: utf-8 -*-
import os

import PySide6

# Русский перевод служебных строк Qt (диалог выбора цвета, кнопки Qt).
# Кладём туда же, где PySide6 держит translations: main.py ищет файл именно
# по <_MEIPASS>/PySide6/translations, когда QLibraryInfo указывает в пустоту.
_QT_RU = os.path.join(
    os.path.dirname(PySide6.__file__), 'translations', 'qtbase_ru.qm'
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('Noteit.ico', '.'), (_QT_RU, 'PySide6/translations')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# Папочная сборка (onedir), а не одиночный exe (onefile). Это не вкусовщина:
# в режиме onefile загрузчик PyInstaller распаковывает Python и все библиотеки
# во временный каталог %TEMP%\_MEIxxxxx и запускает код оттуда. Для поведенческой
# эвристики антивируса это классическая картина упакованного вредоноса — именно
# на неё срабатывал Kaspersky («PDM:Trojan.Win32.Generic») на dist\Stickio.exe.
# В режиме onedir распаковки нет: библиотеки лежат рядом с exe и грузятся с диска.
# Цена — вместо одного файла каталог, но его всё равно ставит инсталлятор.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Stickio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX выключен осознанно: сжатие исполняемого файла — самостоятельный
    # признак для эвристики, ради которого не стоит экономить мегабайты.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Noteit.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Stickio',
)
