#!/usr/bin/env python3
"""
parse_focus.py

Loads a FOCUS-formatted CSV, validates the schema, parses tags and dates,
and produces a per-day, per-service, per-team cost summary. The base layer
that the other analysis scripts import from.

Usage:
    python analysis/parse_focus.py [csv_path]

If no path is given, defaults to data/ai-workload-synthetic.csv.

The script is also importable. Other analysis modules call:
    from analysis.parse_focus import load_focus_data, summary_by_team, ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# FOCUS v1.0 required columns we depend on. Subset of the full spec.
REQUIRED_FOCUS_COLUMNS = [
    "BilledCost",
    "BillingCurrency",
    "ChargeCategory",
    "ChargePeriodStart",
    "ChargePeriodEnd",
    "ConsumedQuantity",
    "ConsumedUnit",
    "EffectiveCost",
    "ListCost",
    "ListUnitPrice",
    "PricingCategory",
    "ProviderName",
    "RegionId",
    "ResourceId",
    "ResourceType",
    "ServiceCategory",
    "ServiceName",
    "Tags",
]


def load_focus_data(csv_path: str | Path) -> pd.DataFrame:
    """Load a FOCUS CSV, validate schema, parse tags and dates."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    validate_schema(df)
    df = parse_tags(df)
    df = parse_dates(df)
    return df


def validate_schema(df: pd.DataFrame) -> None:
    """Confirm required FOCUS columns are present. Raise if not."""
    missing = [col for col in REQUIRED_FOCUS_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Input is not FOCUS-compliant. Missing required columns: {missing}"
        )


def parse_tags(df: pd.DataFrame) -> pd.DataFrame:
    """Parse the Tags JSON string into a dict. Empty becomes {}."""
    def parse_one(value):
        if pd.isna(value) or value == "":
            return {}
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    df = df.copy()
    df["TagsParsed"] = df["Tags"].apply(parse_one)
    df["CostTeam"] = df["TagsParsed"].apply(lambda t: t.get("cost-team"))
    df["Env"] = df["TagsParsed"].apply(lambda t: t.get("env"))
    df["Purpose"] = df["TagsParsed"].apply(lambda t: t.get("purpose"))
    df["IsTagged"] = df["TagsParsed"].apply(lambda t: bool(t))
    return df


def parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert ChargePeriod columns to datetime."""
    df = df.copy()
    df["ChargePeriodStart"] = pd.to_datetime(df["ChargePeriodStart"], utc=True)
    df["ChargePeriodEnd"] = pd.to_datetime(df["ChargePeriodEnd"], utc=True)
    df["Day"] = df["ChargePeriodStart"].dt.date
    return df


def summary_totals(df: pd.DataFrame) -> dict:
    """Return top-line totals."""
    total_effective = df["EffectiveCost"].sum()
    total_list = df["ListCost"].sum()
    discount = total_list - total_effective
    discount_pct = (discount / total_list * 100) if total_list else 0.0
    return {
        "total_effective": total_effective,
        "total_list": total_list,
        "discount": discount,
        "discount_pct": discount_pct,
        "record_count": len(df),
        "resource_count": df["ResourceId"].nunique(),
        "period_start": df["ChargePeriodStart"].min(),
        "period_end": df["ChargePeriodEnd"].max(),
    }


def summary_by_service(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate cost by ServiceCategory."""
    return (
        df.groupby("ServiceCategory")
        .agg(
            EffectiveCost=("EffectiveCost", "sum"),
            ListCost=("ListCost", "sum"),
            ResourceCount=("ResourceId", "nunique"),
        )
        .sort_values("EffectiveCost", ascending=False)
    )


