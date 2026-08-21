# An Integrated Steady-State Biology Framework for Non-Pharmacological Longevity Intervention: From Classical-Text and Genome Fusion to Closed-Loop Validation

**Authors**: Li Xing

**Affiliation**: HealthLens, Independent Research Project, Hangzhou, China

**Corresponding author**: Li Xing, email: corresponding@healthlens.cc

**Manuscript type**: Hypothesis / Theoretical Framework

**Non-medical disclaimer**: This paper proposes a theoretical framework and a decision-support paradigm for ranking intervention priorities. It is not a clinical diagnosis or treatment protocol and does not replace physician judgement; all specific interventions must be undertaken under the guidance of qualified professionals. Human evidence cited herein is used to validate the framework and does not constitute individualized medical advice.

---

## Abstract

**Background**: Traditional medicine (exemplified by Chinese medicine) has accumulated millennia of experiential knowledge on homeostatic regulation, whereas modern aging biology has identified measurable homeostatic pathways (autophagy, mitochondrial biogenesis, senescent-cell clearance, circadian rhythm). The two knowledge systems have long run in parallel, lacking a computable, verifiable unifying framework.

**Objective**: We propose the Integrated Steady-State Biology Framework (ISSBF), which axiomatically maps classical constructs (qi, blood, zang-fu, yin-yang, zheng-xie, shen) onto eight measurable steady-state biology axes, and establishes a fusion rule of classical candidate intersected with individual genetic weakness pathway together with a Sense-Infer-Intervene-Verify (SIIV) closed loop.

**Methods**: (1) Six paradigm axioms constrain the framework; (2) an eight-axis mapping is constructed (A: gasification/autophagy, B: qi-blood/mitochondria, C: luo-network/stasis-clearance, D: yin-yang/circadian, E: zang-fu/neuroendocrine, F: zheng-xie/inflammation, G: shen/affect, H: congenital/epi-clock); (3) a real-world case evidence base (n=29; L1=8, L2=9, L3=12) anchors the framework empirically; (4) wearable/CGM/BCI data interfaces drive the loop; (5) an in-silico computational validation (22 synthetic profiles) quantifies reproducibility, specificity, and coverage.

**Results**: The framework anchors each axis to modern mechanisms and human evidence (e.g., 4-week fasting raised LAMP2 4.2-fold and LC3B 1.9-fold; dasatinib plus quercetin reduced senescent cells by 35% in a first-in-human pilot and improved gait speed in a 240-person Phase II trial; 16:8 time-restricted eating reduced hepatic fat by 25.8% in a 333-person randomized controlled trial). Computational validation showed 100% reproducibility, 100% weakness-profile coverage (90% with L1-grade evidence), zero personalized recommendations for control profiles, and 85% convergent validity with traditional-medicine domain expectations.

**Conclusion**: ISSBF provides a computable, verifiable, non-medical theoretical skeleton for integrating classical and modern medicine. It can serve as a decision-support foundation for personalized non-pharmacological intervention. The framework as a whole requires prospective validation.

**Keywords**: integrative medicine; homeostasis; autophagy; mitochondria; circadian rhythm; network medicine; systems biology; personalized non-pharmacological intervention; closed-loop validation

---

## 1. Introduction

Global aging has made healthspan extension a central medical goal. Modern aging biology has established several quantifiable, intervenable homeostatic pathways: autophagy (AMPK/mTOR), mitochondrial biogenesis (PGC-1-alpha/SIRT1), senescent-cell clearance (senolytics), the stem-cell niche, and circadian rhythm (CLOCK/BMAL1) [1,2]. In parallel, traditional medicine (especially Chinese medicine) records extensive non-pharmacological homeostatic-regulation experience -- daoyin (guided exercise), fasting, food-as-medicine, emotional regulation, and rhythmic living -- through constructs such as qi, blood, zang-fu, yin-yang, zheng-xie, and shen [3,4].

The two systems exhibit structural complementarity: traditional medicine supplies the experiential priors of when and for which constitution to regulate what, while modern biology supplies the mechanistic evidence that regulation indeed changed which measurable pathway. Yet they have long lacked a unified computable language -- classical constructs are mostly not directly measurable, and modern pathways are mostly divorced from individual-constitution context.

