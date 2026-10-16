import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_dirty_marker_and_discard_guard(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    import auricle_gui as gui

    app = QApplication.instance() or QApplication([])
    window = gui.MainWindow()
    try:
        window._dirty = False
        window._update_title()
        assert not window.windowTitle().endswith(" *")

        window._mark_dirty()
        assert window.windowTitle().endswith(" *")
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Discard)
        assert window._confirm_discard_changes()
    finally:
        window.performance_timer.stop()
        window.transport_worker.stop()
        window.transport.stop()
        window.transport.close_ports()
