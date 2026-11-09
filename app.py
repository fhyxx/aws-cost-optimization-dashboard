"""Streamlit entry point for the AWS Cost Optimization Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from aws_cost_dashboard.analysis import (  # noqa: E402
    cost_breakdown,
    executive_metrics,
    monthly_totals,
)
from aws_cost_dashboard.anomalies import detect_cost_anomalies  # noqa: E402
from aws_cost_dashboard.exports import build_export_bundle  # noqa: E402
from aws_cost_dashboard.recommendations import (  # noqa: E402
    build_recommendations,
    recommendations_frame,
)
from aws_cost_dashboard.sample_data import load_sample_data  # noqa: E402
from aws_cost_dashboard.schemas import read_billing_csv  # noqa: E402

st.set_page_config(
    page_title="AWS Cost Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def money(value: float) -> str:
    return f"${value:,.2f}"


st.title("AWS Cost Intelligence")
st.caption(
    "Understand billed spend, investigate anomalies, and prioritize evidence-based optimization."
)

with st.sidebar:
    st.header("Billing data")
    st.caption("Runs locally. No AWS API calls or credentials are used.")
    uploaded = st.file_uploader("Upload normalized billing CSV", type=["csv"])

if uploaded is None:
    try:
        source_frame = load_sample_data()
    except (OSError, ValueError) as exc:
        st.error(f"Could not load the included sample dataset: {exc}")
        st.stop()
    source_label = "SYNTHETIC DEMONSTRATION DATA — generated, not actual AWS billing"
    is_synthetic = True
else:
    try:
        source_frame = read_billing_csv(uploaded)
    except ValueError as exc:
        st.error(str(exc))
        st.info("See the README for required columns and supported AWS CUR header aliases.")
        st.stop()
    source_label = f"Uploaded CSV: {uploaded.name} — user-provided billing records"
    is_synthetic = False

if is_synthetic:
    st.warning(source_label, icon="🧪")
else:
    st.success(source_label)

months = sorted(source_frame["billing_month"].unique().tolist())
if len(months) < 2:
    st.warning("At least two billing months are needed for month-over-month analysis.")
if len(months) < 12:
    st.info(f"This dataset covers {len(months)} billing month(s); trend confidence is limited.")

with st.sidebar:
    st.header("Filters")
    selected_range = st.select_slider(
        "Billing month range",
        options=months,
        value=(months[0], months[-1]),
    )
    region_options = sorted(source_frame["region"].unique().tolist())
    account_options = sorted(source_frame["account"].unique().tolist())
    service_options = sorted(source_frame["service"].unique().tolist())
    selected_regions = st.multiselect("Region", region_options, default=region_options)
    selected_accounts = st.multiselect("Account", account_options, default=account_options)
    selected_services = st.multiselect("Service", service_options, default=service_options)
    st.header("Explainable anomaly rules")
    mom_threshold = st.slider("Minimum month-over-month increase (%)", 25, 200, 50, 5)
    minimum_increase = st.number_input(
        "Minimum cost increase (USD)", min_value=0.0, value=100.0, step=25.0
    )
    st.header("Illustrative savings scenario")
    scenario_low = st.slider("Lower scenario (%)", 0, 50, 5, 1)
    scenario_high = st.slider(
        "Upper scenario (%)",
        min_value=scenario_low,
        max_value=75,
        value=max(15, scenario_low),
        step=1,
    )

filtered = source_frame[
    source_frame["billing_month"].between(selected_range[0], selected_range[1])
    & source_frame["region"].isin(selected_regions)
    & source_frame["account"].isin(selected_accounts)
    & source_frame["service"].isin(selected_services)
].copy()

if filtered.empty:
    st.warning("No billing records match these filters. Adjust the filters to continue.")
    st.stop()

kpis = executive_metrics(filtered)
metric_columns = st.columns(4)
metric_columns[0].metric("Spend in selected period", money(kpis.period_total))
metric_columns[1].metric(f"Latest month · {kpis.current_month}", money(kpis.current_month_spend))
if kpis.month_over_month_change is None:
    metric_columns[2].metric("Month-over-month change", "N/A")
else:
    delta = (
        f"{kpis.month_over_month_percent:+.1f}%"
        if kpis.month_over_month_percent is not None
        else None
    )
    metric_columns[2].metric(
        "Month-over-month change", money(kpis.month_over_month_change), delta=delta
    )
metric_columns[3].metric("Billing months", f"{filtered['billing_month'].nunique():,}")

st.caption(
    "Spend is the sum of uploaded unblended costs after filters. Billing records do not show utilization, "
    "waste, business criticality, or root cause. Savings scenarios are illustrative and not additive."
)

left, right = st.columns((1.65, 1))
with left:
    st.subheader("Monthly spend trend")
    trend = monthly_totals(filtered)
    trend_figure = px.line(
        trend,
        x="billing_month",
        y="spend",
        markers=True,
        labels={"billing_month": "Billing month", "spend": "Spend (USD)"},
    )
    trend_figure.update_layout(margin={"l": 8, "r": 8, "t": 12, "b": 8}, hovermode="x unified")
    st.plotly_chart(trend_figure, use_container_width=True)
with right:
    st.subheader("Latest-month service mix")
    latest = filtered[filtered["billing_month"] == kpis.current_month]
    service_costs = cost_breakdown(latest, "service")
    service_figure = px.bar(
        service_costs,
        x="spend",
        y="service",
        orientation="h",
        labels={"spend": "Spend (USD)", "service": "AWS service"},
        text_auto=".2s",
    )
    service_figure.update_layout(
        margin={"l": 8, "r": 8, "t": 12, "b": 8},
        yaxis={"categoryorder": "total ascending"},
    )
    st.plotly_chart(service_figure, use_container_width=True)

st.subheader("Cost breakdown")
breakdown_tabs = st.tabs(["AWS service", "Region", "Account"])
for tab, dimension in zip(breakdown_tabs, ("service", "region", "account"), strict=True):
    with tab:
        breakdown = cost_breakdown(filtered, dimension)
        st.dataframe(
            breakdown.rename(
                columns={dimension: dimension.replace("_", " ").title(), "spend": "Spend (USD)"}
            ),
            hide_index=True,
            use_container_width=True,
        )

st.subheader("Cost anomaly review")
st.caption(
    f"Rule: flag a cost increase of at least {mom_threshold}% and ${minimum_increase:,.0f} month over month, "
    "or a charge at least 1.5× the previous six-month median and the same dollar threshold. "
    "This identifies unusual billing movement; it does not diagnose the cause."
)
anomalies = detect_cost_anomalies(
    filtered,
    percent_threshold=float(mom_threshold),
    minimum_increase_usd=float(minimum_increase),
)
if anomalies.empty:
    st.success("No cost spikes matched the current rule and filters.")
else:
    st.dataframe(anomalies, hide_index=True, use_container_width=True)

st.subheader("Optimization recommendations")
recommendations = build_recommendations(
    filtered,
    anomalies,
    scenario_low_percent=float(scenario_low),
    scenario_high_percent=float(scenario_high),
)
st.info(
    f"The EC2 range applies {scenario_low}%–{scenario_high}% to the latest-month EC2 bill as a screening "
    "assumption only. Validate utilization, pricing eligibility and commitments before using it. "
    "Other savings stay unquantified where billing data is insufficient."
)
recommendations_table = recommendations_frame(recommendations)
if recommendations_table.empty:
    st.write("No recommendations were generated for the selected data.")
else:
    st.dataframe(recommendations_table, hide_index=True, use_container_width=True)

st.subheader("Export analysis")
export_bytes = build_export_bundle(filtered, anomalies, recommendations, data_label=source_label)
st.download_button(
    "Download analysis package (.zip)",
    data=export_bytes,
    file_name="aws-cost-analysis.zip",
    mime="application/zip",
    help="Contains monthly trend, service/region/account breakdowns, anomaly results, recommendations and a data-label note.",
)

with st.expander("How to interpret this dashboard"):
    st.markdown(
        "- **Billing-derived:** totals, month-over-month change, service/region/account mix and anomaly rules.\n"
        "- **Requires telemetry:** rightsizing, idle-resource findings, utilization, root cause and achievable savings.\n"
        "- The EC2 savings range is an editable illustrative percentage of latest-month EC2 billed cost.\n"
        "- This app makes no AWS API calls, provisions no resources and requires no credentials."
    )
