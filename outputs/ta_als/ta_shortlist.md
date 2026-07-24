# TA-First COI Shortlist — ALS

Corpus: **4490** records (CTG: 1138, PubMed: 3497; after dedup: 4490).
Candidate COIs surfaced: **22** | scored: **22**.

> V1 output for **human review**. Verify the shortlist, then run the coi_first pipeline on the accepted COIs. Draft criteria stubs are at the end.

## Recommendation matrix (clinical importance × digital measurability)

| COI | Importance | Measurability | Quadrant | Action |
|---|:-:|:-:|---|---|
| respiratory_function | 5/5 | 4/5 | core and measurable | **recommend** |
| communication_ability | 4/5 | 5/5 | core and measurable | **recommend** |
| overall_functional_status | 5/5 | 3/5 | core and measurable | **recommend** |
| speech_function | 4/5 | 4/5 | core and measurable | **recommend** |
| muscle_strength | 5/5 | 3/5 | core and measurable | **recommend** |
| physical_mobility | 4/5 | 3/5 | core and measurable | **recommend** |
| upper_limb_function | 4/5 | 3/5 | core and measurable | **recommend** |
| sleep_quality | 3/5 | 4/5 | peripheral but measurable | **consider** |
| muscle_composition | 3/5 | 4/5 | peripheral but measurable | **consider** |
| swallowing_function | 4/5 | 2/5 | core not yet measurable | **white_space** |
| survival | 5/5 | 1/5 | core not yet measurable | **white_space** |
| neurophysiological_integrity | 3/5 | 3/5 | peripheral but measurable | **consider** |
| quality_of_life | 4/5 | 1/5 | core not yet measurable | **white_space** |
| cognitive_function | 4/5 | 1/5 | core not yet measurable | **white_space** |
| nutritional_status | 4/5 | 1/5 | core not yet measurable | **white_space** |
| psychological_distress | 3/5 | 1/5 | peripheral and unmeasured | **deprioritize** |
| fatigue | 3/5 | 1/5 | peripheral and unmeasured | **deprioritize** |
| caregiver_burden | 3/5 | 1/5 | peripheral and unmeasured | **deprioritize** |
| spasticity | 3/5 | 1/5 | peripheral and unmeasured | **deprioritize** |
| dyspnea | 3/5 | 1/5 | peripheral and unmeasured | **deprioritize** |
| pain | 2/5 | 1/5 | peripheral and unmeasured | **deprioritize** |
| muscle_cramps | 2/5 | 1/5 | peripheral and unmeasured | **deprioritize** |

## Recommended — core & digitally measurable

### Overall Functional Status  (`overall_functional_status`)
- **Clinical importance 5/5** — ALSFRS-R is the most widely used primary endpoint across ALS trials, appearing in nearly every Phase 2/3 study in the corpus as the primary or co-primary outcome measure (e.g., NCT07325591, NCT07174492, NCT07082192, NCT07322003). ROADS and CAFS also appear as key secondary endpoints, confirming composite functional status is central to disease progression measurement [NCT07325591]
- **Digital measurability 3/5** — NCT06820008 is specifically designed to explore 'Use of Digital Technologies' for measurement of physical impairment in ALS, with System Usability Scale and 12-month follow-up as outcomes. However, the ALSFRS-R itself remains primarily a clinician/patient-reported scale without validated sensor-based replacement yet [NCT06820008]
- **Literature vocabulary:** ALSFRS-R, ALS Functional Rating Scale-Revised, ALSFRS-R total score, ALSFRS-R sub-domain scores, Rasch Overall ALS Disability Scale (ROADS), functional decline, disease progression, King's Clinical Severity Staging, functional status, Combined Assessment of Function and Survival (CAFS), Norris Scale Score
- **DHT precedent:** digital technologies for physical impairment measurement (NCT06820008)
- **Evidence:** NCT07396818 (Kamlanoflast In Amyotrophic Lateral Sclerosis, 2026); NCT07325591 (Efficacy and Safety of Tazbentetol in ALS Participants, 2026); NCT07322003 (Pridopidine Phase 3 Study to Evaluate Efficacy and Safety in ALS, 2026); NCT07174492 (Efficacy and Safety of Masitinib in Combination With SoC Versus Placeb, 2026) +12 more

### Respiratory Function  (`respiratory_function`)
- **Clinical importance 5/5** — Respiratory measures (SVC, FVC, MIP) appear as primary or key secondary endpoints across numerous trials. Respiratory failure drives mortality in ALS, with time to permanent ventilation used as a survival surrogate (NCT07082192, NCT07410806). Multiple Phase 3 trials use %FVC as co-primary endpoint [NCT07410806]
- **Digital measurability 4/5** — Strong DHT precedent: NCT07502677 validates SleepImage wearable technology for detecting respiratory failure in ALS with outcomes including hypoxic burden, T90, and pulse rate variability. NCT04089696 validates ExSpiron respiratory volume monitor against pneumotachometer. NCT07413718 uses nocturnal pulse oximetry as an endpoint [NCT07502677]
- **Literature vocabulary:** slow vital capacity (SVC), forced vital capacity (FVC), percent predicted FVC, maximal inspiratory pressure (MIP), maximal expiratory pressure (MEP), cough peak flow (CPF), lung insufflation capacity (LIC), maximum insufflation capacity (MIC), sniff nasal inspiratory pressure (SNIP), transcutaneous carbon dioxide (TcCO2), oxygen saturation, spirometry, respiratory function, peak inspiratory flow rate (PIFR), respiratory insufficiency, diaphragmatic excursion, diaphragmatic thickening, oxygenation index, lung volumes, arterial blood gas (PaO2, PaCO2)
- **DHT precedent:** SleepImage wearable for detecting respiratory failure (NCT07502677); ExSpiron respiratory volume monitor (NCT04089696); nocturnal pulse oximetry (NCT07413718)
- **Evidence:** NCT07396818 (Kamlanoflast In Amyotrophic Lateral Sclerosis, 2026); NCT07410806 (HEALEY ALS Platform Trial - Regimen I NUZ-001, 2026); NCT07071935 (A Clinical Trial of Early Ventilation in Amyotrophic Lateral Sclerosis, 2026); NCT07257302 (Lung Insufflation Capacity Training and Respiratory Function in Amyotr, 2025) +15 more

