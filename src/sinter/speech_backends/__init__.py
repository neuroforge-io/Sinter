# SPDX-License-Identifier: Apache-2.0
"""Common contracts and discovery for optional local speech backends."""
from .contracts import (
    BackendCapabilities,
    SpeechBackend,
    SpeechBackendError,
    TranscriptionRequest,
)
from .registry import BACKEND_IDS, capabilities, get

__all__ = [
    "BACKEND_IDS",
    "BackendCapabilities",
    "SpeechBackend",
    "SpeechBackendError",
    "TranscriptionRequest",
    "capabilities",
    "get",
]
