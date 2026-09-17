import logging

from PySide6.QtCore import QObject, QRect

from database.database import Database
from models.note import DEFAULT_HEIGHT, DEFAULT_WIDTH, Note
from services.settings import Settings
from widgets.sticky_note import MIN_VISIBLE_HEIGHT, MIN_VISIBLE_WIDTH, StickyNote

logger = logging.getLogger(__name__)

# Шаг каскада и предел попыток подбора свободного места.
CASCADE_STEP = 28
CASCADE_LIMIT = 60
# Откуда начинаем раскладывать новые заметки.
CASCADE_START = (120, 120)


def rects_overlap(a: QRect, b: QRect) -> bool:
    """Пересекаются ли прямоугольники (касание границ — не пересечение)."""
    return (
        a.x() < b.x() + b.width()
        and b.x() < a.x() + a.width()
        and a.y() < b.y() + b.height()
        and b.y() < a.y() + a.height()
    )


def cascade_position(occupied, width: int, height: int, area: QRect,
                     start=CASCADE_START, step: int = CASCADE_STEP,
                     limit: int = CASCADE_LIMIT) -> tuple:
    """Свободное место для новой заметки — каскадом от стартовой точки.

    Без этого все новые заметки встают в одну точку (x/y по умолчанию из
    схемы БД) и полностью перекрывают друг друга: создаёшь вторую — видишь
    одну.

    Args:
        occupied: прямоугольники уже открытых заметок (QRect).
        area: доступная геометрия экрана.
        start: точка, от которой идёт каскад.

    Returns:
        (x, y) — левый верхний угол. Если целиком свободного места нет,
        возвращает последнюю проверенную позицию каскада: пусть заметка
        ляжет со сдвигом, чем точь-в-точь поверх первой (иначе создаёшь
        вторую — видишь одну).
    """
    span_x = max(1, area.width() - width)
    span_y = max(1, area.height() - height)
    # Стартовую точку зажимаем внутрь экрана: иначе на втором мониторе со
    # своим началом координат каскад уехал бы за пределы видимой области.
    start_x = min(max(start[0], area.left()), area.left() + span_x)
    start_y = min(max(start[1], area.top()), area.top() + span_y)

    position = (start_x, start_y)
    for index in range(limit):
        offset = index * step
        x = area.left() + (start_x - area.left() + offset) % span_x
        y = area.top() + (start_y - area.top() + offset) % span_y
        position = (x, y)
        candidate = QRect(x, y, width, height)
        if not any(rects_overlap(candidate, rect) for rect in occupied):
            return position
    return position


