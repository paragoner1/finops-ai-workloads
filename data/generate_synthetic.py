#!/usr/bin/env python3
"""
Synthetic FOCUS-formatted cost data generator for finops-ai-workloads.

Generates 30 days of daily-granularity AI/GPU workload billing data with
patterns engineered to demonstrate common FinOps optimization signals:

- Two engineering teams (team-a heavy, team-b light) tagged via cost-team
- One untagged "research" workload (~15% of GPU spend)
- Reserved Instance utilization patterns
- 80% on-demand / 20% spot mix
- Weekend inference dropoff
- Week-three training spike
- Variable idle pattern for the research workload

Output: ai-workload-synthetic.csv (FOCUS v1.0 schema, subset of columns)

Run: python generate_synthetic.py
"""
import csv
import json
import os
import random
from datetime import datetime, timedelta

# Reproducibility
random.seed(2026)

# Configuration
START_DATE = datetime(2026, 4, 1)
DAYS = 30
PROVIDER = "AWS"
PUBLISHER = "AWS"
INVOICE_ISSUER = "AWS"
BILLING_ACCOUNT_ID = "111122223333"
BILLING_ACCOUNT_NAME = "ml-platform-prod"
CURRENCY = "USD"
REGION_ID = "us-east-1"
REGION_NAME = "US East (N. Virginia)"

# Resource catalog
# (instance type -> on-demand hourly price, gpu flag, vcpu count, gpu count)
INSTANCES = {
    "g5.xlarge":    {"on_demand": 1.006,  "gpu": True,  "vcpu": 4,  "gpus": 1},
    "g5.2xlarge":   {"on_demand": 1.212,  "gpu": True,  "vcpu": 8,  "gpus": 1},
    "g5.4xlarge":   {"on_demand": 1.624,  "gpu": True,  "vcpu": 16, "gpus": 1},
    "p4d.24xlarge": {"on_demand": 32.77,  "gpu": True,  "vcpu": 96, "gpus": 8},
    "m5.large":     {"on_demand": 0.096,  "gpu": False, "vcpu": 2,  "gpus": 0},
    "m5.xlarge":    {"on_demand": 0.192,  "gpu": False, "vcpu": 4,  "gpus": 0},
}

# Workloads with engineered patterns
WORKLOADS = [
    # Team A - heavy users, training + inference
    {
        "resource_id": "i-team-a-train-001",
        "instance": "p4d.24xlarge",
        "team": "team-a",
        "env": "ml",
        "purpose": "training",
        "hours_baseline": 12,
        "pricing": "Reserved",
    },
    {
        "resource_id": "i-team-a-inf-001",
        "instance": "g5.2xlarge",
        "team": "team-a",
        "env": "ml",
        "purpose": "inference",
        "hours_baseline": 24,
        "pricing": "Standard",
    },
    {
        "resource_id": "i-team-a-inf-002",
        "instance": "g5.xlarge",
        "team": "team-a",
        "env": "ml",
        "purpose": "inference",
        "hours_baseline": 24,
        "pricing": "Standard",
    },
    # Team B - lighter, mostly inference
    {
        "resource_id": "i-team-b-inf-001",
        "instance": "g5.xlarge",
        "team": "team-b",
        "env": "ml",
        "purpose": "inference",
        "hours_baseline": 14,
        "pricing": "Standard",
    },
    {
        "resource_id": "i-team-b-inf-002",
        "instance": "g5.xlarge",
        "team": "team-b",
        "env": "ml",
        "purpose": "inference",
        "hours_baseline": 8,
        "pricing": "Spot",
    },
    # Untagged research workload - the easy FinOps win
    {
        "resource_id": "i-research-gpu-001",
        "instance": "g5.4xlarge",
        "team": None,
        "env": None,
        "purpose": "research",
        "hours_baseline": 18,
        "pricing": "Standard",
    },
    # CPU support infrastructure
    {
        "resource_id": "i-mgmt-001",
        "instance": "m5.large",
        "team": "team-a",
        "env": "production",
        "purpose": "management",
        "hours_baseline": 24,
        "pricing": "Reserved",
    },
    {
        "resource_id": "i-mgmt-002",
        "instance": "m5.xlarge",
        "team": "team-b",
        "env": "production",
        "purpose": "management",
        "hours_baseline": 24,
        "pricing": "Reserved",
    },
]

# FOCUS v1.0 column subset
FOCUS_COLUMNS = [
    "BilledCost",
    "BillingAccountId",
    "BillingAccountName",
    "BillingCurrency",
    "BillingPeriodStart",
    "BillingPeriodEnd",
    "ChargeCategory",
    "ChargeDescription",
    "ChargePeriodStart",
    "ChargePeriodEnd",
    "ConsumedQuantity",
    "ConsumedUnit",
    "EffectiveCost",
    "InvoiceIssuerName",
    "ListCost",
    "ListUnitPrice",
    "PricingCategory",
    "PricingQuantity",
    "PricingUnit",
    "ProviderName",
    "PublisherName",
    "RegionId",
    "RegionName",
    "ResourceId",
    "ResourceName",
    "ResourceType",
    "ServiceCategory",
    "ServiceName",
    "SkuId",
    "SubAccountId",
    "SubAccountName",
    "Tags",
]


