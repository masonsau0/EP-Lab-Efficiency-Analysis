"""
EP Lab AFib Ablation — Procedural Efficiency Analysis
=====================================================

Full statistical pipeline: descriptive stats, coefficient of variation by
phase, physician ANOVA + pairwise t-tests, driver correlations, case-sequence
and warm-up effects. Produces the five figures referenced by the notebook
and README.

Data: ep_lab_data.xlsx (150 cases, 3 physicians, Jan–Oct 2025)
"""

import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import sys, warnings
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
warnings.filterwarnings('ignore')

# ============================================================
# 1. DATA LOADING & CLEANING
# ============================================================
print("=" * 70)
print("SECTION 1: DATA LOADING & CLEANING")
print("=" * 70)

df = pd.read_excel('ep_lab_data.xlsx',
                    sheet_name='All Data', header=None, skiprows=4)

cols = ['Drop', 'Case', 'Date', 'Physician', 'PT_Prep', 'Access', 'TSP',
        'PreMap', 'ABL_Duration', 'ABL_Time', 'NumABL', 'NumApps',
        'LA_Dwell', 'Case_Time', 'Avg_Case_Time', 'Skin_Skin',
        'Avg_Skin_Skin', 'PostCare', 'Avg_Turnover', 'PT_Out_Time',
        'PT_In_Out', 'Note']
df.columns = cols
df = df.drop(columns=['Drop'])
df = df.dropna(subset=['Case'])

# Convert numeric columns
num_cols = ['PT_Prep', 'Access', 'TSP', 'PreMap', 'ABL_Duration',
            'ABL_Time', 'NumABL', 'NumApps', 'LA_Dwell', 'Case_Time',
            'Skin_Skin', 'PostCare', 'PT_In_Out']
for col in num_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Fix date typo
df['Date'] = df['Date'].replace('Juy 21', '2025-07-21')
df['Date'] = pd.to_datetime(df['Date'])

# Flag extra ablation targets
df['Has_Extra'] = df['Note'].notna() & (df['Note'] != 'Dr. D') & (df['Note'] != 'TROUBLESHOOT')
df['Is_Standard_PVI'] = ~df['Has_Extra'] & (df['Note'] != 'TROUBLESHOOT')

print(f"Total cases: {len(df)}")
print(f"Physicians: {df['Physician'].unique().tolist()}")
print(f"Cases per physician: {df['Physician'].value_counts().to_dict()}")
print(f"Missing data per column:\n{df[num_cols].isnull().sum()}")
print(f"\nNote values:\n{df['Note'].value_counts(dropna=False)}")
print(f"\nStandard PVI: {df['Is_Standard_PVI'].sum()} cases")
print(f"Extra targets: {df['Has_Extra'].sum()} cases")


# ============================================================
# 2. DESCRIPTIVE STATISTICS
# ============================================================
print("\n" + "=" * 70)
print("SECTION 2: DESCRIPTIVE STATISTICS")
print("=" * 70)

print("\n--- Overall Summary ---")
summary = df[num_cols].describe().round(2)
print(summary.to_string())

print("\n--- Key Metrics ---")
print(f"Mean Case Time: {df['Case_Time'].mean():.1f} min (σ = {df['Case_Time'].std():.1f})")
print(f"Mean Pt In-Out: {df['PT_In_Out'].mean():.1f} min (σ = {df['PT_In_Out'].std():.1f})")
print(f"Case Time Range: {df['Case_Time'].min():.0f} – {df['Case_Time'].max():.0f} min")
print(f"  → Spread ratio: {df['Case_Time'].max() / df['Case_Time'].min():.1f}x")

"""
REASONING: We use mean ± standard deviation as our primary descriptive 
statistics because:
- Mean captures central tendency for scheduling/capacity planning
- Standard deviation (σ) quantifies the spread — a key concern here since
  the hospital needs predictable case durations for scheduling
- The 9.4x spread (17 to 159 min) immediately signals high variability 
  that warrants deeper investigation
"""


# ============================================================
# 3. COEFFICIENT OF VARIATION (CV) BY STEP
# ============================================================
print("\n" + "=" * 70)
print("SECTION 3: COEFFICIENT OF VARIATION BY PROCEDURE STEP")
print("=" * 70)

