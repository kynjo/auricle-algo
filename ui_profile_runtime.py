"""Lightweight runtime for saved Auricle UI profiles.

Only saved targets and their ancestors are observed. Ordinary style/paint
changes never enumerate the full tree or borrowed QLayoutItems.
"""
from PySide6 import QtCore as _ac_c, QtGui as _ac_g, QtWidgets as _ac_w
import functools as _ac_functools
import ast as _ac_ast
import re as _ac_re
import weakref as _ac_weakref
import shiboken6 as _ac_shiboken


def _ac_valid(obj):
    return obj is not None and _ac_shiboken.isValid(obj)


def _ac_resolve(root, selector):
    """Resolve one saved path without reflecting over the whole Qt tree."""
    obj, chain = root, [root]
    if not isinstance(selector, str) or not selector.startswith("$"):
        return None, chain
    for segment in selector.split("/")[1:]:
        if not _ac_valid(obj): return None, chain
        if segment.startswith("@"):
            field = segment[1:]
            try:
                if "[" in field and field.endswith("]"):
                    field, key = field.split("[", 1)
                    values = getattr(obj, field, None)
                    obj = values.get(_ac_ast.literal_eval(key[:-1])) if isinstance(values, dict) else None
                else:
                    obj = getattr(obj, field, None)
            except (ValueError, SyntaxError, TypeError):
                return None, chain
            if not isinstance(obj, (_ac_w.QWidget, _ac_w.QLayout)):
                return None, chain
        else:
            try:
                class_name, name, ordinal = segment.rsplit(":", 2)
                name = name.replace("~1", "/").replace("~0", "~")
                ordinal = int(ordinal)
            except (ValueError, TypeError):
                return None, chain
            matches = [child for child in obj.children()
                       if isinstance(child, _ac_c.QObject) and _ac_valid(child)
                       and type(child).__name__ == class_name and child.objectName() == name]
            obj = matches[ordinal] if 0 <= ordinal < len(matches) else None
            if obj is None: return None, chain
        chain.append(obj)
    return obj, chain


def _ac_tree(root):
    """Stable keys: public window attributes, nested attributes, then Qt paths.

    Captions and layout positions are deliberately absent from identities:
    renaming and rearranging controls must not change their selectors.
    """
    objects, keys, parents = [], {root: "$"}, {root: None}

    def visit(obj, path):
        # Layout insertion can change QObject.children() order. Preserve the
        # original structural identity for the lifetime of each real object;
        # public field/dictionary anchors below remain backward-compatible.
        cached = obj.property("_algoConfStructuralPath")
        if isinstance(cached, str):
            path = cached
        else:
            obj.setProperty("_algoConfStructuralPath", path)
        keys[obj] = path
        if isinstance(obj, (_ac_w.QWidget, _ac_w.QLayout)):
            objects.append(obj)
        counts = {}
        for child in obj.children():
            if not isinstance(child, _ac_c.QObject) or not _ac_valid(child):
                continue
            token = type(child).__name__ + ":" + child.objectName().replace("~", "~0").replace("/", "~1")
            ordinal = counts.get(token, 0); counts[token] = ordinal + 1
            key = path + "/" + token + ":" + str(ordinal)
            keys[child] = key; parents[child] = obj
            visit(child, key)
    visit(root, "$")
    anchored = {root}
    for owner in objects:
        references = []
        for name, value in sorted(getattr(owner, "__dict__", {}).items()):
            if not name.isidentifier() or name.startswith("_"): continue
            if isinstance(value, (_ac_w.QWidget, _ac_w.QLayout)):
                references.append((name, value))
            elif isinstance(value, dict) and len(value) <= 10000:
                for key, child in sorted(value.items(), key=lambda pair: str(pair[0]) if isinstance(pair[0], (str, int)) else ""):
                    if isinstance(key, (str, int)) and not isinstance(key, bool) and isinstance(child, (_ac_w.QWidget, _ac_w.QLayout)):
                        references.append((name+"["+repr(key)+"]", child))
        for name, child in references:
            if child not in keys or child in anchored or child is owner:
                continue
            # A stored reference to an ancestor is not a new identity.
            ancestor = parents.get(owner)
            while ancestor is not None and ancestor is not child:
                ancestor = parents.get(ancestor)
            if ancestor is child:
                continue
            keys[child] = keys[owner] + "/@" + name
            anchored.add(child)
    return objects, keys, parents


