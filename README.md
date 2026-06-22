# finops-ai-workloads

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![FOCUS 1.0](https://img.shields.io/badge/FOCUS-v1.0-green.svg)](https://focus.finops.org/)
[![FinOps Framework](https://img.shields.io/badge/FinOps_Framework-aligned-blue.svg)](https://www.finops.org/framework/)

> A working FinOps analytical pipeline for AI and GPU cloud spend, built on FOCUS-formatted billing data.

## Why this repo exists

This repo demonstrates how the FinOps Framework applies to AI and GPU workloads, using a working analytical pipeline. It's built around two questions every cloud finance practitioner wrestles with: where is the spend going, and which spend should be optimized first?

The analysis runs against FOCUS-formatted billing data with synthetic AI workload patterns engineered to demonstrate common FinOps signals:

- Untagged spend (the easy first win on most AI cost programs)
- Idle GPU resources (the most expensive form of waste in cloud)
- Reserved Instance under-utilization
- Spot vs on-demand mix opportunities
- Team-level cost attribution

Scripts are Python 3.10+, no external API calls. Run them against the synthetic data shipped in `/data`, or point them at your own FOCUS-formatted CUR.

## Quick start

```bash
git clone https://github.com/paragoner1/finops-ai-workloads.git
cd finops-ai-workloads
pip install -r requirements.txt

# Generate the synthetic dataset (or use the one already in /data)
python data/generate_synthetic.py

# Run the analyses
python analysis/parse_focus.py data/ai-workload-synthetic.csv
python analysis/gpu_cost_analyzer.py data/ai-workload-synthetic.csv
python analysis/tag_compliance.py data/ai-workload-synthetic.csv
python analysis/inference_cost_calc.py data/ai-workload-synthetic.csv
```

Sample outputs are in `examples/sample-output.md`. For a visual walkthrough with charts, open `notebooks/visual_analysis.ipynb` (renders directly in GitHub).

## Repo structure

```
finops-ai-workloads/
├── README.md
├── requirements.txt
├── data/
│   ├── generate_synthetic.py     # FOCUS-formatted data generator
│   ├── ai-workload-synthetic.csv # 30-day synthetic dataset
│   └── README.md                 # data sources and attribution
├── analysis/
│   ├── parse_focus.py            # base FOCUS parser and summary
│   ├── gpu_cost_analyzer.py      # idle GPU, RI gaps, spot opportunities
│   ├── tag_compliance.py         # untagged spend identification
│   └── inference_cost_calc.py    # cost-per-inference framework
├── docs/
│   ├── federal-to-finops-translation.md
│   ├── gpu-economics-primer.md
│   └── cost-per-inference-framework.md
├── notebooks/
│   ├── build_notebook.py         # rebuilds the notebook source from scratch
│   └── visual_analysis.ipynb     # six charts, renders in GitHub
└── examples/
    └── sample-output.md
```

## About the data

This repo uses synthetic billing data formatted to the FOCUS specification (FinOps Open Cost and Usage Specification). No real billing data is exposed.

The synthetic dataset simulates 30 days of GPU and CPU usage across:

- Two engineering teams: `team-a` (heavy users, mix of training and inference) and `team-b` (lighter, mostly inference)
- One untagged "research" workload representing roughly 15% of GPU spend
- Reserved Instance utilization at 67% (an optimization opportunity)
- 80% on-demand / 20% spot mix
- Baseline traffic plus a training spike during week three

The analytical scripts work identically against real CUR or FOCUS-formatted data. Drop your own CSV into `/data` and rerun.

## Analysis modules

### parse_focus.py
Loads a FOCUS-formatted CSV, validates the schema against the FOCUS v1.0 spec, and produces a per-day cost summary by service category and resource type. The base layer everything else builds on.

### gpu_cost_analyzer.py
Identifies optimization opportunities specific to GPU workloads:

- Idle resource detection (utilization windows below threshold)
- Reserved Instance coverage gaps
- Spot instance migration candidates
- Right-sizing recommendations for over-provisioned instances

### tag_compliance.py
Flags untagged spend, partially tagged resources, and tag inconsistency. Outputs a remediation list ranked by spend impact, so the team knows which untagged resources to chase first.

### inference_cost_calc.py
Implements a cost-per-inference framework. Takes inference volume, GPU instance configuration, and pricing model, then produces a per-thousand-inference cost. Useful for unit economics modeling on AI products and for the "should we move this workload to a different tier" conversation.

## Why this exists, the longer version

The FinOps Framework treats Inform, Optimize, and Operate as a continuous loop. The Inform phase needs clean data and shared visibility before any of the other phases can do real work. This repo lives in that phase: parsing the data, surfacing the signals, and producing reports that engineering and finance teams can act on together.

AI and GPU workloads are where most FinOps teams are spending their attention right now. According to the State of FinOps 2026 Report, 98% of FinOps teams now manage AI spend, up from 31% two years ago. The patterns this repo demonstrates (idle GPUs, untagged research workloads, RI under-utilization, spot opportunities) are the same patterns that show up in real cloud bills at production scale.

The translation between traditional finance discipline and modern cloud cost management is more direct than people assume. Cost allocation tags play the role of fund codes. Showback and chargeback map to traditional accountability models. Variance analysis on cloud spend is the same exercise as variance analysis on any other budget, just with a different data source. The FinOps Framework names the work and gives it structure. The underlying skills are 30+ years old.

## Running against your own data

If you have a real AWS CUR or FOCUS-formatted billing export, you can swap it in:

```bash
python analysis/parse_focus.py /path/to/your/billing.csv
```

The scripts assume FOCUS v1.0 column names. If you're on AWS CUR 2.0 (which is FOCUS-aligned but not identical), you may need a small column-rename pass first.

## About

Built by Paragoner ([paragoner1](https://github.com/paragoner1) on GitHub).

17 years of federal healthcare finance leadership, including seven as CFO of a $750M VA healthcare system. FinOps Certified Practitioner, April 2026. Hands-on Rust on GPU infrastructure (Whisper inference, automated trading systems).

Open to FinOps roles where the AI cost modeling work is real. [LinkedIn](https://www.linkedin.com/in/rustdevsec).

## License

MIT.
