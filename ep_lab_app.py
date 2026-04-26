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

tab_cv, tab_phys, tab_drivers, tab_seq, tab_whatif = st.tabs(
    ["CV by phase", "Physician comparison", "Drivers", "Daily sequence", "Schedule what-if"]
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