This paper proposes the ISSBF to: (1) axiomatically map core classical constructs onto eight measurable steady-state biology axes; (2) realize personalized weighting via a fusion rule of classical candidate intersected with individual genetic/omics weakness; (3) validate directional correctness with a real-world human evidence base; (4) achieve continuous verification through the SIIV loop and hardware interfaces. We observe three red lines: mechanisms must anchor to measurable pathways (no empty phrases such as "repair cells"), classical texts are not molecular evidence, and non-pharmacological does not mean risk-free.

---

## 2. Paradigm Axioms

The framework is constrained by six inviolable axioms:

- **A1 Homeostasis-first**: The intervention target is to maintain or restore measurable steady-state axes, not to chase an extreme value of a single metric.
- **A2 Measure-to-intervene**: Any recommended mechanism must map to a quantifiable biomarker (genetic, protein, metabolic, or wearable).
- **A3 Personalized weighting**: Recommendation strength is determined by the intersection of classical candidate and individual genetic/omics weakness; single-SNP decisions are prohibited.
- **A4 Closed-loop verification**: Inferences must be verifiable by post-intervention re-measurement (SIIV).
- **A5 Hormesis boundary**: Most effective interventions follow an inverted-U dose-response; safe ranges and contraindications must be stated.
- **A6 Fallibility of experience**: Classical experiential knowledge is treated as a falsifiable hypothesis, not endowed with molecular-level certainty.

---

## 3. Eight Steady-State Biology Axes

Each axis maps a classical construct onto a modern measurable pathway and anchors evidence:

| Axis | Classical construct | Modern pathway | Representative evidence |
|---|---|---|---|
| **A: Gasification** | qi transformation / transport | AMPK/mTOR autophagy | 4-week fasting: LAMP2 increased 4.2-fold, LC3B 1.9-fold [1] |
| **B: Qi-blood-Mitochondria** | qi-blood / tonify-qi | PGC-1-alpha/SIRT1 biogenesis | Single HIIT: nuclear PGC-1-alpha within 3 h [15] |
| **C: Luo-network-Stasis clearance** | luo-network / phlegm-stasis | Senolytics (p16/p21, SASP) | D+Q: p16+p21 cells reduced 35% [5]; AFFIRM Phase II RCT (n=240): gait speed and grip strength improved [18] |
| **D: Yin-yang-Circadian** | yin-yang / regular routine | CLOCK/BMAL1, melatonin | 16:8 TRE: hepatic fat reduced 25.8% (n=333) [9]; early TRE优于late TRE for insulin sensitivity [8] |
| **E: Zang-fu-Neuroendocrine** | zang-fu / kidney life-gate | HPA axis, cortisol | Meditation/breathing: HRV increased, cortisol decreased [12] |
| **F: Zheng-xie-Inflammation** | zheng-xie / damp-heat | Low-grade inflammation + CD4+T-cell immunosenescence | Fasting: IL-6 and TNF-alpha decreased [1]; CD4-Eomes+ cells modulate tissue senescence (Nature Aging 2025) |
| **G: Shen-Affect** | shen / affect | HRV (RMSSD), EEG | Meditation: EEG alpha increased, HRV increased [12] |
| **H: Congenital-Kidney-essence** | congenital / kidney-essence | Epigenetic clock + CD4 CTL expansion (longevity) | FMD 3 cycles: biological age reduced 2.5 years [3]; CD4 CTL expansion in centenarians (Cell Reports 2026) |

**Mapping philosophy**: Classical constructs are not proven equal to modern pathways; they are projected as experiential priors onto axes, then upgraded or vetoed by modern mechanisms and human evidence.

---

## 4. Fusion Methodology

Given a user's genetic/omics panel (pathway-level aggregated scores; SNP-level conclusions prohibited) and classical-candidate hits:

1. Mechanism mapping: classical candidate mapped to modern pathway label.
2. Personalized weighting: retain only the intersection of classical candidate and genetic-weakness pathway (weakness defined as pathway score less than 0.5); larger intersection yields higher weight.
3. Evidence grading: each candidate tagged L1 through L4.
4. Output: seven fields (target pathway, classical source, genetic relevance, evidence level, contraindication, monitoring metric, actionable prescription).
5. Safety gate: contraindication auto-exclusion, non-medical disclaimer, high-intervention human approval gate.