### Speech Function  (`speech_function`)
- **Clinical importance 4/5** — Quantitative speech assessment is a secondary endpoint in the Phase 3 pridopidine trial (NCT07322003) measuring speaking rate and intelligibility. Bulbar subdomain of ALSFRS-R is separately tracked. Speech decline is a sensitive indicator of bulbar disease progression [NCT07322003]
- **Digital measurability 4/5** — NCT07341334 specifically studies 'Digital Speech Markers for Monitoring ALS' with outcomes including oral speaking rate, maximum phonation time, and listener effort using digital recording/analysis. NCT07322003 uses 'quantitative speech assessment in the clinic' as a Phase 3 endpoint. NCT06819124 examines formant frequencies and duration of speech sounds digitally [NCT07341334]
- **Literature vocabulary:** speaking rate, oral speaking rate, intelligibility, maximum phonation time, listener effort, formant frequencies, duration of speech sounds, syntactic properties, pragmatic properties, quantitative speech assessment, digital speech markers, bulbar subdomain of ALSFRS-R, communication
- **DHT precedent:** digital speech markers and quantitative speech assessment (NCT07341334, NCT07322003)
- **Evidence:** NCT07341334 (Digital Speech Markers for Monitoring ALS in Spanish Speakers, 2026); NCT07322003 (Pridopidine Phase 3 Study to Evaluate Efficacy and Safety in ALS, 2026); NCT07589764 (A Widely Inclusive, Hybrid-Decentralized Pilot Trial Utilizing β-hydro, 2026); NCT06819124 (Examining Interactions Between PALS and Caregivers, 2025) +2 more

### Muscle Strength  (`muscle_strength`)
- **Clinical importance 5/5** — Muscle strength is the cardinal feature of ALS, measured in nearly every interventional trial. HHD megascore is a primary endpoint (NCT06849609), ATLIS appears as key secondary (NCT06649955), and grip strength is tracked extensively (NCT07298486, NCT04220190). Multiple Phase 3 trials include quantitative strength measures [NCT06849609]
- **Digital measurability 3/5** — Handheld dynamometry devices produce digital output and are used across multiple trials (NCT06849609, NCT02478450, NCT04220190). Grip dynamometers (NCT07298486) and ATLIS systems (NCT06649955) are device-based quantitative measurements. However, these are primarily clinic-based measurement devices rather than remote/wearable DHTs [NCT06849609]
- **Literature vocabulary:** handheld dynamometry (HHD), grip strength, pinch strength, finger tip pinch, palmar pinch, key pinch, MRC scale, manual muscle test (MMT), Accurate Test of Limb Isometric Strength (ATLIS), HHD megascore, muscle strength
- **DHT precedent:** handheld dynamometry devices (NCT06849609, NCT02478450)
- **Evidence:** NCT06849609 (A Study to Evaluate the Tolerability, Safety and Efficacy of VGN-R13 i, 2025); NCT07298486 (Impact of Robotic Glove Use on Quality of Life, Grip Strength and Fine, 2026); NCT02478450 (Study to Investigate the Safety of the Transplantation (by Injection) , 2026); NCT06726577 (TP04HN106 in the Treatment of Patients With Amyotrophic Lateral Sclero, 2026) +8 more

### Physical Mobility and Gait  (`physical_mobility`)
- **Clinical importance 4/5** — Walking capacity and mobility are tracked through timed functional tests (NCT07478172), 2-Minute Walking Test (NCT06881979), Time Up and Go (NCT06881979), and the ALSFRS-R climbing stairs item (NCT07341984). Salbutamol trial (NCT05860244) uses walking capacity as primary endpoint, confirming clinical relevance [NCT05860244]
- **Digital measurability 3/5** — NCT06820008 specifically investigates digital technologies for measuring physical impairment in ALS with usability outcomes. NCT06819358 uses 'gait instrument' as an outcome measure for postural gait disorders in ALS. These demonstrate emerging digital approaches to mobility assessment, though validation is still in progress [NCT06820008]
- **Literature vocabulary:** walking capacity, 2-Minute Walking Test, Time Up and Go Test, gait, postural gait disorders, climbing stairs, timed functional tests, broad jump, multidirectional lunge test, walking scale, trunk control
- **DHT precedent:** digital technologies for physical impairment measurement (NCT06820008); gait instrumentation (NCT06819358)
- **Evidence:** NCT05860244 (Effect of Salbutamol on Walking Capacity in Ambulatory ALS Patients, 2024); NCT06881979 (High-Tech Rehabilitation Pathway for Chronic Adult Neuromuscular Disea, 2025); NCT06819358 (Individualized Functional Imaging-Guided Repetitive Transcranial Magne, 2025); NCT07341984 (A Physiotherapy Intervention Study in Patients With Amyotrophic Latera, 2025) +3 more

