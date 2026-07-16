"""
criteria.py — per-COI inclusion / exclusion criteria for PRISMA screening.

What this module is
-------------------
A pure-config module. No LLM, no I/O. Every criterion is a machine-readable
row that (a) gets fed into the screening prompt as the rubric Claude applies,
and (b) gets rendered into the final report's Methodology section verbatim so
a reviewer can reproduce the screen.

Why it matters
--------------
Circadic's report (Section 1.3.2) lists 4 inclusion + 4 exclusion criteria
that make their screen defensible. Without this file, "why did that study get
excluded?" has no answer. With it, every excluded record carries a reason
code that traces back to a specific criterion here.

Structure
---------
Each COI has an EligibilityCriteria bundle. Global criteria (year range,
device-required-in-abstract) apply to all COIs; per-COI criteria narrow
further (e.g., for MVPA: outcome must involve activity minutes, energy
expenditure, or accelerometer-derived metrics).

Adding a new COI = add a new key to `CRITERIA` below. Screening node reads
this dict, no other changes needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ExclusionCode = Literal[
    "wrong_population",      # not the target indication or population
    "wrong_intervention",    # no device / no digital endpoint mentioned
    "wrong_outcome",         # doesn't measure this COI
    "wrong_study_type",      # invasive/implantable, in-clinic only, etc.
    "out_of_date_range",     # published/registered outside window
    "underpowered",          # N too small, no stat-sig findings
    "duplicate",             # caught during dedup but flagged in screen too
    "insufficient_metadata", # abstract/protocol too thin to assess
]


@dataclass
class EligibilityCriteria:
    """One COI's inclusion/exclusion rubric.

    Rendered into (a) the screening system prompt for Claude, (b) the docx
    Methodology section, and (c) the PRISMA flow diagram's exclusion-reason
    tallies.
    """
    coi: str
    coi_description: str

    # Inclusion (all must hold; the screen returns exclude if any fails)
    inclusion: list[str] = field(default_factory=list)

    # Exclusion (any one suffices to exclude); each maps to an ExclusionCode
    exclusion: list[tuple[str, ExclusionCode]] = field(default_factory=list)

    # Positive keyword hints — help the screen recognize on-topic outcomes.
    # NOT hard filters; just cues that tilt Claude toward "include".
    positive_signals: list[str] = field(default_factory=list)

    # Negative keyword hints — cues that tilt toward "exclude".
    negative_signals: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Serialize as a prompt block for the screening node."""
        lines = [
            f"# Eligibility criteria for COI: {self.coi}",
            f"Description: {self.coi_description}",
            "",
            "## Inclusion (ALL must be satisfied):",
        ]
        for i, item in enumerate(self.inclusion, 1):
            lines.append(f"  I{i}. {item}")
        lines.append("")
        lines.append("## Exclusion (ANY triggers exclude, use the given code):")
        for i, (item, code) in enumerate(self.exclusion, 1):
            lines.append(f"  E{i} [{code}]: {item}")
        if self.positive_signals:
            lines.append("")
            lines.append(f"Positive signals: {', '.join(self.positive_signals)}")
        if self.negative_signals:
            lines.append(f"Negative signals: {', '.join(self.negative_signals)}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Global criteria applied to every COI (mirrors Circadic §1.3.2 inclusion 1
# and exclusion 1–2, generalized)
# ─────────────────────────────────────────────────────────────────────────────

GLOBAL_INCLUSION = [
    "Published, registered, or preprinted from 2016 onward "
    "(rationale: modern sensor/wearable era).",
    "Study reports at least one wearable, handheld, ambient sensor, or "
    "digital endpoint in the design.",
]

GLOBAL_EXCLUSION: list[tuple[str, ExclusionCode]] = [
    ("Study uses implantable or invasive devices as the primary measurement.",
     "wrong_study_type"),
    ("Device operates only under specialist supervision in a clinic office "
     "setup (i.e., not deployable at-home or ambulatory).",
     "wrong_study_type"),
    ("Study uses only neuroimaging / CSF endpoints, observer-reported "
     "outcomes, or exclusively paper-and-pen cognitive assessments.",
     "wrong_outcome"),
    ("Study is underpowered with no statistically significant findings AND "
     "no protocol-level pre-specification of digital endpoints.",
     "underpowered"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Per-COI criteria library
#
# Add new COIs by adding a new key. The MVPA entry is the reference/dry-run
# case; sleep, cough, oculomotor, etc. follow the same shape.
# ─────────────────────────────────────────────────────────────────────────────

CRITERIA: dict[str, EligibilityCriteria] = {
    "moderate_to_vigorous_physical_activity": EligibilityCriteria(
        coi="moderate_to_vigorous_physical_activity",
        coi_description=(
            "Time spent in moderate-to-vigorous intensity physical activity, "
            "typically operationalized from tri-axial accelerometer data via "
            "MET-based thresholds (e.g., ≥3 METs) or count-based cut-points "
            "(e.g., Freedson ≥1952 hip counts/min)."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: MVPA minutes/day, "
            "step count, activity counts, energy expenditure, sedentary time, "
            "or accelerometer-derived activity intensity classes.",
            "Device is body-worn (wrist, waist, hip, thigh, or chest) OR "
            "smartphone-based passive activity sensing.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is self-reported activity only (IPAQ, GPAQ, diary) "
             "with no device-derived measure.",
             "wrong_outcome"),
            ("Study population is exclusively pediatric (<18) unless the "
             "indication is pediatric.",
             "wrong_population"),
        ],
        positive_signals=[
            "MVPA", "moderate-to-vigorous", "moderate to vigorous",
            "accelerometer", "actigraphy", "ActiGraph", "Axivity",
            "GENEActiv", "wGT3X", "GT3X+", "GT9X", "Fitbit", "activity counts",
            "step count", "energy expenditure", "sedentary time",
            "cut-point", "Freedson", "METs",
        ],
        negative_signals=[
            "self-report only", "questionnaire only", "IPAQ", "GPAQ",
            "implanted", "in-clinic gait mat only",
        ],
    ),

    # ─── Template for the next COI. Copy, rename, fill in. ───
    # "sleep": EligibilityCriteria(
    #     coi="sleep",
    #     coi_description="Sleep quality and quantity metrics from actigraphy, "
    #                     "bed-mat sensors, or portable PSG/EEG.",
    #     inclusion=GLOBAL_INCLUSION + [...],
    #     exclusion=GLOBAL_EXCLUSION + [...],
    #     positive_signals=["WASO", "sleep efficiency", "TST", "Actiwatch", ...],
    # ),
}


def get(coi: str) -> EligibilityCriteria:
    """Look up criteria for a COI. Raises with a helpful message if missing."""
    try:
        return CRITERIA[coi]
    except KeyError as e:
        available = ", ".join(sorted(CRITERIA)) or "(none defined)"
        raise KeyError(
            f"No criteria defined for COI {coi!r}. "
            f"Available: {available}. Add a new entry in criteria.py."
        ) from e


def render_methodology_block(coi: str) -> str:
    """Verbatim methodology-section text for the docx builder.

    The final report's §Methodology quotes this exactly, so a reviewer can
    reproduce the eligibility screen without reading the code.
    """
    c = get(coi)
    return c.to_prompt_block()


__all__ = [
    "EligibilityCriteria",
    "ExclusionCode",
    "GLOBAL_INCLUSION",
    "GLOBAL_EXCLUSION",
    "CRITERIA",
    "get",
    "render_methodology_block",
]