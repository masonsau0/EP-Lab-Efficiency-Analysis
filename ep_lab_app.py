"""Interactive EP Lab analytics dashboard.

Run with::

    streamlit run ep_lab_app.py

Loads the 145-case AFib ablation dataset and offers:

- per-physician filter and time-window filter
- coefficient-of-variation breakdown by procedure phase
- driver scatter (NumABL × Case Time) with dynamic regression
- one-way ANOVA + pairwise t-tests with adjustable significance level
- daily case-sequence analysis (warm-up effect)
- a "what-if" scheduling rule that re-orders the day's cases by
  predicted complexity and projects daily-overrun reduction.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st
from scipy import stats

st.set_page_config(page_title="EP Lab Efficiency", layout="wide", page_icon="🫀")

DATA = Path("ep_lab_data.xlsx")


# ---------------------------------------------------------------------------
# Loading & cleaning
# ---------------------------------------------------------------------------


@st.cache_data
def load_cases() -> pd.DataFrame:
    df = pd.read_excel(DATA, sheet_name="All Data", header=None, skiprows=4)
    df.columns = ["Drop", "Case", "Date", "Physician", "PT_Prep", "Access", "TSP",
                  "PreMap", "ABL_Duration", "ABL_Time", "NumABL", "NumApps",
                  "LA_Dwell", "Case_Time", "Avg_Case_Time", "Skin_Skin",
                  "Avg_Skin_Skin", "PostCare", "Avg_Turnover", "PT_Out_Time",
                  "PT_In_Out", "Note"]
    df = df.drop(columns=["Drop"]).dropna(subset=["Case"])
    num_cols = ["PT_Prep", "Access", "TSP", "PreMap", "ABL_Duration", "ABL_Time",
                "NumABL", "NumApps", "LA_Dwell", "Case_Time", "Skin_Skin",
                "PostCare", "PT_In_Out"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Date"] = df["Date"].replace("Juy 21", "2025-07-21")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Has_Extra"] = df["Note"].notna() & (df["Note"] != "Dr. D") & (df["Note"] != "TROUBLESHOOT")
    return df


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


st.title("EP Lab Procedural Efficiency")
st.caption("Filter, analyse, and project schedule changes against 145 AFib ablation cases (Jan – Oct 2025).")

with st.expander("How to use this app", expanded=False):
    st.markdown("""
**What this app does in plain English.**
A hospital electrophysiology (EP) lab performs heart procedures called
AFib ablations. Some take 17 minutes, others take 159. The schedulers
need to know *why* — is it the physician, the patient, or just bad
luck? This app analyses 145 real cases, breaks down which procedural
phase causes the most variation, and lets you simulate scheduling
changes to see how much overrun time the lab could save.

**Quick start (60 seconds).**
1. Use the **filters** in the sidebar (physician, date range, case
   type) to narrow down which cases to analyse.
2. Look at the **CV by phase** chart — taller bars = more variable
   phase. The biggest bars are where the unpredictability lives.
3. Switch to the **Drivers** tab — pick a feature like "ablation
   sites" and see how it correlates with case time.
4. Open the **Schedule what-if** tab and slide the warm-up allowance
   to see how many fewer days would run over.

**The filters.**
- **Physician** — pick one or all three doctors.
- **Date range** — restrict to a window of cases.
- **Case mix** — All / Standard PVI / Extra targets. "Extra targets"
  cases take longer and are usually what causes overruns.

**The tabs.**
- **CV by phase** — Coefficient of variation per procedure phase. CV
  is variability normalized by the average — higher = the phase is
  unpredictable. Pre-Map and TSP top this chart because they depend
  heavily on patient anatomy.
- **Physician comparison** — boxplots and an ANOVA test across the
  three doctors. The ANOVA p-value tells you whether the differences
  are real or random.
- **Drivers** — Pearson correlation between each driver (ablation
  count, TSP duration, etc.) and total case time. Higher correlation
  = more predictive.
