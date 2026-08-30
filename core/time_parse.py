"""
Fylorra - Time Parsing
Parses common time formats into seconds.
"""

from __future__ import annotations


def parse_timestamp_to_seconds(value: str) -> float:
    """
    Accepts:
    - "3:47" (mm:ss)
    - "1:03:47" (hh:mm:ss)
    - "227.5" (seconds)
    - "00:03:47.250"
    """
    value = (value or "").strip()
    if not value:
        raise ValueError("Empty timestamp")

    # Raw seconds
    if ":" not in value:
        return float(value)

    parts = value.split(":")
    if len(parts) not in (2, 3):
        raise ValueError("Invalid timestamp format")

    try:
        parts_f = [float(p) for p in parts]
    except Exception as e:
        raise ValueError("Invalid timestamp format") from e

    if len(parts_f) == 2:
        mm, ss = parts_f
        return mm * 60.0 + ss
    hh, mm, ss = parts_f
    return hh * 3600.0 + mm * 60.0 + ss