**Key constraints**: A classical experience without a genetic intersection is downgraded to a general suggestion. Absence of genetic data or human evidence forces an is_demo banner. Every conclusion must trace to at least one of mechanism literature, classical original text, or user genetic evidence.

---

## 5. Evidence Base: Real-World Case Library (n=29)

We built case_evidence_db.json (machine-readable), containing 29 real human-trial or classical-experience entries. Grade distribution: **L1=8 / L2=9 / L3=12**. Representative entries:

| ID | Intervention | Axis | Population/Design | Key effect | Grade | DOI |
|---|---|---|---|---|---|---|
| CASE-001 | 4-week fasting | A/F | 51 adults | LAMP2 increased 4.2-fold, LC3B 1.9-fold | L1 | 10.1016/j.clnesp.2024.11.002 |
| CASE-006 | D+Q AFFIRM trial | C/H | 240 adults aged 65-85, Phase II RCT | p16/SASP reduced; gait speed and grip strength improved | L1 | 10.1038/s41591-026-04102-8 |
| CASE-007 | Early vs late TRE | D | 197 adults, 12-week RCT | All TRE groups reduced VAT; early TRE优于late TRE for HOMA-IR (P less than 0.05) | L1 | 10.1038/s41591-024-03375-y |
| CASE-008 | 16:8 TRE | D/F | 333 MASLD adults, 16-week RCT | Hepatic fat reduced 25.8% (TRE equivalent to calorie restriction) | L1 | 10.1016/j.jhep.2025.06.005 |
| CASE-022 | Evening blue-light avoidance | D | 12 adults, crossover | Melatonin suppressed greater than 55% | L2 | 10.1073/pnas.1418490112 |
| CASE-024 | Exercise-induced exosomes | B/I | Human exercise studies | Circulating exosomes increased 2-3-fold | L2 | 10.1186/s12967-026-08038-9 |
| CASE-014-021 | Food-as-medicine | A-H | Classical experience | Nature-flavor axis projection | L3 | Shi Liao Ben Cao (Tang dynasty) |

---

## 6. Computational Validation of the Fusion Engine

To demonstrate that the fusion rule is a computable, auditable method, we conducted an in-silico validation with 22 synthetic UserProfiles (20 weakness profiles plus 2 controls) and measured reproducibility, specificity, coverage, and convergence validity. All inputs are synthetic pathway scores; no real human genomic data is involved.

**Table 1. Fusion-engine computational validation metrics**

| Metric | Result |
|---|---|
| Reproducibility (dual-run agreement) | 100% (0/22 disagreement) |
| Mean personalized recommendations per weakness profile | 5.95 |
| Mean personalized recommendations per control profile | 0.0 |
| Weakness-profile coverage (at least 1 personalized) | 100% |
| Weakness-profile L1-coverage | 90% |
| Convergent validity vs. traditional-medicine domain expectations | 85% |
| Contraindication exclusion (weak F+D plus pregnancy) | 1 entry (CASE-017) |

**Axis activation distribution** (hits per weakness profile): A=4, B=5, C=4, D=5, E=3, F=5, G=4, H=3 -- all eight axes were activated, with no axis collapse.

**Evidence-grade distribution** (personalized recommendation pool, n=119): L1=47 (39%), L2=46 (39%), L3=26 (22%) -- approximately 80% supported by human or RCT-level (L1 plus L2) evidence.

**Specificity**: Control profiles produced zero personalized recommendations, proving the intersection logic responds to real input rather than emitting indiscriminately.

**Limitation**: This validation tests the engine logic itself (reproducibility, specificity, coverage, validity) and does not represent the human efficacy of the recommended interventions; intervention efficacy must be assessed by independent prospective studies.

---

## 7. Closed-Loop Verification (SIIV)

```
Sense   <- wearable HRV/sleep, CGM postprandial drift, BCI/EEG
   |
Infer   <- eight-axis homeostasis scoring + genetic-weakness fusion
   |
Intervene <- non-pharmacological suggestions (daoyin, fasting, food-as-medicine, rhythm, affect)
   |
Verify  <- re-measure axis markers, update personalized weights
```

