"""UUIDv7 generator (Python 3.11/3.12 stdlib has no uuid7).

Use `uuid7()` for every server-generated id so ids stay time-sortable like the
client-generated ones. RFC 9562 layout: 48-bit unix-ms | ver 7 | 12-bit rand_a | var | 62-bit rand_b.
"""
from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_last_seq = 0


def uuid7() -> uuid.UUID:
    global _last_ms, _last_seq
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms <= _last_ms:  # keep monotonic within one process
            ms = _last_ms
            _last_seq += 1
            if _last_seq > 0xFFF:
                ms += 1
                _last_seq = 0
        else:
            _last_seq = int.from_bytes(os.urandom(2), "big") & 0x7FF
        _last_ms = ms
        seq = _last_seq
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= seq << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)