class NoteManager(QObject):
    def __init__(self, database: Database, parent=None, settings=None):
        super().__init__(parent)
        self.database = database
        self.settings = settings or Settings()
        self.windows: dict[int, StickyNote] = {}
        # Кто был виден на момент последнего hide_all — чтобы Ctrl+Shift+H
        # возвращал ровно ту картину, что была, а не «включить всё».
        self._visible_before_hide: list[int] = []

    def load_all(self):
        saved = self.database.get_all_notes()
        if not saved:
            return
        for note in saved:
            self._open_window(note, show=True)

    def create_note(self) -> StickyNote:
        # Настройки задают вид НОВОЙ заметки; у уже сохранённых свои цвета.
        fields = self.settings.note_defaults()
        # Размер берём из настроек, а не из констант модели: cascade_position
        # подбирает место под конкретный прямоугольник, и если посчитать
        # позицию для одного размера, а записать другой, увеличившаяся заметка
        # налезет на соседнюю.
        width = fields.get("width", DEFAULT_WIDTH)
        height = fields.get("height", DEFAULT_HEIGHT)
        x, y = self._free_position(width, height)
        fields["x"], fields["y"] = x, y
        note_id = self.database.create_note(**fields)
        note = self.database.get_note(note_id)
        window = self._open_window(note, show=True)
        self._raise_window(window)
        return window

    def _free_position(self, width: int, height: int) -> tuple:
        """Подбирает место, где новая заметка никого не перекроет."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        screen = QApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        occupied = [
            QRect(window.note.x, window.note.y, window.note.width, window.note.height)
            for window in self.windows.values()
            if window.isVisible()
        ]
        return cascade_position(occupied, width, height, area)

    def import_notes(self, records) -> list:
        """Добавляет заметки из файла экспорта. Возвращает созданные окна.

        Именно ДОБАВЛЯЕТ, а не заменяет: файл может быть выгрузкой с другого
        компьютера, и затирать текущие заметки было бы потерей данных.

        Координаты из файла не переносим, если они привели бы к наложению:
        выгрузка сделана на экране другого размера, и заметка целиком за
        границей нового выглядела бы как «импорт ничего не дал».
        """
        created = []
        for fields in records:
            fields = dict(fields)
            width = fields.get("width", DEFAULT_WIDTH)
            height = fields.get("height", DEFAULT_HEIGHT)
            if not self._position_visible(fields.get("x"), fields.get("y"), width, height):
                x, y = self._free_position(width, height)
                fields["x"], fields["y"] = x, y
            try:
                note_id = self.database.create_note(**fields)
            except Exception:
                logger.exception("Failed to import note from file")
                continue
            note = self.database.get_note(note_id)
            created.append(self._open_window(note, show=True))
        logger.info("Imported %d notes", len(created))
        return created

    def _position_visible(self, x, y, width: int, height: int) -> bool:
        """Поместится ли заметка из файла на какой-нибудь из экранов.

        Проверяем только видимость: если координаты пересекаются с уже
        открытыми заметками, это не ошибка — пользователь сам разложит их.
        """
        from PySide6.QtWidgets import QApplication

        if x is None or y is None:
            return False
        rect = QRect(int(x), int(y), int(width), int(height))
        for screen in QApplication.screens():
            avail = screen.availableGeometry()
            inter = avail.intersected(rect)
            if inter.width() < MIN_VISIBLE_WIDTH or inter.height() < MIN_VISIBLE_HEIGHT:
                continue
            if rect.top() < avail.top():
                continue
            return True
        return False

    def _open_window(self, note: Note, show: bool) -> StickyNote:
        window = StickyNote(note, self.database, settings=self.settings)
        window.delete_requested.connect(self.delete_window)
        window.new_note_requested.connect(self.create_note)
        self.windows[note.id] = window
        if show:
            window.show()
        return window

    def delete_window(self, window: StickyNote):
        """Удаляет заметку: сначала БД, потом UI.

        Если удаление из БД упало — окно оставляем открытым, чтобы данные
        не «оживали» при следующем запуске (зомби-заметка).
        """
        try:
            self.database.delete_note(window.note.id)
        except Exception:
            logger.exception("Failed to delete note id=%s from database", window.note.id)
            return
        self.windows.pop(window.note.id, None)
        window.close()
        window.deleteLater()

    def _visible_ids(self) -> list[int]:
        """ID видимых заметок в стабильном (по id) порядке."""
        return [i for i in self.windows if self.windows[i].isVisible()]

    def show_one(self):
        """Циклически показывает заметки по одной (клик по иконке трея).

        Если все заметки скрыты — показывает первую. Если одна показана —
        скрывает её и показывает следующую. Последняя → снова первая.
        """
        ids = list(self.windows.keys())
        if not ids:
            return

        visible = self._visible_ids()
        if not visible:
            self._raise_window(self.windows[ids[0]])
            return

        if len(visible) > 1:
            # Несколько видно (после show_all или хоткея) — сворачиваем к одной
            for i in visible[1:]:
                self.windows[i].hide()
            self._raise_window(self.windows[visible[0]])
            return

        current = visible[0]
        if len(ids) == 1:
            # Одна заметка во всём приложении: клик работает как переключатель
            self.windows[current].hide()
            return

        # Следующая считаем по порядку id, но стартуем от реально видимой —
        # раньше индекс брался от начала списка, из-за чего клик по трею
        # с заметки #5 открывал #1, а не #6.
        idx = ids.index(current)
        next_id = ids[(idx + 1) % len(ids)]
        self.windows[current].hide()
        self._raise_window(self.windows[next_id])

    def hide_all(self):
        """Скрывает все заметки, запоминая текущий видимый набор."""
        self._visible_before_hide = self._visible_ids()
        for window in self.windows.values():
            window.hide()

    def show_all(self):
        """Возвращает то, что было видно до последнего hide_all.

        Если скрывать было нечего (заметки гасили по одной) — показываем все:
        для пользователя хоткей должен что-то сделать, а не молча ничего.
        """
        target = [
            self.windows[i] for i in self._visible_before_hide
            if i in self.windows
        ]
        if not target:
            target = list(self.windows.values())
        for window in target:
            window.show()
            window.raise_()
        self._visible_before_hide = []
        if target:
            target[0].activateWindow()

    def close_all(self):
        for window in list(self.windows.values()):
            window.close()

    @staticmethod
    def _raise_window(window: StickyNote):
        window.show()
        window.raise_()
        window.activateWindow()