step_cols = ['PT_Prep', 'Access', 'TSP', 'PreMap', 'ABL_Duration', 'PostCare']
step_labels = ['PT Prep', 'Access', 'TSP', 'Pre-Map', 'ABL Duration', 'Post-Care']

print("\n--- CV Analysis ---")
cv_data = []
for col, label in zip(step_cols, step_labels):
    mean = df[col].mean()
    std = df[col].std()
    cv = (std / mean) * 100
    cv_data.append({'Step': label, 'Mean': mean, 'Std': std, 'CV': cv})
    print(f"{label:15s}: Mean = {mean:6.1f} min, σ = {std:5.1f}, CV = {cv:6.1f}%")

cv_df = pd.DataFrame(cv_data)

"""
REASONING — Why Coefficient of Variation (CV)?

CV = (standard deviation / mean) × 100%

We use CV instead of raw standard deviation because:
- CV normalizes variability relative to the mean, allowing fair comparison
  across steps with very different average durations
- Example: Access has σ=2.2 min and mean=5.4 min → CV=41%
           ABL Duration has σ=9.3 min and mean=24.0 min → CV=39%
  Raw σ would say ABL Duration is "more variable" (9.3 > 2.2), but CV shows
  they have similar RELATIVE variability (~40%). Meanwhile TSP (CV=89%) and
  Pre-Map (CV=196%) are genuinely more unpredictable.

KEY FINDINGS:
- Pre-Map (CV=196%) and TSP (CV=89%) are the most variable steps
  → These are patient-anatomy-dependent — the biggest unpredictable time sinks
  → This is WHY we need patient complexity data (currently unobserved)
- Post-Care (CV=25%) and PT Prep (CV=28%) are the most consistent
  → Protocol-driven, less patient-specific → good candidates for standardization
"""

# Generate CV chart
fig, ax = plt.subplots(figsize=(8, 5))
colors = ['#FF6B6B' if cv > 80 else '#FFE66D' if cv > 35 else '#4ECDC4'
          for cv in cv_df['CV']]
bars = ax.bar(cv_df['Step'], cv_df['CV'], color=colors, edgecolor='white', linewidth=0.5)
ax.set_ylabel('CV (%)', fontsize=12)
ax.set_title('Coefficient of Variation by Procedure Step', fontsize=14, fontweight='bold')
for bar, cv in zip(bars, cv_df['CV']):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
            f'{cv:.0f}%', ha='center', fontsize=10, fontweight='bold')
ax.set_facecolor('#0F1117')
fig.patch.set_facecolor('#0F1117')
ax.tick_params(colors='white')
ax.yaxis.label.set_color('white')
ax.title.set_color('white')
ax.spines['bottom'].set_color('#2A2D3A')
ax.spines['left'].set_color('#2A2D3A')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig('cv_by_step.png', dpi=150, bbox_inches='tight')
plt.close()
print("\n[Chart saved: cv_by_step.png]")


# ============================================================
# 4. PHYSICIAN COMPARISON — ANOVA & PAIRWISE T-TESTS
# ============================================================
print("\n" + "=" * 70)
print("SECTION 4: PHYSICIAN COMPARISON (ANOVA & T-TESTS)")
print("=" * 70)

print("\n--- Per-Physician Summary ---")
for doc in ['Dr. A', 'Dr. B', 'Dr. C']:
    sub = df[df['Physician'] == doc]
    n = len(sub)
    ct_mean = sub['Case_Time'].mean()
    ct_std = sub['Case_Time'].std()
    pio_mean = sub['PT_In_Out'].mean()
    pio_std = sub['PT_In_Out'].std()
    tsp_mean = sub['TSP'].mean()
    tsp_std = sub['TSP'].std()
    abl_mean = sub['NumABL'].mean()
    print(f"\n{doc} (n={n}):")
    print(f"  Case Time:  {ct_mean:.1f} ± {ct_std:.1f} min")
    print(f"  Pt In-Out:  {pio_mean:.1f} ± {pio_std:.1f} min")
    print(f"  TSP:        {tsp_mean:.1f} ± {tsp_std:.1f} min")
    print(f"  # ABL Sites: {abl_mean:.1f}")

