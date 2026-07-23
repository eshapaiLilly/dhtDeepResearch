"""
build_report_from_json.py — build a landscape review document from a saved
dry-run JSON (the output of als_dryRun1.py's _write_output()).

This is the seam that lets the document pipeline run WITHOUT re-running
retrieval/screening/scoring: it rehydrates the merged state that als_dryRun1.py
already wrote to disk, then hands it to assemble.py. It also means BME can
regenerate the document from a completed run instantly, and can diff two runs'
documents without paying for retrieval twice.

Usage:
    python build_report_from_json.py als_landscape_dry_run.json outputs/
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from state import COIEvidence, DeviceRow, Gap, Record
from criteria import render_methodology_block
from assemble import assemble_report


def build_citations_index(corpus: list[Record]) -> dict[str, Record]:
    """Map citation_id -> Record. (retrieval.py provides this in the live
    pipeline; rebuilt here so the JSON runner has no retrieval dependency.)"""
    return {r.citation_id: r for r in corpus}


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def _rec(d: dict) -> Record:
    # Record has many optional fields; construct by filtering to known keys.
    known = Record.__dataclass_fields__.keys()
    return Record(**{k: v for k, v in d.items() if k in known})


def _device(d: dict) -> DeviceRow:
    known = DeviceRow.__dataclass_fields__.keys()
    return DeviceRow(**{k: v for k, v in d.items() if k in known})


def _gap(d: dict) -> Gap:
    known = Gap.__dataclass_fields__.keys()
    return Gap(**{k: v for k, v in d.items() if k in known})


def _evidence(d: dict) -> COIEvidence:
    known = COIEvidence.__dataclass_fields__.keys()
    return COIEvidence(**{k: v for k, v in d.items() if k in known})


def load_state(json_path: Path) -> dict:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    corpus = [_rec(r) for r in data.get("combined_corpus", [])]
    return {
        "indication": data["indication"],
        "cois": data["cois"],
        "corpus": corpus,
        "citations_index": build_citations_index(corpus),
        "devices": [_device(d) for d in data.get("combined_devices", [])],
        "gaps": [_gap(g) for g in data.get("combined_gaps", [])],
        "evidence": [_evidence(e) for e in data.get("combined_evidence", [])],
        "prisma_by_coi": data.get("prisma_by_coi", {}),
        "run_notes": data.get("run_notes", []),
        "failed_cois": data.get("failed_cois", {}),
    }


def main() -> None:
    here = Path(__file__).parent  # the deep_researchDHT folder

    json_arg = sys.argv[1] if len(sys.argv) > 1 else "outputs/als_landscape_dry_run.json"
    out_arg = sys.argv[2] if len(sys.argv) > 2 else "outputs"

    json_path = Path(json_arg)
    if not json_path.is_absolute():
        json_path = here / json_path

    out_dir = Path(out_arg)
    if not out_dir.is_absolute():
        out_dir = here / out_dir

    if not json_path.exists():
        found = "\n  ".join(str(p.relative_to(here)) for p in here.rglob("*.json"))
        raise SystemExit(
            f"Input JSON not found:\n  {json_path}\n\n"
            f".json files under {here}:\n  {found or '(none)'}"
        )

    st = load_state(json_path)

    # Surface any failed COIs as an explicit run note so they travel into the
    # document's Limitations section (they were only in the JSON before).
    run_notes = list(st["run_notes"])
    if st["failed_cois"]:
        run_notes.append(
            "The following COIs FAILED during retrieval/scoring and are absent "
            "from this landscape: "
            + "; ".join(f"{coi} ({err})" for coi, err in st["failed_cois"].items())
            + ". Their absence is a coverage gap, not a finding of 'no devices'."
        )

    result = assemble_report(
        indication=st["indication"],
        cois=st["cois"],
        corpus=st["corpus"],
        citations_index=st["citations_index"],
        devices=st["devices"],
        gaps=st["gaps"],
        evidence=st["evidence"],
        prisma_by_coi=st["prisma_by_coi"],
        criteria_render=render_methodology_block,
        out_dir=out_dir,
        run_notes=run_notes,
        synthesis_llm=None,            # deterministic synthesis (no gateway here)
        strict_citations=False,        # disclose orphans rather than block, for the demo
    )

    print("\n=== ASSEMBLY COMPLETE ===")
    print(f"  synthesis mode : {result['report_sections']['synthesis_mode']}")
    print(f"  citation precision: {result['verify_report']['citation_precision']:.2f} "
          f"({result['verify_report']['n_citations_verified']}/"
          f"{result['verify_report']['n_citations_total']} verified)")
    print(f"  figures        : {len(result['figures'])}")
    print(f"  document       : {result['final_report_path']}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
    print(">>> reached end of script", flush=True)