"""
run_mvpa_dry_run.py — the actual entry point. Run this on your Lilly machine.

What this needs, and why
--------------------------
1. `lilly-code login` already done (this script calls `lilly-code token`
   under the hood, same as your original base_node.py — see llm_client.py).
2. Network access to clinicaltrials.gov and eutils.ncbi.nlm.nih.gov (both
   public APIs, no auth needed — see live_clients.py). If you're behind
   Zscaler, net_bootstrap (imported first, below) handles the TLS trust
   the same way it did in the original dht_pipeline build.
3. Optionally, an NCBI_API_KEY environment variable (free, instant, via an
   NCBI account) — raises the PubMed rate limit from ~3 to ~10 req/sec.
   Without it, live_clients.py's retry-with-backoff handles the occasional
   429 automatically; it just means slower runs at larger corpus sizes.

Usage:
    python run_mvpa_dry_run.py
"""
# Must be first — trusts the Zscaler proxy before anthropic/requests are used.
import net_bootstrap  # noqa: F401,E402

import json
import logging
from pathlib import Path

from graph import build_graph
from live_clients import real_mcp_dispatcher
from llm_client import make_lilly_llm_dispatcher, DEFAULT_SCREEN_MODEL, DEFAULT_SYNTHESIS_MODEL
from evidence import DEFAULT_SKILL_PATH


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    # screen and eligibility use the cheap/fast model; evidence needs
    # Sonnet 4.6, since it's a whole-corpus analytical call, not a
    # per-record classifier — see the model-tier table from earlier.
    cheap_llm = make_lilly_llm_dispatcher(model=DEFAULT_SCREEN_MODEL)

    # Evidence node is skipped entirely if the skill file isn't staged yet
    # at skills/dht-landscape-scout/SKILL.md — the graph just ends after
    # eligibility in that case (retrieval-only dry run), rather than
    # failing. Stage the skill file to get the full analytical pass.
    evidence_llm = None
    if DEFAULT_SKILL_PATH.exists():
        # Higher max_tokens than screen/eligibility's default — the
        # evidence node's JSON output (device rows + gap log for a large
        # corpus) needs more room than a per-record classifier decision.
        # Raised from 8000 after a real run produced an empty response
        # (see llm_client._response_text's diagnostic raise) — if this
        # still happens, the diagnostic will show stop_reason and content
        # block types so we know definitively whether it's a token-budget
        # issue or something else (e.g. a gateway-side reasoning mode).
        evidence_llm = make_lilly_llm_dispatcher(model=DEFAULT_SYNTHESIS_MODEL, max_tokens=16000)
    else:
        log.warning(
            "Skill file not found at %s — evidence node will be skipped "
            "(retrieval-only dry run). Stage the skill file to run the "
            "full analytical pass.", DEFAULT_SKILL_PATH,
        )

    app = build_graph(
        mcp=real_mcp_dispatcher,
        screen_llm=cheap_llm,
        eligibility_llm=cheap_llm,
        evidence_llm=evidence_llm,
    )

    initial_state = {
        "request": "MVPA landscape for COPD",
        "indication": "COPD",
        "cois": ["moderate_to_vigorous_physical_activity"],
        # direction defaults to "coi_first" if omitted — see graph.py
    }

    log.info("Starting MVPA/COPD dry run...")
    result = app.invoke(initial_state)

    print("\n=== PRISMA FUNNEL ===")
    for k, v in result["prisma_counts"].items():
        print(f"  {k}: {v}")

    print(f"\n=== FINAL CORPUS ({len(result['corpus'])} records) ===")
    for r in result["corpus"][:20]:
        print(f"  [{r.citation_id}] {r.title[:80]}")
    if len(result["corpus"]) > 20:
        print(f"  ... and {len(result['corpus']) - 20} more")

    if result.get("devices"):
        print(f"\n=== DEVICE LANDSCAPE ({len(result['devices'])} devices) ===")
        for d in result["devices"]:
            tier = d.v3_evidence.get("tier", "?")
            print(f"  [{tier}] {d.device} ({d.manufacturer}) — {len(d.evidence_citations)} grounded citations")

    if result.get("gaps"):
        print(f"\n=== GAP LOG ({len(result['gaps'])} gaps) ===")
        for g in result["gaps"]:
            print(f"  [{g.gap_id}] ({g.severity}) {g.description}")

    if result.get("evidence"):
        ce = result["evidence"][0]
        print(f"\n=== COI EVIDENCE SUMMARY ===")
        print(f"  Strength: {ce.evidence_strength} | Endpoint role: {ce.endpoint_role_recommendation}")
        print(f"  Gates: {ce.gate_verdicts}")

    # Dump everything to disk for inspection / the next step
    # (corpus_stats.py's figures will read this shape).
    out_path = Path("outputs") / "mvpa_copd_dry_run.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "prisma_counts": result["prisma_counts"],
            "corpus": [r.as_dict() for r in result["corpus"]],
            "devices": [d.__dict__ for d in result.get("devices", [])],
            "gaps": [g.__dict__ for g in result.get("gaps", [])],
            "evidence": [e.__dict__ for e in result.get("evidence", [])],
        }, f, indent=2, default=str)
    print(f"\nFull output written to {out_path}")


if __name__ == "__main__":
    main()