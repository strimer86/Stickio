import logging

from PySide6.QtCore import QObject

from database.database import Database
from models.note import Note
from services.settings import Settings
from widgets.sticky_note import StickyNote

logger = logging.getLogger(__name__)


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
        note_id = self.database.create_note(**self.settings.note_defaults())
        note = self.database.get_note(note_id)
        window = self._open_window(note, show=True)
        self._raise_window(window)
        return window

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
