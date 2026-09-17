"""Генератор иконки приложения — пишет Noteit.ico в корень проекта.

Запускать вручную, если нужна новая иконка:

    python resources/icons/generate_icon.py

Пишем именно в Noteit.ico, а не рядом с этим скриптом: этот файл —
единственный источник иконки и для сборщика (ModernStickyNotes.spec), и для
инсталлятора (installer/ModernStickyNotes.iss). Раньше скрипт писал
resources/icons/icon.ico, который в сборку не попадал: получалось два
разных изображения, и правка иконки ни на что не влияла.
"""
import os
import sys

from PIL import Image, ImageDraw

# Размеры, которые Windows показывает в разных местах: 16 — в заголовке окна,
# 32 — на панели задач, 48/256 — в проводнике и крупных значках.
# ВАЖЕН ПОРЯДОК: первым идёт самый крупный. Pillow в PIL.IcoImagePlugin._save
# берёт базовое изображение (это draw_icon(256)) и в цикле по размерам
# проверяет `size[0] > width`; если базовым отдать мелкую картинку, все
# остальные размеры отсеются. Более того, в ветке else _save вызывает
# `frame.thumbnail(size)` — а это правит объект НА МЕСТЕ: после падения до
# 16x16 базовое изображение становится 16x16, и на следующих итерациях
# условие отсекает уже вообще всё. Итог — .ico с одной записью на 214 байт,
# который Windows показывает как мелкий значок. Проверено вживую.
SIZES = [256, 128, 96, 72, 64, 48, 32, 24, 16]

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


def icon_path() -> str:
    """Путь к Noteit.ico в корне проекта (на два уровня выше этого файла)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    return os.path.join(root, "Noteit.ico")


def main() -> int:
    path = icon_path()
    images = [draw_icon(s) for s in SIZES]
    # Базовым идёт images[0], а он теперь 256x256 (см. комментарий к SIZES).
    images[0].save(
        path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print("Иконка сохранена: %s" % path)
    print("Размеры: %s" % ", ".join("%dx%d" % (s, s) for s in SIZES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
