"""
evidence.py — the first analytical node. Loads the dht-landscape-scout skill
as a real system prompt and applies its 12-criterion rubric / tier logic /
bias rules to the frozen corpus.

This is a different kind of node than identify/screen/eligibility
-----------------------------------------------------------------
Every prior stage was a classifier: "does this record clear a bar,"
answered per-record, cheaply, in batches. This stage is a single call that
sees the WHOLE frozen corpus for one COI at once — because tiering is
inherently cross-record (criterion 1 is "publication count," which you
can't score looking at one paper at a time). That's why it needs Sonnet
4.6, not the Haiku-class model screen/eligibility use, and why it's one
call per COI rather than N calls per record.

The skill IS the system prompt, verbatim
------------------------------------------
dht-landscape-scout's SKILL.md — the 12-criterion rubric, the tier gates,
the bias-propagation rules, the quality standards — is loaded from disk and
used as the system prompt unmodified. This module does not re-derive any
of that judgment; it only (a) renders the corpus into the user message,
(b) appends a strict JSON output contract so the skill's prose-and-tables
analysis comes back in a shape this pipeline can parse into DeviceRow /
Gap / COIEvidence, and (c) validates every citation the model emits against
the frozen citations_index before it's allowed into state.

Citation grounding at this stage
----------------------------------
This is NOT the full verify.py pass (that's a separate, later node that
checks the FINAL report). But it would be irresponsible to let ungrounded
citations flow into `devices`/`gaps`/`evidence` when catching them here is
nearly free — every device_row/gap/coi_evidence citation is checked against
`citations_index` immediately after parsing, and anything that doesn't
resolve is stripped and logged rather than silently kept.

Known gap, carried over honestly from the skill file itself
--------------------------------------------------------------
The skill's Open Questions ledger item 1 (recall_patterns.py not built) and
item 3 (direction-detection/company-first routing) apply here unchanged —
this node scores whatever corpus it's given; it does not compensate for
retrieval-stage recall gaps.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from state import COIEvidence, DeviceRow, Gap, Record


log = logging.getLogger(__name__)

LLMDispatcher = Callable[[str, str], str]

DEFAULT_SKILL_PATH = Path(__file__).parent / "skills" / "dht-landscape-scout" / "SKILL.md"


# ─────────────────────────────────────────────────────────────────────────────
# Skill loading
# ─────────────────────────────────────────────────────────────────────────────

def load_skill_prompt(skill_path: Path = DEFAULT_SKILL_PATH) -> str:
    """Read the skill file verbatim. Raises clearly if it's missing —
    this node should never silently run without the actual analytical
    framework loaded."""
    if not skill_path.exists():
        raise FileNotFoundError(
            f"evidence node: skill file not found at {skill_path}. "
            f"Copy the dht-landscape-scout SKILL.md (the v7 multi-direction "
            f"rewrite) to this path before running the evidence node."
        )
    return skill_path.read_text(encoding="utf-8")


_OUTPUT_CONTRACT = """\

---

## OUTPUT CONTRACT (added for pipeline integration — apply everything above,
## then emit ONLY the JSON object below; no prose before or after, no
## markdown code fences)

You will be given:
- `indication` and `coi`
- `corpus`: a list of records, each with a `citation_id` — this citation_id
  is the ONLY thing you may cite. Do not invent NCT numbers, PMIDs, DOIs,
  or any citation not present in the corpus you were given.

