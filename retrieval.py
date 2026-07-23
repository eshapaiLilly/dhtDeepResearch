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
 
 
def _normalize_europepmc(payload: dict, query: str) -> Record | None:
    """Europe PMC search result -> Record.
 
    Europe PMC is a single API over PubMed/MEDLINE (source="MED"), PMC
    full text (source="PMC"), and — the reason we added it — preprints from
    bioRxiv/medRxiv/ChemRxiv (source="PPR"). One channel, three-plus sources.
 
    Source labelling: PPR hits are tagged source="biorxiv" (the RecordSource
    literal already covers this), everything else "pubmed". Dedup then
    collapses any Europe PMC MED hit against a direct-E-utilities PubMed hit
    with the same DOI/PMID, and prefers the published version over a preprint
    when both exist (pubmed priority 1 < biorxiv priority 2). So Europe PMC
    mostly *adds* preprints plus any peer-reviewed papers the direct PubMed
    query missed, without double-counting.
 
    NOTE: field paths follow Europe PMC's documented core resultType
    (id/source/pmid/pmcid/doi/title/authorString/journalTitle/pubYear/
    abstractText/firstPublicationDate). Verify these live against a real
    response before fully trusting the channel — the same live-shape check
    the CTG/PubMed handlers in live_clients.py went through.
    """
    src_raw = (payload.get("source") or "").upper()
    doi = payload.get("doi")
    pmid = payload.get("pmid")
    epmc_id = payload.get("id")
 
    if doi:
        citation_id = f"DOI:{doi}"
    elif pmid:
        citation_id = f"PMID:{pmid}"
    elif epmc_id:
        citation_id = f"EPMC:{epmc_id}"
    else:
        log.warning("Europe PMC payload missing DOI/PMID/id; skipping")
        return None
 
    record_source = "biorxiv" if src_raw == "PPR" else "pubmed"
    year = _safe_int(payload.get("pubYear")) or _safe_int(
        (payload.get("firstPublicationDate") or "")[:4]
    )
    author_string = payload.get("authorString")
 
    return Record(
        citation_id=citation_id,
        source=record_source,
        title=payload.get("title", "") or "",
        year=year,
        authors=[author_string] if author_string else [],
        pmid=str(pmid) if pmid else None,
        doi=doi,
        journal=payload.get("journalTitle") or payload.get("source"),
        abstract=payload.get("abstractText"),
        raw=payload,
        retrieved_query=query,
    )
 
 
