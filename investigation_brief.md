# EP Lab Efficiency — Investigation Brief

## Problem

The hospital's Electrophysiology (EP) Lab performs AFib ablation procedures
through a structured sequence of stages. In practice, total case time
varies from **17 to 159 minutes** across the 150-case observation window,
making lab scheduling unpredictable and capacity hard to manage. Because
lab time is fixed and demand is increasing, this variability is a
recurring operational issue.

Initial analysis suggests the variability is *not random*. A small number
of procedural drivers — ablation duration, catheter repositioning, and
case-to-case ordering — concentrate most of the differences. Yet the
existing data captures only timestamps and physician identity; it does
not capture **why** some cases run longer than others.

## Objective

Move the EP Lab from *measuring what happens* to *understanding why it
happens*, then use that understanding to drive concrete scheduling
improvements.

Specifically, this investigation will:

1. Quantify the main drivers of case-time variability across procedural
   stages, physicians, and case order.
2. Test whether patient complexity, which is currently unobserved, is the
   primary explanation for the residual unexplained variance.
3. Develop a pre-operative **Patient Complexity Score (PCS)** that lets
   schedulers estimate case difficulty *before* the procedure.
4. Use the PCS to evaluate whether complexity-aware case ordering
   improves daily throughput, without changing how physicians perform
   the procedure itself.

## Scope

| | |
|---|---|
| Dataset | 150 AFib ablation cases, January – October 2025 |
| Physicians | 3 (Dr. A, Dr. B, Dr. C) |
| Procedure days | 33 |
| Standard PVI cases | 127 |
| Cases with extra ablation targets | 22 |
| Per-case variables | 21 timestamped procedural-stage durations + physician + free-text note |

## Methodology

The investigation proceeds in four stages:

1. **Performance overview.** Descriptive statistics on each procedural
   stage and on overall case time, using **coefficient of variation
   (CV)** to compare variability fairly across stages of different scale.
2. **Driver identification.**
   - **Kruskal–Wallis** test for between-physician differences on
     case-time and stage-time distributions.
   - **Two-sample t-test** comparing standard-PVI cases to those with
     extra ablation targets.
   - **Pearson correlation** of each stage with total case time to rank
     stage-level contribution to variability.
3. **Solution design.** Construct the Patient Complexity Score from
   six pre-operative inputs intended for live deployment:
   septal anatomy, ablation scope, cardiac history, BMI, ASA score, and
   anticoagulation status. Each input contributes a 0 – 3 ordinal score
   under a weighted formula; the composite is normalised to a 1 – 10
   scale and partitioned into Low / Medium / High complexity tiers.
4. **Validation.**
   - **V1 — Predictive power.** Backwards-calculate proxies for the six
     EHR factors from the existing timestamp data and test whether the
     proxy PCS correlates with actual case time.
   - **V2 — Scheduling effect.** Compare actual case-time distributions
     when high-complexity cases are placed in position 1 vs. positions
     2 – 5 to test the warm-up hypothesis.
   - **Sensitivity analysis.** Re-run V1 under alternative weight
     schemes (equal, TSP-dominant, scope-dominant) to check robustness.

## Hypotheses entering the analysis

1. A small number of stages — ablation duration and TSP — drive most
   of the case-time variability.
2. Physician-level differences in mean case time are largely attributable
   to patient case mix rather than individual skill.
3. The first case of the day systematically runs longer due to a team
   warm-up effect.
4. Patient complexity is the largest unobserved factor; capturing it
   pre-operatively will explain a meaningful share of the residual
   variance and unlock scheduling improvements.

## Out of scope

- Re-engineering the procedure itself or training-related interventions.
- New sensor instrumentation or hardware deployment in the lab.
- Individual physician performance evaluation. Inter-physician analyses
  are used only to characterise *structural* sources of variability.

## Deliverables

- A statistical analysis of variability sources with confidence-bound
  evidence.
- A documented, weight-calibrated Patient Complexity Score.
- A validated case-ordering recommendation derived from the score.
- A staged implementation plan covering immediate (spreadsheet),
  intermediate (EHR integration), and long-term (scheduling dashboard)
  rollout.
