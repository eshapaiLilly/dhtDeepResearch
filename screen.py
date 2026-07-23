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
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
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
- Each record's "source" field is either "clinicaltrials" or "pubmed" — these
  carry fundamentally different metadata shapes, and "missing abstract" means
  something different for each:
    * source="clinicaltrials": these records NEVER carry a prose abstract —
      that is normal for this source, not a sign of thin data. Judge these
      from title + condition + intervention + intervention_type +
      outcome_measures instead. Do NOT exclude a clinicaltrials record as
      "insufficient_metadata" solely because its abstract field is empty —
      only do so if title/condition/intervention/outcome_measures TOGETHER
      give too little signal to assess the inclusion/exclusion criteria.
    * source="pubmed": these records normally DO carry an abstract. If a
      pubmed record's abstract is genuinely missing or too thin to assess
      (and the title alone isn't enough), exclude with code
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


_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")


def _fix_trailing_commas(text: str) -> str:
    """Strip a trailing comma before a closing ] or } — a JSON5-ism the
    model occasionally emits despite instructions, and one that a live run
    hit twice, each time forcing an entire ~20-record batch into the
    fault-tolerant fallback (exclude, insufficient_metadata) for a pure
    formatting slip rather than an actual judgment problem. This is a
    narrow, safe fix: it only removes a comma immediately before a closing
    bracket/brace, so it can't silently change any value the model
    actually returned."""
    return _TRAILING_COMMA_RE.sub(r"\1", text)


from typing import get_args

_VALID_EXCLUSION_CODES = set(get_args(ExclusionCode))


def _normalize_exclusion_code(code_raw: str | None, reason: str) -> tuple[str, str]:
    """Validate exclusion_code against the known ExclusionCode set.

    criteria.py's to_prompt_block() labels each exclusion criterion "E1",
    "E2", "E3"... with the actual code in brackets (e.g. "E3
    [wrong_study_type]: ..."). Observed in a real run: the model
    occasionally echoes the LABEL ("E3") instead of the CODE
    ("wrong_study_type") for a small fraction of records — harmless to the
    include/exclude decision itself, but it silently pollutes the PRISMA
    exclusion-reason tally with non-standard keys if not caught. Normalize
    anything not in the known set to "insufficient_metadata" and keep the
    raw value visible in the reason text rather than losing it.
    """
    if code_raw in _VALID_EXCLUSION_CODES:
        return code_raw, reason
    if code_raw:
        log.warning(
            "Unrecognized exclusion_code %r from model (expected one of %s); "
            "normalizing to insufficient_metadata",
            code_raw, sorted(_VALID_EXCLUSION_CODES),
        )
        return "insufficient_metadata", f"{reason} (raw model code: {code_raw})"
    return "insufficient_metadata", reason


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
        payload = json.loads(_fix_trailing_commas(_strip_fences(raw)))
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
        reason_text = str(row.get("reason", ""))[:250]
        if not include:
            code, reason_text = _normalize_exclusion_code(code, reason_text)
        fallback[cid] = ScreenDecision(
            citation_id=cid,
            include=include,
            exclusion_code=code,
            reason=reason_text,
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
    batch_workers: int = 4,
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

    def _run_batch(batch: list[Record]) -> tuple[list[Record], list[ScreenDecision]]:
        """One batch's LLM call + parse. Pure w.r.t. shared state — returns
        its results for the caller to aggregate serially, so the parallel
        map has no data races. _parse_decisions is already fault-tolerant:
        a malformed batch degrades to conservative excludes, it never
        raises, so one bad batch can't poison the pool."""
        user_msg = _build_batch_user_message(criteria, batch)
        raw = llm(_SYSTEM_PROMPT, user_msg)
        return batch, _parse_decisions(raw, batch)

    batches = list(_batches(records, batch_size))
    # Batch LLM calls are independent network-bound work — the same reason
    # enrich_all() in eligibility.py uses a pool. map() preserves input order
    # in its output, so PRISMA-relevant ordering is unchanged vs. the old
    # serial loop. Aggregation below stays single-threaded, so Counter /
    # list mutation is race-free. Keep batch_workers modest: when the COI
    # loop itself is parallelized (als_dryRun.py), total concurrent gateway
    # calls = COI_workers * batch_workers — lower either if the gateway 429s.
    workers = max(1, min(batch_workers, len(batches)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run_batch, batches))

    for batch, decisions in results:
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