# One-way ANOVA
print("\n--- One-Way ANOVA ---")
groups_ct = [df[df['Physician'] == d]['Case_Time'].dropna() for d in ['Dr. A', 'Dr. B', 'Dr. C']]
f_ct, p_ct = stats.f_oneway(*groups_ct)
print(f"Case Time:  F = {f_ct:.3f}, p = {p_ct:.6f} {'***' if p_ct < 0.001 else '**' if p_ct < 0.01 else '*' if p_ct < 0.05 else 'n.s.'}")

groups_pio = [df[df['Physician'] == d]['PT_In_Out'].dropna() for d in ['Dr. A', 'Dr. B', 'Dr. C']]
f_pio, p_pio = stats.f_oneway(*groups_pio)
print(f"Pt In-Out:  F = {f_pio:.3f}, p = {p_pio:.6f} {'***' if p_pio < 0.001 else '**' if p_pio < 0.01 else '*' if p_pio < 0.05 else 'n.s.'}")

"""
REASONING — Why One-Way ANOVA?

ANOVA tests whether the means of 3+ groups differ significantly.
- H₀ (null hypothesis): All three physicians have the same mean Case Time
- H₁ (alternative): At least one physician's mean differs

The F-statistic measures the ratio of between-group variance to within-group variance.
- F = 16.22 means the between-physician variance is 16.22× larger than the 
  within-physician variance
- p < 0.0001 means there is less than a 0.01% chance of observing this large
  an F-statistic if the null hypothesis were true
- *** indicates significance at p < 0.001 (very strong evidence)

We use ANOVA rather than multiple t-tests because:
- Running 3 separate t-tests inflates the Type I error rate (false positives)
- ANOVA controls for this by testing all groups simultaneously
- We THEN follow up with pairwise t-tests to identify WHICH pairs differ
"""

# Pairwise t-tests
print("\n--- Pairwise T-Tests (Case Time) ---")
pairs = [('Dr. A', 'Dr. B'), ('Dr. A', 'Dr. C'), ('Dr. B', 'Dr. C')]
for d1, d2 in pairs:
    g1 = df[df['Physician'] == d1]['Case_Time'].dropna()
    g2 = df[df['Physician'] == d2]['Case_Time'].dropna()
    t, p = stats.ttest_ind(g1, g2)
    sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else 'n.s.'
    print(f"  {d1} vs {d2}: t = {t:.3f}, p = {p:.4f} {sig}")

"""
REASONING — T-Test Interpretation:

- t-statistic measures how many standard errors apart the two group means are
  - t = -5.63 (Dr. A vs Dr. B): means are 5.63 standard errors apart → very different
  - t = -2.35 (Dr. A vs Dr. C): means are 2.35 standard errors apart → moderately different
  - t = 1.62 (Dr. B vs Dr. C): means are only 1.62 standard errors apart → not significantly different

- p-value is the probability of seeing this difference (or larger) by chance alone
  - p < 0.0001: less than 0.01% chance → extremely strong evidence of real difference
  - p = 0.021: 2.1% chance → significant at α=0.05 level
  - p = 0.109: 10.9% chance → NOT significant (we can't rule out chance)

CRITICAL CAVEAT:
Dr. B handles most complex cases (mean 22.8 ABL sites vs. 20.0 for Dr. A).
Without patient complexity data, we CANNOT separate case difficulty from 
physician effect. This confounding is why we need the Patient Complexity Score.
"""


# ============================================================
# 5. STANDARD PVI vs. EXTRA TARGETS (Two-Sample T-Test)
# ============================================================
print("\n" + "=" * 70)
print("SECTION 5: STANDARD PVI vs. EXTRA ABLATION TARGETS")
print("=" * 70)

std_pvi = df[df['Is_Standard_PVI']]
extra = df[df['Has_Extra']]

print(f"\nStandard PVI (n={len(std_pvi)}):")
print(f"  Mean Case Time: {std_pvi['Case_Time'].mean():.1f} min")
print(f"  Mean Pt In-Out: {std_pvi['PT_In_Out'].mean():.1f} min")

print(f"\nExtra Targets (n={len(extra)}):")
print(f"  Mean Case Time: {extra['Case_Time'].mean():.1f} min")
print(f"  Mean Pt In-Out: {extra['PT_In_Out'].mean():.1f} min")

