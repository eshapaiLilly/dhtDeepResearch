---
name: dht-landscape-scout
version: v7 (multi-direction, pipeline-aware)
description: >
  Analytical framework for a systematic DHT (Digital Health Technology)
  landscape assessment. Generates a device/technology universe, scores every
  candidate on a 12-criterion rubric, assigns a three-tier priority shortlist
  plus a horizon watch list, and logs gaps — for ANY indication, ANY concept
  of interest (COI), ANY modality, and (new in v7) ANY landscape DIRECTION:
  COI-first, measure-first, device-first, or company-first. Used two ways:
  (1) standalone in chat, where it performs retrieval itself; (2) as the
  system prompt for the evidence/device scoring nodes in the deep_researchDHT
  pipeline, where retrieval and screening already ran and this skill's job is
  scoring, tiering, and synthesis over an already-grounded corpus. Triggers
  on: "DHT landscape", "what devices exist for [COI]", "landscape for
  [modality]", "which devices compute [measure]", "compare [device A] vs
  [device B]", "what is [company]'s DHT footprint", "wearables validated for
  [indication]", or any request to identify, characterize, or rank DHTs.
---

# DHT Landscape Scouting — Analytical Framework

## Purpose and Framing

This skill produces a **systematic, comparatively graded DHT landscape**: an
evidence-graded map of devices/technologies — cited, quantified, bias-flagged
— structured so a team can decide which DHTs warrant full STR defense. It is
deliberately indication-, COI-, and modality-agnostic: the same scoring
engine must serve a well-trodden question (physical activity in COPD) and a
novel one (oculomotor function in a rare disease), and — new in this version
— must serve questions that don't start from a COI at all ("characterize
ActiGraph's evidence base," "what is Novoic's clinical footprint," "give me
the whole MVPA device-and-company landscape").

**Methodology principles that never change, regardless of direction or COI:**
- Longitudinal validity is scored separately from diagnostic accuracy.
  HC-vs.-patient AUC does not imply trial endpoint readiness.
- High bias ratings propagate to tiers. High-bias evidence cannot earn a
  Strong rating regardless of AUC.
- Sample size is judged against the endpoint use case, not labeled generically.
- The shortlist is explicit tiers (Progress / Diligence / Monitor / Watch),
  never a flat ranked list.

**Output is organized research** (tables, ratings, citations, gap logs), not
finished prose or slides. Formatting is a downstream step.

---

## The Core Abstraction: Direction Selects the Entry Point and the Rollup; the Scoring Engine Is Shared

This is the central design idea of v7 and the answer to "any direction of
landscape." Every landscape question, no matter how it's phrased, resolves
into the same three-part machine:

```
   ENTRY PRIMITIVE            SHARED SCORING ENGINE           OUTPUT ROLLUP
  (seeds the universe)   →   (Phases 2–5, direction-       →  (how results are
                              invariant: rubric, tiers,        grouped for the
                              bias rules, gaps)                reader)
```

**Only the entry primitive and the output rollup change with direction. The
12-criterion rubric, the tier gates, the bias-propagation rules, the
longitudinal/diagnostic separation, and the quality standards are identical
across all four directions.** This is what makes "any direction" tractable
without four separate skills: you are not writing four analyses, you are
seeding one analysis four different ways and grouping its output two or three
different ways.

### The four directions

| Direction | Example query | Entry primitive (what seeds the universe) | Output rollup (how results group) |
|---|---|---|---|
| **COI-first** (default) | "DHTs for MVPA in COPD" | Indication + COI → wide universe search | Per-device tiers, grouped by COI |
| **Measure-first** | "ultrasound landscape for diaphragm thickening fraction" | Locked measure (algorithm + acquisition params) → devices that can compute it | Per-device tiers + measure-fidelity rating |
| **Device-first** | "characterize ActiGraph GT9X" / "compare Empatica vs Axivity for activity" | Named device(s) → score directly; optionally find same-niche competitors | Per-device deep dive; comparison table if >1 |
| **Company-first** | "what is Novoic's clinical footprint" | Company name → enumerate its products/platforms → each becomes a device-first entry | Per-company rollup + per-product tiers |

