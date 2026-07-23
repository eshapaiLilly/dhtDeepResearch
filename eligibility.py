"""
eligibility.py — full-record eligibility node (PRISMA stage 3 of 4).

Where this sits in the funnel
------------------------------
  identify  (Python only)        → raw_records
  screen    (cheap LLM, per-record, title/abstract only) → screened_records
  ELIGIBILITY (this file: Python enrich + cheap LLM, per-record, FULL record)
                                  → corpus + citations_index (FROZEN)
  evidence/device (Sonnet 4.6, dht-landscape-scout SKILL.md, whole-corpus)
  synthesize      (Sonnet 4.6, dht-str SKILL.md, all-COIs)

What eligibility is NOT
------------------------
It is not tiering. It does not apply the 12-criterion rubric, does not rank,
does not compute bias ratings. That is the evidence/device node's job, done
once over the whole surviving corpus with the actual skill prompt loaded —
a fundamentally different kind of judgment (cross-record, e.g. "how many
total publications exist") than the per-record yes/no this file answers.

What eligibility IS
--------------------
The same inclusion/exclusion question screen.py already asked, asked again
with fuller data. Screen only ever saw a title + abstract snippet. This
stage:
  1. ENRICHES each surviving record — fetches the full CT study record or
     full PubMed metadata, filling in fields retrieval.py couldn't populate
     from search-result payloads alone (full outcome-measure list, full
     abstract, confirmed DOI).
  2. RE-JUDGES eligibility against the enriched record. This catches two
     things screen structurally cannot:
       (a) a record that looked include-worthy from the abstract but the
           full record reveals a disqualifying detail
       (b) a record screen excluded as "insufficient_metadata" that fuller
           data actually resolves — these get a chance to come back in
  3. FREEZES the corpus and citations_index. After this stage, no new
     citation_ids are ever introduced — the verify node's job later is only
     to check that nothing downstream cites outside this frozen set.

The Python↔model↔Python template (reusable for recall_patterns.py later)
--------------------------------------------------------------------------
  enrich_record()      — Python: MCP fetch, deterministic, fault-tolerant
  eligibility_screen()  — LLM: judgment call over the enriched text
  eligibility()         — Python: orchestrates enrich → judge → freeze

This is the same three-step shape sub-construct elicitation and the
naming-fragmentation recovery passes will need later (see the Open
Questions ledger in dht-landscape-scout's SKILL.md, item 2): Python runs a
fetch, the model judges the result, Python commits it to state. Getting the
shape right here means those later features can copy this file's structure
rather than re-deriving it.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any, Callable, Iterable, get_args

from criteria import EligibilityCriteria, ExclusionCode, get as get_criteria
from retrieval import MCPDispatcher, build_citations_index
from state import Record


log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 (Python): enrichment
# ─────────────────────────────────────────────────────────────────────────────

def _merge_ctg_detail(record: Record, detail: dict) -> Record:
    """Merge a get_trial_details payload into a Record.

    `search_trials` results (used in retrieval.py) are often summary views;
    `get_trial_details` returns the full protocol, which can include
    secondary outcome measures, fuller enrollment/eligibility text, and
    arm-level intervention detail not present in the summary payload.
    """
    try:
        proto = detail["protocolSection"]
    except (KeyError, TypeError):
        log.warning("get_trial_details payload malformed for %s; skipping merge", record.citation_id)
        return record

    outcomes_mod = proto.get("outcomesModule", {})
    full_outcomes = [
        o.get("measure")
        for o in (outcomes_mod.get("primaryOutcomes", []) or [])
        + (outcomes_mod.get("secondaryOutcomes", []) or [])
        if o.get("measure")
    ]
    # Prefer the fuller list if it's actually fuller; never shrink what we had.
    outcome_measures = full_outcomes if len(full_outcomes) > len(record.outcome_measures) else record.outcome_measures

    enrollment = (
        proto.get("designModule", {}).get("enrollmentInfo", {}).get("count")
        or record.enrollment
    )

    return replace(
        record,
        outcome_measures=outcome_measures,
        enrollment=enrollment,
        raw={**record.raw, "full_detail": detail},
    )


def _merge_pubmed_detail(record: Record, detail: dict) -> Record:
    """Merge a get_article_metadata payload into a Record.

    Search-result payloads sometimes omit the abstract or DOI to keep
    result lists compact; the per-article metadata call returns the full
    record.
    """
    abstract = detail.get("abstract") or record.abstract
    doi = detail.get("doi") or record.doi
    journal = detail.get("journal") or detail.get("source") or record.journal
    return replace(
        record,
        abstract=abstract,
        doi=doi,
        journal=journal,
        raw={**record.raw, "full_metadata": detail},
    )


def enrich_record(record: Record, mcp: MCPDispatcher) -> Record:
    """Fetch the full record for one Record and merge it in.

    Fault-tolerant by design: enrichment is a best-effort upgrade, not a
    requirement. If the fetch fails or returns nothing usable, the original
    record is returned unchanged and eligibility judges on what it already
    has — a missing enrichment is a reporting-quality note, not a crash.
    """
    try:
        if record.source == "clinicaltrials" and record.nct_id:
            detail = mcp("ClinicalTrials:get_trial_details", {"nct_id": record.nct_id})
            if detail:
                return _merge_ctg_detail(record, detail)
        elif record.source == "pubmed" and record.pmid:
            detail = mcp("PubMed:get_article_metadata", {"pmid": record.pmid})
            if detail:
                return _merge_pubmed_detail(record, detail)
    except Exception as e:  # noqa: BLE001 — enrichment must never take down the run
        log.warning("Enrichment failed for %s: %s", record.citation_id, e)
    return record


def enrich_all(
    records: list[Record],
    mcp: MCPDispatcher,
    *,
    max_workers: int = 8,
) -> list[Record]:
    """Enrich every record, concurrently. Order preserved; failures fall
    back per-record (enrich_record already catches its own exceptions and
    returns the un-enriched record — that contract is unchanged here).

    This was previously a plain serial list comprehension — one HTTP round
    trip per record, one at a time, even though every record's enrichment
    is fully independent of every other. That's pure network-bound wait
    time with no reason to be sequential, and was a real contributor to a
    live run taking over an hour on a ~800-initial-hit COI.

    max_workers=8 is a starting point, not tuned against a hard ceiling:
    live_clients.py's _throttle() is now thread-safe (a shared lock, not
    per-thread), so raising max_workers doesn't bypass the rate limit —
    it just lets more threads queue up waiting on the same shared pacing,
    which is exactly what should happen. Total request rate across all
    workers is still capped by _MIN_INTERVAL regardless of max_workers.
    """
    if not records:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # map() preserves input order in its output order, even though
        # completion order across threads is unordered — exactly what's
        # needed here, since downstream code (eligibility_screen, PRISMA
        # counts) assumes records stay in their original sequence.
        return list(pool.map(lambda r: enrich_record(r, mcp), records))


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 (LLM): the full-record eligibility judgment
# ─────────────────────────────────────────────────────────────────────────────
# Same dispatcher shape as screen.py's LLMDispatcher — kept as a distinct
# type alias here so eligibility.py has no import dependency on screen.py;
# the two stages are siblings, not a chain of imports.

LLMDispatcher = Callable[[str, str], str]


_SYSTEM_PROMPT = """\
You are performing the FULL-RECORD eligibility assessment in a PRISMA-style
DHT (digital health technology) landscape review — the second and final
screen, after a title/abstract pass has already run. You are seeing more
data than the first pass saw (full outcome-measure lists, full abstracts,
confirmed metadata where available).

