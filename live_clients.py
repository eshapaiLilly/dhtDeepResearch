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

Pagination (this revision)
---------------------------
retrieval.py's identify() now paginates via _paginate_pubmed(), which
calls this module with `retstart` and expects a `count` field back (NCBI's
true total for the query, not just this page's size) alongside `articles`
— that's what lets the pagination loop know whether it's exhausted a query
or just received one page of many. The PREVIOUS version of this file only
accepted `max_results` and ignored `retstart` entirely, which meant a
pagination-aware caller passing a large page_size (e.g. 1000) got exactly
that many PMIDs back from a single esearch call with no retstart offset
ever advancing — and then tried to efetch all of them in one comma-joined
GET request, which is what produced a live 414 Request-URI Too Long.

efetch batching (GET + small chunks — do NOT switch this back to POST)
----------------------------------------------------------------------
_pubmed_efetch joins requested PMIDs into a GET query string, chunked at
_EFETCH_BATCH_SIZE so no single URL gets long enough to trip a 414
Request-URI Too Long (observed live from an ~400-ID call ≈ 3600+ chars).
At the current batch size a chunk's URL is well under ~1000 chars — far
below every practical client/proxy/server ceiling.

IMPORTANT — why GET and not POST, even though NCBI "recommends POST" for
long ID lists: this pipeline runs behind a Zscaler proxy that redirects/
rewrites outbound requests. On a redirect, `requests` silently downgrades
POST→GET and DISCARDS the form body — so a POST efetch arrives at NCBI
with NO parameters at all, and efetch returns HTTP 400 "Mandatory
parameter: db - is omitted". (esearch is unaffected because it's a GET:
its params live in the URL query string, which survives a redirect.)
GET + a chunk size small enough to never hit 414 sidesteps this entirely:
the params ride in the URL where the proxy can't drop them. Keep it GET.
Chunking also isolates faults — one bad chunk can't lose a whole page's
enrichment — and keeps per-request payload size predictable.

Rate limiting
-------------
NCBI's usage policy caps unauthenticated E-utilities calls at ~3 requests/
second, and ~10 requests/second with an API key. Set NCBI_API_KEY in the
environment and this module picks it up automatically — both the throttle
rate and every outgoing request's `api_key` param follow its presence, no
other change needed.

ClinicalTrials.gov v2 has no documented hard rate limit for reasonable use,
but this module throttles it lightly too, out of politeness.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlsplit

import certifi
import requests

import net_bootstrap


log = logging.getLogger(__name__)

CTG_BASE = "https://clinicaltrials.gov/api/v2"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Europe PMC RESTful web service — free, no auth, indexes PubMed + PMC +
# preprints (bioRxiv/medRxiv/ChemRxiv). Host is on the corporate allowlist
# (www.ebi.ac.uk). Keyword search + cursorMark pagination, JSON out.
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_EPMC_MAX_PAGE_SIZE = 1000

# Semantic Scholar Graph API — a SECOND, independent literature index (200M+
# papers, includes arXiv/bioRxiv/medRxiv preprints and citation graph data),
# free and no-auth for moderate volume. Added as an addition to, not a
# replacement for, Europe PMC: different host entirely, so it's unaffected
# by any Zscaler/cert issue specific to www.ebi.ac.uk, and it's a genuinely
# separate crawl/index — overlap with PubMed/EuropePMC is expected and
# dedup in retrieval.py handles it, but S2 covers some preprints and
# conference papers neither PubMed nor CTG ever will.
S2_BASE = "https://api.semanticscholar.org/graph/v1"

