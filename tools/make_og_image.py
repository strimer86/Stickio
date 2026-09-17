"""Картинка предпросмотра ссылки (og:image) 1200x630.

Её показывают мессенджеры, соцсети и поисковики рядом с ссылкой на сайт.
Рисуем сами, а не берём скриншот: в маленьком превью текст со скриншота
не читается, а название и суть должны быть видны сразу.

Размер 1200x630 — то, что ждут и ВКонтакте, и Telegram, и Яндекс с Google.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QApplication

W, H = 1200, 630
OUT = os.path.join(ROOT, "site", "assets", "og-stickio.png")

app = QApplication([])

canvas = QPixmap(W, H)
canvas.fill(QColor("#f5f4ef"))
painter = QPainter(canvas)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

# Мягкая подсветка справа — тот же приём, что на сайте в подложке заметок.
glow = QRadialGradient(W * 0.78, H * 0.3, W * 0.6)
glow.setColorAt(0.0, QColor(102, 87, 221, 40))
glow.setColorAt(1.0, QColor(102, 87, 221, 0))
painter.fillRect(0, 0, W, H, glow)

glow2 = QRadialGradient(W * 0.16, H * 0.92, W * 0.5)
glow2.setColorAt(0.0, QColor(83, 188, 137, 34))
glow2.setColorAt(1.0, QColor(83, 188, 137, 0))
painter.fillRect(0, 0, W, H, glow2)


def note(x, y, w, h, color, angle, title, lines):
    """Стикер: скруглённый прямоугольник с заголовком и строками."""
    painter.save()
    painter.translate(x + w / 2, y + h / 2)
    painter.rotate(angle)
    painter.translate(-(x + w / 2), -(y + h / 2))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 26))
    painter.drawRoundedRect(QRectF(x + 6, y + 10, w, h), 12, 12)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(x, y, w, h), 12, 12)

    painter.setPen(QColor("#1c2430"))
    painter.setFont(QFont("Segoe UI", 17, QFont.Weight.DemiBold))
    painter.drawText(QPointF(x + 26, y + 52), title)

    painter.setFont(QFont("Segoe UI", 15))
    painter.setPen(QColor("#3a4550"))
    for index, line in enumerate(lines):
        painter.drawText(QPointF(x + 26, y + 90 + index * 27), line)

    painter.restore()


note(782, 124, 296, 206, "#A8E6CF", -4,
     "На сегодня", ["Позвонить в сервис", "Купить корм коту", "Отправить отчёт"])
note(906, 322, 254, 164, "#FFF4A8", 3,
     "Идея", ["Записывать сразу,", "пока мысль не ушла"])

# Значок программы — тот же Noteit.ico, что и в exe.
icon = QIcon(os.path.join(ROOT, "Noteit.ico"))
painter.drawPixmap(72, 62, icon.pixmap(64, 64))

painter.setPen(QColor("#1c2430"))
painter.setFont(QFont("Segoe UI", 62, QFont.Weight.Bold))
painter.drawText(QPointF(72, 240), "Stickio")

painter.setPen(QColor("#2f3a45"))
painter.setFont(QFont("Segoe UI", 29))
painter.drawText(QPointF(72, 300), "Заметки на рабочем столе Windows")

painter.setPen(QColor("#5f6b76"))
painter.setFont(QFont("Segoe UI", 23))
painter.drawText(QPointF(72, 350), "Стикеры поверх всех окон · горячие клавиши")

painter.setPen(QColor("#4b3cc1"))
painter.setFont(QFont("Segoe UI", 25, QFont.Weight.DemiBold))
painter.drawText(QPointF(72, 470), "Бесплатно")

painter.setPen(QColor("#5f6b76"))
painter.setFont(QFont("Segoe UI", 23))
painter.drawText(QPointF(72, 512), "Windows 10 и 11 · без регистрации")

painter.setPen(QColor("#8d96a1"))
painter.setFont(QFont("Segoe UI", 22))
painter.drawText(QPointF(72, 570), "stickio.tumioai.ru")

painter.end()
canvas.save(OUT)
print("готово:", OUT, canvas.size())
