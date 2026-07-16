"""
live_clients.py — real MCP dispatcher: ClinicalTrials.gov v2 + PubMed E-utilities.

Why direct REST instead of an actual MCP server connection
-------------------------------------------------------------
retrieval.py and eligibility.py were written against an `MCPDispatcher`
shim — `Callable[[str, dict], dict]` — deliberately so the retrieval logic
doesn't care HOW a tool call happens, only that calling
"ClinicalTrials:search_trials" with some args returns a dict. Both
ClinicalTrials.gov (api/v2) and PubMed (E-utilities) are PUBLIC, no-auth
REST APIs. Standing up a real MCP protocol client (the `mcp` Python SDK,
session negotiation, tool discovery) buys nothing over calling the public
REST endpoints directly — it's the exact same data, with an extra protocol
layer in between. So this module implements the four tool names our code
already calls as direct HTTP requests, live-verified against both APIs:

  ClinicalTrials:search_trials      → GET /api/v2/studies?query.cond=...&query.outc=...
  ClinicalTrials:get_trial_details  → GET /api/v2/studies/{nct_id}
  PubMed:search_articles            → esearch.fcgi (IDs) + efetch.fcgi (records)
  PubMed:get_article_metadata       → efetch.fcgi (single ID)

Both response shapes were checked live against the real APIs and match what
retrieval.py's _normalize_ctg/_normalize_pubmed and eligibility.py's
_merge_ctg_detail/_merge_pubmed_detail already expect — CTG passes through
essentially unmodified; PubMed's XML gets parsed into the flat dict shape
_normalize_pubmed wants (pmid, title, year, journal, abstract, doi).

Rate limiting
-------------
NCBI's usage policy caps unauthenticated E-utilities calls at ~3 requests/
second. This module throttles accordingly. If you get an NCBI API key
(free, instant, via an NCBI account), set NCBI_API_KEY in the environment —
this module will pick it up and you can raise the throttle to ~10 req/sec
by lowering _MIN_INTERVAL. Not done automatically here; deliberately
conservative by default so a first run doesn't get you rate-limited.

ClinicalTrials.gov v2 has no documented hard rate limit for reasonable use,
but this module throttles it lightly too, out of politeness.
"""
from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests


log = logging.getLogger(__name__)

CTG_BASE = "https://clinicaltrials.gov/api/v2"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

NCBI_API_KEY = os.environ.get("NCBI_API_KEY")  # optional; raises rate limit if set

_MIN_INTERVAL = 0.34  # ~3 req/sec, NCBI's unauthenticated guideline
_last_call_at = 0.0
_MAX_RETRIES = 3


def _throttle() -> None:
    global _last_call_at
    elapsed = time.monotonic() - _last_call_at
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_at = time.monotonic()


def _get_with_retry(url: str, params: dict, timeout: int) -> requests.Response:
    """GET with retry-on-429, exponential backoff.

    Added after a live run against a ~170-record MVPA/COPD corpus produced
    three 429s during eligibility's per-record PubMed enrichment — the
    baseline throttle (~3 req/sec) isn't always enough headroom once a
    session has made a couple hundred prior calls. Respects Retry-After if
    NCBI sends it; otherwise backs off 1s/2s/4s. After _MAX_RETRIES, raises
    so the caller's existing fault-tolerant fallback (enrich_record already
    catches exceptions and returns the un-enriched record) takes over —
    this doesn't change that contract, it just makes hitting it less likely.
    """
    for attempt in range(_MAX_RETRIES + 1):
        _throttle()
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        if attempt == _MAX_RETRIES:
            resp.raise_for_status()  # exhausted retries — raise the 429
        wait = float(resp.headers.get("Retry-After", 2 ** attempt))
        log.warning("live_clients: 429 from %s, retrying in %.1fs (attempt %d/%d)",
                    url, wait, attempt + 1, _MAX_RETRIES)
        time.sleep(wait)
    raise RuntimeError("unreachable")  # loop always returns or raises above


# ─────────────────────────────────────────────────────────────────────────────
# ClinicalTrials.gov v2 — live-verified shape, passes through near-unmodified
# ─────────────────────────────────────────────────────────────────────────────

def _ctg_search_trials(args: dict) -> dict:
    """GET /api/v2/studies. Returns {"studies": [...]} exactly as retrieval.py
    expects — confirmed live: studies[].protocolSection.identificationModule.nctId
    matches _normalize_ctg's field paths with no translation needed."""
    params = {k: v for k, v in args.items() if k != "pageSize"}
    params["pageSize"] = args.get("pageSize", 50)
    resp = _get_with_retry(f"{CTG_BASE}/studies", params, timeout=30)
    return resp.json()


def _ctg_get_trial_details(args: dict) -> dict:
    """GET /api/v2/studies/{nct_id}. Returns the study dict directly (top-level
    key is "protocolSection", confirmed live) — matches _merge_ctg_detail's
    expectation exactly, no wrapping needed."""
    nct_id = args["nct_id"]
    resp = _get_with_retry(f"{CTG_BASE}/studies/{nct_id}", {}, timeout=30)
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# PubMed E-utilities — esearch (IDs) + efetch (XML, parsed to flat dicts)
# ─────────────────────────────────────────────────────────────────────────────