# T-tests
t_ct, p_ct = stats.ttest_ind(std_pvi['Case_Time'].dropna(), extra['Case_Time'].dropna())
t_pio, p_pio = stats.ttest_ind(std_pvi['PT_In_Out'].dropna(), extra['PT_In_Out'].dropna())

diff_ct = extra['Case_Time'].mean() - std_pvi['Case_Time'].mean()
diff_pio = extra['PT_In_Out'].mean() - std_pvi['PT_In_Out'].mean()

print(f"\n--- Two-Sample T-Tests ---")
print(f"Case Time:  Δ = +{diff_ct:.1f} min, t = {t_ct:.3f}, p = {p_ct:.4f} {'***' if p_ct < 0.001 else '**' if p_ct < 0.01 else '*' if p_ct < 0.05 else 'n.s.'}")
print(f"Pt In-Out:  Δ = +{diff_pio:.1f} min, t = {t_pio:.3f}, p = {p_pio:.4f} {'***' if p_pio < 0.001 else '**' if p_pio < 0.01 else '*' if p_pio < 0.05 else 'n.s.'}")

"""
REASONING — Why Two-Sample T-Test?

We compare two independent groups (Standard PVI vs. Extra Targets) to test 
whether the additional ablation targets significantly increase procedure time.

- H₀: Mean Case Time is the same for both groups
- H₁: Mean Case Time differs between groups

Results:
- Case Time: Δ = +14.2 min, p = 0.0003
  → There is only a 0.03% chance that this 14.2-minute difference is due to 
    random chance alone. This is STRONG evidence that extra targets genuinely
    increase procedure time.
- Pt In-Out: Δ = +10.5 min, p = 0.035
  → 3.5% chance → significant at α=0.05

This is the STRONGEST finding in the dataset: case mix (extra targets) is the 
#1 driver of variability. The Note column is currently the ONLY patient-level 
variable — the PCS would capture this more systematically.
"""

# Generate Standard vs Extra chart
fig, ax = plt.subplots(figsize=(6, 4))
x = np.arange(2)
width = 0.35
bars1 = ax.barh(x + width/2, [std_pvi['Case_Time'].mean(), extra['Case_Time'].mean()],
                width, label='Mean Case Time', color='#4ECDC4')
bars2 = ax.barh(x - width/2, [std_pvi['PT_In_Out'].mean(), extra['PT_In_Out'].mean()],
                width, label='Mean Pt In-Out', color='#A29BFE')
ax.set_yticks(x)
ax.set_yticklabels(['Standard PVI\n(n=127)', 'Extra Targets\n(n=22)'])
ax.set_xlabel('Minutes')
ax.set_title('Standard PVI vs. Additional Ablation Targets', fontweight='bold')
ax.legend()
for bar in bars1:
    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
            f'{bar.get_width():.1f}', va='center', fontsize=9)
for bar in bars2:
    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
            f'{bar.get_width():.1f}', va='center', fontsize=9)
ax.set_facecolor('#0F1117')
fig.patch.set_facecolor('#0F1117')
ax.tick_params(colors='white')
ax.xaxis.label.set_color('white')
ax.title.set_color('white')
ax.legend(facecolor='#1A1D27', edgecolor='#2A2D3A', labelcolor='white')
ax.spines['bottom'].set_color('#2A2D3A')
ax.spines['left'].set_color('#2A2D3A')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig('standard_vs_extra.png', dpi=150, bbox_inches='tight')
plt.close()
print("\n[Chart saved: standard_vs_extra.png]")


# ============================================================
# 6. CORRELATIONS WITH CASE TIME (Pearson r)
# ============================================================
print("\n" + "=" * 70)
print("SECTION 6: CORRELATIONS WITH CASE TIME")
print("=" * 70)

corr_vars = ['ABL_Duration', 'TSP', 'PT_Prep', 'NumABL', 'Access']
corr_labels = ['ABL Duration', 'TSP', 'PT Prep', 'Num ABL Sites', 'Access']

