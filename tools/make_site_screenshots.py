"""Скриншоты Stickio для сайта.

Снимаем настоящие окна приложения, а не рисуем их заново: на сайте должны
быть картинки того, что человек получит после установки.

Две вещи, которые легко сделать неправильно:

  * Платформа — windows, а не offscreen: в offscreen шрифты не рисуются
    вовсе (вместо букв квадраты), см. .trash/_font_probe.py. Окна при этом
    не показываются — render() по скрытому виджету работает, если раскладка
    уже посчитана (ensurePolished).
  * Содержимое заметки — HTML, а не простой текст: редактор грузит его
    через setHtml, поэтому переводы строк в простом тексте превращаются
    в пробелы и вся заметка склеивается в одну строку. Берём ровно то,
    что приложение само записало бы в базу (QTextEdit.toHtml).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QTextEdit

from app import SettingsDialog
from models.note import Note
from services.settings import Settings
from widgets.search_window import SearchWindow
from widgets.sticky_note import StickyNote, load_app_icon

OUT = os.path.join(ROOT, "site", "assets")
os.makedirs(OUT, exist_ok=True)


class SilentDatabase:
    """Заглушка базы: окну заметки она нужна только чтобы сохранять."""

    def save_note(self, note):
        pass


app = QApplication([])
# Скриншоты делаем в светлой теме. Программа следует теме системы, а на
# машине сборки включена тёмная — на светлой странице сайта тёмные окна
# выглядели бы чужими. Это тот же интерфейс, просто при светлой теме.
app.styleHints().setColorScheme(Qt.ColorScheme.Light)
load_app_icon()


def as_stored(text: str) -> str:
    """Текст заметки в том виде, в каком его хранит база (HTML)."""
    editor = QTextEdit()
    editor.setPlainText(text)
    return editor.toHtml()


def render(widget) -> QPixmap:
    """Рисует виджет в картинку его собственного размера.

    Окно показываем, но за пределами экрана: у скрытого виджета раскладка
    не окончательная — например, у спинбоксов «ширина × высота» кнопки
    рисуются, а поле значения нет, и строка выглядит сломанной. За краем
    экрана окно не мешает и при этом считается как настоящее.
    """
    widget.move(-4000, -4000)
    widget.show()
    app.processEvents()
    app.processEvents()
    widget.adjustSize()
    app.processEvents()
    pixmap = QPixmap(widget.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    widget.render(pixmap)
    widget.hide()
    return pixmap


def draw_shadow(painter, x, y, w, h, radius=10, spread=34, alpha=26, dy=8):
    """Мягкая тень под окном.

    Рисуем расширяющимися скруглёнными прямоугольниками с быстро падающей
    прозрачностью: они накладываются друг на друга и дают градиент.
    QGraphicsDropShadowEffect здесь не годится — render() рисует виджет
    в его собственный прямоугольник, и тень за краями обрезалась бы.
    """
    painter.setPen(Qt.PenStyle.NoPen)
    for step in range(spread, 0, -1):
        share = 1.0 - step / float(spread)
        painter.setBrush(QColor(0, 0, 0, max(1, int(alpha * share ** 3))))
        painter.drawRoundedRect(
            QRectF(x - step, y - step + dy, w + step * 2, h + step * 2),
            radius + step, radius + step,
        )


def wallpaper(width: int, height: int) -> QPixmap:
    """Обои рабочего стола: спокойный градиент с двумя подсветками."""
    pixmap = QPixmap(width, height)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QLinearGradient(0, 0, width * 0.35, height)
    gradient.setColorAt(0.0, QColor("#e3eaf8"))
    gradient.setColorAt(1.0, QColor("#f3f1ea"))
    painter.fillRect(0, 0, width, height, gradient)

    glow = QRadialGradient(width * 0.82, height * 0.14, width * 0.5)
    glow.setColorAt(0.0, QColor(102, 87, 221, 38))
    glow.setColorAt(1.0, QColor(102, 87, 221, 0))
    painter.fillRect(0, 0, width, height, glow)

    glow2 = QRadialGradient(width * 0.1, height * 0.95, width * 0.45)
    glow2.setColorAt(0.0, QColor(83, 188, 137, 34))
    glow2.setColorAt(1.0, QColor(83, 188, 137, 0))
    painter.fillRect(0, 0, width, height, glow2)

    painter.end()
    return pixmap


def backdrop(width: int, height: int) -> QPixmap:
    """Подложка для диалогов: тот же градиент, но ровнее."""
    pixmap = QPixmap(width, height)
    painter = QPainter(pixmap)
    gradient = QLinearGradient(0, 0, width * 0.4, height)
    gradient.setColorAt(0.0, QColor("#e9edf6"))
    gradient.setColorAt(1.0, QColor("#f2f0ea"))
    painter.fillRect(0, 0, width, height, gradient)
    painter.end()
    return pixmap


def place(pixmap: QPixmap, widget_pixmap: QPixmap, pad: int,
          radius=6, spread=26, alpha=30, dy=7) -> QPixmap:
    """Ставит картинку окна на подложку с тенью по центру."""
    canvas = backdrop(pixmap.width(), pixmap.height())
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_shadow(painter, pad, pad, widget_pixmap.width(), widget_pixmap.height(),
                radius=radius, spread=spread, alpha=alpha, dy=dy)
    painter.drawPixmap(pad, pad, widget_pixmap)
    painter.end()
    return canvas


# Все снимки делаем одного размера. В галерее на сайте они стоят в ряд,
# и разные пропорции давали бы разную высоту карточек с пустотами под
# короткими — ровный ряд читается спокойнее.
SHOT_W, SHOT_H = 880, 620


def centred(widget_pixmap: QPixmap, dx: int = 0, dy: int = 0) -> QPixmap:
    """Снимок окна на подложке общего размера, окно по центру."""
    x = (SHOT_W - widget_pixmap.width()) // 2 + dx
    y = (SHOT_H - widget_pixmap.height()) // 2 + dy
    canvas = backdrop(SHOT_W, SHOT_H)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_shadow(painter, x, y, widget_pixmap.width(), widget_pixmap.height())
    painter.drawPixmap(x, y, widget_pixmap)
    painter.end()
    return canvas


# --- 1. Заметка на рабочем столе --------------------------------------

NOTE_TEXT = (
    "На сегодня\n"
    "\n"
    "Позвонить в сервис — забрать документы\n"
    "Купить корм коту\n"
    "Отправить отчёт до 18:00\n"
    "Поздравить Сергея с повышением\n"
    "Записаться к врачу"
)
note = Note(
    id=1,
    content=as_stored(NOTE_TEXT),
    background_color="#FFF4A8",
    font_size=18,
    width=500,
    height=400,
)
# Вторая заметка — не для красоты: на одном стикере посреди пустого
# рабочего стола не видно, что заметок может быть сколько угодно и они
# разного размера. Ставим их рядом, как в жизни, — без наложения:
# в самой программе заметки тоже не перекрываются.
second = Note(
    id=2,
    content=as_stored("Пятница, 15:00\nВстреча\nПодготовить вопросы"),
    background_color="#A8E6CF",
    font_size=15,
    width=250,
    height=300,
)

canvas = wallpaper(SHOT_W, SHOT_H)
painter = QPainter(canvas)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
for widget, (x, y) in (
    (StickyNote(note, SilentDatabase(), Settings()), (52, 140)),
    (StickyNote(second, SilentDatabase(), Settings()), (578, 210)),
):
    pixmap = render(widget)
    draw_shadow(painter, x, y, pixmap.width(), pixmap.height())
    painter.drawPixmap(x, y, pixmap)
painter.end()
canvas.save(os.path.join(OUT, "screenshot-note.png"))
print("screenshot-note.png", canvas.size())

# --- 2. Настройки ------------------------------------------------------

settings_pixmap = render(SettingsDialog(Settings()))
centred(settings_pixmap).save(os.path.join(OUT, "screenshot-settings.png"))
print("screenshot-settings.png", SHOT_W, SHOT_H)

# --- 3. Поиск ----------------------------------------------------------

search_widget = SearchWindow()
search_widget.set_notes_provider(lambda: [
    Note(id=2, content=as_stored("Забрать документы из сервиса до пятницы")),
    Note(id=5, content=as_stored(
        "Проект «Весна»\nОтправить документы в бухгалтерию\nСверить суммы"
    )),
    Note(id=7, content=as_stored(
        "Домашние дела\nКупить корм коту\nРазобрать документы в шкафу"
    )),
])
search_widget.query_edit.setText("документ")
search_widget.refresh()
search_pixmap = render(search_widget)
centred(search_pixmap).save(os.path.join(OUT, "screenshot-search.png"))
print("screenshot-search.png", SHOT_W, SHOT_H)

# Те же снимки в WebP. Браузер берёт их вместо PNG: они в 2–7 раз легче,
# а снимок рабочего стола — в шесть раз (78 КБ против 12 КБ). Делаем это
# здесь, а не отдельной командой: иначе после правки окна PNG обновятся,
# а WebP останутся старыми, и на сайте будет прежняя картинка.
try:
    from PIL import Image
except ImportError:
    print("Pillow не установлен — WebP не пересобран, PNG продолжают работать")
else:
    for name in ("screenshot-note", "screenshot-settings", "screenshot-search"):
        src = os.path.join(OUT, name + ".png")
        dst = os.path.join(OUT, name + ".webp")
        Image.open(src).convert("RGB").save(dst, "WEBP", quality=84, method=6)
        print("%s.webp %d байт (PNG %d)"
              % (name, os.path.getsize(dst), os.path.getsize(src)))

print("готово, папка:", OUT)
