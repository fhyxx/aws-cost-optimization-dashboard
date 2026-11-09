from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pandas as pd

from aws_cost_dashboard.anomalies import detect_cost_anomalies
from aws_cost_dashboard.exports import build_export_bundle
from aws_cost_dashboard.recommendations import build_recommendations


def test_recommendation_savings_assumptions_are_explicit_and_not_additive() -> None:
    frame = pd.DataFrame(
        [
            {
                "billing_month": "2025-01",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": 1000.0,
            },
            {
                "billing_month": "2025-02",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": 1200.0,
            },
            {
                "billing_month": "2025-02",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon S3",
                "unblended_cost": 100.0,
            },
        ]
    )
    recs = build_recommendations(
        frame, pd.DataFrame(), scenario_low_percent=5, scenario_high_percent=15
    )
    ec2 = next(item for item in recs if "EC2" in item.title)
    s3 = next(item for item in recs if "S3" in item.title)
    assert ec2.savings_low_usd == 60.0
    assert ec2.savings_high_usd == 180.0
    assert "not a predicted or guaranteed saving" in ec2.savings_basis
    assert s3.savings_low_usd is None


def test_anomaly_recommendation_has_no_unsubstantiated_savings() -> None:
    frame = pd.DataFrame(
        [
            {
                "billing_month": f"2025-{i:02d}",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": amount,
            }
            for i, amount in enumerate([100, 105, 98, 102, 350], start=1)
        ]
    )
    recs = build_recommendations(frame, detect_cost_anomalies(frame))
    anomaly = next(item for item in recs if "anomaly" in item.title.casefold())
    assert anomaly.savings_low_usd is None
    assert anomaly.savings_high_usd is None


def test_export_package_contains_analysis_and_recommendations() -> None:
    frame = pd.DataFrame(
        [
            {
                "billing_month": "2025-01",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": 100.0,
            }
        ]
    )
    anomalies = detect_cost_anomalies(frame)
    recs = build_recommendations(frame, anomalies)
    package = build_export_bundle(frame, anomalies, recs, data_label="SYNTHETIC DEMONSTRATION DATA")
    with ZipFile(BytesIO(package)) as archive:
        names = set(archive.namelist())
        assert {
            "monthly_trend.csv",
            "cost_by_service.csv",
            "anomalies.csv",
            "recommendations.csv",
            "README.txt",
        } <= names
        assert b"SYNTHETIC DEMONSTRATION DATA" in archive.read("README.txt")


def test_export_escapes_spreadsheet_formulas_in_user_supplied_text() -> None:
    frame = pd.DataFrame(
        [
            {
                "billing_month": "2025-01",
                "account": '=HYPERLINK("https://example.invalid")',
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": 100.0,
            }
        ]
    )
    package = build_export_bundle(
        frame, pd.DataFrame(), [], data_label="uploaded demonstration input"
    )
    with ZipFile(BytesIO(package)) as archive:
        assert b"'=HYPERLINK" in archive.read("cost_by_account.csv")
