"""
state.py — typed state schema for the DHT landscape pipeline (Architecture C).

Design principles
-----------------
1. State is the audit trail. Every field is either populated by a deterministic
   Python node (retrieval, screening, stats, verification) or by a skill-driven
   Claude node (evidence, device, gap, synthesis). If a reviewer asks "where did
   this claim come from?" the answer is always a walk from the final report
   back through this state to a specific record in `corpus` with a
   `citation_id` that resolves in `citations_index`.

2. `override_reducer` (borrowed from langchain-ai/open_deep_research) lets a
   node either APPEND to a list channel or HARD-RESET it by emitting
   `{"type": "override", "value": [...]}`. This is essential for two things:
     - Resetting the corpus between COIs when the graph is reused per-COI.
     - Letting the `verify` node strip orphan citations from the citations_index
       without appending duplicates.

3. Records carry stable citation IDs from the moment they're retrieved. IDs are
   assigned in `retrieval.py` and NEVER regenerated downstream. This is what
   makes the verify node's set-membership check possible: an orphan is any
   token that looks like a citation but isn't in `citations_index`.

4. PRISMA counts are populated at each pipeline transition. Circadic's "937 →
   203" funnel is a byproduct of these counters, not a fabricated figure.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field, asdict
from typing import Annotated, Any, Literal, TypedDict


# ─────────────────────────────────────────────────────────────────────────────
# Reducer
# ─────────────────────────────────────────────────────────────────────────────

def override_reducer(current: list, new: Any) -> list:
    """Append by default; hard-reset if `new` is {"type": "override", "value": [...]}.

    LangGraph reducers must be pure functions of (current_channel_value,
    node_return_value) → new_channel_value. When a node returns
    `{"channel": {"type": "override", "value": [...]}}`, we replace instead
    of append — useful for resetting per-COI corpora or rewriting the
    citations_index after verification.
    """
    if isinstance(new, dict) and new.get("type") == "override":
        return new.get("value", [])
    return operator.add(current or [], new or [])


def dict_override_or_merge(current: dict, new: Any) -> dict:
    """Reducer for dict channels. Merge by default; hard-reset on override.

    The verify node prunes orphan citations by emitting the trimmed dict as
    an override rather than trying to compute a diff.
    """
    if isinstance(new, dict) and new.get("type") == "override":
        return new.get("value", {})
    merged = dict(current or {})
    merged.update(new or {})
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Records: the atomic unit of retrieved evidence
# ─────────────────────────────────────────────────────────────────────────────

RecordSource = Literal["pubmed", "clinicaltrials", "biorxiv", "cortellis"]
SponsorClass = Literal["INDUSTRY", "ACADEMIC", "OTHER", "UNKNOWN"]
InterventionType = Literal["DRUG", "DEVICE", "BEHAVIORAL", "DIAGNOSTIC", "OTHER", "UNKNOWN"]


@dataclass
class Record:
    """One retrieved study/paper. The atomic citable unit.

    `citation_id` is the ONLY thing downstream nodes are allowed to cite.
    Assigned once at retrieval time (e.g., "NCT04413344", "PMID:28527205").
    A citation in the final report is valid iff its citation_id resolves here.
    """
    citation_id: str                # canonical, stable — the citation token
    source: RecordSource            # which MCP server produced this
    title: str
    year: int | None = None
    authors: list[str] = field(default_factory=list)

    # ClinicalTrials.gov fields
    nct_id: str | None = None
    phase: str | None = None
    status: str | None = None
    sponsor: str | None = None
    sponsor_class: SponsorClass = "UNKNOWN"
    intervention: str | None = None
    intervention_type: InterventionType = "UNKNOWN"
    enrollment: int | None = None
    condition: str | None = None
    outcome_measures: list[str] = field(default_factory=list)

    # PubMed / bioRxiv fields
    pmid: str | None = None
    doi: str | None = None
    journal: str | None = None
    abstract: str | None = None

    # DHT-specific extracted metadata (populated during screening/eligibility)
    device: str | None = None
    wear_location: str | None = None
    endpoint_class: str | None = None   # e.g., "physical_activity", "sleep"
    digital_endpoint: str | None = None # e.g., "MVPA minutes", "step count"

    # Provenance
    raw: dict = field(default_factory=dict)   # original API payload, for audit
    retrieved_query: str | None = None        # exact query that surfaced this

    def as_dict(self) -> dict:
        return asdict(self)

    def to_prompt_text(self) -> str:
        """Render as a compact text block for Claude document input.

        The Citations API will anchor cited_text spans to positions within
        this string, so keep the format stable and include everything a
        synthesis node might need to cite.
        """
        parts = [f"[{self.citation_id}] {self.title}"]
        if self.year:
            parts.append(f"Year: {self.year}")
        if self.nct_id:
            parts.append(f"NCT: {self.nct_id} | Phase: {self.phase} | Status: {self.status}")
            parts.append(f"Sponsor: {self.sponsor} ({self.sponsor_class})")
            parts.append(f"Intervention: {self.intervention} ({self.intervention_type})")
            if self.enrollment:
                parts.append(f"N = {self.enrollment}")
            if self.outcome_measures:
                parts.append("Outcome measures: " + "; ".join(self.outcome_measures))
        if self.pmid:
            parts.append(f"PMID: {self.pmid} | Journal: {self.journal}")
        if self.device:
            parts.append(f"Device: {self.device} | Wear location: {self.wear_location}")
        if self.abstract:
            parts.append(f"Abstract: {self.abstract}")
        return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Analytical outputs (produced by skill-driven nodes)
# ─────────────────────────────────────────────────────────────────────────────

GateVerdict = Literal["PASS", "FAIL", "CONDITIONAL"]


@dataclass
class COIEvidence:
    """Output of the evidence node for one COI. Every citation must be a
    citation_id that exists in DHTState.citations_index."""
    coi: str
    clinical_definition: str
    gate_verdicts: dict[str, GateVerdict]         # {"disease_relevance": "PASS", ...}
    gate_rationale: dict[str, str]                # each ends with [citation_id]
    evidence_strength: Literal["STRONG", "MODERATE", "EMERGING", "WEAK"]
    endpoint_role_recommendation: Literal["PRIMARY", "SECONDARY", "EXPLORATORY"]
    key_citations: list[str]                      # citation_ids only
    measurement_spec: dict                        # metric, epoch, algorithm, valid-day rule


@dataclass
class DeviceRow:
    """One row of the device comparison table. Grounded in retrieved device
    metadata — the `evidence_citations` list must contain citation_ids that
    support each claim in the row."""
    coi: str
    device: str
    manufacturer: str
    regulatory_clearance: str | None
    wear_location: str | None
    measures_supported: list[str]
    v3_evidence: dict          # {"verification": "...", "analytical": "...", "clinical": "..."}
    limitations: str | None
    evidence_citations: list[str]


@dataclass
class Gap:
    gap_id: str                # e.g., "GAP-REG-01"
    category: Literal["regulatory", "clinical_trial", "statistical", "device", "internal_data"]
    description: str
    severity: Literal["blocking", "notable", "acknowledged"]
    affected_cois: list[str]
    action: str
    supporting_citations: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# PRISMA + verification tracking
# ─────────────────────────────────────────────────────────────────────────────

class PRISMACounts(TypedDict, total=False):
    """Populated at each pipeline transition. Becomes the PRISMA flow diagram.

    `screen_excluded_reasons` and `eligible_excluded_reasons` are kept as
    SEPARATE keys, not one shared `excluded_reasons` — screen.py and
    eligibility.py both run and both produce a Counter of exclusion codes,
    and prisma_counts merges dicts SHALLOWLY (top-level key replace, see
    dict_override_or_merge below). A shared key would mean eligibility's
    write silently clobbers screen's tally instead of both surviving. This
    also happens to match how a real PRISMA diagram wants it: exclusion
    reasons reported per-stage, not pooled.
    """
    identification_by_source: dict[str, int]   # {"pubmed": 512, "clinicaltrials": 388, ...}
    identification_total: int
    after_dedup: int
    screened: int
    screened_excluded: int
    screen_excluded_reasons: dict[str, int]        # {"wrong_population": 47, ...}
    eligible: int
    eligible_excluded: int
    eligible_excluded_reasons: dict[str, int]
    reversals_from_screen: int
    included: int


class VerifyReport(TypedDict, total=False):
    """Output of the verify node. Presence of orphans is a blocking condition
    for the docx builder — you don't ship a report with unresolvable citations."""
    orphan_citations: list[str]                # tokens in draft not in citations_index
    unresolved_citations: list[str]            # in index but ClinicalTrials/PubMed lookup failed
    entailment_failures: list[dict]            # [{"citation_id": ..., "claim": ..., "reason": ...}]
    n_citations_total: int
    n_citations_verified: int
    citation_precision: float                  # verified / total