### Upper Limb Function and Dexterity  (`upper_limb_function`)
- **Clinical importance 4/5** — Upper limb function is measured via 9 Hole Peg test (NCT07298486), QuickDASH, Fugl-Meyer Assessment, ABILHAND Scale, and ARAT in NCT07636538. Functional eating status (NCT07151950) and robotic glove assessment (NCT07298486) target hand/arm function decline that compromises independence [NCT07298486]
- **Digital measurability 3/5** — NCT07298486 uses a robotic glove to assess grip strength and fine motor control (9 Hole Peg test) as a device-based intervention/measurement. NCT07636538 deploys an 'Auto-calibrating System for Upper Limb disability Assessment' with multiple quantitative outputs. These represent device-based digital measurement approaches [NCT07636538]
- **Literature vocabulary:** 9 Hole Peg test, hand function, Quick Disabilities of Arm Shoulder and Hand (QuickDASH), Fugl-Meyer Assessment, ABILHAND Scale, Action Research Arm Test (ARAT), fine motor control, functional eating status
- **DHT precedent:** robotic glove for grip and fine motor assessment (NCT07298486); auto-calibrating upper limb rehabilitation system (NCT07636538)
- **Evidence:** NCT07298486 (Impact of Robotic Glove Use on Quality of Life, Grip Strength and Fine, 2026); NCT07636538 (Auto-calibrating System for Upper Limb Disability Assessment, Neurolog, 2026); NCT07067229 (Non-invasive Brain Stimulation and Exercise Intervention for Patients , 2025); NCT07151950 (Obi Medical Robot: Evaluating Effectiveness Related to Usability, 2025)

### Communication Ability (Assistive Technology / BCI)  (`communication_ability`)
- **Clinical importance 4/5** — Communication restoration is the primary functional goal of multiple BCI/AT trials. NCT07407725 assesses performance outcomes for AT and BCI devices with ALSFRS-R context. Progressive locked-in state makes communication throughput a critical functional endpoint for severely affected ALS patients [NCT07407725]
- **Digital measurability 5/5** — Extensive DHT precedent: implantable BCIs (Neuralink N1 NCT07224256, Synchron Stentrode NCT07446114/NCT07543367, Paradromics Connexus NCT07357428), non-invasive EEG BCI (Cognixion ONE NCT06810219 measuring WPM and ITR), ECoG speech decoding (NCT07460037), and eye tracking. Multiple devices with quantitative communication throughput metrics [NCT07224256]
- **Literature vocabulary:** words per minute (WPM), phrases per minute, information transfer rate (ITR), BCI control, cursor task performance, system usability, assistive technology, eye tracker, speech BCI, neural decoding
- **DHT precedent:** implantable BCI (Neuralink N1, Synchron Stentrode, Paradromics Connexus); non-invasive EEG BCI (Cognixion ONE); eye tracking; ECoG-based speech decoding
- **Evidence:** NCT07357428 (Connect-One: Early Feasibility Study of Connexus® Brain-Computer Inter, 2026); NCT07446114 (Functional Outcomes and Control Using Synchron BCI - Canada, 2026); NCT07543367 (INdependence Through Endovascular Neuroprosthetic Technology (INTENT):, 2026); NCT06810219 (Augmented Reality BCI Longitudinal Study for Persons With Late Stage A, 2025) +13 more


## Consider — measurable but clinically peripheral

### Sleep Quality  (`sleep_quality`)
- **Clinical importance 3/5** — Sleep measures appear as secondary endpoints in respiratory and QoL-focused ALS trials: Epworth Sleepiness Scale (NCT07071935), Karolinska Sleepiness Scale (NCT07071935), quality of sleep (NCT06719947). While clinically relevant as an indicator of respiratory decline, sleep is not a primary disease progression endpoint [NCT07071935]
- **Digital measurability 4/5** — NCT07502677 validates SleepImage wearable technology specifically in ALS for detecting respiratory failure during sleep, with outcomes including pulse rate variability and hypoxic burden. NCT07413718 uses nocturnal pulse oximetry as a digital endpoint. These represent validated wearable approaches to sleep-respiratory monitoring [NCT07502677]
- **Literature vocabulary:** Epworth Sleepiness Scale (ESS), Karolinska Sleepiness Scale (KSS), quality of sleep, daytime sleepiness, nocturnal pulse oximetry, sleep quality, hypoxic burden, T90, pulse rate variability
- **DHT precedent:** SleepImage wearable for respiratory-sleep monitoring (NCT07502677); nocturnal pulse oximetry (NCT07413718)
- **Evidence:** NCT07071935 (A Clinical Trial of Early Ventilation in Amyotrophic Lateral Sclerosis, 2026); NCT06719947 (HD-tDCS in Amyotrophic Lateral Sclerosis: A Multicenter Randomized Con, 2025); NCT06841341 (Electrophysiology and Ultrasound of Respiratory Muscles and Respective, 2025); NCT07502677 (Diagnostic Accuracy of SleepImage Technology for Detecting Respiratory, 2026) +1 more

### Muscle Composition and Integrity  (`muscle_composition`)
- **Clinical importance 3/5** — EIM is used as a biomarker endpoint (NCT06491732, NCT02478450). Diaphragm ultrasound measures (excursion, thickening) appear in NCT07170865 and NCT06841341. Thigh muscle volume is tracked (NCT05860244). These are objective quantitative biomarkers but serve as supporting/exploratory measures rather than primary efficacy endpoints [NCT06491732]
- **Digital measurability 4/5** — NCT06491732 specifically validates the portable Myolex mScan EIM device as an ALS biomarker, tracking EIM phase change over time. NCT02478450 uses EIM values on bilateral limbs. These represent validated, portable, sensor-based devices for quantitative muscle composition assessment that could function outside traditional clinical settings [NCT06491732]
- **Literature vocabulary:** Electrical Impedance Myography (EIM), muscle volume, thigh muscle volume, diaphragmatic excursion, diaphragmatic thickening, diaphragm diameter, phrenic nerve cross-sectional area, muscle ultrasound
- **DHT precedent:** portable EIM device (Myolex mScan) as biomarker (NCT06491732); ExSpiron respiratory volume monitor (NCT04089696)
- **Evidence:** NCT06491732 (EIM Via the Myolex mScan as an ALS Biomarker, 2025); NCT02478450 (Study to Investigate the Safety of the Transplantation (by Injection) , 2026); NCT05860244 (Effect of Salbutamol on Walking Capacity in Ambulatory ALS Patients, 2024); NCT07170865 (Dynamic Impact of NIV on Diaphragmatic Ultrasound in Patients With Amy, 2025) +1 more

