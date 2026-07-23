"""
als_dryRun.py — ALS device landscape dry run across 5 COIs.

What this is, and how it differs from mvpa_dryRun.py
------------------------------------------------------
mvpa_dryRun.py runs the graph once, for one COI. This script runs the SAME
graph — unmodified — once per COI, concurrently in a thread pool (each invoke is independent —
no checkpointer, so no state leaks between COI runs), then merges the
5 per-COI results into one combined landscape. This is a deliberate
workaround, not a pipeline feature: graph.py's router node hard-raises if
`cois` isn't length 1 (multi-COI Send()-based fan-out is a documented,
not-yet-built next step — see graph.py's module docstring). Looping
app.invoke() per COI needs no change to graph.py's router contract, because
each invoke() call is independent (no checkpointer is passed to build_graph,
so no state leaks between COI runs).

Model wiring (updated for llm_client's two-dispatcher API)
-------------------------------------------------------------
llm_client.py no longer exposes one model-agnostic make_lilly_llm_dispatcher().
It exposes two purpose-built builders instead:
  - make_lilly_classifier_dispatcher(): thinking disabled, bounded output —
    for screen.py's per-record batch classification.
  - make_lilly_analytical_dispatcher(): adaptive thinking at high effort,
    max_tokens pinned to the model's synchronous ceiling (128k) — for any
    node doing real cross-record judgment.

eligibility.py is a re-adjudication gate (enrich → re-judge → freeze the
corpus), not a cheap pass-through, so it now gets its own analytical
dispatcher rather than sharing the classifier one screen.py uses. That's a
real behavior change from the previous cheap_llm-for-both wiring, not just
a rename — eligibility decisions should measurably improve.

Known, disclosed gaps in this run (carried over honestly, not papered over)
-----------------------------------------------------------------------------
1. No recall_patterns.py. The dht-landscape-scout skill's naming-fragmentation
   recovery (PI-branded companies, methods-section-only device naming) isn't
   built — its own Open Questions ledger calls this "very likely a major
   reason the original ALS report was good." This run WILL undercount
   PI-branded speech/oculomotor platforms and methods-only-named
   dynamometers/spirometers relative to a standalone-skill run. Partial
   mitigation: each COI's positive_signals in criteria.py hand-encodes the
   ALS-specific sub-construct vocabulary the skill doc names explicitly
   (e.g. range_of_motion → "reachable workspace", "head drop", "cervical
   range of motion") instead of relying on the label alone.
2. No cross-COI device dedup / company-index rollup. A device that shows up
   under two COIs (e.g. an IMU used for both range_of_motion and muscle
   function) appears as two separate DeviceRow entries, each correctly
   tagged with its own `coi`, rather than merged into one row. Building the
   "broad modality landscape" company-index rollup the skill doc describes
   is a manual follow-up step, not automated here.

Both notes are written into the output JSON's `run_notes` field, not just
logged, so they travel with the report.

Usage:
    python als_dryRun.py
"""
# Must be first — trusts the Zscaler proxy before anthropic/requests are used.
import net_bootstrap  # noqa: F401,E402

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from graph import build_graph
from live_clients import real_mcp_dispatcher
from llm_client import make_lilly_classifier_dispatcher, make_lilly_analytical_dispatcher
from evidence import DEFAULT_SKILL_PATH
from retrieval import build_citations_index


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


INDICATION = "ALS"
COIS = [
    "bulbar_speech",
    "range_of_motion",
    "muscle_function",
    "respiratory_function",
    "oculomotor",
]

RUN_NOTES = [
    "recall_patterns.py (naming-fragmentation recovery for PI-branded "
    "companies and methods-section-only device naming) is not built. Per "
    "dht-landscape-scout SKILL.md's Open Questions ledger, this is likely a "
    "major source of recall gap for ALS specifically. PI-branded speech/"
    "oculomotor platforms and methods-only-named dynamometers/spirometers "
    "are systematically undercounted in this run.",
    "No cross-COI device dedup or company-index rollup was performed. A "
    "device appearing under multiple COIs is listed once per COI as a "
    "separate DeviceRow, not merged into a single cross-COI row.",
]


def _merge_devices(per_coi_results: dict) -> list:
    return [d for result in per_coi_results.values() for d in result.get("devices", [])]