def _ac_caption(obj):
    value = ""
    if isinstance(obj, _ac_w.QGroupBox): value = obj.title()
    elif isinstance(obj, (_ac_w.QLabel, _ac_w.QAbstractButton)): value = obj.text()
    elif isinstance(obj, _ac_w.QLineEdit): value = obj.placeholderText()
    if not value and isinstance(obj, _ac_w.QFrame):
        labels = obj.findChildren(_ac_w.QLabel, options=_ac_c.Qt.FindDirectChildrenOnly)
        named = [label for label in labels if label.objectName() in ("blockName", "nameLabel")]
        labels = named or [label for label in labels if label.text().strip() and not label.text().strip().isdigit()]
        if labels: value = labels[0].text()
    return str(value or obj.accessibleName() if isinstance(obj, _ac_w.QWidget) else value)[:160]


def _ac_owner(obj, objects):
    # indexOf(QWidget) stays inside Qt. Walking itemAt()/layout() for every
    # widget manufactured thousands of borrowed QLayoutItem wrappers per scan.
    for layout in objects:
        if not isinstance(layout, _ac_w.QLayout): continue
        if isinstance(obj, _ac_w.QWidget):
            index = layout.indexOf(obj)
            if index >= 0: return layout, index
        elif isinstance(obj, _ac_w.QLayout) and obj.parent() is layout:
            index = layout.indexOf(obj)
            if index >= 0: return layout, index
    return None, -1


def _ac_order(layout, keys):
    result, spacers = [], 0
    for index in range(layout.count()):
        item = layout.itemAt(index)
        child = item.widget() or item.layout()
        if child in keys: result.append(keys[child])
        else: result.append("@spacer:" + str(spacers)); spacers += 1
    return result


def _ac_state(obj, objects, owner_info=None):
    if isinstance(obj, _ac_w.QLayout):
        margins = obj.contentsMargins()
        state = {"spacing": obj.spacing(), "margins": [margins.left(), margins.top(), margins.right(), margins.bottom()]}
        if isinstance(obj, _ac_w.QBoxLayout): state["direction"] = int(obj.direction().value)
        return state
    state = {"min_width": obj.minimumWidth(), "max_width": obj.maximumWidth(),
             "min_height": obj.minimumHeight(), "max_height": obj.maximumHeight(),
             "x": obj.x(), "y": obj.y(), "visible": not obj.isHidden(),
             "font": _ac_g.QFont(obj.font()), "style": obj.styleSheet(),
             "tooltip": obj.toolTip()}
    if isinstance(obj, _ac_w.QGroupBox): state["text"] = obj.title()
    elif isinstance(obj, (_ac_w.QLabel, _ac_w.QAbstractButton)): state["text"] = obj.text()
    if isinstance(obj, _ac_w.QLineEdit): state["placeholder"] = obj.placeholderText()
    owner, index = _ac_owner(obj, objects) if owner_info is None else owner_info
    if owner:
        state["alignment"] = int(owner.itemAt(index).alignment().value)
        if isinstance(owner, _ac_w.QBoxLayout): state["stretch"] = owner.stretch(index)
        if isinstance(owner, _ac_w.QGridLayout): state["grid"] = owner.getItemPosition(index)
    return state


def _ac_set(obj, value, getter, setter):
    if getter() != value: setter(value)


def _ac_style(base, token, rules):
    if not rules: return base
    base = _ac_re.sub(r'/\*algo_conf:begin\*/.*?/\*algo_conf:end\*/', '', base, flags=_ac_re.S)
    parsed = _ac_re.sub(r'/\*.*?\*/', '', base, flags=_ac_re.S).strip()
    if parsed and '{' not in parsed:
        base = '* {' + base + '}'
        parsed = '* {' + parsed + '}'
    own = '[algoConfTarget="'+token+'"]'
    selectors = ['*'+own]
    for header in _ac_re.findall(r'(?:^|})([^{}]+){', parsed):
        for selector in header.split(','):
            selector = selector.strip()
            if not selector or '::' in selector: continue
            # Reuse each local selector and add the exact-instance qualifier.
            # This keeps its existing ID/state specificity and then exceeds it.
            states = _ac_re.search(r'(?::!?[A-Za-z_-]+)+$', selector)
            point = states.start() if states else len(selector)
            scoped = selector[:point]+own+selector[point:]
            if scoped not in selectors: selectors.append(scoped)
    return base+'\n/*algo_conf:begin*/\n'+',\n'.join(selectors)+' {'+';'.join(rules)+';}\n/*algo_conf:end*/'


