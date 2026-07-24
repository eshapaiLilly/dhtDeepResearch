"""
ta_offline_test.py — exercise the full TA-first stage with NO gateway/MCP.

Injects a stub LLM (canned JSON) and a fake corpus so every deterministic path
runs: search-plan shape, extraction+grounding, two-axis scoring (with the
quadrant/recommendation recomputed server-side), orphan stripping, criteria-stub
emission in the exact criteria.py shape, and memo rendering. Proves the seam
into coi_first is real before spending a live run.

    python ta_offline_test.py
"""
from __future__ import annotations

import json
import logging

from state import Record
from criteria import EligibilityCriteria, get as get_criteria
from ta_landscape import (
    ta_search_plan, extract_candidate_cois, score_cois,
    criteria_stub_for, render_criteria_stub_block,
    render_memo, TAResult, result_as_json,
)
from retrieval import build_citations_index

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def fake_corpus() -> list[Record]:
    return [
        Record(citation_id="NCT01111111", source="clinicaltrials",
               title="Wearable accelerometry to track ambulation decline in ALS",
               year=2021, nct_id="NCT01111111", phase="2", status="Completed",
               outcome_measures=["Daily step count", "Time in active movement",
                                 "Accelerometer-derived mobility"]),
        Record(citation_id="PMID:2222222", source="pubmed",
               title="Bulbar speech deterioration measured by smartphone voice tasks in ALS",
               year=2022, pmid="2222222", journal="Amyotroph Lateral Scler",
               abstract="Speech rate and articulatory precision from phone recordings "
                        "tracked bulbar decline; head drop and cervical range of motion "
                        "were also noted as functional markers."),
        Record(citation_id="NCT03333333", source="clinicaltrials",
               title="Respiratory function home monitoring in ALS",
               year=2020, nct_id="NCT03333333", phase="N/A", status="Recruiting",
               outcome_measures=["Slow vital capacity", "Home spirometry FVC"]),
        Record(citation_id="PMID:4444444", source="pubmed",
               title="Cognitive-behavioral change in ALS: a clinical review",
               year=2019, pmid="4444444", journal="Neurology",
               abstract="Executive dysfunction and apathy are clinically important in ALS "
                        "but are typically assessed by in-clinic neuropsychological batteries; "
                        "no digital measurement precedent was identified."),
    ]


class StubLLM:
    """Returns canned JSON keyed by which system prompt it sees. Also emits one
    ORPHAN citation (PMID:9999999) to prove the grounding gate strips it."""
    def __call__(self, system: str, user: str) -> str:
        if "enumerate the distinct CONSTRUCTS" in system or "Concept-of-Interest (COI) map" in system:
            return json.dumps({"candidates": [
                {"coi": "physical_activity", "label": "Physical Activity / Ambulation",
                 "clinical_rationale": "Mobility decline is a core ALS progression marker.",
                 "literature_vocabulary": ["step count", "time in active movement",
                                            "accelerometer-derived mobility", "ambulation"],
                 "dht_precedent": "wrist/waist accelerometry in a completed Phase 2",
                 "evidence_citations": ["NCT01111111"]},
                {"coi": "bulbar_speech", "label": "Bulbar Speech",
                 "clinical_rationale": "Bulbar decline drives communication loss in ALS.",
                 "literature_vocabulary": ["speech rate", "articulatory precision",
                                            "head drop", "cervical range of motion"],
                 "dht_precedent": "smartphone voice tasks",
                 "evidence_citations": ["PMID:2222222"]},
                {"coi": "respiratory_function", "label": "Respiratory Function",
                 "clinical_rationale": "Respiratory failure is the leading cause of death in ALS.",
                 "literature_vocabulary": ["slow vital capacity", "home spirometry", "FVC"],
                 "dht_precedent": "home spirometry",
                 "evidence_citations": ["NCT03333333"]},
                {"coi": "executive_function", "label": "Executive Function",
                 "clinical_rationale": "Cognitive-behavioral change is clinically meaningful in ALS.",
                 "literature_vocabulary": ["executive dysfunction", "apathy"],
                 "dht_precedent": "",
                 "evidence_citations": ["PMID:4444444"]},
                {"coi": "ungrounded_ghost", "label": "Ghost Construct",
                 "clinical_rationale": "Should be dropped — no resolvable citation.",
                 "literature_vocabulary": [], "dht_precedent": "",
                 "evidence_citations": ["PMID:9999999"]},  # orphan → candidate dropped
            ]})
        # scoring prompt
        return json.dumps({"scores": [
            {"coi": "physical_activity", "clinical_importance": 5,
             "clinical_importance_rationale": "Core progression marker [NCT01111111]",
             "digital_measurability": 4,
             "digital_measurability_rationale": "Validated accelerometry [NCT01111111]",
             "quadrant": "core_and_measurable", "recommendation": "recommend",
             "evidence_citations": ["NCT01111111"]},
            {"coi": "bulbar_speech", "clinical_importance": 5,
             "clinical_importance_rationale": "Drives communication loss [PMID:2222222]",
             "digital_measurability": 4,
             "digital_measurability_rationale": "Smartphone voice tasks [PMID:2222222]",
             "quadrant": "core_and_measurable", "recommendation": "recommend",
             "evidence_citations": ["PMID:2222222"]},
            {"coi": "respiratory_function", "clinical_importance": 5,
             "clinical_importance_rationale": "Leading cause of death [NCT03333333]",
             "digital_measurability": 3,
             "digital_measurability_rationale": "Home spirometry emerging [NCT03333333]",
             "quadrant": "core_and_measurable", "recommendation": "recommend",
             "evidence_citations": ["NCT03333333"]},
            # Model MISLABELS this as recommend; server must recompute -> white_space
            {"coi": "executive_function", "clinical_importance": 4,
             "clinical_importance_rationale": "Clinically meaningful [PMID:4444444]",
             "digital_measurability": 1,
             "digital_measurability_rationale": "No digital precedent [PMID:4444444]",
             "quadrant": "core_and_measurable", "recommendation": "recommend",
             "evidence_citations": ["PMID:4444444"]},
        ]})


