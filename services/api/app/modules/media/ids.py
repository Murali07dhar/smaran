"""UUIDv7 generator (RFC 9562). Python 3.11 has no uuid.uuid7; briefing says ids are UUIDv7."""
import os
import time
import uuid


def uuid7(now_ms: int | None = None) -> uuid.UUID:
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    rand_a = (rand >> 68) & 0xFFF  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits
    value = ((ms & ((1 << 48) - 1)) << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)