A "broad modality landscape" ("the whole MVPA landscape, devices and
companies") is not a fifth direction — it is **COI-first (or measure-first)
in broad universe mode, with a company-index rollup added** to the output.
Handle it as such.

### What each entry primitive actually does differently

- **COI-first** casts the widest net: all source channels, sub-construct
  vocabulary expansion, and the full naming-fragmentation recovery passes
  (below). This is the only direction that *generates* a universe from
  scratch, and it's the most expensive.
- **Measure-first** constrains the net to devices that can acquire the
  required signal and implement the locked algorithm. The measure must be
  locked *first* — searching before the measure is defined produces devices
  compared on different outputs. Universe is naturally small (5–20 devices);
  do not inflate it.
- **Device-first** *skips universe generation entirely* when the device(s)
  are named — it goes straight to Phase 2 scoring for those devices. The one
  subtlety: "find competitors in the same niche" re-introduces a
  COI-first-style search to populate the niche, so device-first-with-
  competitors partially collapses into COI-first. Do the narrow scoring
  first, then run a scoped COI-first pass only for the competitor set.
- **Company-first** has two steps: (1) *enumerate* the company's DHT products
  — from its own materials, the trials it sponsors, and papers by its named
  scientists — then (2) treat each enumerated product as a device-first
  entry. The enumeration step is the weak link (see Open Questions — there is
  no authoritative registry of "all DHTs a company makes," so completeness
  can't be guaranteed the way a PRISMA count can).

### What the output rollup changes

- COI-first / measure-first / device-first roll up **per device**.
- Company-first additionally rolls up **per company**: a company-level
  summary (how many products, strongest product, aggregate evidence posture,
  regulatory footprint) sitting above the per-product tiers.
- Broad modality landscape adds a **company index** — a table mapping every
  device in the universe to its vendor, so the reader can see the commercial
  landscape and the device landscape at once.

**[OPEN QUESTION — routing]** *Which skill decides the direction?* In the
pipeline, direction detection is a router-node job, not this skill's — this
skill should be told the direction, not infer it. Standalone, this skill
infers it from the query. The boundary is currently unspecified and must be
resolved when the router is built. See Open Questions ledger at the end.

---

## Two Output Phases: Universe (breadth) then Scoring (quality)

**Device breadth and evidence quality are separated into two phases.**
Collapsing them produces either an inflated evidence picture (every found
device tiered on thin evidence) or an artificially narrow universe (devices
dropped before scoring because evidence looked thin at search time).

- **Universe phase:** record every device found, with only name, source
  channel, context-of-use flag, and a raw evidence-density count (papers +
  CT registrations naming it as an outcome instrument). **No tier
  assignment.** A device with zero indication papers still appears
  (`evidence density: 0, commercial-only`), not excluded, not pre-demoted.
- **Scoring phase:** the 12-criterion rubric applies only to devices passing
  a minimum threshold — ≥1 peer-reviewed paper OR ≥1 CT registration naming
  the device as an outcome instrument, and commercially available or
  near-commercial.

This makes every exclusion traceable to a scored criterion rather than an
impression at search time. **Note:** device-first with named devices skips
the universe phase (the device is the universe); company-first runs the
universe phase only over the enumerated product set, not the whole field.

---

## Retrieval Requirements
### (execution belongs in Python; the reasoning below is the specification that retrieval must satisfy)

Everything in this section was, in the original skill, written as literal
step-by-step tool-call sequences for the model to execute. **The execution moves to
Python (`retrieval.py` + a `recall_patterns.py` module — the latter not yet
built). What stays here is the *why*, because none of it is retrieval
mechanics — it is durable knowledge about how DHT literature and device
naming behave, and it does not go stale.**

### The vocabulary-gap problem (sub-construct elicitation)

A COI label ("Range of Motion," "Gait," "Motor Function") is a category, not
a search term. The literature uses the specific clinical construct or task
that operationalizes it *in that indication* — almost never the label.
Searching the label alone yields a systematically incomplete universe no
matter how many queries run, because the gap is in the vocabulary, not the
depth. Examples of silent failure: "Range of Motion" in ALS → literature
says "reachable workspace," "head drop," "cervical movement"; "Gait" in
Parkinson's → "freezing of gait," "timed up and go," "step length
variability"; "Motor Function" in DMD → "North Star Ambulatory Assessment,"
"time to rise," "4-stair climb."

**Requirement:** before any COI-first universe search, sub-construct
vocabulary must be derived from three sources — (a) known clinical context
for the indication, (b) the exact outcome-measure text strings from
completed Phase 2/3 trials in that indication (the most reliable source: it
is the literature's own vocabulary), (c) the same check against adjacent
indications, tagged at lower weight. Sub-constructs are *added as parallel
search lanes*, never substituted for the label. Every sub-construct used is
recorded, so a reader comparing two runs can tell a vocabulary change from a
data change.

**[OPEN QUESTION — split point]** Sub-construct elicitation is genuinely
split-brain between Python and skill, and the boundary is shaky:
- *Generating candidate sub-constructs from clinical knowledge* (step a) is
  LLM domain knowledge — belongs in a skill/model call.
- *Pulling outcome-measure text from ClinicalTrials.gov* (step b) is
  deterministic retrieval — belongs in Python.
- *Deciding which newly-pulled outcome strings are genuinely new
  sub-constructs worth adding* is LLM judgment again.
So a single logical step ping-pongs Python → model → Python → model. This is
implementable (the pipeline already has an LLM-dispatch shim in `screen.py`
that a retrieval helper could reuse) but the control flow is not designed
yet. Flagged to resolve. Do not assume it's a clean one-sided lift.

### The naming-fragmentation problem (why a naive universe undercounts)

Three failure modes cause a real, deployed, validated device to be
systematically absent from a naive search — none fixed by searching harder
with the same method, only by searching *differently*.

**1. PI-branded companies.** The commercial brand never appears in any
PubMed title/abstract/MeSH field because every publication is authored under
the academic PI's name or university, not the company. A company-name PubMed
search returns zero results even with substantial validation. Most prevalent
in: speech/acoustic platforms (PI is a communication-sciences academic),
digital cognitive assessment (PI is a neuropsychologist), algorithm-only
DHTs (academic spinouts), small startups with an academically-appointed lead
scientist. *Recovery:* for any commercial device with zero PubMed hits under
its own name, identify named scientific founders from public materials, then
search PubMed by PI name × indication × the specific construct measured (a
construct-level search — "articulatory precision," "saccadic velocity" —
needs no company name at all). For software-platform-dominated COIs, run
this proactively for the 2–3 most-cited academic groups *before* any company
is identified.

**2. Methods-section-only naming.** The device is named only in the Methods
section — never title/abstract/affiliations — because the paper's finding is
about the disease construct and the device is "just" the instrument.
Field-restricted searches never surface these by device name. *Recovery:*
category-level reverse search using a generic measurement descriptor ("eye
tracking," "acoustic analysis platform," "dynamometry") instead of a product
name; for papers not already captured, fetch metadata and scan Methods for a
named device.

**3. Device-class systematic under-naming.** Failure mode 2 is reliable for
specific device *classes* — the paper reports "FVC" or "muscle strength" or
"physical activity," never the instrument. **Whenever a listed class is
relevant to the COI, the recovery pass must run for it** — a completeness
requirement, not optional deepening, which is exactly why it belongs in
always-executed Python rather than an LLM judgment about whether to bother:

| Device class | Reported-as (why it's methods-only) | Generic recovery query shape |
|---|---|---|
| Named spirometers | "FVC" / "spirometry" | indication × spirometry × clinical-outcome correlation |
| Named dynamometers | "muscle strength" / "grip strength" | indication × dynamometry × outcome-measure |
| Named accelerometers/activity monitors | "physical activity" / "steps" | indication × accelerometry × clinical-outcome |
| Named goniometers/IMU systems | "ROM" / "kinematics" | indication × sub-construct × inertial-sensor |
| Named PSG/sleep systems | "sleep quality" / "AHI" | indication × sleep-construct × clinical trial |

**This table is durable domain knowledge, not a cached answer.** Unlike a
stale precedent list, "spirometry papers name the device in Methods, not the
abstract" is a stable property of how that literature is written — it does
not need re-deriving each run. It should live as extensible config in
`recall_patterns.py`; new classes are added as rows when a new fragmentation
pattern is found. The *judgment* that stays with the model even after
execution moves to Python: for a paper a recovery query surfaces, deciding
whether it actually describes the class and names a specific device — a
record-level classification call, structurally identical to what the
screening node already does.

**[OPEN QUESTION — the highest-stakes one]** The recall-recovery passes are
very likely a large part of why the original ALS report was good. In the
pipeline they are currently **unbuilt** (`recall_patterns.py` does not
exist). Until it does, a pipeline run under-counts exactly the PI-branded and
methods-section-only devices this skill was best at catching. Two
implications to resolve, not paper over: (1) the device-class recovery is
"run these query templates" (Python) + "does this hit match the class"
(model) — same split-brain control-flow problem as sub-construct
elicitation, and it should reuse whatever pattern resolves that one; (2)
until `recall_patterns.py` exists, either run this skill standalone (model
does recovery itself) or accept a known recall gap in pipeline runs and say
so in the report's methodology. Do not silently ship a pipeline landscape
that skipped recovery.

### Clinical outcome assessment (COA) tools — a separate lane

COA tools live in trial-methodology literature, not product catalogues, and
predate the "DHT" framing — commercial searches systematically miss them,
and skipping the lane omits the current gold standard for the COI. Search
ClinicalTrials.gov **by outcome-measure text**, not intervention type — the
most reliable way to surface them. A tool found only via outcome-measure
text with no vendor page is included with a COA flag; commercial presence is
not a prerequisite when a tool is a pre-specified endpoint in a completed
Phase 2/3 trial.

### Universe filtering and scope

*Include:* commercially available or near-commercial with an identifiable
vendor; measures ≥1 confirmed COI; ≥1 peer-reviewed paper OR trial
registration with outcome-measure text; COA tools per above.
*Exclude:* custom academic sensors with no trial-endpoint record and no
commercial path; generic vital-sign-only monitors with no disease-specific
endpoint; digitized PRO apps with no passive sensor signal; non-peer-reviewed
sources only (watchlist, don't drop); confirmed-discontinued (document
when/source, then exclude).

Every excluded device is logged with a reason code. Universe size is reported
before scoring (per channel, after dedup, entering scoring) so a thin
landscape is visible, not silently accepted.

**[OPEN QUESTION — deferred filtering vs. eligibility screen]** The original's
"broad mode" deferred all feasibility filtering to the scoring phase. The
pipeline already has an eligibility screen (`screen.py` + `criteria.py`)
running *before* this skill sees anything. These two filtering philosophies
overlap and may conflict: the screen might exclude a commercial-only device
that broad mode intends to keep as a Tier 4 watch entry. Which layer owns
"keep thin-evidence commercial devices for the horizon list" is unresolved.
Flagged — resolve when wiring this skill to the screening node.

---

## Phase 2 — Scientific Scoring Pass (direction-invariant)

Apply the full 12-criterion rubric to every device in the filtered universe
(or, for device-first, to each named device). Execute systematically — never
skip criteria because a device looks weak or strong at a glance.

**Extraction per paper:** title/authors/journal/year/DOI, study design,
patient population (N patients, N HCs, severity), validation domain
(diagnostic / concurrent validity / longitudinal / analytical-only),
performance metrics with CI and p-value, gold-standard comparator, validation
setting, bias indicators. Abstract-only extraction must be flagged — method
details (blinding, sampling, operator training) aren't visible.

**External validity (1–4):**

| Criterion | Weak | Moderate | Strong |
|---|---|---|---|
| 1. Publication count (clinical) | <3 | 3–5 | 5+ |
| 2. Journal rank | Q3–Q4 | Q2 | Q1 |
| 3. Impact factor | <2 | 2–5 | >5 |
| 4. Author independence | Company sole authorship | Mixed | Fully external |

**Internal validity (5–9):**

| Criterion | Weak | Moderate | Strong |
|---|---|---|---|
| 5. Patient population | No specific disease | Non-adjacent indication | Target/adjacent indication |
| 6. Sample size (patients) | <15 | 15–50 | >50 |
| 7. Validation setting | Specialist clinic, single-site, no remote | PCP/multi-site or mixed | At-home/remote or unsupervised in patients |
| 8. Risk of bias | High (unmitigated) | Moderate | Low |
| 9. Comparator strength | Non-disease measure | Disease-adjacent scale | Target-indication gold standard |

**Context of Use (COU) is a flag, not a scored criterion.** Criterion 7
scores validation-setting rigor as evidence quality; COU compatibility with
the trial's deployment context is a separate flag (Clinic-only / Clinic+home
/ Home-first / Remote-first; unsupervised-use evidence; match/partial/
mismatch vs. trial) that does *not* alter the composite or tier. This stops a
clinic-only device with strong Phase 3 evidence being auto-downgraded beneath
a home-use device with weaker evidence — the team weighs COU fit; the rubric
doesn't decide it by suppressing rank.

**Endpoint use-case (10–12) — the most important:**

| Criterion | Weak | Moderate | Strong |
|---|---|---|---|
| 10. Validation domain | Analytical only (HV/bench) | Diagnostic classification only | Concurrent validity in patients |
| 11. Longitudinal sensitivity to change | Not assessed | Disease-duration correlation only | Repeated measures with change score |
| 12. Trial endpoint fit | No trial use found | Exploratory endpoint only | Secondary/primary in RCT |

**Criteria 10, 11, 12 never collapse into one "clinical validation" rating.**
A device can be Strong on 10 (good HC-vs-patient AUC), Weak on 11 (no
repeated measures), Weak on 12 (never in an RCT) — that means scientifically
interesting but not trial-ready, and the distinction must survive into the
matrix.

**Bias indicators** (flag explicitly): company sole authorship; single site;
no pre-registered analysis plan; post-hoc best-metric selection; severity
not reported/controlled; HC sample from different site/time than patients;
abstract-only. ≥2 = High, 1 = Moderate, 0 = Low.
**A High bias rating on the only paper caps the device at Moderate evidence
regardless of AUC — non-negotiable, never overridden by a strong metric.**

**Patient population tiers:** T1 (validated in target indication) → T4 (HV /
analytical only). Assign the highest justified by the best paper.

**[OPEN QUESTION — partial Python opportunity, not shaky, worth noting]**
Criteria 1, 3, 6 (publication count, impact factor, sample-size thresholds)
are mechanical and could be pre-computed in Python from the corpus, leaving
the model only the judgment criteria (4, 7, 8, 9, 10, 11, 12). This would
improve consistency and auditability. Not required for correctness — the
model can score all 12 — but flagged as a clean optimization to consider.

---

## Phase 3 — COI-Specific Deep Dive (direction-invariant)

Run only for devices with composite evidence Moderate+ and population T1/T2.
T3/T4-only devices get a two-row summary, keeping depth proportional to
evidence quality rather than uniform.

**Longitudinal validity (mandatory for any Tier 1/2 device)** — answer
explicitly, flagging GAP rather than inferring: repeated-measures study
(same patients, ≥2 timepoints) in target/adjacent indication? within-patient
change score at a meaningful interval? SEM or MDC reported? MID/MICD
established, or a method paper for estimating one? did it detect a
between-arm difference in any trial where used? **A device with strong
cross-sectional performance but no change-score, MID, or treatment-
sensitivity answers is an exploratory candidate, not a primary/secondary one
— state this explicitly for every qualifying device.** This is the single
most common way a scientifically-strong device gets mis-recommended.

**Analytical-only devices:** what signal, what gold standard, what population
(HV or patients?), correlation magnitude (r ≥ 0.80 for substitution;
0.60–0.79 exploratory only), any trial use as an exploratory measure.

**Regulatory fit per device:** is the construct named as an endpoint of
interest in FDA/EMA guidance (fetch and cite the section — never rely on
training knowledge for regulatory position, guidance is revised); used as
primary/secondary/exploratory in a completed trial; any agency comment in an
advisory record; device clearance for a relevant intended use (clearance ≠
endpoint acceptance, but absence is a gap for non-exploratory use).

**Measure-fidelity (measure-first direction only):** native implementation
vs. offline export; pinnable algorithm version; equivalence vs. reference
(ICC, N, population); operator training and intra-/inter-operator ICC;
multi-site harmonization; published SOP. Rate High / Moderate / Low. **A
device that is standard-Tier-1 but measure-fidelity Low is demoted to Tier 2
regardless of other evidence** — it can't reliably implement the locked
measure. State the demotion explicitly.

---

## Phase 4 — Priority Matrix and Shortlist (direction-invariant scoring; rollup varies)

**Evidence matrix:** Y-axis evidence strength, X-axis one column per COI,
cells show device with longitudinal-readiness, trial-endpoint-readiness, and
COU flags. Every filtered-universe device appears; excluded devices live in
the Exclusion Log, not the matrix.

**Tier assignment — read COI maturity (established vs. nascent) before
applying any gate; the wrong gate on a nascent COI yields a structurally
empty matrix.**

**Tier 1 — Progress.** *Established COIs*, all must hold: composite Moderate+;
population T1/T2; longitudinal Yes/Partial; trial-endpoint secondary/
primary-capable; no bias ceiling; FDA/CE clearance for non-exploratory use;
COU match/partial (mismatch noted, doesn't block). A device meeting all but
longitudinal readiness may still be Tier 1 for an exploratory endpoint only —
state it. *Nascent COIs*, all must hold: composite Moderate+; population
T1/T2; ≥1 repeated-measures study in target/adjacent indication (no MID
required); no bias ceiling; clearance preferred but its absence is a flagged
gap, not a demotion. **The nascent-COI question is "which device has the most
credible signal in this population," not "which is trial-ready"** — Tier 1
here means best-available-candidate warranting a pilot, and the label says so.

**Tier 2 — Diligence.** Established: meets ≥4 of 7 Tier-1 criteria, fails ≤2
(common patterns: strong indication evidence but no longitudinal; good
longitudinal but wrong population; strong science but clearance in-process;
high bias on primary paper with other low-bias papers; COU mismatch).
Nascent: composite Moderate+, any population tier, diagnostic-classification
evidence exists, no unmitigated bias ceiling. Every Tier 2 device gets
specific diligence questions — what data would move its tier.

**Tier 3 — Monitor.** Analytical-only, or clinical validation in non-adjacent
population only, or emerging/preprint only, or not yet commercial. Tracked,
not excluded, with the milestone that would move it to Tier 2.

**Tier 4 — Watch List (horizon).** Universe devices with zero papers and zero
CT registrations — commercial/horizon-scan only. **Not a failure state; often
the most commercially advanced devices for a nascent COI, ahead of their
publication record.** Per entry: regulatory signal (BDD/De Novo/CE — cited
specifically), one-sentence inclusion rationale, advancement trigger,
recommended action. No composite score, no endpoint recommendation.

**Within-tier ranking:** unweighted count of Strong ratings across the 12
criteria; ties within 1 point are effectively equivalent — don't overclaim
precision.

**Measurement-niche deduplication (mandatory):** for any COI with 2+ Tier 1/2
devices, check whether each pair measures the same sub-construct via the same
modality and, if substitutable, which has stronger evidence/regulatory/
maturity. The weaker device isn't removed — it's compared with a written
retention rationale.

**Cross-COI coverage:** per COI — how many Tier 1 devices, is one home/remote-
capable, is one cleared, and if no Tier 1 exists, what's the gap. A stated
COU preference is a within-tier tie-breaker, never an exclusion criterion.

**Rollup by direction (this is where output grouping changes):**
- COI-first / measure-first: the matrix above, grouped by COI.
- Device-first: skip the matrix; produce a per-device deep dive, and a
  side-by-side comparison table if multiple devices were named.
- Company-first: the per-product tiers above, plus a **company-level
  summary** — product count, strongest product and its tier, aggregate
  evidence posture, consolidated regulatory footprint, and the single
  sentence a reader most wants ("Company X's DHT footprint is [N products],
  strongest is [product] at Tier [t], concentrated in [COI/modality], with
  [regulatory status]").
- Broad modality landscape: the COI-first matrix plus a **company index**
  (device → vendor table) so commercial and device landscapes are both visible.

---

## Phase 5 — Gap Log and Recommendations (direction-invariant)

**Gap log** — every gap from Phases 1–4:
```
[GAP-ID] Category: [Scientific/Regulatory/Commercial/Operational]
  Item: [specific missing information]
  Affects: [which devices/sections]
  Required from: [vendor / internal / literature not yet retrieved / agency]
  Priority: [Blocking / High / Moderate / Low]
  Specific question to ask: [exact question for a vendor call or internal request]
```
Recurring categories: longitudinal data for Tier 2 diagnostic-only devices;
missing MID/MICD; vendor trial/pharma-partnership history; data-infrastructure
interoperability; pricing/study-support model; country availability; stale
"submission in process"; abstract-only papers needing full text.

**Prior-landscape reconciliation** (only if a prior landscape exists): every
device in the prior top two tiers must be present at a stated current tier or
explicitly accounted for — scope exclusion, evidence downgrade (with delta),
knowledge gap (search failure: add it back and score it now), or superseded
(name what superseded it). Output as a table (prior tier → current tier →
status → reason). **This table must appear** — it's what makes two runs
comparable rather than mysteriously different.

**Recommendations**, from assembled evidence only: per-COI device
recommendation with the specific criteria met, plus the strongest competitor
and key differentiator; per-device endpoint-use recommendation
(primary/secondary/exploratory) from the Phase 3 longitudinal assessment, not
marketing claims — flag any primary-endpoint recommendation lacking MID/MICD
as a sample-size gap; regulatory-pathway notes flagging any COI lacking
direct guidance support (cite the strongest cross-indication precedent —
searched fresh, not recalled from a fixed list; same principle as dht-str);
and a forward-looking Phase 3 readiness note per Tier 1 device.

---

## Quality Standards — Non-Negotiable

**No tier without a cited basis** — state which criteria were Strong and
which weren't. **Longitudinal validity always scored separately** from
diagnostic accuracy. **Bias ratings propagate to tiers, stated explicitly.**
**Sample size judged against its specific use case.** **All metrics include
CI and p-value** — if not reported, say so as a reporting gap, don't
estimate. **Regulatory status fetched, not recalled.**

**Citation hygiene (every evidence claim):**
1. Specific sample size needs an inline source: `n=54 (PMID: 12345678)`.
2. Regulatory-clearance claim needs the document number: `FDA 510(k) K231416`,
   not "FDA cleared"; if unverified in the run, say so and recommend the
   accessdata.fda.gov check.
3. Specific result (effect size, AUC, SRM) needs the primary source and its
   population; a predecessor device's result cited for a successor is flagged.
4. Vendor/press/conference claims not cross-checked against peer-reviewed
   sources are tagged `[UNVERIFIED — source: vendor/commercial]` inline.
5. DOIs preferred over PMIDs for Tier-1 primary references.
6. A key reference co-authored by an internal team member is flagged — a
   signal internal data may exist, not a conflict note.

**These rules govern claims about a device, not whether it appears** — a
device with zero citations is still a valid universe entry.

**The shortlist is tiered, never flat. COA tools are mandatory. Scope
exclusions are always documented** ("not found" ≠ "found but excluded").
**Broad-mode:** every excluded device in the Exclusion Log, source-channel
provenance per device, universe size reported before scoring.
**Measurement-niche substitutions documented, never silently omitted.**
**This is research input, not a finished report.**

---

## Pipeline Integration Note

As the evidence/device scoring node's system prompt in deep_researchDHT:

**Input received:** indication, COI(s), **direction** (COI/measure/device/
company-first — told, not inferred), COI maturity (established/nascent), and
a `corpus` of `Record` objects each with a stable `citation_id`, already
produced by `retrieval.py` (channels + recall recovery) and screened by
`screen.py`.

**Output shape** (maps onto `state.py`): per-device rubric scoring + tier →
`DeviceRow` (`v3_evidence` carries the 12-criterion breakdown;
`evidence_citations` are citation_ids only); every flagged issue → `Gap`; the
Exclusion Log, Tier 4 watch list, and (company-first) company rollup are
additional structured sections the docx builder renders. Every citation
emitted must resolve in the corpus — the `verify` node enforces this.

---

## OPEN QUESTIONS LEDGER — resolve before trusting an unattended pipeline run

These are the shaky Python-vs-skill boundaries and unbuilt pieces, collected
in one place so they don't get lost in the prose above. Ordered by stakes.

1. **`recall_patterns.py` does not exist yet (HIGHEST STAKES).** The
   naming-fragmentation recovery (PI-branded, methods-section, device-class)
   is very likely a major reason the original ALS report was strong. In the
   pipeline it is currently unbuilt. Until it exists: run standalone (model
   does recovery), or accept and *disclose* a recall gap in pipeline runs.
   Do not ship a pipeline landscape that silently skipped recovery.

2. **Split-brain control flow (Python → model → Python) is undesigned.** Both
   sub-construct elicitation and device-class recovery need: Python runs a
   query template → model judges which hits are relevant/new → Python
   continues. The pipeline has an LLM-dispatch shim (`screen.py`) that could
   be reused, but the actual control flow (who calls whom, how partial
   results accumulate in state) is not designed. Resolve once; both features
   depend on it.

3. **Direction detection ownership is unspecified.** In the pipeline the
   router should tell this skill its direction; standalone this skill infers
   it. The handoff contract (what field carries direction into the node)
   isn't defined. Resolve when building the router — and note the router
   itself needs a new "device-first / company-first" classification branch
   that the current dht-router does not have.

4. **Deferred-filtering vs. eligibility-screen conflict.** Broad mode defers
   feasibility filtering to scoring; the pipeline screens eligibility
   *before* this skill runs. They can disagree about keeping thin-evidence
   commercial devices for the Tier 4 watch list. Decide which layer owns the
   "keep for horizon" call. Resolve when wiring to `screen.py`.

5. **Company-first enumeration has no completeness guarantee.** There is no
   authoritative registry of "all DHTs company X makes." Enumeration from
   website + sponsored trials + PI papers is inherently incomplete and the
   incompleteness is not measurable like a PRISMA count. The report must
   state this limitation explicitly for company-first landscapes rather than
   implying exhaustiveness.

6. **Device-first-with-competitors partially collapses into COI-first.**
   Finding same-niche competitors re-introduces a universe search. Decide
   whether "compare these devices" stays narrow (score only what's named) or
   auto-expands to the niche — probably a user/router choice, not a default.

7. **Partial-Python scoring (optional, not shaky).** Mechanical criteria (1,
   3, 6) could be pre-computed in Python for consistency, leaving the model
   the judgment criteria. Clean optimization, not required for correctness.

8. **`coi-search-terms.md` and other original reference files are dropped.**
   The original loaded per-COI search-term files and per-COI modules. Those
   become either `recall_patterns.py` config or the router's rubric-fragment
   library. Confirm nothing domain-critical lived in them beyond search
   strings before discarding — flagged for a read-through, same as the
   dht-str COI modules.
