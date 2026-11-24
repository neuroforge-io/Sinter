# SPDX-License-Identifier: Apache-2.0
"""Bounded speech-backend discovery for Sinter."""
from __future__ import annotations

import importlib.util

from . import erais_native_backend
from .contracts import BackendCapabilities

BACKEND_IDS = ("faster-whisper", "erais-native")


def faster_whisper_capabilities(models: tuple[str, ...]) -> BackendCapabilities:
    available = importlib.util.find_spec("faster_whisper") is not None
    return BackendCapabilities(
        backend_id="faster-whisper",
        installed=available,
        local=True,
        models=models,
        supported_languages=(),
        word_timing="estimated",
        channel_separation=True,
        speaker_diarization=False,
        network_required=False,
        notice=(
            "Optional local faster-whisper package found."
            if available else
            "Install the optional faster-whisper speech package, then restart Sinter."),
    )


def capabilities(models: tuple[str, ...]) -> dict:
    descriptors = [
        faster_whisper_capabilities(models),
        erais_native_backend.capabilities(),
    ]
    return {
        "backends": [item.to_mapping() for item in descriptors],
        "available_backends": [
            item.backend_id for item in descriptors if item.installed],
    }


def get(backend_id: str):
    if backend_id == "erais-native":
        return erais_native_backend
    if backend_id == "faster-whisper":
        return None
    raise ValueError("Choose a supported local speech backend.")


__all__ = ["BACKEND_IDS", "capabilities", "faster_whisper_capabilities", "get"]
