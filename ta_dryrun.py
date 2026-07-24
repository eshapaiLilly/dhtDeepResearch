"""
ta_dryRun.py — Therapeutic-Area-first COI discovery run.

Mirrors als_dryRun1.py's wiring (net_bootstrap first, real MCP dispatcher, the
two-dispatcher LLM API) but runs the NEW upstream stage: instead of taking COIs
as input and scoring devices, it takes an indication and produces a ranked,
evidence-grounded COI shortlist for human review.

Outputs (to outputs/ta_<indication>/):
  - ta_result.json        machine-readable candidates + scores + prisma + notes
  - ta_shortlist.md       human-review memo (2x2 matrix, per-COI evidence,
                          draft criteria.py stubs)

Next step is human, not automated: review ta_shortlist.md, accept COIs, paste
their draft stubs into criteria.py (or map to authored entries), then run the
existing coi_first pipeline (als_dryRun1.py-style) on the accepted COIs.

Usage:
    python ta_dryRun.py "ALS"
    python ta_dryRun.py "COPD"
"""
# Must be first — trusts the Zscaler proxy before anthropic/requests are used.
import net_bootstrap  # noqa: F401,E402

import json
import logging
import re
import sys
from pathlib import Path

from live_clients import real_mcp_dispatcher
from llm_client import make_lilly_analytical_dispatcher
from ta_landscape import run_ta_landscape, render_memo, result_as_json

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def main(indication: str) -> None:
    # real_mcp_dispatcher IS the dispatcher — a (tool_name, args) -> dict
    # callable — not a factory. Pass it by reference, exactly as
    # als_dryRun1.py does (build_graph(mcp=real_mcp_dispatcher)). retrieval's
    # identify() calls mcp(tool_name, args) internally.
    mcp = real_mcp_dispatcher

    # Analytical dispatcher (Opus, adaptive thinking, high effort) for BOTH the
    # extraction and scoring calls: these are open-ended, whole-corpus judgment
    # tasks — the same class as evidence.py, NOT the bounded per-record
    # classification screen.py does. One streamed high-effort call each.
    llm = make_lilly_analytical_dispatcher()

    log.info("=== TA-first COI discovery: %s ===", indication)
    result = run_ta_landscape(indication, mcp, llm)

    slug = re.sub(r"[^a-z0-9]+", "_", indication.lower()).strip("_")
    out_dir = Path("outputs") / f"ta_{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "ta_result.json").write_text(
        json.dumps(result_as_json(result), indent=2), encoding="utf-8")
    (out_dir / "ta_shortlist.md").write_text(render_memo(result), encoding="utf-8")

    rec = result.recommended()
    ws = result.white_space()
    log.info("--- done ---")
    log.info("corpus: %d records | candidates: %d | scored: %d",
             result.corpus_size, len(result.candidates), len(result.scores))
    log.info("recommended COIs (-> coi_first): %s", [s.coi for s in rec] or "none")
    log.info("white space (core, no DHT precedent): %s", [s.coi for s in ws] or "none")
    log.info("outputs: %s", out_dir)


if __name__ == "__main__":
    indication = sys.argv[1] if len(sys.argv) > 1 else "ALS"
    main(indication)