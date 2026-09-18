from dataclasses import dataclass

DEFAULT_BACKGROUND = "#FFF4A8"
DEFAULT_TEXT_COLOR = "#222222"
DEFAULT_FONT_SIZE = 18
DEFAULT_OPACITY = 1.0
DEFAULT_WIDTH = 380
DEFAULT_HEIGHT = 300


@dataclass
class Note:
    id: int = None
    content: str = ""
    background_color: str = DEFAULT_BACKGROUND
    text_color: str = DEFAULT_TEXT_COLOR
    font_size: int = DEFAULT_FONT_SIZE
    bold: bool = False
    always_on_top: bool = False
    opacity: float = DEFAULT_OPACITY
    x: int = 120
    y: int = 120
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT

    def __post_init__(self):
        # Clamp-и защищают от «кривых» значений в БД (старые версии, ручные правки)
        self.font_size = max(1, int(self.font_size))
        self.opacity = min(1.0, max(0.0, float(self.opacity)))
        self.width = max(1, int(self.width))
        self.height = max(1, int(self.height))
        self.x = int(self.x)
        self.y = int(self.y)
