"""Поиск по заметкам: разбор запроса и отбор совпадений.

Логика намеренно отделена от окон: заметки хранят текст как HTML, и чтобы
найти в нём слово, нужно сначала получить из разметки читаемый текст —
это чистая функция, которую легко проверить без поднятия Qt-окна.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Сколько символов контекста показывать вокруг найденного слова в результатах.
SNIPPET_PADDING = 34
# Предел длины выдержки в строке результатов. Без него длинная заметка
# растягивает окно поиска: QListWidget подстраивает ширину под самую
# длинную строку, и окно разъезжается с 420 до 700+ пикселей.
MAX_SNIPPET_LENGTH = 120
# Совпадения длиннее этого не подсвечиваем целиком — иначе при поиске по
# пустой строке или одному символу подсветка залила бы весь текст.
MAX_HIGHLIGHT_LENGTH = 200


class SearchError(ValueError):
    """Запрос не удалось разобрать (некорректное регулярное выражение)."""


def normalise(query: str) -> str:
    """Приводит запрос к виду, в котором его сравнивают с текстом."""
    return (query or "").strip()


def is_active(query: str) -> bool:
    """Стоит ли вообще искать по такому запросу."""
    return bool(normalise(query))


def compile_query(query: str, regex: bool = False):
    """Собирает регулярное выражение под режим поиска.

    Не в режиме регулярных выражений запрос экранируется: пользователь
    ищет «(черновик)» буквально, а не как группу — иначе скобки и звёздочки
    в обычном тексте давали бы ошибку разбора.

    Raises:
        SearchError: регулярное выражение не компилируется.
    """
    text = normalise(query)
    if not text:
        return None
    if not regex:
        text = re.escape(text)
    try:
        return re.compile(text, re.IGNORECASE | re.DOTALL)
    except re.error as exc:
        raise SearchError("Некорректное выражение: %s" % exc)


def plain_text(content: str) -> str:
    """Читаемый текст заметки вместо HTML-разметки редактора.

    Без этого поиск нашёл бы «font» и «span» в служебных атрибутах Qt, а
    пользователь искал слова своего текста.
    """
    if not content:
        return ""
    # Быстрый путь: заметка без разметки — типичный случай для коротких
    # стикеров, и поднимать QTextDocument ради неё не нужно.
    if "<" not in content:
        return content
    from PySide6.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(content)
    return document.toPlainText()


def find_matched_spans(text: str, pattern) -> list:
    """Диапазоны (начало, конец) совпадений в тексте.

    Пустые совпадения отбрасываются: регулярное выражение вида «.*?» даёт
    совпадение нулевой длины на каждой позиции, и подсветка превратилась бы
    в сплошную заливку.
    """
    if pattern is None or not text:
        return []
    spans = []
    for match in pattern.finditer(text):
        start, end = match.start(), match.end()
        if end <= start:
            continue
        if end - start > MAX_HIGHLIGHT_LENGTH:
            continue
        spans.append((start, end))
    return spans


def count_matches(text: str, pattern) -> int:
    """Сколько раз запрос встречается в тексте."""
    return len(find_matched_spans(text, pattern))


def snippet(text: str, spans, padding: int = SNIPPET_PADDING,
            limit: int = MAX_SNIPPET_LENGTH) -> str:
    """Кусок текста вокруг первого совпадения — для строки результатов.

    Возвращает весь текст, если он короткий: обрезать то, что и так
    помещается, значит прятать от пользователя нужное. Итог всё равно
    ограничивается `limit` — иначе строка списка растягивает окно поиска
    (QListWidget берёт ширину по самой длинной строке).
    """
    collapsed = " ".join(text.split())
    if not spans or len(collapsed) <= padding * 2:
        result = collapsed
    else:
        start, end = spans[0]
        left = max(0, start - padding)
        right = min(len(collapsed), end + padding)
        prefix = "…" if left > 0 else ""
        suffix = "…" if right < len(collapsed) else ""
        result = "%s%s%s" % (prefix, collapsed[left:right].strip(), suffix)

    if len(result) > limit:
        # Обрезаем по границе слова, если она рядом: обрубок посередине
        # слова читается как опечатка.
        cut = result.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        result = result[:cut].rstrip() + "…"
    return result


def match_notes(notes, query: str, regex: bool = False) -> list:
    """Отбирает заметки, в которых встречается запрос.

    Args:
        notes: список объектов Note (или чего угодно с полями id и content).
        query: строка поиска.

    Returns:
        Список словарей: id, текст целиком, найденные диапазоны и краткая
        выдержка. Порядок — как в переданном списке (обычно по id), чтобы
        результаты не прыгали между запусками.

    Raises:
        SearchError: запрос не компилируется в регулярное выражение.
    """
    pattern = compile_query(query, regex=regex)
    if pattern is None:
        return []

    results = []
    for note in notes:
        text = plain_text(note.content)
        spans = find_matched_spans(text, pattern)
        if not spans:
            continue
        results.append({
            "id": note.id,
            "text": text,
            "spans": spans,
            "snippet": snippet(text, spans),
            "count": len(spans),
        })
    return results
