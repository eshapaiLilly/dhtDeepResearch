"""
assemble.py — the post-merge report assembly stage.

This is the second half of the pipeline, deliberately SEPARATE from graph.py.
graph.py runs per-COI (its router raises if cois != 1); als_dryRun1.py runs it
once per COI and merges. Everything here operates on that MERGED, whole-
landscape state — gap consolidation, corpus statistics, citation verification,
narrative synthesis, and docx rendering are all landscape-level, not COI-level.
Putting them in graph.py would (wrongly) produce one document per COI.

Order and rationale
-------------------
  1. consolidate_gaps   — collapse duplicate cross-COI gaps first, so stats and
                          the gap log count systemic gaps once, not N times.
  2. corpus_stats       — compute distributions + render figures. Pure, no LLM.
  3. synthesize         — write narrative (LLM if provided, else deterministic).
                          Runs BEFORE verify so verify can check the prose too.
  4. verify             — citation integrity gate over structured state AND the
                          synthesized prose. Strict by default (raises on
                          orphans); non-strict downgrades to a disclosure.
  5. build_docx         — render everything. Pure, no LLM.

The result is a dict that maps onto DHTState's presentation channels
(report_sections, figures, corpus_stats, verify_report, final_report_path) so
this can later be lifted into a LangGraph subgraph with no shape changes.
"""
from __future__ import annotations

import logging
from pathlib import Path

from state import COIEvidence, DeviceRow, Gap, Record
from gaps_consolidate import consolidate_gaps, group_by_severity
from corpus_stats import run_corpus_stats
from synthesize import run_synthesis
from verify import run_verify
from build_docx import build_docx


log = logging.getLogger(__name__)


def assemble_report(
    *,
    indication: str,
    cois: list[str],
    corpus: list[Record],
    citations_index: dict[str, Record],
    devices: list[DeviceRow],
    gaps: list[Gap],
    evidence: list[COIEvidence],
    prisma_by_coi: dict[str, dict],
    criteria_render,                       # criteria.render_methodology_block
    out_dir: Path,
    run_notes: list[str] | None = None,
    synthesis_llm=None,                    # LLMDispatcher | None
    strict_citations: bool = True,
) -> dict:
    """Run the full assembly stage and write the .docx. Returns a dict of the
    presentation-channel outputs (maps onto DHTState)."""
    out_dir = Path(out_dir)
    fig_dir = out_dir / "figures"

    # 1. consolidate gaps across COIs
    consolidated = consolidate_gaps(gaps)

    # 2. corpus statistics + figures
    stats, figures = run_corpus_stats(
        corpus=corpus, devices=devices, evidence=evidence,
        prisma_by_coi=prisma_by_coi, out_dir=fig_dir,
    )

    # 3. synthesize narrative (LLM or deterministic)
    report_sections = run_synthesis(
        indication=indication, cois=cois, devices=devices,
        evidence=evidence, gaps=consolidated, stats=stats,
        llm=synthesis_llm, run_notes=run_notes,
    )

    # 4. verify citations over structured state + synthesized prose
    prose_blob = "\n".join(
        [report_sections.get("executive_summary", "")]
        + [p for s in report_sections.get("coi_sections", []) for p in s.get("paragraphs", [])]
        + report_sections.get("recommendations", [])
    )
    verify_report, cleaned_prose = run_verify(
        citations_index, devices, consolidated, evidence, prose_blob,
        strict=strict_citations,
    )
    # if non-strict stripped in-text orphans, reflect that back into the prose
    if not strict_citations and cleaned_prose != prose_blob:
        report_sections["executive_summary"] = strip_from(
            report_sections["executive_summary"], verify_report["orphan_citations"]
        )
        for s in report_sections.get("coi_sections", []):
            s["paragraphs"] = [
                strip_from(p, verify_report["orphan_citations"]) for p in s.get("paragraphs", [])
            ]

    # 5. render docx
    gaps_by_sev = group_by_severity(consolidated)
    out_path = out_dir / f"{indication.lower().replace(' ', '_')}_dht_landscape_review.docx"
    build_docx(
        indication=indication, cois=cois,
        report_sections=report_sections,
        devices=devices,
        gaps_by_severity=gaps_by_sev,
        figures=figures,
        citations_index=citations_index,
        verify_report=verify_report,
        corpus_stats=stats,
        criteria_render=criteria_render,
        out_path=out_path,
        run_notes=run_notes,
    )

    return {
        "report_sections": report_sections,
        "figures": figures,
        "corpus_stats": stats,
        "verify_report": verify_report,
        "final_report_path": str(out_path),
    }


def strip_from(text: str, orphans: list[str]) -> str:
    from verify import strip_text_orphans
    return strip_text_orphans(text, orphans)


__all__ = ["assemble_report"]