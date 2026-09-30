"""Text-only provider protocols; transport, credentials and budgets stay in client.

No adapter retries a generation or executes model-proposed tools. The same
normalized reply is used by JSON and streaming callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from . import __version__

OPENAI_COMPATIBLE = "openai-compatible"
ANTHROPIC = "anthropic"
CHATGPT = "chatgpt"
CHATGPT_API_URL = "https://api.openai.com/v1"
PROVIDER_IDS = frozenset({OPENAI_COMPATIBLE, ANTHROPIC, CHATGPT})


class ProviderProtocolError(ValueError):
    """A safe protocol error that never includes upstream content."""


class ProviderCompletionMismatch(ProviderProtocolError):
    """Verified streamed text remains reviewable after inconsistent completion."""


class ProviderIdentityError(ProviderProtocolError):
    """An untrusted model identity prevents treating the response as output."""


@dataclass(frozen=True)
class ProviderFailure:
    """Whitelisted recovery advice and bounded, non-secret diagnostics."""

    message: str
    code: str = ""
    upstream_status: int | None = None


_CHATGPT_ERRORS = {
    "subscription_sharing_usage_limit_exceeded": (
        "ChatGPT reported a usage limit for this connection. Pause requests and "
        "check ChatGPT Settings → Usage for Sinter's app limit and plan limits. "
        "This code does not establish which limit applies or its reset time."
    ),
    "subscription_sharing_user_not_eligible": (
        "ChatGPT plan usage is unavailable for the selected account, workspace "
        "or policy. Choose an eligible connection; repeating sign-in will not "
        "resolve this restriction."
    ),
    "subscription_sharing_usage_unavailable": (
        "ChatGPT could not check usage availability. Keep this connection and "
        "try again later."
    ),
    "subscription_sharing_user_unavailable": (
        "ChatGPT account or workspace information is temporarily unavailable. "
        "Keep this connection and try again later."
    ),
    "subscription_sharing_invalid_user": (
        "ChatGPT could not validate the selected account. Check the account "
        "and permissions; sign in again after a confirmed disconnection."
    ),
    "chatpass_v2_scope_not_authorized": (
        "The ChatGPT grant does not permit this request. Check the selected "
        "account's granted permissions before trying again."
    ),
    "chatpass_v2_invalid_authorization_context": (
        "The ChatGPT authorization context does not permit this request. "
        "Check the account and grant configuration before trying again."
    ),
    "subscription_sharing_unsupported_capability": (
        "ChatGPT plan usage does not support a requested capability. Review "
        "the request before trying again; do not repeat the same request."
    ),
    "subscription_sharing_route_not_supported": (
        "ChatGPT plan usage does not support this API route. Check the "
        "connection configuration before trying again."
    ),
    "rate_limit_exceeded": (
        "ChatGPT reported a rate limit. Pause requests and try again later. "
        "This does not establish that the whole plan is exhausted."
    ),
    "server_error": (
        "ChatGPT could not complete this request because of a service error. "
        "Keep this connection and try again later."
    ),
}


def chatgpt_failure(
    error: object, *, http_status: int | None = None
) -> ProviderFailure:
    """Classify documented codes without trusting messages or guessing quota.

    Responses error events carry a top-level code; failed responses and HTTP
    errors carry an error object. Unknown codes and upstream text stay private.
    Only an actual HTTP status supplied by the transport is retained as such.
    """
    fields = error if isinstance(error, dict) else {}
    if isinstance(fields.get("error"), dict):
        fields = fields["error"]
    code = fields.get("code")
    code = code if isinstance(code, str) and code in _CHATGPT_ERRORS else ""
    status = (
        http_status if type(http_status) is int and 400 <= http_status <= 599 else None
    )
    message = _CHATGPT_ERRORS.get(
        code,
        {
            401: (
                "ChatGPT did not accept the sign-in or plan permission. Check the "
                "selected account and granted permissions."
            ),
            403: (
                "The selected ChatGPT account or workspace does not permit this "
                "request. Check its permissions and policy before trying again."
            ),
            429: (
                "ChatGPT reported a request limit. Check ChatGPT Settings → Usage "
                "before trying again; the affected limit and reset time are not "
                "known."
            ),
            500: (
                "ChatGPT could not complete this request. Keep this connection and "
                "try again later."
            ),
            502: (
                "ChatGPT is temporarily unavailable. Keep this connection and "
                "try again later."
            ),
            503: (
                "ChatGPT routing or capacity is unavailable. Keep this connection "
                "and try again later."
            ),
            504: (
                "ChatGPT took too long to respond. Keep this connection and "
                "try again later."
            ),
        }.get(
            status,
            "ChatGPT could not complete this request. Check the connection "
            "before trying again.",
        ),
    )
    diagnostics = [f"Provider code: {code}."] if code else []
    if status is not None:
        diagnostics.append(f"Upstream HTTP status: {status}.")
    return ProviderFailure(" ".join([message, *diagnostics]), code, status)


@dataclass(frozen=True)
class ProviderReply:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    model: str = ""


def _tokens(usage: dict, key: str) -> int:
    value = usage.get(key, 0)
    if type(value) is not int or value < 0:
        raise ProviderProtocolError("The API returned invalid token usage.")
    return value


def _usage(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProviderProtocolError("The API returned invalid token usage.")
    return value


def _finish_reason(value: object, *, anthropic: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProviderProtocolError("The API returned an invalid completion reason.")
    if anthropic:
        return {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
        }.get(value, value)
    return value


def require_model(actual: object, requested: str, base_url: str) -> str:
    """Accept exact IDs and documented dated aliases at the official vendors.

    An arbitrary compatible service must return the exact requested identity.
    A stream must additionally keep the same resolved ID throughout.
    """
    if not isinstance(actual, str) or not actual or len(actual) > 200:
        raise ProviderIdentityError(
            "The response model did not match the requested model. "
            "The output was rejected; no request was replayed."
        )
    if actual == requested:
        return actual
    base = urlsplit(base_url)
    allowed = False
    if (
        base.scheme == "https"
        and base.port in {None, 443}
        and base.path.rstrip("/") == "/v1"
    ):
        if base.hostname == "api.openai.com":
            allowed = bool(
                re.fullmatch(re.escape(requested) + r"-\d{4}-\d{2}-\d{2}", actual)
            )
        elif base.hostname == "api.anthropic.com":
            alias = requested.removesuffix("-latest")
            allowed = bool(re.fullmatch(re.escape(alias) + r"-\d{8}", actual))
    if not allowed:
        raise ProviderIdentityError(
            "The response model did not match the requested model. "
            "The output was rejected; no request was replayed."
        )
    return actual


@dataclass(frozen=True)
class ProviderTransport:
    identifier: str
    chat_path: str

    def headers(self, key: str, base_url: str = "") -> dict[str, str]:
        if self.identifier == ANTHROPIC:
            headers = {"anthropic-version": "2023-06-01"}
            if key:
                headers["x-api-key"] = key
            return headers
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        base = urlsplit(base_url)
        if (
            self.identifier == OPENAI_COMPATIBLE
            and base.scheme == "https"
            and base.hostname == "generativelanguage.googleapis.com"
            and base.port in {None, 443}
            and base.path.rstrip("/") == "/v1beta/openai"
        ):
            headers["x-goog-api-client"] = f"sinter/{__version__}"
        return headers

    def request_body(self, body: dict, base_url: str) -> dict:
        output = dict(body)
        if self.identifier == CHATGPT:
            if not _official_openai(base_url):
                raise ValueError(
                    "ChatGPT account connections require the official OpenAI API."
                )
            return {
                "model": body["model"],
                "input": [
                    {**message, "role": "developer"}
                    if message["role"] == "system"
                    else dict(message)
                    for message in body["messages"]
                ],
                "store": False,
                "stream": True,
            }
        if self.identifier == ANTHROPIC:
            messages = [dict(message) for message in body["messages"]]
            if messages and messages[0]["role"] == "system":
                output["system"] = messages.pop(0)["content"]
            if any(message["role"] == "system" for message in messages):
                raise ValueError(
                    "Claude accepts system instructions only first. "
                    "Move them to the start before sending."
                )
            if not messages or messages[-1]["role"] != "user":
                raise ValueError("End the Claude conversation with your question.")
            output["messages"] = messages
        elif _official_openai(base_url):
            # Current OpenAI reasoning models reject legacy max_tokens.
            output["max_completion_tokens"] = output.pop("max_tokens")
            if re.match(r"^(?:o[1-9](?:-|$)|gpt-[5-9](?:[.-]|$))", body["model"]):
                output["messages"] = [
                    {**message, "role": "developer"}
                    if message["role"] == "system"
                    else dict(message)
                    for message in body["messages"]
                ]
        return output

    def parse_reply(self, value: dict, model: str, base_url: str) -> ProviderReply:
        actual = require_model(value.get("model"), model, base_url)
        usage = _usage(value.get("usage"))
        if self.identifier == ANTHROPIC:
            if not value.get("stop_reason"):
                raise ProviderProtocolError("The API returned no completion reason.")
            blocks = value.get("content")
            if not isinstance(blocks, list):
                raise ProviderProtocolError(
                    "The API returned an invalid chat response."
                )
            parts = []
            for block in blocks:
                if (
                    not isinstance(block, dict)
                    or block.get("type") != "text"
                    or not isinstance(block.get("text"), str)
                ):
                    raise ProviderProtocolError(
                        "The model returned unsupported content. "
                        "Sinter currently accepts text answers."
                    )
                parts.append(block["text"])
            prompt, completion = (
                _tokens(usage, "input_tokens"),
                _tokens(usage, "output_tokens"),
            )
            return ProviderReply(
                "".join(parts),
                prompt,
                completion,
                prompt + completion,
                _finish_reason(value.get("stop_reason"), anthropic=True),
                actual,
            )
        try:
            if not isinstance(value.get("choices"), list) or len(value["choices"]) != 1:
                raise TypeError
            choice = value["choices"][0]
            if not isinstance(choice, dict):
                raise TypeError
            if choice.get("index", 0) != 0:
                raise TypeError
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            return ProviderReply(
                content,
                _tokens(usage, "prompt_tokens"),
                _tokens(usage, "completion_tokens"),
                _tokens(usage, "total_tokens"),
                _finish_reason(choice.get("finish_reason", "")),
                actual,
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderProtocolError(
                "The API returned an invalid chat response."
            ) from exc

    def stream_decoder(self, model: str, base_url: str) -> ProviderStream:
        return ProviderStream(self, model, base_url)


def _official_openai(base_url: str) -> bool:
    base = urlsplit(base_url)
    return (
        base.scheme == "https"
        and base.hostname == "api.openai.com"
        and base.port in {None, 443}
        and base.path.rstrip("/") == "/v1"
    )


TRANSPORTS = {
    OPENAI_COMPATIBLE: ProviderTransport(OPENAI_COMPATIBLE, "/chat/completions"),
    ANTHROPIC: ProviderTransport(ANTHROPIC, "/messages"),
    CHATGPT: ProviderTransport(CHATGPT, "/responses"),
}


def transport_for(identifier: str = OPENAI_COMPATIBLE) -> ProviderTransport:
    try:
        return TRANSPORTS[identifier]
    except (KeyError, TypeError) as exc:
        raise ValueError("Choose a supported model provider in Settings.") from exc


@dataclass
class ProviderStream:
    """Incremental text decoder; SSE byte and time bounds are enforced upstream."""

    transport: ProviderTransport
    requested_model: str
    base_url: str
    actual_model: str = ""
    parts: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""
    started: bool = False
    finished: bool = False
    active_blocks: set[int] = field(default_factory=set)
    error_message: str = ""
    error_code: str = ""
    error_status: int | None = None
    text_segments: dict[tuple[int, int], list[str]] = field(default_factory=dict)
    final_segments: dict[tuple[int, int], str] = field(default_factory=dict)
    unindexed_text: bool = False

    def _identity(self, actual: object) -> None:
        resolved = require_model(actual, self.requested_model, self.base_url)
        if self.actual_model and resolved != self.actual_model:
            raise ProviderIdentityError(
                "The response model changed during generation. "
                "The partial answer is not complete."
            )
        self.actual_model = resolved

    def feed(self, chunk: dict) -> tuple[str, bool]:
        if not isinstance(chunk, dict):
            raise ProviderProtocolError("The API reported an error during generation.")
        if self.finished:
            raise ProviderProtocolError(
                "The API sent output after completing its answer."
            )
        if self.transport.identifier == CHATGPT:
            content, done = self._responses(chunk)
        elif self.transport.identifier == ANTHROPIC:
            if "error" in chunk:
                raise ProviderProtocolError(
                    "The API reported an error during generation."
                )
            content, done = self._anthropic(chunk)
        else:
            if "error" in chunk:
                raise ProviderProtocolError(
                    "The API reported an error during generation."
                )
            self._identity(chunk.get("model"))
            self.started = True
            if chunk.get("usage") is not None:
                self.usage = _usage(chunk["usage"])
            choices = chunk.get("choices", [])
            if not isinstance(choices, list) or len(choices) > 1:
                raise ProviderProtocolError("The API returned a malformed stream.")
            content, done = "", False
            if choices:
                choice = choices[0]
                if not isinstance(choice, dict) or not isinstance(
                    choice.get("delta", {}), dict
                ):
                    raise ProviderProtocolError("The API returned a malformed stream.")
                if choice.get("index", 0) != 0:
                    raise ProviderProtocolError("The API returned a malformed stream.")
                reason = _finish_reason(choice.get("finish_reason"))
                self.finish_reason = reason or self.finish_reason
                content = choice.get("delta", {}).get("content")
                content = "" if content is None else content
                if not isinstance(content, str):
                    raise ProviderProtocolError("The API returned a malformed stream.")
        if content:
            self.parts.append(content)
        self.finished = done
        return content, done

    def _responses(self, chunk: dict) -> tuple[str, bool]:
        kind = chunk.get("type")
        if kind == "error" or "error" in chunk:
            failure = chatgpt_failure(chunk)
            self.finish_reason = "error"
            self.error_message, self.error_code = failure.message, failure.code
            return "", True
        if kind in {"response.created", "response.in_progress"}:
            response = chunk.get("response")
            if not isinstance(response, dict):
                raise ProviderProtocolError("The API returned a malformed stream.")
            self._identity(response.get("model"))
            self.started = True
            return "", False
        if kind == "response.output_text.delta":
            if not self.started or not isinstance(chunk.get("delta"), str):
                raise ProviderProtocolError("The API returned a malformed stream.")
            self._record_text_segment(chunk, chunk["delta"])
            return chunk["delta"], False
        if kind == "response.refusal.delta":
            if not self.started or not isinstance(chunk.get("delta"), str):
                raise ProviderProtocolError("The API returned a malformed stream.")
            self.finish_reason = "refusal"
            self._record_text_segment(chunk, chunk["delta"])
            return chunk["delta"], False
        if kind not in {"response.completed", "response.incomplete", "response.failed"}:
            # Reasoning and item-lifecycle events carry no user-visible text.
            return "", False
        response = chunk.get("response")
        if not self.started or not isinstance(response, dict):
            raise ProviderProtocolError("The API returned a malformed stream.")
        self._identity(response.get("model"))
        status = kind.removeprefix("response.")
        if response.get("status") != status:
            raise ProviderProtocolError(
                "The API returned an inconsistent completion status."
            )
        self.usage = dict(_usage(response.get("usage")))
        if kind == "response.completed":
            final_text = self._response_output_text(response)
            streamed_text = "".join(self.parts)
            matches = final_text == streamed_text
            if self.text_segments and not self.unindexed_text:
                # Multiple output/content items can stream in interleaved
                # order. Reconcile each indexed segment with the final item,
                # then use the completed response's canonical output order.
                matches = {
                    key: text for key, text in self.final_segments.items() if text
                } == {
                    key: "".join(parts)
                    for key, parts in self.text_segments.items()
                    if any(parts)
                }
            if not matches:
                self.finish_reason = "error"
                raise ProviderCompletionMismatch(
                    "The completed response did not match its streamed text. "
                    "The partial answer is not complete. "
                    f"Stream diagnostics: {len(self.parts)} deltas, "
                    f"{len(self.text_segments)} indexed stream segments / "
                    f"{len(self.final_segments)} final segments; "
                    f"{len(streamed_text)} streamed / {len(final_text)} "
                    "final characters."
                )
            if final_text != streamed_text:
                self.parts = [final_text]
            self.finish_reason = self.finish_reason or "stop"
        elif kind == "response.incomplete":
            details = response.get("incomplete_details") or {}
            self.finish_reason = (
                "length"
                if isinstance(details, dict)
                and details.get("reason") == "max_output_tokens"
                else "incomplete"
            )
            self.error_message = "ChatGPT stopped before completing the answer."
        else:
            self.finish_reason = "error"
            failure = chatgpt_failure(response.get("error"))
            self.error_message, self.error_code = failure.message, failure.code
        return "", True

    def _record_text_segment(self, chunk: dict, text: str) -> None:
        if "output_index" not in chunk and "content_index" not in chunk:
            self.unindexed_text = True
            return
        indexes = chunk.get("output_index"), chunk.get("content_index")
        if any(type(value) is not int or value < 0 for value in indexes):
            raise ProviderProtocolError("The API returned malformed text indexes.")
        self.text_segments.setdefault(indexes, []).append(text)

    def _response_output_text(self, response: dict) -> str:
        output = response.get("output")
        if not isinstance(output, list):
            raise ProviderProtocolError(
                "The API returned a malformed completed response."
            )
        text = []
        for output_index, item in enumerate(output):
            if not isinstance(item, dict):
                raise ProviderProtocolError(
                    "The API returned a malformed completed response."
                )
            if item.get("type") == "reasoning":
                continue
            if item.get("type") != "message" or not isinstance(
                item.get("content"), list
            ):
                raise ProviderProtocolError(
                    "The model returned unsupported content. "
                    "Sinter currently accepts text answers."
                )
            for content_index, part in enumerate(item["content"]):
                if not isinstance(part, dict):
                    raise ProviderProtocolError(
                        "The API returned a malformed completed response."
                    )
                if part.get("type") == "output_text" and isinstance(
                    part.get("text"), str
                ):
                    text.append(part["text"])
                    self.final_segments[output_index, content_index] = part["text"]
                elif part.get("type") == "refusal" and isinstance(
                    part.get("refusal"), str
                ):
                    text.append(part["refusal"])
                    self.final_segments[output_index, content_index] = part["refusal"]
                    self.finish_reason = "refusal"
                else:
                    raise ProviderProtocolError(
                        "The model returned unsupported content. "
                        "Sinter currently accepts text answers."
                    )
        return "".join(text)

    def _anthropic(self, chunk: dict) -> tuple[str, bool]:
        kind = chunk.get("type")
        if kind == "error":
            raise ProviderProtocolError("The API reported an error during generation.")
        if kind == "ping":
            return "", False
        if kind == "message_start":
            if self.started or not isinstance(chunk.get("message"), dict):
                raise ProviderProtocolError("The API returned a malformed stream.")
            message = chunk["message"]
            self._identity(message.get("model"))
            if message.get("content", []) != []:
                raise ProviderProtocolError("The API returned a malformed stream.")
            self.usage = dict(_usage(message.get("usage")))
            self.started = True
            return "", False
        known = {
            "content_block_start",
            "content_block_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
        }
        if kind not in known:
            # Anthropic adds event types compatibly; never expose unknown data.
            return "", False
        if not self.started:
            raise ProviderProtocolError("The API returned a malformed stream.")
        if kind.startswith("content_block_"):
            index = chunk.get("index")
            if type(index) is not int or index < 0:
                raise ProviderProtocolError("The API returned a malformed stream.")
            if kind == "content_block_start":
                block = chunk.get("content_block")
                if index in self.active_blocks or not isinstance(block, dict):
                    raise ProviderProtocolError("The API returned a malformed stream.")
                if block.get("type") != "text" or not isinstance(
                    block.get("text"), str
                ):
                    raise ProviderProtocolError(
                        "The model returned unsupported content. "
                        "Sinter currently accepts text answers."
                    )
                self.active_blocks.add(index)
                return block["text"], False
            if index not in self.active_blocks:
                raise ProviderProtocolError("The API returned a malformed stream.")
            if kind == "content_block_stop":
                self.active_blocks.remove(index)
                return "", False
            delta = chunk.get("delta")
            if (
                not isinstance(delta, dict)
                or delta.get("type") != "text_delta"
                or not isinstance(delta.get("text"), str)
            ):
                raise ProviderProtocolError("The API returned a malformed stream.")
            return delta["text"], False
        if kind == "message_delta":
            delta = chunk.get("delta")
            if not isinstance(delta, dict):
                raise ProviderProtocolError("The API returned a malformed stream.")
            reason = _finish_reason(delta.get("stop_reason"), anthropic=True)
            self.finish_reason = reason or self.finish_reason
            self.usage.update(_usage(chunk.get("usage")))
            return "", False
        if self.active_blocks or not self.finish_reason:
            raise ProviderProtocolError(
                "The response ended early. The partial answer is not complete."
            )
        return "", True

    def result(self) -> ProviderReply:
        if not self.started:
            raise ProviderProtocolError(
                "The response ended early. The partial answer is not complete."
            )
        if self.transport.identifier in {ANTHROPIC, CHATGPT}:
            prompt, completion = (
                _tokens(self.usage, "input_tokens"),
                _tokens(self.usage, "output_tokens"),
            )
            total = prompt + completion
        else:
            prompt = _tokens(self.usage, "prompt_tokens")
            completion = _tokens(self.usage, "completion_tokens")
            total = _tokens(self.usage, "total_tokens")
        return ProviderReply(
            "".join(self.parts),
            prompt,
            completion,
            total,
            self.finish_reason,
            self.actual_model,
        )
