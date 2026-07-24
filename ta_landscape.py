"""
ta_landscape.py — Therapeutic-Area-first COI discovery stage (V1).

What this is, and where it sits
-------------------------------
Every other entry point in this pipeline (coi_first, and the not-yet-wired
measure_first / device_first) takes the COI list as an INPUT and terminates in
the device-scoring machinery. This stage sits one level UP: given only an
indication, it researches the therapeutic area and PRODUCES a ranked,
evidence-grounded COI shortlist — the thing a human currently types into the
router's Q2 by hand.

    indication  ──▶  ta_landscape (this file)  ──▶  reviewed COI shortlist
                                                         │
                                    (human verifies, then runs, per COI:)
                                                         ▼
                                        coi_first graph (graph.build_graph)

V1 deliberately STOPS at the reviewed shortlist. It does not auto-run coi_first
and it does not write into criteria.py. Its outputs are (a) a human-review memo
with a clinical-importance × digital-measurability 2x2, and (b) a *draft*
criteria stub per recommended COI, emitted as a copy-pasteable criteria.py block
so wiring the accepted COIs into coi_first later is a paste, not a rebuild.

Why it reuses the existing spine
--------------------------------
Retrieval (`retrieval.identify`), the Record schema, the analytical-dispatcher
contract (Callable[[system, user], str]), and the evidence node's grounding
discipline (strip any citation the model emits that doesn't resolve in the
frozen citations_index) are all reused verbatim. The only genuinely new parts
are: a TA-level search plan (different query INTENT than coi_first — map the
disease's symptom/endpoint landscape, not one COI's device vocabulary), a
construct-level extraction step, and a two-axis construct scorer.

Grounding contract
------------------
Candidate COIs are extracted FROM the retrieved corpus, not from the model's
free-form disease knowledge. Every candidate and every score carries
citation_ids; any id that doesn't resolve in the corpus's citations_index is
stripped before it can reach the memo — identical to evidence.py's rule. The
ClinicalTrials.gov outcome-measures lane is the precision backbone: it is a
direct record of what constructs real trials in this indication actually
measure.

Two axes, kept separate (see the design discussion this build came from)
------------------------------------------------------------------------
A construct is scored on clinical importance AND digital measurability
INDEPENDENTLY, then placed in a 2x2. The "core to the disease but no DHT
precedent yet" quadrant is white space — a finding, not a COI to hand to
coi_first (which would come back empty). Collapsing the axes into one score
would bury exactly the most interesting output.

Disclosed V1 limitations (carried in TAResult.run_notes, not just this docstring)
---------------------------------------------------------------------------------
1. No recall_patterns pass at the TA level. TA queries are inherently broad, so
   the corpus is noisier than a COI-first pull and PI-branded / methods-only
   constructs may be under-surfaced. Mitigation: the CTG outcome-measures lane
   is high-precision and construct-explicit.
2. Emitted criteria stubs are DRAFT and unreviewed. Their positive_signals come
   from vocabulary the model observed in-corpus, which is better than a cold
   guess but is NOT the hand-tuned, ALS-specific vocabulary in criteria.py's
   authored entries. Every stub is flagged draft and must get a human glance
   before an unattended coi_first run trusts it.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Callable, Literal

from state import Record
from retrieval import identify, build_citations_index, MCPDispatcher
from criteria import EligibilityCriteria, GLOBAL_INCLUSION, CRITERIA
# Reuse evidence.py's grounding helpers verbatim — do NOT reinvent the
# fence-stripping / citation-collection logic, so both stages stay identical.
from evidence import _strip_fences, _collect_citations

log = logging.getLogger(__name__)

# Same shape as evidence.LLMDispatcher: (system_prompt, user_prompt) -> text.
LLMDispatcher = Callable[[str, str], str]

Quadrant = Literal[
    "core_and_measurable",        # high clinical importance + strong DHT precedent  → recommend
    "core_not_yet_measurable",    # high clinical importance + weak/no DHT precedent → WHITE SPACE
    "peripheral_but_measurable",  # low clinical importance + strong DHT precedent   → consider / de-risk
    "peripheral_and_unmeasured",  # low on both                                       → deprioritize
]
Recommendation = Literal["recommend", "consider", "white_space", "deprioritize"]


# ─────────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CandidateCOI:
    """One construct surfaced from the TA corpus. `coi` is the canonical
    snake_case key that must match (or become) a criteria.py entry.
    `literature_vocabulary` is the naming-fragmentation term list observed
    in-corpus — it becomes the draft stub's positive_signals."""
    coi: str
    label: str
    clinical_rationale: str
    literature_vocabulary: list[str] = field(default_factory=list)
    dht_precedent: str = ""                       # short phrase; "" == none seen
    evidence_citations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class COIScore:
    """Two-axis score for one candidate. Scores are 1–5; each axis carries its
    own rationale + citation_ids so the memo can show the receipts."""
    coi: str
    clinical_importance: int
    clinical_importance_rationale: str
    digital_measurability: int
    digital_measurability_rationale: str
    quadrant: Quadrant
    recommendation: Recommendation
    evidence_citations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class TAResult:
    indication: str
    corpus_size: int
    prisma: dict
    candidates: list[CandidateCOI]
    scores: list[COIScore]
    citations_index: dict[str, Record]
    run_notes: list[str] = field(default_factory=list)

    def score_for(self, coi: str) -> COIScore | None:
        return next((s for s in self.scores if s.coi == coi), None)

    def candidate_for(self, coi: str) -> CandidateCOI | None:
        return next((c for c in self.candidates if c.coi == coi), None)

    def recommended(self) -> list[COIScore]:
        """COIs to hand to coi_first: recommend + consider, best first.
        White space is intentionally EXCLUDED — coi_first would find nothing."""
        order = {"recommend": 0, "consider": 1}
        picks = [s for s in self.scores if s.recommendation in order]
        return sorted(
            picks,
            key=lambda s: (order[s.recommendation],
                           -(s.clinical_importance + s.digital_measurability)),
        )

    def white_space(self) -> list[COIScore]:
        return [s for s in self.scores if s.recommendation == "white_space"]