Your only job is inclusion/exclusion against the criteria you are given.
You are NOT scoring evidence quality, NOT assigning tiers, NOT ranking
devices — that happens in a separate step, over the whole surviving set at
once, not here.

For each record, output one JSON object with these keys:
  - "citation_id": string, exactly as given
  - "include": boolean
  - "exclusion_code": one of the ExclusionCode values, or null if include=true
  - "reason": one short sentence (<= 25 words), grounded in the record text
  - "reversed_from_screen": boolean — true if you are including a record
    that was previously excluded at the title/abstract stage, now resolved
    by fuller data (or vice versa: excluding one that previously passed)

Rules:
- Judge against the FULL record now available, not just title/abstract.
- If a record was excluded at screen as "insufficient_metadata" and the
  enriched data resolves the ambiguity, judge fresh — don't defer to the
  prior decision.
- If ANY exclusion criterion applies, exclude (choose the FIRST matching code).
- Do NOT invent metadata not present in the record. If still uncertain after
  seeing the full record, exclude with "insufficient_metadata".
- Return a JSON ARRAY of decision objects, one per input record, in the same
  order. No prose before or after. No markdown code fences.
"""


def _render_record_for_eligibility(r: Record) -> dict:
    """Fuller view than screen.py's — includes the enriched fields."""
    abstract = (r.abstract or "").strip()
    if len(abstract) > 2000:  # more room than screen's 1200: this is the full-data pass
        abstract = abstract[:2000] + " …[truncated]"
    return {
        "citation_id": r.citation_id,
        "source": r.source,
        "title": r.title,
        "year": r.year,
        "condition": r.condition,
        "intervention": r.intervention,
        "intervention_type": r.intervention_type,
        "sponsor": r.sponsor,
        "sponsor_class": r.sponsor_class,
        "enrollment": r.enrollment,
        "phase": r.phase,
        "status": r.status,
        "outcome_measures": r.outcome_measures,   # full list now, not truncated
        "abstract": abstract,
        "device": r.device,
        "wear_location": r.wear_location,
    }


