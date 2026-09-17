"""ЧЕРНОВИК. Рабочую иконку НЕ перезаписывает — только пишет образец рядом.

Запускать, если нужно посмотреть, что получится, прежде чем делать иконку:

    python resources/icons/generate_icon.py

Результат: resources/icons/draft_icon.ico (файл в .gitignore).

== Почему так ==

Иконка приложения — Noteit.ico в КОРНЕ проекта. Её берут:
  * ModernStickyNotes.spec  — datas=[('Noteit.ico', '.')] и icon=;
  * installer/ModernStickyNotes.iss — SetupIconFile;
  * widgets/sticky_note.py — иконка окна заметки.

Это нарисованный вручную файл на 241 КБ: стопка разноцветных стикеров с
кнопкой, 9 размеров от 16 до 256. Скрипт, который здесь лежит, рисует
примитивами PIL плоскую жёлтую накладку с линиями — это совсем другое
изображение, и подменять им Noteit.ico нельзя.

Так уже случилось: скрипт писал свои поделки в Noteit.ico, рабочая иконка
была потеряна и восстанавливалась из истории git. Поэтому здесь стоит
явная защита: `save()` никогда не получает путь к Noteit.ico, а `main()`
дополнительно проверяет, что пишет именно в draft_icon.ico.
"""

import os
import sys

from PIL import Image, ImageDraw

# Размеры, которые Windows показывает в разных местах: 16 — в заголовке окна,
# 32 — на панели задач, 48/256 — в проводнике и крупных значках.
# ВАЖЕН ПОРЯДОК: первым идёт самый крупный. Pillow в PIL.IcoImagePlugin._save
# берёт базовое изображение и в цикле по размерам проверяет
# `size[0] > width`; если базовым отдать мелкую картинку, все остальные
# размеры отсеются. Более того, в ветке else _save вызывает
# `frame.thumbnail(size)` — а это правит объект НА МЕСТЕ: после падения до
# 16x16 базовое изображение становится 16x16, и на следующих итерациях
# условие отсекает уже вообще всё. Итог — .ico с одной записью на 214 байт.
SIZES = [256, 128, 96, 72, 64, 48, 32, 24, 16]

# Куда пишем черновик. Путь собирается здесь и НЕ может указывать на
# Noteit.ico: имя зафиксировано, а каталог — только рядом с этим файлом.
DRAFT_NAME = "draft_icon.ico"
# Имя рабочей иконки — используется лишь для защиты от подмены.
PROTECTED_NAME = "Noteit.ico"

BG = "#FFD55E"
BORDER = "#D4A82E"
LINE = "#222222"
FOLD = "#F5C842"


def draw_icon(size: int) -> Image.Image:
    """Рисует стикер с загнутым уголком в заданном размере."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, size // 16)
    fold = max(2, size // 5)

    body = [
        margin,
        margin,
        size - margin - fold,
        size - margin,
    ]
    draw.rounded_rectangle(
        body,
        radius=max(2, size // 10),
        fill=BG,
        outline=BORDER,
        width=max(1, size // 40),
    )

    corner = [
        size - margin - fold,
        margin,
        size - margin,
        margin + fold,
    ]
    draw.polygon(
        [tuple(corner[:2]), (size - margin, size - margin), (corner[2], corner[3])],
        fill=FOLD,
    )

    text_lines = max(2, fold // 3)
    for i in range(text_lines):
        y = margin + fold + (size // 8) + i * max(2, size // 7)
        x1 = margin + max(2, size // 8)
        x2 = size - margin - max(3, size // 5)
        if y > size - margin - max(1, size // 10):
            break
        draw.line((x1, y, x2, y), fill=LINE, width=max(1, size // 32))

    return img


def draft_path() -> str:
    """Путь к файлу-образцу рядом с этим скриптом."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, DRAFT_NAME)


def work_icon_path() -> str:
    """Путь к рабочей иконке — только для чтения и для сообщений."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, PROTECTED_NAME)


def main() -> int:
    path = draft_path()
    # Защита от будущих правок: даже если путь поменяют, рабочий файл не тронем.
    if os.path.basename(path) == PROTECTED_NAME:
        print("Отказ: этот скрипт не должен писать %s." % PROTECTED_NAME)
        return 1

    images = [draw_icon(s) for s in SIZES]
    # Базовым идёт images[0], а он 256x256 (см. комментарий к SIZES).
    images[0].save(
        path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print("Черновик сохранён: %s" % path)
    print("Размеры: %s" % ", ".join("%dx%d" % (s, s) for s in SIZES))
    print()
    print("Рабочая иконка (%s) НЕ изменена." % work_icon_path())
    return 0


if __name__ == "__main__":
    sys.exit(main())