def _read_s2_api_key() -> str | None:
    """Read SEMANTIC_SCHOLAR_API_KEY defensively and log, once, exactly
    what was loaded (masked) — added after a run showed 429s persisting
    even though max_retries=3 (the "key present" branch) was selected,
    meaning the code THOUGHT it had a key but S2 was still rate-limiting
    like an unauthenticated caller. The most likely causes are copy-paste
    artifacts (stray quotes or whitespace from setting the env var in
    PowerShell — `$env:VAR = '"abc123"'` embeds literal quote characters
    in the value) or running in a terminal session from before the var was
    set. Stripping quotes/whitespace fixes the first; the log line below
    makes the second immediately visible instead of silently guessing.
    """
    raw = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if not raw:
        log.info(
            "live_clients: no SEMANTIC_SCHOLAR_API_KEY set — Semantic "
            "Scholar calls use the unauthenticated shared rate limit "
            "(~100 req/5min, shared across every anonymous caller globally)."
        )
        return None
    cleaned = raw.strip().strip('"').strip("'")
    if not cleaned:
        log.warning("live_clients: SEMANTIC_SCHOLAR_API_KEY is set but empty after cleanup — ignoring.")
        return None
    masked = f"{cleaned[:4]}...{cleaned[-2:]}" if len(cleaned) > 8 else "(short/suspicious value)"
    if raw != cleaned:
        log.warning(
            "live_clients: SEMANTIC_SCHOLAR_API_KEY had leading/trailing "
            "whitespace or quote characters — stripped before use. "
            "Loaded key: %s (length %d)", masked, len(cleaned),
        )
    else:
        log.info("live_clients: SEMANTIC_SCHOLAR_API_KEY loaded: %s (length %d)", masked, len(cleaned))
    return cleaned


S2_API_KEY = _read_s2_api_key()
# NOTE: uses /paper/search/bulk (not /paper/search) — see _semanticscholar_search
# docstring for why. Bulk search has no client-controlled page size, so
# there's no analogous "_S2_MAX_PAGE_SIZE" constant here.

NCBI_API_KEY = os.environ.get("NCBI_API_KEY")  # optional; raises rate limit if set

# Throttle now follows NCBI_API_KEY's presence automatically — this used to
# require manually lowering a hardcoded constant (per this module's own
# docstring, "not done automatically"). With a key, NCBI's documented
# ceiling is ~10 req/sec; 0.11s leaves a small margin under that rather
# than riding the exact limit. Without a key, stays at the unauthenticated
# ~3 req/sec guideline.
_MIN_INTERVAL = 0.11 if NCBI_API_KEY else 0.34
_last_call_at = 0.0
_MAX_RETRIES = 3

# Opt-in only: if the OS trust store AND certifi's bundle both fail to
# verify a host (observed for www.ebi.ac.uk on at least one Lilly-managed
# machine), the failure isn't about WHICH roots are trusted — it's either
# an incomplete cert chain served by that host (no CA bundle fixes a
# missing intermediate) or active interference on that specific connection
# somewhere in the network path. Verify with
# `openssl s_client -connect <host>:443 -showcerts` before reaching for
# this. This toggle is a deliberate, explicit stopgap: it disables
# verification ONLY for the hosts listed here, ONLY when the env var is
# set, and logs loudly every time it's used. Don't enable it for anything
# beyond read-only public bibliographic metadata.
_INSECURE_FALLBACK_HOSTS = {"www.ebi.ac.uk", "api.semanticscholar.org"}
_INSECURE_FALLBACK_ENABLED = os.environ.get(
    "PIPELINE_ALLOW_INSECURE_SSL_FALLBACK", ""
).lower() in ("1", "true", "yes")

log.info(
    "live_clients: NCBI_API_KEY %s — throttling at %.2fs/request (~%.0f req/sec)",
    "found" if NCBI_API_KEY else "not set", _MIN_INTERVAL, 1.0 / _MIN_INTERVAL,
)

# efetch ID-list batch size. efetch goes over GET (see module docstring:
# POST bodies get dropped by the Zscaler redirect, producing a bogus
# "Mandatory parameter: db - is omitted" 400), so this cap DOES govern URL
# length. At 100 IDs a chunk's URL is ~1000 chars — comfortably under the
# ~3600+ that tripped the original 414, with wide margin for any proxy in
# the path. Also gives fault isolation: a bad chunk can't lose a whole page.
_EFETCH_BATCH_SIZE = 100

# NCBI esearch's own hard ceiling: retstart + retmax <= 10,000. Enforced
# here defensively too, even though retrieval.py's _paginate_pubmed already
# respects this — a caller bypassing that loop shouldn't be able to request
# something NCBI will reject anyway.
_PUBMED_MAX_ACCESSIBLE = 10_000

# Guards _last_call_at. _throttle() was originally written assuming a
# single-threaded caller (retrieval.py's identify() runs one query at a
# time). eligibility.py's enrich_all() now calls into this module from a
# thread pool — without this lock, two threads could both read
# _last_call_at before either updates it, both sleep less than
# _MIN_INTERVAL, and the throttle silently stops enforcing anything under
# concurrency (a classic check-then-act race, not just a cosmetic issue).
_throttle_lock = threading.Lock()