### Neurophysiological Integrity  (`neurophysiological_integrity`)
- **Clinical importance 3/5** — CMAP, MUNE/MUNIX, TMS measures appear as secondary/exploratory endpoints across multiple trials (NCT07067229, NCT06726577, NCT06681610, NCT06649955). Neurophysiological Index and denervation scores are used (NCT07312240, NCT06607900). These provide objective quantification but remain biomarker-level measures rather than regulatory primary endpoints [NCT07067229]
- **Digital measurability 3/5** — NCT07478172 uses decomposition electromyography (dEMG) for motor unit firing rate analysis as a primary outcome. Threshold tracking nerve conduction studies are device-based digital measurements (NCT06649955). TMS cortical excitability measures are device-derived (NCT06681610). These are specialized electronic devices producing digital data, though typically clinic-based [NCT07478172]
- **Literature vocabulary:** compound muscle action potential (CMAP), motor unit number estimation (MUNE), motor unit number index (MUNIX), motor evoked potential (MEP), cortical silent period (CSP), short intracortical inhibition (SICI), intra-cortical facilitation (ICF), resting motor threshold, threshold tracking nerve conduction, central motor conduction time (CMCT), Neurophysiological Index (NI), motor unit firing rates, denervation score (EMG), electromyographic activity
- **DHT precedent:** decomposition electromyography (dEMG) for motor unit analysis (NCT07478172)
- **Evidence:** NCT07067229 (Non-invasive Brain Stimulation and Exercise Intervention for Patients , 2025); NCT06726577 (TP04HN106 in the Treatment of Patients With Amyotrophic Lateral Sclero, 2026); NCT06681610 (Testing Pulse Stimulation to Improve Motor Function in People With ALS, 2024); NCT07478172 (Effects of Whole-body Electrical Muscle Stimulation Exercise on Adults, 2026) +5 more


## WHITE SPACE — core to the disease, no DHT precedent yet

### Swallowing and Oral Motor Function  (`swallowing_function`)
- **Clinical importance 4/5** — Swallowing measures track bulbar disease progression. Time to gastrostomy is used as a milestone endpoint (NCT07414212, NCT06126315). NCT07606235 specifically targets swallowing frequency and urge-to-swallow as primary outcomes. Aspiration risk and nutritional compromise make this clinically critical [NCT07606235]
- **Digital measurability 2/5** — NCT07295990 uses the TongueMeter device for measuring maximum anterior isometric lingual pressure, representing a device-based measurement approach. However, this is a single point-of-care device for one aspect of swallowing; no comprehensive wearable/remote digital swallowing monitoring approach is evidenced in the corpus [NCT07295990]
- **Literature vocabulary:** swallowing frequency, urge-to-swallow, videofluoroscopic swallowing evaluation, fiberoptic endoscopic evaluation of swallowing (FEES), lingual pressure, Test of Mastication and Swallowing Solids (TOMASS), EAT-10, jaw range of motion, mastication, oral hygiene, time to gastrostomy
- **DHT precedent:** TongueMeter device for lingual pressure (NCT07295990)
- **Evidence:** NCT07606235 (Transcutaneous Superior Laryngeal Nerve Stimulation to Upregulate Swal, 2026); NCT07295990 (Tongue-strengthening Exercises in People With ALS., 2026); NCT07187388 (Investigating the Impact of Electrical Stimulation on Facial Pain, Jaw, 2026); NCT06126315 (Trial on the Biological and Clinical Effects of Acetyl-L-carnitine in , 2025) +1 more

### Quality of Life  (`quality_of_life`)
- **Clinical importance 4/5** — QoL measures appear as secondary endpoints in major Phase 2/3 trials: ALSAQ-40 (NCT07325591, NCT07082192, NCT06126315), EQ-5D-5L (NCT07067229), ALSSQOL-SF (NCT07473765). The Phase 3 masitinib trial includes QoL as a co-primary endpoint (NCT07174492), confirming regulatory importance [NCT07174492]
- **Digital measurability 1/5** — No DHT/sensor precedent is evidenced in the corpus for measuring quality of life. All QoL assessments (ALSAQ-40, EQ-5D, ALSSQOL) are traditional patient-reported outcome questionnaires administered on paper or electronically, with no wearable or sensor-based approach identified [NCT02988297]
- **Literature vocabulary:** ALSAQ-40, ALS Assessment Questionnaire, ALS-Specific Quality of Life (ALSSQOL), ALSSQOL-SF, EuroQol-5D (EQ-5D), EQ-5D-5L, WHOQOL-BREF, individual quality of life, health-related quality of life, physical mobility, ADL/independence, eating and drinking, emotional reactions
- **Evidence:** NCT02988297 (Nebulized RNS60 for the Treatment of Amyotrophic Lateral Sclerosis, 2026); NCT07454733 (Do Video Recordings of Multidisciplinary Clinics Improve Quality of Li, 2026); NCT07325591 (Efficacy and Safety of Tazbentetol in ALS Participants, 2026); NCT07174492 (Efficacy and Safety of Masitinib in Combination With SoC Versus Placeb, 2026) +10 more