print("\n--- Pearson Correlation Coefficients ---")
corr_data = []
for var, label in zip(corr_vars, corr_labels):
    valid = df[['Case_Time', var]].dropna()
    r, p = stats.pearsonr(valid['Case_Time'], valid[var])
    corr_data.append({'Variable': label, 'r': r, 'p': p})
    sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else 'n.s.'
    print(f"  {label:15s}: r = {r:.3f}, p = {p:.4f} {sig}")

corr_df = pd.DataFrame(corr_data)

"""
REASONING — Pearson Correlation (r) Interpretation:

r measures the LINEAR relationship between two variables:
- r = 1.0: perfect positive correlation
- r = 0.0: no linear relationship
- r = -1.0: perfect negative correlation

Strength guidelines (Cohen's conventions):
- |r| < 0.10: negligible
- |r| = 0.10–0.29: small
- |r| = 0.30–0.49: medium
- |r| ≥ 0.50: large

Our results:
- ABL Duration (r=0.76): LARGE — strongest predictor. Makes clinical sense: 
  ablation is the longest phase. A 1-min increase in ABL Duration corresponds
  to a ~0.76-min increase in Case Time.
  
- TSP (r=0.50): LARGE — second strongest. TSP difficulty (anatomy-dependent)
  cascades into total procedure time because a difficult TSP often means 
  difficult anatomy for all subsequent steps.

- PT Prep (r=0.38): MEDIUM — partly reflects anesthesia complexity (which 
  correlates with patient comorbidity — an unobserved factor)

- NumABL (r=0.38): MEDIUM — more ablation sites = more time. But r is only 
  0.38, not higher, because repositioning time per site varies significantly 
  (~70% of ABL Duration is repositioning, per Dr. Chan).

- Access (r=0.17): SMALL — vascular access is short and mostly standardized,
  contributing little to total time variation.

The p-values for all correlations are < 0.0001, meaning these relationships 
are statistically significant (not due to chance). The p-value tells us IF a
relationship exists; the r-value tells us HOW STRONG it is.
"""

# Generate correlation chart
fig, ax = plt.subplots(figsize=(7, 4))
colors = ['#FF6B6B' if r > 0.5 else '#FFE66D' if r > 0.3 else '#4ECDC4'
          for r in corr_df['r']]
bars = ax.barh(corr_df['Variable'][::-1], corr_df['r'][::-1], color=colors[::-1],
               edgecolor='white', linewidth=0.5)
ax.set_xlabel('Pearson r')
ax.set_title('Correlations with Case Time', fontsize=14, fontweight='bold')
ax.set_xlim(0, 1.0)
for bar, r in zip(bars, corr_df['r'][::-1]):
    ax.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2,
            f'{r:.2f}', va='center', fontsize=10, color='white')
ax.set_facecolor('#F0F4F8')
fig.patch.set_facecolor('#F0F4F8')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig('correlations.png', dpi=150, bbox_inches='tight')
plt.close()
print("\n[Chart saved: correlations.png]")


# ============================================================
# 7. NUMBER OF ABLATION SITES → CASE TIME
# ============================================================
print("\n" + "=" * 70)
print("SECTION 7: NUMBER OF ABLATION SITES → CASE TIME")
print("=" * 70)

abl_groups = df.groupby('NumABL')['Case_Time'].agg(['mean', 'std', 'count']).reset_index()
abl_groups = abl_groups[abl_groups['count'] >= 3]
abl_groups.columns = ['NumABL', 'Mean_CT', 'Std_CT', 'Count']

print("\n--- Mean Case Time by Number of ABL Sites ---")
for _, row in abl_groups.iterrows():
    print(f"  NumABL = {int(row['NumABL']):2d}: Mean CT = {row['Mean_CT']:5.1f} min (n={int(row['Count'])})")

# Correlation
valid = df[['NumABL', 'ABL_Duration']].dropna()
r_abl, p_abl = stats.pearsonr(valid['NumABL'], valid['ABL_Duration'])
print(f"\nCorrelation NumABL vs ABL_Duration: r = {r_abl:.3f}, p = {p_abl:.6f}")

"""
REASONING:
- Clear step increase at 21+ sites: cases with 17–20 sites average ~34 min,
  while 21+ sites average 42–88 min
- Cases with 30 sites average 88.3 min — 2.5x the standard case
- The planned ablation scope is KNOWABLE before the procedure starts 
  (from the physician's pre-op plan) — this is why Ablation Scope gets 
  25% weight in the PCS
"""

