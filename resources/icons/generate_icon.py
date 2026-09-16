"""Generate application icon in ICO format with multiple sizes."""
from PIL import Image, ImageDraw, ImageFont
import os

SIZES = [16, 24, 32, 48, 64, 128, 256]
BG = "#FFD55E"
BG_DARK = "#E8C24A"
BORDER = "#D4A82E"
LINE = "#222222"
FOLD = "#F5C842"


def draw_icon(size: int) -> Image.Image:
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
    draw.rounded_rectangle(body, radius=max(2, size // 10), fill=BG, outline=BORDER, width=max(1, size // 40))

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


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(script_dir, "icon.ico")

    images = [draw_icon(s) for s in SIZES]
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print(f"Icon saved: {ico_path}")


if __name__ == "__main__":
    main()