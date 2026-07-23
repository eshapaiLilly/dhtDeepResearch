"""
alzheimers_dryRun.py — Alzheimer's digital-endpoint landscape dry run across
multiple endpoint classes.

What this is, and how it differs from als_dryRun.py
------------------------------------------------------
Same workaround pattern as als_dryRun.py: graph.py's router hard-raises if
`cois` isn't length 1 (multi-COI Send()-based fan-out is a documented,
not-yet-built next step), so this script builds the graph ONCE and calls
app.invoke() once per endpoint CLASS in a plain Python loop — each COI here
is a class (e.g. "sleep_quality_quantity"), not a single narrow construct.

The "metrics under each class, with devices rated per metric" framing asked
for maps onto the EXISTING DeviceRow shape with no schema change: each
DeviceRow already carries `measures_supported` (the specific metrics that
device covers) and `v3_evidence` (tier + criteria_breakdown) within its
`coi` (here, its class). This script's only addition over als_dryRun.py is
in HOW the combined output is organized for reading — grouped by class, and
within each class, grouped again by metric so "what devices measure X" is
directly answerable — not a new analytical pass.

Known, disclosed gaps in this run (same caveats as als_dryRun.py)
--------------------------------------------------------------------
1. No recall_patterns.py — PI-branded companies and methods-section-only
   device naming are systematically undercounted. Partial mitigation:
   each class's positive_signals in criteria.py hand-encodes AD-specific
   vocabulary (e.g. "sundowning", "interdaily stability" for sleep) rather
   than relying on the class label alone.
2. No cross-class device dedup / company-index rollup — a device used in
   two classes (e.g. an IMU used for both motor_control and
   falls_balance_postural_control) appears as two separate DeviceRow
   entries, each correctly tagged with its own class, not merged.
3. Six classes were chosen to be non-overlapping in construct (sleep vs.
   activity vs. gait vs. speech/cognition vs. falls/balance vs. ADL), but
   coverage of "many classes" is inherently a judgment call, not an
   exhaustive taxonomy — additional classes (e.g. autonomic/cardiac,
   swallowing, driving) can be added to CLASSES below the same way ALS's
   COIs were added, by adding a new criteria.py entry.

All three notes are written into the output JSON's `run_notes` field.

Usage:
    python alzheimers_dryRun.py
"""
# Must be first — trusts the Zscaler proxy before anthropic/requests are used.
import net_bootstrap  # noqa: F401,E402

import json
import logging
from collections import defaultdict
from pathlib import Path

from graph import build_graph
from live_clients import real_mcp_dispatcher
from llm_client import make_lilly_llm_dispatcher, DEFAULT_SCREEN_MODEL, DEFAULT_SYNTHESIS_MODEL
from evidence import DEFAULT_SKILL_PATH
from retrieval import build_citations_index


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


INDICATION = "Alzheimer's disease"
CLASSES = [
    "sleep_quality_quantity",
    "physical_activity_adherence",
    "motor_control",
    "speech_language_cognition",
    "falls_balance_postural_control",
    "adl_functional_independence",
]

RUN_NOTES = [
    "recall_patterns.py (naming-fragmentation recovery for PI-branded "
    "companies and methods-section-only device naming) is not built. "
    "PI-branded speech/cognition platforms and methods-only-named "
    "actigraphs/balance platforms are systematically undercounted in this "
    "run.",
    "No cross-class device dedup or company-index rollup was performed. A "
    "device appearing under multiple classes (e.g. an IMU used for both "
    "motor_control and falls_balance_postural_control) is listed once per "
    "class as a separate DeviceRow, not merged into a single cross-class "
    "row.",
    "The 6 classes below were chosen for non-overlapping construct "
    "coverage, not as an exhaustive taxonomy of AD digital endpoints. "
    "Additional classes (e.g. autonomic/cardiac, swallowing, driving "
    "safety) can be added the same way — a new criteria.py entry plus a "
    "line in CLASSES.",
]


def _merge_devices(per_class_results: dict) -> list:
    return [d for result in per_class_results.values() for d in result.get("devices", [])]


def _merge_gaps(per_class_results: dict) -> list:
    return [g for result in per_class_results.values() for g in result.get("gaps", [])]


def _merge_evidence(per_class_results: dict) -> list:
    return [e for result in per_class_results.values() for e in result.get("evidence", [])]


def _merge_corpus(per_class_results: dict) -> list:
    """Union across classes, deduped by citation_id — the same trial can
    legitimately surface under more than one class's search."""
    by_id = {}
    for result in per_class_results.values():
        for r in result.get("corpus", []):
            by_id[r.citation_id] = r
    return list(by_id.values())


