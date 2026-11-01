"""Backend-independent MIDI input queue reader.

Some MIDI backends deliver callbacks inconsistently. This reader uses the
portable Mido ``iter_pending`` API and forwards only normalized event records.
"""
from __future__ import annotations

from midi_learn import decode_input_message


def read_input_loop(port, emit, stop_event, poll_interval=0.001, *, diagnostics=None):
    """Drain an opened Mido input port until stopped.

    ``emit`` receives normalized dictionaries. Exceptions from the backend are
    allowed to propagate to the owning worker so the UI can report a read error.
    """
    interval = max(0.0005, min(0.02, float(poll_interval)))
    while not stop_event.is_set():
        if diagnostics is not None:
            diagnostics.poll()
        if getattr(port, "closed", False):
            raise OSError("MIDI input port closed")
        # Do not exhaust a potentially busy stream before checking Stop.
        for message in port.iter_pending():
            if stop_event.is_set():
                return
            if diagnostics is not None:
                diagnostics.observe(message)
            event = decode_input_message(message)
            if event is not None:
                if diagnostics is not None:
                    diagnostics.decoded(event)
                emit(dict(event))
        stop_event.wait(interval)