def _build_batch_user_message(criteria: EligibilityCriteria, batch: list[Record]) -> str:
    records_json = json.dumps([_render_record_for_eligibility(r) for r in batch], indent=2)
    return (
        f"{criteria.to_prompt_block()}\n\n"
        f"Full records to assess ({len(batch)} total):\n{records_json}\n\n"
        "Return a JSON array of decision objects."
    )


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")


def _fix_trailing_commas(text: str) -> str:
    """Same fix as screen.py's — kept duplicated rather than shared per
    this file's existing convention (see _strip_fences/_batches, both
    already near-duplicates of screen.py's versions). Strips a trailing
    comma before a closing ]/} — a JSON5-ism the model occasionally
    emits, narrow enough that it can't change any actual returned value."""
    return _TRAILING_COMMA_RE.sub(r"\1", text)


class EligibilityDecision:
    """Lightweight record of one eligibility judgment. Kept for the audit trail."""

    __slots__ = ("citation_id", "include", "exclusion_code", "reason", "reversed_from_screen")

    def __init__(self, citation_id: str, include: bool, exclusion_code: ExclusionCode | None,
                 reason: str, reversed_from_screen: bool = False):
        self.citation_id = citation_id
        self.include = include
        self.exclusion_code = exclusion_code
        self.reason = reason
        self.reversed_from_screen = reversed_from_screen


_VALID_EXCLUSION_CODES = set(get_args(ExclusionCode))


def _normalize_exclusion_code(code_raw: str | None, reason: str) -> tuple[str, str]:
    """Same validation as screen.py's — kept as a near-duplicate rather
    than a shared import so eligibility.py and screen.py stay independent
    siblings (matches this file's existing convention, e.g. its own
    _batches() helper duplicated rather than imported from screen.py)."""
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


def _parse_decisions(raw: str, batch: list[Record]) -> list[EligibilityDecision]:
    """Same fault-tolerant contract as screen.py: malformed output never
    crashes the run — it falls back to a safe, conservative exclude."""
    fallback = {
        r.citation_id: EligibilityDecision(
            citation_id=r.citation_id, include=False,
            exclusion_code="insufficient_metadata",
            reason="Eligibility response malformed; excluded conservatively.",
        )
        for r in batch
    }

    try:
        payload = json.loads(_fix_trailing_commas(_strip_fences(raw)))
    except json.JSONDecodeError as e:
        log.warning("Eligibility batch JSON parse failed: %s", e)
        return list(fallback.values())

    if not isinstance(payload, list):
        log.warning("Eligibility batch returned non-array: %r", type(payload).__name__)
        return list(fallback.values())

    for row in payload:
        if not isinstance(row, dict):
            continue
        cid = row.get("citation_id")
        if not cid or cid not in fallback:
            continue
        include = bool(row.get("include", False))
        code_raw = row.get("exclusion_code")
        code: ExclusionCode | None = code_raw if not include and code_raw else None
        if include and code_raw:          # contradiction guard, same as screen.py
            include, code = False, code_raw
        if not include and code is None:
            code = "insufficient_metadata"
        reason_text = str(row.get("reason", ""))[:250]
        if not include:
            code, reason_text = _normalize_exclusion_code(code, reason_text)
        fallback[cid] = EligibilityDecision(
            citation_id=cid,
            include=include,
            exclusion_code=code,
            reason=reason_text,
            reversed_from_screen=bool(row.get("reversed_from_screen", False)),
        )
    return [fallback[r.citation_id] for r in batch]


