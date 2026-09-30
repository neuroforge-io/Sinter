"""Versioned, destination-bound public model capabilities.

Protocol qualification does not establish answer quality. Native ERAIS remains
explicitly unqualified for general chat; it accepts a small buffered text subset.
The contract is mirrored from NeuroForge's public native_model_api_contract.mjs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .providers import OPENAI_COMPATIBLE, ProviderProtocolError, ProviderReply

NATIVE_MODEL = "erais-native-qwen3"
NATIVE_CONTRACT_VERSION = 1
PUBLIC_TEXT_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


@dataclass(frozen=True)
class NativeProfile:
    model: str = NATIVE_MODEL
    min_output_tokens: int = 1
    max_output_tokens: int = 128
    max_prompt_tokens: int = 512
    max_question_bytes: int = 2048
    max_history_bytes: int = 4096
    max_history_exchanges: int = 3
    max_output_bytes: int = 8192
    request_bytes: int = 32768
    response_bytes: int = 65536
    deadline_seconds: float = 50.0


NATIVE_PROFILE = NativeProfile()
NATIVE_CAPABILITIES = {
    "model_id": NATIVE_MODEL,
    "architecture": "ERAIS native adaptive decoder",
    "backend_kind": "erais_native_adaptive_decoder",
    "fully_native": True,
    "source_family": "Qwen3",
    "tokenizer_dependency": True,
    "dynamic_adaptive_patching": False,
    "native_learned_breadth": True,
    "native_learned_recurrence": True,
    "training": False,
    "retained_session_learning": False,
    "externally_resident": False,
    "sparse_savings_verified": False,
    "quality_scope": "unqualified_for_general_chat",
    "request_state": "ephemeral_same_world_lease",
    "streaming": False,
    "max_output_tokens": NATIVE_PROFILE.max_output_tokens,
    "max_prompt_bytes": NATIVE_PROFILE.max_question_bytes,
    "max_history_bytes": NATIVE_PROFILE.max_history_bytes,
    "max_history_exchanges": NATIVE_PROFILE.max_history_exchanges,
    "system_prompt": "deployment_owned",
    "sampling": "deployment_owned",
    "assistant_quality": False,
    "account_billing_complete": False,
}


def native_profile_applies(model: str, base_url: str, provider: str) -> bool:
    """A name on a custom server never inherits NeuroForge capabilities."""
    if model != NATIVE_MODEL or provider != OPENAI_COMPATIBLE:
        return False
    try:
        parsed = urlsplit(base_url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "neuroforge.io"
            and parsed.port in {None, 443}
            and parsed.path.rstrip("/") == "/v1"
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )
    except (TypeError, ValueError):
        return False


def qualify_native_catalog(item: dict) -> None:
    """Require the advertised native identity and truthful capability flags."""
    metadata = item.get("erais") if isinstance(item, dict) else None
    if (
        not isinstance(item, dict)
        or item.get("id") != NATIVE_MODEL
        or not isinstance(metadata, dict)
        or any(
            type(metadata.get(key)) is not type(expected) or metadata[key] != expected
            for key, expected in NATIVE_CAPABILITIES.items()
        )
        or metadata.get("modalities") != ["text"]
        or not isinstance(metadata.get("runtime_id"), str)
        or re.fullmatch(r"[a-f0-9]{32}", metadata["runtime_id"]) is None
    ):
        raise ProviderProtocolError(
            "The service did not advertise the supported native ERAIS contract. "
            "Its identity or capabilities could not be verified. "
            "No generation request was sent."
        )


def native_request(value: object) -> dict:
    """Validate/normalize the exact buffered subset; never trim caller text."""
    profile = NATIVE_PROFILE
    if (
        not isinstance(value, dict)
        or set(value) - {"model", "messages", "max_tokens", "stream", "n"}
        or value.get("model") != NATIVE_MODEL
    ):
        raise ValueError(
            "Use the supported native ERAIS text request. "
            "Caller sampling, tools and runtime overrides are not supported."
        )
    maximum = value.get("max_tokens", profile.max_output_tokens)
    if (
        type(maximum) is not int
        or not profile.min_output_tokens <= maximum <= profile.max_output_tokens
    ):
        raise ValueError("Native ERAIS accepts an output limit from 1 to 128 tokens.")
    if (
        value.get("stream", False) is not False
        or type(value.get("n", 1)) is not int
        or value.get("n", 1) != 1
    ):
        raise ValueError(
            "Native ERAIS accepts one buffered JSON answer; streaming is unavailable."
        )
    messages = value.get("messages")
    if isinstance(messages, list) and any(
        isinstance(message, dict) and message.get("role") == "system"
        for message in messages
    ):
        raise ValueError(
            "The selected native ERAIS model does not accept system "
            "instructions. Use a short question, or choose a model "
            "that supports this workflow in Settings. No request was sent."
        )
    if (
        not isinstance(messages, list)
        or not 1 <= len(messages) <= 2 * profile.max_history_exchanges + 1
        or len(messages) % 2 != 1
    ):
        raise ValueError(
            "Native ERAIS accepts a question and at most three earlier "
            "exchanges. Start a new chat; no history was silently removed."
        )
    history = 0
    for index, message in enumerate(messages):
        if (
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or message.get("role") != ("assistant" if index % 2 else "user")
        ):
            raise ValueError(
                "Native ERAIS requires alternating user and assistant "
                "messages ending with your question."
            )
        content = message["content"]
        if (
            not isinstance(content, str)
            or not content.strip(PUBLIC_TEXT_WHITESPACE)
            or "\0" in content
        ):
            raise ValueError(
                "Native ERAIS needs non-empty ordinary text without null characters."
            )
        try:
            size = len(content.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError("The native ERAIS text contains invalid Unicode.") from exc
        if index == len(messages) - 1:
            if size > profile.max_question_bytes:
                raise ValueError(
                    "The native ERAIS question exceeds 2,048 UTF-8 bytes. "
                    "Shorten it or choose another model; no text was removed."
                )
        else:
            history += size
    if history > profile.max_history_bytes:
        raise ValueError(
            "The native ERAIS history exceeds 4,096 UTF-8 bytes. "
            "Start a new chat or choose another model; no history was removed."
        )
    output = {
        "model": NATIVE_MODEL,
        "messages": [dict(message) for message in messages],
        "max_tokens": maximum,
        "stream": False,
        "n": 1,
    }
    if (
        len(
            json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        > profile.request_bytes
    ):
        raise ValueError(
            "The native ERAIS request exceeds its JSON limit. "
            "Shorten the supplied text before sending."
        )
    return output


def native_reply(value: object, maximum: int) -> ProviderReply:
    """Validate the complete public native JSON contract before exposing text."""
    profile = NATIVE_PROFILE
    try:
        if (
            type(maximum) is not int
            or not profile.min_output_tokens <= maximum <= profile.max_output_tokens
            or not isinstance(value, dict)
            or value.get("object") != "chat.completion"
            or value.get("model") != NATIVE_MODEL
        ):
            raise ValueError
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError
        choice = choices[0]
        if (
            not isinstance(choice, dict)
            or type(choice.get("index")) is not int
            or choice["index"] != 0
        ):
            raise ValueError
        message = choice.get("message")
        if (
            not isinstance(message, dict)
            or message.get("role") != "assistant"
            or "tool_calls" in message
            or "function_call" in message
        ):
            raise ValueError
        text = message.get("content")
        if (
            not isinstance(text, str)
            or not text.strip(PUBLIC_TEXT_WHITESPACE)
            or "\0" in text
            or len(text.encode("utf-8")) > profile.max_output_bytes
        ):
            raise ValueError
        reason = choice.get("finish_reason")
        if reason not in {"stop", "length"}:
            raise ValueError
        usage = value.get("usage")
        if not isinstance(usage, dict):
            raise ValueError
        prompt, completion, total = (
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
        if (
            any(type(amount) is not int for amount in (prompt, completion, total))
            or not 1 <= prompt <= profile.max_prompt_tokens
            or not 1 <= completion <= maximum
            or total != prompt + completion
        ):
            raise ValueError
        return ProviderReply(text, prompt, completion, total, reason, NATIVE_MODEL)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ProviderProtocolError(
            "The native ERAIS response did not match its supported text contract. "
            "The output was rejected; no request was replayed."
        ) from exc
