# Sample Output

What you'll see when you run the four analysis scripts against the synthetic dataset shipped in `/data`. Run them yourself with:

```bash
python analysis/parse_focus.py
python analysis/tag_compliance.py
python analysis/gpu_cost_analyzer.py
python analysis/inference_cost_calc.py
```

The dataset is 30 days, 8 resources, 240 records, $11,786 effective cost.

---

## 1. parse_focus.py: cost summary

The base layer. Loads the FOCUS-formatted CSV, validates schema, parses tags, and produces a multi-dimensional cost summary.

```
================================================================
FOCUS Cost Summary
================================================================

Period:    2026-04-01 to 2026-05-01
Records:   240
Resources: 8

Total effective cost:  $   11,786.72
Total list cost:       $   17,554.26
Discount captured:     $    5,767.53  (32.9%)

----------------------------------------------------------------
By Service Category
----------------------------------------------------------------
  AI and Machine Learning          $ 11,656.92  ( 98.9%)
  Compute                          $    129.80  (  1.1%)

----------------------------------------------------------------
By Resource Type
----------------------------------------------------------------
  p4d.24xlarge                     $  9,045.11  (445 hrs)
  g5.xlarge                        $  1,022.38  (1,160 hrs)
  g5.4xlarge                       $    863.78  (532 hrs)
  g5.2xlarge                       $    725.66  (599 hrs)
  m5.xlarge                        $     86.06  (723 hrs)
  m5.large                         $     43.75  (735 hrs)

----------------------------------------------------------------
By Team (cost-team tag)
----------------------------------------------------------------
  team-a                           $ 10,420.94  ( 88.4%)
  (untagged)                       $    863.78  (  7.3%)
  team-b                           $    502.00  (  4.3%)

----------------------------------------------------------------
By Pricing Category
----------------------------------------------------------------
  Reserved                         $  9,174.91  (saved $5,623.33, 38.0%)
  Standard                         $  2,550.01  (saved $0.00, 0.0%)
  Spot                             $     61.80  (saved $144.20, 70.0%)
```

**What this tells you:** GPU/ML spend dominates at 98.9%. Team A drives 88% of cost. 7.3% is untagged (the easy first remediation target). Reserved Instances captured $5,623 of the $5,767 total discount; Spot captured $144.

---

## 2. tag_compliance.py: untagged spend identification

The most direct value-add for any new FinOps program. Surfaces untagged and partially tagged resources, ranked by dollar impact.

```
================================================================
Tag Compliance Report
================================================================

Required tags: cost-team, env

Compliance summary:
  Fully tagged:  $ 10,922.95  ( 92.7%)
  Partial:       $     -0.00  ( -0.0%)
  Untagged:      $    863.78  (  7.3%)
  Total:         $ 11,786.72

----------------------------------------------------------------
Untagged Resources ($863.78 total)
----------------------------------------------------------------
Remediation: assign cost-team and env tags. Highest impact first.

  i-research-gpu-001
    Type:    g5.4xlarge
    Service: AI and Machine Learning
    Cost:    $863.78  over 30 days

================================================================
Recommended actions
================================================================
  1. Tag i-research-gpu-001 immediately ($863.78/30 days, ~$10,365/yr exposure).
  3. Drive fully-tagged coverage from 92.7% to 95% (gap: 2.3 points).
```

**What this tells you:** A single untagged research workload (`i-research-gpu-001`) accounts for the entire 7.3% untagged bucket. Annualized exposure is roughly $10,365. The remediation is a single tagging operation. This is exactly the pattern that shows up in real cloud bills: one or two specific resources owning the bulk of untagged spend.

---

## 3. gpu_cost_analyzer.py: optimization opportunities

Looks across the GPU workload subset for idle resources, pricing-tier migration opportunities, training spikes, and cost concentration.

```
================================================================
GPU Cost Analyzer
================================================================

GPU/ML spend:     $   11,656.92  (98.9% of total)
GPU resources:    6
GPU types in use: g5.2xlarge, g5.4xlarge, g5.xlarge, p4d.24xlarge

----------------------------------------------------------------
Low Utilization Resources (avg < 14 hrs/day)
----------------------------------------------------------------
  i-team-b-inf-001 (g5.xlarge)
    Team:               team-b
    Avg hrs/day:        11.7
    30-day cost:        $354.15
    Annual waste est:   $1,275

  i-team-b-inf-002 (g5.xlarge)
    Team:               team-b
    Avg hrs/day:        6.8
    30-day cost:        $61.80
    Annual waste est:   $222

----------------------------------------------------------------
Pricing Mix and Migration Opportunities
----------------------------------------------------------------
  Reserved     $  9,045.11  ( 77.6%)     445 hrs
  Spot         $     61.80  (  0.5%)     205 hrs
  Standard     $  2,550.01  ( 21.9%)   2,086 hrs

  On-demand spend: $2,550.01 (21.9% of GPU)
  If migrated to Reserved Instances (~38% discount): ~$969/30d savings
  If migrated to Spot for fault-tolerant inference (~70%): ~$1,785/30d savings
  Annualized RI opportunity: ~$11,628

----------------------------------------------------------------
Training Spike Detection
----------------------------------------------------------------
  Days with elevated spend (potential training events):
  2026-04-15  $590.64  (1.62x trailing 7-day avg)

----------------------------------------------------------------
Cost Concentration (resources driving 80% of GPU spend)
----------------------------------------------------------------
  i-team-a-train-001             $  9,045.11  (cumulative  77.6%)
  i-research-gpu-001             $    863.78  (cumulative  85.0%)

================================================================
Recommended actions (in priority order)
================================================================
  1. Right-size or terminate i-team-b-inf-001 (avg 11.7 hrs/day, ~$1,275/yr exposure).
  2. Convert eligible on-demand inference workloads to Reserved Instances (~$11,628/yr potential).
  3. Build a capacity planning rhythm for training events. Detected 1 spike day(s) in the period.
```