def _throttle() -> None:
    global _last_call_at
    with _throttle_lock:
        elapsed = time.monotonic() - _last_call_at
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_call_at = time.monotonic()


# Separate throttle for Semantic Scholar — a different host with its own
# published rate limit (deliberately
# conservative; with an API key, S2's tutorial documents exactly 1
# request/second across all endpoints). 1.05s rather than a bare 1.0s —
# small safety margin against clock/network jitter around a hard limit;
# costs nothing in practice, avoids landing exactly on the edge of it.
# Kept as its own lock so EBI/NCBI pacing above is unaffected either way.
_S2_MIN_INTERVAL = 1.05 if S2_API_KEY else 3.1
_s2_last_call_at = 0.0
_s2_throttle_lock = threading.Lock()


def _s2_throttle() -> None:
    global _s2_last_call_at
    with _s2_throttle_lock:
        elapsed = time.monotonic() - _s2_last_call_at
        if elapsed < _S2_MIN_INTERVAL:
            time.sleep(_S2_MIN_INTERVAL - elapsed)
        _s2_last_call_at = time.monotonic()


def _request_with_retry(
    method: str, url: str, params: dict, timeout: int, *, throttle=_throttle,
    headers: dict | None = None, max_retries: int = _MAX_RETRIES,
) -> requests.Response:
    """GET or POST with retry-on-429, exponential backoff. Shared by both
    _get_with_retry and _post_with_retry below so the throttle/backoff
    logic lives in exactly one place.

    Added after a live run against a ~170-record MVPA/COPD corpus produced
    three 429s during eligibility's per-record PubMed enrichment — the
    baseline throttle (~3 req/sec) isn't always enough headroom once a
    session has made a couple hundred prior calls. Respects Retry-After if
    NCBI sends it; otherwise backs off 1s/2s/4s. After max_retries, raises
    so the caller's existing fault-tolerant fallback (enrich_record already
    catches exceptions and returns the un-enriched record) takes over —
    this doesn't change that contract, it just makes hitting it less likely.

    max_retries is overridable per-host: Semantic Scholar's unauthenticated
    tier is a bucket SHARED ACROSS EVERY ANONYMOUS CALLER GLOBALLY, not a
    per-client allowance, so a 429 there can happen on the very first call
    of a session and isn't a sign of misuse — it's ambient contention that
    usually clears within a couple of backoff cycles. _s2_get_with_retry
    below passes a higher max_retries for exactly this reason.
    """
    for attempt in range(max_retries + 1):
        throttle()
        try:
            if method == "GET":
                resp = requests.get(url, params=params, timeout=timeout, headers=headers)
            else:
                resp = requests.post(url, data=params, timeout=timeout, headers=headers)
        except requests.exceptions.SSLError as e:
            # If TWO unrelated public hosts (different orgs/CAs) both fail
            # identically on the OS-trust-store attempt AND this fallback,
            # that's the signature of truststore.inject_into_ssl() never
            # actually having taken effect — see net_bootstrap.py's
            # docstring. In that case this "fallback" is really re-running
            # the same certifi-based verification that just failed, UNLESS
            # net_bootstrap.MERGED_CA_BUNDLE exists (certifi's public roots
            # + your corporate root CA, concatenated) — that's the
            # deterministic fix: it doesn't depend on truststore correctly
            # detecting anything, it just trusts both categories directly.
            # Falls back to certifi alone if no corporate CA is configured
            # (LILLY_CA_BUNDLE unset) — same behavior as before, which
            # means Zscaler-intercepted hosts will still fail until that
            # env var points at a real corporate root. Run
            # `python -c "import net_bootstrap; net_bootstrap.print_diagnostics()"`
            # to check which case you're in.
            verify_target = net_bootstrap.MERGED_CA_BUNDLE or certifi.where()
            log.warning(
                "live_clients: SSL verify failed for %s via OS trust store "
                "(%s) — retrying with %s", url, e,
                "merged certifi+corporate CA bundle" if net_bootstrap.MERGED_CA_BUNDLE
                else "certifi's bundled CA list (no corporate CA configured — "
                     "see net_bootstrap.print_diagnostics())",
            )
            try:
                if method == "GET":
                    resp = requests.get(url, params=params, timeout=timeout, verify=verify_target, headers=headers)
                else:
                    resp = requests.post(url, data=params, timeout=timeout, verify=verify_target, headers=headers)
            except requests.exceptions.SSLError as e2:
                # Both the OS store AND certifi's bundle failed identically.
                # That rules out "wrong trust store" as the cause — it's
                # either an incomplete chain served by the host (no CA
                # bundle fixes a missing intermediate) or something in the
                # network path actively breaking this specific connection.
                # Only fall through to no-verification if the host is
                # explicitly allow-listed AND the operator opted in via env
                # var — this is a deliberate, visible security downgrade,
                # never a silent default.
                host = urlsplit(url).hostname or ""
                if _INSECURE_FALLBACK_ENABLED and host in _INSECURE_FALLBACK_HOSTS:
                    log.warning(
                        "live_clients: SSL verify failed for %s under BOTH "
                        "the OS trust store and certifi (%s) — "
                        "PIPELINE_ALLOW_INSECURE_SSL_FALLBACK is set and %s "
                        "is allow-listed, so retrying with certificate "
                        "verification DISABLED. This is a deliberate, "
                        "operator-opted-in downgrade for read-only public "
                        "metadata only — do not leave this on for anything "
                        "else.", url, e2, host,
                    )
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    if method == "GET":
                        resp = requests.get(url, params=params, timeout=timeout, verify=False, headers=headers)
                    else:
                        resp = requests.post(url, data=params, timeout=timeout, verify=False, headers=headers)
                else:
                    raise

        if resp.status_code != 429:
            resp.raise_for_status()
            return resp

        # Distinguish a TRUE rate-limit 429 (worth retrying) from Semantic
        # Scholar's "too many hits" 429 (query matched >10M papers — retrying
        # is pointless, the query itself must be narrowed). The latter comes
        # back as JSON with an "error" key containing "too many hits".
        if resp.status_code == 429:
            try:
                body = resp.json()
                if isinstance(body, dict) and "error" in body:
                    err_msg = body["error"]
                    if "too many hits" in err_msg.lower():
                        log.warning(
                            "live_clients: S2 'too many hits' rejection (not a "
                            "rate limit — retrying won't help): %s", err_msg,
                        )
                        # Return the response as-is; caller
                        # (_semanticscholar_search) checks for "error" in the
                        # parsed JSON and returns empty gracefully.
                        return resp
            except (ValueError, KeyError):
                pass  # not JSON or unexpected shape — treat as normal 429

        if attempt == max_retries:
            resp.raise_for_status()  # exhausted retries — raise the 429
        wait = float(resp.headers.get("Retry-After", 2 ** attempt))
        log.warning("live_clients: 429 from %s, retrying in %.1fs (attempt %d/%d)",
                    url, wait, attempt + 1, max_retries)
        time.sleep(wait)
    raise RuntimeError("unreachable")  # loop always returns or raises above


