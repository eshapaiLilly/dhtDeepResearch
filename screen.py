"""
screen.py — title/abstract screening node for the DHT pipeline.

What this module does
---------------------
Takes the deduplicated records from `identify()` and, for each COI, asks
Claude to decide include / exclude against the criteria in `criteria.py`.
Returns:
  - The subset of records passing the screen (→ state.screened_records)
  - Exclusion tallies keyed by ExclusionCode (→ prisma_counts.excluded_reasons)

Design decisions
----------------
1. **Two-pass funnel**: this module handles the title/abstract screen only.
   A subsequent `eligibility()` step (in eligibility.py, next file) does the
   full-record assessment. Same as PRISMA: identification → screening →
   eligibility → included.

2. **Batched LLM calls**: screening 500 records one at a time would burn
   50× the tokens for no gain. We batch ~20 records per call and ask Claude
   to return a JSON array. Batch size is tuned for context: with a 3-sentence
   abstract per record, ~20 records fits comfortably under 8k input tokens.

3. **Cheap model, not Sonnet**: title/abstract screening is a pattern-match
   task, not a reasoning task. The screening node uses a cheaper/faster model
   (Haiku-class) — the model ID is a parameter so the graph can swap it. This
   is the ODR "four-model roles" pattern.

4. **Structured output via a strict schema**: we require Claude to emit one
   JSON object per record with fields {citation_id, decision, exclusion_code,
   reason}. Any malformed row is treated as "exclude, insufficient_metadata"
   rather than crashing the batch — screening must never be the pipeline's
   fragile link.

5. **Deterministic re-mapping**: the LLM never sees the full Record. It sees
   an anonymized view (citation_id + title + abstract snippet). This keeps
   the prompt short AND prevents the model from inventing metadata that
   isn't in the retrieved payload.

6. **NO retrieval, NO synthesis here**. Screening is a classifier. It has one
   job.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from criteria import EligibilityCriteria, ExclusionCode, get as get_criteria
from state import Record


log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# LLM dispatch shim (same pattern as retrieval.MCPDispatcher)
# ─────────────────────────────────────────────────────────────────────────────
# The dispatcher takes a system prompt + user message and returns the raw
# text of Claude's reply. The graph node binds this to a real Anthropic client
# call; tests bind a fake.

LLMDispatcher = Callable[[str, str], str]


# ─────────────────────────────────────────────────────────────────────────────
# Screening result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScreenDecision:
    citation_id: str
    include: bool
    exclusion_code: ExclusionCode | None = None
    reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Prompt construction
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a systematic-review screener for a digital-health-technology (DHT)
landscape assessment in a pharmaceutical clinical trial context. You apply
PRISMA-style eligibility criteria to titles and abstracts.

Your only job is to decide, for each record, whether it passes the criteria.
You are NOT synthesizing evidence, NOT making device recommendations, NOT
extracting effect sizes. You are a classifier.

For each record you receive, output one JSON object with these keys:
  - "citation_id": string, exactly as given (do not modify)
  - "include": boolean
  - "exclusion_code": one of the ExclusionCode values, or null if include=true
  - "reason": one short sentence (<= 25 words) grounded in the record text

Rules:
- If ANY exclusion criterion applies, exclude (choose the FIRST matching code).
- If ALL inclusion criteria are satisfied, include.
- If the abstract is missing or too thin to assess, exclude with code
  "insufficient_metadata".
- Do NOT invent metadata not present in the record. If in doubt, exclude.
- Return a JSON ARRAY of decision objects, one per input record, in the same
  order. No prose before or after. No markdown code fences.
"""


def _render_record_for_screen(r: Record) -> dict:
    """Compact view sent to the screener. Abstract is truncated to control tokens."""
    abstract = (r.abstract or "").strip()
    if len(abstract) > 1200:
        abstract = abstract[:1200] + " …[truncated]"
    return {
        "citation_id": r.citation_id,
        "source": r.source,
        "title": r.title,
        "year": r.year,
        "condition": r.condition,
        "intervention": r.intervention,
        "intervention_type": r.intervention_type,
        "outcome_measures": r.outcome_measures[:5],  # first 5 is plenty
        "abstract": abstract,
    }