### Cognitive and Behavioral Function  (`cognitive_function`)
- **Clinical importance 4/5** — ECAS is included as a secondary endpoint in the Phase 2/3 tazbentetol trial (NCT07325591) and multiple other studies (NCT07407725, NCT06126315). Neuropsychological phenotyping is a primary outcome in NCT07312240. Cognitive impairment affects up to 50% of ALS patients and informs prognosis [NCT07325591]
- **Digital measurability 1/5** — No DHT/sensor precedent for cognitive measurement in ALS is evidenced in the corpus. All cognitive assessments (ECAS, MoCA, MMSE, FAB, Trail Making) are traditional neuropsychological tests administered in clinical settings without wearable or sensor-based digital alternatives demonstrated [NCT06126315]
- **Literature vocabulary:** Edinburgh Cognitive and Behavioural ALS Screen (ECAS), Montreal Cognitive Assessment (MoCA), neuropsychological phenotyping, cognitive and behavioral profile, MMSE, Frontal Assessment Battery (FAB), Trail Making Test, Stroop Test, Rey's 15-word test, semantic fluency, phonemic fluency
- **Evidence:** NCT07325591 (Efficacy and Safety of Tazbentetol in ALS Participants, 2026); NCT07407725 (Clinical Outcome Assessment for AT & BCI, 2026); NCT06126315 (Trial on the Biological and Clinical Effects of Acetyl-L-carnitine in , 2025); NCT06903286 (Extension Study of Participants From SPG302-ALS-001, 2025) +5 more

### Survival  (`survival`)
- **Clinical importance 5/5** — Overall survival is the most definitive endpoint in ALS. It appears as primary or co-primary outcome in Phase 3 trials (NCT07322003: overall survival at Week 96; NCT07082192: time to PAV/death). Tracheostomy-free survival is used in multiple trials (NCT07071935, NCT07257302). CAFS combines function and survival [NCT07322003]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring survival exists in the corpus. Survival is tracked through clinical records, death certificates, and study visits. While wearables could theoretically detect vital status, no such application is demonstrated in ALS trials [NCT07410806]
- **Literature vocabulary:** overall survival, tracheostomy-free survival, ventilation-free survival, time to death or permanent ventilation, time to permanent assisted ventilation (PAV), time to tracheostomy or death, survival adjusted for mortality, progression free survival
- **Evidence:** NCT07410806 (HEALEY ALS Platform Trial - Regimen I NUZ-001, 2026); NCT06513546 (A Study to Evaluate the Safety, Efficacy, and Pharmacodynamics of PLL0, 2026); NCT07571486 (Therapeutic Approach of Repeated Transient Blood-brain Barrier Opening, 2026); NCT07706270 (Serum Neurofilaments in the Diagnosis of Amyotrophic Lateral Sclerosis, 2026) +8 more

### Nutritional Status and Body Composition  (`nutritional_status`)
- **Clinical importance 4/5** — Body weight/BMI appears across multiple trials (NCT07606235, NCT06877143, NCT06765499). The hypercaloric nutrition trial (NCT06877143) uses BMI as a key secondary outcome. L3-SMI is used for skeletal muscle assessment (NCT06765499). Weight loss is an independent predictor of faster progression and mortality [NCT06877143]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring nutritional status in ALS is evidenced in the corpus. All nutritional assessments use clinical measures (body weight, BMI, bioelectrical impedance, CT imaging, dietary intake questionnaires) without demonstrated wearable or remote sensor-based digital approaches [NCT06877143]
- **Literature vocabulary:** body weight, BMI, body mass index, fat mass, muscle mass, body cell mass, lean body mass, resting energy expenditure, appetite, eating habits, Third Lumbar Skeletal Muscle Index (L3-SMI), frailty, dietary intake, gastrointestinal symptoms
- **Evidence:** NCT07606235 (Transcutaneous Superior Laryngeal Nerve Stimulation to Upregulate Swal, 2026); NCT06877143 (Hypercaloric PEG Nutrition in ALS to Sustain Energy Homeostasis, 2025); NCT06765499 (The Study Evaluating the Improvement of Nutritional Status and Frailty, 2025); NCT06608004 (Influence of Olfacto-gustatory Sensoriality on the Nutritional Status , 2026) +2 more


## Deprioritize — low on both axes

### Psychological Distress (Depression and Anxiety)  (`psychological_distress`)
- **Clinical importance 3/5** — Depression and anxiety measures (HADS, MADRS, PHQ-9) appear as secondary endpoints in several ALS trials (NCT06968468, NCT07082192, NCT06656702). HAMD-17 is included in the Phase 2 CB03-154 trial (NCT07082192). However, psychological distress is not a primary disease progression marker [NCT07082192]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring psychological distress in ALS is evidenced in the corpus. All measures (HADS, MADRS, PHQ-9, GAD-7, C-SSRS) are traditional questionnaire-based PROs without demonstrated wearable or sensor-based digital alternatives [NCT06968468]
- **Literature vocabulary:** Hospital Anxiety and Depression Scale (HADS), Montgomery-Asberg Depression Rating Scale (MADRS), ALS Depression Inventory, Patient Health Questionnaire-9 (PHQ-9), Generalized Anxiety Disorder-7 (GAD-7), State Trait Inventory for Cognitive and Somatic Anxiety (STICSA), Beck Hopelessness Scale, Hamilton Depression Rating Scale (HAMD-17), demoralization, Columbia-Suicide Severity Rating Scale
- **Evidence:** NCT06656702 (Effects of Psilocybin in Patients With Amyotrophic Lateral Sclerosis, 2025); NCT07473765 (Virtual Reality for Anxiety Management in Persons With Amyotrophic Lat, 2026); NCT06968468 (Resiliency Intervention for Patients With ALS and Their Care-Partners, 2026); NCT07082192 (A Study to Evaluate the Efficacy and Safety of Different Doses of CB03, 2025) +5 more

