"""
retrieval.py — MCP-driven identification stage of the DHT pipeline.

Responsibilities
----------------
1. Call ClinicalTrials.gov v2 and PubMed (via Anthropic MCP servers) with the
   per-COI search plan produced by the router.
2. Normalize each raw payload into a `Record` with a STABLE citation_id.
3. Deduplicate across sources (NCT > DOI > PMID > normalized-title).
4. Log per-source hit counts into `prisma_counts.identification_by_source` so
   the PRISMA flow diagram can be drawn from real numbers.

Design notes
------------
- Retrieval is DETERMINISTIC. No LLM here. The identification stage is what
  makes the pipeline auditable — a reviewer must be able to re-run the same
  queries and get the same corpus.
- MCP tools are deferred; in the LangGraph node this module runs inside, the
  MCP client is passed in (dependency-injected) so tests can stub it.
- The `_dispatch_mcp` shim isolates the MCP-call surface. In Esha's runtime
  this dispatches to real tools like `ClinicalTrials:search_trials` and
  `PubMed:search_articles`. In tests it dispatches to a fake.
- Citation IDs: NCT_ID for trials, `PMID:<id>` for PubMed, `DOI:<doi>` for
  preprints. Once assigned, NEVER regenerated downstream.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import replace
from typing import Any, Callable, Iterable

from state import Record, SponsorClass, InterventionType


log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# MCP dispatch shim
# ─────────────────────────────────────────────────────────────────────────────
# In the LangGraph node, this is bound to the real MCP client. In tests, to a
# fake. Keeping the shim thin means retrieval.py has no hard dependency on the
# MCP transport.

MCPDispatcher = Callable[[str, dict], dict]


def _dispatch_mcp(client: MCPDispatcher, tool_name: str, args: dict) -> dict:
    """Call an MCP tool and return the parsed result payload."""
    return client(tool_name, args)


# ─────────────────────────────────────────────────────────────────────────────
# Normalization: raw MCP payload → Record
# ─────────────────────────────────────────────────────────────────────────────

def _classify_sponsor(sponsor_class_raw: str | None) -> SponsorClass:
    """ClinicalTrials.gov `leadSponsorClass` enum → our normalized enum."""
    if not sponsor_class_raw:
        return "UNKNOWN"
    s = sponsor_class_raw.upper()
    if s in ("INDUSTRY",):
        return "INDUSTRY"
    if s in ("NIH", "US_FED", "OTHER_GOV", "NETWORK", "AMBIG"):
        return "OTHER"
    if s in ("OTHER",):     # academic often falls here in CTG classification
        return "ACADEMIC"
    return "UNKNOWN"


def _classify_intervention(intervention_types: Iterable[str]) -> InterventionType:
    """ClinicalTrials.gov `interventionType` list → our primary type."""
    types = {t.upper() for t in intervention_types or []}
    # Priority order: DEVICE and DRUG signal endpoint-relevant studies most strongly.
    if "DRUG" in types:
        return "DRUG"
    if "DEVICE" in types:
        return "DEVICE"
    if "BEHAVIORAL" in types:
        return "BEHAVIORAL"
    if "DIAGNOSTIC_TEST" in types:
        return "DIAGNOSTIC"
    if types:
        return "OTHER"
    return "UNKNOWN"


def _normalize_ctg(payload: dict, query: str) -> Record | None:
    """ClinicalTrials.gov v2 study payload → Record.

    Field paths follow the OpenAPI v2 schema:
      protocolSection.identificationModule.nctId
      protocolSection.identificationModule.briefTitle
      protocolSection.statusModule.overallStatus
      protocolSection.designModule.phases
      protocolSection.sponsorCollaboratorsModule.leadSponsor
      protocolSection.armsInterventionsModule.interventions
      protocolSection.outcomesModule.primaryOutcomes / secondaryOutcomes
      protocolSection.designModule.enrollmentInfo.count
      protocolSection.conditionsModule.conditions
    """
    try:
        proto = payload["protocolSection"]
        ident = proto["identificationModule"]
        nct_id = ident["nctId"]
    except KeyError:
        log.warning("CTG payload missing nctId; skipping")
        return None

    status = proto.get("statusModule", {}).get("overallStatus")
    phases = proto.get("designModule", {}).get("phases", []) or []
    phase = phases[0] if phases else None
    enrollment = (
        proto.get("designModule", {}).get("enrollmentInfo", {}).get("count")
    )

    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
    lead = sponsor_mod.get("leadSponsor", {})
    sponsor_name = lead.get("name")
    sponsor_class = _classify_sponsor(lead.get("class"))

    interventions = proto.get("armsInterventionsModule", {}).get("interventions", []) or []
    intervention_names = [i.get("name") for i in interventions if i.get("name")]
    intervention_type = _classify_intervention(i.get("type") for i in interventions)

    outcomes_mod = proto.get("outcomesModule", {})
    outcome_names = [
        o.get("measure")
        for o in (outcomes_mod.get("primaryOutcomes", []) or [])
        + (outcomes_mod.get("secondaryOutcomes", []) or [])
        if o.get("measure")
    ]

    conditions = proto.get("conditionsModule", {}).get("conditions", []) or []

    # Extract year from study start or first-posted date if available
    year = None
    for date_field in ("startDateStruct", "studyFirstPostDateStruct"):
        d = proto.get("statusModule", {}).get(date_field, {}).get("date")
        if d and len(d) >= 4:
            try:
                year = int(d[:4])
                break
            except ValueError:
                pass

    return Record(
        citation_id=nct_id,       # NCT ID is already canonical + stable
        source="clinicaltrials",
        title=ident.get("briefTitle", ""),
        year=year,
        nct_id=nct_id,
        phase=phase,
        status=status,
        sponsor=sponsor_name,
        sponsor_class=sponsor_class,
        intervention="; ".join(intervention_names) if intervention_names else None,
        intervention_type=intervention_type,
        enrollment=enrollment,
        condition="; ".join(conditions) if conditions else None,
        outcome_measures=outcome_names,
        raw=payload,
        retrieved_query=query,
    )


def _normalize_pubmed(payload: dict, query: str) -> Record | None:
    """PubMed article payload → Record.

    Exact field paths depend on which PubMed MCP tool is called; this handles
    both the common `pubmed.ncbi.nlm.nih.gov` E-utilities shape and the
    Anthropic PubMed MCP `get_article_metadata` shape (which returns a
    flattened dict).
    """
    pmid = payload.get("pmid") or payload.get("uid") or payload.get("PMID")
    if not pmid:
        log.warning("PubMed payload missing PMID; skipping")
        return None
    pmid = str(pmid)

    return Record(
        citation_id=f"PMID:{pmid}",
        source="pubmed",
        title=payload.get("title", ""),
        year=_safe_int(payload.get("year") or payload.get("pubdate", "")[:4]),
        authors=payload.get("authors", []) or [],
        pmid=pmid,
        doi=payload.get("doi"),
        journal=payload.get("journal") or payload.get("source"),
        abstract=payload.get("abstract"),
        raw=payload,
        retrieved_query=query,
    )


def _safe_int(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")


def _title_key(title: str) -> str:
    """Normalized title for fuzzy dedup (lowercase, punctuation stripped)."""
    if not title:
        return ""
    t = title.lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t


def _dedup_key(record: Record) -> str:
    """Priority: NCT > DOI > PMID > normalized title.

    A PubMed article about NCTXXXXXXXX and the CTG record for the same trial
    should collapse — CTG wins because it has structured metadata.
    """
    if record.nct_id:
        return f"nct:{record.nct_id}"
    if record.doi:
        return f"doi:{record.doi.lower()}"
    if record.pmid:
        return f"pmid:{record.pmid}"
    return f"title:{_title_key(record.title)}"


def deduplicate(records: list[Record]) -> list[Record]:
    """Collapse duplicates. CTG records preferred over PubMed for the same trial."""
    by_key: dict[str, Record] = {}
    source_priority = {"clinicaltrials": 0, "pubmed": 1, "biorxiv": 2, "cortellis": 3}
    for r in records:
        k = _dedup_key(r)
        if k not in by_key:
            by_key[k] = r
            continue
        # Keep the higher-priority source (lower number wins)
        if source_priority.get(r.source, 99) < source_priority.get(by_key[k].source, 99):
            by_key[k] = r
    return list(by_key.values())


# ─────────────────────────────────────────────────────────────────────────────
# Identification stage: the node-level entry point
# ─────────────────────────────────────────────────────────────────────────────

def identify(
    search_plan: dict,
    mcp: MCPDispatcher,
    *,
    max_per_query: int = 100,
) -> tuple[list[Record], dict]:
    """Run the identification stage. Returns (deduplicated records, prisma counts).

    search_plan shape:
      {
        "clinicaltrials": [
          {"query.cond": "COPD", "query.outc": "moderate to vigorous physical activity"},
          ...
        ],
        "pubmed": [
          {"query": "COPD AND (MVPA OR \"moderate-to-vigorous physical activity\")"},
          ...
        ],
      }

    prisma_counts shape:
      {"identification_by_source": {"clinicaltrials": N, "pubmed": M},
       "identification_total": N+M,
       "after_dedup": K}
    """
    raw: list[Record] = []
    by_source: Counter[str] = Counter()

    # --- ClinicalTrials.gov v2 ---
    for query_args in search_plan.get("clinicaltrials", []):
        args = {**query_args, "pageSize": max_per_query}
        result = _dispatch_mcp(mcp, "ClinicalTrials:search_trials", args)
        # v2 returns {"studies": [...], "nextPageToken": ...}
        studies = result.get("studies", []) if isinstance(result, dict) else []
        by_source["clinicaltrials"] += len(studies)
        query_str = str(query_args)
        for s in studies:
            rec = _normalize_ctg(s, query_str)
            if rec:
                raw.append(rec)

    # --- PubMed ---
    for query_args in search_plan.get("pubmed", []):
        args = {**query_args, "max_results": max_per_query}
        result = _dispatch_mcp(mcp, "PubMed:search_articles", args)
        articles = (
            result.get("articles", []) if isinstance(result, dict) else []
        ) or (result.get("results", []) if isinstance(result, dict) else [])
        by_source["pubmed"] += len(articles)
        query_str = str(query_args)
        for a in articles:
            rec = _normalize_pubmed(a, query_str)
            if rec:
                raw.append(rec)



    # (bioRxiv / Cortellis can be added the same way; omitted here for brevity.)

    deduped = deduplicate(raw)

    prisma = {
        "identification_by_source": dict(by_source),
        "identification_total": sum(by_source.values()),
        "after_dedup": len(deduped),
    }

    log.info(
        "identify: %d raw across sources %s → %d after dedup",
        prisma["identification_total"],
        prisma["identification_by_source"],
        prisma["after_dedup"],
    )
    return deduped, prisma


# ─────────────────────────────────────────────────────────────────────────────
# Citation index construction
# ─────────────────────────────────────────────────────────────────────────────

def build_citations_index(corpus: list[Record]) -> dict[str, Record]:
    """After eligibility, freeze the citations_index.

    A citation in the final report is valid iff its token appears here as a key.
    The verify node uses this set for orphan detection.
    """
    return {r.citation_id: r for r in corpus}


__all__ = [
    "identify",
    "deduplicate",
    "build_citations_index",
    "MCPDispatcher",
]