def _get_with_retry(url: str, params: dict, timeout: int, *, throttle=_throttle, headers: dict | None = None) -> requests.Response:
    return _request_with_retry("GET", url, params, timeout, throttle=throttle, headers=headers)


def _post_with_retry(url: str, params: dict, timeout: int, *, throttle=_throttle, headers: dict | None = None) -> requests.Response:
    return _request_with_retry("POST", url, params, timeout, throttle=throttle, headers=headers)


def _s2_get_with_retry(url: str, params: dict, timeout: int) -> requests.Response:
    """Same retry/SSL-fallback machinery as _get_with_retry, paced against
    Semantic Scholar's own throttle instead of NCBI's — a different host
    with a different published rate limit. Sends the API key header when
    SEMANTIC_SCHOLAR_API_KEY is set (raises S2's rate limit substantially
    AND moves you off the shared unauthenticated bucket onto a dedicated
    one — get one free at
    https://www.semanticscholar.org/product/api#api-key-form).

    max_retries is higher than the default here: unauthenticated S2 traffic
    shares ONE rate-limit bucket across every anonymous caller on the
    internet, not a per-client allowance, so a 429 can happen on literally
    the first call of a session — observed live. That's ambient
    contention, not misuse, and it usually clears within a few backoff
    cycles rather than being a persistent block, so it's worth a few more
    attempts than we'd give a well-behaved dedicated-quota host like NCBI.

    IMPORTANT: distinguishes between TRUE rate-limit 429s (ambient contention,
    worth retrying) and S2's "too many hits" 429 (query matched >10M papers,
    retrying is pointless). The latter comes back as HTTP 429 with a JSON body
    containing {"error": "Search returned too many hits ..."} — detected here
    so _request_with_retry's retry loop doesn't burn all attempts on an
    unresolvable condition.
    """
    headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else None
    return _request_with_retry(
        "GET", url, params, timeout, throttle=_s2_throttle, headers=headers,
        max_retries=6 if not S2_API_KEY else _MAX_RETRIES,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ClinicalTrials.gov v2 — live-verified shape, passes through near-unmodified
# ─────────────────────────────────────────────────────────────────────────────

def _ctg_search_trials(args: dict) -> dict:
    """GET /api/v2/studies. Returns {"studies": [...], "nextPageToken": ...}
    exactly as retrieval.py's _paginate_ctg expects — confirmed live:
    studies[].protocolSection.identificationModule.nctId matches
    _normalize_ctg's field paths with no translation needed. `pageToken`
    passes through untouched if the caller includes it (this function
    doesn't paginate itself; retrieval.py's loop owns that)."""
    params = {k: v for k, v in args.items() if k != "pageSize"}
    params["pageSize"] = args.get("pageSize", 1000)  # was 50 — 1000 is the API's hard ceiling
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

def _pubmed_esearch(query: str, retmax: int, retstart: int = 0) -> tuple[list[str], int]:
    """Returns (idlist_for_this_page, total_count_matching_query).

    NCBI returns `count` on every esearch call — the TRUE total number of
    matching records, not this page's size. That's the field
    retrieval.py's _paginate_pubmed needs to tell "more pages exist" apart
    from "this was everything." The previous version of this function
    ignored retstart and discarded count entirely, which is what made
    pagination silently not work even after retrieval.py was updated to
    call it that way.
    """
    params = {
        "db": "pubmed", "term": query, "retmode": "json",
        "retmax": retmax, "retstart": retstart,
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    resp = _get_with_retry(f"{EUTILS_BASE}/esearch.fcgi", params, timeout=30)
    result = resp.json().get("esearchresult", {})
    idlist = result.get("idlist", [])
    count = _safe_int(result.get("count")) or 0
    return idlist, count


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
    """Batch fetch via GET, chunked at _EFETCH_BATCH_SIZE.

    GET, NOT POST — this is load-bearing in this environment. A POST body
    is silently dropped when the Zscaler proxy redirects the request
    (`requests` downgrades POST→GET on redirect and discards the form
    body), so a POST efetch reaches NCBI with no `db` and comes back
    HTTP 400 "Mandatory parameter: db - is omitted". Sending params in the
    URL query string (GET) keeps them where the proxy can't drop them.

    The only reason POST was ever considered is URL length (a several-
    hundred-ID GET tripped a 414). _EFETCH_BATCH_SIZE is set small enough
    (~1000-char URLs) that this never happens, so GET is strictly safer
    here with no downside. Chunking also isolates faults: each chunk that
    succeeds is kept even if a later chunk raises.
    """
    if not pmids:
        return []
    out: list[dict] = []
    for i in range(0, len(pmids), _EFETCH_BATCH_SIZE):
        batch = pmids[i:i + _EFETCH_BATCH_SIZE]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY
        resp = _get_with_retry(f"{EUTILS_BASE}/efetch.fcgi", params, timeout=60)
        out.extend(_parse_pubmed_xml(resp.text))
    return out


def _pubmed_search_articles(args: dict) -> dict:
    """esearch (one page) → efetch, combined into the shape retrieval.py's
    _paginate_pubmed expects: {"articles": [...], "count": N, "retstart": M}.

    Accepts `retstart` (default 0) — this is the field the previous
    version of this function silently dropped, which is what broke
    pagination even after retrieval.py was updated to send it.
    """
    query = args["query"]
    max_results = args.get("max_results", 300)
    retstart = args.get("retstart", 0)
    # Defensive clamp — mirrors retrieval.py's own clamp, so a caller that
    # bypasses that loop can't request past NCBI's hard ceiling anyway.
    max_results = min(max_results, max(_PUBMED_MAX_ACCESSIBLE - retstart, 0))

    pmids, count = _pubmed_esearch(query, retmax=max_results, retstart=retstart)
    articles = _pubmed_efetch(pmids)
    return {"articles": articles, "count": count, "retstart": retstart}


def _pubmed_get_article_metadata(args: dict) -> dict:
    """Single-PMID efetch, returned as one flat dict — matches
    eligibility.py's _merge_pubmed_detail expectation (abstract/doi/journal
    keys) directly."""
    pmid = args["pmid"]
    results = _pubmed_efetch([pmid])
    return results[0] if results else {}


# ─────────────────────────────────────────────────────────────────────────────
# Europe PMC — one keyword-searchable REST API over PubMed + PMC + preprints
# ─────────────────────────────────────────────────────────────────────────────

def _europepmc_search(args: dict) -> dict:
    """GET /search. Returns the shape retrieval.py's _paginate_europepmc
    expects: {"results": [...], "hitCount": N, "nextCursorMark": ...}.

    resultType=core returns full metadata incl. abstractText. cursorMark
    (default "*") drives pagination — Europe PMC echoes a nextCursorMark that
    stops advancing once the result set is exhausted. No api_key needed.

    Shares _get_with_retry (and therefore the module throttle/backoff) with
    the NCBI calls — over-conservative for a different host, but keeps us
    polite to Europe PMC and needs no second throttle. Verify the response
    field paths (resultList.result[]) against a live call before relying on
    this channel, same discipline as the CTG/PubMed handlers.
    """
    params = {
        "query": args["query"],
        "resultType": "core",
        "format": "json",
        "pageSize": min(args.get("pageSize", 100), _EPMC_MAX_PAGE_SIZE),
        "cursorMark": args.get("cursorMark", "*"),
    }
    resp = _get_with_retry(f"{EPMC_BASE}/search", params, timeout=30)
    data = resp.json()
    return {
        "results": (data.get("resultList", {}) or {}).get("result", []) or [],
        "hitCount": data.get("hitCount", 0),
        "nextCursorMark": data.get("nextCursorMark"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Semantic Scholar Graph API — independent index, different host than EPMC
# ─────────────────────────────────────────────────────────────────────────────

def _semanticscholar_search(args: dict) -> dict:
    """GET /paper/search/bulk — NOT /paper/search (relevance search).

    Per Semantic Scholar's own tutorial: "Paper bulk search should be used
    in most cases because paper relevance search is more resource
    intensive." Relevance search is tuned for "best single match" ranking
    and paginates via offset/limit with a practical results ceiling; bulk
    search is built for exactly our use case — exhaustive systematic-review
    -style retrieval — has no such ceiling, and paginates via an opaque
    `token` instead. This was a real bug in the first cut of this
    integration, not just a suboptimal choice: bulk search's `query`
    parameter uses boolean syntax (`|` for OR, `+`/`-` for required/
    excluded, `"..."` for exact phrase) which the CALLER must construct
    correctly (see recall_patterns.build_s2_bulk_query) — the literal
    English word "OR" is NOT an operator here and would be searched for
    as a literal token.

    Returns the shape retrieval.py's _paginate_semanticscholar expects:
    {"data": [...], "total": N, "token": <next page token, or None>}.
    Bulk search has no `limit` parameter — page size is fixed server-side
    (observed ~1000/page); `token` is absent from the response once the
    result set is exhausted.

    Uses its own throttle (_s2_throttle) and its own SSL-fallback path via
    _s2_get_with_retry — entirely independent of the EPMC/NCBI machinery,
    so an outage or cert issue on one host can't affect the other.

    Filtering (year, fieldsOfStudy)
    --------------------------------
    Semantic Scholar's bulk search has a hard ceiling of 10 million matching
    papers — queries broader than that are rejected with HTTP 429 and a body
    like {"error":"Search returned too many hits (236709528 of 10000000)..."}.
    This is NOT a rate limit; it's a result-set-too-large rejection that will
    never resolve with retries. The fix is server-side narrowing via `year`
    and `fieldsOfStudy` query parameters, both documented in S2's API:
      - year: "2016-" restricts to 2016-onward (matches GLOBAL_INCLUSION).
      - fieldsOfStudy: "Medicine,Biology" restricts to biomedical papers.
    These are passed by the caller (graph.py / recall_patterns.py) via args,
    with sensible defaults here as a safety net.
    """
    params = {
        "query": args["query"],
        "fields": "title,abstract,year,venue,externalIds,authors.name",
    }
    if args.get("token"):
        params["token"] = args["token"]
    # Server-side filters to keep result count under S2's 10M ceiling.
    # Callers should pass these explicitly; defaults here are a safety net
    # that matches our pipeline's global inclusion criteria (2016+, biomedical).
    if args.get("year"):
        params["year"] = args["year"]
    else:
        params["year"] = "2016-"
    if args.get("fieldsOfStudy"):
        params["fieldsOfStudy"] = args["fieldsOfStudy"]
    else:
        params["fieldsOfStudy"] = "Medicine,Biology"
    if args.get("publicationTypes"):
        params["publicationTypes"] = args["publicationTypes"]
    if args.get("minCitationCount"):
        params["minCitationCount"] = args["minCitationCount"]

    resp = _s2_get_with_retry(f"{S2_BASE}/paper/search/bulk", params, timeout=30)
    data = resp.json()

    # Detect the "too many hits" error — S2 returns this as a 200 with an
    # "error" key (or sometimes a 429 whose body is JSON with "error") when
    # the query matches more than 10M papers. This is NOT a rate limit and
    # retrying won't help — the query itself must be narrower. Log and
    # return empty so the pipeline continues with other sources.
    if "error" in data:
        log.warning(
            "live_clients: Semantic Scholar rejected query as too broad: %s "
            "(query was: %s, params: %s). Returning empty — other sources "
            "still cover this lane.",
            data["error"], args.get("query", ""), params,
        )
        return {"data": [], "total": 0, "token": None}

    return {
        "data": data.get("data", []) or [],
        "total": data.get("total", 0),
        "token": data.get("token"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public dispatcher — this is what gets passed to build_graph(mcp=...)
# ─────────────────────────────────────────────────────────────────────────────

_ROUTES = {
    "ClinicalTrials:search_trials": _ctg_search_trials,
    "ClinicalTrials:get_trial_details": _ctg_get_trial_details,
    "PubMed:search_articles": _pubmed_search_articles,
    "PubMed:get_article_metadata": _pubmed_get_article_metadata,
    "EuropePMC:search": _europepmc_search,
    "SemanticScholar:search": _semanticscholar_search,
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


__all__ = ["real_mcp_dispatcher", "print_s2_diagnostics"]


def print_s2_diagnostics() -> None:
    """Run as:
        python -c "import net_bootstrap, live_clients; live_clients.print_s2_diagnostics()"
    (import net_bootstrap first, same as any real entry point, so TLS is
    configured identically to a real run.)

    Makes ONE real request to Semantic Scholar and prints what actually
    came back — status code, and any rate-limit headers S2 sends — so you
    can see directly whether you're on the authenticated tier rather than
    inferring it from retry-count behavior. Added after a run showed 429s
    persisting even with max_retries=3 selected (the "key present"
    branch), which only tells you the code THOUGHT it had a key — not
    that S2 actually honored it.
    """
    print(f"S2_API_KEY loaded = {bool(S2_API_KEY)}")
    if S2_API_KEY:
        masked = f"{S2_API_KEY[:4]}...{S2_API_KEY[-2:]}" if len(S2_API_KEY) > 8 else "(short/suspicious value)"
        print(f"  masked value = {masked} (length {len(S2_API_KEY)})")
    print(f"_S2_MIN_INTERVAL = {_S2_MIN_INTERVAL}s between calls")
    print()
    headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
    try:
        resp = requests.get(
            f"{S2_BASE}/paper/search/bulk",
            params={"query": '"test"', "fields": "title"},
            headers=headers, timeout=15,
        )
        print(f"HTTP status: {resp.status_code}")
        rl_headers = {k: v for k, v in resp.headers.items() if "rate" in k.lower() or "limit" in k.lower()}
        if rl_headers:
            print(f"Rate-limit headers returned: {rl_headers}")
        else:
            print("(no rate-limit headers in the response — S2 doesn't always send them)")
        if resp.status_code == 429:
            print(
                "\n429 even on a single isolated call strongly suggests the key "
                "isn't actually reaching S2 as valid — double check for copy-paste "
                "quotes/whitespace (this module now strips those automatically, "
                "but only from what the env var actually contains), or that the "
                "key hasn't finished activating yet (some API key systems have a "
                "short propagation delay after creation)."
            )
        elif resp.status_code == 200 and S2_API_KEY:
            print("\n200 with a key present — looks like it's working correctly.")
    except requests.exceptions.RequestException as e:
        print(f"Request failed before getting a response: {e}")