RUN_NOTES_V1 = [
    "TA-first V1: no recall_patterns pass at the TA level. TA-level queries are "
    "broad, so this corpus is noisier than a COI-first pull; PI-branded and "
    "methods-only constructs may be under-surfaced. The ClinicalTrials.gov "
    "outcome-measures lane is the high-precision, construct-explicit backbone.",
    "Emitted criteria stubs are DRAFT: positive_signals are vocabulary the model "
    "observed in-corpus, not the hand-tuned indication-specific vocabulary in "
    "criteria.py's authored entries. Human-review each stub before an unattended "
    "coi_first run trusts it.",
    "V1 stops at the reviewed shortlist. Running coi_first on the accepted COIs "
    "is a separate, human-gated step.",
]


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — TA-level search plan (reused by retrieval.identify)
# ─────────────────────────────────────────────────────────────────────────────

def ta_search_plan(indication: str) -> dict:
    """Build a TA-level search plan for retrieval.identify().

    INTENT differs from graph.default_search_plan: instead of expanding one
    COI's device vocabulary, we map the indication's symptom/endpoint landscape.
    Two ideas keep this from tripping the over-broad rejection we hit at the COI
    level (the 236M-hit S2 bug): the indication is ALWAYS a required, scoping
    term, and the CTG `query.cond` lane is naturally bounded to the disease.

    Lanes:
      - CTG cond=indication ............ harvest outcome_measures from real
                                         trials (the construct backbone)
      - CTG cond=indication + DHT terms  bias toward trials that actually used a
                                         wearable/sensor/remote measure
      - PubMed endpoint/natural-history  reviews that enumerate disease domains
      - PubMed DHT lane .............. digital-biomarker literature for precedent
    """
    dht_terms = (
        'wearable OR sensor OR accelerometer OR "digital biomarker" OR '
        'smartphone OR "remote monitoring" OR actigraphy OR "digital endpoint"'
    )
    endpoint_terms = (
        '"outcome measures" OR "clinical endpoints" OR "functional decline" OR '
        '"disease progression" OR "natural history" OR symptoms OR "quality of life"'
    )
    return {
        "clinicaltrials": [
            {"query.cond": indication},
            {"query.cond": indication, "query.term": "wearable OR sensor OR digital OR remote"},
        ],
        "pubmed": [
            {"query": f'"{indication}" AND ({endpoint_terms})'},
            {"query": f'"{indication}" AND ({dht_terms})'},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Corpus rendering (token-bounded, precision-first ordering)
# ─────────────────────────────────────────────────────────────────────────────

def _corpus_priority(r: Record) -> tuple:
    """Sort key: CTG records WITH explicit outcome_measures first (the
    construct-explicit backbone), then anything with an abstract, newest first.
    Lower tuple sorts earlier."""
    has_outcomes = bool(r.outcome_measures)
    has_abstract = bool(r.abstract)
    return (0 if has_outcomes else 1, 0 if has_abstract else 1, -(r.year or 0))


def render_corpus_for_ta(corpus: list[Record], *, max_records: int = 160) -> str:
    """Render the corpus for the extraction/scoring prompt, precision-first and
    capped so a broad TA pull can't blow the token budget. Uses Record's own
    to_prompt_text() — the same rendering evidence.py feeds the scorer."""
    ordered = sorted(corpus, key=_corpus_priority)[:max_records]
    return "\n\n".join(r.to_prompt_text() for r in ordered)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Candidate COI extraction (analytical LLM call, corpus-grounded)
# ─────────────────────────────────────────────────────────────────────────────

TA_EXTRACT_SYSTEM = """\
You are a clinical-measurement scientist building the Concept-of-Interest (COI) \
map for a therapeutic area, to support digital-health-technology (DHT) endpoint \
selection in clinical trials.

You are given a CORPUS of clinical-trial records and papers for one indication. \
Each record starts with a [citation_id] token. Your job is to enumerate the \
distinct CONSTRUCTS (functional domains, symptoms, or measurable concepts) that \
this literature shows matter for the disease — NOT devices, NOT specific \
algorithms. Think "range of motion", "bulbar speech", "sleep quality", "physical \
activity" — the layer a trial would name as an endpoint domain.

Hard rules:
1. Extract ONLY constructs the corpus actually evidences. Do not add constructs \
from your own disease knowledge that no record supports.
2. Collapse naming fragmentation: if the corpus says "reachable workspace", \
"head drop", and "cervical range of motion", these are ONE construct \
(range_of_motion) — list the surface terms under literature_vocabulary.
3. For each construct, capture whether the corpus shows any DHT/sensor/wearable/ \
digital precedent for measuring it (dht_precedent: a short phrase, or "" if none \
is evidenced).
4. Every construct MUST carry evidence_citations: the exact [citation_id] tokens \
from the corpus that support it. Use only ids present in the corpus.
5. `coi` must be a canonical snake_case key (e.g. "bulbar_speech", \
"range_of_motion"). `label` is the human-readable name.

Return ONLY JSON, no prose, no markdown fences:
{
  "candidates": [
    {
      "coi": "snake_case_key",
      "label": "Human Readable Name",
      "clinical_rationale": "why this construct matters in the disease, 1-2 sentences, grounded",
      "literature_vocabulary": ["surface term 1", "surface term 2", "..."],
      "dht_precedent": "short phrase describing sensor/wearable precedent, or empty string",
      "evidence_citations": ["<citation_id>", "..."]
    }
  ]
}
"""


def build_extract_user_message(indication: str, corpus: list[Record]) -> str:
    return (
        f"INDICATION: {indication}\n\n"
        f"CORPUS ({len(corpus)} records; a precision-first subset is shown):\n\n"
        f"{render_corpus_for_ta(corpus)}\n\n"
        "Enumerate the distinct COIs this corpus evidences. Return ONLY the JSON object."
    )


def extract_candidate_cois(
    corpus: list[Record],
    indication: str,
    llm: LLMDispatcher,
    citations_index: dict[str, Record],
) -> tuple[list[CandidateCOI], dict]:
    report = {"orphan_citations_stripped": [], "parse_error": None}
    if not corpus:
        report["parse_error"] = "empty corpus"
        return [], report

    raw = llm(TA_EXTRACT_SYSTEM, build_extract_user_message(indication, corpus))
    try:
        payload = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        report["parse_error"] = f"extract parse failed: {e}"
        log.error("ta.extract: %s", report["parse_error"])
        return [], report

    valid = set(citations_index.keys())
    orphans = _collect_citations(payload) - valid
    if orphans:
        log.warning("ta.extract: %d orphan citation(s) stripped: %s",
                    len(orphans), sorted(orphans)[:10])
        report["orphan_citations_stripped"] = sorted(orphans)

    candidates: list[CandidateCOI] = []
    for c in payload.get("candidates", []):
        cites = [x for x in c.get("evidence_citations", []) if x in valid]
        if not cites:
            # Grounding gate: a construct with no resolvable citation is not
            # corpus-evidenced — drop it rather than let it into the shortlist.
            log.warning("ta.extract: dropping ungrounded candidate %r", c.get("coi"))
            continue
        candidates.append(CandidateCOI(
            coi=c["coi"],
            label=c.get("label", c["coi"]),
            clinical_rationale=c.get("clinical_rationale", ""),
            literature_vocabulary=list(dict.fromkeys(c.get("literature_vocabulary", []))),
            dht_precedent=c.get("dht_precedent", ""),
            evidence_citations=cites,
        ))
    log.info("ta.extract: %d grounded candidate COIs", len(candidates))
    return candidates, report


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Two-axis scoring (analytical LLM call, corpus-grounded)
# ─────────────────────────────────────────────────────────────────────────────

TA_SCORE_SYSTEM = """\
You are scoring candidate Concepts of Interest (COIs) for a therapeutic area to \
decide which deserve a full digital-endpoint (DHT) landscape review.

Score each candidate on TWO INDEPENDENT axes, 1-5:
  - clinical_importance: how central this construct is to the disease and its \
progression / patient-relevant impact. 5 = core disease feature; 1 = peripheral.
  - digital_measurability: how strong the DHT/sensor precedent is for measuring \
it, per the corpus. 5 = validated digital measures exist; 1 = no digital \
precedent evidenced.

Do NOT average the axes. Place each COI in a quadrant:
  - "core_and_measurable"       : importance>=4 AND measurability>=3  -> recommend
  - "core_not_yet_measurable"   : importance>=4 AND measurability<=2  -> white_space
  - "peripheral_but_measurable" : importance<=3 AND measurability>=3  -> consider
  - "peripheral_and_unmeasured" : importance<=3 AND measurability<=2  -> deprioritize

Set `recommendation` to match the quadrant mapping above exactly.

Ground BOTH rationales in the corpus and cite [citation_id] tokens. Use only ids \
present in the corpus/candidate evidence.

Return ONLY JSON, no prose, no fences:
{
  "scores": [
    {
      "coi": "snake_case_key",
      "clinical_importance": 1-5,
      "clinical_importance_rationale": "grounded, ends with [citation_id]",
      "digital_measurability": 1-5,
      "digital_measurability_rationale": "grounded, ends with [citation_id]",
      "quadrant": "one of the four",
      "recommendation": "recommend|consider|white_space|deprioritize",
      "evidence_citations": ["<citation_id>", "..."]
    }
  ]
}
"""


def _render_candidates_for_scoring(candidates: list[CandidateCOI]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- coi={c.coi} | label={c.label}\n"
            f"    rationale: {c.clinical_rationale}\n"
            f"    vocabulary: {', '.join(c.literature_vocabulary) or '(none)'}\n"
            f"    dht_precedent: {c.dht_precedent or '(none evidenced)'}\n"
            f"    citations: {', '.join(c.evidence_citations)}"
        )
    return "\n".join(lines)


def score_cois(
    candidates: list[CandidateCOI],
    corpus: list[Record],
    indication: str,
    llm: LLMDispatcher,
    citations_index: dict[str, Record],
) -> tuple[list[COIScore], dict]:
    report = {"orphan_citations_stripped": [], "parse_error": None}
    if not candidates:
        return [], report

    user = (
        f"INDICATION: {indication}\n\n"
        f"CANDIDATE COIs:\n{_render_candidates_for_scoring(candidates)}\n\n"
        f"SUPPORTING CORPUS (precision-first subset):\n\n"
        f"{render_corpus_for_ta(corpus)}\n\n"
        "Score every candidate. Return ONLY the JSON object."
    )
    raw = llm(TA_SCORE_SYSTEM, user)
    try:
        payload = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        report["parse_error"] = f"score parse failed: {e}"
        log.error("ta.score: %s", report["parse_error"])
        return [], report

    valid = set(citations_index.keys())
    orphans = _collect_citations(payload) - valid
    if orphans:
        report["orphan_citations_stripped"] = sorted(orphans)

    known = {c.coi for c in candidates}
    scores: list[COIScore] = []
    for s in payload.get("scores", []):
        if s.get("coi") not in known:
            continue  # scorer must not invent COIs the extractor didn't surface
        ci = _clamp(s.get("clinical_importance"))
        dm = _clamp(s.get("digital_measurability"))
        scores.append(COIScore(
            coi=s["coi"],
            clinical_importance=ci,
            clinical_importance_rationale=s.get("clinical_importance_rationale", ""),
            digital_measurability=dm,
            digital_measurability_rationale=s.get("digital_measurability_rationale", ""),
            quadrant=_quadrant(ci, dm),               # recompute — don't trust the model's label
            recommendation=_recommendation(ci, dm),   # deterministic from axes
            evidence_citations=[x for x in s.get("evidence_citations", []) if x in valid],
        ))
    log.info("ta.score: scored %d/%d candidates", len(scores), len(candidates))
    return scores, report


def _clamp(v, lo: int = 1, hi: int = 5) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def _quadrant(importance: int, measurability: int) -> Quadrant:
    if importance >= 4 and measurability >= 3:
        return "core_and_measurable"
    if importance >= 4 and measurability <= 2:
        return "core_not_yet_measurable"
    if importance <= 3 and measurability >= 3:
        return "peripheral_but_measurable"
    return "peripheral_and_unmeasured"


def _recommendation(importance: int, measurability: int) -> Recommendation:
    q = _quadrant(importance, measurability)
    return {
        "core_and_measurable": "recommend",
        "core_not_yet_measurable": "white_space",
        "peripheral_but_measurable": "consider",
        "peripheral_and_unmeasured": "deprioritize",
    }[q]


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Draft criteria stubs (deterministic; the seam into coi_first)
# ─────────────────────────────────────────────────────────────────────────────

def criteria_stub_for(candidate: CandidateCOI) -> EligibilityCriteria:
    """Build a DRAFT EligibilityCriteria in the EXACT shape criteria.py uses,
    so it can be pasted into CRITERIA and consumed by coi_first unchanged.

    positive_signals = the in-corpus vocabulary (the naming-fragmentation terms
    the extractor collapsed). Inclusion = GLOBAL_INCLUSION plus one COI-specific
    line. Exclusion is left to GLOBAL_EXCLUSION — a draft should not invent new
    per-COI exclusions. This is intentionally conservative; a human tightens it."""
    coi_specific_inclusion = (
        f"Outcome measure assesses {candidate.label.lower()} "
        f"({', '.join(candidate.literature_vocabulary[:6]) or candidate.coi}) "
        "via a wearable, handheld, ambient sensor, or other digital endpoint."
    )
    return EligibilityCriteria(
        coi=candidate.coi,
        coi_description=candidate.clinical_rationale or candidate.label,
        inclusion=GLOBAL_INCLUSION + [coi_specific_inclusion],
        exclusion=[],  # rely on GLOBAL_EXCLUSION; draft adds none
        positive_signals=list(candidate.literature_vocabulary),
        negative_signals=[],
    )


def render_criteria_stub_block(candidate: CandidateCOI) -> str:
    """Copy-pasteable criteria.py entry, flagged DRAFT. Reuses the authored
    style so a reviewer sees exactly what they're accepting."""
    c = criteria_stub_for(candidate)
    existing = " (OVERRIDES an existing authored entry — review carefully!)" if candidate.coi in CRITERIA else ""
    incl = ",\n".join(f"            {inc!r}" for inc in c.inclusion)
    pos = ", ".join(repr(s) for s in c.positive_signals)
    return (
        f"    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed){existing} ──\n"
        f"    {c.coi!r}: EligibilityCriteria(\n"
        f"        coi={c.coi!r},\n"
        f"        coi_description=(\n            {c.coi_description!r}\n        ),\n"
        f"        inclusion=GLOBAL_INCLUSION + [\n{incl}\n        ],\n"
        f"        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting\n"
        f"        positive_signals=[{pos}],\n"
        f"        negative_signals=[],\n"
        f"    ),"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_ta_landscape(
    indication: str,
    mcp: MCPDispatcher,
    llm: LLMDispatcher,
    *,
    total_cap_per_source: int = 3000,
) -> TAResult:
    """identify (reused) → extract → score → assemble. Returns a TAResult ready
    for the memo renderer. Does NOT touch criteria.py or run coi_first."""
    plan = ta_search_plan(indication)
    corpus, prisma = identify(plan, mcp, total_cap_per_source=total_cap_per_source)
    citations_index = build_citations_index(corpus)
    log.info("ta: %d records identified for %s", len(corpus), indication)

    candidates, ex_report = extract_candidate_cois(corpus, indication, llm, citations_index)
    scores, sc_report = score_cois(candidates, corpus, indication, llm, citations_index)

    notes = list(RUN_NOTES_V1)
    for tag, rep in (("extract", ex_report), ("score", sc_report)):
        if rep.get("parse_error"):
            notes.append(f"{tag} parse error: {rep['parse_error']}")
        if rep.get("orphan_citations_stripped"):
            notes.append(f"{tag}: {len(rep['orphan_citations_stripped'])} orphan citation(s) stripped")

    return TAResult(
        indication=indication,
        corpus_size=len(corpus),
        prisma=prisma,
        candidates=candidates,
        scores=scores,
        citations_index=citations_index,
        run_notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Human-review memo (markdown) + machine outputs
# ─────────────────────────────────────────────────────────────────────────────

_QUAD_TITLE = {
    "core_and_measurable": "Recommended — core & digitally measurable",
    "core_not_yet_measurable": "WHITE SPACE — core to the disease, no DHT precedent yet",
    "peripheral_but_measurable": "Consider — measurable but clinically peripheral",
    "peripheral_and_unmeasured": "Deprioritize — low on both axes",
}


def _cite_line(cids: list[str], citations_index: dict[str, Record], limit: int = 4) -> str:
    out = []
    for cid in cids[:limit]:
        rec = citations_index.get(cid)
        if rec:
            yr = f", {rec.year}" if rec.year else ""
            out.append(f"{cid} ({rec.title[:70]}{yr})")
        else:
            out.append(cid)
    more = f" +{len(cids) - limit} more" if len(cids) > limit else ""
    return "; ".join(out) + more


def render_memo(result: TAResult) -> str:
    L = [
        f"# TA-First COI Shortlist — {result.indication}",
        "",
        f"Corpus: **{result.corpus_size}** records "
        f"(CTG: {result.prisma.get('identification_by_source', {}).get('clinicaltrials', 0)}, "
        f"PubMed: {result.prisma.get('identification_by_source', {}).get('pubmed', 0)}; "
        f"after dedup: {result.prisma.get('after_dedup', result.corpus_size)}).",
        f"Candidate COIs surfaced: **{len(result.candidates)}** | scored: **{len(result.scores)}**.",
        "",
        "> V1 output for **human review**. Verify the shortlist, then run the "
        "coi_first pipeline on the accepted COIs. Draft criteria stubs are at the end.",
        "",
        "## Recommendation matrix (clinical importance × digital measurability)",
        "",
        "| COI | Importance | Measurability | Quadrant | Action |",
        "|---|:-:|:-:|---|---|",
    ]
    for s in sorted(result.scores,
                    key=lambda s: -(s.clinical_importance + s.digital_measurability)):
        L.append(
            f"| {s.coi} | {s.clinical_importance}/5 | {s.digital_measurability}/5 | "
            f"{s.quadrant.replace('_', ' ')} | **{s.recommendation}** |"
        )

    # Grouped detail by recommendation bucket
    for bucket in ("recommend", "consider", "white_space", "deprioritize"):
        group = [s for s in result.scores if s.recommendation == bucket]
        if not group:
            continue
        L += ["", f"## {_QUAD_TITLE[_quadrant_for_rec(bucket, group[0])]}", ""]
        for s in group:
            cand = result.candidate_for(s.coi)
            L += [
                f"### {cand.label if cand else s.coi}  (`{s.coi}`)",
                f"- **Clinical importance {s.clinical_importance}/5** — {s.clinical_importance_rationale}",
                f"- **Digital measurability {s.digital_measurability}/5** — {s.digital_measurability_rationale}",
            ]
            if cand:
                if cand.literature_vocabulary:
                    L.append(f"- **Literature vocabulary:** {', '.join(cand.literature_vocabulary)}")
                if cand.dht_precedent:
                    L.append(f"- **DHT precedent:** {cand.dht_precedent}")
                L.append(f"- **Evidence:** {_cite_line(cand.evidence_citations, result.citations_index)}")
            L.append("")

    L += ["## Draft criteria.py stubs (recommended + consider COIs)", "",
          "```python", "# Paste accepted entries into criteria.py's CRITERIA dict.",
          "# Every entry is DRAFT — review inclusion lines and positive_signals first.", ""]
    for s in result.recommended():
        cand = result.candidate_for(s.coi)
        if cand:
            L.append(render_criteria_stub_block(cand))
            L.append("")
    L += ["```", "", "## Run notes", ""]
    L += [f"- {n}" for n in result.run_notes]
    return "\n".join(L)


def _quadrant_for_rec(rec: str, sample: COIScore) -> str:
    return {"recommend": "core_and_measurable", "consider": "peripheral_but_measurable",
            "white_space": "core_not_yet_measurable",
            "deprioritize": "peripheral_and_unmeasured"}[rec]


def result_as_json(result: TAResult) -> dict:
    return {
        "indication": result.indication,
        "corpus_size": result.corpus_size,
        "prisma": result.prisma,
        "candidates": [c.as_dict() for c in result.candidates],
        "scores": [s.as_dict() for s in result.scores],
        "recommended_cois": [s.coi for s in result.recommended()],
        "white_space_cois": [s.coi for s in result.white_space()],
        "run_notes": result.run_notes,
    }


__all__ = [
    "CandidateCOI", "COIScore", "TAResult", "LLMDispatcher",
    "ta_search_plan", "extract_candidate_cois", "score_cois",
    "criteria_stub_for", "render_criteria_stub_block",
    "run_ta_landscape", "render_memo", "result_as_json",
]