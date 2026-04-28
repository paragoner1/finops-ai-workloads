#!/usr/bin/env python3
"""
tag_compliance.py

Identifies untagged spend, partially tagged resources, and tag
inconsistency. Outputs a remediation list ranked by spend impact.

This is usually the highest-impact first move on any new FinOps
program: you can't optimize what you can't attribute.

Usage:
    python analysis/tag_compliance.py [csv_path]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Make sibling parse_focus importable when running as a script
sys.path.insert(0, str(Path(__file__).parent))
from parse_focus import load_focus_data, summary_totals  # noqa: E402

# Tags considered required for full compliance
REQUIRED_TAGS = ["cost-team", "env"]


def find_untagged_spend(df: pd.DataFrame) -> pd.DataFrame:
    """Resources with zero tags."""
    untagged = df[~df["IsTagged"]]
    if untagged.empty:
        return pd.DataFrame()

    return (
        untagged.groupby("ResourceId")
        .agg(
            EffectiveCost=("EffectiveCost", "sum"),
            ResourceType=("ResourceType", "first"),
            ServiceCategory=("ServiceCategory", "first"),
            Days=("Day", "nunique"),
        )
        .sort_values("EffectiveCost", ascending=False)
    )


def find_partially_tagged(df: pd.DataFrame) -> pd.DataFrame:
    """Resources missing one or more required tags but tagged with something."""
    rows = []
    for resource_id, group in df.groupby("ResourceId"):
        # Pull the first row's tags as representative (resource-level tags don't change)
        tags = group["TagsParsed"].iloc[0]
        if not tags:
            continue  # Fully untagged, handled separately

        missing = [t for t in REQUIRED_TAGS if t not in tags]
        if missing:
            rows.append({
                "ResourceId": resource_id,
                "ResourceType": group["ResourceType"].iloc[0],
                "EffectiveCost": group["EffectiveCost"].sum(),
                "MissingTags": ", ".join(missing),
                "PresentTags": ", ".join(sorted(tags.keys())),
            })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("EffectiveCost", ascending=False)


def find_inconsistent_tags(df: pd.DataFrame) -> pd.DataFrame:
    """Resources where tag values change across line items (data quality issue)."""
    inconsistent = []
    for resource_id, group in df.groupby("ResourceId"):
        for tag_key in REQUIRED_TAGS:
            values = group["TagsParsed"].apply(lambda t: t.get(tag_key))
            unique_vals = values.dropna().unique()
            if len(unique_vals) > 1:
                inconsistent.append({
                    "ResourceId": resource_id,
                    "TagKey": tag_key,
                    "Values": ", ".join(map(str, unique_vals)),
                    "EffectiveCost": group["EffectiveCost"].sum(),
                })

    if not inconsistent:
        return pd.DataFrame()
    return pd.DataFrame(inconsistent).sort_values("EffectiveCost", ascending=False)


def compliance_score(df: pd.DataFrame) -> dict:
    """Top-line compliance metrics."""
    total = df["EffectiveCost"].sum()
    untagged_cost = df[~df["IsTagged"]]["EffectiveCost"].sum()
    fully_tagged_mask = df["TagsParsed"].apply(
        lambda t: all(k in t for k in REQUIRED_TAGS)
    )
    fully_tagged_cost = df[fully_tagged_mask]["EffectiveCost"].sum()
    partial_cost = total - untagged_cost - fully_tagged_cost

    return {
        "total": total,
        "fully_tagged": fully_tagged_cost,
        "fully_tagged_pct": fully_tagged_cost / total * 100,
        "partial": partial_cost,
        "partial_pct": partial_cost / total * 100,
        "untagged": untagged_cost,
        "untagged_pct": untagged_cost / total * 100,
    }


def print_report(df: pd.DataFrame) -> None:
    """Render the tag compliance report."""
    score = compliance_score(df)

    print("=" * 64)
    print("Tag Compliance Report")
    print("=" * 64)
    print()
    print(f"Required tags: {', '.join(REQUIRED_TAGS)}")
    print()

    print("Compliance summary:")
    print(f"  Fully tagged:  ${score['fully_tagged']:>10,.2f}  ({score['fully_tagged_pct']:5.1f}%)")
    print(f"  Partial:       ${score['partial']:>10,.2f}  ({score['partial_pct']:5.1f}%)")
    print(f"  Untagged:      ${score['untagged']:>10,.2f}  ({score['untagged_pct']:5.1f}%)")
    print(f"  Total:         ${score['total']:>10,.2f}")
    print()

    untagged = find_untagged_spend(df)
    if not untagged.empty:
        print("-" * 64)
        print(f"Untagged Resources (${untagged['EffectiveCost'].sum():,.2f} total)")
        print("-" * 64)
        print("Remediation: assign cost-team and env tags. Highest impact first.")
        print()
        for resource_id, row in untagged.iterrows():
            print(f"  {resource_id}")
            print(f"    Type:    {row['ResourceType']}")
            print(f"    Service: {row['ServiceCategory']}")
            print(f"    Cost:    ${row['EffectiveCost']:,.2f}  over {row['Days']} days")
            print()

    partial = find_partially_tagged(df)
    if not partial.empty:
        print("-" * 64)
        print(f"Partially Tagged Resources (${partial['EffectiveCost'].sum():,.2f} total)")
        print("-" * 64)
        for _, row in partial.iterrows():
            print(f"  {row['ResourceId']}")
            print(f"    Cost:         ${row['EffectiveCost']:,.2f}")
            print(f"    Present:      {row['PresentTags']}")
            print(f"    Missing:      {row['MissingTags']}")
            print()
    else:
        print("No partially tagged resources detected.")
        print()

    inconsistent = find_inconsistent_tags(df)
    if not inconsistent.empty:
        print("-" * 64)
        print("Tag Value Inconsistency (data quality issue)")
        print("-" * 64)
        for _, row in inconsistent.iterrows():
            print(f"  {row['ResourceId']} / {row['TagKey']}: {row['Values']}  (${row['EffectiveCost']:,.2f})")
        print()
    else:
        print("No tag value inconsistencies detected.")
        print()

    print("=" * 64)
    print("Recommended actions")
    print("=" * 64)
    if not untagged.empty:
        top = untagged.iloc[0]
        print(f"  1. Tag {top.name} immediately (${top['EffectiveCost']:,.2f}/30 days, "
              f"~${top['EffectiveCost'] * 12:,.0f}/yr exposure).")
    if not partial.empty:
        top_partial = partial.iloc[0]
        print(f"  2. Backfill missing tags on {top_partial['ResourceId']} ({top_partial['MissingTags']}).")
    if score["fully_tagged_pct"] < 95:
        gap = 95 - score["fully_tagged_pct"]
        print(f"  3. Drive fully-tagged coverage from {score['fully_tagged_pct']:.1f}% "
              f"to 95% (gap: {gap:.1f} points).")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tag compliance analysis for FOCUS billing data.")
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

    print_report(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
