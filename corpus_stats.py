"""
corpus_stats.py — descriptive statistics + figures for the final report.

What it produces
----------------
1. `corpus_stats`: a plain dict of distributions computed from the merged
   corpus / devices / evidence — source mix, tier distribution, evidence-
   strength distribution, per-COI inclusion counts. These feed both the
   report's prose ("of 20 devices scored, 3 reached Tier 1") and the figures.
2. `figures`: {png_path: caption}. Rendered with matplotlib (Agg backend, no
   display). Every figure caption states the exact counts it was built from,
   so a figure is never a floating claim — it traces back to the numbers in
   `corpus_stats`, which trace back to state.

Design rules
------------
- PRISMA is built from `prisma_by_coi` by SUMMING each stage across COIs.
  This is defensible because als_dryRun1.py's corpus merge dedupes by
  citation_id, so the *combined corpus* is deduped — but the PRISMA funnel
  reports per-COI search effort, which is legitimately additive (each COI ran
  its own identify→screen→eligibility). The caption says so explicitly rather
  than implying the numbers are a single deduped funnel.
- No figure is emitted for an empty distribution — an empty bar chart is worse
  than no chart. Missing figures are recorded in `corpus_stats["skipped_figures"]`
  so their absence is visible, not silent.
- Deterministic: same input → same numbers and same figures. No LLM.
"""
from __future__ import annotations

import logging
from collections import Counter, OrderedDict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — must be set before pyplot import
import matplotlib.pyplot as plt

from state import COIEvidence, DeviceRow, Record


log = logging.getLogger(__name__)

# A single muted palette so all figures in the document look like one set.
_PALETTE = ["#2F5C8A", "#3E7CB1", "#81A4CD", "#B8C5D6", "#D8DEE9"]
_TIER_COLOR = {
    "Tier 1": "#2F5C8A",
    "Tier 2": "#3E7CB1",
    "Tier 3": "#81A4CD",
    "Tier 4": "#B8C5D6",
}


def _tier_of(row: DeviceRow) -> str:
    t = (row.v3_evidence or {}).get("tier", "Unclassified")
    return t if t in _TIER_COLOR else "Unclassified"


def compute_corpus_stats(
    corpus: list[Record],
    devices: list[DeviceRow],
    evidence: list[COIEvidence],
    prisma_by_coi: dict[str, dict],
) -> dict:
    """Compute every distribution the report needs. Pure function."""
    # --- source mix of the merged (deduped) corpus ---
    source_mix = Counter(r.source for r in corpus)

    # --- tier distribution across all scored devices ---
    tier_dist = Counter(_tier_of(d) for d in devices)

    # --- evidence-strength distribution across COIs ---
    strength_dist = Counter(e.evidence_strength for e in evidence)

    # --- per-COI included count (from prisma) ---
    per_coi_included = {
        coi: counts.get("included", 0) for coi, counts in prisma_by_coi.items()
    }

    # --- summed PRISMA funnel across COIs ---
    funnel_stages = OrderedDict([
        ("identification_total", "Identified"),
        ("after_dedup", "After dedup"),
        ("screened", "Screened"),
        ("eligible", "Eligibility-assessed"),
        ("included", "Included"),
    ])
    prisma_funnel = OrderedDict()
    for key, label in funnel_stages.items():
        prisma_funnel[label] = sum(
            counts.get(key, 0) for counts in prisma_by_coi.values()
        )

    # --- summed screen-exclusion reasons across COIs ---
    screen_excl = Counter()
    for counts in prisma_by_coi.values():
        for reason, n in (counts.get("screen_excluded_reasons") or {}).items():
            screen_excl[reason] += n

    return {
        "n_corpus": len(corpus),
        "n_devices": len(devices),
        "n_cois": len(prisma_by_coi),
        "source_mix": dict(source_mix),
        "tier_distribution": dict(tier_dist),
        "evidence_strength_distribution": dict(strength_dist),
        "per_coi_included": per_coi_included,
        "prisma_funnel": dict(prisma_funnel),
        "screen_excluded_reasons": dict(screen_excl),
        "skipped_figures": [],  # filled by render_figures
    }


