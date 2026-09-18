"""Перевод интерфейса: русский (исходный) и английский.

Почему словарём в Python, а не .ts/.qm через lupdate
----------------------------------------------------
Штатный путь Qt — обернуть строки в tr(), прогнать lupdate, перевести
получившийся .ts в Qt Linguist и собрать .qm при каждой сборке. Для двух
языков и одного разработчика это даёт больше работы, чем пользы: .ts — это
XML на сотни строк, который правится руками, а lupdate надо не забыть
запустить. Словарь в Python делает то же самое, но целиком виден в диффе
и проверяется тестом (tests/test_i18n.py сверяет его с исходниками), а в
сборку не добавляет ни одного шага.

Русский — ИСХОДНЫЙ язык: строки в коде остаются русскими, словарь держит
только перевод на английский. Поэтому забытая строка не ломает русский
интерфейс — она просто остаётся русской, и это ловит тест полноты.

Служебные строки Qt (диалог выбора цвета, стандартное меню редактора,
кнопки QMessageBox) переводятся отдельно — файлом qtbase_<язык>.qm. Для
английского файл не нужен: английский у Qt язык по умолчанию.

Qt здесь импортируется ЛЕНИВО (внутри функций). Модуль подключают в том
числе `services/hotkeys.py` — чистый Win32-модуль без Qt, и затаскивать в
него графическую библиотеку на импорте незачем.
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Язык, на котором написаны строки в коде. Совпадает с языком по умолчанию
# для тех, у кого настройка ещё не сохранена.
SOURCE_LANGUAGE = "ru"

# Порядок задаёт порядок пунктов в выпадающем списке настроек.
LANGUAGES = (
    ("ru", "Русский"),
    ("en", "English"),
)
LANGUAGE_CODES = tuple(code for code, _ in LANGUAGES)

# Формы слова для числа. Ключ — условное имя слова, а не сама строка: саму
# строку переводит словарь, а форму выбирает правило языка.
#
# Русский: три формы, и правило не сводится к «1 — одна, остальное — много»:
# 2, 3, 4 и 22 — «заметки», но 11..14 — «заметок» (второй десяток ведёт себя
# как исключение). Английский: две формы, всё просто.
PLURAL_FORMS = {
    "note": {
        "ru": ("заметка", "заметки", "заметок"),
        "en": ("note", "notes"),
    },
}

_active = SOURCE_LANGUAGE


# --- язык ---------------------------------------------------------------

def current_language() -> str:
    """Код языка, на котором сейчас говорит интерфейс."""
    return _active


def set_language(code: str) -> bool:
    """Переключает язык. False — код неизвестен, язык не менялся.

    Только меняет язык: ни в настройки, ни в Qt ничего не пишет. Кто и
    когда сохраняет выбор и перерисовывает окна — решает вызывающий
    (app.py), потому что «применить» и «запомнить» — разные вещи: диалог
    настроек применяет язык сразу, а при «Отмене» его откатывают.
    """
    global _active
    if code not in LANGUAGE_CODES:
        logger.warning("Unknown language %r, keeping %s", code, _active)
        return False
    if code != _active:
        logger.info("Language switched: %s -> %s", _active, code)
    _active = code
    return True


def language_name(code: str) -> str:
    """Название языка для списка в настройках. Всегда на самом языке."""
    for known, name in LANGUAGES:
        if known == code:
            return name
    return code


def system_language() -> str:
    """Язык системы, если он у нас есть. Иначе — исходный.

    Нужен только при первом запуске: дальше выбор пользователя уже
    сохранён, и подстраиваться под систему нельзя — человек мог специально
    поставить другой язык.
    """
    from PySide6.QtCore import QLocale

    for tag in QLocale.system().uiLanguages():
        code = tag.split("-")[0].lower()
        if code in LANGUAGE_CODES:
            return code
    return SOURCE_LANGUAGE


# --- перевод строк ------------------------------------------------------

def tr(text: str) -> str:
    """Перевод строки. Строки нет в словаре — возвращается как есть.

    Отсутствие перевода не ошибка: русский — исходный язык, и непереведённая
    строка остаётся читаемой. За тем, чтобы таких не было, следит
    tests/test_i18n.py.
    """
    if _active == SOURCE_LANGUAGE:
        return text
    catalog = TRANSLATIONS.get(_active)
    if not catalog:
        return text
    return catalog.get(text, text)


def plural(key: str, count: int) -> str:
    """Форма слова `key` для числа `count` по правилам текущего языка."""
    forms = PLURAL_FORMS[key]
    language = _active if _active in forms else SOURCE_LANGUAGE
    forms = forms[language]
    count = abs(int(count))

    if language == "ru":
        if count % 10 == 1 and count % 100 != 11:
            index = 0
        elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
            index = 1
        else:
            index = 2
    else:
        index = 0 if count == 1 else 1
    return forms[index]


# --- служебные строки Qt ------------------------------------------------

def translation_dirs() -> list:
    """Каталоги, где ищем qtbase_<язык>.qm.

    В собранном приложении `QLibraryInfo` обычно отдаёт путь, которого рядом
    с exe нет, поэтому вторым кандидатом идёт распакованная PySide6 — именно
    туда PyInstaller кладёт translations, если они добавлены в .spec.
    """
    from PySide6.QtCore import QLibraryInfo

    dirs = []
    try:
        dirs.append(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    except Exception:
        logger.exception("Failed to locate Qt translations path")

    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.append(os.path.join(base, "PySide6", "translations"))
    return dirs


class QtTranslation:
    """Перевод служебных строк Qt, который можно переключать на ходу.

    Держит загруженный QTranslator и снимает его перед установкой нового:
    два перевода одновременно дали бы смесь языков, а removeTranslator без
    сохранённой ссылки невозможен.
    """

    def __init__(self, app):
        self._app = app
        self._translator = None

    def apply(self, code: str) -> bool:
        """Ставит перевод для языка `code`. False — файла перевода нет."""
        self._drop()
        if code == "en":
            # Английский у Qt язык по умолчанию: файла для него не существует,
            # и снятого русского перевода уже достаточно.
            return True

        from PySide6.QtCore import QTranslator

        name = "qtbase_%s" % code
        for directory in translation_dirs():
            translator = QTranslator(self._app)
            if translator.load(name, directory):
                self._app.installTranslator(translator)
                self._translator = translator
                logger.info("Qt translation %s loaded from %s", name, directory)
                return True
            translator.deleteLater()
        # Не повод падать: без .qm остаются строки Qt по умолчанию.
        logger.warning("Qt translation %s not found in %s", name, translation_dirs())
        return False

    def _drop(self):
        if self._translator is not None:
            self._app.removeTranslator(self._translator)
            self._translator.deleteLater()
            self._translator = None


# --- словарь ------------------------------------------------------------
#
# Ключ — строка ровно в том виде, в каком она стоит в коде (включая
# переносы \n и подстановки %s/%d/%r). Изменишь русский текст — перевод
# перестанет находиться, и это заметит тест полноты.

TRANSLATIONS = {
    "en": {
        # --- main.py ---
        "Не удалось запустить приложение (мьютекс).":
            "Could not start the application (mutex).",
        "Не удалось запустить приложение.\n"
        "Подробности — в журнале logs/stickio.log.":
            "Could not start the application.\n"
            "See logs/stickio.log for details.",

        # --- app.py: диалог настроек ---
        "Настройки": "Settings",
        "Язык интерфейса:": "Interface language:",
        "Запускать вместе с Windows": "Start with Windows",
        "Спрашивать при удалении": "Ask before deleting",
        "Показывать запрос перед удалением заметки.\n"
        "Удаление безвозвратное, поэтому по умолчанию запрос включён.":
            "Show a confirmation before deleting a note.\n"
            "Deleting is permanent, so the prompt is on by default.",
        "Сохранять текст через:": "Save text after:",
        " мс": " ms",
        "Пауза после последнего нажатия клавиши. Пока печатаешь без "
        "остановки, запись не идёт — она начинается, когда перестанешь "
        "печатать.":
            "Pause after the last keypress. While you keep typing, nothing "
            "is written — saving starts once you stop.",
        "Новая заметка": "New note",
        "Цвет фона:": "Background color:",
        "Цвет текста:": "Text color:",
        "Размер шрифта:": "Font size:",
        "Ширина заметки:": "Note width:",
        " пт": " pt",
        "Относится только к новым заметкам.": "Applies to new notes only.",
        "Горячие клавиши": "Hotkeys",
        "Клавиша назначается при фокусе в поле. Backspace — снять. "
        "Нужен модификатор: Ctrl, Alt, Shift или Win.":
            "Press the key while the field is focused. Backspace clears it. "
            "A modifier is required: Ctrl, Alt, Shift or Win.",
        "ОК": "OK",
        "Отмена": "Cancel",
        "По умолчанию": "Restore defaults",
        "Ширина новой заметки в пикселях.": "Width of a new note, in pixels.",
        "Высота новой заметки в пикселях.": "Height of a new note, in pixels.",
        "Комбинация %s назначена дважды: «%s» и «%s».":
            "Shortcut %s is assigned twice: \u201c%s\u201d and \u201c%s\u201d.",
        "Не удалось изменить автозапуск.":
            "Could not change the autostart setting.",

        # --- app.py: трей ---
        "Не удалось занять горячие клавиши: %s.\n"
        "Их перехватила другая программа.":
            "Could not register hotkeys: %s.\n"
            "Another program has taken them.",
        "%s\nВидимых: %d": "%s\nVisible: %d",
        "+ Новая заметка": "+ New note",
        "Показать одну": "Show one",
        "Показать/скрыть все": "Show/hide all",
        "Скрыть все": "Hide all",
        "Поиск по заметкам": "Search notes",
        "Экспорт заметок (JSON)…": "Export notes (JSON)…",
        "Экспорт заметок (HTML)…": "Export notes (HTML)…",
        "Импорт заметок из JSON…": "Import notes from JSON…",
        "Копия базы данных…": "Database copy…",
        "О программе": "About",
        "Выход": "Quit",

        # --- app.py: экспорт, импорт, копия базы ---
        "Заметок нет — выгружать нечего.": "There are no notes to export.",
        "Экспорт заметок": "Export notes",
        "Экспорт заметок в HTML": "Export notes to HTML",
        "Импорт заметок": "Import notes",
        "Копия базы данных": "Database copy",
        "Файл заметок Stickio (*.json);;Все файлы (*)":
            "Stickio notes (*.json);;All files (*)",
        "Веб-страница (*.html);;Все файлы (*)": "Web page (*.html);;All files (*)",
        "База данных SQLite (*.db);;Все файлы (*)":
            "SQLite database (*.db);;All files (*)",
        "Не удалось сохранить файл:\n%s": "Could not save the file:\n%s",
        "Сохранено заметок: %d\n%s": "Notes saved: %d\n%s",
        "Добавить заметок из файла: %d?\n"
        "Существующие заметки останутся на месте.":
            "Add %d notes from the file?\nExisting notes will stay in place.",
        "Не удалось добавить ни одной заметки.": "No notes could be added.",
        "Добавлено заметок: %d": "Notes added: %d",
        "Не удалось создать копию:\n%s": "Could not create the copy:\n%s",
        "Сохранено:\n%s": "Saved:\n%s",

        # --- services/search.py ---
        "Некорректное выражение: %s": "Invalid expression: %s",

        # --- services/transfer.py ---
        "Заметки Stickio": "Stickio notes",
        "Запись заметки должна быть объектом.": "A note entry must be an object.",
        "Недопустимое значение поля «%s»: %r":
            "Invalid value for field \u201c%s\u201d: %r",
        "Это не файл экспорта Stickio.": "This is not a Stickio export file.",
        "Файл создан более новой версией Stickio (версия %s).":
            "The file was created by a newer version of Stickio (version %s).",
        "В файле нет списка заметок.": "The file has no list of notes.",
        "В файле нет ни одной заметки.": "The file has no notes.",
        "(пусто)": "(empty)",
        "жирный": "bold",
        "обычный": "regular",
        "Шрифт %s пт": "Font %s pt",
        "Выгружено %s · заметок: %d": "Exported %s · notes: %d",
        "Не удалось прочитать файл: %s": "Could not read the file: %s",
        "Файл не является корректным JSON: %s": "The file is not valid JSON: %s",

        # --- services/hotkeys.py ---
        "Горячая клавиша должна содержать модификатор и клавишу: %r":
            "A hotkey must contain a modifier and a key: %r",
        "Неизвестный модификатор %r в %r": "Unknown modifier %r in %r",
        "Неизвестная клавиша %r в %r": "Unknown key %r in %r",
        "Нужен хотя бы один модификатор: %r":
            "At least one modifier is required: %r",
        "Нет подписи для виртуального кода 0x%X":
            "No label for virtual key code 0x%X",

        # --- widgets/sticky_note.py ---
        "Отменить": "Undo",
        "Вернуть": "Redo",
        "Вырезать": "Cut",
        "Копировать": "Copy",
        "Вставить": "Paste",
        "Удалить": "Delete",
        "Выделить всё": "Select all",
        "Панель оформления": "Appearance panel",
        "Скрыть": "Hide",
        "Удалить заметку": "Delete note",
        "Удалить эту заметку безвозвратно?": "Delete this note permanently?",

        # --- widgets/toolbar.py ---
        "Закрепить заметку поверх всех окон": "Pin note on top of all windows",
        "Открепить заметку": "Unpin note",
        "Цвет фона": "Background color",
        "Цвет текста": "Text color",
        "Уменьшить текст": "Decrease text size",
        "Размер шрифта": "Font size",
        "Увеличить текст": "Increase text size",
        "Жирный": "Bold",
        "Прозрачность": "Opacity",
        "Прозрачность заметки": "Note opacity",
        "Цвет фона — %s": "Background color — %s",
        "Цвет текста — %s": "Text color — %s",

        # --- widgets/color_picker.py ---
        "Цвет": "Color",
        "Свой цвет…": "Custom color…",
        "Выбрать произвольный цвет": "Pick an arbitrary color",
        "Выбор цвета": "Choose a color",

        # --- widgets/hotkey_edit.py ---
        "Эту клавишу назначить нельзя": "This key cannot be assigned",
        "Нужен модификатор: Ctrl, Alt, Shift или Win":
            "A modifier is required: Ctrl, Alt, Shift or Win",
        "Нажмите сочетание": "Press a shortcut",
        "Нажмите нужное сочетание. Backspace — снять комбинацию. "
        "Только латиница и цифры.":
            "Press the shortcut you want. Backspace clears it. "
            "Latin letters and digits only.",

        # --- widgets/search_window.py ---
        "Искать по всем заметкам. Enter — открыть найденную.":
            "Searches all notes. Enter opens the match.",
        "Что искать…": "Search for…",
        "Рег. выражение": "Regex",
        "Искать как регулярное выражение. Без галки запрос ищется "
        "буквально: скобки и звёздочки не имеют особого смысла.":
            "Treat the query as a regular expression. Without the checkbox "
            "the query is matched literally: brackets and asterisks have no "
            "special meaning.",
        "Закрыть": "Close",
        "Заметка %d — совпадений: %d\n%s": "Note %d — matches: %d\n%s",
        "Ничего не найдено.": "Nothing found.",
        "Найдено заметок: %d, совпадений: %d": "Notes found: %d, matches: %d",

        # --- widgets/about_dialog.py ---
        "Автор: %s": "Author: %s",

        # --- services/app_info.py ---
        "Заметки на рабочем столе": "Notes on your desktop",
    },
}