def _devices_by_metric(devices: list) -> dict:
    """Group a class's device_rows by the specific metric each one
    supports, so 'what devices measure X' is directly answerable without
    re-deriving it from measures_supported at read time."""
    by_metric = defaultdict(list)
    for d in devices:
        metrics = d.measures_supported or ["(metric not specified)"]
        for m in metrics:
            by_metric[m].append(d)
    return dict(by_metric)


def main() -> None:
    cheap_llm = make_lilly_llm_dispatcher(model=DEFAULT_SCREEN_MODEL)

    evidence_llm = None
    if DEFAULT_SKILL_PATH.exists():
        evidence_llm = make_lilly_llm_dispatcher(model=DEFAULT_SYNTHESIS_MODEL, max_tokens=16000)
    else:
        log.warning(
            "Skill file not found at %s — evidence node will be skipped "
            "(retrieval-only dry run) for every class.", DEFAULT_SKILL_PATH,
        )

    app = build_graph(
        mcp=real_mcp_dispatcher,
        screen_llm=cheap_llm,
        eligibility_llm=cheap_llm,
        evidence_llm=evidence_llm,
    )

    per_class_results: dict = {}
    per_class_by_metric: dict = {}

    for cls in CLASSES:
        log.info("=== Starting Alzheimer's dry run for class: %s ===", cls)
        initial_state = {
            "request": f"Digital endpoint landscape for {cls} in Alzheimer's disease",
            "indication": INDICATION,
            "cois": [cls],
            # direction defaults to "coi_first" if omitted — see graph.py
        }
        result = app.invoke(initial_state)
        per_class_results[cls] = result

        print(f"\n=== PRISMA FUNNEL [{cls}] ===")
        for k, v in result["prisma_counts"].items():
            print(f"  {k}: {v}")

        print(f"\n=== CORPUS [{cls}] ({len(result['corpus'])} records) ===")
        for r in result["corpus"][:10]:
            print(f"  [{r.citation_id}] {r.title[:80]}")
        if len(result["corpus"]) > 10:
            print(f"  ... and {len(result['corpus']) - 10} more")

        devices = result.get("devices", [])
        by_metric = _devices_by_metric(devices)
        per_class_by_metric[cls] = by_metric

        if devices:
            print(f"\n=== METRICS & DEVICES [{cls}] ({len(devices)} devices, {len(by_metric)} metrics) ===")
            for metric, ds in by_metric.items():
                print(f"  Metric: {metric}")
                for d in ds:
                    tier = d.v3_evidence.get("tier", "?")
                    print(f"    [{tier}] {d.device} ({d.manufacturer}) — {len(d.evidence_citations)} grounded citations")

        if result.get("gaps"):
            print(f"\n=== GAPS [{cls}] ({len(result['gaps'])}) ===")
            for g in result["gaps"]:
                print(f"  [{g.gap_id}] ({g.severity}) {g.description}")

    combined_corpus = _merge_corpus(per_class_results)
    combined_devices = _merge_devices(per_class_results)
    combined_gaps = _merge_gaps(per_class_results)
    combined_evidence = _merge_evidence(per_class_results)
    combined_citations_index = build_citations_index(combined_corpus)

    print("\n=== COMBINED ALZHEIMER'S DIGITAL ENDPOINT LANDSCAPE SUMMARY ===")
    print(f"  Combined corpus (deduped across classes): {len(combined_corpus)} records")
    print(f"  Combined devices: {len(combined_devices)}")
    print(f"  Combined gaps: {len(combined_gaps)}")
    print(f"  Class evidence summaries: {len(combined_evidence)}")
    for note in RUN_NOTES:
        print(f"  NOTE: {note}")

    out_path = Path("outputs") / "alzheimers_landscape_dry_run.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "indication": INDICATION,
            "classes": CLASSES,
            "run_notes": RUN_NOTES,
            "prisma_by_class": {
                cls: result["prisma_counts"] for cls, result in per_class_results.items()
            },
            # Per-class metric -> device rollup, the shape the request asked
            # for directly (device.__dict__ per row, grouped under its metric).
            "metrics_and_devices_by_class": {
                cls: {
                    metric: [d.__dict__ for d in ds]
                    for metric, ds in by_metric.items()
                }
                for cls, by_metric in per_class_by_metric.items()
            },
            "combined_corpus": [r.as_dict() for r in combined_corpus],
            "combined_citation_ids": sorted(combined_citations_index.keys()),
            "combined_devices": [d.__dict__ for d in combined_devices],
            "combined_gaps": [g.__dict__ for g in combined_gaps],
            "combined_evidence": [e.__dict__ for e in combined_evidence],
        }, f, indent=2, default=str)
    print(f"\nFull output written to {out_path}")


if __name__ == "__main__":
    main()