def _ac_apply_widget(obj, values, old_values, original, objects):
    touched = set(values) | set(old_values)
    for axis, title in (("width", "Width"), ("height", "Height")):
        if touched & {"fixed_"+axis, "min_"+axis, "max_"+axis}:
            low = int(values.get("min_"+axis, original["min_"+axis]))
            high = int(values.get("max_"+axis, original["max_"+axis]))
            fixed = values.get("fixed_"+axis)
            if fixed is not None: low = high = int(fixed)
            high = max(low, high)
            _ac_set(obj, low, getattr(obj, "minimum"+title), getattr(obj, "setMinimum"+title))
            _ac_set(obj, high, getattr(obj, "maximum"+title), getattr(obj, "setMaximum"+title))
    if touched & {"x", "y"}:
        owner, _index = _ac_owner(obj, objects)
        if owner is None and obj.parentWidget() is not None:
            position = _ac_c.QPoint(int(values.get("x", original["x"])), int(values.get("y", original["y"])))
            if obj.pos() != position: obj.move(position)
    if "visible" in touched:
        visible = bool(values.get("visible", original["visible"]))
        if obj.isHidden() == visible: obj.setVisible(visible)
    if "text" in touched and "text" in original:
        text = values.get("text", original["text"])
        if isinstance(obj, _ac_w.QGroupBox): _ac_set(obj, text, obj.title, obj.setTitle)
        else: _ac_set(obj, text, obj.text, obj.setText)
    if "placeholder" in touched and "placeholder" in original:
        _ac_set(obj, values.get("placeholder", original["placeholder"]), obj.placeholderText, obj.setPlaceholderText)
    if "tooltip" in touched:
        _ac_set(obj, values.get("tooltip", original["tooltip"]), obj.toolTip, obj.setToolTip)
    if touched & {"font_size", "bold"}:
        font = _ac_g.QFont(original["font"])
        if "font_size" in values: font.setPointSizeF(float(values["font_size"]))
        if "bold" in values: font.setBold(bool(values["bold"]))
        if obj.font() != font: obj.setFont(font)
    style_keys = {"color", "background", "radius", "border_color", "border_width", "font_size", "bold"}
    if touched & style_keys:
        rules = []
        if "font_size" in values: rules.append("font-size:"+str(values["font_size"])+"pt")
        if "bold" in values: rules.append("font-weight:"+("bold" if values["bold"] else "normal"))
        if "color" in values: rules.append("color:"+values["color"])
        if "background" in values: rules.append("background-color:"+values["background"])
        if "radius" in values: rules.append("border-radius:"+str(values["radius"])+"px")
        if "border_color" in values or "border_width" in values:
            rules.append("border:"+str(values.get("border_width", 1))+"px solid "+values.get("border_color", "#808080"))
        token = str(id(obj))
        if obj.property("algoConfTarget") != token: obj.setProperty("algoConfTarget", token)
        previous_style = original.get("_applied_style")
        if previous_style is not None and obj.styleSheet() != previous_style:
            original["style"] = obj.styleSheet()
        style = _ac_style(original["style"], token, rules)
        original["_applied_style"] = style
        _ac_set(obj, style, obj.styleSheet, obj.setStyleSheet)
    layout_keys = {"alignment", "stretch", "grid_row", "grid_column", "row_span", "column_span"}
    owner, index = _ac_owner(obj, objects) if touched & layout_keys else (None, -1)
    if owner and "alignment" in touched:
        alignment = int(values.get("alignment", original.get("alignment", 0)))
        if int(owner.itemAt(index).alignment().value) != alignment:
            owner.setAlignment(obj, _ac_c.Qt.AlignmentFlag(alignment))
    if isinstance(owner, _ac_w.QBoxLayout) and "stretch" in touched:
        stretch = int(values.get("stretch", original.get("stretch", 0)))
        if owner.stretch(index) != stretch: owner.setStretch(index, stretch)
    if isinstance(owner, _ac_w.QGridLayout) and touched & {"grid_row", "grid_column", "row_span", "column_span"}:
        current = owner.getItemPosition(index)
        base = original.get("grid", current)
        grid = tuple(int(values.get(key, base[i])) for i, key in enumerate(("grid_row", "grid_column", "row_span", "column_span")))
        if current != grid:
            alignment = owner.itemAt(index).alignment()
            owner.removeWidget(obj)
            owner.addWidget(obj, *grid, alignment)


