"""Preserve transcript provenance when deriving a reviewed correction."""
from datetime import datetime

from .evidence import Source, source

_ABSENT = object()


def original_transcript_source(notes: str, pin: object = _ABSENT) -> Source:
    """Keep an originating source's metadata after checking its raw text.

    Args:
        notes: The unchanged original transcript, before reviewed corrections.
        pin: Optional source ID, content hash and original capture timestamp.

    Returns:
        The canonical transcript source, retaining a supplied timestamp verbatim.

    Raises:
        ValueError: A supplied pin is malformed or describes different text.

    A pin preserves local history; it does not authenticate the capture time.
    Only an absent pin means a fresh capture. Invalid pins never fall back.
    """
    if pin is _ABSENT:
        return source("Original transcript", notes, kind="transcript")
    if (not isinstance(pin, dict)
            or set(pin) != {"id", "sha256", "retrieved_at"}
            or any(not isinstance(value, str) or not value
                   for value in pin.values())):
        raise ValueError("The original transcript source pin is invalid.")
    captured = pin["retrieved_at"]
    message = "The transcript capture time must be a timezone-aware ISO timestamp."
    if (len(captured) > 100 or captured != captured.strip()
            or len(captured) <= 10 or captured[10] not in {"T", "t"}):
        raise ValueError(message)
    try:
        parsed = datetime.fromisoformat(
            captured[:-1] + "+00:00"
            if captured.endswith(("Z", "z")) else captured)
        aware = parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (ValueError, OverflowError):
        aware = False
    if not aware:
        raise ValueError(message)
    original = source("Original transcript", notes, kind="transcript",
                      retrieved_at=captured)
    if original.id != pin["id"] or original.sha256 != pin["sha256"]:
        raise ValueError(
            "The transcript source no longer matches the original notes. "
            "Keep the earlier report, or prepare changed notes as a new transcript.")
    return original
