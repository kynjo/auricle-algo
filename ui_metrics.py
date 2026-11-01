"""Shared logical-pixel dimensions and bounded window geometry."""
from functools import wraps

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

CONTROL_HEIGHT = 26
DENSE_HEIGHT = 24
TRANSPORT_HEIGHT = 36
TRANSPORT_WIDTH = 42
MODE_WIDTH = 50
TAB_ICON_SIZE = 24
CARD_HEIGHT = 86


def initial_window_geometry(available):
    """Leave room for native window decorations, including on small displays."""
    width = min(1440, max(820, round(available.width() * .94)), max(1, available.width() - 32))
    height = min(900, max(520, round(available.height() * .90)), max(1, available.height() - 64))
    return QRect(available.x() + (available.width() - width) // 2,
                 available.y() + (available.height() - height) // 2, width, height)


def quiet_rebuild(method):
    """Exclude construction/layout traffic from history's gesture event filter."""
    @wraps(method)
    def rebuild(host, *args, **kwargs):
        app = QApplication.instance()
        history = getattr(host, "history_controller", None)
        outermost = not getattr(host, "_ui_rebuild_depth", 0)
        host._ui_rebuild_depth = getattr(host, "_ui_rebuild_depth", 0) + 1
        updates = host.updatesEnabled()
        if outermost:
            if app is not None and history is not None:
                app.removeEventFilter(history)
            host.setUpdatesEnabled(False)
        try:
            return method(host, *args, **kwargs)
        finally:
            host._ui_rebuild_depth -= 1
            if outermost:
                host.setUpdatesEnabled(updates)
                if app is not None and history is not None:
                    app.installEventFilter(history)
    return rebuild