def _pubmed_esearch(query: str, max_results: int) -> list[str]:
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    resp = _get_with_retry(f"{EUTILS_BASE}/esearch.fcgi", params, timeout=30)
    return resp.json().get("esearchresult", {}).get("idlist", [])


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Parse an efetch retmode=xml response (one or many <PubmedArticle>) into
    the flat dict shape retrieval.py's _normalize_pubmed and eligibility.py's
    _merge_pubmed_detail expect: pmid, title, year, journal, abstract, doi.

    Live-verified against a real efetch response (activPAL/ActiGraph COPD
    MVPA paper, PMID 42419359) during development of this module.
    """
    root = ET.fromstring(xml_text)
    out: list[dict] = []

    for article_el in root.findall(".//PubmedArticle"):
        pmid_el = article_el.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None else None
        if not pmid:
            continue

        title_el = article_el.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""

        journal_el = article_el.find(".//Journal/Title")
        journal = journal_el.text if journal_el is not None else None

        year = None
        year_el = article_el.find(".//JournalIssue/PubDate/Year")
        if year_el is not None and year_el.text:
            year = _safe_int(year_el.text)
        else:
            # Some records only carry an ArticleDate (electronic pub), not a
            # JournalIssue/PubDate — fall back to that.
            article_date_year = article_el.find(".//ArticleDate/Year")
            if article_date_year is not None and article_date_year.text:
                year = _safe_int(article_date_year.text)

        # Abstract: multiple labeled <AbstractText> sections (OBJECTIVE,
        # METHODS, RESULTS, CONCLUSIONS) — join into one string, dropping
        # the labels themselves (retrieval.py just wants a flat abstract).
        abstract_parts = [
            "".join(el.itertext()).strip()
            for el in article_el.findall(".//Abstract/AbstractText")
        ]
        abstract = " ".join(p for p in abstract_parts if p) or None

        doi = None
        for aid in article_el.findall(".//ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text
                break

        authors = []
        for author_el in article_el.findall(".//AuthorList/Author"):
            last = author_el.findtext("LastName")
            initials = author_el.findtext("Initials")
            if last:
                authors.append(f"{last} {initials}" if initials else last)

        out.append({
            "pmid": pmid,
            "title": title,
            "year": year,
            "journal": journal,
            "abstract": abstract,
            "doi": doi,
            "authors": authors,
        })

    return out


def _safe_int(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _pubmed_efetch(pmids: list[str]) -> list[dict]:
    """Batch fetch — one HTTP call for all IDs (NCBI supports comma-joined
    IDs, up to a couple hundred per call), not one call per article."""
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    resp = _get_with_retry(f"{EUTILS_BASE}/efetch.fcgi", params, timeout=60)
    return _parse_pubmed_xml(resp.text)


def _pubmed_search_articles(args: dict) -> dict:
    """esearch → efetch, combined into the {"articles": [...]} shape
    retrieval.py's identify() already expects from PubMed:search_articles."""
    query = args["query"]
    max_results = args.get("max_results", 50)
    pmids = _pubmed_esearch(query, max_results)
    articles = _pubmed_efetch(pmids)
    return {"articles": articles}


def _pubmed_get_article_metadata(args: dict) -> dict:
    """Single-PMID efetch, returned as one flat dict — matches
    eligibility.py's _merge_pubmed_detail expectation (abstract/doi/journal
    keys) directly."""
    pmid = args["pmid"]
    results = _pubmed_efetch([pmid])
    return results[0] if results else {}


# ─────────────────────────────────────────────────────────────────────────────
# Public dispatcher — this is what gets passed to build_graph(mcp=...)
# ─────────────────────────────────────────────────────────────────────────────

_ROUTES = {
    "ClinicalTrials:search_trials": _ctg_search_trials,
    "ClinicalTrials:get_trial_details": _ctg_get_trial_details,
    "PubMed:search_articles": _pubmed_search_articles,
    "PubMed:get_article_metadata": _pubmed_get_article_metadata,
}


def real_mcp_dispatcher(tool_name: str, args: dict) -> dict:
    """The MCPDispatcher passed to build_graph(). Routes each of the four
    tool names retrieval.py/eligibility.py call to the real REST
    implementation above. Raises clearly on an unknown tool name rather
    than silently returning an empty result — a typo here should be loud."""
    try:
        handler = _ROUTES[tool_name]
    except KeyError:
        raise ValueError(
            f"real_mcp_dispatcher: no handler for tool {tool_name!r}. "
            f"Known tools: {sorted(_ROUTES)}"
        )
    try:
        return handler(args)
    except requests.HTTPError as e:
        log.warning("live_clients: HTTP error calling %s: %s", tool_name, e)
        return {}
    except requests.RequestException as e:
        log.warning("live_clients: network error calling %s: %s", tool_name, e)
        return {}


__all__ = ["real_mcp_dispatcher"]