# Cost-Per-Inference Framework

A methodology for converting cloud GPU spend into a unit-economics number that product, finance, and engineering can all reason about.

## Why cost-per-inference matters

"What's our cloud bill?" is the wrong question for an AI product. The right questions are:

- What does it cost us to serve one customer request?
- How does that cost change at 10x volume?
- Are we losing money on inference at our current pricing?

A board, a CFO, and a head of product all need an answer to those questions. Total cloud spend doesn't answer them. Cost-per-inference does.

## The base formula

```
Cost per 1,000 inferences = (Effective hourly instance cost / Inferences per hour) x 1,000
```

Where:
- **Effective hourly instance cost** is the per-hour price after Reserved Instance, Savings Plan, or Spot discounts. Pull this directly from your CUR or FOCUS data.
- **Inferences per hour** is the throughput you actually achieve in production, expressed at the requests-per-second level multiplied by 3,600.

Example: a g5.xlarge at $1.006/hr on-demand serving 25 requests per second:

```
Cost per 1k = (1.006 / (25 x 3600)) x 1000 = $0.01118 per 1,000 inferences
```

## Why throughput is the harder number

Effective hourly cost is easy. Your CUR has it.

Throughput is hard because it varies by:

- Model size (a 7B parameter LLM is dramatically slower than a Whisper STT model on the same GPU)
- Batch size (bigger batches usually mean higher throughput per request, up to a point)
- Sequence length (longer prompts/audio mean more compute per request)
- Quantization (FP16 vs INT8 vs INT4 changes throughput by 2-4x)
- Prefill vs decode (LLM serving has wildly different costs for the two phases)
- Concurrency tuning (how the inference server handles parallel requests)

The framework in `inference_cost_calc.py` uses conservative defaults, but production teams need to measure their actual throughput and override the defaults. The whole framework is only as good as the throughput number.

## The three numbers to track

For any AI product, three numbers belong on the dashboard:

1. **Cost per 1,000 inferences (last 30 days)** at effective pricing. This is the "what are we paying right now" number.
2. **Cost per 1,000 inferences at on-demand list pricing.** The unhedged version. Tells you what you'd pay if every RI and Savings Plan vanished tomorrow.
3. **Inferences per dollar of revenue.** Tie the cost number to product economics. If a customer's subscription generates X dollars of revenue and consumes Y inferences, you should know Y/X.

The third one is the one that triggers product decisions. If your cost-per-inference rises faster than your inferences-per-revenue-dollar drops, you have a unit economics problem.

## Volume sensitivity

The script in this repo also outputs monthly cost at different inference volumes. The point of that table is to expose the volume sensitivity that often surprises product leaders.

A g5.xlarge at on-demand list serving 25 RPS:

| Inferences per month | Monthly cost (g5.xlarge on-demand) |
|---|---|
| 1 million | $11.18 |
| 10 million | $111.78 |
| 100 million | $1,117.78 |
| 1 billion | $11,177.78 |

Linear, as you'd expect. But this rarely shows up in product planning conversations until the bill is uncomfortable. Putting the table in front of product leaders during pricing decisions changes the discussion.

## What to do with the numbers

Three concrete uses:

1. **Pricing decisions.** If you're charging $0.10 per 1,000 customer requests and your cost-per-inference is $0.05, your gross margin contribution from inference is 50%. Below 30% is usually a red flag for AI products without other revenue layers.

2. **Tier and pricing-model decisions.** Run the same calculation across Reserved, On-Demand, and Spot. The delta between the columns tells you how much margin you're leaving on the table by not committing.

3. **Architecture decisions.** Compare cost-per-inference across instance types. If g5.4xlarge gives you 2.2x the throughput of g5.xlarge but only costs 1.6x more, the larger instance has better unit economics. The framework makes that comparison explicit.

## What this framework doesn't capture

The script in this repo computes inference cost at the instance level. Real production cost-per-inference also includes:

- **Networking and data transfer.** Often 5-15% of total inference cost.
- **Storage of model artifacts.** Usually trivial but can matter at very high volume.
- **The cost of cold starts and idle capacity.** If you provision for peak but average traffic is 30% of peak, your effective cost-per-inference is 3x your peak-utilization number.
- **Pre and post-processing CPU work.** Tokenization, normalization, response formatting. Usually small but non-zero.
- **Logging, observability, and security tooling.** Not free, often shared across services.

For a board-level number, the instance-level calculation is usually within 15-20% of the true number. For an engineering decision, you'll want the fuller model.

## How to integrate this into a real reporting rhythm

A practical FinOps cadence for cost-per-inference:

- **Daily:** automated calculation against the previous day's CUR, posted to a Slack channel.
- **Weekly:** the same number plotted as a 7-day trend, plus a cohort breakdown by team or product.
- **Monthly:** included in the FP&A close package alongside revenue and margin numbers.
- **Quarterly:** revisit the throughput assumptions. Models change. Hardware changes. The defaults in the calculator drift.

## References

- AWS GPU instance pricing: https://aws.amazon.com/ec2/instance-types/g5/
- Hugging Face inference benchmarks: https://huggingface.co/blog (search "inference benchmark")
- vLLM throughput documentation: https://docs.vllm.ai/
- AWS Cost and Usage Report documentation: https://docs.aws.amazon.com/cur/latest/userguide/