Apply Phases 1-5 of the framework above (universe generation is implicit —
you're building the universe FROM this corpus, not searching for one) and
return exactly this JSON shape:

{
  "coi_evidence": {
    "clinical_definition": "<2-3 sentences>",
    "gate_verdicts": {"disease_relevance": "PASS|FAIL|CONDITIONAL",
                       "regulatory_precedent": "PASS|FAIL|CONDITIONAL",
                       "sensor_maturity": "PASS|FAIL|CONDITIONAL"},
    "gate_rationale": {"disease_relevance": "<one sentence citing citation_id(s)>",
                        "regulatory_precedent": "<...>",
                        "sensor_maturity": "<...>"},
    "evidence_strength": "STRONG|MODERATE|EMERGING|WEAK",
    "endpoint_role_recommendation": "PRIMARY|SECONDARY|EXPLORATORY",
    "key_citations": ["<citation_id>", "..."],
    "measurement_spec": {"primary_metric": "<...>", "epoch": "<...>",
                          "algorithm": "<...>", "valid_day_rule": "<...>"}
  },
  "device_rows": [
    {
      "device": "<device name, extracted from the corpus text>",
      "manufacturer": "<manufacturer, or 'unknown' if not stated>",
      "regulatory_clearance": "<specific clearance/number, or null>",
      "wear_location": "<e.g. wrist/waist/hip, or null>",
      "measures_supported": ["<metric>", "..."],
      "v3_evidence": {
        "tier": "Tier 1|Tier 2|Tier 3|Tier 4",
        "composite_evidence": "Strong|Moderate|Weak",
        "population_tier": "T1|T2|T3|T4",
        "bias_rating": "Low|Moderate|High",
        "longitudinal_readiness": "Yes|Partial|No|Not assessed",
        "trial_endpoint_fit": "Primary|Secondary|Exploratory|None found",
        "criteria_breakdown": {"1_pub_count": "Strong|Moderate|Weak", "...": "..."}
      },
      "limitations": "<key limitations, or null>",
      "evidence_citations": ["<citation_id>", "..."]
    }
  ],
  "gaps": [
    {
      "gap_id": "GAP-<CATEGORY>-<NN>",
      "category": "regulatory|clinical_trial|statistical|device|internal_data",
      "description": "<specific gap>",
      "severity": "blocking|notable|acknowledged",
      "action": "<what's needed>",
      "supporting_citations": ["<citation_id>", "..."]
    }
  ],
  "exclusion_log": [
    {"device": "<name>", "reason": "<why it wasn't tiered>"}
  ]
}

Every citation_id in your output MUST be one that appears in the corpus you
were given. If you are not confident a device or claim is grounded in the
corpus, omit it rather than inventing supporting evidence.
"""


def build_evidence_system_prompt(skill_content: str) -> str:
    """Skill content + the output contract, concatenated. The skill's own
    analytical judgment is untouched; only the output-shape instruction is
    appended."""
    return skill_content + _OUTPUT_CONTRACT


# ─────────────────────────────────────────────────────────────────────────────
# Corpus rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_corpus_for_evidence(corpus: list[Record]) -> str:
    """Render the frozen corpus as the user message body. Uses each
    Record's own to_prompt_text() (same rendering used for Citations-API
    document blocks elsewhere) so there's one canonical text representation
    of a record across the pipeline, not two competing ones."""
    blocks = [r.to_prompt_text() for r in corpus]
    return "\n\n---\n\n".join(blocks)


def build_evidence_user_message(indication: str, coi: str, corpus: list[Record]) -> str:
    return (
        f"indication: {indication}\n"
        f"coi: {coi}\n\n"
        f"corpus ({len(corpus)} records):\n\n"
        f"{render_corpus_for_evidence(corpus)}\n\n"
        "Return the JSON object specified in the OUTPUT CONTRACT above. "
        "No prose, no markdown fences."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response parsing + citation grounding
# ─────────────────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _collect_citations(obj) -> set[str]:
    """Recursively collect every string under a key that looks like a
    citation list (evidence_citations, key_citations, supporting_citations)
    — used only for the grounding check below, not for building output."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("evidence_citations", "key_citations", "supporting_citations") and isinstance(v, list):
                found.update(x for x in v if isinstance(x, str))
            else:
                found.update(_collect_citations(v))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_collect_citations(item))
    return found


