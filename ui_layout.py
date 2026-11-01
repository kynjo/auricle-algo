"""Small responsive layouts that retain controls and their signal connections."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy


PARAMETER_CELL_WIDTH = 74


def parameter_cell(text, control, *, label_factory=None):
    """Build the shared Inspector caption/control cell without binding signals."""
    cell = QWidget()
    cell.setFixedWidth(PARAMETER_CELL_WIDTH)
    column = QVBoxLayout(cell)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    label = label_factory(text, control) if label_factory is not None else QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setObjectName("knobLabel")
    column.addWidget(label)
    column.addWidget(control, 0, Qt.AlignCenter)
    return cell


class InspectorControlGrid(QGridLayout):
    """Retain parameter cells and wrap them to the width of their own group."""
    CELL_WIDTH = PARAMETER_CELL_WIDTH

    def __init__(self, parent, max_columns=8):
        super().__init__(parent)
        self.cells, self.footers = [], []
        self.max_columns = max_columns
        self.columns = 0
        self.setContentsMargins(7, 5, 7, 5)
        self.setHorizontalSpacing(4)
        self.setVerticalSpacing(3)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

    def addWidget(self, widget, *_position):
        # Source order defines navigation and wrapping. Old row/column hints
        # no longer reserve empty slots or push an anchor into a distant row.
        self.cells.append(widget)
        index = len(self.cells) - 1
        super().addWidget(widget, index // self.max_columns, index % self.max_columns,
                          Qt.AlignLeft | Qt.AlignTop)
        self.columns = 0

    def add_footer(self, widget):
        self.footers.append(widget)
        row = (len(self.cells) + self.max_columns - 1) // self.max_columns
        super().addWidget(widget, row + len(self.footers) - 1, 0, 1,
                          min(self.max_columns, max(1, len(self.cells))), Qt.AlignLeft)
        self.columns = 0

    def preferred_width(self):
        columns = min(self.max_columns, max(1, len(self.cells)))
        margins = self.contentsMargins()
        frame = self.parentWidget().contentsMargins()
        width = columns * self.CELL_WIDTH + (columns - 1) * self.horizontalSpacing()
        width += margins.left() + margins.right() + frame.left() + frame.right()
        footer_width = max((item.minimumSizeHint().width() for item in self.footers), default=0)
        return max(width, footer_width + margins.left() + margins.right() + 2)

    def reflow(self, width):
        margins = self.contentsMargins()
        frame = self.parentWidget().contentsMargins()
        available = width - margins.left() - margins.right() - frame.left() - frame.right()
        gap = self.horizontalSpacing()
        columns = max(1, min(self.max_columns, len(self.cells),
                             int((available + gap) // (self.CELL_WIDTH + gap))))
        if columns == self.columns:
            return
        self.columns = columns
        for widget in (*self.cells, *self.footers):
            self.removeWidget(widget)
        for index, widget in enumerate(self.cells):
            row, column = divmod(index, columns)
            super().addWidget(widget, row, column, Qt.AlignLeft | Qt.AlignTop)
        row = (len(self.cells) + columns - 1) // columns
        for offset, widget in enumerate(self.footers):
            super().addWidget(widget, row + offset, 0, 1, columns, Qt.AlignLeft)
        self.invalidate()


class InspectorPair(QWidget):
    """Pack two or more compact groups without stretching them into equal halves."""
    def __init__(self, host, *groups):
        super().__init__()
        self.host, self.groups, self.columns = host, groups, 0
        self._placement = None
        self._rows = {}
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.reflow()

    def reflow(self):
        available = max(InspectorControlGrid.CELL_WIDTH,
                        self.host.inspector_scroll.viewport().width() - 60)
        placements, used_widths, counts = [], [], []
        for group in self.groups:
            controls = group.layout()
            preferred = (controls.preferred_width() if isinstance(controls, InspectorControlGrid)
                         else group.minimumSizeHint().width())
            width = min(available, preferred)
            # Fill a gap in an earlier row before starting another one.
            # For example Velocity can sit beside Scale when Role wraps below.
            row = next((i for i, used in enumerate(used_widths)
                        if used + self.grid.horizontalSpacing() + width <= available), len(used_widths))
            if row == len(used_widths):
                used_widths.append(0)
                counts.append(0)
            column = counts[row]
            placements.append((row, column, width))
            used_widths[row] += (self.grid.horizontalSpacing() if column else 0) + width
            counts[row] += 1
        signature = tuple(placements)
        if signature == self._placement:
            return
        self._placement = signature
        self.columns = max(counts)
        # Keep row layouts too. Groups retain the same QWidget parent and
        # focus chain while they move between rows.
        for layout in self._rows.values():
            for group in self.groups:
                layout.removeWidget(group)
        for group, (row, column, width) in zip(self.groups, placements):
            controls = group.layout()
            if isinstance(controls, InspectorControlGrid):
                controls.reflow(width)
            group.setFixedWidth(width)
            if row not in self._rows:
                layout = QGridLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setHorizontalSpacing(self.grid.horizontalSpacing())
                layout.setVerticalSpacing(0)
                layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                self.grid.addLayout(layout, row, 0)
                self._rows[row] = layout
            self._rows[row].addWidget(group, 0, column, Qt.AlignLeft | Qt.AlignTop)
        self.grid.invalidate()
        self.updateGeometry()


class InspectorIdentity:
    """Reflow the existing identity/output fields without reconstructing them."""
    def __init__(self, host, grid, fields, footer):
        self.host, self.grid, self.fields, self.footer = host, grid, fields, footer
        self.columns = 0
        self.reflow()

    def reflow(self):
        width = self.host.inspector_scroll.viewport().width() - 60
        columns = 3 if width >= 840 else 2 if width >= 580 else 1
        if columns == self.columns:
            return
        self.columns = columns
        for label, field in self.fields:
            self.grid.removeWidget(label)
            self.grid.removeWidget(field)
        self.grid.removeWidget(self.footer)
        for column in range(6):
            self.grid.setColumnStretch(column, 0)
        for index, (label, field) in enumerate(self.fields):
            row, column = divmod(index, columns)
            self.grid.addWidget(label, row, column * 2)
            self.grid.addWidget(field, row, column * 2 + 1, Qt.AlignLeft)
        self.grid.setColumnStretch(columns * 2 - 1, 1)
        self.grid.addWidget(self.footer, (len(self.fields) + columns - 1) // columns,
                            0, 1, columns * 2)
        self.grid.invalidate()