# ─────────────────────────────────────────────────────────────────────────────
# The graph state
# ─────────────────────────────────────────────────────────────────────────────

class DHTState(TypedDict, total=False):
    """LangGraph state for the DHT landscape pipeline.

    `total=False` because nodes populate different channels at different
    stages. Reducers (`override_reducer`) let nodes append or hard-reset.

    Populated by (in order):
      router      → request, cois, indication, direction, search_plan, inclusion_criteria
      identify    → raw_records, prisma_counts (identification_*)
      screen      → screened_records, prisma_counts (screened*, screen_excluded_reasons)
      eligibility → corpus, citations_index, prisma_counts (eligible*, included, reversals_from_screen)
      evidence    → evidence  (skill: dht-landscape-scout, per-COI via Send)
      device      → devices   (skill: dht-measure-spec, per-COI)
      gap         → gaps      (skill: dht-str prompt-fragment, sees all COIs)
      corpus_stats→ figures, corpus_stats
      verify      → verify_report, citations_index (with orphans stripped)
      synthesize  → report_sections (skill: dht-str)
      build_docx  → final_report_path
    """
    # --- routing / request ---
    request: str
    indication: str
    cois: list[str]
    direction: Literal["coi_first", "measure_first", "device_first", "company_first"]
    #   ^ set by the router node. Only "coi_first" is wired end-to-end as of
    #     graph.py's first version — see dht-landscape-scout SKILL.md's Open
    #     Questions ledger item 3. The conditional edge in graph.py enforces
    #     this rather than silently mishandling an unsupported direction.
    search_plan: dict                                          # per-COI query terms
    inclusion_criteria: dict                                   # per-COI, from criteria.py

    # --- retrieval / corpus (deterministic Python) ---
    raw_records: Annotated[list[Record], override_reducer]
    screened_records: Annotated[list[Record], override_reducer]
    corpus: Annotated[list[Record], override_reducer]
    citations_index: Annotated[dict[str, Record], dict_override_or_merge]
    prisma_counts: Annotated[PRISMACounts, dict_override_or_merge]
    #   ^ FIXED: previously had no reducer at all, meaning eligibility's
    #     partial write would have replaced the whole dict and silently
    #     dropped identify's and screen's counts. Now each node's partial
    #     PRISMACounts dict merges into the running total.

    # --- analytical outputs (skill-driven) ---
    evidence: Annotated[list[COIEvidence], override_reducer]
    devices: Annotated[list[DeviceRow], override_reducer]
    gaps: list[Gap]

    # --- presentation ---
    figures: dict[str, str]                                    # path → caption
    corpus_stats: dict                                         # pandas-computed distributions
    report_sections: dict                                      # structured spec for docx builder
    final_report_path: str

    # --- verification ---
    verify_report: VerifyReport

    # --- meta ---
    run_id: str
    telemetry_path: str