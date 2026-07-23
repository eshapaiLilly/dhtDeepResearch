"""
synthesize.py — turn assembled structured state into narrative report sections.

This is where "research insight" becomes prose. Everything upstream produced
tables, tiers, and gap objects; this node writes the connective narrative a
reader actually reads: an executive summary, per-COI interpretation, and
cross-cutting recommendations. The device tables, gap log, PRISMA figures, and
methodology are rendered directly from state by build_docx and do NOT depend on
this node — so if synthesis degrades, the document is thinner prose over the
same hard data, never missing data.

Two paths, same output shape
----------------------------
`run_synthesis(..., llm=<dispatcher>)`  → LLM writes the prose (Opus analytical
    dispatcher; optionally the dht-str skill as system prompt for house style).
`run_synthesis(..., llm=None)`          → deterministic template writes the
    prose from the same structured state.

Both return the SAME `report_sections` dict shape, so build_docx is identical
either way. The deterministic path exists for three reasons:
  1. It lets the whole document pipeline be built, run, and unit-tested with no
     Lilly gateway access at all (this is how the sample doc in this repo was
     produced).
  2. It is the graceful-degradation fallback: if the gateway call fails or the
     JSON won't parse, the pipeline still ships a real, accurate — if drier —
     document rather than crashing, matching the codebase's disclose-don't-crash
     posture. The degradation is recorded in report_sections["synthesis_mode"].
  3. It is a factual floor: the template only ever restates numbers already in
     state, so it cannot hallucinate. The LLM path adds interpretation on top.

Grounding
---------
The LLM path is constrained the same way evidence.py constrains scoring: it may
only cite citation_ids present in the corpus, and its output is checked by
verify.py afterward. The deterministic path cites only what's already in the
structured rows, so it is orphan-free by construction.
"""
from __future__ import annotations

import json
import logging
from collections import OrderedDict
from pathlib import Path

from state import COIEvidence, DeviceRow, Gap


log = logging.getLogger(__name__)

LLMDispatcher = "Callable[[str, str], str]"  # documented; not imported to keep this leaf-light

# Optional house-style system prompt. If the dht-str skill is staged, we load
# it so LLM synthesis matches the STR report voice; absence is non-fatal.
DEFAULT_STR_SKILL_PATH = Path(__file__).parent / "skills" / "dht-str" / "SKILL.md"


# ─────────────────────────────────────────────────────────────────────────────
# Tier bucketing shared by both paths
# ─────────────────────────────────────────────────────────────────────────────

_TIER_ORDER = ["Tier 1", "Tier 2", "Tier 3", "Tier 4"]
_TIER_NAME = {
    "Tier 1": "Progress", "Tier 2": "Diligence",
    "Tier 3": "Monitor", "Tier 4": "Watch",
}


def _tier(row: DeviceRow) -> str:
    return (row.v3_evidence or {}).get("tier", "Unclassified")


def _devices_by_coi(devices: list[DeviceRow]) -> "OrderedDict[str, list[DeviceRow]]":
    out: "OrderedDict[str, list[DeviceRow]]" = OrderedDict()
    for d in devices:
        out.setdefault(d.coi, []).append(d)
    # within each COI, order by tier then by device name
    for coi in out:
        out[coi].sort(key=lambda d: (_TIER_ORDER.index(_tier(d)) if _tier(d) in _TIER_ORDER else 99, d.device))
    return out


