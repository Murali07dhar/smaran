"""Minimal single-range HTTP Range parsing (RFC 9110). Safari needs Range for <audio>/<video>.

Pure module. Multi-range and malformed headers are ignored (full response), which the RFC allows.
"""
import re

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeNotSatisfiable(Exception):
    pass


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Return inclusive (start, end) for a satisfiable single range, or None for 'send everything'.

    Raises RangeNotSatisfiable when the range lies outside the representation.
    """
    if not header:
        return None
    match = _RANGE.fullmatch(header.strip())
    if not match:
        return None
    first, last = match.groups()
    if first == "" and last == "":
        return None
    if first == "":  # suffix: last N bytes
        count = int(last)
        if count == 0 or size == 0:
            raise RangeNotSatisfiable()
        return max(size - count, 0), size - 1
    start = int(first)
    if last != "" and int(last) < start:
        return None  # invalid syntax, ignore
    if start >= size:
        raise RangeNotSatisfiable()
    end = size - 1 if last == "" else min(int(last), size - 1)
    return start, end
