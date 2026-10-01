"""Hash-pinned fictional historical reports for compatibility tests and QA.

This is a data oracle, not an old application reader or a current qualification.
Original report/draft golden hashes and previously published receipts stay intact.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ORACLE_SHA256 = "f64d626cfe7344f00dc499eae3f1a7e0fd7d9238269bc5be2d12f8718076bdb4"
ORACLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/handover_pre_recipient_v1.json"
)


def historical_handover(name: str) -> dict:
    """Return a distinct copy of the exact old fictional data, without rerender."""
    content = ORACLE_PATH.read_bytes()
    if hashlib.sha256(content).hexdigest() != ORACLE_SHA256:
        raise ValueError("The historical handover oracle bytes changed.")
    data = json.loads(content)
    if (
        set(data) != {"schema", "source_commit", "handover_source_sha256", "fixtures"}
        or data["schema"] != "sinter-historical-handover-oracles/v1"
        or data["source_commit"] != "246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe"
        or data["handover_source_sha256"]
        != "0a29fed573e365b44a747ada0ecb3934d22914b336b43cbf684fbf763e6f513d"
        or name not in data["fixtures"]
    ):
        raise ValueError("The historical handover oracle identity is unsupported.")
    return copy.deepcopy(data["fixtures"][name])