def _merge_gaps(per_coi_results: dict) -> list:
    return [g for result in per_coi_results.values() for g in result.get("gaps", [])]


def _merge_evidence(per_coi_results: dict) -> list:
    return [e for result in per_coi_results.values() for e in result.get("evidence", [])]


def _merge_corpus(per_coi_results: dict) -> list:
    """Union across COIs, deduped by citation_id — the same trial can
    legitimately surface under more than one COI's search."""
    by_id = {}
    for result in per_coi_results.values():
        for r in result.get("corpus", []):
            by_id[r.citation_id] = r
    return list(by_id.values())


def main() -> None:
    # screen.py: classifier dispatcher — thinking off, bounded JSON output.
    screen_llm = make_lilly_classifier_dispatcher()

    # eligibility.py: analytical dispatcher, still Opus 4.8 (fuller-text
    # judgment genuinely benefits from the stronger model), but now with
    # thinking DISABLED. Reading eligibility.py's own system prompt: this
    # node's task is a bounded per-record include/exclude classification
    # (structurally the same shape as screen.py's task, just on fuller
    # text) — NOT the open-ended cross-record reasoning evidence.py does.
    # Adaptive thinking, even at effort="medium", was spending wall-clock on
    # deliberation this task doesn't need; at ~20+ batches per COI that was a
    # dominant cost in the >1hr run. thinking=False keeps Opus's judgment,
    # removes the thinking tax, and (at modest max_tokens) drops to a plain
    # non-streaming call under the SDK's 10-minute guard. If eligibility
    # quality holds, dropping to make_lilly_classifier_dispatcher() (Sonnet 5)
    # would be cheaper still — A/B before/after against Blackletter's counts.
    # evidence_llm below keeps thinking ON at effort="high" (its default)
    # since whole-corpus tiering/gap-finding is exactly what benefits from it.
    eligibility_llm = make_lilly_analytical_dispatcher(thinking=False, max_tokens=16_000)

    # evidence.py: analytical dispatcher, only if the skill file is staged.
    # No max_tokens override here — the analytical dispatcher already
    # defaults to 128k (the synchronous ceiling), which replaces the old
    # hardcoded 16000 that was truncating whole-corpus tiering calls.
    evidence_llm = None
    if DEFAULT_SKILL_PATH.exists():
        evidence_llm = make_lilly_analytical_dispatcher()
    else:
        log.warning(
            "Skill file not found at %s — evidence node will be skipped "
            "(retrieval-only dry run) for every COI.", DEFAULT_SKILL_PATH,
        )

    app = build_graph(
        mcp=real_mcp_dispatcher,
        screen_llm=screen_llm,
        eligibility_llm=eligibility_llm,
        evidence_llm=evidence_llm,
    )

    per_coi_results: dict = {}
    failed_cois: dict[str, str] = {}  # coi -> error message, for the report's transparency

    out_path = Path("outputs") / "als_landscape_dry_run.json"
    out_path.parent.mkdir(exist_ok=True)

    def _write_output() -> None:
        """Write current progress to disk. Called after EVERY COI (success
        or failure), not just once at the end — a live run previously lost
        an entire COI's already-completed, already-paid-for screen +
        eligibility work when evidence crashed on a later COI, because the
        only write happened after the full loop finished. This makes that
        impossible: whatever has completed so far is always on disk."""
        combined_corpus = _merge_corpus(per_coi_results)
        combined_devices = _merge_devices(per_coi_results)
        combined_gaps = _merge_gaps(per_coi_results)
        combined_evidence = _merge_evidence(per_coi_results)
        combined_citations_index = build_citations_index(combined_corpus)
        with open(out_path, "w") as f:
            json.dump({
                "indication": INDICATION,
                "cois": COIS,
                "run_notes": RUN_NOTES,
                "failed_cois": failed_cois,
                "prisma_by_coi": {
                    coi: result["prisma_counts"] for coi, result in per_coi_results.items()
                },
                "combined_corpus": [r.as_dict() for r in combined_corpus],
                "combined_citation_ids": sorted(combined_citations_index.keys()),
                "combined_devices": [d.__dict__ for d in combined_devices],
                "combined_gaps": [g.__dict__ for g in combined_gaps],
                "combined_evidence": [e.__dict__ for e in combined_evidence],
            }, f, indent=2, default=str)

    # COIs run concurrently. This is safe TODAY, without touching graph.py's
    # router contract: build_graph is called with no checkpointer, so each
    # app.invoke() is fully independent state (the module docstring's whole
    # rationale for the per-COI loop). We're just running those independent
    # invokes in parallel instead of one at a time — the proper Send()-based
    # fan-out remains the documented next step in graph.py.
    #
    # Concurrency safety: `lock` guards every mutation of per_coi_results /
    # failed_cois and every _write_output() call (which READS per_coi_results
    # to build the combined output) and the per-COI print block (so summaries
    # don't interleave). NCBI request rate stays capped regardless of how many
    # COIs run at once, because live_clients._throttle() holds a single shared
    # lock — extra threads just queue on the same pacing. Total concurrent
    # gateway LLM calls ≈ COI_WORKERS * batch_workers (see screen/eligibility);
    # lower COI_WORKERS if the Lilly gateway rate-limits.
    lock = threading.Lock()
    COI_WORKERS = min(len(COIS), 5)

    def _process_coi(coi: str) -> None:
        log.info("=== Starting ALS dry run for COI: %s ===", coi)
        initial_state = {
            "request": f"DHT device landscape for {coi} in ALS",
            "indication": INDICATION,
            "cois": [coi],
            # direction defaults to "coi_first" if omitted — see graph.py
        }

        try:
            result = app.invoke(initial_state)
        except Exception as e:  # noqa: BLE001 — one COI's failure must not
            # take down the others. A live run hit exactly this: a single
            # httpx.ReadTimeout on evidence's streamed call for one COI killed
            # the whole script, discarding screen+eligibility results already
            # completed (and paid for) on other COIs.
            log.error("=== COI %s FAILED: %s: %s ===", coi, type(e).__name__, e)
            with lock:
                failed_cois[coi] = f"{type(e).__name__}: {e}"
                _write_output()  # save whatever's completed so far
            return

        with lock:
            per_coi_results[coi] = result
            _write_output()  # incremental save — persist each COI immediately

            print(f"\n=== PRISMA FUNNEL [{coi}] ===")
            for k, v in result["prisma_counts"].items():
                print(f"  {k}: {v}")

            print(f"\n=== CORPUS [{coi}] ({len(result['corpus'])} records) ===")
            for r in result["corpus"][:10]:
                print(f"  [{r.citation_id}] {r.title[:80]}")
            if len(result["corpus"]) > 10:
                print(f"  ... and {len(result['corpus']) - 10} more")

            if result.get("devices"):
                print(f"\n=== DEVICES [{coi}] ({len(result['devices'])}) ===")
                for d in result["devices"]:
                    tier = d.v3_evidence.get("tier", "?")
                    print(f"  [{tier}] {d.device} ({d.manufacturer}) — "
                          f"{len(d.evidence_citations)} grounded citations")

            if result.get("gaps"):
                print(f"\n=== GAPS [{coi}] ({len(result['gaps'])}) ===")
                for g in result["gaps"]:
                    print(f"  [{g.gap_id}] ({g.severity}) {g.description}")

    with ThreadPoolExecutor(max_workers=COI_WORKERS) as pool:
        list(pool.map(_process_coi, COIS))

    combined_corpus = _merge_corpus(per_coi_results)
    combined_devices = _merge_devices(per_coi_results)
    combined_gaps = _merge_gaps(per_coi_results)
    combined_evidence = _merge_evidence(per_coi_results)

    print("\n=== COMBINED ALS LANDSCAPE SUMMARY ===")
    print(f"  Combined corpus (deduped across COIs): {len(combined_corpus)} records")
    print(f"  Combined devices: {len(combined_devices)}")
    print(f"  Combined gaps: {len(combined_gaps)}")
    print(f"  COI evidence summaries: {len(combined_evidence)}")
    if failed_cois:
        print(f"  FAILED COIs ({len(failed_cois)}): {list(failed_cois.keys())} — "
              f"see run_notes/failed_cois in the output JSON; rerun these individually.")
    for note in RUN_NOTES:
        print(f"  NOTE: {note}")

    _write_output()  # final write — redundant with the last incremental save, kept for clarity
    print(f"\nFull output written to {out_path}")


if __name__ == "__main__":
    main()