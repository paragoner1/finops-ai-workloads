#!/usr/bin/env python3
"""
gpu_cost_analyzer.py

Identifies optimization opportunities specific to GPU and AI workloads:
- Low-utilization resources (idle GPU detection)
- Pricing mix opportunities (on-demand spend that could move to Reserved or Spot)
- Workload pattern analysis (training spike detection)
- Cost concentration (Pareto: top resources driving 80% of spend)

Usage:
    python analysis/gpu_cost_analyzer.py [csv_path]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from parse_focus import load_focus_data  # noqa: E402

# Threshold for "low utilization" flag: average daily hours below this
IDLE_THRESHOLD_HOURS = 14
# Threshold for spike detection: day's cost vs trailing 7-day average
SPIKE_MULTIPLIER = 1.5
# Pareto threshold for cost concentration
PARETO_PCT = 0.80


def filter_gpu(df: pd.DataFrame) -> pd.DataFrame:
    """Restrict to GPU/ML workloads."""
    return df[df["ServiceCategory"] == "AI and Machine Learning"].copy()


def utilization_by_resource(df: pd.DataFrame) -> pd.DataFrame:
    """Average daily hours per resource (idle detection)."""
    by_resource = df.groupby("ResourceId").agg(
        ResourceType=("ResourceType", "first"),
        TotalHours=("ConsumedQuantity", "sum"),
        TotalCost=("EffectiveCost", "sum"),
        ActiveDays=("Day", "nunique"),
        PricingCategory=("PricingCategory", "first"),
        CostTeam=("CostTeam", "first"),
    )
    by_resource["AvgHoursPerDay"] = by_resource["TotalHours"] / by_resource["ActiveDays"]
    return by_resource.sort_values("TotalCost", ascending=False)


def detect_idle(df: pd.DataFrame) -> pd.DataFrame:
    """Flag resources running below the idle threshold."""
    util = utilization_by_resource(df)
    idle = util[util["AvgHoursPerDay"] < IDLE_THRESHOLD_HOURS].copy()
    if idle.empty:
        return pd.DataFrame()
    # Estimated waste assumes the resource could either be terminated when idle
    # or right-sized down. Conservative estimate: 30% of current cost.
    idle["EstimatedAnnualWaste"] = idle["TotalCost"] * 12 * 0.30
    return idle.sort_values("EstimatedAnnualWaste", ascending=False)


def pricing_mix(df: pd.DataFrame) -> dict:
    """Spend by pricing category and migration opportunity sizing."""
    by_pricing = df.groupby("PricingCategory").agg(
        EffectiveCost=("EffectiveCost", "sum"),
        ListCost=("ListCost", "sum"),
        Hours=("ConsumedQuantity", "sum"),
    )
    total = by_pricing["EffectiveCost"].sum()
    on_demand_cost = by_pricing.loc["Standard", "EffectiveCost"] if "Standard" in by_pricing.index else 0

    # Migration opportunity (rough sizing using common AWS discount levels)
    # Reserved 1yr no-upfront: ~38% discount on Compute.
    # Spot: ~70% discount, but only suitable for fault-tolerant workloads.
    return {
        "total": total,
        "by_category": by_pricing,
        "on_demand_cost": on_demand_cost,
        "on_demand_pct": on_demand_cost / total * 100 if total else 0,
        "potential_ri_savings": on_demand_cost * 0.38,
        "potential_spot_savings": on_demand_cost * 0.70,
    }


def detect_training_spikes(df: pd.DataFrame) -> pd.DataFrame:
    """Days where cost exceeds trailing 7-day average by SPIKE_MULTIPLIER."""
    daily = df.groupby("Day")["EffectiveCost"].sum().sort_index()
    rolling = daily.rolling(7, min_periods=3).mean()
    spike_days = daily[daily > rolling * SPIKE_MULTIPLIER]
    if spike_days.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Day": spike_days.index,
        "EffectiveCost": spike_days.values,
        "TrailingAvg": rolling.loc[spike_days.index].values,
        "Multiplier": (spike_days.values / rolling.loc[spike_days.index].values),
    })


def cost_concentration(df: pd.DataFrame, pct: float = PARETO_PCT) -> pd.DataFrame:
    """Find the resources that drive `pct` of total cost (Pareto)."""
    by_resource = df.groupby("ResourceId")["EffectiveCost"].sum().sort_values(ascending=False)
    cumulative = by_resource.cumsum() / by_resource.sum()
    # Find first index where cumulative >= pct
    cutoff = cumulative[cumulative >= pct].index[0] if (cumulative >= pct).any() else by_resource.index[-1]
    cutoff_pos = by_resource.index.get_loc(cutoff)
    top = by_resource.iloc[: cutoff_pos + 1]
    return pd.DataFrame({
        "ResourceId": top.index,
        "EffectiveCost": top.values,
        "CumulativePct": cumulative.loc[top.index].values * 100,
    })


def print_report(df: pd.DataFrame) -> None:
    gpu_df = filter_gpu(df)

    print("=" * 64)
    print("GPU Cost Analyzer")
    print("=" * 64)
    print()
    gpu_total = gpu_df["EffectiveCost"].sum()
    overall_total = df["EffectiveCost"].sum()
    print(f"GPU/ML spend:     ${gpu_total:>12,.2f}  ({gpu_total / overall_total * 100:.1f}% of total)")
    print(f"GPU resources:    {gpu_df['ResourceId'].nunique()}")
    print(f"GPU types in use: {', '.join(sorted(gpu_df['ResourceType'].unique()))}")
    print()

    # Idle / low-utilization
    print("-" * 64)
    print(f"Low Utilization Resources (avg < {IDLE_THRESHOLD_HOURS} hrs/day)")
    print("-" * 64)
    idle = detect_idle(gpu_df)
    if idle.empty:
        print("  None detected.")
    else:
        print("  These resources are good candidates for right-sizing or termination.")
        print()
        for resource_id, row in idle.iterrows():
            print(f"  {resource_id} ({row['ResourceType']})")
            print(f"    Team:               {row['CostTeam'] or '(untagged)'}")
            print(f"    Avg hrs/day:        {row['AvgHoursPerDay']:.1f}")
            print(f"    30-day cost:        ${row['TotalCost']:,.2f}")
            print(f"    Annual waste est:   ${row['EstimatedAnnualWaste']:,.0f}")
            print()

    # Pricing mix
    print("-" * 64)
    print("Pricing Mix and Migration Opportunities")
    print("-" * 64)
    pmix = pricing_mix(gpu_df)
    for category, row in pmix["by_category"].iterrows():
        pct = row["EffectiveCost"] / pmix["total"] * 100
        print(f"  {category:12s} ${row['EffectiveCost']:>10,.2f}  ({pct:5.1f}%)  {row['Hours']:>6,.0f} hrs")
    print()
    if pmix["on_demand_cost"] > 0:
        print(f"  On-demand spend: ${pmix['on_demand_cost']:,.2f} ({pmix['on_demand_pct']:.1f}% of GPU)")
        print(f"  If migrated to Reserved Instances (~38% discount): ~${pmix['potential_ri_savings']:,.0f}/30d savings")
        print(f"  If migrated to Spot for fault-tolerant inference (~70%): ~${pmix['potential_spot_savings']:,.0f}/30d savings")
        print(f"  Annualized RI opportunity: ~${pmix['potential_ri_savings'] * 12:,.0f}")
    print()

    # Spikes
    print("-" * 64)
    print("Training Spike Detection")
    print("-" * 64)
    spikes = detect_training_spikes(gpu_df)
    if spikes.empty:
        print("  No training spikes detected (no day exceeds trailing avg by 1.5x).")
    else:
        print("  Days with elevated spend (potential training events):")
        for _, row in spikes.iterrows():
            print(f"  {row['Day']}  ${row['EffectiveCost']:,.2f}  ({row['Multiplier']:.2f}x trailing 7-day avg)")
    print()

    # Pareto concentration
    print("-" * 64)
    print(f"Cost Concentration (resources driving {int(PARETO_PCT * 100)}% of GPU spend)")
    print("-" * 64)
    pareto = cost_concentration(gpu_df)
    for _, row in pareto.iterrows():
        print(f"  {row['ResourceId']:30s} ${row['EffectiveCost']:>10,.2f}  (cumulative {row['CumulativePct']:5.1f}%)")
    print()

    # Recommendations
    print("=" * 64)
    print("Recommended actions (in priority order)")
    print("=" * 64)
    rank = 1
    if not idle.empty:
        top_idle = idle.iloc[0]
        print(f"  {rank}. Right-size or terminate {top_idle.name} "
              f"(avg {top_idle['AvgHoursPerDay']:.1f} hrs/day, ~${top_idle['EstimatedAnnualWaste']:,.0f}/yr exposure).")
        rank += 1
    if pmix["on_demand_cost"] > 0:
        print(f"  {rank}. Convert eligible on-demand inference workloads to Reserved Instances "
              f"(~${pmix['potential_ri_savings'] * 12:,.0f}/yr potential).")
        rank += 1
    if not spikes.empty:
        print(f"  {rank}. Build a capacity planning rhythm for training events. "
              f"Detected {len(spikes)} spike day(s) in the period.")
        rank += 1
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="GPU and AI workload cost analyzer.")
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
