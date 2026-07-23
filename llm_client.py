"""
llm_client.py — Lilly gateway LLM dispatcher.

Two dispatcher builders, not one:
  - make_lilly_classifier_dispatcher(): screen.py. Cheap, fast, bounded
    JSON-array output. Thinking OFF — a 20-record batch decision doesn't
    benefit from reasoning, and disabling it removes any risk of thinking
    eating the (small) max_tokens budget. Non-streaming — well under any
    duration threshold at these token counts.
  - make_lilly_analytical_dispatcher(): eligibility.py / evidence.py /
    synthesize.py. Adaptive thinking ON at high effort, max_tokens pinned
    to the model ceiling (128k). STREAMS internally, then reassembles the
    full response before returning — see "Why streaming" below.

Both still return the same LLMDispatcher shape (Callable[[str, str], str])
screen.py/eligibility.py/evidence.py already expect, so nothing downstream
changes — only which builder a node is wired to, and the analytical one's
internal transport.

Why streaming (fixes a live crash)
--------------------------------------
At max_tokens=128000 with adaptive thinking on high effort, the Anthropic
SDK refuses to run a plain non-streaming `messages.create()` call —
it raises `ValueError: Streaming is required for operations that may
take longer than 10 minutes` before the request is even sent. This isn't
a Lilly-gateway quirk, it's the SDK's own guard against a client-side
timeout on a call that's genuinely likely to run long at this max_tokens/
effort combination — exactly the eligibility/evidence nodes.

The fix is NOT to lower max_tokens or effort (that's the "don't limit
reasoning" tradeoff we explicitly don't want to make) — it's to use the
SDK's streaming interface and reassemble the full message from the
stream, via `client.messages.stream(...)` as a context manager and
`.get_final_message()`. The returned Message object has the identical
shape `_response_text()` already expects (content blocks, stop_reason,
usage), so nothing downstream of `_dispatch()` needs to change — this is
purely a transport-layer fix, invisible to every caller.

The classifier dispatcher does NOT need this — 8k max_tokens with
thinking disabled is nowhere near the SDK's duration threshold, so it
stays on the simpler non-streaming `.create()` call.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Callable, Literal

import anthropic
import httpx


log = logging.getLogger(__name__)

GATEWAY_BASE_URL = "https://lilly-code-server.api.gateway.llm.lilly.com"

# Confirm both of these are actually exposed on the Lilly gateway before
# relying on them — a Lilly-managed proxy can lag the public API's model
# list. If claude-sonnet-5 / claude-opus-4-8 aren't available yet, that's
# worth getting enabled rather than silently falling back to 4.6.
DEFAULT_CLASSIFIER_MODEL = "claude-sonnet-5"   # screen.py
DEFAULT_ANALYTICAL_MODEL = "claude-opus-4-8"   # eligibility.py / evidence.py / synthesize.py

MAX_OUTPUT_TOKENS = 128_000  # synchronous ceiling on both models above
EffortLevel = Literal["low", "medium", "high", "max"]

_client: anthropic.Anthropic | None = None  # lazily initialised, unchanged from before


def _get_gateway_token() -> str:
    """Fetch a fresh Lilly gateway bearer token via the lilly-code CLI. Unchanged."""
    try:
        return subprocess.check_output(["lilly-code", "token"], text=True).strip()
    except Exception as e:
        raise RuntimeError(
            "Unable to get Lilly gateway token. "
            "Run `lilly-code login` and verify with `lilly-code status`."
        ) from e


def _get_client() -> anthropic.Anthropic:
    """Lazily create (and cache) the Anthropic client. Bearer auth via
    auth_token=, not api_key= — unchanged.

    timeout= is new: a live run hit httpx.ReadTimeout mid-stream on
    evidence.py's analytical call (respiratory_function, 15-record corpus
    — small, so this wasn't corpus size overwhelming the call). Streaming
    fixed the SDK's own 10-minute non-streaming guard, but a stream can
    still fail if no chunk arrives within the CLIENT's read-timeout
    window — the default is too short for a call where adaptive thinking
    may go a while between emitted chunks, especially through the
    Zscaler-fronted gateway path adding its own latency. connect/write/pool
    stay short (a hung TCP handshake or slow write should still fail
    fast); read is set long, since that's specifically what timed out.
    """
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            auth_token=_get_gateway_token(),
            base_url=GATEWAY_BASE_URL,
            timeout=httpx.Timeout(600.0, connect=10.0, write=30.0, read=600.0),
        )
    return _client


def _response_text(response) -> str:
    """Concatenate all text blocks; raise with diagnostic detail if none
    exist. Unchanged from before — this is still the right guard, and
    still applies identically whether `response` came from a plain
    `.create()` call or `.stream().get_final_message()` — both return the
    same Message shape."""
    block_types = [getattr(b, "type", "unknown") for b in response.content]
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()

    if not text:
        raise RuntimeError(
            f"_response_text: model returned no usable text content. "
            f"stop_reason={getattr(response, 'stop_reason', '?')!r}, "
            f"content block types={block_types!r}, "
            f"usage={getattr(response, 'usage', '?')!r}."
        )

    log.debug("_response_text: %d chars, block types=%r, stop_reason=%r",
               len(text), block_types, getattr(response, "stop_reason", "?"))
    return text


def make_lilly_classifier_dispatcher(
    model: str = DEFAULT_CLASSIFIER_MODEL,
    max_tokens: int = 8_000,
) -> Callable[[str, str], str]:
    """Screen.py's dispatcher. Thinking explicitly disabled — on Sonnet 5,
    a request with no `thinking` field runs WITH adaptive thinking by
    default (that's new vs. 4.6), so this disable is now load-bearing,
    not a no-op. 8k is comfortable headroom for a 20-record JSON array;
    raise it if you widen batch_size. Non-streaming: well under the SDK's
    duration threshold at these settings."""
    def _dispatch(system: str, user: str) -> str:
        client = _get_client()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "disabled"},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _response_text(response)
    return _dispatch


def make_lilly_analytical_dispatcher(
    model: str = DEFAULT_ANALYTICAL_MODEL,
    max_tokens: int = MAX_OUTPUT_TOKENS,
    effort: EffortLevel = "high",
    *,
    thinking: bool = True,
    stream: bool | None = None,
) -> Callable[[str, str], str]:
    """eligibility.py / evidence.py / synthesize.py's dispatcher. Adaptive
    thinking ON by default, effort steers how hard it pushes (soft guidance —
    the model can still skip thinking on a trivial call), max_tokens is the
    hard ceiling on thinking + response combined. At high/max effort the
    model can genuinely approach max_tokens, which is why the default is
    pinned to the model's synchronous ceiling (128k).

    `effort` is a top-level `output_config` field, NOT nested inside
    `thinking` — that placement matters, nesting it under `thinking`
    raises a validation error.

    thinking / stream toggles (NEW — the eligibility speed fix)
    -----------------------------------------------------------
    eligibility.py is, per evidence.py's own docstring, a bounded per-record
    include/exclude CLASSIFIER over fuller text — structurally the same
    shape as screen.py's task, NOT the open-ended cross-record reasoning
    evidence.py does. Running it with adaptive thinking on Opus spent
    wall-clock on deliberation the task doesn't need; at 20+ batches per COI
    that was a dominant cost in the >1hr run.

    Passing thinking=False keeps the STRONGER model (Opus) for the judgment
    call — honoring the prior decision to upgrade eligibility off the cheap
    classifier — while removing the thinking tax entirely. With thinking off
    and a modest max_tokens, the call is well under the SDK's 10-minute
    streaming guard, so it also drops back to a plain non-streaming
    .create() (faster to first/last token, less overhead). Two ways to use
    it for eligibility, in increasing order of speed:
        make_lilly_analytical_dispatcher(thinking=False, max_tokens=16000)  # Opus, no thinking
        make_lilly_classifier_dispatcher()                                  # Sonnet 5, no thinking (cheapest)

    evidence.py keeps the default (thinking=True, effort="high", streamed) —
    whole-corpus tiering genuinely benefits from it.

    `stream` overrides transport when you need to: None = auto (stream iff
    thinking is on OR max_tokens is large enough to risk the SDK guard).

    Retries on transient network errors (httpx.ReadTimeout/ConnectError,
    anthropic.APIConnectionError) on BOTH transports — a dropped connection
    through the gateway/Zscaler path doesn't mean the request was bad. If it
    still fails after retries it raises, so this papers over a blip, not a
    persistent failure.
    """
    _RETRYABLE = (httpx.ReadTimeout, httpx.ConnectError, anthropic.APIConnectionError)

    # Auto transport: the SDK forces streaming only for long-running calls
    # (high max_tokens + thinking). A thinking-off, modest-token call is safe
    # non-streaming, which is both simpler and a touch faster.
    _STREAM_GUARD = 32_000
    use_stream = stream if stream is not None else (thinking or max_tokens > _STREAM_GUARD)

    # Build the request kwargs once. When thinking is disabled we drop
    # output_config entirely — effort is meaningful only alongside thinking,
    # and passing it without thinking risks a validation error on the gateway.
    def _kwargs(system: str, user: str) -> dict:
        kw: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if thinking:
            kw["thinking"] = {"type": "adaptive"}
            kw["output_config"] = {"effort": effort}
        else:
            kw["thinking"] = {"type": "disabled"}
        return kw

    def _dispatch(system: str, user: str) -> str:
        client = _get_client()
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                kw = _kwargs(system, user)
                if use_stream:
                    with client.messages.stream(**kw) as s:
                        response = s.get_final_message()
                else:
                    response = client.messages.create(**kw)
                return _response_text(response)
            except _RETRYABLE as e:
                last_err = e
                wait = 5.0 * (attempt + 1)
                log.warning(
                    "make_lilly_analytical_dispatcher: %s on attempt %d/3, "
                    "retrying in %.0fs", type(e).__name__, attempt + 1, wait,
                )
                if attempt < 2:
                    time.sleep(wait)
        raise last_err  # exhausted retries — surface the real error, not a generic one
    return _dispatch


__all__ = [
    "make_lilly_classifier_dispatcher",
    "make_lilly_analytical_dispatcher",
    "DEFAULT_CLASSIFIER_MODEL",
    "DEFAULT_ANALYTICAL_MODEL",
    "MAX_OUTPUT_TOKENS",
    "GATEWAY_BASE_URL",
]