def summary_by_resource_type(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate cost by ResourceType (instance type)."""
    return (
        df.groupby("ResourceType")
        .agg(
            EffectiveCost=("EffectiveCost", "sum"),
            Hours=("ConsumedQuantity", "sum"),
            ResourceCount=("ResourceId", "nunique"),
        )
        .sort_values("EffectiveCost", ascending=False)
    )


def summary_by_team(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate cost by cost-team tag. Untagged grouped together."""
    df_copy = df.copy()
    df_copy["TeamLabel"] = df_copy["CostTeam"].fillna("(untagged)")
    return (
        df_copy.groupby("TeamLabel")
        .agg(
            EffectiveCost=("EffectiveCost", "sum"),
            ResourceCount=("ResourceId", "nunique"),
        )
        .sort_values("EffectiveCost", ascending=False)
    )


def summary_by_pricing(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate cost by pricing category (Standard/Reserved/Spot)."""
    return (
        df.groupby("PricingCategory")
        .agg(
            EffectiveCost=("EffectiveCost", "sum"),
            ListCost=("ListCost", "sum"),
            Hours=("ConsumedQuantity", "sum"),
        )
        .sort_values("EffectiveCost", ascending=False)
    )


def summary_by_day(df: pd.DataFrame) -> pd.DataFrame:
    """Daily cost trend."""
    return (
        df.groupby("Day")
        .agg(EffectiveCost=("EffectiveCost", "sum"))
        .sort_index()
    )


def print_summary(df: pd.DataFrame) -> None:
    """Render a CLI-friendly cost summary."""
    totals = summary_totals(df)

    print("=" * 64)
    print("FOCUS Cost Summary")
    print("=" * 64)
    print()
    print(f"Period:    {totals['period_start'].date()} to {totals['period_end'].date()}")
    print(f"Records:   {totals['record_count']:,}")
    print(f"Resources: {totals['resource_count']:,}")
    print()
    print(f"Total effective cost:  ${totals['total_effective']:>12,.2f}")
    print(f"Total list cost:       ${totals['total_list']:>12,.2f}")
    print(f"Discount captured:     ${totals['discount']:>12,.2f}  ({totals['discount_pct']:.1f}%)")
    print()

    print("-" * 64)
    print("By Service Category")
    print("-" * 64)
    svc = summary_by_service(df)
    for category, row in svc.iterrows():
        pct = row["EffectiveCost"] / totals["total_effective"] * 100
        print(f"  {category:32s} ${row['EffectiveCost']:>10,.2f}  ({pct:5.1f}%)")
    print()

    print("-" * 64)
    print("By Resource Type")
    print("-" * 64)
    res = summary_by_resource_type(df)
    for rtype, row in res.iterrows():
        print(f"  {rtype:32s} ${row['EffectiveCost']:>10,.2f}  ({row['Hours']:,.0f} hrs)")
    print()

    print("-" * 64)
    print("By Team (cost-team tag)")
    print("-" * 64)
    team = summary_by_team(df)
    for label, row in team.iterrows():
        pct = row["EffectiveCost"] / totals["total_effective"] * 100
        print(f"  {label:32s} ${row['EffectiveCost']:>10,.2f}  ({pct:5.1f}%)")
    print()

    print("-" * 64)
    print("By Pricing Category")
    print("-" * 64)
    pricing = summary_by_pricing(df)
    for category, row in pricing.iterrows():
        save = row["ListCost"] - row["EffectiveCost"]
        save_pct = (save / row["ListCost"] * 100) if row["ListCost"] else 0
        print(f"  {category:32s} ${row['EffectiveCost']:>10,.2f}  (saved ${save:,.2f}, {save_pct:.1f}%)")
    print()

    print("-" * 64)
    print("Daily Cost Trend (last 7 days shown)")
    print("-" * 64)
    daily = summary_by_day(df).tail(7)
    for day, row in daily.iterrows():
        bar_len = int(row["EffectiveCost"] / daily["EffectiveCost"].max() * 30)
        bar = "█" * bar_len
        print(f"  {day}  ${row['EffectiveCost']:>8,.2f}  {bar}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="FOCUS billing data parser and summary.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="data/ai-workload-synthetic.csv",
        help="Path to FOCUS-formatted CSV (default: data/ai-workload-synthetic.csv)",
    )
    args = parser.parse_args()

    try:
        df = load_focus_data(args.csv_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print_summary(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
