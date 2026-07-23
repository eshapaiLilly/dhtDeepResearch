"""
recall_patterns.py — naming-fragmentation recovery, as extensible config.

Why this module exists
----------------------
dht-landscape-scout SKILL.md's Open Questions ledger flags the absence of
this module as the HIGHEST-STAKES gap: the naming-fragmentation recovery
passes are "very likely a major reason the original ALS report was good,"
and without them a pipeline run systematically under-counts exactly the
devices the skill was best at catching. als_dryRun.py's RUN_NOTES disclose
the same gap. This module is the first build of that recovery.

What it does (and does NOT do)
------------------------------
It implements the DETERMINISTIC half of recovery — the part SKILL.md says
"belongs in always-executed Python rather than an LLM judgment about
whether to bother":

  1. Device-class reverse search. The SKILL.md device-class table is
     durable domain knowledge ("spirometry papers name the device in
     Methods, not the abstract" is a stable property of how that
     literature is written). For every device class relevant to a COI,
     this adds generic-descriptor query lanes ("dynamometry", "acoustic
     analysis platform") that surface methods-section-only-named devices a
     product-name search can never reach.

  2. Construct-level recovery for software/PI-branded platforms. For
     speech, oculomotor, and cognitive platforms — where the commercial
     brand never appears in PubMed because papers are authored under the
     academic PI — this adds construct-level query lanes ("articulatory
     precision", "saccadic velocity") that need no company name at all,
     per SKILL.md failure-mode #1.

It does NOT implement the split-brain (Python -> model -> Python) half:
taking a company with zero PubMed hits, identifying its named PI from
public materials, and re-querying by PI-name. That control flow is
undesigned (Open Questions ledger item 2) and is left as a documented
TODO stub (`pi_author_recovery_lanes`) rather than faked. Runs using this
module still recover the construct-level and device-class devices, which
is the bulk of the gap; the report methodology should disclose that the
PI-by-author pass is not yet automated.

Design
------
Pure config + pure functions. No I/O, no LLM. `expand_search_plan()` takes
whatever `graph.default_search_plan()` built and ADDS recovery lanes to it;
dedup in retrieval.py collapses any overlap, so over-generating lanes here
is safe (it costs redundant, deduped hits, not wrong results). Every added
lane is a normal query dict, so each surfaced Record still records the
exact query that found it via `Record.retrieved_query` — recovery lanes are
therefore auditable with no extra bookkeeping (SKILL.md: "Every
sub-construct used is recorded").

Adding a new fragmentation pattern = add a row to DEVICE_CLASS_PATTERNS.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from criteria import EligibilityCriteria


log = logging.getLogger(__name__)


def s2_bulk_query_syntax(indication: str, terms: list[str]) -> str:
    """Build a query string in Semantic Scholar BULK SEARCH's actual boolean
    syntax — NOT the same convention used for CTG's query.outc or PubMed's
    query string elsewhere in this pipeline.

    This matters because it's a real correctness issue, not a style choice:
    S2 bulk search's query grammar uses `|` for OR, `+`/`-` for required/
    excluded terms, and `"..."` for an exact phrase (see Semantic Scholar's
    own tutorial, "Examples using search query parameters"). The literal
    English word "OR" is NOT an operator in this grammar — passed as-is,
    it would be searched for as the literal token "or", silently changing
    what the query means rather than raising an error. Multi-word terms
    MUST be quoted to be treated as a phrase; unquoted, S2 treats each word
    as a separate token.

    Builds: '"{indication}" + (term1|term2|"multi word term3")'
    — indication is required (+), the term list is an OR-group.
    """
    quoted_terms = [f'"{t}"' if " " in t else t for t in terms]
    or_group = "|".join(quoted_terms)
    return f'"{indication}" + ({or_group})'


@dataclass(frozen=True)
class DeviceClassPattern:
    """One naming-fragmentation pattern.

    name:                human-readable class label (for logging/audit).
    reported_as:         how the device is named in the literature (the
                         Methods-only phrase) — documentation of WHY it's
                         missed by a product-name search. Not queried.
    generic_descriptors: the reverse-search terms to query on — generic
                         measurement descriptors that surface the class
                         regardless of product name.
    trigger_terms:       if ANY of these appears in the COI's name,
                         description, or positive_signals, this class is
                         relevant to the COI and its recovery lanes run.
                         Matching this way (rather than a hardcoded COI
                         list) means new COIs pick up recovery automatically
                         if they share vocabulary.
    software_platform:   True for PI-branded / algorithm-only classes where
                         construct_terms recovery (below) also applies.
    construct_terms:     construct-level search terms (no company name) for
                         software_platform classes — SKILL.md failure-mode
                         #1 recovery. Ignored unless software_platform.
    """
    name: str
    reported_as: tuple[str, ...]
    generic_descriptors: tuple[str, ...]
    trigger_terms: tuple[str, ...]
    software_platform: bool = False
    construct_terms: tuple[str, ...] = field(default_factory=tuple)


# ─────────────────────────────────────────────────────────────────────────────
# The device-class table — this IS the SKILL.md table, encoded.
#
# The five hardware rows are copied directly from SKILL.md's
# "Device-class systematic under-naming" table. The three software rows
# encode SKILL.md's PI-branded failure-mode #1 for the platform-dominated
# COIs it names explicitly (speech/acoustic, digital cognitive, eye-tracking).
# ─────────────────────────────────────────────────────────────────────────────

DEVICE_CLASS_PATTERNS: tuple[DeviceClassPattern, ...] = (
    DeviceClassPattern(
        name="spirometers",
        reported_as=("FVC", "spirometry", "vital capacity"),
        generic_descriptors=(
            "spirometry", "home spirometry", "portable spirometer",
            "forced vital capacity", "slow vital capacity",
        ),
        trigger_terms=(
            "respiratory", "spirometry", "vital capacity", "fvc", "svc",
            "pulmonary", "breathing", "ventilation",
        ),
    ),
    DeviceClassPattern(
        name="dynamometers",
        reported_as=("muscle strength", "grip strength", "MVIC"),
        generic_descriptors=(
            "dynamometry", "handheld dynamometer", "grip strength",
            "myometry", "maximum voluntary isometric contraction",
        ),
        trigger_terms=(
            "muscle", "strength", "grip", "dynamom", "myometry", "mvic",
            "force", "fine motor",
        ),
    ),
    DeviceClassPattern(
        name="accelerometers",
        reported_as=("physical activity", "steps", "activity counts"),
        generic_descriptors=(
            "accelerometry", "actigraphy", "activity monitor",
            "wrist-worn accelerometer", "wearable activity monitor",
        ),
        trigger_terms=(
            "activity", "accelerom", "actigraph", "step count", "steps",
            "mvpa", "sedentary", "energy expenditure", "gait", "ambulation",
        ),
    ),
    DeviceClassPattern(
        name="goniometers_imu",
        reported_as=("ROM", "range of motion", "kinematics"),
        generic_descriptors=(
            "goniometry", "inertial measurement unit", "inertial sensor",
            "motion capture", "kinematics", "reachable workspace",
        ),
        trigger_terms=(
            "range of motion", "rom", "kinematic", "goniom", "imu",
            "joint angle", "reachable workspace", "head drop", "cervical",
            "motion capture",
        ),
    ),
    DeviceClassPattern(
        name="psg_sleep",
        reported_as=("sleep quality", "AHI", "sleep efficiency"),
        generic_descriptors=(
            "polysomnography", "actigraphy sleep", "home sleep monitoring",
            "under-mattress sensor", "contactless sleep monitoring",
        ),
        trigger_terms=(
            "sleep", "waso", "circadian", "polysomnog", "actigraph",
            "nocturnal", "sleep-disordered breathing", "apnea",
        ),
    ),
    # ── Software / PI-branded classes (failure-mode #1) ──
    DeviceClassPattern(
        name="speech_acoustic_platforms",
        reported_as=("speech intelligibility", "acoustic analysis", "voice biomarker"),
        generic_descriptors=(
            "acoustic analysis platform", "speech biomarker",
            "automatic speech analysis", "voice biomarker platform",
        ),
        trigger_terms=(
            "speech", "bulbar", "acoustic", "voice", "articulat", "prosody",
            "phonation", "dysarthria", "intelligibility", "language",
        ),
        software_platform=True,
        construct_terms=(
            "articulatory precision", "speech intelligibility",
            "articulation rate", "speaking rate", "acoustic voice analysis",
            "pause duration", "vowel space area",
        ),
    ),
    DeviceClassPattern(
        name="eye_tracking_platforms",
        reported_as=("saccadic velocity", "gaze tracking", "oculomotor"),
        generic_descriptors=(
            "eye tracking", "video-oculography", "infrared eye tracker",
            "electrooculography",
        ),
        trigger_terms=(
            "oculomotor", "eye track", "eye-track", "saccad", "gaze",
            "pursuit", "oculography", "eog",
        ),
        software_platform=True,
        construct_terms=(
            "saccadic velocity", "saccade latency", "smooth pursuit gain",
            "gaze fixation stability", "antisaccade",
        ),
    ),
    DeviceClassPattern(
        name="digital_cognitive_platforms",
        reported_as=("cognitive assessment", "reaction time", "NLP linguistic marker"),
        generic_descriptors=(
            "digital cognitive assessment", "computerized cognitive test",
            "tablet-based cognitive test", "natural language processing biomarker",
        ),
        trigger_terms=(
            "cognit", "linguistic", "lexical", "natural language",
            "reaction time", "neuropsych",
        ),
        software_platform=True,
        construct_terms=(
            "lexical diversity", "linguistic decline", "reaction time task",
            "speech-derived cognitive marker",
        ),
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Relevance + lane construction
# ─────────────────────────────────────────────────────────────────────────────

def _coi_haystack(coi: str, criteria: EligibilityCriteria) -> str:
    """Everything we match trigger_terms against: COI name, description,
    and its positive_signals (which already hand-encode the ALS-specific
    sub-construct vocabulary)."""
    parts = [coi, criteria.coi or "", criteria.coi_description or ""]
    parts.extend(criteria.positive_signals or [])
    return " ".join(parts).lower()


def _term_matches(term: str, haystack: str) -> bool:
    """Match a trigger term at a word boundary, allowing stems.

    Raw substring matching is wrong here: it fires "rom" inside "f-rom" and
    "imu" inside random words, cross-contaminating unrelated device classes.
    We instead require the term to start at a word boundary (\\b), while
    still allowing it to be a PREFIX of a longer word — so stems like
    "dynamom" match "dynamometry"/"dynamometer", and "accelerom" matches
    "accelerometer", but "rom" no longer matches "from" (no boundary before
    the 'r' in "from"). Multi-word terms are matched as phrases.
    """
    term = term.lower().strip()
    if not term:
        return False
    if " " in term:
        return term in haystack  # phrase match is fine as substring
    return re.search(r"\b" + re.escape(term), haystack) is not None


def _pattern_applies(p: DeviceClassPattern, haystack: str) -> bool:
    return any(_term_matches(t, haystack) for t in p.trigger_terms)


def applicable_patterns(coi: str, criteria: EligibilityCriteria) -> list[DeviceClassPattern]:
    """Which device-class patterns are relevant to this COI.

    SKILL.md: "Whenever a listed class is relevant to the COI, the recovery
    pass must run for it" — a completeness requirement, which is exactly why
    it lives in always-executed config rather than a per-run judgment call.
    """
    hay = _coi_haystack(coi, criteria)
    hits = [p for p in DEVICE_CLASS_PATTERNS if _pattern_applies(p, hay)]
    return hits


def _clinical_outcome_clause() -> str:
    """The clinical-outcome qualifier appended to PubMed reverse-search
    lanes so a generic descriptor ("dynamometry") is scoped to validation
    literature rather than returning the entire descriptor corpus."""
    return '(validation OR "clinical outcome" OR correlation OR reliability OR ALSFRS)'


def recovery_lanes(
    coi: str,
    indication: str,
    criteria: EligibilityCriteria,
) -> dict:
    """Build the recovery query lanes for a COI.

    Returns a search_plan-shaped dict ({"clinicaltrials": [...],
    "pubmed": [...], "europepmc": [...]}) containing ONLY the recovery lanes
    (the caller merges these onto the base plan).

    - CTG lanes search by OUTCOME-MEASURE TEXT (query.outc), which SKILL.md's
      COA section calls the single most reliable way to surface
      methods-only-named instruments and COA tools.
    - PubMed/Europe PMC lanes pair the descriptor with the indication and a
      clinical-outcome qualifier.
    - Software-platform classes additionally get construct-level lanes with
      NO company name (failure-mode #1 recovery).
    """
    patterns = applicable_patterns(coi, criteria)
    ctg: list[dict] = []
    pubmed: list[dict] = []
    epmc: list[dict] = []
    s2: list[dict] = []
    clause = _clinical_outcome_clause()

    for p in patterns:
        for desc in p.generic_descriptors:
            ctg.append({"query.cond": indication, "query.outc": desc})
            pubmed.append({"query": f'{indication} AND "{desc}" AND {clause}'})
            # Europe PMC field syntax: TITLE_ABS scopes to title+abstract;
            # SRC:PPR is added later by the base plan's preprint lane, so
            # here we search all sources (preprints + peer-reviewed).
            epmc.append({"query": f'"{desc}" AND "{indication}"'})
            # Semantic Scholar — independent index/host, unaffected by any
            # EBI-specific connectivity issue. Single-term lane, so there's
            # no OR to get wrong here, but routed through the same helper
            # as graph.py's multi-term lanes for one consistent, correct
            # code path rather than two slightly different ad-hoc ones.
            s2.append({"query": s2_bulk_query_syntax(indication, [desc])})
        if p.software_platform:
            for c in p.construct_terms:
                # Construct-level PI recovery: no company name at all.
                pubmed.append({"query": f'{indication} AND "{c}"'})
                epmc.append({"query": f'"{c}" AND "{indication}"'})
                s2.append({"query": s2_bulk_query_syntax(indication, [c])})

    if patterns:
        log.info(
            "recall_patterns[%s]: %d class(es) applied (%s) -> "
            "+%d CTG, +%d PubMed, +%d Europe PMC, +%d Semantic Scholar recovery lanes",
            coi, len(patterns), ", ".join(p.name for p in patterns),
            len(ctg), len(pubmed), len(epmc), len(s2),
        )
    else:
        log.info("recall_patterns[%s]: no device-class pattern matched", coi)

    return {"clinicaltrials": ctg, "pubmed": pubmed, "europepmc": epmc, "semanticscholar": s2}


def expand_search_plan(
    base_plan: dict,
    coi: str,
    indication: str,
    criteria: EligibilityCriteria,
) -> dict:
    """Merge recovery lanes onto a base search plan, per source channel.

    Order preserved: base lanes first (they're the most precise), recovery
    lanes appended. Dedup downstream in retrieval.py collapses overlap.
    """
    rec = recovery_lanes(coi, indication, criteria)
    merged = dict(base_plan)
    for source in ("clinicaltrials", "pubmed", "europepmc", "semanticscholar", "biorxiv"):
        base_lanes = list(base_plan.get(source, []))
        rec_lanes = list(rec.get(source, []))
        if base_lanes or rec_lanes:
            merged[source] = base_lanes + rec_lanes
    return merged


def pi_author_recovery_lanes(coi: str, indication: str, criteria: EligibilityCriteria) -> dict:
    """TODO (Open Questions ledger item 2): the split-brain
    Python -> model -> Python PI-by-author recovery.

    Not built. Would take commercial devices with zero PubMed hits under
    their own name, identify named scientific founders from public
    materials (model judgment), then query PubMed by PI-name x indication
    x construct. The control flow (who calls whom, how partial results
    accumulate in state) is undesigned. Until it exists, the construct-level
    lanes in recovery_lanes() cover the deterministic portion, and the
    report methodology must disclose that PI-by-author recovery is not yet
    automated. Returns empty so callers can wire it in without a signature
    change later.
    """
    return {"clinicaltrials": [], "pubmed": [], "europepmc": [], "semanticscholar": []}


__all__ = [
    "DeviceClassPattern",
    "DEVICE_CLASS_PATTERNS",
    "applicable_patterns",
    "recovery_lanes",
    "expand_search_plan",
    "pi_author_recovery_lanes",
    "s2_bulk_query_syntax",
]