# Generate NumABL chart
fig, ax = plt.subplots(figsize=(8, 4))
colors = ['#FF6B6B' if x >= 27 else '#4ECDC4' for x in abl_groups['NumABL']]
ax.bar(abl_groups['NumABL'].astype(str), abl_groups['Mean_CT'], color=colors,
       edgecolor='white', linewidth=0.5)
ax.set_xlabel('# Ablation Sites')
ax.set_ylabel('Mean Case Time (min)')
ax.set_title('Number of Ablation Sites → Case Time', fontsize=14, fontweight='bold')
ax.set_facecolor('#F0F4F8')
fig.patch.set_facecolor('#F0F4F8')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig('numabl_vs_casetime.png', dpi=150, bbox_inches='tight')
plt.close()
print("\n[Chart saved: numabl_vs_casetime.png]")


# ============================================================
# 8. CASE SEQUENCE EFFECT (Daily Position)
# ============================================================
print("\n" + "=" * 70)
print("SECTION 8: CASE SEQUENCE EFFECT (DAILY POSITION)")
print("=" * 70)

df_sorted = df.sort_values(['Date', 'Physician', 'Case'])
df_sorted['Case_Seq'] = df_sorted.groupby(['Date', 'Physician']).cumcount() + 1

print("\n--- Mean by Case Sequence Position ---")
seq_data = []
for seq in [1, 2, 3, 4]:
    sub = df_sorted[df_sorted['Case_Seq'] == seq]
    prep = sub['PT_Prep'].dropna()
    ct = sub['Case_Time'].dropna()
    if len(ct) > 3:
        seq_data.append({
            'Sequence': seq, 'n': len(ct),
            'Mean_Prep': prep.mean(), 'Mean_CT': ct.mean()
        })
        print(f"  Case #{seq} of day (n={len(ct)}): Prep = {prep.mean():.1f} min, Case Time = {ct.mean():.1f} min")

seq_df = pd.DataFrame(seq_data)

# Test 1st vs 4th case
first = df_sorted[df_sorted['Case_Seq'] == 1]['Case_Time'].dropna()
fourth = df_sorted[df_sorted['Case_Seq'] == 4]['Case_Time'].dropna()
t_seq, p_seq = stats.ttest_ind(first, fourth)
print(f"\n  1st vs 4th case t-test: t = {t_seq:.3f}, p = {p_seq:.4f}")
print(f"  Difference: {first.mean() - fourth.mean():.1f} min (1st case penalty)")

"""
REASONING:
- The 1st case of the day averages 47.3 min vs. 36.8 for the 4th case
  → 10.5 min difference — a "warm-up penalty"
- Prep time is also highest for 1st case (22.1 vs. 17.4–19.5 min)
- This reflects: room setup overhead, equipment boot-up, team synchronization
- The 4th case prep time rises slightly (19.5 min) — possibly fatigue

IMPLICATION FOR SCHEDULING:
- This finding directly informs our Med → High → Med → Low scheduling rule
- Don't schedule the hardest case first (warm-up penalty)
- Don't schedule it last (fatigue)
- Schedule it 2nd: team is warmed up AND cognitive resources are near-peak
"""

# Generate case sequence chart
fig, ax = plt.subplots(figsize=(6, 4))
x = np.arange(len(seq_df))
width = 0.35
bars1 = ax.bar(x - width/2, seq_df['Mean_Prep'], width, label='Mean Prep Time',
               color='#A29BFE', edgecolor='white', linewidth=0.5)
bars2 = ax.bar(x + width/2, seq_df['Mean_CT'], width, label='Mean Case Time',
               color='#4ECDC4', edgecolor='white', linewidth=0.5)
ax.set_xticks(x)
ax.set_xticklabels(['1st', '2nd', '3rd', '4th'])
ax.set_xlabel('Case of the Day')
ax.set_ylabel('Minutes')
ax.set_title('Case Sequence Effect (Daily Position)', fontsize=14, fontweight='bold')
ax.legend()
for bar in bars1:
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            f'{bar.get_height():.1f}', ha='center', fontsize=8)
for bar in bars2:
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            f'{bar.get_height():.1f}', ha='center', fontsize=8)
ax.set_facecolor('#F0F4F8')
fig.patch.set_facecolor('#F0F4F8')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig('case_sequence.png', dpi=150, bbox_inches='tight')
plt.close()
print("\n[Chart saved: case_sequence.png]")


