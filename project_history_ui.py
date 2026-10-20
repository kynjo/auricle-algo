"""Qt adapter for document history; no widget instances are stored in snapshots."""
from __future__ import annotations

import os
import time
from pathlib import Path
from shiboken6 import isValid
from PySide6.QtCore import QObject, QEvent, QTimer, Qt, QStandardPaths
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QSlider, QMessageBox, QInputDialog, QWidget
from auricle_persistence import project_from_dict
from project_history import ProjectHistory, RecoveryStore, document_state, process_alive

_GESTURE_EVENTS = frozenset((QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                           QEvent.Wheel, QEvent.KeyPress, QEvent.ContextMenu))


class HistoryController(QObject):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.restoring = False
        self.pending = False
        self.group = None
        self.pending_group = None
        self.serial = 0
        self.wheel = None
        self.last_wheel = 0.0
        self.history = ProjectHistory(self.snapshot())
        directory = os.environ.get('AURICLE_RECOVERY_DIR') or str(Path(
            QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'Auricle' / 'recovery')
        self.recovery = RecoveryStore(directory)
        self.commit_timer = QTimer(self)
        self.commit_timer.setSingleShot(True)
        self.commit_timer.timeout.connect(self.flush)
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setSingleShot(True)
        self.recovery_timer.setInterval(2000)
        self.recovery_timer.timeout.connect(self.checkpoint)
        menu = host.menuBar().addMenu('Edit')
        self.undo_action = menu.addAction('Undo')
        self.undo_action.setShortcut(QKeySequence('Ctrl+Z'))
        self.undo_action.triggered.connect(lambda: self.move(False))
        self.redo_action = menu.addAction('Redo')
        self.redo_action.setShortcuts([QKeySequence('Ctrl+Shift+Z'), QKeySequence('Ctrl+Y')])
        self.redo_action.triggered.connect(lambda: self.move(True))
        menu.addSeparator()
        menu.addAction('Parameter influences…', self.show_influences)
        menu.addAction('Recover session…', self.offer_recovery)
        QApplication.instance().installEventFilter(self)
        self.sync_actions()

    def snapshot(self):
        with self.host.transport._state_lock:
            return document_state(self.host.project, self.host.engine)

    def changed(self):
        if self.restoring: return
        self.pending = True
        self.pending_group = self.group
        self.commit_timer.start(0)
        if not self.recovery_timer.isActive(): self.recovery_timer.start()

    def flush(self):
        self.commit_timer.stop()
        if self.pending and not self.restoring:
            self.history.commit(self.snapshot(), self.pending_group)
        self.pending = False
        self.sync_actions()

    def sync_actions(self):
        self.undo_action.setEnabled(self.history.can_undo)
        self.redo_action.setEnabled(self.history.can_redo)
        self.host._dirty = self.history.dirty
        self.host._update_title()

    def reset(self):
        if self.restoring: return
        self.pending = False
        self.commit_timer.stop()
        self.recovery_timer.stop()
        self._clear_checkpoint()
        self.history.reset(self.snapshot())
        self.group = None
        self.sync_actions()

    def saved(self):
        self.flush()
        self.history.mark_clean()
        self.recovery_timer.stop()
        self._clear_checkpoint()
        self.sync_actions()

    def _clear_checkpoint(self):
        try: self.recovery.clear()
        except OSError as exc: self.host.set_message('Recovery cleanup failed: ' + str(exc))

    def move(self, redo=False):
        self.flush()
        if not (self.history.can_redo if redo else self.history.can_undo): return
        before = self.snapshot()
        state = self.history.redo() if redo else self.history.undo()
        host = self.host
        selected, voice = host.selected_block_id, host.selected_drum_voice_id
        self.restoring = True
        # Widget construction emits thousands of layout/style events. History
        # only needs user gestures; do not route rebuild traffic through Python.
        app = QApplication.instance()
        app.removeEventFilter(self)
        updates_enabled = host.updatesEnabled()
        host.setUpdatesEnabled(False)
        try:
            with host.transport._state_lock:
                running = host.transport.running
                position = host.engine.clock.position_beats
                active = bool(host.engine.performance.active or host.engine.director.phrase.running)
                message = 'Redo' if redo else 'Undo'
                if host._restore_parameter_history(before, state):
                    host.set_message(message)
                else:
                    host._install_project(project_from_dict(state, normalize=False), host.current_path,
                                          message, selection=(selected, voice))
                if running:
                    # Keep musical time; an undo must not restart every part at bar 1.
                    now = time.monotonic()
                    host.engine.clock.start(now, host.project.tempo)
                    host.engine.clock.position_beats = position
                    host.engine.performance._last_time = now
                    host.transport._master_due = now
                    host.transport._master_step = int(position * 4)
                    host.transport.running = True
                    # Parameter Undo must not probe/reopen native MIDI devices.
                    def ports(data):
                        return [(b.get('midi_port', ''), [v.get('midi_port', '') for v in b.get('drum_voices') or []])
                                for b in data.get('blocks', [])]
                    if ports(before) != ports(state):
                        host.transport.refresh_ports()
                if active: host.set_message(('Redo' if redo else 'Undo') + ' · performance gestures stopped')
        finally:
            self.restoring = False
            host.setUpdatesEnabled(updates_enabled)
            app.installEventFilter(self)
        self.group = None
        self.sync_actions()
        self.recovery_timer.start()

    def checkpoint(self):
        self.flush()
        try:
            if self.history.dirty:
                self.recovery.write(self.snapshot(), self.host.current_path)
            else:
                self.recovery.clear()
        except (OSError, ValueError, TypeError) as exc:
            self.host.set_message('Recovery checkpoint failed: ' + str(exc))

    def offer_recovery(self, startup=False):
        candidates = []
        for path, data in self.recovery.candidates():
            if process_alive(data.get('pid')):
                continue  # another Auricle instance still owns this session
            candidates.append((path, data))
        if not candidates:
            if not startup: self.host.set_message('No interrupted sessions to recover')
            return
        labels = [time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['time'])) + ' · ' +
                  (Path(data['source_path']).name if data.get('source_path') else 'untitled') +
                  ' · ' + path.stem[-6:] for path, data in candidates]
        choice, ok = QInputDialog.getItem(self.host, 'Recover interrupted session',
            'Restore unsaved changes (the saved project will not be overwritten):', labels, 0, False)
        if not ok or not self.host._confirm_discard_changes(): return
        path, data = candidates[labels.index(choice)]
        self.host._install_project(project_from_dict(data['project']), data.get('source_path'), 'Recovered unsaved session')
        self.history.clean = None
        self.sync_actions()
        # Keep the old checkpoint unless a new durable copy is safely written.
        try:
            self.recovery.write(self.snapshot(), self.host.current_path)
            path.unlink(missing_ok=True)
        except OSError as exc:
            self.host.set_message('Recovered; could not move checkpoint: ' + str(exc))

    def show_influences(self, block_id=None, key=None):
        from parameter_influence_ui import InfluenceDialog
        host = self.host
        block_id = block_id if block_id is not None else (host.selected_drum_voice_id or host.selected_block_id)
        if host.get_entity(block_id) is None: return
        dialog = InfluenceDialog(host, block_id, key)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()

    def eventFilter(self, obj, event):
        if self.restoring: return False
        kind = event.type()
        if kind not in _GESTURE_EVENTS: return False
        if not isValid(self.host) or not isValid(obj): return False
        if not isinstance(obj, QWidget) or (obj.window() is not self.host and not self.host.isAncestorOf(obj)):
            return False
        parameter = getattr(obj, '_auricle_parameter', None)
        if parameter and ((kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton
                           and event.position().y() >= obj.height() - 21)
                          or kind == QEvent.ContextMenu):
            self.flush()
            self.show_influences(*parameter)
            return True
        if kind == QEvent.MouseButtonPress:
            self.flush()
            self.serial += 1
            self.group = ('press', self.serial)
        elif kind == QEvent.MouseButtonRelease:
            # Flush after clicked/valueChanged and any same-turn model updates.
            QTimer.singleShot(0, self._end_gesture)
        elif kind == QEvent.Wheel:
            now = time.monotonic()
            if self.wheel != id(obj) or now - self.last_wheel > .4:
                self.flush()
                self.serial += 1
            self.wheel, self.last_wheel = id(obj), now
            self.group = ('wheel', self.serial)
            QTimer.singleShot(450, self._finish_wheel)
        elif kind == QEvent.KeyPress and not event.isAutoRepeat():
            self.flush()
            self.serial += 1
            self.group = ('key', self.serial)
        return False

    def _finish_wheel(self):
        if time.monotonic() - self.last_wheel >= .4: self._end_gesture()

    def _end_gesture(self):
        self.flush()
        self.group = None

    def close(self):
        self.commit_timer.stop()
        self.recovery_timer.stop()
        self._clear_checkpoint()
        QApplication.instance().removeEventFilter(self)
