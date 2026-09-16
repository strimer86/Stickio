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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Stickio',
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Noteit.ico',
)
