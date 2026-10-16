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