### Fatigue  (`fatigue`)
- **Clinical importance 3/5** — Fatigue Severity Scale appears as a secondary outcome in rehabilitation (NCT06881979) and EMS trials (NCT07478172). Correlation with SVC is explored (NCT06841341). Impact of fatigue on quality of life is assessed (NCT07178574). However, fatigue remains a supporting symptom measure rather than a core disease progression endpoint [NCT06881979]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring fatigue in ALS is evidenced in the corpus. All fatigue assessments use the Fatigue Severity Scale or similar self-report questionnaires without any demonstrated sensor-based digital measurement approach [NCT06881979]
- **Literature vocabulary:** Fatigue Severity Scale, perceived fatigue, impact of fatigue on quality of life, fatigue
- **Evidence:** NCT06881979 (High-Tech Rehabilitation Pathway for Chronic Adult Neuromuscular Disea, 2025); NCT06719947 (HD-tDCS in Amyotrophic Lateral Sclerosis: A Multicenter Randomized Con, 2025); NCT07178574 (Polish Version Dyspnea in Amyotrophic Lateral Sclerosis, 2025); NCT07478172 (Effects of Whole-body Electrical Muscle Stimulation Exercise on Adults, 2026) +1 more

### Pain  (`pain`)
- **Clinical importance 2/5** — Pain measures appear in only a few trials: NRS for facial pain (NCT07187388), VAS (NCT02478450), impact of pain on daily life (NCT07478172), and NPS for safety monitoring (NCT07093268). Pain is not used as a primary efficacy endpoint and is peripheral to the core motor neuron degeneration process [NCT07187388]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring pain in ALS is evidenced in the corpus. All pain assessments use traditional rating scales (NRS, VAS, NPS) without any demonstrated wearable or sensor-based digital measurement approach [NCT07187388]
- **Literature vocabulary:** Numerical Rating Scale for Pain, Visual Analog Scale (VAS), Neuropathic Pain Scale (NPS), facial pain, severity of pain and impact of pain on daily life
- **Evidence:** NCT07187388 (Investigating the Impact of Electrical Stimulation on Facial Pain, Jaw, 2026); NCT02478450 (Study to Investigate the Safety of the Transplantation (by Injection) , 2026); NCT07093268 (Safety of Intrathecal Riluzole in Patients With Amyotrophic Lateral Sc, 2025); NCT07478172 (Effects of Whole-body Electrical Muscle Stimulation Exercise on Adults, 2026)

### Muscle Cramps  (`muscle_cramps`)
- **Clinical importance 2/5** — Muscle cramps are specifically targeted in only one trial (NCT06527222 evaluating ranolazine) with frequency, severity, and QoL impact as outcomes. While distressing to patients, cramps are a peripheral symptom not central to disease progression measurement or regulatory endpoints [NCT06527222]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring muscle cramps in ALS is evidenced in the corpus. The single trial measuring cramps (NCT06527222) uses patient-reported frequency and severity scales without any sensor-based digital measurement approach [NCT06527222]
- **Literature vocabulary:** muscle cramp frequency, muscle cramp severity, muscle cramps impact on quality of life
- **Evidence:** NCT06527222 (A Study of Ranolazine in ALS, 2025)

### Caregiver Burden  (`caregiver_burden`)
- **Clinical importance 3/5** — Caregiver burden measures appear as secondary endpoints in a limited number of trials: BSFC (NCT07454733), CBI (NCT07006571), Preparedness for Caregiving Scale (NCT07454733), and caregiver burden in BCI trials (NCT06829212). While important for supportive care, it is not a direct disease progression measure [NCT07454733]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring caregiver burden is evidenced in the corpus. All caregiver burden assessments use questionnaire-based instruments (BSFC, CBI, DCI) without any demonstrated sensor-based or digital health technology approach [NCT07454733]
- **Literature vocabulary:** Burden Scale for Family Caregivers (BSFC), Caregiver Burden Inventory (CBI), Preparedness for Caregiving Scale, Dyadic Coping Inventory, caregiver burden, multidimensional social support
- **Evidence:** NCT07454733 (Do Video Recordings of Multidisciplinary Clinics Improve Quality of Li, 2026); NCT07006571 (At-home Treatment With Cortico-spinal tDCS for Amyotrophic Lateral Scl, 2025); NCT06968468 (Resiliency Intervention for Patients With ALS and Their Care-Partners, 2026); NCT06829212 (Research on Wireless Brain Implant System for General Control of Exter, 2025)

### Spasticity and Upper Motor Neuron Signs  (`spasticity`)
- **Clinical importance 3/5** — Spasticity is measured via Modified Ashworth Scale (NCT07636538, NCT02478450) and Penn UMN Score (NCT07067229, NCT07312240). While clinically relevant for phenotyping and symptom management, it is a secondary feature that supplements rather than drives primary efficacy endpoints [NCT07636538]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring spasticity in ALS is evidenced in the corpus. All spasticity assessments use clinical rating scales (MAS, PUMNS) requiring manual examination without any demonstrated wearable or sensor-based digital measurement approach [NCT02478450]
- **Literature vocabulary:** Modified Ashworth Scale (MAS), Ashworth Spasticity Scale, Penn Upper Motor Neuron Score (PUMNS), Penn UMN Score
- **Evidence:** NCT07636538 (Auto-calibrating System for Upper Limb Disability Assessment, Neurolog, 2026); NCT02478450 (Study to Investigate the Safety of the Transplantation (by Injection) , 2026); NCT07312240 (LONgitudinal and Integrated Evaluation of Biomarkers in reLation to ph, 2025); NCT07067229 (Non-invasive Brain Stimulation and Exercise Intervention for Patients , 2025)

