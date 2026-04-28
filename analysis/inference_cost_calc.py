#!/usr/bin/env python3
"""
inference_cost_calc.py

Cost-per-inference framework for AI workloads. Takes GPU instance pricing
plus an assumed inference throughput and produces $/1000 inference unit
economics. Useful for product pricing decisions, board reporting, and the
"should this workload move to a different tier" conversation.

The throughput assumptions below are conservative defaults for transformer
inference workloads (e.g., Whisper-class STT, 7B-class LLM inference).
Override them for your own model and batch size.

Usage:
    python analysis/inference_cost_calc.py [csv_path]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from parse_focus import load_focus_data  # noqa: E402

# Conservative inference throughput baselines (requests per second)
# Real numbers depend on model, batch size, sequence length, and quantization.
# These are reasonable order-of-magnitude defaults for transformer inference
# at modest sequence lengths.
THROUGHPUT_RPS = {
    "g5.xlarge":    25,    # 1x A10G, 24 GB
    "g5.2xlarge":   45,    # 1x A10G, 24 GB, more vCPU headroom
    "g5.4xlarge":   55,    # 1x A10G, 24 GB, more memory
    "p4d.24xlarge": 600,   # 8x A100 40GB, training-class but capable inference at scale
}


def filter_inference(df: pd.DataFrame) -> pd.DataFrame:
    """Restrict to workloads tagged as inference (or untagged GPU as a fallback)."""
    inference_mask = (df["Purpose"] == "inference") | (
        (df["ServiceCategory"] == "AI and Machine Learning") & (df["Purpose"].isna())
    )
    return df[inference_mask].copy()


def per_resource_cost_economics(df: pd.DataFrame) -> pd.DataFrame:
    """For each inference resource, compute cost per 1000 inferences at baseline throughput."""
    rows = []
    by_resource = df.groupby("ResourceId").agg(
        ResourceType=("ResourceType", "first"),
        EffectiveCost=("EffectiveCost", "sum"),
        Hours=("ConsumedQuantity", "sum"),
        CostTeam=("CostTeam", "first"),
        Purpose=("Purpose", "first"),
    )

    for resource_id, row in by_resource.iterrows():
        instance_type = row["ResourceType"]
        rps = THROUGHPUT_RPS.get(instance_type, 0)
        if rps == 0 or row["Hours"] == 0:
            continue
        hourly_cost = row["EffectiveCost"] / row["Hours"]
        # Inferences per hour at baseline RPS
        inferences_per_hour = rps * 3600
        # Cost per 1000 inferences
        cost_per_1k = hourly_cost / inferences_per_hour * 1000
        rows.append({
            "ResourceId": resource_id,
            "InstanceType": instance_type,
            "Team": row["CostTeam"] or "(untagged)",
            "Purpose": row["Purpose"] or "(untagged)",
            "TotalCost": row["EffectiveCost"],
            "TotalHours": row["Hours"],
            "EffectiveHourlyRate": hourly_cost,
            "AssumedRPS": rps,
            "InferencesPerHour": inferences_per_hour,
            "CostPer1k": cost_per_1k,
        })

    return pd.DataFrame(rows).sort_values("TotalCost", ascending=False)


def per_instance_breakeven(throughput_rps_overrides: dict | None = None) -> pd.DataFrame:
    """For each instance type, compute cost per 1000 inferences at on-demand pricing."""
    # On-demand list prices used in the synthetic generator (kept in sync there)
    list_prices = {
        "g5.xlarge":    1.006,
        "g5.2xlarge":   1.212,
        "g5.4xlarge":   1.624,
        "p4d.24xlarge": 32.77,
    }
    overrides = throughput_rps_overrides or {}
    rows = []
    for instance_type, hourly in list_prices.items():
        rps = overrides.get(instance_type, THROUGHPUT_RPS[instance_type])
        inferences_per_hour = rps * 3600
        cost_per_1k = hourly / inferences_per_hour * 1000
        rows.append({
            "InstanceType": instance_type,
            "ListHourly": hourly,
            "AssumedRPS": rps,
            "InferencesPerHour": inferences_per_hour,
            "OnDemandCostPer1k": cost_per_1k,
            "ReservedCostPer1k": cost_per_1k * 0.62,  # ~38% RI discount
            "SpotCostPer1k": cost_per_1k * 0.30,      # ~70% Spot discount
        })
    return pd.DataFrame(rows)


def print_report(df: pd.DataFrame) -> None:
    print("=" * 64)
    print("Cost-Per-Inference Analysis")
    print("=" * 64)
    print()
    print("Throughput assumptions (requests per second):")
    for instance, rps in THROUGHPUT_RPS.items():
        print(f"  {instance:18s} {rps:>5d} RPS  ({rps * 3600:,} inferences/hour)")
    print()
    print("Override these in inference_cost_calc.py for your model + batch size.")
    print()

    inference_df = filter_inference(df)
    if inference_df.empty:
        print("No inference workloads detected in the data.")
        return

    print("-" * 64)
    print("Per-Resource Unit Economics")
    print("-" * 64)
    economics = per_resource_cost_economics(inference_df)
    if economics.empty:
        print("  No matching inference resources to compute economics for.")
    else:
        for _, row in economics.iterrows():
            print(f"  {row['ResourceId']}")
            print(f"    Instance:           {row['InstanceType']}")
            print(f"    Team:               {row['Team']}")
            print(f"    30-day cost:        ${row['TotalCost']:,.2f}  ({row['TotalHours']:,.0f} hrs)")
            print(f"    Effective hourly:   ${row['EffectiveHourlyRate']:.4f}/hr")
            print(f"    Cost per 1k req:    ${row['CostPer1k']:.5f}  (at {row['AssumedRPS']} RPS)")
            print()

    print("-" * 64)
    print("Pricing Tier Comparison (per 1,000 inferences, on-demand list)")
    print("-" * 64)
    breakeven = per_instance_breakeven()
    print(f"  {'Instance':18s} {'On-Demand':>11s} {'Reserved':>11s} {'Spot':>11s}")
    for _, row in breakeven.iterrows():
        print(f"  {row['InstanceType']:18s} ${row['OnDemandCostPer1k']:>10.5f} ${row['ReservedCostPer1k']:>10.5f} ${row['SpotCostPer1k']:>10.5f}")
    print()

    print("-" * 64)
    print("Volume Sensitivity: Monthly Cost at Different Inference Volumes")
    print("-" * 64)
    print("  (using g5.xlarge on-demand as baseline)")
    print()
    print(f"  {'Inferences/month':>20s} {'Monthly cost':>15s}")
    g5_xlarge_per_1k = breakeven[breakeven["InstanceType"] == "g5.xlarge"]["OnDemandCostPer1k"].iloc[0]
    for volume in [1_000_000, 10_000_000, 100_000_000, 1_000_000_000]:
        cost = volume / 1000 * g5_xlarge_per_1k
        print(f"  {volume:>20,} ${cost:>14,.2f}")
    print()

    print("=" * 64)
    print("How to use this output")
    print("=" * 64)
    print("  1. Compare actual per-inference cost to your product's gross margin target.")
    print("  2. If the workload is fault-tolerant, run the Spot column - savings are significant.")
    print("  3. For predictable steady-state inference, the Reserved column maps to a 1-year RI commitment.")
    print("  4. Override the throughput assumptions for your specific model. Real RPS varies by 5-10x")
    print("     based on batch size, sequence length, and quantization.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Cost-per-inference unit economics calculator.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="data/ai-workload-synthetic.csv",
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
