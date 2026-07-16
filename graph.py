"""
graph.py — LangGraph wiring for the DHT landscape pipeline (Architecture C).

Current scope (be honest about what's real)
---------------------------------------------
This graph wires exactly what's built: router → identify → screen →
eligibility → END, for ONE COI, in "coi_first" direction only.

NOT yet implemented, and deliberately made to fail loudly rather than
silently misbehave:
  - measure_first / device_first / company_first directions (routed to an
    `unsupported_direction` node that raises with a pointer to the design —
    see dht-landscape-scout SKILL.md's Open Questions ledger item 3)
  - multi-COI fan-out (the router node raises if `cois` isn't length 1;
    parallel fan-out via Send(), mirroring evidence_fanout.py, is the
    documented next step, not a silent limitation)
  - evidence / device / gap / corpus_stats / verify / synthesize / build_docx
    nodes — these come after this file, once the skill-driven nodes and the
    docx builder exist. This graph currently ends at a real, enriched,
    PRISMA-counted corpus, which is the Week-2 milestone.

Dependency injection pattern
-----------------------------
Every node that needs an MCP or LLM call is built by a factory function
(`make_identify_node(mcp)`, etc.) that closes over the dispatcher and
returns a plain `(state) -> partial_update` function. This is the same
shim pattern as retrieval.py/screen.py/eligibility.py's `MCPDispatcher`/
`LLMDispatcher` types — it's what makes every node testable by calling it
directly with a fake, with no live Lilly gateway or MCP connection required,
and it's what `build_graph()` uses to wire in the real clients at runtime.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from langgraph.graph import StateGraph, START, END

from state import DHTState, dict_override_or_merge  # noqa: F401 (dict_override_or_merge documented for graph builders who need it explicitly)
from criteria import get as get_criteria
from retrieval import identify as run_identify, MCPDispatcher
from screen import screen as run_screen, LLMDispatcher as ScreenLLM
from eligibility import eligibility as run_eligibility, LLMDispatcher as EligLLM
from evidence import run_evidence, LLMDispatcher as EvidenceLLM, DEFAULT_SKILL_PATH


log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Search-plan construction — PLACEHOLDER
# ─────────────────────────────────────────────────────────────────────────────
# This is deliberately minimal: it just ORs together the positive_signals
# keyword hints already in criteria.py into a ClinicalTrials.gov + PubMed
# query. It does NOT do the sub-construct vocabulary elicitation the
# landscape-scout skill's "Retrieval Requirements" section calls for
# (mapping "Range of Motion" -> "reachable workspace", "head drop", etc. for
# ALS specifically). That elicitation needs a Python-fetch + model-judge
# round trip (pull outcome-measure text from completed trials, have the
# model decide which are genuinely new sub-constructs) — see Open Questions
# ledger item 2 for why that control flow isn't designed yet.
#
# This placeholder is good enough to produce a real corpus for a COI where
# the label IS close to the literature's vocabulary — which MVPA is. It is
# NOT good enough for a genuinely novel COI where the label and the
# literature's terms diverge. Replace before running this on one of those.

def default_search_plan(coi: str, indication: str) -> dict:
    """Minimal query-plan builder from criteria.py's positive_signals."""
    criteria = get_criteria(coi)
    signal_terms = criteria.positive_signals[:8]  # cap — don't let this balloon
    outcome_query = " OR ".join(f'"{t}"' if " " in t else t for t in signal_terms)

    return {
        "clinicaltrials": [
            {"query.cond": indication, "query.outc": outcome_query},
        ],
        "pubmed": [
            {"query": f"{indication} AND ({outcome_query})"},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node factories
# ─────────────────────────────────────────────────────────────────────────────

def make_router_node() -> Callable[[DHTState], dict]:
    """Resolves direction and builds the search plan.

    Hard requirements enforced here (raise, don't silently misbehave):
      - exactly one COI (multi-COI fan-out not built yet)
      - `indication` present

    Direction is NOT validated here — that's the conditional edge's job
    (route_by_direction below), so there's a single source of truth for
    "which directions are actually wired" rather than two.
    """
    def _node(state: DHTState) -> dict:
        cois = state.get("cois") or []
        if len(cois) != 1:
            raise NotImplementedError(
                f"router: this graph supports exactly one COI per run; got "
                f"{cois!r}. Multi-COI parallel fan-out (Send()-based, "
                f"mirroring evidence_fanout.py) is a flagged next step."
            )
        indication = state.get("indication")
        if not indication:
            raise ValueError("router: state['indication'] is required")

        coi = cois[0]
        direction = state.get("direction", "coi_first")
        plan = default_search_plan(coi, indication)

        log.info("router: coi=%s indication=%s direction=%s", coi, indication, direction)
        return {
            "direction": direction,
            "search_plan": plan,
        }
    return _node


def route_by_direction(state: DHTState) -> str:
    """Conditional edge: the single source of truth for which directions
    are actually wired. Only 'coi_first' proceeds; everything else routes
    to a node that raises clearly rather than running the wrong logic."""
    direction = state.get("direction", "coi_first")
    if direction == "coi_first":
        return "identify"
    return "unsupported_direction"


def unsupported_direction_node(state: DHTState) -> dict:
    direction = state.get("direction")
    raise NotImplementedError(
        f"direction={direction!r} is not implemented. Only 'coi_first' is "
        f"wired end-to-end today. measure_first/device_first/company_first "
        f"are DESIGNED (see dht-landscape-scout SKILL.md's Core Abstraction "
        f"section) but not built — see Open Questions ledger item 3."
    )


def make_identify_node(mcp: MCPDispatcher) -> Callable[[DHTState], dict]:
    def _node(state: DHTState) -> dict:
        records, prisma = run_identify(state["search_plan"], mcp)
        log.info("identify: %d records after dedup", len(records))
        return {
            "raw_records": {"type": "override", "value": records},
            "prisma_counts": prisma,
        }
    return _node


def make_screen_node(llm: ScreenLLM) -> Callable[[DHTState], dict]:
    def _node(state: DHTState) -> dict:
        coi = state["cois"][0]
        included, report = run_screen(state["raw_records"], coi, llm)
        log.info(
            "screen: %d in -> %d included, %d excluded",
            report["screened"], len(included), report["screened_excluded"],
        )
        return {
            "screened_records": {"type": "override", "value": included},
            "prisma_counts": {
                "screened": report["screened"],
                "screened_excluded": report["screened_excluded"],
                "screen_excluded_reasons": report["screen_excluded_reasons"],
            },
        }
    return _node


def make_eligibility_node(mcp: MCPDispatcher, llm: EligLLM) -> Callable[[DHTState], dict]:
    def _node(state: DHTState) -> dict:
        coi = state["cois"][0]
        corpus, citations_index, report = run_eligibility(
            state["screened_records"], coi, mcp, llm
        )
        log.info(
            "eligibility: %d in -> %d included (corpus frozen, %d citation_ids)",
            report["eligible"], report["included"], len(citations_index),
        )
        return {
            "corpus": {"type": "override", "value": corpus},
            "citations_index": {"type": "override", "value": citations_index},
            "prisma_counts": {
                "eligible": report["eligible"],
                "eligible_excluded": report["eligible_excluded"],
                "eligible_excluded_reasons": report["eligible_excluded_reasons"],
                "included": report["included"],
                "reversals_from_screen": report["reversals_from_screen"],
            },
        }
    return _node


def make_evidence_node(
    llm: EvidenceLLM,
    skill_path: Path = DEFAULT_SKILL_PATH,
) -> Callable[[DHTState], dict]:
    """First analytical node — loads dht-landscape-scout SKILL.md as the
    system prompt and scores the frozen corpus. See evidence.py for why
    this is a fundamentally different kind of node than everything before
    it (single whole-corpus call, Sonnet-tier model, not a per-record
    classifier)."""
    def _node(state: DHTState) -> dict:
        coi = state["cois"][0]
        device_rows, gaps, coi_evidence, report = run_evidence(
            corpus=state["corpus"],
            citations_index=state["citations_index"],
            coi=coi,
            indication=state["indication"],
            llm=llm,
            skill_path=skill_path,
        )
        if report.get("parse_error"):
            log.error("evidence: parse failed, devices/gaps/evidence will be empty this run: %s",
                       report["parse_error"])
        update: dict = {
            "devices": {"type": "override", "value": device_rows},
            "gaps": gaps,
        }
        if coi_evidence is not None:
            update["evidence"] = {"type": "override", "value": [coi_evidence]}
        return update
    return _node


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(
    mcp: MCPDispatcher,
    screen_llm: ScreenLLM,
    eligibility_llm: EligLLM,
    evidence_llm: EvidenceLLM | None = None,
    evidence_skill_path: Path = DEFAULT_SKILL_PATH,
    checkpointer=None,
):
    """Compile the identify→screen→eligibility→evidence graph.

    Args:
        mcp: dispatcher used by both identify and eligibility.
        screen_llm: cheap-model dispatcher for the screen node.
        eligibility_llm: cheap-model dispatcher for the eligibility node.
        evidence_llm: Sonnet-tier dispatcher for the evidence node. If None,
             the evidence node is SKIPPED and the graph ends after
             eligibility — useful for a retrieval-only dry run, or if you
             don't have the skill file staged yet.
        evidence_skill_path: path to dht-landscape-scout's SKILL.md. Must
             exist if evidence_llm is provided — see evidence.py's
             load_skill_prompt, which raises clearly if it's missing rather
             than silently running without the analytical framework.
        checkpointer: optional LangGraph checkpointer for resumable runs.

    Returns the compiled graph (call `.invoke(initial_state)` on it).
    """
    builder = StateGraph(DHTState)

    builder.add_node("router", make_router_node())
    builder.add_node("identify", make_identify_node(mcp))
    builder.add_node("screen", make_screen_node(screen_llm))
    builder.add_node("eligibility", make_eligibility_node(mcp, eligibility_llm))
    builder.add_node("unsupported_direction", unsupported_direction_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        route_by_direction,
        {"identify": "identify", "unsupported_direction": "unsupported_direction"},
    )
    builder.add_edge("identify", "screen")
    builder.add_edge("screen", "eligibility")
    builder.add_edge("unsupported_direction", END)

    if evidence_llm is not None:
        builder.add_node("evidence", make_evidence_node(evidence_llm, evidence_skill_path))
        builder.add_edge("eligibility", "evidence")
        builder.add_edge("evidence", END)
    else:
        log.info("build_graph: evidence_llm not provided — graph ends after eligibility")
        builder.add_edge("eligibility", END)

    return builder.compile(checkpointer=checkpointer)


__all__ = [
    "build_graph",
    "default_search_plan",
    "make_router_node",
    "make_identify_node",
    "make_screen_node",
    "make_eligibility_node",
    "route_by_direction",
    "unsupported_direction_node",
]