### Dyspnea  (`dyspnea`)
- **Clinical importance 3/5** — Dyspnea is assessed via Modified Borg Dyspnea Scale in a few trials (NCT06719947, NCT07178574) and as global rate of change of breathing (NCT07071935). While clinically meaningful as a patient-reported respiratory symptom, it serves as a secondary measure subordinate to objective respiratory function [NCT07071935]
- **Digital measurability 1/5** — No DHT/sensor precedent for measuring dyspnea in ALS is evidenced in the corpus. All dyspnea assessments use subjective rating scales (Modified Borg, Borg RPE) without any demonstrated wearable or sensor-based digital measurement [NCT04089696]
- **Literature vocabulary:** Modified Borg Dyspnea Scale, dyspnea, global rate of change of breathing, Borg RPE
- **Evidence:** NCT06719947 (HD-tDCS in Amyotrophic Lateral Sclerosis: A Multicenter Randomized Con, 2025); NCT07178574 (Polish Version Dyspnea in Amyotrophic Lateral Sclerosis, 2025); NCT07071935 (A Clinical Trial of Early Ventilation in Amyotrophic Lateral Sclerosis, 2026); NCT04089696 (Validation of the "ExSpiron©" in Patients With ALS, 2025)

## Draft criteria.py stubs (recommended + consider COIs)