This loop turns the theory from a text hypothesis into a measurable, falsifiable living system.

---

## 8. Novelty and Dialogue with Existing Paradigms

- **vs Network Medicine** [6]: We add the non-molecular node of classical experiential prior, projecting it as the initial weight of an axis rather than inferring solely from molecular interaction networks.
- **vs Hormesis theory**: The framework writes the hormetic inverted-U into axiom A5, avoiding the more-is-better fallacy.
- **vs Systems-biology Chinese medicine** [3,4]: ISSBF maps luo/phlegm-stasis to axis C (senolytics) and adds a quantifiable closed-loop verification layer, descending from formula-level to individual-executable micro-interventions.
- **vs Chronobiology**: Axis D anchors regular routine and light avoidance to the measurable melatonin-SCN loop.

**Novelty statement**: The core increments are (1) a computable mapping from classical constructs to eight axes, (2) an intersection fusion of classical candidate and genetic weakness, (3) the SIIV closed loop, and (4) a unified definition of hardware data interfaces. The framework offers a meta-framework for integration and prioritization; it does not claim any mechanism beyond known biology.

---

## 9. Limitations and Future Validation

1. The framework as a whole is not yet frontally validated by a single RCT. Each axis has evidence, but fusion judgement outperforming experience or single omics remains to be proven.
2. Subjectivity of classical projection: nature-flavor to axis mapping needs further calibration by independent expert Delphi and quantitative text mining.
3. Low effect size at the genetic layer: consumer-chip pathway scores are probabilistic; fusion weights must be conservative.
4. Hardware data are non-medical-grade: trend-only, diagnostic use prohibited.
5. Senolytics (dasatinib plus quercetin) serve as mechanistic anchors for axis C evidence but are prescription drugs; the framework restricts personalized recommendations to non-pharmacological interventions (e.g., dietary quercetin from food sources). High-intervention pharmacological candidates require human approval gate.
6. Next steps: preprint first; publish theoretical framework; design precision fasting and circadian-rhythm RCTs to validate fusion judgement; backfill anonymized user data.

---

## 10. Conclusion

ISSBF provides a computable, verifiable, non-medical theoretical skeleton for integrating East and West, classical and modern, experience and technology. It projects classical experience onto modern measurable pathways through six axioms and eight axes, validates directional correctness with a real-world human evidence base, and achieves continuous verification through the SIIV loop and hardware interfaces. The in-silico computational validation shows that the fusion judgement is a reproducible, specific, high-coverage, and auditable method. As a decision-support framework, it can become a research foundation for personalized non-pharmacological intervention; its overall efficacy awaits prospective validation.

---

## References

[1] Bou Malhab LJ, Madkour MI, Abdelrahim DN, et al. Dawn-to-dusk intermittent fasting is associated with overexpression of autophagy genes: a prospective study on overweight and obese cohort. Clin Nutr ESPEN. 2025;65:209-217. doi:10.1016/j.clnesp.2024.11.002

[2] Li T, et al. Intermittent fasting and health outcomes: an umbrella review of systematic reviews and meta-analyses of randomised controlled trials. EClinicalMedicine. 2024.

[3] Brandhorst S, et al. Fasting-mimicking diet causes hepatic and blood markers changes indicating reduced biological age and disease risk. Nat Commun. 2024;15:1373. doi:10.1038/s41467-024-45260-9

[4] Wang YY (Wang Yongyan). Kidney-deficiency phlegm-stasis and toxin-damaged luo theory. In: Academic System of Chinese Internal Medicine. Beijing: People's Medical Publishing House.

[5] Hickson LJ, Prata LGPL, Bobart SA, et al. Senolytics decrease senescent cells in humans: preliminary report from a clinical trial of dasatinib plus quercetin in individuals with diabetic kidney disease. EBioMedicine. 2019;47:446-456. doi:10.1016/j.ebiom.2019.08.069

[6] Barabasi AL, Gulbahce N, Loscalzo J. Network medicine: a network-based approach to human disease. Nat Rev Genet. 2011;12(1):56-68.