def main() -> None:
    corpus = fake_corpus()
    idx = build_citations_index(corpus)
    llm = StubLLM()
    checks = []

    # 1. search plan shape
    plan = ta_search_plan("ALS")
    checks.append(("search_plan has CTG + PubMed lanes",
                   set(plan) == {"clinicaltrials", "pubmed"} and len(plan["clinicaltrials"]) == 2))
    checks.append(("CTG backbone lane is bare cond=indication",
                   plan["clinicaltrials"][0] == {"query.cond": "ALS"}))

    # 2. extraction + grounding gate (orphan candidate dropped)
    candidates, ex_rep = extract_candidate_cois(corpus, "ALS", llm, idx)
    got = {c.coi for c in candidates}
    checks.append(("4 grounded candidates, ghost dropped",
                   got == {"physical_activity", "bulbar_speech",
                           "respiratory_function", "executive_function"}))
    checks.append(("orphan PMID:9999999 recorded as stripped",
                   "PMID:9999999" in ex_rep["orphan_citations_stripped"]))

    # 3. scoring + server-side quadrant recompute
    scores, _ = score_cois(candidates, corpus, "ALS", llm, idx)
    ef = next(s for s in scores if s.coi == "executive_function")
    checks.append(("executive_function recomputed to white_space (importance 4, measurability 1)",
                   ef.quadrant == "core_not_yet_measurable" and ef.recommendation == "white_space"))

    result = TAResult(indication="ALS", corpus_size=len(corpus), prisma={},
                      candidates=candidates, scores=scores, citations_index=idx)
    checks.append(("recommended excludes white space",
                   {s.coi for s in result.recommended()} ==
                   {"physical_activity", "bulbar_speech", "respiratory_function"}))
    checks.append(("white_space() surfaces executive_function",
                   [s.coi for s in result.white_space()] == ["executive_function"]))

    # 4. criteria stub is a real EligibilityCriteria in criteria.py's shape
    stub = criteria_stub_for(result.candidate_for("physical_activity"))
    checks.append(("stub is EligibilityCriteria with GLOBAL_INCLUSION + signals",
                   isinstance(stub, EligibilityCriteria)
                   and "step count" in stub.positive_signals
                   and len(stub.inclusion) >= 3))
    # stub must serialize with the SAME prompt-block method authored entries use
    checks.append(("stub.to_prompt_block() renders (screen-node compatible)",
                   "Eligibility criteria for COI: physical_activity" in stub.to_prompt_block()))

    # 5. bulbar_speech already exists in criteria.py — stub flags the override
    block = render_criteria_stub_block(result.candidate_for("bulbar_speech"))
    checks.append(("stub for existing COI flags OVERRIDES authored entry",
                   "OVERRIDES an existing authored entry" in block))

    # 6. memo + json render without error
    memo = render_memo(result)
    js = result_as_json(result)
    checks.append(("memo renders with matrix + white-space section",
                   "Recommendation matrix" in memo and "WHITE SPACE" in memo))
    checks.append(("json result_as_json carries recommended + white_space",
                   js["recommended_cois"] and js["white_space_cois"] == ["executive_function"]))

    # 7. authored criteria.py still loads (no accidental mutation)
    checks.append(("authored bulbar_speech entry intact",
                   get_criteria("bulbar_speech").coi == "bulbar_speech"))

    print("\n=== TA-first V1 offline structural test ===")
    ok = 0
    for name, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
        ok += passed
    print(f"\n{ok}/{len(checks)} checks passed")

    print("\n----- sample criteria stub (physical_activity) -----")
    print(render_criteria_stub_block(result.candidate_for("physical_activity")))
    print("\n----- memo preview (first 40 lines) -----")
    print("\n".join(memo.splitlines()[:40]))

    if ok != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()