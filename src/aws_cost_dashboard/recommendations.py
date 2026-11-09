"""Evidence-led recommendations with transparent, non-additive scenario savings."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class Recommendation(BaseModel):
    """A recommendation traceable to billing evidence and an explicit next step."""

    model_config = ConfigDict(extra="forbid")

    priority: str = Field(pattern=r"^(High|Medium|Low)$")
    title: str
    evidence: str
    confidence: str = Field(pattern=r"^(High|Medium|Low)$")
    evidence_type: str
    savings_low_usd: float | None = Field(default=None, ge=0)
    savings_high_usd: float | None = Field(default=None, ge=0)
    savings_basis: str
    next_step: str


def build_recommendations(
    frame: pd.DataFrame,
    anomalies: pd.DataFrame,
    *,
    scenario_low_percent: float = 5.0,
    scenario_high_percent: float = 15.0,
) -> list[Recommendation]:
    """Generate recommendations without treating billing as utilization telemetry.

    The compute savings range is an explicitly illustrative sensitivity on the latest
    month's Amazon EC2 service charge. It is not an AWS rate, forecast, or commitment.
    """
    if not 0 <= scenario_low_percent <= scenario_high_percent <= 100:
        raise ValueError("Savings scenario percentages must satisfy 0 <= low <= high <= 100.")
    if frame.empty:
        return []

    latest_month = str(frame["billing_month"].max())
    latest = frame[frame["billing_month"] == latest_month]
    recommendations: list[Recommendation] = []
    ec2 = latest.loc[latest["service"].str.casefold().eq("amazon ec2"), "unblended_cost"].sum()
    if ec2 > 0:
        low = round(float(ec2) * scenario_low_percent / 100, 2)
        high = round(float(ec2) * scenario_high_percent / 100, 2)
        monthly = (
            frame[frame["service"].str.casefold().eq("amazon ec2")]
            .groupby("billing_month")["unblended_cost"]
            .sum()
        )
        evidence = (
            f"Amazon EC2 billed ${ec2:,.2f} in the latest available month ({latest_month}); "
            f"the selected period includes {len(monthly)} distinct billing months. Billing cost alone "
            "does not show CPU, memory, burst-credit, or ASG utilization."
        )
        recommendations.append(
            Recommendation(
                priority="Medium",
                title="Review EC2 sizing and commitment coverage",
                evidence=evidence,
                confidence="Low",
                evidence_type="Billing-derived; utilization telemetry required",
                savings_low_usd=low,
                savings_high_usd=high,
                savings_basis=(
                    f"Illustrative scenario of {scenario_low_percent:g}%–{scenario_high_percent:g}% of "
                    f"latest-month Amazon EC2 billed cost (${ec2:,.2f}); not a predicted or guaranteed saving. "
                    "Does not include EBS or non-EC2 services and is not additive to other scenarios."
                ),
                next_step=(
                    "Review Compute Optimizer and representative CPU, memory, network, burst-credit, "
                    "and Auto Scaling history; separately model Savings Plans/Reserved Instance coverage."
                ),
            )
        )

    if not anomalies.empty:
        top = anomalies.sort_values("anomaly_increase_usd", ascending=False).iloc[0]
        recommendations.append(
            Recommendation(
                priority="High",
                title="Investigate the largest billing anomaly",
                evidence=str(top["explanation"]),
                confidence=str(top["confidence"]),
                evidence_type="Billing-derived rule; root cause unverified",
                savings_low_usd=None,
                savings_high_usd=None,
                savings_basis="Not quantified: an anomaly does not establish avoidable spend or its cause.",
                next_step=(
                    "Compare the bill line items, resource changes, deployment events, usage quantities and "
                    "Cost Explorer dimensions for this month before taking action."
                ),
            )
        )

    s3_cost = float(
        latest.loc[latest["service"].str.casefold().eq("amazon s3"), "unblended_cost"].sum()
    )
    if s3_cost > 0:
        recommendations.append(
            Recommendation(
                priority="Low",
                title="Review S3 storage-class and lifecycle fit",
                evidence=(
                    f"Amazon S3 billed ${s3_cost:,.2f} in {latest_month}. Billing data does not reveal "
                    "object age, retrieval frequency, minimum-duration exposure, or restore requirements."
                ),
                confidence="Low",
                evidence_type="Billing-derived; object inventory and access telemetry required",
                savings_low_usd=None,
                savings_high_usd=None,
                savings_basis="Not quantified until object age, access, retrieval and retention are validated.",
                next_step=(
                    "Review S3 Storage Lens or inventory, access logs, retention policy, retrieval needs and "
                    "lifecycle-transition charges before estimating savings."
                ),
            )
        )
    return recommendations


def recommendations_frame(recommendations: list[Recommendation]) -> pd.DataFrame:
    """Serialize recommendations to a user-friendly table."""
    return pd.DataFrame([item.model_dump() for item in recommendations])


def recommendation_records(recommendations: list[Recommendation]) -> list[dict[str, Any]]:
    """Return JSON-safe recommendation records for downloads."""
    return [item.model_dump(mode="json") for item in recommendations]