def _tier_counts(rows: list[DeviceRow]) -> "OrderedDict[str, int]":
    c: "OrderedDict[str, int]" = OrderedDict((t, 0) for t in _TIER_ORDER)
    for r in rows:
        t = _tier(r)
        if t in c:
            c[t] += 1
    return c


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic synthesis (the factual floor / fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _det_executive_summary(
    indication: str,
    cois: list[str],
    devices: list[DeviceRow],
    evidence: list[COIEvidence],
    gaps: list[Gap],
    stats: dict,
) -> str:
    by_coi = _devices_by_coi(devices)
    tier_dist = stats.get("tier_distribution", {})
    n_t1 = tier_dist.get("Tier 1", 0)
    n_t2 = tier_dist.get("Tier 2", 0)
    n_blocking = sum(1 for g in gaps if g.severity == "blocking")

    lead = (
        f"This landscape assesses digital health technologies (DHTs) for "
        f"{len(cois)} concept(s) of interest in {indication}: "
        f"{', '.join(c.replace('_', ' ') for c in cois)}. "
        f"A combined, de-duplicated corpus of {stats.get('n_corpus', 0)} records "
        f"across {stats.get('n_cois', 0)} independent COI searches yielded "
        f"{stats.get('n_devices', 0)} devices that met the scoring threshold."
    )

    posture = (
        f"Of the scored devices, {n_t1} reached Tier 1 (Progress) and {n_t2} "
        f"reached Tier 2 (Diligence); the remainder sit in Monitor/Watch. "
        if (n_t1 + n_t2) else
        "No device reached Tier 1 or Tier 2, which for a nascent set of COIs "
        "reflects the best-available-candidate framing rather than a failure "
        "state — the strongest current signals are identified below for pilot "
        "consideration. "
    )

    strengths = []
    for e in evidence:
        strengths.append(f"{e.coi.replace('_', ' ')} ({e.evidence_strength.lower()})")
    strength_line = (
        "Per-COI evidence strength: " + "; ".join(strengths) + ". "
        if strengths else ""
    )

    gaps_line = (
        f"{n_blocking} gap(s) are rated blocking and must be resolved before "
        f"any primary-endpoint use. "
        if n_blocking else
        "No blocking gaps were identified, though diligence items remain. "
    )

    return lead + " " + posture + strength_line + gaps_line


def _det_coi_narrative(
    coi: str,
    rows: list[DeviceRow],
    coi_evidence: COIEvidence | None,
    gaps: list[Gap],
) -> dict:
    tc = _tier_counts(rows)
    leaders = [r for r in rows if _tier(r) in ("Tier 1", "Tier 2")]
    coi_gaps = [g for g in gaps if coi in g.affected_cois]

    paras: list[str] = []
    if coi_evidence and coi_evidence.clinical_definition:
        paras.append(coi_evidence.clinical_definition)

    tier_summary = ", ".join(
        f"{n} at {t} ({_TIER_NAME[t]})" for t, n in tc.items() if n
    ) or "no devices reached a scored tier"
    paras.append(
        f"{len(rows)} device(s) were scored for this COI: {tier_summary}."
    )

    if leaders:
        lead_names = "; ".join(
            f"{r.device} ({r.manufacturer}, {_tier(r)})" for r in leaders
        )
        paras.append(f"Leading candidate(s): {lead_names}.")
    else:
        paras.append(
            "No device reached Tier 1/2. The strongest current signal is "
            + (rows[0].device if rows else "not established in this corpus")
            + "."
        )

    if coi_evidence:
        verds = "; ".join(f"{k}: {v}" for k, v in (coi_evidence.gate_verdicts or {}).items())
        if verds:
            paras.append(f"Gate verdicts — {verds}. "
                         f"Recommended endpoint role: "
                         f"{coi_evidence.endpoint_role_recommendation.lower()}.")

    if coi_gaps:
        block = [g for g in coi_gaps if g.severity == "blocking"]
        if block:
            paras.append(
                "Blocking gap(s): " + "; ".join(g.description for g in block[:3])
                + ("." if len(block) <= 3 else f"; and {len(block)-3} more.")
            )

    return {"coi": coi, "heading": coi.replace("_", " ").title(), "paragraphs": paras}


def _det_recommendations(
    devices: list[DeviceRow],
    evidence: list[COIEvidence],
    gaps: list[Gap],
) -> list[str]:
    recs: list[str] = []
    by_coi = _devices_by_coi(devices)
    for coi, rows in by_coi.items():
        leaders = [r for r in rows if _tier(r) in ("Tier 1", "Tier 2")]
        if leaders:
            top = leaders[0]
            recs.append(
                f"{coi.replace('_', ' ').title()}: advance {top.device} "
                f"({top.manufacturer}) — {_tier(top)}. "
                + (f"Key limitation to close: {top.limitations}" if top.limitations else "")
            )
        else:
            recs.append(
                f"{coi.replace('_', ' ').title()}: no trial-ready device; treat "
                f"the strongest current signal as an exploratory pilot candidate "
                f"and prioritize the blocking gaps below."
            )
    blocking = [g for g in gaps if g.severity == "blocking"]
    if blocking:
        recs.append(
            "Cross-cutting: resolve blocking gaps before any primary-endpoint "
            "commitment — most concern missing longitudinal / MID data or "
            "unpublished vendor trial results (see Gap Log)."
        )
    return recs


def synthesize_deterministic(
    indication: str,
    cois: list[str],
    devices: list[DeviceRow],
    evidence: list[COIEvidence],
    gaps: list[Gap],
    stats: dict,
    run_notes: list[str] | None = None,
) -> dict:
    """Build report_sections from state with no LLM. Cannot hallucinate."""
    by_coi = _devices_by_coi(devices)
    ev_by_coi = {e.coi: e for e in evidence}

    coi_sections = [
        _det_coi_narrative(coi, rows, ev_by_coi.get(coi), gaps)
        for coi, rows in by_coi.items()
    ]

    return {
        "synthesis_mode": "deterministic",
        "title": f"DHT Landscape Review — {indication}",
        "executive_summary": _det_executive_summary(
            indication, cois, devices, evidence, gaps, stats
        ),
        "coi_sections": coi_sections,
        "recommendations": _det_recommendations(devices, evidence, gaps),
        "run_notes": run_notes or [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM synthesis (interpretation on top of the factual floor)
# ─────────────────────────────────────────────────────────────────────────────

_SYNTH_CONTRACT = """\
You are writing the narrative sections of a regulatory-grade DHT landscape
review. You are given the FULLY SCORED, TIERED state as JSON: per-COI evidence
verdicts, per-device tier assignments, a consolidated gap log, and corpus
statistics. The device tables, gap log, and figures are rendered separately
from the same state — your job is the INTERPRETIVE PROSE around them.

Hard rules:
- You may ONLY cite citation_ids that appear in the state you are given. Never
  invent an NCT number, PMID, or DOI. If you cannot ground a claim, state it
  qualitatively without a citation.
- Do not contradict the tier assignments or gate verdicts in the state. You
  interpret them; you do not overturn them.
- Distinguish diagnostic accuracy from longitudinal / trial-endpoint readiness,
  per the framework. A device good at HC-vs-patient separation is NOT thereby
  endpoint-ready.
- Be specific and quantitative. "Strong evidence" is not output; "Tier 1 on 3
  of 3 gate verdicts with a cleared predicate (K-number in state)" is.

Return ONLY this JSON (no prose outside it, no markdown fences):
{
  "executive_summary": "<3-5 sentence synthesis: what the landscape shows, how mature it is, the headline recommendation>",
  "coi_sections": [
    {"coi": "<coi key>", "heading": "<Title Case>", "paragraphs": ["<para>", "..."]}
  ],
  "recommendations": ["<actionable, per-COI or cross-cutting recommendation>", "..."]
}
"""


def _load_str_style(path: Path = DEFAULT_STR_SKILL_PATH) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8") + "\n\n---\n\n" + _SYNTH_CONTRACT
    return _SYNTH_CONTRACT


def _state_as_json(
    indication: str, cois: list[str], devices: list[DeviceRow],
    evidence: list[COIEvidence], gaps: list[Gap], stats: dict,
) -> str:
    return json.dumps({
        "indication": indication,
        "cois": cois,
        "corpus_stats": stats,
        "coi_evidence": [e.__dict__ for e in evidence],
        "devices": [d.__dict__ for d in devices],
        "gaps": [g.__dict__ for g in gaps],
    }, default=str, indent=2)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def run_synthesis(
    indication: str,
    cois: list[str],
    devices: list[DeviceRow],
    evidence: list[COIEvidence],
    gaps: list[Gap],
    stats: dict,
    llm=None,                     # LLMDispatcher | None
    run_notes: list[str] | None = None,
    str_skill_path: Path = DEFAULT_STR_SKILL_PATH,
) -> dict:
    """Produce report_sections. Uses the LLM if given, else the deterministic
    template. On ANY LLM failure, falls back to deterministic and records it."""
    if llm is None:
        log.info("synthesize: no LLM dispatcher — using deterministic synthesis")
        return synthesize_deterministic(
            indication, cois, devices, evidence, gaps, stats, run_notes
        )

    system = _load_str_style(str_skill_path)
    user = _state_as_json(indication, cois, devices, evidence, gaps, stats)

    try:
        raw = llm(system, user)
        payload = json.loads(_strip_fences(raw))
        # Merge LLM prose with the deterministic scaffold so any missing key is
        # backfilled from the factual floor rather than dropped.
        floor = synthesize_deterministic(
            indication, cois, devices, evidence, gaps, stats, run_notes
        )
        floor.update({
            "synthesis_mode": "llm",
            "executive_summary": payload.get("executive_summary") or floor["executive_summary"],
            "coi_sections": payload.get("coi_sections") or floor["coi_sections"],
            "recommendations": payload.get("recommendations") or floor["recommendations"],
        })
        log.info("synthesize: LLM synthesis parsed and merged with factual floor")
        return floor
    except Exception as e:  # noqa: BLE001 — any failure degrades to deterministic
        log.error("synthesize: LLM path failed (%s: %s) — falling back to "
                  "deterministic synthesis", type(e).__name__, e)
        floor = synthesize_deterministic(
            indication, cois, devices, evidence, gaps, stats, run_notes
        )
        floor["synthesis_mode"] = "deterministic_fallback"
        floor["synthesis_error"] = f"{type(e).__name__}: {e}"
        return floor


__all__ = [
    "run_synthesis",
    "synthesize_deterministic",
    "DEFAULT_STR_SKILL_PATH",
]