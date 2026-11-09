"""Generate the checked-in synthetic AWS billing dataset deterministically."""

from __future__ import annotations

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "sample_aws_costs.csv"
SEED = 20261109
SERVICES = {
    "Amazon EC2": (4_800.0, "BoxUsage:t3.large", "Hours"),
    "Amazon RDS": (2_700.0, "InstanceUsage:db.m6i.large", "Hours"),
    "Amazon S3": (700.0, "TimedStorage-ByteHrs", "GB-Mo"),
    "AWS Lambda": (260.0, "Lambda-GB-Second", "GB-Seconds"),
    "Amazon CloudWatch": (420.0, "DataProcessing-Bytes", "GB"),
    "Amazon VPC": (650.0, "NatGateway-Hours", "Hours"),
    "Data Transfer": (900.0, "DataTransfer-Out-Bytes", "GB"),
    "Amazon EBS": (550.0, "VolumeUsage.gp3", "GB-Mo"),
}
ACCOUNTS = {"demo-commerce": 0.72, "demo-shared-services": 0.28}
REGIONS = {"us-east-1": 0.70, "us-west-2": 0.18, "eu-west-1": 0.12}


def month_values() -> list[str]:
    return [f"2025-{month:02d}" for month in range(6, 13)] + [
        f"2026-{month:02d}" for month in range(1, 12)
    ]


def generate_rows() -> list[dict[str, str]]:
    rng = random.Random(SEED)
    rows: list[dict[str, str]] = []
    for month_index, month in enumerate(month_values()):
        month_number = int(month[-2:])
        seasonality = 1.07 if month_number == 12 else 1.0
        trend = 1.0 + month_index * 0.007
        for account, account_weight in ACCOUNTS.items():
            for region, region_weight in REGIONS.items():
                for service, (base, usage_type, unit) in SERVICES.items():
                    noise = rng.uniform(0.97, 1.03)
                    cost = base * account_weight * region_weight * seasonality * trend * noise
                    quantity = cost / 0.12 if unit in {"GB", "GB-Mo"} else cost / 0.08
                    # Deliberately introduced billing spikes for anomaly-rule demonstrations.
                    if month == "2026-04" and account == "demo-commerce" and region == "us-east-1":
                        if service == "Amazon EC2":
                            cost *= 2.05
                            quantity *= 2.05
                        elif service == "Amazon VPC":
                            cost *= 3.7
                            quantity *= 3.7
                    if (
                        month == "2026-02"
                        and account == "demo-commerce"
                        and region == "us-east-1"
                        and service == "Data Transfer"
                    ):
                        cost *= 5.2
                        quantity *= 5.2
                    rows.append(
                        {
                            "billing_month": month,
                            "account_alias": account,
                            "region": region,
                            "service": service,
                            "usage_type": usage_type,
                            "unblended_cost": f"{cost:.2f}",
                            "usage_quantity": f"{quantity:.2f}",
                            "usage_unit": unit,
                            "data_origin": "SYNTHETIC DEMONSTRATION DATA",
                        }
                    )
    return rows


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic billing rows to {OUTPUT}")


if __name__ == "__main__":
    main()
