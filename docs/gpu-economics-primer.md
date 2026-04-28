# GPU Economics Primer for FinOps Practitioners

A reference doc for finance practitioners who need to make sense of GPU cloud spend without going deep on the engineering side.

## Why GPU costs are different

CPU compute economics are mature. Workloads, pricing tiers, and optimization patterns are well understood. GPU economics are not. Three things make GPU spend behave differently:

1. **Per-hour cost is high.** A p4d.24xlarge instance (8x A100 GPUs) lists at $32.77/hr on AWS. That's roughly $24,000/month if it runs continuously. Single-instance budget exposure is significant in a way that CPU compute usually isn't.

2. **Utilization patterns are bursty.** Training jobs run for hours or days, then stop. Inference workloads scale with traffic. There's no equivalent of "always-on web server" pattern that maps cleanly to a Reserved Instance commitment.

3. **The pricing models are evolving.** AWS, Azure, and GCP are all introducing new GPU-specific pricing constructs (Capacity Blocks, On-Demand Capacity Reservations, etc.) faster than commercial FinOps tooling can keep up.

## The GPU instance landscape (AWS, as of early 2026)

| Family | Use case | Typical hourly (us-east-1) | GPU |
|---|---|---|---|
| g5 | Inference, light training | $1.00 - $16.29 | NVIDIA A10G (24 GB) |
| g6 | Inference, ML training | varies | NVIDIA L4 |
| p4d | Large model training | $32.77 | 8x NVIDIA A100 (40 GB) |
| p4de | Large model training | $40.96 | 8x NVIDIA A100 (80 GB) |
| p5 | Frontier model training | $98.32 | 8x NVIDIA H100 |
| p5e / p5en | Largest-scale training | varies | 8x NVIDIA H200 |
| inf1 / inf2 | Inference-optimized | $0.23 - $24.78 | AWS Inferentia |
| trn1 / trn2 | Training-optimized | varies | AWS Trainium |

Pricing is illustrative and changes frequently. Always check the AWS pricing page or your CUR for current rates.

## The four pricing models

### On-demand
Pay per second of usage. No commitment. Highest cost.

When to use: unpredictable workloads, short experiments, anything you don't trust to run for the full commitment period.

### Reserved Instance (RI)
Commit to a specific instance family in a specific region for 1 or 3 years. Get 30-50% off list. Convertible RIs let you change instance family at the cost of a slightly smaller discount.

When to use: steady-state inference workloads where you know the daily traffic floor.

### Savings Plans (SP)
More flexible than RIs. Compute Savings Plans cover any instance family in any region. EC2 Instance Savings Plans cover a specific family. You commit to a dollar amount per hour for 1 or 3 years.

When to use: predictable spend at the dollar level, even if you're not sure about specific instance types.

### Spot
Bid for unused capacity. 60-90% discount versus on-demand. AWS can reclaim the instance with two minutes notice.

When to use: fault-tolerant workloads (batch training with checkpointing, asynchronous inference, dev/test environments).

## How to think about each pricing model for AI workloads

The pricing model decision is workload-specific:

| Workload | Best fit | Why |
|---|---|---|
| Production inference (steady traffic) | Reserved Instance, 1-year, no upfront | Predictable, ~38% discount, locks in capacity |
| Production inference (variable traffic) | Compute Savings Plan + Spot for burst | Base load on SP, scale-out on Spot |
| Model training (planned, recurring) | Reserved capacity (Capacity Blocks) | Guarantees GPU availability when needed |
| Experimentation / R&D | On-demand or Spot | Don't commit to capacity you might not use |
| Batch processing (fault-tolerant) | Spot, with checkpointing | Highest discount, acceptable interruption tolerance |

## The four optimization moves that matter most

### 1. Tag everything
Untagged GPU spend is the single biggest waste category in most AI organizations. A p4d.24xlarge running untagged for a weekend is roughly $1,500. The tagging fix is policy plus enforcement, not technology.

### 2. Right-size early and often
GPU instances are easy to over-provision. A team picks a p4d for training because someone read a blog post, when a g5 would have worked fine. Quarterly right-sizing reviews against actual GPU utilization metrics (not just hours running) typically surface 15-30% savings.

### 3. Idle detection
The single most expensive form of waste in cloud is a GPU running with zero utilization. Common causes: stuck training jobs, abandoned notebook environments, autoscaling that scaled up but never scaled down. Idle detection is a job for monitoring tooling integrated with your cost data, not just CUR analysis.

### 4. Right pricing model for the workload
Most teams underuse Reserved Instances and Savings Plans because they fear lock-in. The math usually favors commitment for any workload that's been running for more than 90 days at predictable levels. The breakeven analysis is straightforward: if you'll use the capacity for more than 6-9 months, the RI pays for itself.

## What the analysis scripts in this repo cover

`gpu_cost_analyzer.py` automates four of the moves above:

- Idle resource detection (avg hours per day below threshold)
- Pricing mix analysis (what % is on-demand and could move)
- Training spike detection (capacity planning trigger)
- Cost concentration (Pareto: which resources drive 80% of spend)

`inference_cost_calc.py` complements with unit economics:

- Cost per 1000 inferences at baseline throughput
- Pricing tier comparison (on-demand vs Reserved vs Spot)
- Volume sensitivity at different inference monthly volumes

The two together give you the answer to: "where is the GPU spend going, what should be optimized first, and what does it cost us per unit of customer value delivered."

## What this primer doesn't cover

- Multi-cloud GPU procurement strategy
- Custom silicon (Trainium, Inferentia, Cerebras) economics
- On-premise vs cloud GPU TCO modeling
- GPU memory bandwidth and interconnect implications for cost
- Fine-grained model architecture cost optimization (quantization, distillation, etc.)

These are deeper engineering-adjacent topics. They matter at scale. They're outside the scope of this repo, which focuses on the FinOps practitioner-level analytical work.

## References

- AWS GPU instance pricing: https://aws.amazon.com/ec2/instance-types/g5/
- AWS Savings Plans: https://aws.amazon.com/savingsplans/
- FinOps Foundation State of FinOps 2026: https://stateoffinops.org/
- NVIDIA cloud GPU instance comparison: https://www.nvidia.com/en-us/data-center/products/cloud-gpu-platforms/