**What this tells you:** Annualized Reserved Instance opportunity is roughly $11,628 across the on-demand inference workloads. Two Team B inference resources are running below the 14-hour-per-day threshold and warrant a right-sizing conversation. One training spike was detected on April 15 (the engineered week-three event in the synthetic data, which validates the spike detector works). Two resources drive 85% of GPU cost, which means the optimization conversation is concentrated, not diffuse.

---

## 4. inference_cost_calc.py: unit economics

Cost-per-1000-inferences for each inference workload, plus pricing tier comparison and volume sensitivity.

```
================================================================
Cost-Per-Inference Analysis
================================================================

Throughput assumptions (requests per second):
  g5.xlarge             25 RPS  (90,000 inferences/hour)
  g5.2xlarge            45 RPS  (162,000 inferences/hour)
  g5.4xlarge            55 RPS  (198,000 inferences/hour)
  p4d.24xlarge         600 RPS  (2,160,000 inferences/hour)

----------------------------------------------------------------
Per-Resource Unit Economics
----------------------------------------------------------------
  i-team-a-inf-001
    Instance:           g5.2xlarge
    Team:               team-a
    30-day cost:        $725.66  (599 hrs)
    Effective hourly:   $1.2120/hr
    Cost per 1k req:    $0.00748  (at 45 RPS)

  i-team-a-inf-002
    Instance:           g5.xlarge
    Team:               team-a
    30-day cost:        $606.43  (603 hrs)
    Effective hourly:   $1.0060/hr
    Cost per 1k req:    $0.01118  (at 25 RPS)

  i-team-b-inf-001
    Instance:           g5.xlarge
    Team:               team-b
    30-day cost:        $354.15  (352 hrs)
    Effective hourly:   $1.0060/hr
    Cost per 1k req:    $0.01118  (at 25 RPS)

  i-team-b-inf-002
    Instance:           g5.xlarge
    Team:               team-b
    30-day cost:        $61.80  (205 hrs)
    Effective hourly:   $0.3018/hr
    Cost per 1k req:    $0.00335  (at 25 RPS)

----------------------------------------------------------------
Pricing Tier Comparison (per 1,000 inferences, on-demand list)
----------------------------------------------------------------
  Instance             On-Demand    Reserved        Spot
  g5.xlarge          $   0.01118 $   0.00693 $   0.00335
  g5.2xlarge         $   0.00748 $   0.00464 $   0.00224
  g5.4xlarge         $   0.00820 $   0.00509 $   0.00246
  p4d.24xlarge       $   0.01517 $   0.00941 $   0.00455

----------------------------------------------------------------
Volume Sensitivity: Monthly Cost at Different Inference Volumes
----------------------------------------------------------------
  (using g5.xlarge on-demand as baseline)

      Inferences/month    Monthly cost
             1,000,000 $         11.18
            10,000,000 $        111.78
           100,000,000 $      1,117.78
         1,000,000,000 $     11,177.78
```

**What this tells you:** Cost-per-1k-inferences ranges from $0.00335 (Team B Spot inference) to $0.01118 (Team A on-demand g5.xlarge inference). The Spot workload is roughly 3.3x cheaper per inference than the on-demand equivalent on the same instance type. The pricing tier table makes the trade-off explicit: g5.2xlarge at Spot pricing is the cheapest cost-per-inference on the menu at $0.00224 per 1,000.

---

## How to interpret all four together

The four scripts produce a coherent FinOps story:

1. **Where is the spend going?** (parse_focus) → Mostly GPU, mostly Team A, mostly Reserved.
2. **What's not being attributed?** (tag_compliance) → One untagged research workload at $864/month.
3. **Where are the optimization opportunities?** (gpu_cost_analyzer) → ~$11,628/yr in Reserved Instance migration on the on-demand inference workloads, plus right-sizing on two underutilized instances.
4. **What does it cost us per unit of customer value?** (inference_cost_calc) → Roughly $0.003 to $0.011 per 1,000 inferences depending on pricing tier and instance.

These are the four questions any FinOps practitioner should be able to answer about an AI workload portfolio. The repo demonstrates them end to end.
