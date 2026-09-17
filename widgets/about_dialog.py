"""Окно «О программе»: название, версия, автор и сайт.

Отдельное окно, а не строка в настройках: настройки — про поведение
программы, а здесь сведения о ней самой. Открывается редко, поэтому
модальное и с одной кнопкой.
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from services.app_info import (
    APP_AUTHOR, APP_NAME, APP_SITE, APP_SITE_LABEL, APP_TAGLINE,
    app_version, copyright_line,
)
from widgets.sticky_note import create_app_icon

logger = logging.getLogger(__name__)

# Размер значка в окне. 64 px — тот же размер, что у запасной нарисованной
# иконки, поэтому крупный кадр из Noteit.ico берётся без искажения.
ICON_SIZE = 64


class AboutDialog(QDialog):
    """Сведения о программе и её авторе."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("О программе")

        icon = create_app_icon()
        self.setWindowIcon(icon)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(16)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.icon_label.setPixmap(icon.pixmap(ICON_SIZE, ICON_SIZE))
        # Значок прижат к верху: справа текста на несколько строк, и
        # выровненный по центру значок «плавал» бы относительно названия.
        top.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(4)

        self.name_label = QLabel("%s %s" % (APP_NAME, app_version()))
        # Кегль берём от собственного шрифта подписи, а не числом: у разных
        # систем он разный, и «+3» читается крупнее заголовка везде.
        name_font = self.name_label.font()
        name_font.setPointSize(name_font.pointSize() + 3)
        name_font.setBold(True)
        self.name_label.setFont(name_font)
        texts.addWidget(self.name_label)

        self.tagline_label = QLabel(APP_TAGLINE)
        texts.addWidget(self.tagline_label)

        texts.addSpacing(6)

        self.author_label = QLabel("Автор: %s" % APP_AUTHOR)
        texts.addWidget(self.author_label)

        self.site_label = QLabel(
            '<a href="%s">%s</a>' % (APP_SITE, APP_SITE_LABEL)
        )
        # Ссылку открывает система: свой обработчик здесь не нужен.
        self.site_label.setOpenExternalLinks(True)
        self.site_label.setToolTip(APP_SITE)
        texts.addWidget(self.site_label)

        texts.addStretch(1)
        top.addLayout(texts)
        top.addStretch(1)
        layout.addLayout(top)

        self.copyright_label = QLabel(copyright_line())
        layout.addWidget(self.copyright_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        # Стандартная подпись кнопки приходит из перевода Qt, а он может
        # быть не загружен — тогда кнопка осталась бы английской.
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
