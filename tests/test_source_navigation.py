"""Source colours remain legible without replacing native tab navigation."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout

import auricle_gui as gui
from parameter_sources import SOURCE_COLORS
from test_kit_preview_lifecycle import inspector
from ui_themes import theme_names, theme_palette, theme_stylesheet, contrast_ratio


@pytest.mark.parametrize("theme_name", theme_names())
def test_source_tabs_are_painted_with_readable_labels_in_every_theme(theme_name):
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    theme = theme_palette(theme_name)
    host._active_theme = theme
    host.setStyleSheet(theme_stylesheet(theme_name))
    layout = QVBoxLayout(host)
    bar = gui.SourceTabBar()
    bar.setObjectName("headerNavigation")
    bar.setExpanding(False)
    bar.setDrawBase(False)
    layout.addWidget(bar)
    for name, symbol in gui.NAVIGATION_SYMBOLS.items():
        index = bar.addTab(gui.monochrome_tab_icon(symbol), name)
        if name.title() in SOURCE_COLORS:
            bar.setTabData(index, name.title())
    host.resize(850, 75)
    host.show()
    app.processEvents()
    original_rects = [bar.tabRect(i) for i in range(bar.count())]
    for selected in (0, 1, 2, 3):
        bar.setCurrentIndex(selected)
        app.processEvents()
        image = bar.grab().toImage()
        for index in (1, 2, 3):
            source = bar.tabData(index)
            background, ink, border = bar.source_colors(theme, source, index == selected)
            assert contrast_ratio(ink, background) >= 4.5
            rect = bar.tabRect(index)
            assert image.pixelColor(rect.center().x(), rect.top() + 4).name() == background
            # Check actual rendered text/icon pixels, not just the palette.
            pixels = [image.pixelColor(x, y).name()
                      for y in range(rect.top() + 8, rect.bottom() - 5)
                      for x in range(rect.left() + 8, rect.right() - 8)]
            assert max(contrast_ratio(pixel, background) for pixel in pixels) >= 4.5
        assert [bar.tabRect(i) for i in range(bar.count())] == original_rects
    host.close()
    host.deleteLater()
    app.processEvents()


def test_coloured_tabs_keep_click_keyboard_and_programmatic_navigation(inspector):
    gui, win, drum, melody, errors = inspector
    win.show()
    QTest.qWait(40)
    bar = win.header_nav
    assert isinstance(bar, gui.SourceTabBar)
    assert [bar.tabData(i) for i in range(bar.count())] == [None, "Composition", "Relations", None, None]
    before = win.history_controller.snapshot()
    for index in (1, 2, 3, 0):
        QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(index).center())
        assert bar.currentIndex() == win.tabs.currentIndex() == index
    bar.setFocus()
    QTest.keyClick(bar, Qt.Key_Right)
    assert bar.currentIndex() == win.tabs.currentIndex() == 1
    win.tabs.setCurrentWidget(win.composition_panel)
    assert bar.currentIndex() == win.tabs.currentIndex() == 1
    assert win.history_controller.snapshot() == before
    assert not errors


def test_theme_changes_preserve_coloured_sources_and_all_five_icons(inspector):
    gui, win, drum, melody, errors = inspector
    win.show()
    win.header_nav.setCurrentIndex(1)
    for theme_name in ("Solar", "Midnight", "Cream Studio"):
        win.theme_combo.setCurrentText(theme_name)
        QApplication.processEvents()
        for index in range(win.tabs.count()):
            text = win.tabs.tabText(index)
            expected = gui.monochrome_tab_icon(gui.NAVIGATION_SYMBOLS[text], color=theme_palette(theme_name).muted)
            assert win.tabs.tabIcon(index).pixmap(16, 16).toImage() == expected.pixmap(16, 16).toImage()
        assert win.header_nav.tabData(1) == "Composition"
        assert win.header_nav.currentIndex() == 1
    assert not errors