```python
# Paste accepted entries into criteria.py's CRITERIA dict.
# Every entry is DRAFT — review inclusion lines and positive_signals first.

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) (OVERRIDES an existing authored entry — review carefully!) ──
    'respiratory_function': EligibilityCriteria(
        coi='respiratory_function',
        coi_description=(
            'Respiratory failure from progressive diaphragm and accessory muscle weakness is the primary cause of death in ALS; respiratory measures serve as key efficacy and survival surrogate endpoints.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses respiratory function (slow vital capacity (SVC), forced vital capacity (FVC), percent predicted FVC, maximal inspiratory pressure (MIP), maximal expiratory pressure (MEP), cough peak flow (CPF)) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['slow vital capacity (SVC)', 'forced vital capacity (FVC)', 'percent predicted FVC', 'maximal inspiratory pressure (MIP)', 'maximal expiratory pressure (MEP)', 'cough peak flow (CPF)', 'lung insufflation capacity (LIC)', 'maximum insufflation capacity (MIC)', 'sniff nasal inspiratory pressure (SNIP)', 'transcutaneous carbon dioxide (TcCO2)', 'oxygen saturation', 'spirometry', 'respiratory function', 'peak inspiratory flow rate (PIFR)', 'respiratory insufficiency', 'diaphragmatic excursion', 'diaphragmatic thickening', 'oxygenation index', 'lung volumes', 'arterial blood gas (PaO2, PaCO2)'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'communication_ability': EligibilityCriteria(
        coi='communication_ability',
        coi_description=(
            'Progressive loss of speech and limb motor control leads to locked-in states; brain-computer interfaces and assistive technologies aim to restore communication throughput as a functional endpoint.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses communication ability (assistive technology / bci) (words per minute (WPM), phrases per minute, information transfer rate (ITR), BCI control, cursor task performance, system usability) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['words per minute (WPM)', 'phrases per minute', 'information transfer rate (ITR)', 'BCI control', 'cursor task performance', 'system usability', 'assistive technology', 'eye tracker', 'speech BCI', 'neural decoding'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'overall_functional_status': EligibilityCriteria(
        coi='overall_functional_status',
        coi_description=(
            'ALS causes progressive loss of function across multiple domains; composite functional scales are the most widely used primary endpoints to capture disease progression holistically.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses overall functional status (ALSFRS-R, ALS Functional Rating Scale-Revised, ALSFRS-R total score, ALSFRS-R sub-domain scores, Rasch Overall ALS Disability Scale (ROADS), functional decline) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['ALSFRS-R', 'ALS Functional Rating Scale-Revised', 'ALSFRS-R total score', 'ALSFRS-R sub-domain scores', 'Rasch Overall ALS Disability Scale (ROADS)', 'functional decline', 'disease progression', "King's Clinical Severity Staging", 'functional status', 'Combined Assessment of Function and Survival (CAFS)', 'Norris Scale Score'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'speech_function': EligibilityCriteria(
        coi='speech_function',
        coi_description=(
            'Bulbar motor neuron degeneration impairs speech production, making quantitative speech measures sensitive indicators of disease progression in bulbar-onset and generalized ALS.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses speech function (speaking rate, oral speaking rate, intelligibility, maximum phonation time, listener effort, formant frequencies) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['speaking rate', 'oral speaking rate', 'intelligibility', 'maximum phonation time', 'listener effort', 'formant frequencies', 'duration of speech sounds', 'syntactic properties', 'pragmatic properties', 'quantitative speech assessment', 'digital speech markers', 'bulbar subdomain of ALSFRS-R', 'communication'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'muscle_strength': EligibilityCriteria(
        coi='muscle_strength',
        coi_description=(
            'Progressive motor neuron loss causes muscle weakness, the cardinal feature of ALS; quantitative strength measures capture the rate of lower motor neuron degeneration across body regions.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses muscle strength (handheld dynamometry (HHD), grip strength, pinch strength, finger tip pinch, palmar pinch, key pinch) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['handheld dynamometry (HHD)', 'grip strength', 'pinch strength', 'finger tip pinch', 'palmar pinch', 'key pinch', 'MRC scale', 'manual muscle test (MMT)', 'Accurate Test of Limb Isometric Strength (ATLIS)', 'HHD megascore', 'muscle strength'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'physical_mobility': EligibilityCriteria(
        coi='physical_mobility',
        coi_description=(
            'Lower extremity weakness and spasticity progressively impair walking, balance, and mobility, representing major milestones of disability in ALS.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses physical mobility and gait (walking capacity, 2-Minute Walking Test, Time Up and Go Test, gait, postural gait disorders, climbing stairs) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['walking capacity', '2-Minute Walking Test', 'Time Up and Go Test', 'gait', 'postural gait disorders', 'climbing stairs', 'timed functional tests', 'broad jump', 'multidirectional lunge test', 'walking scale', 'trunk control'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'upper_limb_function': EligibilityCriteria(
        coi='upper_limb_function',
        coi_description=(
            'Loss of hand dexterity and arm function compromises self-care, eating, writing, and device use; integrated upper-limb measures capture coordination beyond raw strength.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses upper limb function and dexterity (9 Hole Peg test, hand function, Quick Disabilities of Arm Shoulder and Hand (QuickDASH), Fugl-Meyer Assessment, ABILHAND Scale, Action Research Arm Test (ARAT)) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['9 Hole Peg test', 'hand function', 'Quick Disabilities of Arm Shoulder and Hand (QuickDASH)', 'Fugl-Meyer Assessment', 'ABILHAND Scale', 'Action Research Arm Test (ARAT)', 'fine motor control', 'functional eating status'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'sleep_quality': EligibilityCriteria(
        coi='sleep_quality',
        coi_description=(
            'Nocturnal hypoventilation, disrupted sleep architecture, and daytime somnolence are early features of respiratory decline in ALS, impacting quality of life and indicating need for ventilatory support.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses sleep quality (Epworth Sleepiness Scale (ESS), Karolinska Sleepiness Scale (KSS), quality of sleep, daytime sleepiness, nocturnal pulse oximetry, sleep quality) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['Epworth Sleepiness Scale (ESS)', 'Karolinska Sleepiness Scale (KSS)', 'quality of sleep', 'daytime sleepiness', 'nocturnal pulse oximetry', 'sleep quality', 'hypoxic burden', 'T90', 'pulse rate variability'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'muscle_composition': EligibilityCriteria(
        coi='muscle_composition',
        coi_description=(
            'Progressive denervation causes detectable changes in muscle impedance, volume, and architecture; imaging and bioimpedance measures provide objective, quantitative biomarkers of disease burden.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses muscle composition and integrity (Electrical Impedance Myography (EIM), muscle volume, thigh muscle volume, diaphragmatic excursion, diaphragmatic thickening, diaphragm diameter) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['Electrical Impedance Myography (EIM)', 'muscle volume', 'thigh muscle volume', 'diaphragmatic excursion', 'diaphragmatic thickening', 'diaphragm diameter', 'phrenic nerve cross-sectional area', 'muscle ultrasound'],
        negative_signals=[],
    ),

    # ── DRAFT (auto-generated by ta_landscape, NOT human-reviewed) ──
    'neurophysiological_integrity': EligibilityCriteria(
        coi='neurophysiological_integrity',
        coi_description=(
            'Electrophysiological measures of motor neuron and axonal function (CMAP, MUNE, cortical excitability) provide objective quantification of upper and lower motor neuron degeneration and therapeutic target engagement.'
        ),
        inclusion=GLOBAL_INCLUSION + [
            'Published, registered, or preprinted from 2016 onward (rationale: modern sensor/wearable era).',
            'Study reports at least one wearable, handheld, ambient sensor, or digital endpoint in the design.',
            'Outcome measure assesses neurophysiological integrity (compound muscle action potential (CMAP), motor unit number estimation (MUNE), motor unit number index (MUNIX), motor evoked potential (MEP), cortical silent period (CSP), short intracortical inhibition (SICI)) via a wearable, handheld, ambient sensor, or other digital endpoint.'
        ],
        exclusion=[],  # DRAFT: relies on GLOBAL_EXCLUSION; tighten before trusting
        positive_signals=['compound muscle action potential (CMAP)', 'motor unit number estimation (MUNE)', 'motor unit number index (MUNIX)', 'motor evoked potential (MEP)', 'cortical silent period (CSP)', 'short intracortical inhibition (SICI)', 'intra-cortical facilitation (ICF)', 'resting motor threshold', 'threshold tracking nerve conduction', 'central motor conduction time (CMCT)', 'Neurophysiological Index (NI)', 'motor unit firing rates', 'denervation score (EMG)', 'electromyographic activity'],
        negative_signals=[],
    ),

```

## Run notes

- TA-first V1: no recall_patterns pass at the TA level. TA-level queries are broad, so this corpus is noisier than a COI-first pull; PI-branded and methods-only constructs may be under-surfaced. The ClinicalTrials.gov outcome-measures lane is the high-precision, construct-explicit backbone.
- Emitted criteria stubs are DRAFT: positive_signals are vocabulary the model observed in-corpus, not the hand-tuned indication-specific vocabulary in criteria.py's authored entries. Human-review each stub before an unattended coi_first run trusts it.
- V1 stops at the reviewed shortlist. Running coi_first on the accepted COIs is a separate, human-gated step.