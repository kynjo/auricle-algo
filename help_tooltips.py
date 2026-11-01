"""Passive help bindings: no timers, event filters or model mutations."""
from html import escape
import weakref

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid

from help_catalog import entry

_language = "ru"
_bound = {}


def help_language():
    return _language


def _tooltip(widget):
    scope, key, extra = widget._auricle_help
    item = entry(scope, key)
    if item is None:
        return
    parts = [f"<b>{escape(item.label)}</b>", escape(item.text(_language))]
    if hasattr(widget, "lo") and hasattr(widget, "hi"):
        label = "Диапазон" if _language == "ru" else "Range"
        default = "По умолчанию" if _language == "ru" else "Default"
        parts.append(f"{label}: {widget.lo:g}…{widget.hi:g}. {default}: {widget.default:g}.")
        parts.append("Перетащите или прокрутите; двойной щелчок — сброс." if _language == "ru"
                     else "Drag or scroll; double-click resets the default.")
        if getattr(widget, "_auricle_has_midi_learn_menu", False):
            parts.append("Правый щелчок: MIDI Learn / удалить назначение." if _language == "ru"
                         else "Right-click: MIDI Learn / clear mapping.")
    if extra:
        parts.append(escape(extra))
    tip = '<table width="360"><tr><td>' + "<br>".join(parts) + "</td></tr></table>"
    setter = getattr(widget, "set_base_tooltip", widget.setToolTip)
    table = widget.tableWidget() if hasattr(widget, "tableWidget") else None
    # Item tooltip roles emit itemChanged too. Keep help/language changes
    # out of MIDI-expression and mapping edit handlers.
    if table is not None:
        with QSignalBlocker(table):
            setter(tip)
    else:
        setter(tip)
    # Custom steppers and mode buttons receive mouse events in their children.
    for name in ("editor", "minus", "plus", "value_label", "seq", "live"):
        child = getattr(widget, name, None)
        if child is not None and hasattr(child, "setToolTip") and isValid(child):
            child.setToolTip(tip)


def bind_help(widget, key, scope="block", *, extra=""):
    if widget is None or entry(scope, key) is None:
        return False
    widget._auricle_help = (scope, key, extra)
    ident = id(widget)
    _bound[ident] = weakref.ref(widget, lambda _ref, ident=ident: _bound.pop(ident, None))
    _tooltip(widget)
    return True


def copy_help(source, destination):
    binding = getattr(source, "_auricle_help", None)
    if binding:
        scope, key, extra = binding
        bind_help(destination, key, scope, extra=extra)


def bind_attributes(panel, scope, names=None):
    """Bind named widget attributes, optionally with attr -> catalog-key mapping."""
    if names is None:
        from help_catalog import CATALOG
        names = list(CATALOG[scope])
    pairs = names.items() if hasattr(names, "items") else ((name, name) for name in names)
    for attr, key in pairs:
        widget = getattr(panel, attr, None)
        if widget is not None and hasattr(widget, "setToolTip"):
            bind_help(widget, key, scope)


def bind_controls(controls, scope):
    for key, widget in controls.items():
        bind_help(widget, key, scope)


def bind_table(table, keys, scope):
    for col, key in enumerate(keys):
        header = table.horizontalHeaderItem(col)
        if header is not None:
            bind_help(header, key, scope)
        for row in range(table.rowCount()):
            item = table.item(row, col)
            if item is not None:
                bind_help(item, key, scope)
            widget = table.cellWidget(row, col)
            if widget is not None:
                # Composition Active lives inside a centering QWidget.
                if not bind_help(widget, key, scope):
                    continue
                for child in widget.findChildren(QWidget):
                    bind_help(child, key, scope)


def refresh_tree(root):
    """Restore descriptions after construction-time/dynamic tooltip overrides."""
    for widget in (root, *root.findChildren(QWidget)):
        if hasattr(widget, "_auricle_help"):
            _tooltip(widget)
        elif getattr(widget, "_auricle_parameter", None):
            bind_help(widget, widget._auricle_parameter[1])


def set_help_language(language):
    global _language
    _language = "ru" if str(language).lower().startswith("ru") else "en"
    for ref in tuple(_bound.values()):
        widget = ref()
        if widget is not None and isValid(widget):
            _tooltip(widget)


def render_help(view, markdown):
    """Render Markdown and restore explicit contents anchors dropped by Qt.

    Empty HTML anchors survive in exported Markdown but Qt's parser removes
    them. Attach each name to the first character of its existing heading;
    this neither duplicates content nor replaces the Markdown rendering.
    """
    import re
    from PySide6.QtGui import QTextCursor
    headings = iter(re.findall(r'<a name="([^"]+)"></a>\s+#+ ([^\n]+)', markdown))
    wanted = next(headings, None)
    view.setMarkdown(markdown)
    block = view.document().begin()
    while wanted and block.isValid():
        if block.blockFormat().headingLevel() and block.text() == wanted[1]:
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            fmt = cursor.charFormat()
            fmt.setAnchor(True)
            fmt.setAnchorNames([wanted[0]])
            cursor.setCharFormat(fmt)
            wanted = next(headings, None)
        block = block.next()