def _batches(records: list[Record], size: int) -> Iterable[list[Record]]:
    for i in range(0, len(records), size):
        yield records[i : i + size]


def eligibility_screen(
    records: list[Record],
    coi: str,
    llm: LLMDispatcher,
    *,
    batch_size: int = 15,   # smaller than screen.py's 20 — full records are bigger per-item
    batch_workers: int = 4,
) -> tuple[list[Record], list[EligibilityDecision]]:
    """Run the full-record eligibility judgment. Returns (included, decisions).

    Batches run concurrently (same rationale as enrich_all() above): each
    batch's LLM call is independent network-bound work. map() preserves
    order, and _parse_decisions is fault-tolerant (a malformed batch becomes
    conservative excludes, never raises), so the pool can't be poisoned by a
    single bad response. Aggregation stays serial and race-free. NOTE: total
    concurrent gateway calls = COI_workers (als_dryRun) * batch_workers;
    lower either if the gateway rate-limits."""
    criteria = get_criteria(coi)
    included: list[Record] = []
    all_decisions: list[EligibilityDecision] = []

    def _run_batch(batch: list[Record]) -> tuple[list[Record], list[EligibilityDecision]]:
        user_msg = _build_batch_user_message(criteria, batch)
        raw = llm(_SYSTEM_PROMPT, user_msg)
        return batch, _parse_decisions(raw, batch)

    batches = list(_batches(records, batch_size))
    workers = max(1, min(batch_workers, len(batches)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run_batch, batches))

    for batch, decisions in results:
        cid_to_record = {r.citation_id: r for r in batch}
        for d in decisions:
            all_decisions.append(d)
            if d.include:
                included.append(cid_to_record[d.citation_id])

    return included, all_decisions


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 (Python): orchestrate enrich → judge → freeze
# ─────────────────────────────────────────────────────────────────────────────

def eligibility(
    screened_records: list[Record],
    coi: str,
    mcp: MCPDispatcher,
    llm: LLMDispatcher,
    *,
    enrich_workers: int = 8,
) -> tuple[list[Record], dict[str, Record], dict[str, Any]]:
    """The eligibility node's full pipeline: enrich, judge, freeze.

    `enrich_workers` is passed straight through to enrich_all()'s thread
    pool — exposed here rather than hardcoded so graph.py can tune it per
    run without another signature change later.

    Returns:
      corpus:           the final, included Record list — THIS IS FROZEN.
                         No downstream node introduces new citation_ids.
      citations_index:  {citation_id: Record}, built once here.
      report:           PRISMA-shaped dict, ready to merge into
                         state["prisma_counts"]:
                           {"eligible": <int screened in>,
                            "eligible_excluded": <int>,
                            "excluded_reasons": {code: count},
                            "included": <int final corpus size>,
                            "reversals_from_screen": <int>,
                            "decisions": [...]}  # audit trail
    """
    enriched = enrich_all(screened_records, mcp, max_workers=enrich_workers)
    included, decisions = eligibility_screen(enriched, coi, llm)

    reason_counts: Counter[str] = Counter(
        d.exclusion_code for d in decisions if not d.include and d.exclusion_code
    )
    reversals = sum(1 for d in decisions if d.reversed_from_screen)

    corpus = included
    citations_index = build_citations_index(corpus)

    report = {
        "eligible": len(screened_records),
        "eligible_excluded": len(screened_records) - len(corpus),
        "eligible_excluded_reasons": dict(reason_counts),
        "included": len(corpus),
        "reversals_from_screen": reversals,
        "decisions": decisions,
    }

    log.info(
        "eligibility[%s]: %d in → %d included, %d excluded (%s), %d reversed from screen",
        coi, len(screened_records), len(corpus), report["eligible_excluded"],
        dict(reason_counts), reversals,
    )
    return corpus, citations_index, report


__all__ = [
    "enrich_record",
    "enrich_all",
    "eligibility_screen",
    "eligibility",
    "EligibilityDecision",
    "LLMDispatcher",
]