def render_figures(stats: dict, out_dir: Path) -> "OrderedDict[str, str]":
    """Render figures from precomputed stats. Returns {path: caption}, ordered.

    Empty distributions are skipped and recorded in stats['skipped_figures'].
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    figures: "OrderedDict[str, str]" = OrderedDict()

    # 1) PRISMA funnel (horizontal bars, descending)
    funnel = stats.get("prisma_funnel", {})
    if any(funnel.values()):
        path = out_dir / "prisma_funnel.png"
        labels = list(funnel.keys())
        vals = list(funnel.values())
        fig, ax = plt.subplots(figsize=(6.5, 3.2))
        ax.barh(range(len(labels)), vals, color=_PALETTE[1])
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        for i, v in enumerate(vals):
            ax.text(v, i, f" {v}", va="center", fontsize=9)
        ax.set_xlabel("Records")
        ax.set_title("PRISMA flow (summed across COIs)")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        figures[str(path)] = (
            f"Figure 1. PRISMA record flow, summed across {stats['n_cois']} COIs "
            f"(each COI ran an independent identify→screen→eligibility pass; the "
            f"combined corpus of {stats['n_corpus']} records is deduplicated by "
            f"citation ID, so per-stage totals reflect per-COI search effort, not "
            f"a single deduplicated funnel)."
        )
    else:
        stats["skipped_figures"].append("prisma_funnel (all stages zero)")

    # 2) Tier distribution
    tiers = stats.get("tier_distribution", {})
    if any(tiers.values()):
        path = out_dir / "tier_distribution.png"
        order = [t for t in ("Tier 1", "Tier 2", "Tier 3", "Tier 4", "Unclassified") if t in tiers]
        vals = [tiers[t] for t in order]
        colors = [_TIER_COLOR.get(t, "#999999") for t in order]
        fig, ax = plt.subplots(figsize=(5.5, 3.2))
        ax.bar(range(len(order)), vals, color=colors)
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(order, rotation=15, ha="right")
        for i, v in enumerate(vals):
            ax.text(i, v, str(v), ha="center", va="bottom", fontsize=9)
        ax.set_ylabel("Devices")
        ax.set_title("Device tier distribution")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        figures[str(path)] = (
            f"Figure 2. Tier assignment across all {stats['n_devices']} scored "
            f"devices. Tiers follow the dht-landscape-scout rubric (Progress / "
            f"Diligence / Monitor / Watch)."
        )
    else:
        stats["skipped_figures"].append("tier_distribution (no scored devices)")

    # 3) Source mix
    smix = stats.get("source_mix", {})
    if any(smix.values()):
        path = out_dir / "source_mix.png"
        labels = list(smix.keys())
        vals = list(smix.values())
        fig, ax = plt.subplots(figsize=(4.5, 3.2))
        ax.pie(vals, labels=labels, autopct=lambda p: f"{p*sum(vals)/100:.0f}",
               colors=_PALETTE, startangle=90)
        ax.set_title("Corpus by source")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        figures[str(path)] = (
            f"Figure 3. Provenance of the {stats['n_corpus']}-record combined "
            f"corpus by retrieval source."
        )
    else:
        stats["skipped_figures"].append("source_mix (empty corpus)")

    log.info("corpus_stats: rendered %d figure(s), skipped %d",
             len(figures), len(stats["skipped_figures"]))
    return figures


def run_corpus_stats(
    corpus: list[Record],
    devices: list[DeviceRow],
    evidence: list[COIEvidence],
    prisma_by_coi: dict[str, dict],
    out_dir: Path,
) -> tuple[dict, "OrderedDict[str, str]"]:
    """Compute stats then render figures. Returns (stats, figures)."""
    stats = compute_corpus_stats(corpus, devices, evidence, prisma_by_coi)
    figures = render_figures(stats, out_dir)
    return stats, figures


__all__ = ["compute_corpus_stats", "render_figures", "run_corpus_stats"]