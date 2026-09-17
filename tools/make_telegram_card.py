"""Картинка к посту в Telegram, 1280x720.

Не берём og:image: та картинка для превью ссылки, её показывают маленькой
рядом с заголовком, а в посте она открывается во всю ширину ленты. Здесь
другая задача — чтобы за полсекунды было понятно, что это и как выглядит,
поэтому в кадре настоящий снимок окна программы.

Собирается из site/assets/screenshot-note.png, то есть после правки
интерфейса достаточно пересобрать снимки и запустить этот скрипт.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication

W, H = 1280, 720
SHOT = os.path.join(ROOT, "site", "assets", "screenshot-note.png")
OUT_DIR = os.path.join(ROOT, "promo")
OUT = os.path.join(OUT_DIR, "telegram-card.png")

os.makedirs(OUT_DIR, exist_ok=True)
app = QApplication([])

canvas = QPixmap(W, H)
canvas.fill(QColor("#f5f4ef"))
painter = QPainter(canvas)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

# Те же подсветки, что на сайте и в og-картинке: кадр должен читаться
# как часть одного оформления, а не как случайная картинка.
glow = QRadialGradient(W * 0.8, H * 0.22, W * 0.62)
glow.setColorAt(0.0, QColor(102, 87, 221, 42))
glow.setColorAt(1.0, QColor(102, 87, 221, 0))
painter.fillRect(0, 0, W, H, glow)

glow2 = QRadialGradient(W * 0.14, H * 0.94, W * 0.5)
glow2.setColorAt(0.0, QColor(83, 188, 137, 34))
glow2.setColorAt(1.0, QColor(83, 188, 137, 0))
painter.fillRect(0, 0, W, H, glow2)

# --- снимок окна справа -----------------------------------------------

shot = QPixmap(SHOT)
shot = shot.scaledToWidth(660, Qt.TransformationMode.SmoothTransformation)
x = W - shot.width() - 56
y = (H - shot.height()) // 2

# Мягкая тень: расширяющиеся скруглённые прямоугольники, как в скрипте
# снимков для сайта. QGraphicsDropShadowEffect тут не подходит — рисуем
# вручную, чтобы тень не обрезалась по краю картинки.
painter.setPen(Qt.PenStyle.NoPen)
for step in range(30, 0, -1):
    share = 1.0 - step / 30.0
    painter.setBrush(QColor(0, 0, 0, max(1, int(30 * share ** 3))))
    painter.drawRoundedRect(
        QRectF(x - step, y - step + 8, shot.width() + step * 2,
               shot.height() + step * 2), 18 + step, 18 + step)

clip = QPainterPath()
clip.addRoundedRect(QRectF(x, y, shot.width(), shot.height()), 18, 18)
painter.setClipPath(clip)
painter.drawPixmap(x, y, shot)
painter.setClipping(False)

# --- подписи слева ----------------------------------------------------
#
# Блок выровнен по вертикали: сверху до иконки и снизу до адреса примерно
# одинаковый воздух. В первой версии всё жалась к верху, снизу оставалась
# четверть кадра пустой — в ленте это выглядело как обрезанная картинка.

icon = QIcon(os.path.join(ROOT, "Noteit.ico"))
painter.drawPixmap(72, 130, icon.pixmap(64, 64))

painter.setPen(QColor("#1c2430"))
painter.setFont(QFont("Segoe UI", 64, QFont.Weight.Bold))
painter.drawText(QPointF(72, 322), "Stickio")

painter.setPen(QColor("#2f3a45"))
painter.setFont(QFont("Segoe UI", 28))
painter.drawText(QPointF(72, 382), "Заметки на рабочем столе")
painter.drawText(QPointF(72, 422), "Windows")

painter.setPen(QColor("#4b3cc1"))
painter.setFont(QFont("Segoe UI", 26, QFont.Weight.DemiBold))
painter.drawText(QPointF(72, 512), "Бесплатно")

painter.setPen(QColor("#5f6b76"))
painter.setFont(QFont("Segoe UI", 23))
painter.drawText(QPointF(72, 552), "Без регистрации и рекламы")

painter.setPen(QColor("#8d96a1"))
painter.setFont(QFont("Segoe UI", 22))
painter.drawText(QPointF(72, 664), "stickio.tumioai.ru")

painter.end()
canvas.save(OUT)
print("готово:", OUT, canvas.size())
