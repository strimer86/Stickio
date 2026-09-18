"""Закрепление окна заметки поверх всех окон (Win32).

Почему не флаг Qt: ``WindowStaysOnTopHint`` даёт только «выше обычных окон»,
но клик по такому окну делает его активным — заметка отбирает фокус у
программы, в которой человек работал. Настоящий пин требует двух разных
расширенных стилей окна, и у Qt под них отдельных флагов нет.

Стили:

* ``WS_EX_TOPMOST`` — окно выше всех остальных, не только обычных.
* ``WS_EX_NOACTIVATE`` — окно не становится активным при клике.

Второй стиль и есть то, ради чего затевалось: с ним заметка видна поверх
всего, а фокус остаётся в активной программе.

Обратная сторона найдена пробой, а не по документации: окно с
``WS_EX_NOACTIVATE`` **не получает клавиатурный ввод** (``isActiveWindow()``
остаётся False, WM_KEYDOWN уходит активной программе). Поэтому на время
набора флаг приходится снимать — этим занимается окно заметки, здесь
только расчёт стилей и вызовы Win32.

Модуль намеренно не знает про Qt: все действия — над числами и hwnd,
поэтому их можно проверить тестом без поднятия окна.
"""
import ctypes
import logging
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)

GWL_EXSTYLE = -20

WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000

# Параметры SetWindowPos: только z-порядок и стиль, без перемещения.
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010


def supported() -> bool:
    """Есть ли Win32 под рукой.

    На не-Windows модуль импортируется (тесты), но работать не должен:
    вместо падения на ctypes.windll выдаём False, и вызывающий код
    просто не станет ничего закреплять.
    """
    return sys.platform == "win32"


def _user32():
    """ctypes.windll.user32 с объявленными типами.

    Типы объявляем каждый раз, а не один раз на модуль: windll кеширует
    функции, но argtypes у них общие на процесс, и в тестах их удобнее
    иметь предсказуемыми.
    """
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    return user32


def pinned_exstyle(exstyle: int) -> int:
    """Расширенный стиль окна, закреплённого поверх всех."""
    return exstyle | WS_EX_TOPMOST | WS_EX_NOACTIVATE


def unpinned_exstyle(exstyle: int) -> int:
    """Обычный стиль: без закрепления и без запрета активации."""
    return exstyle & ~WS_EX_TOPMOST & ~WS_EX_NOACTIVATE


def editable_exstyle(exstyle: int) -> int:
    """Стиль для набора текста: поверх всех, но окно можно активировать.

    Закрепление остаётся, снимается только запрет активации — иначе
    клавиатура не дойдёт до редактора.
    """
    return (exstyle | WS_EX_TOPMOST) & ~WS_EX_NOACTIVATE


def is_pinned(exstyle: int) -> bool:
    """Стоит ли у окна признак закрепления."""
    return bool(exstyle & WS_EX_TOPMOST)


def is_activatable(exstyle: int) -> bool:
    """Можно ли окно активировать (не стоит запрет активации)."""
    return not (exstyle & WS_EX_NOACTIVATE)


def _as_unsigned(value: int) -> int:
    """Приводит LONG со знаком к беззнаковому виду стиля.

    GetWindowLongW возвращает ctypes.c_long, и у стиля со старшим битом
    (WS_EX_NOACTIVATE = 0x08000000 как раз такой) значение приходит
    положительным, а вот биты старше 0x7FFFFFFF дали бы отрицательное.
    """
    return value & 0xFFFFFFFF


def get_exstyle(hwnd: int) -> int:
    """Текущий расширенный стиль окна; 0, если прочитать не удалось."""
    if not hwnd or not supported():
        return 0
    try:
        return _as_unsigned(_user32().GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE))
    except (OSError, AttributeError) as e:
        logger.warning("GetWindowLongW failed for hwnd=%s: %s", hwnd, e)
        return 0


def set_exstyle(hwnd: int, exstyle: int) -> bool:
    """Задаёт расширенный стиль окна.

    Стиль ставим через SetWindowLongW, а z-порядок — отдельным вызовом:
    SetWindowLongW меняет флаг, но не переставляет уже созданное окно
    в список TOPMOST. Без второго вызова окно получит стиль, а поверх
    всех встанет только после следующего показа.
    """
    if not hwnd or not supported():
        return False
    try:
        user32 = _user32()
        user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, ctypes.c_long(exstyle))
        topmost = bool(exstyle & WS_EX_TOPMOST)
        user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(HWND_TOPMOST if topmost else HWND_NOTOPMOST),
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        return True
    except (OSError, AttributeError) as e:
        logger.warning("set_exstyle failed for hwnd=%s: %s", hwnd, e)
        return False
