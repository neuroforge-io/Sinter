# SPDX-License-Identifier: Apache-2.0
"""Common speech-backend contracts without importing an optional engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

Progress = Callable[[str | dict], None]


class SpeechBackendError(ValueError):
    """A stable, user-safe backend failure."""


@dataclass(frozen=True)
class BackendCapabilities:
    backend_id: str
    installed: bool
    local: bool
    models: tuple[str, ...] = ()
    model_labels: tuple[tuple[str, str], ...] = ()
    supported_languages: tuple[str, ...] = ()
    word_timing: str = "unavailable"
    channel_separation: bool = False
    speaker_diarization: bool = False
    meeting_stream: bool = False
    network_required: bool = False
    notice: str = ""
    runtime_identity: str = ""
    manifest_identity: str = ""

    def to_mapping(self) -> dict:
        return {
            "id": self.backend_id,
            "installed": self.installed,
            "local": self.local,
            "models": list(self.models),
            "model_labels": dict(self.model_labels),
            "supported_languages": list(self.supported_languages),
            "word_timing": self.word_timing,
            "channel_separation": self.channel_separation,
            "speaker_diarization": self.speaker_diarization,
            "meeting_stream": self.meeting_stream,
            "network_required": self.network_required,
            "notice": self.notice,
            "runtime_identity": self.runtime_identity,
            "manifest_identity": self.manifest_identity,
        }


@dataclass(frozen=True)
class TranscriptionRequest:
    source: Path
    model: str
    language: str = "auto"
    split_channels: bool = False
    allow_download: bool = False
    consent: bool = False
    backend: str = "erais-native"
    request_id: str = ""
    retention_policy: str = "temporary_only"


class SpeechBackend(Protocol):
    def capabilities(self) -> BackendCapabilities:
        ...

    def transcribe(
        self,
        request: TranscriptionRequest,
        progress: Progress = lambda _message: None,
    ) -> dict:
        ...


__all__ = [
    "BackendCapabilities",
    "Progress",
    "SpeechBackend",
    "SpeechBackendError",
    "TranscriptionRequest",
]
