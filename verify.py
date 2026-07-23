"""
verify.py — the citation-integrity gate for the assembled landscape.

Where this sits vs. evidence.py's grounding check
--------------------------------------------------
evidence.py already strips orphan citations from ONE COI's output at parse
time. This node is different and comes later: it runs over the FULLY MERGED,
CONSOLIDATED state (all COIs' devices + gaps + evidence together) and over the
SYNTHESIZED report text, and it is the last line of defense before a document
ships. state.py's VerifyReport docstring calls orphan presence "a blocking
condition for the docx builder — you don't ship a report with unresolvable
citations." This module implements that gate.

What it checks
--------------
1. Structured orphans: every citation_id referenced by any DeviceRow /
   Gap / COIEvidence must resolve in `citations_index`. (Should be empty if
   evidence.py did its job per-COI, but merging can't introduce orphans and
   consolidation shouldn't either — this proves it.)
2. Report-text orphans: after synthesis, the report prose may reference
   citation tokens. Any citation-looking token in the report that isn't in
   `citations_index` is an orphan. This catches an LLM synthesizer inventing
   or mis-transcribing a PMID/NCT in the narrative — exactly the failure the
   structured grounding check can't see because it lives in prose.

Blocking vs. disclosed-degradation
-----------------------------------
Default: orphans BLOCK (raise). But consistent with how this codebase treats
recall gaps (disclose, don't crash), `run_verify(..., strict=False)` downgrades
orphans to a disclosed limitation: they're stripped from the report text,
recorded in the VerifyReport, and surfaced in the document's Limitations
section. The pipeline chooses which mode; the default is strict.

Deterministic. No LLM. (Entailment checking — does the cited source actually
support the claim — is a genuinely LLM task and is left as a documented
extension point, NOT silently claimed. See ENTAILMENT_NOTE.)
"""
from __future__ import annotations

import logging
import re

from state import COIEvidence, DeviceRow, Gap, Record, VerifyReport


log = logging.getLogger(__name__)

# Tokens that look like citation IDs this pipeline emits: NCT numbers and
# PMID:12345 forms. DOIs are intentionally not auto-detected in free text
# (too many false positives from URLs); DOI citations flow through the
# structured citation lists, which are checked exhaustively regardless.
_CITATION_TOKEN = re.compile(r"\b(?:NCT\d{8}|PMID:\s?\d+)\b")

ENTAILMENT_NOTE = (
    "Entailment verification (confirming a cited source actually supports the "
    "specific claim it's attached to) is a separate LLM-driven check and is "
    "NOT performed here. This node verifies citation RESOLVABILITY only — that "
    "every cited token exists in the frozen corpus. state.py's VerifyReport "
    "reserves an `entailment_failures` field for the future check."
)


def _structured_citations(
    devices: list[DeviceRow],
    gaps: list[Gap],
    evidence: list[COIEvidence],
) -> set[str]:
    """Collect every citation_id referenced by the structured outputs."""
    cited: set[str] = set()
    for d in devices:
        cited.update(d.evidence_citations or [])
    for g in gaps:
        cited.update(g.supporting_citations or [])
    for e in evidence:
        cited.update(e.key_citations or [])
    return cited


def _text_citation_tokens(report_text: str) -> set[str]:
    """Extract citation-looking tokens from report prose, normalized so
    'PMID: 123' and 'PMID:123' match the index key form 'PMID:123'."""
    raw = set(_CITATION_TOKEN.findall(report_text or ""))
    return {re.sub(r"PMID:\s?", "PMID:", t) for t in raw}


def verify_citations(
    citations_index: dict[str, Record],
    devices: list[DeviceRow],
    gaps: list[Gap],
    evidence: list[COIEvidence],
    report_text: str = "",
) -> VerifyReport:
    """Build the VerifyReport. Does not raise — callers decide on strictness."""
    valid = set(citations_index.keys())

    struct_cited = _structured_citations(devices, gaps, evidence)
    struct_orphans = struct_cited - valid

    text_cited = _text_citation_tokens(report_text)
    text_orphans = text_cited - valid

    all_orphans = sorted(struct_orphans | text_orphans)
    n_total = len(struct_cited | text_cited)
    n_verified = n_total - len(all_orphans)

    report: VerifyReport = {
        "orphan_citations": all_orphans,
        "unresolved_citations": [],       # reserved: index entries whose live lookup failed
        "entailment_failures": [],        # reserved: see ENTAILMENT_NOTE
        "n_citations_total": n_total,
        "n_citations_verified": n_verified,
        "citation_precision": (n_verified / n_total) if n_total else 1.0,
    }
    log.info(
        "verify: %d cited tokens, %d verified, %d orphan(s) (%d structured, %d in-text)",
        n_total, n_verified, len(all_orphans), len(struct_orphans), len(text_orphans),
    )
    return report


def strip_text_orphans(report_text: str, orphans: list[str]) -> str:
    """Remove orphan citation tokens from report prose (non-strict mode).
    Replaces '(PMID:999)' / 'PMID:999' with '[citation removed — unresolved]'
    so the reader sees a deliberate redaction, not a silent deletion."""
    text = report_text
    for tok in orphans:
        # match the token with optional surrounding parens/space
        text = re.sub(
            r"\(?\s*" + re.escape(tok) + r"\s*\)?",
            "[citation removed — unresolved]",
            text,
        )
    return text


def run_verify(
    citations_index: dict[str, Record],
    devices: list[DeviceRow],
    gaps: list[Gap],
    evidence: list[COIEvidence],
    report_text: str = "",
    *,
    strict: bool = True,
) -> tuple[VerifyReport, str]:
    """Run verification. Returns (verify_report, possibly_cleaned_report_text).

    strict=True (default): raise ValueError if any orphan exists — the docx
        builder must not run.
    strict=False: strip in-text orphans, keep going, and rely on the caller to
        surface report['orphan_citations'] in the document's Limitations
        section (build_docx does this automatically).
    """
    report = verify_citations(citations_index, devices, gaps, evidence, report_text)
    orphans = report["orphan_citations"]

    if orphans and strict:
        raise ValueError(
            f"verify: {len(orphans)} orphan citation(s) do not resolve in the "
            f"frozen corpus: {orphans[:10]}"
            + (" ..." if len(orphans) > 10 else "")
            + ". Refusing to build the report (strict mode). Re-run with "
            "strict=False to downgrade to a disclosed limitation."
        )

    cleaned = report_text
    if orphans and not strict:
        cleaned = strip_text_orphans(report_text, orphans)
        log.warning("verify: non-strict — stripped %d in-text orphan(s), "
                    "will disclose in Limitations", len(orphans))

    return report, cleaned


__all__ = [
    "verify_citations",
    "run_verify",
    "strip_text_orphans",
    "ENTAILMENT_NOTE",
]