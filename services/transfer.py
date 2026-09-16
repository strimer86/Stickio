"""Экспорт и импорт заметок, ручные копии базы.

Зачем отдельный модуль: заметки живут в одной SQLite-базе в LOCALAPPDATA,
автоматические .bak.N лежат рядом с ней и защищают только от порчи файла.
Если база потеряется целиком (переустановка Windows, сбой диска, переезд на
другой компьютер) — копии уедут вместе с ней. Поэтому нужен человекочитаемый
файл, который пользователь сохраняет куда хочет: JSON переносит заметки на
другую машину, HTML просто открывается в браузере для чтения.
"""
import html as html_module
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Формат файла. Номер нужен, чтобы будущий импорт отличал свои файлы от
# чужих (пользователь однажды подсунет произвольный JSON) и чтобы старые
# версии приложения читали новые файлы осознанно, а не «как получится».
EXPORT_FORMAT = "stickio-notes"
EXPORT_VERSION = 1

# Что переносим. Порядок задаёт и порядок колонок в JSON, и порядок в HTML.
EXPORT_FIELDS = (
    "content",
    "background_color",
    "text_color",
    "font_size",
    "bold",
    "opacity",
    "x",
    "y",
    "width",
    "height",
)

# Значения, которые обязаны быть в каждой записи. Отсутствие ключа — не
# ошибка (старый файл), битое значение — ошибка.
_NUMERIC_FIELDS = {
    "font_size": int,
    "x": int,
    "y": int,
    "width": int,
    "height": int,
    "opacity": float,
}

_TITLE = "Заметки Stickio"


class TransferError(Exception):
    """Файл не удалось прочитать или разобрать.

    Отдельный тип, чтобы вызывающий код отличал «пользователь выбрал не тот
    файл» (понятное сообщение в диалоге) от сбоя записи на диск.
    """


def note_to_dict(note) -> dict:
    """Заметку в словарь для JSON. Ключ id намеренно не переносим.

    При импорте заметки добавляются новыми записями: id — это первичный
    ключ таблицы, и попытка сохранить его сломалась бы при первом же
    конфликте с уже существующей заметкой (заметки «перезаписывали» бы
    друг друга).
    """
    return {name: getattr(note, name) for name in EXPORT_FIELDS}


def build_export(notes) -> dict:
    """Готовит структуру файла экспорта."""
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "notes": [note_to_dict(note) for note in notes],
    }


def note_from_dict(raw) -> dict:
    """Проверяет одну запись из файла и возвращает поля для создания заметки.

    Битые значения не проглатываются молча: лучше отказаться от импорта и
    сказать «файл повреждён», чем создать заметку с font_size = "abc" и
    потом ловить это при отрисовке.
    """
    if not isinstance(raw, dict):
        raise TransferError("Запись заметки должна быть объектом.")

    fields = {}
    for name in EXPORT_FIELDS:
        if name not in raw or raw[name] is None:
            continue
        value = raw[name]
        caster = _NUMERIC_FIELDS.get(name)
        if caster is not None:
            try:
                value = caster(value)
            except (TypeError, ValueError):
                raise TransferError(
                    "Недопустимое значение поля «%s»: %r" % (name, raw[name])
                )
        elif name == "bold":
            value = bool(value)
        elif not isinstance(value, str):
            raise TransferError(
                "Недопустимое значение поля «%s»: %r" % (name, raw[name])
            )
        fields[name] = value

    if "content" not in fields:
        fields["content"] = ""
    return fields


def parse_export(data) -> list[dict]:
    """Разбирает содержимое файла экспорта в список полей заметок.

    Raises:
        TransferError: файл не является экспортом Stickio или повреждён.
    """
    if not isinstance(data, dict):
        raise TransferError("Это не файл экспорта Stickio.")
    if data.get("format") != EXPORT_FORMAT:
        raise TransferError("Это не файл экспорта Stickio.")

    version = data.get("version", 0)
    if not isinstance(version, int) or version > EXPORT_VERSION:
        raise TransferError(
            "Файл создан более новой версией Stickio (версия %s)." % (version,)
        )

    notes = data.get("notes")
    if not isinstance(notes, list):
        raise TransferError("В файле нет списка заметок.")
    if not notes:
        raise TransferError("В файле нет ни одной заметки.")

    return [note_from_dict(item) for item in notes]


def plain_text(content: str) -> str:
    """Превращает HTML заметки в простой текст для экспорта в HTML.

    Редактор хранит текст как HTML (QTextEdit.toHtml), поэтому без этого
    шага в HTML-файл попала бы разметка Qt с её километровыми служебными
    стилями, а не то, что видит пользователь.
    """
    from PySide6.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(content or "")
    return document.toPlainText()


def build_html(notes) -> str:
    """Читаемая выгрузка заметок: один файл, открывается в браузере."""
    exported = datetime.now().strftime("%d.%m.%Y %H:%M")
    cards = []
    for note in notes:
        text = plain_text(note.content) or "(пусто)"
        cards.append(
            '<article class="note" style="background: {bg}; color: {fg};">'
            '<pre>{text}</pre>'
            '<div class="meta">Шрифт {size} пт{nbsp}· {bold}{nbsp}· {opacity}%</div>'
            "</article>".format(
                bg=html_module.escape(str(note.background_color), quote=True),
                fg=html_module.escape(str(note.text_color), quote=True),
                text=html_module.escape(text),
                size=note.font_size,
                bold="жирный" if note.bold else "обычный",
                opacity=round(float(note.opacity) * 100),
                nbsp="&nbsp;",
            )
        )

    return """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ background: #f2f2f2; color: #222; margin: 0; padding: 24px;
         font-family: "Segoe UI", Arial, sans-serif; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitle {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
  .note {{ width: 300px; min-height: 140px; padding: 14px;
          border-radius: 10px; border: 1px solid rgba(0,0,0,0.25);
          box-sizing: border-box; display: flex; flex-direction: column; }}
  .note pre {{ margin: 0 0 12px; white-space: pre-wrap; word-wrap: break-word;
              font: inherit; flex: 1; }}
  .meta {{ font-size: 11px; opacity: 0.6; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">Выгружено {exported} · заметок: {count}</div>
<div class="grid">
{cards}
</div>
</body>
</html>
""".format(
        title=_TITLE,
        exported=exported,
        count=len(notes),
        cards="\n".join(cards),
    )


def write_text(path: str, text: str):
    """Пишет текстовый файл в UTF-8 (кириллица в заметках — обычное дело)."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_export_file(path: str) -> list[dict]:
    """Читает и разбирает JSON-экспорт с диска."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError) as exc:
        raise TransferError("Не удалось прочитать файл: %s" % exc)
    except json.JSONDecodeError as exc:
        raise TransferError("Файл не является корректным JSON: %s" % exc)
    return parse_export(data)


def backup_database(database, dest_path: str):
    """Копия базы в выбранный пользователем файл.

    Используется sqlite backup API, а не копирование файла: при активном
    журнале WAL часть данных лежит в notes.db-wal, и простое копирование
    дало бы устаревший или битый слепок.
    """
    import sqlite3

    dest = sqlite3.connect(dest_path)
    try:
        with dest:
            database.backup_to(dest)
    finally:
        dest.close()
    logger.info("Manual database backup written to %s", dest_path)


def default_export_name(extension: str) -> str:
    """Имя по умолчанию: Stickio_2026-09-16.json."""
    return "Stickio_%s.%s" % (datetime.now().strftime("%Y-%m-%d"), extension)