def parse_evidence_response(
    raw: str,
    coi: str,
    valid_citation_ids: set[str],
) -> tuple[list[DeviceRow], list[Gap], COIEvidence | None, dict]:
    """Parse the model's JSON, strip any citation that doesn't resolve in
    the frozen corpus, and build the typed dataclasses.

    Returns (device_rows, gaps, coi_evidence_or_None, parse_report).
    parse_report carries orphan-citation counts and any parse failure, so
    the caller can decide whether to log a warning or treat this as a
    blocking issue for the run.
    """
    report = {"orphan_citations_stripped": [], "parse_error": None, "exclusion_log": []}

    try:
        payload = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        report["parse_error"] = str(e)
        log.error("evidence[%s]: JSON parse failed: %s", coi, e)
        return [], [], None, report

    if not isinstance(payload, dict):
        report["parse_error"] = f"expected a JSON object, got {type(payload).__name__}"
        return [], [], None, report

    # Grounding check BEFORE building dataclasses — strip orphans, don't
    # just fail the whole node over one bad citation.
    all_cited = _collect_citations(payload)
    orphans = all_cited - valid_citation_ids
    if orphans:
        log.warning("evidence[%s]: %d orphan citation(s) stripped: %s",
                    coi, len(orphans), sorted(orphans)[:10])
        report["orphan_citations_stripped"] = sorted(orphans)
        payload = _strip_orphans(payload, orphans)

    report["exclusion_log"] = payload.get("exclusion_log", [])

    # --- COIEvidence ---
    coi_evidence = None
    ce = payload.get("coi_evidence")
    if isinstance(ce, dict):
        try:
            coi_evidence = COIEvidence(
                coi=coi,
                clinical_definition=ce.get("clinical_definition", ""),
                gate_verdicts=ce.get("gate_verdicts", {}),
                gate_rationale=ce.get("gate_rationale", {}),
                evidence_strength=ce.get("evidence_strength", "WEAK"),
                endpoint_role_recommendation=ce.get("endpoint_role_recommendation", "EXPLORATORY"),
                key_citations=ce.get("key_citations", []),
                measurement_spec=ce.get("measurement_spec", {}),
            )
        except Exception as e:  # noqa: BLE001 — malformed sub-object shouldn't crash the node
            log.warning("evidence[%s]: coi_evidence malformed, dropped: %s", coi, e)

    # --- DeviceRow list ---
    device_rows: list[DeviceRow] = []
    for row in payload.get("device_rows", []):
        if not isinstance(row, dict):
            continue
        try:
            device_rows.append(DeviceRow(
                coi=coi,
                device=row.get("device", "unknown"),
                manufacturer=row.get("manufacturer", "unknown"),
                regulatory_clearance=row.get("regulatory_clearance"),
                wear_location=row.get("wear_location"),
                measures_supported=row.get("measures_supported", []),
                v3_evidence=row.get("v3_evidence", {}),
                limitations=row.get("limitations"),
                evidence_citations=row.get("evidence_citations", []),
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("evidence[%s]: malformed device_row dropped: %s", coi, e)

    # --- Gap list ---
    gaps: list[Gap] = []
    for g in payload.get("gaps", []):
        if not isinstance(g, dict):
            continue
        try:
            gaps.append(Gap(
                gap_id=g.get("gap_id", "GAP-UNSPECIFIED"),
                category=g.get("category", "device"),
                description=g.get("description", ""),
                severity=g.get("severity", "notable"),
                affected_cois=[coi],
                action=g.get("action", ""),
                supporting_citations=g.get("supporting_citations", []),
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("evidence[%s]: malformed gap dropped: %s", coi, e)

    return device_rows, gaps, coi_evidence, report


def _strip_orphans(payload: dict, orphans: set[str]) -> dict:
    """Remove orphan citation_ids from every citation list in the payload,
    in place on a shallow-copied structure. Doesn't remove the containing
    device/gap/claim — only the unresolvable citation reference."""
    def _clean(obj):
        if isinstance(obj, dict):
            return {
                k: ([x for x in v if x not in orphans] if k in
                    ("evidence_citations", "key_citations", "supporting_citations")
                    and isinstance(v, list) else _clean(v))
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_clean(x) for x in obj]
        return obj
    return _clean(payload)


# ─────────────────────────────────────────────────────────────────────────────
# Node entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_evidence(
    corpus: list[Record],
    citations_index: dict[str, Record],
    coi: str,
    indication: str,
    llm: LLMDispatcher,
    skill_path: Path = DEFAULT_SKILL_PATH,
) -> tuple[list[DeviceRow], list[Gap], COIEvidence | None, dict]:
    """The evidence node's full pipeline: load skill, build prompt, call
    Sonnet, parse + ground-check the response."""
    skill_content = load_skill_prompt(skill_path)
    system_prompt = build_evidence_system_prompt(skill_content)
    user_message = build_evidence_user_message(indication, coi, corpus)

    log.info("evidence[%s]: calling model over %d-record corpus", coi, len(corpus))
    try:
        raw = llm(system_prompt, user_message)
    except RuntimeError as e:
        # llm_client._response_text raises this with real diagnostic detail
        # (stop_reason, content block types) when the model returns no
        # usable text — surface it as-is rather than letting it fall
        # through to json.loads and produce an uninformative parse error.
        log.error("evidence[%s]: model call produced no usable text: %s", coi, e)
        return [], [], None, {"orphan_citations_stripped": [], "parse_error": str(e), "exclusion_log": []}

    device_rows, gaps, coi_evidence, report = parse_evidence_response(
        raw, coi, set(citations_index.keys())
    )

    log.info(
        "evidence[%s]: %d device rows, %d gaps, coi_evidence=%s, %d orphan citations stripped",
        coi, len(device_rows), len(gaps), coi_evidence is not None,
        len(report["orphan_citations_stripped"]),
    )
    return device_rows, gaps, coi_evidence, report


__all__ = [
    "load_skill_prompt",
    "build_evidence_system_prompt",
    "render_corpus_for_evidence",
    "build_evidence_user_message",
    "parse_evidence_response",
    "run_evidence",
    "DEFAULT_SKILL_PATH",
    "LLMDispatcher",
]