def get_pricing_multiplier(pricing_category):
    """Discount factor relative to on-demand list price."""
    return {
        "Standard": 1.00,   # On-demand
        "Reserved": 0.62,   # Standard 1-yr no-upfront RI
        "Spot": 0.30,       # ~70% spot discount
    }[pricing_category]


def get_daily_hours(workload, day_index):
    """Compute hours used on a given day with engineered patterns."""
    base = workload["hours_baseline"]
    is_weekend = (day_index % 7) in (5, 6)
    is_week_three = 14 <= day_index < 21

    # Week-three training spike
    if workload["purpose"] == "training" and is_week_three:
        return min(24.0, base * 2.0)

    # Weekend dropoff for inference
    if is_weekend and workload["purpose"] == "inference":
        return max(0.0, base * 0.4 + random.uniform(-1.0, 1.0))

    # Research workload variable idle
    if workload["purpose"] == "research":
        if random.random() < 0.15:
            return max(0.0, base * 0.1 + random.uniform(-0.5, 0.5))
        return max(0.0, base + random.uniform(-2.0, 4.0))

    # Default: small daily variance
    return max(0.0, base + random.uniform(-1.5, 1.5))


def build_tags(workload):
    """Construct the Tags JSON string. None for untagged workloads."""
    tags = {}
    if workload["team"]:
        tags["cost-team"] = workload["team"]
    if workload["env"]:
        tags["env"] = workload["env"]
    if workload["purpose"] and workload["team"]:
        tags["purpose"] = workload["purpose"]
    return json.dumps(tags) if tags else ""


def generate_records():
    rows = []
    period_start = START_DATE
    period_end = START_DATE + timedelta(days=DAYS)
    billing_period_start = period_start.strftime("%Y-%m-%dT00:00:00Z")
    billing_period_end = period_end.strftime("%Y-%m-%dT00:00:00Z")

    for day_index in range(DAYS):
        day_start = START_DATE + timedelta(days=day_index)
        day_end = day_start + timedelta(days=1)
        charge_period_start = day_start.strftime("%Y-%m-%dT00:00:00Z")
        charge_period_end = day_end.strftime("%Y-%m-%dT00:00:00Z")

        for workload in WORKLOADS:
            instance_type = workload["instance"]
            instance_meta = INSTANCES[instance_type]
            hours = get_daily_hours(workload, day_index)
            if hours <= 0:
                continue

            list_unit_price = instance_meta["on_demand"]
            pricing_multiplier = get_pricing_multiplier(workload["pricing"])
            list_cost = round(list_unit_price * hours, 4)
            effective_cost = round(list_cost * pricing_multiplier, 4)
            service_category = "AI and Machine Learning" if instance_meta["gpu"] else "Compute"

            row = {
                "BilledCost": effective_cost,
                "BillingAccountId": BILLING_ACCOUNT_ID,
                "BillingAccountName": BILLING_ACCOUNT_NAME,
                "BillingCurrency": CURRENCY,
                "BillingPeriodStart": billing_period_start,
                "BillingPeriodEnd": billing_period_end,
                "ChargeCategory": "Usage",
                "ChargeDescription": f"{instance_type} {workload['pricing']} compute",
                "ChargePeriodStart": charge_period_start,
                "ChargePeriodEnd": charge_period_end,
                "ConsumedQuantity": round(hours, 2),
                "ConsumedUnit": "Hours",
                "EffectiveCost": effective_cost,
                "InvoiceIssuerName": INVOICE_ISSUER,
                "ListCost": list_cost,
                "ListUnitPrice": list_unit_price,
                "PricingCategory": workload["pricing"],
                "PricingQuantity": round(hours, 2),
                "PricingUnit": "Hours",
                "ProviderName": PROVIDER,
                "PublisherName": PUBLISHER,
                "RegionId": REGION_ID,
                "RegionName": REGION_NAME,
                "ResourceId": workload["resource_id"],
                "ResourceName": workload["resource_id"],
                "ResourceType": instance_type,
                "ServiceCategory": service_category,
                "ServiceName": "Amazon Elastic Compute Cloud",
                "SkuId": f"{instance_type}-{workload['pricing'].lower()}",
                "SubAccountId": "",
                "SubAccountName": "",
                "Tags": build_tags(workload),
            }
            rows.append(row)

    return rows


def main():
    rows = generate_records()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "ai-workload-synthetic.csv")

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FOCUS_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    total_effective = sum(r["EffectiveCost"] for r in rows)
    total_list = sum(r["ListCost"] for r in rows)
    discount = total_list - total_effective
    pct = (discount / total_list * 100) if total_list else 0

    untagged_cost = sum(r["EffectiveCost"] for r in rows if not r["Tags"])
    gpu_cost = sum(r["EffectiveCost"] for r in rows if r["ServiceCategory"] == "AI and Machine Learning")

    print(f"Generated {len(rows)} records across {DAYS} days.")
    print(f"Total effective cost:   ${total_effective:>12,.2f}")
    print(f"Total list cost:        ${total_list:>12,.2f}")
    print(f"Discount captured:      ${discount:>12,.2f}  ({pct:.1f}%)")
    print(f"GPU/ML spend:           ${gpu_cost:>12,.2f}  ({gpu_cost / total_effective * 100:.1f}% of total)")
    print(f"Untagged spend:         ${untagged_cost:>12,.2f}  ({untagged_cost / total_effective * 100:.1f}% of total)")
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