# ============================================================
# 9. ABLATION: REPOSITIONING vs. ENERGY DELIVERY
# ============================================================
print("\n" + "=" * 70)
print("SECTION 9: ABLATION REPOSITIONING ANALYSIS")
print("=" * 70)

valid_abl = df[['ABL_Duration', 'ABL_Time']].dropna()
mean_dur = valid_abl['ABL_Duration'].mean()
mean_time = valid_abl['ABL_Time'].mean()
reposition_time = mean_dur - mean_time
reposition_pct = (reposition_time / mean_dur) * 100

print(f"Mean ABL Duration (total phase): {mean_dur:.1f} min")
print(f"Mean ABL Time (energy delivery):  {mean_time:.1f} min")
print(f"Mean Repositioning Time:          {reposition_time:.1f} min")
print(f"Repositioning Percentage:         {reposition_pct:.1f}%")

"""
REASONING:
- ABL Duration (24.0 min) is the total time from first to last ablation delivery
- ABL Time (7.4 min) is the actual cumulative energy delivery time
- The difference (16.6 min = ~70%) is CATHETER REPOSITIONING
- This was confirmed by Dr. Chan in the guest lecture: "Most time is NOT energy 
  delivery. It is positioning. This is the hidden inefficiency."
- This means layout optimization (reducing repositioning friction) has a much 
  larger potential impact than improving the ablation technology itself
"""


# ============================================================
# 10. OUTLIER IDENTIFICATION
# ============================================================
print("\n" + "=" * 70)
print("SECTION 10: OUTLIER ANALYSIS")
print("=" * 70)

threshold = df['Case_Time'].mean() + 2 * df['Case_Time'].std()
outliers = df[df['Case_Time'] > threshold]

print(f"\nOutlier threshold (mean + 2σ): {threshold:.1f} min")
print(f"Number of outliers: {len(outliers)}")
print(f"\n{'Case':>5} {'Physician':>10} {'Case Time':>10} {'#ABL':>5} {'Note':>15} {'TSP':>5}")
print("-" * 60)
for _, row in outliers.iterrows():
    print(f"{int(row['Case']):5d} {row['Physician']:>10} {row['Case_Time']:10.0f} "
          f"{int(row['NumABL']) if pd.notna(row['NumABL']) else 'N/A':>5} "
          f"{str(row['Note']) if pd.notna(row['Note']) else '—':>15} "
          f"{row['TSP']:5.0f}")

# TSP outliers
tsp_outliers = df[df['TSP'] > 15]
print(f"\n--- TSP Outliers (>15 min) ---")
print(f"{'Case':>5} {'Physician':>10} {'TSP':>5} {'Case Time':>10}")
for _, row in tsp_outliers.iterrows():
    print(f"{int(row['Case']):5d} {row['Physician']:>10} {row['TSP']:5.0f} {row['Case_Time']:10.0f}")

"""
REASONING:
- We use mean + 2σ as the outlier threshold (a standard statistical convention)
- 6 cases exceed this threshold — 5 involve Dr. B
- Key drivers: extremely long TSP times (anatomy-dependent), extra ablation 
  targets, and high ABL site counts
- Case 57 (159 min) is the extreme: AAFL+PST BOX with 30 ABL sites
- Case 90 (Dr. C, 83 min) was due to TROUBLESHOOT — a technical equipment issue
- TSP outliers >15 min occur almost exclusively with Dr. B, likely reflecting 
  more complex patient selection rather than technique issues
"""


# ============================================================
# 11. MONTHLY TEMPORAL TREND
# ============================================================
print("\n" + "=" * 70)
print("SECTION 11: MONTHLY TEMPORAL TREND (LEARNING CURVE)")
print("=" * 70)

df['Month'] = df['Date'].dt.to_period('M')
monthly = df.groupby('Month')['Case_Time'].agg(['mean', 'std', 'count']).reset_index()
monthly.columns = ['Month', 'Mean_CT', 'Std_CT', 'Count']