[7] Justice JN, Nambiar AM, Tchkonia T, et al. Senolytics in idiopathic pulmonary fibrosis: results from a first-in-human, open-label, pilot study. EBioMedicine. 2019;40:554-563. doi:10.1016/j.ebiom.2018.12.052

[8] Dote-Montero M, Clavero-Jimeno A, Merchan-Ramirez E, et al. Effects of early, late and self-selected time-restricted eating on visceral adipose tissue and cardiometabolic health in participants with overweight or obesity: a randomized controlled trial. Nat Med. 2025;31:524-533. doi:10.1038/s41591-024-03375-y

[9] Oh JH, Yoon EL, Park H, et al. Efficacy and safety of time-restricted eating in metabolic dysfunction-associated steatotic liver disease: a randomized controlled trial. J Hepatol. 2025. doi:10.1016/j.jhep.2025.06.005

[10] Chang AM, Aeschbach D, Duffy JF, Czeisler CA. Evening use of light-emitting eReaders negatively affects sleep, circadian timing, and next-morning alertness. Proc Natl Acad Sci USA. 2015;112(4):1232-1237. doi:10.1073/pnas.1418490112

[11] Ma J, et al. Morning bright light exposure improves sleep efficiency and latency in disturbed sleepers: a randomized controlled trial. Sleep Med. 2020;71:62-68. doi:10.1016/j.sleep.2020.05.009

[12] Goyal M, Singh S, Sibinga EM, et al. Meditation programs for psychological stress and well-being: a systematic review and meta-analysis. JAMA Intern Med. 2014;174(3):357-368.

[13] China Academy of Information and Communications Technology. Brain-Computer Interface Technology and Application Research Report 2025.

[14] Huawei HiHealth Kit. Open data types and Extended Health Service Kit documentation.

[15] Little JP, Safdar A, Bishop D, et al. An acute bout of high-intensity interval training increases the capacity for fat oxidation during exercise in women. J Appl Physiol. 2010;109(6):1568-1574.

[16] Kirkland JL, Tchkonia T. Senolytic drugs: from discovery to translation. J Intern Med. 2020;288(5):518-536.

[17] Su Z, Chen L. Utilizing circulating microRNAs for personalized exercise programs: insights into physiological adaptations and individual responses. Biology. 2025.

[18] Kirkland JL, Tchkonia T, Musi N, et al. Senolytic drugs extend healthspan in first large human trial (AFFIRM). Nat Med. 2026. doi:10.1038/s41591-026-04102-8

[19] Yu P, et al. Exercise-induced muscle exosomes: microRNA cargo as regulators of cardiovascular remodeling and disease progression. J Nanobiotechnol. 2026. doi:10.1186/s12967-026-08038-9

[20] Wang X, Huang H, Chen J, Zhang Q. Mechanism of exercise-derived circulating exosomes as a target for sarcopenia management. Front Physiol. 2026;16:1680485.

[21] Nature Aging 2025. CD4 T cells acquire Eomesodermin to modulate cellular senescence and aging. doi:10.1038/s43587-025-00953-8

[22] Cell Reports 2026. CD4 CTLs in supercentenarians: Signs of adaptive expansion in healthy aging. doi:10.1016/j.celrep.2026.117728

---

## Ethics Statement

This study did not involve human participants, human data, or human tissue. All computational validation used synthetic pathway scores generated in silico. No institutional review board approval was required.

## Funding

This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

## Conflicts of Interest

The author declares no conflicts of interest.

## Data Availability

The case evidence database (case_evidence_db.json), computational validation metrics (engine_validation_metrics.json), and the validation script (tools/engine_validation.py) are available at the project GitHub repository. The supplementary data (HealthLens_computational_validation_supplement.csv) is included with this manuscript.

## Code Availability

The fusion engine validation script (engine_validation.py) is open-source and available at the project repository. The script is deterministic and fully auditable.

## Author Contributions

Li Xing: conceptualization, methodology, software (computational validation), writing -- original draft, writing -- review and editing.

## AI-Assistance Disclosure

AI language models were used to assist with manuscript editing and literature synthesis. All claims and data were verified by the author against primary sources.
