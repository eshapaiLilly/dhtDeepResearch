"""
gaps_consolidate.py — cross-COI gap consolidation (post-merge assembly stage).

Why this exists
---------------
The per-COI graph emits `Gap` objects scoped to one COI. als_dryRun1.py's
`_merge_gaps()` simply *concatenates* them (its RUN_NOTES even admits "no
cross-COI ... rollup"). That produces duplicates: the same structural gap
("no MID/MICD for the primary endpoint", "vendor trial history missing")
recurs verbatim under three or four COIs, so a reader sees the same finding
four times and can't tell one systemic gap from four independent ones.

This module merges gaps that are the *same finding* across COIs into a single
row whose `affected_cois` lists every COI it touches, keeping the highest
severity seen. That is exactly the "systemic vs. local" distinction a reviewer
needs, and it's what makes the gap log actionable rather than repetitive.

Deterministic on purpose
-------------------------
This is pure Python — no LLM. Two reasons, both matching the codebase's
"state is the audit trail" principle (state.py docstring):
  1. Reproducibility: two runs over the same gaps must consolidate identically,
     or the reconciliation/comparison story the SKILL.md requires falls apart.
  2. Auditability: the merge key is inspectable and explainable ("these two
     rows merged because their category + normalized description matched"),
     whereas an LLM semantic merge is not.

Semantic merge (an LLM deciding "these two differently-worded gaps are really
the same") is a possible future enhancement and is noted in __doc__ of
`consolidate_gaps`, but it is deliberately NOT the default.
"""
from __future__ import annotations

import logging
import re
from collections import OrderedDict

from state import Gap


log = logging.getLogger(__name__)

# Severity ordering so a merge keeps the worst severity seen across COIs.
_SEVERITY_RANK = {"blocking": 3, "notable": 2, "acknowledged": 1}


def _normalize(text: str) -> str:
    """Normalize a gap description for keying: lowercase, collapse whitespace,
    strip trailing punctuation, and remove COI-specific and citation-specific
    tokens so 'no MID for MVPA (PMID:123)' and 'no MID for gait (PMID:456)'
    key to the same systemic gap.

    This is intentionally conservative: it removes obvious per-COI noise
    (parenthetical citations, NCT/PMID tokens, digits) but does NOT try to do
    semantic clustering. If two gaps are worded differently they stay separate
    — a false split is safe (reader sees two rows), a false merge is not
    (reader loses a distinct finding).
    """
    t = text.lower().strip()
    t = re.sub(r"\((?:pmid|nct|doi)[^)]*\)", " ", t)   # drop parenthetical cites
    t = re.sub(r"\b(?:pmid|nct)[:\s]?\d+\b", " ", t)     # drop bare cite tokens
    t = re.sub(r"\bk\d{6}\b", " ", t)                    # drop 510(k) numbers
    t = re.sub(r"\d+", " ", t)                            # drop remaining digits (N=, years)
    t = re.sub(r"[^\w\s]", " ", t)                        # drop punctuation
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _merge_key(gap: Gap) -> tuple[str, str]:
    """Two gaps merge iff they share a category AND a normalized description."""
    return (gap.category, _normalize(gap.description))


def consolidate_gaps(gaps: list[Gap]) -> list[Gap]:
    """Merge same-finding gaps across COIs into one row each.

    Merge rule (deterministic):
      - key = (category, normalized_description)
      - affected_cois = union of all merged rows' affected_cois (sorted)
      - severity = max severity seen (blocking > notable > acknowledged)
      - supporting_citations = union (sorted, deduped)
      - description/action = taken from the FIRST-seen row with the highest
        severity, so the surviving text is the most urgent phrasing, not an
        arbitrary one
      - gap_id = the first-seen row's id (stable; renumbering would break any
        cross-reference a synthesized report makes to it)

    Returns a new list; input is not mutated. Order is preserved by
    first-appearance so the output is stable run-to-run.

    NOTE (future option, not default): a semantic-merge variant could ask an
    LLM whether two differently-worded gaps are the same finding before
    merging. Kept out of the default path for reproducibility/auditability
    (see module docstring).
    """
    buckets: "OrderedDict[tuple[str, str], list[Gap]]" = OrderedDict()
    for g in gaps:
        buckets.setdefault(_merge_key(g), []).append(g)

    consolidated: list[Gap] = []
    n_merged = 0
    for key, group in buckets.items():
        if len(group) == 1:
            consolidated.append(group[0])
            continue

        n_merged += len(group) - 1
        # Winner (for surviving text) = highest severity, then first-seen.
        winner = max(group, key=lambda g: _SEVERITY_RANK.get(g.severity, 0))
        affected = sorted({c for g in group for c in g.affected_cois})
        citations = sorted({c for g in group for c in g.supporting_citations})
        worst_sev = max(group, key=lambda g: _SEVERITY_RANK.get(g.severity, 0)).severity

        consolidated.append(Gap(
            gap_id=group[0].gap_id,
            category=winner.category,
            description=winner.description,
            severity=worst_sev,
            affected_cois=affected,
            action=winner.action,
            supporting_citations=citations,
        ))

    log.info(
        "gaps_consolidate: %d gaps -> %d consolidated (%d duplicate rows merged)",
        len(gaps), len(consolidated), n_merged,
    )
    return consolidated


def group_by_severity(gaps: list[Gap]) -> "OrderedDict[str, list[Gap]]":
    """Order gaps blocking → notable → acknowledged for report rendering.
    Blocking gaps must lead the gap log — they're what stops a submission."""
    out: "OrderedDict[str, list[Gap]]" = OrderedDict(
        (s, []) for s in ("blocking", "notable", "acknowledged")
    )
    for g in gaps:
        out.setdefault(g.severity, []).append(g)
    # Drop empty severity buckets so the report doesn't render empty headers.
    return OrderedDict((k, v) for k, v in out.items() if v)


__all__ = ["consolidate_gaps", "group_by_severity"]