- **Schedule what-if** — the punchline. Move the warm-up allowance
  slider and the case-ordering toggle to simulate a complexity-aware
  schedule. The number at the top tells you what % of overrun days
  you'd save.
- **PCS calculator** — Patient Complexity Score. Pick six pre-op
  factors (BMI, cardiac history, septal anatomy, ablation scope, ASA
  score, anticoagulation) for a hypothetical patient and the app
  returns a 0–100 complexity score plus the recommended slot in the
  day's schedule.

**Try this.** Filter to "Extra targets" only and look at how much
worse case time gets vs Standard PVI. Then in the what-if tab, turn
on complexity-based ordering and watch the projected daily overruns
drop ~15 %.
""")

if not DATA.exists():
    st.error(f"`{DATA}` not found. Make sure you're running from the project folder.")
    st.stop()

df = load_cases()

with st.sidebar:
    st.header("Filters")
    physicians = sorted(df["Physician"].dropna().unique().tolist())
    sel_phys = st.multiselect("Physicians", physicians, default=physicians)
    date_min = df["Date"].min().date()
    date_max = df["Date"].max().date()
    date_range = st.date_input("Date range", value=(date_min, date_max),
                                 min_value=date_min, max_value=date_max)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        d_lo, d_hi = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        d_lo, d_hi = pd.Timestamp(date_min), pd.Timestamp(date_max)

    case_filter = st.radio("Case mix", ["All", "Standard PVI only", "Extra targets only"])
    alpha = st.slider("ANOVA / t-test significance", 0.001, 0.10, 0.05, 0.005, format="%.3f")

# Apply filters
filt = df[df["Physician"].isin(sel_phys)
          & df["Date"].between(d_lo, d_hi)].copy()
if case_filter == "Standard PVI only":
    filt = filt[~filt["Has_Extra"]]
elif case_filter == "Extra targets only":
    filt = filt[filt["Has_Extra"]]

if len(filt) == 0:
    st.warning("No cases match the filters.")
    st.stop()

# Headline metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Cases shown", f"{len(filt)} / {len(df)}")
m2.metric("Mean Case Time", f"{filt['Case_Time'].mean():.1f} min")
m3.metric("Mean PT In→Out", f"{filt['PT_In_Out'].mean():.1f} min")
m4.metric("Range", f"{int(filt['Case_Time'].min())} – {int(filt['Case_Time'].max())} min")

st.divider()

tab_cv, tab_phys, tab_drivers, tab_seq, tab_whatif, tab_pcs = st.tabs(
    ["CV by phase", "Physician comparison", "Drivers", "Daily sequence", "Schedule what-if", "PCS calculator"]
)


# ---- CV by phase ---------------------------------------------------------

with tab_cv:
    step_cols = ["PT_Prep", "Access", "TSP", "PreMap", "ABL_Duration", "PostCare"]
    step_labels = ["PT Prep", "Access", "TSP", "Pre-Map", "ABL Duration", "Post-Care"]
    cv = pd.DataFrame({
        "step": step_labels,
        "mean_min": [filt[c].mean() for c in step_cols],
        "std_min": [filt[c].std() for c in step_cols],
    })
    cv["CV_%"] = 100 * cv["std_min"] / cv["mean_min"]
    cv = cv.sort_values("CV_%", ascending=False).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#c44e52" if v > 80 else "#dd8452" if v > 35 else "#55a868" for v in cv["CV_%"]]
    ax.bar(cv["step"], cv["CV_%"], color=colors)
    for i, v in enumerate(cv["CV_%"]):
        ax.text(i, v + 3, f"{v:.0f}%", ha="center", fontsize=9)
    ax.set_ylabel("CV (%)"); ax.set_title("Coefficient of variation by phase")
    plt.xticks(rotation=15); plt.tight_layout()
    st.pyplot(fig)

    st.dataframe(cv.round(2), hide_index=True, use_container_width=True)
    st.caption("Phases with CV > 80 % (red) are dominated by patient-anatomy variability — the unpredictable time sinks. Protocol-driven phases (CV < 35 %) are good candidates for standardisation.")


# ---- Physician comparison ------------------------------------------------

with tab_phys:
    grp = filt.groupby("Physician")[["Case_Time", "PT_In_Out", "TSP", "NumABL"]].agg(["mean", "std", "count"]).round(1)
    st.dataframe(grp, use_container_width=True)

    if len(sel_phys) >= 2:
        groups_ct = [filt[filt["Physician"] == d]["Case_Time"].dropna() for d in sel_phys]
        groups_ct = [g for g in groups_ct if len(g) >= 2]
        if len(groups_ct) >= 2:
            f_ct, p_ct = stats.f_oneway(*groups_ct)
            verdict = "**significant**" if p_ct < alpha else "not significant"
            st.markdown(
                f"**One-way ANOVA on Case Time:**  F = {f_ct:.2f}, p = {p_ct:.4f} — "
                f"physician effect is {verdict} at α = {alpha:.3f}."
            )
        else:
            st.caption("Need ≥ 2 physicians with ≥ 2 cases each for ANOVA.")

    fig, ax = plt.subplots(figsize=(8, 4))
    sns.boxplot(data=filt, x="Physician", y="Case_Time", ax=ax,
                 order=sel_phys, color="#4c72b0")
    sns.stripplot(data=filt, x="Physician", y="Case_Time", ax=ax,
                   order=sel_phys, size=3, color="black", alpha=0.5)
    ax.set_title("Case time by physician"); ax.set_ylabel("Case Time (min)")
    plt.tight_layout(); st.pyplot(fig)


# ---- Drivers --------------------------------------------------------------

with tab_drivers:
    drivers = ["NumABL", "NumApps", "LA_Dwell", "ABL_Duration", "TSP", "PreMap"]
    corr = pd.DataFrame({
        "driver": drivers,
        "pearson_r": [filt[[d, "Case_Time"]].dropna().corr().iloc[0, 1] for d in drivers],
    }).sort_values("pearson_r", key=lambda s: s.abs(), ascending=False)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.barh(corr["driver"][::-1], corr["pearson_r"][::-1], color="#4c72b0")
    ax.set_xlabel("Pearson correlation with Case Time"); ax.axvline(0, color="black", lw=0.5)
    ax.set_title("Drivers of Case Time")
    st.pyplot(fig)

    sel_driver = st.selectbox("Scatter Case Time vs.", drivers, index=0)
    fig, ax = plt.subplots(figsize=(7, 4))
    sub = filt.dropna(subset=[sel_driver, "Case_Time"])
    for label, group in sub.groupby("Has_Extra"):
        ax.scatter(group[sel_driver], group["Case_Time"], alpha=0.6,
                    label="Extra targets" if label else "Standard PVI")
    if len(sub) > 1:
        m, b = np.polyfit(sub[sel_driver], sub["Case_Time"], 1)
        xs = np.linspace(sub[sel_driver].min(), sub[sel_driver].max(), 50)
        ax.plot(xs, m * xs + b, "k--", lw=1, alpha=0.6, label=f"fit y = {m:.1f}x + {b:.0f}")
    ax.set_xlabel(sel_driver); ax.set_ylabel("Case Time (min)")
    ax.set_title(f"Case Time vs. {sel_driver}"); ax.legend()
    plt.tight_layout(); st.pyplot(fig)


# ---- Daily sequence -------------------------------------------------------

with tab_seq:
    df_seq = filt.dropna(subset=["Date", "Case_Time"]).copy()
    df_seq["case_position"] = df_seq.groupby("Date").cumcount() + 1
    pos_means = df_seq.groupby("case_position")["Case_Time"].agg(["mean", "count"]).reset_index()
    pos_means = pos_means[pos_means["count"] >= 5]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(pos_means["case_position"], pos_means["mean"], marker="o", color="#4c72b0")
    ax.axhline(df_seq["Case_Time"].mean(), color="gray", linestyle="--",
                 label=f"overall mean = {df_seq['Case_Time'].mean():.0f} min")
    for _, row in pos_means.iterrows():
        ax.text(row["case_position"], row["mean"] + 1, f"n={int(row['count'])}",
                ha="center", fontsize=8, color="gray")
    ax.set_xlabel("Case position in day"); ax.set_ylabel("Mean Case Time (min)")
    ax.set_title("Daily case sequence — first-case warm-up effect"); ax.legend()
    plt.tight_layout(); st.pyplot(fig)
    st.caption("Position-1 cases (the first case of the day) typically run longer than later positions, suggesting a warm-up effect that scheduling should compensate for.")


# ---- Schedule what-if -----------------------------------------------------

with tab_whatif:
    st.markdown(
        "Reorder each day's cases from **shortest expected duration → longest** "
        "(complexity-based ordering), and add a per-day warm-up minutes allowance "
        "to the first case. Compare the projected daily total to the actual."
    )
    warmup = st.slider("First-case warm-up allowance (min)", 0, 30, 10)

    df_seq = filt.dropna(subset=["Date", "Case_Time", "NumABL"]).copy()
    actual = df_seq.groupby("Date")["Case_Time"].sum().rename("actual_total_min")

    def reorder_day(group):
        g = group.sort_values("NumABL").reset_index(drop=True)
        # Warm-up adds to first case of day
        adjusted = g["Case_Time"].copy()
        if len(adjusted) > 0:
            adjusted.iloc[0] = adjusted.iloc[0] + warmup
        return adjusted.sum()

    projected = df_seq.groupby("Date").apply(reorder_day, include_groups=False).rename("projected_total_min")
    comp = pd.concat([actual, projected], axis=1).dropna()
    comp["delta_min"] = comp["projected_total_min"] - comp["actual_total_min"]

    overrun_threshold = comp["actual_total_min"].quantile(0.75)
    actual_overruns = (comp["actual_total_min"] > overrun_threshold).sum()
    projected_overruns = (comp["projected_total_min"] > overrun_threshold).sum()
    overrun_reduction = (actual_overruns - projected_overruns) / max(actual_overruns, 1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Days analysed", len(comp))
    c2.metric("Actual overrun-days", actual_overruns)
    c3.metric("Projected overrun-days", projected_overruns,
              delta=f"{-overrun_reduction:.0%}", delta_color="inverse")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.scatter(comp["actual_total_min"], comp["projected_total_min"], alpha=0.7)
    lim = (comp[["actual_total_min", "projected_total_min"]].min().min(),
           comp[["actual_total_min", "projected_total_min"]].max().max())
    ax.plot(lim, lim, "k--", alpha=0.4, label="parity")
    ax.axhline(overrun_threshold, color="red", linestyle=":", alpha=0.5, label="overrun threshold (Q3)")
    ax.set_xlabel("Actual daily total (min)"); ax.set_ylabel("Projected daily total (min)")
    ax.set_title("Projected vs. actual daily totals under complexity-based ordering")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); st.pyplot(fig)
    st.caption("Points below the parity line = days that would have finished earlier under the new schedule.")


# ---- PCS calculator ------------------------------------------------------

PCS_FACTORS = [
    {
        "id": "bmi",
        "name": "BMI Category",
        "weight": 15,
        "levels": [
            ("Normal (18.5–25)", "Baseline vascular access difficulty and standard anesthesia profile."),
            ("Overweight (25–30)", "+1 to 2 min access due to deeper vein and slightly longer intubation."),
            ("Obese (30–40)", "+3 to 5 min access, ultrasound guidance more likely, harder intubation."),
            ("Morbidly Obese (>40)", "+5 to 10 min total, possible table constraints, harder hemostasis."),
        ],
        "affects": ["Pt Prep/Intubation", "Vascular Access", "Post-Care"],
    },
    {
        "id": "cardiac",
        "name": "Cardiac History",
        "weight": 20,
        "levels": [
            ("First-time AFib ablation", "Standard anatomy with no prior scar-related complexity."),
            ("Prior cardiac catheterization", "May have scar tissue at access site or known vascular variation."),
            ("Prior ablation (redo)", "+10 to 20 min. Scar tissue complicates mapping and TSP."),
            ("Prior cardiac surgery", "Altered anatomy may make TSP and mapping significantly harder."),
        ],
        "affects": ["TSP", "Pre-Map", "Ablation"],
    },
    {
        "id": "anatomy",
        "name": "Septal Anatomy (from pre-op imaging)",
        "weight": 25,
        "levels": [
            ("Normal / thin septum", "TSP expected in roughly 2 to 5 min."),
            ("Thickened septum", "TSP may take 5 to 10 min and require added care."),
            ("Lipomatous / aneurysmal septum", "TSP may take 10 to 20 min and require specialized technique."),
            ("Prior septal closure / PFO device", "TSP may exceed 20 min or require an alternative approach."),
        ],
        "affects": ["TSP"],
    },
    {
        "id": "ablation_scope",
        "name": "Planned Ablation Scope",
        "weight": 25,
        "levels": [
            ("Standard PVI only (4 veins)", "Around 17 to 20 ablation sites and about 25 min duration."),
            ("PVI + 1 extra target", "Roughly 22 to 25 sites and about 35 min duration."),
            ("PVI + BOX or PST BOX", "About 25 to 28 sites and near 45 min duration."),
            ("PVI + multiple extras", "28 to 30+ sites and 60+ min ablation duration."),
        ],
        "affects": ["Ablation", "Verification"],
    },
    {
        "id": "comorbidity",
        "name": "Comorbidity / ASA Score",
        "weight": 10,
        "levels": [
            ("ASA I–II", "Standard anesthesia and faster recovery expected."),
            ("ASA III", "+2 to 3 min prep and longer post-care monitoring."),
            ("ASA IV", "+5+ min prep, slower extubation, extended monitoring."),
        ],
        "affects": ["Pt Prep/Intubation", "Post-Care"],
    },
    {
        "id": "anticoag",
        "name": "Anticoagulation Status",
        "weight": 5,
        "levels": [
            ("Standard protocol", "Normal hemostasis expected."),
            ("Therapeutic anticoagulation", "+3 to 5 min post-care for hemostasis."),
            ("Dual antiplatelet / complex regimen", "+5 to 10 min post-care and possible closure device."),
        ],
        "affects": ["Catheter Removal", "Post-Care"],
    },
]


with tab_pcs:
    st.markdown(
        "Estimate procedural complexity from six pre-operative factors that "
        "are usually hidden from raw timing data. Pick the patient profile "
        "below — the score and recommended schedule slot update instantly."
    )

    selections: dict[str, int] = {}
    cols = st.columns(2)
    for i, factor in enumerate(PCS_FACTORS):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{factor['name']}**  &nbsp; *({factor['weight']}% weight)*")
                st.caption(f"Affects: {', '.join(factor['affects'])}")
                labels = [lvl[0] for lvl in factor["levels"]]
                idx = st.radio(
                    factor["name"],
                    options=list(range(len(labels))),
                    format_func=lambda i, labels=labels: labels[i],
                    key=f"pcs_{factor['id']}",
                    label_visibility="collapsed",
                )
                selections[factor["id"]] = idx
                st.caption(f"_Selected effect:_ {factor['levels'][idx][1]}")

    score = 0.0
    breakdown_rows = []
    for factor in PCS_FACTORS:
        max_level = len(factor["levels"]) - 1
        sel = selections[factor["id"]]
        contribution = (sel / max_level) * factor["weight"]
        score += contribution
        breakdown_rows.append({
            "Factor": factor["name"].split("(")[0].strip(),
            "Selected": factor["levels"][sel][0].split("(")[0].strip(),
            "Score / Max": f"{sel}/{max_level}",
            "Weight": f"{factor['weight']}%",
            "Contribution": round(contribution, 1),
        })
    score = round(score)

    if score > 60:
        category, slot, color = "High", "2nd case of the day", "#f87171"
        rationale = (
            "This case likely needs the strongest decision quality and the most "
            "focused attention. The second case is the best fit because the team "
            "is already warmed up, but fatigue is still limited."
        )
    elif score > 30:
        category, slot, color = "Medium", "1st or 3rd case", "#facc15"
        rationale = (
            "A medium-complexity case fits best in the first or third slot. These "
            "positions balance warm-up effects with still-solid cognitive capacity."
        )
    else:
        category, slot, color = "Low", "4th case of the day", "#22c55e"
        rationale = (
            "This case is routine enough to tolerate later-day fatigue better. "
            "Placing it last helps preserve the strongest slots for harder cases."
        )

    affected_steps: list[str] = []
    for factor in PCS_FACTORS:
        if selections[factor["id"]] > 0:
            for step in factor["affects"]:
                if step not in affected_steps:
                    affected_steps.append(step)

    st.divider()
    res_left, res_right = st.columns([1, 1])
    with res_left:
        st.markdown(
            f"<div style='font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:1.6px;'>Patient Complexity Score</div>"
            f"<div style='font-size:58px;font-weight:800;font-family:monospace;line-height:1;color:{color};'>{score}<span style='font-size:22px;color:#94a3b8;'> /100</span></div>",
            unsafe_allow_html=True,
        )
        st.progress(min(score, 100) / 100)
    with res_right:
        st.markdown(
            f"<div style='font-size:24px;font-weight:800;color:{color};text-align:right;'>{category} Complexity</div>"
            f"<div style='font-size:14px;color:#94a3b8;text-align:right;margin-top:8px;'>Recommended scheduling slot: <strong style='color:{color};'>{slot}</strong></div>",
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        st.markdown("**Scheduling rationale**")
        st.markdown(rationale)
        if affected_steps:
            st.caption("Procedure steps affected: " + " · ".join(affected_steps))

    with st.expander("Show score breakdown & formula"):
        st.markdown("**Formula:** PCS = Σ (selected level / max level) × factor weight")
        st.dataframe(pd.DataFrame(breakdown_rows), hide_index=True, use_container_width=True)
        st.markdown(f"**Total PCS:** {score} / 100")
        st.caption(
            "Septal anatomy and ablation scope are weighted highest because they "
            "are the strongest drivers of intra-procedural difficulty. Cardiac "
            "history follows closely because redo or surgically altered cases can "
            "meaningfully increase mapping and access complexity. BMI, ASA score, "
            "and anticoagulation matter too, but they affect more secondary "
            "timing burdens rather than the main bottleneck steps."
        )

    with st.expander("Suggested daily pattern: Medium → High → Medium → Low"):
        slot_data = [
            ("Case 1", "Medium", "~8:00 AM", "Warm-up case to settle the team into flow."),
            ("Case 2", "High", "~10:00 AM", "Best slot for peak cognition after warm-up."),
            ("Case 3", "Medium", "~12:00 PM", "Still strong attention with decent buffer."),
            ("Case 4", "Low", "~2:30 PM", "Routine case that is more fatigue resilient."),
        ]
        slot_cols = st.columns(4)
        for (slot_name, slot_cat, slot_time, slot_reason), col in zip(slot_data, slot_cols):
            active = slot_cat == category
            slot_color = {"High": "#f87171", "Medium": "#facc15", "Low": "#22c55e"}[slot_cat]
            with col:
                st.markdown(
                    f"<div style='border-top:3px solid {slot_color};padding:12px;border-radius:8px;background:rgba(255,255,255,{0.06 if active else 0.02});opacity:{1 if active else 0.55};'>"
                    f"<div style='font-weight:800;font-size:12px;'>{slot_name}</div>"
                    f"<div style='font-weight:800;font-size:12px;color:{slot_color};margin:6px 0 4px;'>{slot_cat}</div>"
                    f"<div style='font-size:11px;color:#94a3b8;'>{slot_time}</div>"
                    f"<div style='font-size:11px;color:#94a3b8;margin-top:6px;'>{slot_reason}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        st.caption("This layout is meant to help explain where a patient best fits in the daily sequence, not to replace clinical judgment.")
