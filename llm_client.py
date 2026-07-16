"""
llm_client.py — Lilly gateway LLM dispatcher.

This is your existing base_node.py auth pattern verbatim (auth_token=,
GATEWAY_BASE_URL, lazy client via `lilly-code token`) — that part already
worked and isn't touched. The only change is the OUTPUT SHAPE: base_node.py's
`run_node()` returned a parsed dict (it did its own JSON-fence-stripping and
json.loads). screen.py and eligibility.py want raw text back — they already
do their own fence-stripping and fault-tolerant JSON parsing (see
_strip_fences / _parse_decisions in both files), so double-parsing here
would be redundant and would hide parse failures one layer too early.

So: `make_lilly_llm_dispatcher()` returns a plain
`Callable[[str, str], str]` — exactly the `LLMDispatcher` type screen.py
and eligibility.py already expect — that internally does the same
_get_client / _response_text dance as base_node.py, just stops one step
earlier (no JSON parsing, no fence stripping — that's the caller's job).
"""
from __future__ import annotations

import importlib
import subprocess
from typing import Any, Callable
import anthropic


GATEWAY_BASE_URL = "https://lilly-code-server.api.gateway.llm.lilly.com"

# Cheap/fast model for screen + eligibility (high call volume, classifier-
# shaped task). Sonnet 4.6 is reserved for the evidence/device/synthesize
# nodes downstream, which do the actual analytical work — see the model-tier
# table from the eligibility.py conversation.
DEFAULT_SCREEN_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_SYNTHESIS_MODEL = "claude-sonnet-4-6"

_client: anthropic.Anthropic | None = None  # lazily initialised, same as base_node.py


def _get_gateway_token() -> str:
    """Fetch a fresh Lilly gateway bearer token via the lilly-code CLI.

    Verbatim from base_node.py — this already worked, not touched.
    """
    try:
        return subprocess.check_output(["lilly-code", "token"], text=True).strip()
    except Exception as e:
        raise RuntimeError(
            "Unable to get Lilly gateway token. "
            "Run `lilly-code login` and verify with `lilly-code status`."
        ) from e


def _get_client() -> anthropic.Anthropic:
    """Lazily create (and cache) the Anthropic client.

    Verbatim from base_node.py: auth_token= (Bearer), not api_key= (x-api-key)
    — the gateway expects bearer auth, and this was the fix that made auth
    actually work in the earlier build. Not touched.
    """
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            auth_token=_get_gateway_token(),
            base_url=GATEWAY_BASE_URL,
        )
    return _client


def _response_text(response) -> str:
    """Concatenate all text blocks from a Messages API response.

    Verbatim from base_node.py.
    """
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


def make_lilly_llm_dispatcher(
    model: str = DEFAULT_SCREEN_MODEL,
    max_tokens: int = 2000,
) -> Callable[[str, str], str]:
    """Build an LLMDispatcher (Callable[[str, str], str]) bound to a model.

    Pass the result directly as `screen_llm` / `eligibility_llm` to
    graph.build_graph(). Call this twice with different `model` args if you
    want screen and eligibility on different models — same client/auth
    underneath either way (the client is a module-level singleton).

    Example:
        cheap_llm = make_lilly_llm_dispatcher(DEFAULT_SCREEN_MODEL)
        app = build_graph(mcp=real_mcp_dispatcher, screen_llm=cheap_llm,
                           eligibility_llm=cheap_llm)
    """
    def _dispatch(system: str, user: str) -> str:
        client = _get_client()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _response_text(response)
    return _dispatch


__all__ = [
    "make_lilly_llm_dispatcher",
    "DEFAULT_SCREEN_MODEL",
    "DEFAULT_SYNTHESIS_MODEL",
    "GATEWAY_BASE_URL",
]