def _ac_reorder(layout, wanted, keys):
    current = _ac_order(layout, keys)
    wanted = [key for key in wanted if key in current] + [key for key in current if key not in wanted]
    if current == wanted: return
    records = {}
    for key in current:
        stretch = layout.stretch(0)
        item = layout.takeAt(0)
        records[key] = (item, stretch)
    for index, key in enumerate(wanted):
        item, stretch = records[key]
        child_layout = item.layout()
        widget = item.widget()
        if child_layout is not None:
            layout.insertLayout(index, child_layout, stretch)
        elif widget is not None:
            layout.insertWidget(index, widget, stretch, item.alignment())
        else:
            layout.insertItem(index, item)
            layout.setStretch(index, stretch)


class _AlgoConfRuntime(_ac_c.QObject):
    def __init__(self, root, profile, watch=True):
        super().__init__(root)
        self.root = root
        self.profile = profile
        self.originals = _ac_weakref.WeakKeyDictionary()
        self.applied = _ac_weakref.WeakKeyDictionary()
        self.orders = _ac_weakref.WeakKeyDictionary()
        self.busy = False
        self.missing = []
        self.timer = _ac_c.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.apply)
        self.watch = watch
        self.watched = _ac_weakref.WeakSet()
        self.apply()

    def eventFilter(self, obj, event):
        if obj is self.root and event.type() == _ac_c.QEvent.DeferredDelete:
            self.stop()
            return False
        # Repaint, MIDI indicators, fonts and ordinary showing/hiding must not
        # rescan the whole application. Only a changed widget tree needs it.
        if self.watch and not self.busy and event.type() == _ac_c.QEvent.ChildAdded:
            if _ac_valid(self.root) and _ac_valid(self.timer):
                if not self.timer.isActive(): self.timer.start(40)
        return False

    def stop(self):
        self.watch = False
        if _ac_valid(self.timer): self.timer.stop()
        for obj in list(self.watched):
            if _ac_valid(obj): obj.removeEventFilter(self)
        self.watched.clear()
        self.originals.clear(); self.applied.clear(); self.orders.clear()

    def update_profile(self, profile):
        self.profile = profile
        self.apply()

    def apply(self):
        if self.busy or not _ac_valid(self.root): return
        self.busy = True
        try:
            entries = self.profile.get("entries", {})
            by_key, keys, objects, watched = {}, {}, [], {self.root}
            for key in entries:
                obj, chain = _ac_resolve(self.root, key)
                watched.update(chain)
                if obj is not None and _ac_valid(obj):
                    by_key[key] = obj; keys[obj] = key
                    if obj not in objects: objects.append(obj)
            # Only explicit layout edits need ownership metadata. The current
            # size/font profile never enumerates or wraps layout items.
            layout_keys = {"x", "y", "alignment", "stretch", "grid_row", "grid_column", "row_span", "column_span", "order"}
            needs_layout = (any(layout_keys & set(row.get("properties", {})) for row in entries.values())
                            or any(layout_keys & set(values) for values in self.applied.values()))
            owner_objects, order_keys = [], {}
            if needs_layout:
                owner_objects, order_keys, _parents = _ac_tree(self.root)
                by_key = {key: obj for obj, key in order_keys.items() if key in entries}
                keys = order_keys
                objects = list(by_key.values())
                watched.update(owner_objects)
            if self.watch:
                for obj in watched:
                    if obj not in self.watched:
                        obj.installEventFilter(self)
                        self.watched.add(obj)
                for obj in list(self.watched):
                    if obj not in watched:
                        if _ac_valid(obj): obj.removeEventFilter(self)
                        self.watched.discard(obj)
            self.missing = [key for key, row in entries.items() if key not in by_key or type(by_key[key]).__name__ != row.get("class")]
            for obj in list(self.applied):
                if _ac_valid(obj) and obj not in objects: objects.append(obj)
            for obj in objects:
                if not _ac_valid(obj): continue
                key = keys.get(obj)
                row = entries.get(key, {})
                values = row.get("properties", {}) if row.get("class") == type(obj).__name__ else {}
                old_values = self.applied.get(obj, {})
                if not values and not old_values: continue
                if obj not in self.originals:
                    layout_keys = {"alignment", "stretch", "grid_row", "grid_column", "row_span", "column_span"}
                    owner = _ac_owner(obj, owner_objects) if set(values) & layout_keys else (None, -1)
                    self.originals[obj] = _ac_state(obj, owner_objects, owner_info=owner)
                original = self.originals[obj]
                if isinstance(obj, _ac_w.QLayout):
                    touched = set(values) | set(old_values)
                    if "spacing" in touched:
                        spacing = int(values.get("spacing", original["spacing"]))
                        if obj.spacing() != spacing: obj.setSpacing(spacing)
                    if "margins" in touched:
                        margins = values.get("margins", original["margins"])
                        m = obj.contentsMargins()
                        if [m.left(), m.top(), m.right(), m.bottom()] != list(margins): obj.setContentsMargins(*margins)
                    if isinstance(obj, _ac_w.QBoxLayout):
                        if "direction" in touched:
                            direction = _ac_w.QBoxLayout.Direction(int(values.get("direction", original["direction"])))
                            if obj.direction() != direction: obj.setDirection(direction)
                        if "order" in touched:
                            if obj not in self.orders: self.orders[obj] = _ac_order(obj, order_keys)
                            _ac_reorder(obj, values.get("order", self.orders[obj]), order_keys)
                else:
                    _ac_apply_widget(obj, values, old_values, original, owner_objects)
                self.applied[obj] = dict(values)
        finally:
            self.busy = False

    def manifest(self):
        objects, keys, parents = _ac_tree(self.root)
        result = []
        object_set = set(objects)
        owners = {}
        for layout in objects:
            if not isinstance(layout, _ac_w.QLayout): continue
            for index in range(layout.count()):
                item = layout.itemAt(index)
                child = item.widget() or item.layout()
                if child is not None: owners[child] = (layout, index)
        for obj in objects:
            parent = parents.get(obj)
            while parent is not None and parent not in object_set: parent = parents.get(parent)
            is_layout = isinstance(obj, _ac_w.QLayout)
            owner, index = owners.get(obj, (None, -1))
            row = {"id": keys[obj], "parent": keys.get(parent), "class": type(obj).__name__,
                   "name": obj.objectName(), "caption": _ac_caption(obj), "kind": "layout" if is_layout else "widget",
                   "owner": keys.get(owner), "index": index, "properties": {}}
            if is_layout:
                p = obj.parentWidget()
                position = p.mapTo(self.root, obj.geometry().topLeft()) if p else _ac_c.QPoint()
                row["rect"] = [position.x(), position.y(), obj.geometry().width(), obj.geometry().height()]
                row["visible"] = bool(p and p.isVisibleTo(self.root))
                row["properties"] = _ac_state(obj, objects)
                if isinstance(obj, _ac_w.QBoxLayout): row["properties"]["order"] = _ac_order(obj, keys)
            else:
                point = obj.mapTo(self.root, _ac_c.QPoint())
                row["rect"] = [point.x(), point.y(), obj.width(), obj.height()]
                row["visible"] = obj.isVisibleTo(self.root) and not obj.isHidden()
                state = _ac_state(obj, objects, (owner, index))
                state.pop("font", None); state.pop("style", None)
                state["visible"] = not obj.isHidden()
                state["font_size"] = obj.font().pointSizeF() if obj.font().pointSizeF() > 0 else obj.font().pixelSize()*.75
                state["bold"] = obj.font().bold()
                state["color"] = obj.palette().color(_ac_g.QPalette.WindowText).name()
                state["background"] = obj.palette().color(_ac_g.QPalette.Window).name()
                row["properties"] = state
                if isinstance(obj, _ac_w.QComboBox):
                    row["preview"] = {"type": "combo", "items": [obj.itemText(i) for i in range(obj.count())], "current": obj.currentIndex()}
                elif isinstance(obj, _ac_w.QTabWidget):
                    row["preview"] = {"type": "tab", "items": [obj.tabText(i) for i in range(obj.count())], "current": obj.currentIndex()}
                elif isinstance(obj, _ac_w.QListWidget):
                    row["preview"] = {"type": "list", "items": [obj.item(i).text() for i in range(obj.count())], "current": obj.currentRow()}
            result.append(row)
        return result


def _algo_conf_install(namespace, profile):
    """Install after class definitions and before the normal main entry point."""
    cls = namespace.get(profile.get("window_class", "MainWindow"))
    if not isinstance(cls, type) or not issubclass(cls, _ac_w.QWidget):
        return
    original = cls.__init__
    @_ac_functools.wraps(original)
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self._algo_conf_runtime = _AlgoConfRuntime(self, profile)
    cls.__init__ = initialize

