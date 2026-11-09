"""Downloadable analysis package generation."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from aws_cost_dashboard.analysis import cost_breakdown, monthly_totals
from aws_cost_dashboard.recommendations import Recommendation


def build_export_bundle(
    frame: pd.DataFrame,
    anomalies: pd.DataFrame,
    recommendations: list[Recommendation],
    *,
    data_label: str,
) -> bytes:
    """Package filtered billing summaries, anomalies and recommendations as CSV files."""
    memory = BytesIO()
    with ZipFile(memory, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("monthly_trend.csv", monthly_totals(frame).to_csv(index=False))
        for dimension in ("service", "region", "account"):
            archive.writestr(
                f"cost_by_{dimension}.csv", cost_breakdown(frame, dimension).to_csv(index=False)
            )
        archive.writestr("anomalies.csv", anomalies.to_csv(index=False))
        recs = pd.DataFrame([item.model_dump() for item in recommendations])
        archive.writestr("recommendations.csv", recs.to_csv(index=False))
        archive.writestr(
            "README.txt",
            f"AWS Cost Optimization Dashboard analysis export\nData source: {data_label}\n"
            "All savings ranges are illustrative scenarios. An empty savings value means not quantified.\n"
            "Billing patterns do not prove utilization, waste, root cause, or achievable savings.\n",
        )
    return memory.getvalue()