print("\n--- Monthly Case Time ---")
for _, row in monthly.iterrows():
    print(f"  {str(row['Month']):8s}: Mean = {row['Mean_CT']:5.1f} min, σ = {row['Std_CT']:5.1f}, n = {int(row['Count'])}")

pct_reduction = (monthly.iloc[0]['Mean_CT'] - monthly.iloc[-1]['Mean_CT']) / monthly.iloc[0]['Mean_CT'] * 100
print(f"\n  Overall reduction: {monthly.iloc[0]['Mean_CT']:.1f} → {monthly.iloc[-1]['Mean_CT']:.1f} min ({pct_reduction:.0f}%)")


# ============================================================
# 12. SUMMARY OF ALL STATISTICAL TESTS
# ============================================================
print("\n" + "=" * 70)
print("SECTION 12: COMPLETE STATISTICAL TEST SUMMARY")
print("=" * 70)

print("""
┌─────────────────────────────────────────────────────────────────────┐
│ TEST                          │ STATISTIC    │ P-VALUE  │ RESULT   │
├─────────────────────────────────────────────────────────────────────┤
│ ANOVA (Case Time, 3 doctors)  │ F = 16.22    │ <0.0001  │ ***      │
│ ANOVA (Pt In-Out, 3 doctors)  │ F = 24.19    │ <0.0001  │ ***      │
│ T-test: Dr. A vs Dr. B (CT)   │ t = -5.63    │ <0.0001  │ ***      │
│ T-test: Dr. A vs Dr. C (CT)   │ t = -2.35    │ 0.021    │ *        │
│ T-test: Dr. B vs Dr. C (CT)   │ t = 1.62     │ 0.109    │ n.s.     │
│ T-test: Std PVI vs Extra (CT) │ t = -3.67    │ 0.0003   │ ***      │
│ T-test: Std PVI vs Extra (PIO)│ t = -2.12    │ 0.035    │ *        │
│ Pearson r: ABL Dur vs CT      │ r = 0.76     │ <0.0001  │ Large    │
│ Pearson r: TSP vs CT          │ r = 0.50     │ <0.0001  │ Large    │
│ Pearson r: PT Prep vs CT      │ r = 0.38     │ <0.0001  │ Medium   │
│ Pearson r: NumABL vs CT       │ r = 0.38     │ <0.0001  │ Medium   │
│ Pearson r: Access vs CT       │ r = 0.17     │ 0.044    │ Small    │
│ Pearson r: NumABL vs ABL Dur  │ r = 0.43     │ <0.0001  │ Medium   │
└─────────────────────────────────────────────────────────────────────┘

SIGNIFICANCE LEVELS:
  ***  p < 0.001  (very strong evidence against H₀)
  **   p < 0.01   (strong evidence)
  *    p < 0.05   (moderate evidence — conventional significance threshold)
  n.s. p ≥ 0.05   (not significant — cannot reject H₀)

KEY STATISTICAL CONCEPTS USED:

1. p-value: The probability of observing results at least as extreme as the 
   data, assuming the null hypothesis is true. A small p-value (< 0.05) means
   the observed effect is unlikely due to chance alone.

2. F-statistic (ANOVA): Ratio of between-group variance to within-group variance.
   F >> 1 means groups are more different from each other than within themselves.

3. t-statistic: Measures how many standard errors apart two group means are.
   |t| > 2 generally indicates significance with moderate sample sizes.

4. Pearson r: Measures linear correlation strength and direction (-1 to +1).
   r² gives the proportion of variance explained (e.g., r=0.76 → r²=0.58, 
   meaning ABL Duration explains ~58% of Case Time variance).

5. Coefficient of Variation (CV): σ/μ × 100%. Normalizes variability for 
   comparison across variables with different scales/units.
""")


print("\n" + "=" * 70)
print("ANALYSIS COMPLETE - All charts saved to ./")
print("=" * 70)
print("\nGenerated files:")
print("  cv_by_step.png          — Coefficient of Variation by procedure step")
print("  standard_vs_extra.png   — Standard PVI vs. Extra Targets comparison")
print("  correlations.png        — Pearson correlations with Case Time")
print("  numabl_vs_casetime.png  — NumABL sites vs. Case Time")
print("  case_sequence.png       — Daily case sequence effect")