def _build_batch_user_message(
    criteria: EligibilityCriteria, batch: list[Record]
) -> str:
    """Assemble the per-batch user message."""
    records_json = json.dumps(
        [_render_record_for_screen(r) for r in batch], indent=2
    )
    return (
        f"{criteria.to_prompt_block()}\n\n"
        f"Records to screen ({len(batch)} total):\n{records_json}\n\n"
        "Return a JSON array of decision objects."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response parsing (robust to typical LLM output flaws)
# ─────────────────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove ```json … ``` fences the model may add despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        # Drop the first fence line and any trailing fence
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def _parse_decisions(raw: str, batch: list[Record]) -> list[ScreenDecision]:
    """Parse Claude's JSON reply into ScreenDecisions.

    Fault-tolerant: if parsing fails, or the array is short, or a row is
    malformed, we return a safe default (exclude, insufficient_metadata) for
    the missing rows. Screening must never crash the pipeline.
    """
    fallback = {
        r.citation_id: ScreenDecision(
            citation_id=r.citation_id,
            include=False,
            exclusion_code="insufficient_metadata",
            reason="Screener response malformed; excluded conservatively.",
        )
        for r in batch
    }

    try:
        payload = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        log.warning("Screen batch JSON parse failed: %s", e)
        return list(fallback.values())

    if not isinstance(payload, list):
        log.warning("Screen batch returned non-array: %r", type(payload).__name__)
        return list(fallback.values())

    for row in payload:
        if not isinstance(row, dict):
            continue
        cid = row.get("citation_id")
        if not cid or cid not in fallback:
            continue
        include = bool(row.get("include", False))
        code_raw = row.get("exclusion_code")
        code: ExclusionCode | None = code_raw if include is False and code_raw else None
        # Guard: if the model says include but also gave a code, trust include=False
        if include and code_raw:
            include = False
            code = code_raw
        # Guard: if excluded but no code, tag insufficient_metadata
        if not include and code is None:
            code = "insufficient_metadata"
        fallback[cid] = ScreenDecision(
            citation_id=cid,
            include=include,
            exclusion_code=code,
            reason=str(row.get("reason", ""))[:250],
        )

    # Preserve original batch order
    return [fallback[r.citation_id] for r in batch]


# ─────────────────────────────────────────────────────────────────────────────
# Batching
# ─────────────────────────────────────────────────────────────────────────────

def _batches(records: list[Record], size: int) -> Iterable[list[Record]]:
    for i in range(0, len(records), size):
        yield records[i : i + size]


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point: the screen() function called by the LangGraph node
# ─────────────────────────────────────────────────────────────────────────────

def screen(
    records: list[Record],
    coi: str,
    llm: LLMDispatcher,
    *,
    batch_size: int = 20,
) -> tuple[list[Record], dict[str, Any]]:
    """Title/abstract screen a list of records against the COI's criteria.

    Returns:
      included: records passing the screen (order preserved)
      screening_report: {
        "screened": <int>,
        "screened_excluded": <int>,
        "excluded_reasons": {<ExclusionCode>: <count>, ...},
        "decisions": [ScreenDecision, ...]  # per-record trace, for audit
      }

    The screening_report is designed to slot directly into PRISMACounts:
      state["prisma_counts"]["screened"] = report["screened"]
      state["prisma_counts"]["screened_excluded"] = report["screened_excluded"]
      state["prisma_counts"]["excluded_reasons"] = report["excluded_reasons"]
    """
    criteria = get_criteria(coi)

    included: list[Record] = []
    all_decisions: list[ScreenDecision] = []
    reason_counts: Counter[str] = Counter()

    for batch in _batches(records, batch_size):
        user_msg = _build_batch_user_message(criteria, batch)
        raw = llm(_SYSTEM_PROMPT, user_msg)
        decisions = _parse_decisions(raw, batch)

        # Map decisions back to records
        cid_to_record = {r.citation_id: r for r in batch}
        for d in decisions:
            all_decisions.append(d)
            if d.include:
                included.append(cid_to_record[d.citation_id])
            elif d.exclusion_code:
                reason_counts[d.exclusion_code] += 1

    report = {
        "screened": len(records),
        "screened_excluded": len(records) - len(included),
        "screen_excluded_reasons": dict(reason_counts),
        "decisions": all_decisions,   # keep for audit / debugging / eval harness
    }

    log.info(
        "screen[%s]: %d in → %d included, %d excluded (%s)",
        coi,
        len(records),
        len(included),
        report["screened_excluded"],
        dict(reason_counts),
    )
    return included, report


__all__ = [
    "screen",
    "ScreenDecision",
    "LLMDispatcher",
]