def _safe_int(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None
 
 
def _normalize_semanticscholar(payload: dict, query: str) -> Record | None:
    """Semantic Scholar Graph API paper -> Record.
 
    S2's externalIds dict may carry DOI / PubMed / PubMedCentral / ArXiv,
    depending on what the paper has. Priority mirrors the rest of this
    module: DOI > PMID > a S2-specific fallback ID (paperId), so dedup
    against PubMed/CTG/EuropePMC records collapses correctly on shared
    DOI/PMID rather than creating a duplicate S2-only entry for the same
    paper.
 
    S2 doesn't cleanly separate preprints from peer-reviewed the way
    EuropePMC's `source` field does; venue text is the only signal
    available, so a venue containing "bioRxiv"/"medRxiv"/"arXiv" is tagged
    source="biorxiv", everything else "pubmed" — same convention as
    _normalize_europepmc, and the same caveat: verify field paths
    (externalIds keys, authors[].name) against a live response before fully
    trusting this channel.
    """
    ext = payload.get("externalIds") or {}
    doi = ext.get("DOI")
    pmid = ext.get("PubMed")
    s2_id = payload.get("paperId")
 
    if doi:
        citation_id = f"DOI:{doi}"
    elif pmid:
        citation_id = f"PMID:{pmid}"
    elif s2_id:
        citation_id = f"S2:{s2_id}"
    else:
        log.warning("Semantic Scholar payload missing DOI/PMID/paperId; skipping")
        return None
 
    venue = (payload.get("venue") or "")
    is_preprint = any(v in venue.lower() for v in ("biorxiv", "medrxiv", "arxiv"))
    record_source = "biorxiv" if is_preprint else "pubmed"
 
    authors = [a.get("name") for a in (payload.get("authors") or []) if a.get("name")]
 
    return Record(
        citation_id=citation_id,
        source=record_source,
        title=payload.get("title", "") or "",
        year=_safe_int(payload.get("year")),
        authors=authors,
        pmid=str(pmid) if pmid else None,
        doi=doi,
        journal=venue or None,
        abstract=payload.get("abstract"),
        raw=payload,
        retrieved_query=query,
    )
 
 
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
# Pagination — per-source loops, each respecting that source's real ceiling
# ─────────────────────────────────────────────────────────────────────────────
 
_CTG_MAX_PAGE_SIZE = 1000        # ClinicalTrials.gov v2 hard ceiling on pageSize
_PUBMED_MAX_ACCESSIBLE = 10_000  # NCBI esearch hard ceiling: retstart + retmax <= 10,000
 
 
def _paginate_ctg(
    mcp: MCPDispatcher,
    query_args: dict,
    page_size: int,
    total_cap: int,
) -> tuple[list[dict], bool]:
    """Loop ClinicalTrials.gov v2 pages via nextPageToken until either the
    query is genuinely exhausted (no nextPageToken, or an empty page) or
    total_cap studies have been collected.
 
    Returns (studies, capped) — `capped` is True iff we stopped because of
    total_cap rather than real exhaustion, i.e. more results existed than
    we chose to pull. This is what lets prisma_counts distinguish "we saw
    everything" from "we stopped early."
    """
    page_size = min(page_size, _CTG_MAX_PAGE_SIZE)
    studies: list[dict] = []
    page_token: str | None = None
 
    while True:
        args = {**query_args, "pageSize": page_size}
        if page_token:
            args["pageToken"] = page_token
        result = _dispatch_mcp(mcp, "ClinicalTrials:search_trials", args)
        page_studies = result.get("studies", []) if isinstance(result, dict) else []
        studies.extend(page_studies)
 
        if len(studies) >= total_cap:
            more_available = bool(result.get("nextPageToken")) if isinstance(result, dict) else False
            return studies[:total_cap], more_available
 
        page_token = result.get("nextPageToken") if isinstance(result, dict) else None
        if not page_token or not page_studies:
            return studies, False  # genuinely exhausted, not capped
 
 
def _paginate_pubmed(
    mcp: MCPDispatcher,
    query_args: dict,
    page_size: int,
    total_cap: int,
) -> tuple[list[dict], bool]:
    """Loop PubMed pages via retstart until either the query is exhausted
    (retstart has covered NCBI's reported total count), NCBI's hard
    10,000-record esearch ceiling is reached, or total_cap articles have
    been collected.
 
    Returns (articles, capped) — same contract as _paginate_ctg above.
    Requires the PubMed:search_articles MCP tool to accept a `retstart`
    arg and return `count` (NCBI's true total for the query, not just this
    page's size) alongside `articles` — see live_clients.py's
    _pubmed_search_articles for the reference implementation.
    """
    articles: list[dict] = []
    retstart = 0
 
    while True:
        room = min(page_size, _PUBMED_MAX_ACCESSIBLE - retstart)
        if room <= 0:
            return articles[:total_cap], True  # hit NCBI's hard ceiling — capped by definition
 
        args = {**query_args, "max_results": room, "retstart": retstart}
        result = _dispatch_mcp(mcp, "PubMed:search_articles", args)
        page_articles = result.get("articles", []) if isinstance(result, dict) else []
        count = result.get("count", 0) if isinstance(result, dict) else 0
        articles.extend(page_articles)
 
        if len(articles) >= total_cap:
            more_available = (retstart + len(page_articles)) < count
            return articles[:total_cap], more_available
 
        if not page_articles:
            return articles, False  # empty page — treat as exhausted regardless of reported count
 
        retstart += len(page_articles)
        if retstart >= count:
            return articles, False  # genuinely exhausted
 
 
_EPMC_MAX_PAGE_SIZE = 1000  # Europe PMC JSON pageSize ceiling
 
 
def _paginate_europepmc(
    mcp: MCPDispatcher,
    query_args: dict,
    page_size: int,
    total_cap: int,
) -> tuple[list[dict], bool]:
    """Loop Europe PMC pages via cursorMark until the query is exhausted
    (nextCursorMark stops advancing, or an empty page) or total_cap results
    have been collected. Same (results, capped) contract as the other
    paginators.
 
    Europe PMC paginates with an opaque cursorMark starting at "*"; when the
    server returns a nextCursorMark equal to the one just sent (or omits it),
    the result set is exhausted. Requires the EuropePMC:search tool to accept
    `cursorMark`/`pageSize` and return {"results", "hitCount",
    "nextCursorMark"} — see live_clients.py's _europepmc_search.
    """
    page_size = min(page_size, _EPMC_MAX_PAGE_SIZE)
    results: list[dict] = []
    cursor = "*"
    seen: set[str] = set()
 
    while True:
        args = {**query_args, "pageSize": page_size, "cursorMark": cursor}
        result = _dispatch_mcp(mcp, "EuropePMC:search", args)
        page = result.get("results", []) if isinstance(result, dict) else []
        hit_count = result.get("hitCount", 0) if isinstance(result, dict) else 0
        results.extend(page)
 
        if len(results) >= total_cap:
            more_available = len(results) < hit_count
            return results[:total_cap], more_available
 
        next_cursor = result.get("nextCursorMark") if isinstance(result, dict) else None
        # Exhausted: empty page, no/blank next cursor, or cursor didn't advance.
        if not page or not next_cursor or next_cursor == cursor or next_cursor in seen:
            return results, False
        seen.add(cursor)
        cursor = next_cursor
 
 
_S2_MAX_PAGE_SIZE = 100  # Semantic Scholar search endpoint's per-call limit


def _paginate_semanticscholar(
    mcp: MCPDispatcher,
    query_args: dict,
    page_size: int,
    total_cap: int,
) -> tuple[list[dict], bool]:
    """Loop Semantic Scholar BULK search pages via `token` until the query
    is exhausted (no token returned, or an empty page) or total_cap results
    have been collected. Same (results, capped) contract as the other
    paginators, but the pagination mechanism itself is different from every
    other source here: bulk search has no client-controlled page size
    (server decides, observed ~1000/page) and no offset — it's a pure
    continuation token, so `page_size` is accepted for interface
    consistency with the other _paginate_* functions but unused here.

    live_clients._semanticscholar_search returns `total` (true match count,
    same "true total vs. this page's size" signal _paginate_pubmed uses)
    and `token` (absent once the result set is exhausted).
    """
    results: list[dict] = []
    token: str | None = None

    while True:
        args = dict(query_args)
        if token:
            args["token"] = token
        result = _dispatch_mcp(mcp, "SemanticScholar:search", args)
        page = result.get("data", []) if isinstance(result, dict) else []
        total = result.get("total", 0) if isinstance(result, dict) else 0
        results.extend(page)

        if len(results) >= total_cap:
            more_available = len(results) < total
            return results[:total_cap], more_available

        next_token = result.get("token") if isinstance(result, dict) else None
        if not page or not next_token:
            return results, False  # exhausted
        token = next_token


# ─────────────────────────────────────────────────────────────────────────────
# Identification stage: the node-level entry point
# ─────────────────────────────────────────────────────────────────────────────
 
def identify(
    search_plan: dict,
    mcp: MCPDispatcher,
    *,
    page_size: int = 1000,
    total_cap_per_source: int = 5000,
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
 
    `page_size`: per-HTTP-call size, internally clamped to each source's
    real ceiling (1000 for CTG, NCBI's 10k-retstart ceiling for PubMed).
    You generally don't need to tune this per source — it's page
    mechanics, not the breadth knob.
 
    `total_cap_per_source`: the actual breadth knob — how many records per
    source per query this pipeline will accumulate across pages before
    moving on. Raise this to widen recall; both sources' real ceilings sit
    at or above 5000 for any query this pipeline has run so far, so this
    default is a starting point, not a hard limit worth leaving untouched.
 
    prisma_counts shape:
      {"identification_by_source": {"clinicaltrials": N, "pubmed": M},
       "identification_total": N+M,
       "identification_capped_by_source": {"clinicaltrials": bool, "pubmed": bool},
       "after_dedup": K}
 
    `identification_capped_by_source` is True for a source iff
    total_cap_per_source (not real exhaustion) is why that source's
    pagination loop stopped, for ANY query targeting that source in this
    search_plan — one capped query is enough to mark the whole source
    capped, since the PRISMA count for that source is then a lower bound,
    not a final figure.
    """
    raw: list[Record] = []
    by_source: Counter[str] = Counter()
    capped_by_source: dict[str, bool] = {}
 
    # --- ClinicalTrials.gov v2 ---
    for query_args in search_plan.get("clinicaltrials", []):
        studies, capped = _paginate_ctg(mcp, query_args, page_size, total_cap_per_source)
        by_source["clinicaltrials"] += len(studies)
        capped_by_source["clinicaltrials"] = capped_by_source.get("clinicaltrials", False) or capped
        query_str = str(query_args)
        for s in studies:
            rec = _normalize_ctg(s, query_str)
            if rec:
                raw.append(rec)
 
    # --- PubMed ---
    for query_args in search_plan.get("pubmed", []):
        articles, capped = _paginate_pubmed(mcp, query_args, page_size, total_cap_per_source)
        by_source["pubmed"] += len(articles)
        capped_by_source["pubmed"] = capped_by_source.get("pubmed", False) or capped
        query_str = str(query_args)
        for a in articles:
            rec = _normalize_pubmed(a, query_str)
            if rec:
                raw.append(rec)
 
    # --- Europe PMC (bioRxiv/medRxiv preprints + peer-reviewed recall) ---
    # One channel, source="PPR" hits become biorxiv-tagged Records, MED/PMC
    # hits become pubmed-tagged and dedup against the direct PubMed lane.
    for query_args in search_plan.get("europepmc", []):
        epmc_results, capped = _paginate_europepmc(mcp, query_args, page_size, total_cap_per_source)
        by_source["europepmc"] += len(epmc_results)
        capped_by_source["europepmc"] = capped_by_source.get("europepmc", False) or capped
        query_str = str(query_args)
        for a in epmc_results:
            rec = _normalize_europepmc(a, query_str)
            if rec:
                raw.append(rec)
 
    # (Cortellis can be added the same way — add a normalizer + a paginator
    #  + a channel loop here, and a route in live_clients.py.)

    # --- Semantic Scholar (independent index; different host than Europe
    #     PMC, so unaffected by any EBI-specific network/cert issue) ---
    for query_args in search_plan.get("semanticscholar", []):
        s2_results, capped = _paginate_semanticscholar(mcp, query_args, page_size, total_cap_per_source)
        by_source["semanticscholar"] += len(s2_results)
        capped_by_source["semanticscholar"] = capped_by_source.get("semanticscholar", False) or capped
        query_str = str(query_args)
        for a in s2_results:
            rec = _normalize_semanticscholar(a, query_str)
            if rec:
                raw.append(rec)

 
    deduped = deduplicate(raw)
 
    prisma = {
        "identification_by_source": dict(by_source),
        "identification_total": sum(by_source.values()),
        "identification_capped_by_source": capped_by_source,
        "after_dedup": len(deduped),
    }
 
    log.info(
        "identify: %d raw across sources %s (capped=%s) → %d after dedup",
        prisma["identification_total"],
        prisma["identification_by_source"],
        capped_by_source,
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