"""Count the bounded, normalized campaign without duplicating nested records."""

from __future__ import annotations


def text_characters(value: object) -> int:
    """Count string values once, including identity fields and saved snapshots.

    Use only after campaign field/row validation has bounded the structure.
    Keys and JSON punctuation belong to the separate encoded-byte limit.
    """
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(text_characters(item) for item in value.values())
    if isinstance(value, list):
        return sum(text_characters(item) for item in value)
    return 0
