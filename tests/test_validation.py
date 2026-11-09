from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from aws_cost_dashboard.schemas import read_billing_csv, validate_billing_data


def test_normalized_csv_schema_is_validated_and_sorted() -> None:
    raw = pd.DataFrame(
        [
            {
                "billing_month": "2025-02",
                "account_alias": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": "25.50",
            },
            {
                "billing_month": "2025-01",
                "account_alias": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "unblended_cost": "20",
            },
        ]
    )
    result = validate_billing_data(raw)
    assert result["billing_month"].tolist() == ["2025-01", "2025-02"]
    assert result["unblended_cost"].tolist() == [20.0, 25.5]


def test_aws_cur_header_aliases_and_account_masking() -> None:
    raw = pd.DataFrame(
        [
            {
                "line_item_usage_start_date": "2025-06-12T00:00:00Z",
                "line_item_usage_account_id": "123456789012",
                "product_region_code": "us-east-1",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "100.00",
                "line_item_usage_amount": "20",
                "pricing_unit": "Hours",
                "line_item_usage_type": "BoxUsage:t3.large",
            }
        ]
    )
    row = validate_billing_data(raw).iloc[0]
    assert row["billing_month"] == "2025-06"
    assert row["account"] == "AWS account ••••9012"
    assert row["service"] == "Amazon EC2"


def test_missing_columns_have_actionable_error() -> None:
    with pytest.raises(ValueError, match="Missing required billing columns"):
        validate_billing_data(pd.DataFrame({"service": ["Amazon EC2"]}))


def test_negative_cost_adjustment_is_allowed_but_invalid_month_is_rejected() -> None:
    valid = pd.DataFrame(
        [
            {
                "month": "2025-01",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon S3",
                "cost": -5.0,
            }
        ]
    )
    assert validate_billing_data(valid).iloc[0]["unblended_cost"] == -5.0
    invalid = valid.assign(month="not-a-month")
    with pytest.raises(ValueError, match="failed validation"):
        validate_billing_data(invalid)


def test_optional_currency_must_be_usd() -> None:
    raw = pd.DataFrame(
        [
            {
                "month": "2025-01",
                "account": "demo",
                "region": "us-east-1",
                "service": "Amazon EC2",
                "cost": 10.0,
                "currency_code": "USD",
            }
        ]
    )
    assert validate_billing_data(raw).iloc[0]["currency"] == "USD"
    raw.loc[0, "currency_code"] = "EUR"
    with pytest.raises(ValueError, match="currency.*USD"):
        validate_billing_data(raw)


def test_mixed_currency_file_is_rejected() -> None:
    raw = pd.DataFrame(
        [
            {
                "month": "2025-01",
                "account": "a",
                "region": "us-east-1",
                "service": "S3",
                "cost": 10,
                "currency": "USD",
            },
            {
                "month": "2025-01",
                "account": "b",
                "region": "eu-west-1",
                "service": "S3",
                "cost": 10,
                "currency": "EUR",
            },
        ]
    )
    with pytest.raises(ValueError, match="currency.*USD"):
        validate_billing_data(raw)


def test_malformed_csv_has_actionable_error() -> None:
    malformed = BytesIO(b"a,b\n1,2\n3,4,5,6\n")
    with pytest.raises(ValueError, match="Could not read this CSV"):
        read_billing_csv(malformed)


def test_empty_upload_and_oversized_record_set_are_rejected() -> None:
    with pytest.raises(ValueError, match="contains no billing rows"):
        validate_billing_data(pd.DataFrame())
    oversized = pd.DataFrame(
        {
            "billing_month": ["2025-01"] * 500_001,
            "account": ["demo"] * 500_001,
            "region": ["us-east-1"] * 500_001,
            "service": ["S3"] * 500_001,
            "unblended_cost": [1] * 500_001,
        }
    )
    with pytest.raises(ValueError, match="more than 500,000"):
        validate_billing_data(oversized)
