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

    # ─── ALS device-landscape COIs (als_dryRun.py) ───
    # positive_signals for each deliberately include the ALS-specific
    # sub-construct vocabulary the dht-landscape-scout skill calls out by
    # name (SKILL.md's "naming-fragmentation problem" section) — e.g. ROM in
    # ALS is reported as "reachable workspace"/"head drop", never "ROM".
    # recall_patterns.py (automatic sub-construct elicitation) doesn't exist
    # yet, so these are hand-encoded rather than derived at run time.

    "bulbar_speech": EligibilityCriteria(
        coi="bulbar_speech",
        coi_description=(
            "Bulbar/speech function in ALS — articulatory precision, speech "
            "intelligibility, and voice/prosody metrics derived from acoustic "
            "analysis platforms, typically tracking bulbar-onset progression."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: speech intelligibility "
            "score, articulation rate, acoustic/voice biomarker, speaking "
            "rate, pause/phonation metrics, or ALSFRS-R bulbar subscore "
            "derived from device recording (not clinician rating alone).",
            "Device is a microphone/acoustic-recording platform, tablet/app-"
            "based speech-capture tool, or EMA (ecological momentary "
            "assessment) speech sensor.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is clinician-administered ALSFRS-R bulbar subscore "
             "only, with no device-derived acoustic or speech-timing "
             "measure.",
             "wrong_outcome"),
            ("Study is exclusively about swallowing/dysphagia with no "
             "speech-production or voice measure.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "dysarthria", "speech intelligibility", "articulation rate",
            "acoustic analysis", "voice biomarker", "prosody",
            "speaking rate", "phonation", "bulbar", "ALSFRS-R bulbar",
            "speech rate", "vowel space", "pause duration",
        ],
        negative_signals=[
            "clinician-rated only", "ALSFRS-R total score only",
            "dysphagia only", "swallowing only",
        ],
    ),

    "range_of_motion": EligibilityCriteria(
        coi="range_of_motion",
        coi_description=(
            "Range of motion / functional reach in ALS — joint kinematics "
            "and movement-envelope metrics from IMU, goniometry, or motion-"
            "capture systems. In ALS literature this construct is almost "
            "never labeled 'ROM'; it appears as 'reachable workspace', "
            "'head drop', or 'cervical range of motion'."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: joint angle/ROM "
            "(degrees), reachable workspace volume, head drop angle, "
            "cervical range of motion, or IMU-derived kinematic metric.",
            "Device is an IMU, goniometer, motion-capture (optical or "
            "markerless), or wearable inertial sensor.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is manual clinician goniometry with no wearable/"
             "digital sensor involved.",
             "wrong_intervention"),
            ("Study is exclusively about spasticity/tone scoring with no "
             "kinematic range-of-motion measure.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "range of motion", "reachable workspace", "head drop",
            "cervical range of motion", "goniometry", "IMU", "kinematics",
            "joint angle", "motion capture", "markerless motion capture",
            "inertial measurement unit", "upper limb workspace",
        ],
        negative_signals=[
            "manual goniometry only", "spasticity scale only",
            "tone assessment only",
        ],
    ),

    "muscle_function": EligibilityCriteria(
        coi="muscle_function",
        coi_description=(
            "Muscle strength/function in ALS — grip strength, dynamometry, "
            "and myometry metrics, typically reported as 'muscle strength' "
            "or 'grip strength' rather than naming the instrument (methods-"
            "section-only naming per the dht-landscape-scout naming-"
            "fragmentation pattern for dynamometers)."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: grip strength (kg/N), "
            "maximum voluntary isometric contraction (MVIC), dynamometry "
            "score, myometry score, or device-derived fine-motor/ALSFRS-R "
            "fine-motor item.",
            "Device is a handheld or fixed dynamometer, myometer, load-cell "
            "based strength sensor, or instrumented pinch/grip gauge.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is manual muscle testing (MMT) via clinician ordinal "
             "scale only, with no instrumented force measurement.",
             "wrong_intervention"),
            ("Study is exclusively about electromyography (EMG) diagnostic "
             "classification with no strength/force outcome.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "grip strength", "dynamometry", "dynamometer", "myometry",
            "muscle strength", "MVIC", "maximum voluntary isometric "
            "contraction", "pinch strength", "load cell", "handheld "
            "dynamometer", "fine motor", "ALSFRS-R fine motor",
        ],
        negative_signals=[
            "manual muscle testing only", "MMT only", "EMG diagnostic only",
        ],
    ),

    "respiratory_function": EligibilityCriteria(
        coi="respiratory_function",
        coi_description=(
            "Respiratory function in ALS — forced/slow vital capacity, "
            "sniff nasal inspiratory pressure, cough peak flow, and home "
            "spirometry/NIV-adherence metrics, the most closely tracked "
            "functional domain in ALS trials."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: forced vital capacity "
            "(FVC), slow vital capacity (SVC), sniff nasal inspiratory "
            "pressure (SNIP), maximal inspiratory/expiratory pressure "
            "(MIP/MEP), cough peak flow, or NIV usage/adherence hours.",
            "Device is a home/portable spirometer, SNIP meter, peak-flow "
            "meter, or NIV device with usage-logging capability.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is in-clinic spirometry only, performed under "
             "specialist supervision with no home/portable device "
             "involved.",
             "wrong_study_type"),
            ("Study is exclusively about polysomnography-diagnosed sleep-"
             "disordered breathing with no vital-capacity or respiratory-"
             "muscle-strength measure.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "forced vital capacity", "FVC", "slow vital capacity", "SVC",
            "sniff nasal inspiratory pressure", "SNIP", "MIP", "MEP",
            "cough peak flow", "home spirometry", "NIV adherence",
            "noninvasive ventilation", "respiratory muscle strength",
        ],
        negative_signals=[
            "in-clinic spirometry only", "polysomnography only",
            "sleep-disordered breathing only",
        ],
    ),

    "oculomotor": EligibilityCriteria(
        coi="oculomotor",
        coi_description=(
            "Oculomotor function in ALS — eye-tracking, saccadic velocity, "
            "and gaze/pursuit metrics, relevant both as a disease biomarker "
            "and as an assistive-communication modality in advanced ALS."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: saccadic velocity/"
            "latency, smooth pursuit gain, gaze fixation stability, "
            "electrooculography (EOG) metric, or eye-tracking-derived "
            "communication rate.",
            "Device is an infrared eye-tracker, video-oculography system, "
            "EOG sensor, or eye-tracking-based assistive communication "
            "device.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is clinician-observed nystagmus/gaze-palsy assessment "
             "only, with no instrumented eye-tracking or EOG measure.",
             "wrong_intervention"),
            ("Study is exclusively about eye-tracking as an augmentative-"
             "communication interface with no oculomotor-function outcome "
             "measure reported.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "eye tracking", "eye-tracking", "saccadic velocity",
            "saccade latency", "smooth pursuit", "gaze fixation",
            "electrooculography", "EOG", "video-oculography",
            "oculomotor", "gaze-based communication",
        ],
        negative_signals=[
            "clinician-observed only", "nystagmus assessment only",
            "communication interface only",
        ],
    ),

    # ─── Alzheimer's digital-endpoint classes (alzheimers_dryRun.py) ───
    # Each is a broad ENDPOINT CLASS, not a single construct — the evidence
    # node's device_rows within each class are what map individual metrics
    # (e.g. sleep efficiency, WASO, gait speed) to the devices that measure
    # them, per the v3_evidence.measures_supported / criteria_breakdown
    # fields already in state.DeviceRow. No schema change needed; classes
    # are kept non-overlapping so a device isn't scored redundantly under
    # two classes for the same construct.

    "sleep_quality_quantity": EligibilityCriteria(
        coi="sleep_quality_quantity",
        coi_description=(
            "Sleep quality and quantity in Alzheimer's disease — actigraphy- "
            "or PSG-derived sleep-stage, continuity, and circadian metrics. "
            "Sleep fragmentation and circadian disruption (including "
            "sundowning) are established AD biomarkers, not just comorbid "
            "symptoms."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: total sleep time "
            "(TST), sleep efficiency, wake after sleep onset (WASO), sleep "
            "stage distribution, sleep fragmentation index, or circadian "
            "rhythm metric (e.g., interdaily stability, intradaily "
            "variability).",
            "Device is a wrist/ambient actigraph, portable/home PSG, "
            "under-mattress sensor, or radar/contactless sleep monitor.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is self-reported sleep quality (PSQI, sleep diary) "
             "only, with no device-derived measure.",
             "wrong_outcome"),
            ("Study is exclusively about obstructive sleep apnea diagnosis "
             "with no sleep-continuity or circadian-rhythm metric relevant "
             "to AD.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "sleep efficiency", "WASO", "total sleep time", "sleep "
            "fragmentation", "actigraphy", "circadian rhythm", "interdaily "
            "stability", "intradaily variability", "sundowning",
            "sleep staging", "polysomnography", "under-mattress sensor",
            "contactless sleep monitoring",
        ],
        negative_signals=[
            "self-report only", "PSQI only", "sleep diary only",
            "apnea diagnosis only",
        ],
    ),

    "physical_activity_adherence": EligibilityCriteria(
        coi="physical_activity_adherence",
        coi_description=(
            "Physical activity levels and treatment/medication adherence in "
            "Alzheimer's disease — accelerometer-derived activity metrics "
            "alongside digital adherence monitoring (smart pillboxes, "
            "ingestible sensors, connected inhalers/injectors), both "
            "tracked as behavioral digital endpoints in AD trials."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: MVPA minutes/day, "
            "step count, activity counts, sedentary time, medication "
            "adherence rate, dose-timing accuracy, or missed-dose count "
            "captured by a connected device.",
            "Device is body-worn (wrist/waist) activity sensor OR a "
            "digital adherence device (smart pillbox, ingestible sensor, "
            "connected drug-delivery device, adherence app with sensor "
            "confirmation).",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is self-reported activity or adherence (pill count "
             "by caregiver report, activity diary) only, with no "
             "device-derived measure.",
             "wrong_outcome"),
            ("Study population is exclusively pediatric (<18) unless the "
             "indication is pediatric.",
             "wrong_population"),
        ],
        positive_signals=[
            "MVPA", "step count", "accelerometer", "actigraphy",
            "medication adherence", "smart pillbox", "ingestible sensor",
            "connected inhaler", "dose-timing", "missed dose",
            "adherence monitoring", "electronic pillbox", "MEMS cap",
        ],
        negative_signals=[
            "self-report only", "caregiver-reported pill count only",
            "activity diary only",
        ],
    ),

    "motor_control": EligibilityCriteria(
        coi="motor_control",
        coi_description=(
            "Motor control in Alzheimer's disease — gait, tremor, and fine-"
            "motor metrics from wearable IMUs or instrumented walkways. "
            "Gait speed decline and stride-time variability are established "
            "prodromal-AD and cognitive-decline correlates, distinct from "
            "general physical-activity volume."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: gait speed, stride "
            "length/time variability, dual-task gait cost, tremor "
            "amplitude/frequency, finger-tapping rate, or Timed Up and Go "
            "(TUG) duration captured by an instrumented device.",
            "Device is a wearable IMU, instrumented walkway/mat, "
            "smartphone-based gait-sensing app, or motion-capture system.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is clinician-timed gait (stopwatch) or manual TUG "
             "scoring only, with no instrumented sensor involved.",
             "wrong_intervention"),
            ("Study is exclusively about MVPA/step-count activity volume "
             "with no gait-quality or motor-control-specific metric.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "gait speed", "stride time variability", "dual-task gait",
            "gait analysis", "tremor", "finger tapping", "Timed Up and Go",
            "TUG", "IMU", "instrumented walkway", "GAITRite",
            "motion capture", "smartphone gait",
        ],
        negative_signals=[
            "manually timed only", "stopwatch only", "step count only",
            "MVPA only",
        ],
    ),

    "speech_language_cognition": EligibilityCriteria(
        coi="speech_language_cognition",
        coi_description=(
            "Speech, language, and digital cognitive assessment in "
            "Alzheimer's disease — passive acoustic/linguistic biomarkers "
            "and tablet/computer-administered cognitive testing, both "
            "increasingly used as remote digital cognitive endpoints."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: speech/acoustic "
            "biomarker (pause ratio, lexical diversity, articulation rate), "
            "natural-language-processing-derived linguistic metric, or a "
            "digital/computerized cognitive test score (reaction time, "
            "trial-level accuracy) from a tablet or computer platform.",
            "Device or platform is a microphone/speech-recording tool, "
            "NLP-based transcript analysis pipeline, or tablet/computer-"
            "administered cognitive-testing application.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is paper-and-pencil neuropsychological testing (e.g., "
             "MMSE, MoCA administered on paper) only, with no digital "
             "capture or scoring.",
             "wrong_intervention"),
            ("Study is exclusively about neuroimaging-based language-"
             "network mapping with no behavioral speech or cognitive-test "
             "outcome.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "speech biomarker", "acoustic analysis", "linguistic marker",
            "natural language processing", "digital cognitive assessment",
            "computerized cognitive test", "tablet-based cognitive test",
            "reaction time", "pause ratio", "lexical diversity",
            "automatic speech recognition", "voice biomarker",
        ],
        negative_signals=[
            "paper-and-pencil only", "MMSE paper administration only",
            "neuroimaging only",
        ],
    ),

    "falls_balance_postural_control": EligibilityCriteria(
        coi="falls_balance_postural_control",
        coi_description=(
            "Falls risk and postural control in Alzheimer's disease — "
            "wearable- or force-platform-derived balance and fall-detection "
            "metrics. Falls are a major AD/dementia morbidity driver and "
            "postural sway is an established early motor correlate."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: postural sway "
            "(center-of-pressure path length/area), fall count/rate "
            "detected by a device, near-fall detection, or balance-"
            "platform-derived stability index.",
            "Device is a wearable fall-detection sensor, force/balance "
            "platform, IMU-based sway-measurement device, or ambient fall-"
            "detection system.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is caregiver- or self-reported fall history only, "
             "with no device-based detection or balance measurement.",
             "wrong_outcome"),
            ("Study is exclusively about fracture/injury outcomes post-fall "
             "with no balance or fall-detection sensor data.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "postural sway", "center of pressure", "balance platform",
            "fall detection", "near-fall", "fall risk", "force platform",
            "stability index", "wearable fall sensor", "ambient fall "
            "detection",
        ],
        negative_signals=[
            "self-reported falls only", "caregiver-reported falls only",
            "fracture outcome only",
        ],
    ),

    "adl_functional_independence": EligibilityCriteria(
        coi="adl_functional_independence",
        coi_description=(
            "Activities-of-daily-living (ADL) and functional independence "
            "in Alzheimer's disease — ambient/smart-home sensor-derived "
            "behavioral metrics (activity recognition, routine deviation, "
            "IADL-relevant task detection), used as passive functional-"
            "decline endpoints."
        ),
        inclusion=GLOBAL_INCLUSION + [
            "Outcome measure includes at least one of: in-home activity-"
            "recognition rate, routine/behavioral-pattern deviation, "
            "instrumented-IADL task completion (e.g., meal prep, "
            "medication-area visits), or passive monitoring-derived "
            "functional-decline index.",
            "Device is an ambient/smart-home sensor system (PIR, door/"
            "contact sensors, smart-home hub), passive in-home monitoring "
            "platform, or personal-emergency-response system (PERS) with "
            "activity logging.",
        ],
        exclusion=GLOBAL_EXCLUSION + [
            ("Outcome is caregiver- or self-reported ADL/IADL scale "
             "(e.g., Katz ADL, Lawton IADL questionnaire) only, with no "
             "device-derived measure.",
             "wrong_outcome"),
            ("Study is exclusively about assistive-technology usability "
             "with no functional-decline or activity-recognition outcome.",
             "wrong_outcome"),
        ],
        positive_signals=[
            "ambient sensor", "smart home", "activity recognition",
            "passive monitoring", "in-home sensor", "IADL", "routine "
            "deviation", "behavioral pattern", "PERS", "personal "
            "emergency response", "PIR sensor",
        ],
        negative_signals=[
            "caregiver-reported only", "Katz ADL questionnaire only",
            "Lawton IADL questionnaire only", "usability study only",
        ],
    ),
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