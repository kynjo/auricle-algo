"""Thread-safe transport event queue for v105 look-ahead scheduling."""
from __future__ import annotations
import heapq
import threading
import time

class TransportEventQueue:
    def __init__(self):
        self._heap=[]
        self._lock=threading.Lock()
        self._counter=0
        self._keys=set()

    def push(self, when, callback, key=None):
        """Queue one event, returning False when its key is already pending.

        Look-ahead scheduling runs repeatedly while the worker catches up. A
        stable key makes that loop idempotent and prevents duplicate ticks from
        entering the heap.
        """
        with self._lock:
            if key is not None and key in self._keys:
                return False
            self._counter += 1
            if key is not None:
                self._keys.add(key)
            heapq.heappush(self._heap,(when,self._counter,key,callback))
            return True

    def pop_due(self, now=None):
        if now is None: now=time.monotonic()
        out=[]
        with self._lock:
            while self._heap and self._heap[0][0] <= now:
                _when, _counter, key, callback = heapq.heappop(self._heap)
                if key is not None:
                    self._keys.discard(key)
                out.append(callback)
        return out

    def __len__(self):
        with self._lock:
            return len(self._heap)


class TransportCommandQueue:
    """Thread-safe queue for model edits submitted by the Qt GUI.

    Commands are drained only by the transport thread at a tick boundary.
    Optional keys coalesce high-rate controls (knob/slider drags) while
    preserving the original queue position of the first edit.
    """
    def __init__(self):
        from collections import deque
        self._items = deque()
        self._by_key = {}
        self._lock = threading.Lock()

    def push(self, callback, *, key=None, notification=None, label="GUI edit"):
        if not callable(callback):
            raise TypeError("transport command must be callable")
        with self._lock:
            if key is not None and key in self._by_key:
                item = self._by_key[key]
                item["callback"] = callback
                item["notification"] = notification
                item["label"] = str(label)
                return False
            item = {"key": key, "callback": callback,
                    "notification": notification, "label": str(label)}
            self._items.append(item)
            if key is not None:
                self._by_key[key] = item
            return True

    def pop_all(self):
        with self._lock:
            items = list(self._items)
            self._items.clear()
            self._by_key.clear()
        return items

    def __len__(self):
        with self._lock:
            return len(self._items)
