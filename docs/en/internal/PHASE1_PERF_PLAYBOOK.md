# Phase-1 Perf Playbook (First 5 Steps)

This playbook automates the first five optimization steps for `plugin-test` stress.

## What it does

1. Freeze target metadata (`target_throughput_pps=1000000`).
2. Run baseline/concurrency matrix:
   - `p12 t2 b256`
   - `p6 t4 b256`
   - `p4 t6 b256`
3. Extract bottleneck diagnostics from `worst_sample` and `worst_topk`.
4. Select best concurrency shape by throughput.
5. Run batch neighborhood on the best shape (`b128/b256/b512/b1024`).

## Script

- `scripts/phase1_perf_playbook.py`

## Quick smoke (fast)

```bash
python -u scripts/phase1_perf_playbook.py --total 20000 --repeats 1 --chain-mode e2e
```

## Full run (heavy)

```bash
python -u scripts/phase1_perf_playbook.py --total 1000000 --repeats 3 --chain-mode e2e
```

## Optional custom config

```bash
python -u scripts/phase1_perf_playbook.py --config data/benchmarks/Config_e2e_flush1024.json --total 1000000 --repeats 2 --chain-mode e2e
```

## Output

All artifacts are written under `data/benchmarks/phase1/`:

- `target_<timestamp>.json`
- `bottleneck_<timestamp>.json`
- `phase1_summary_<timestamp>.json`
- raw benchmark files per run

The summary includes:

- best concurrency candidate
- best batch candidate
- throughput baseline stats
- bottleneck decomposition (tracked vs untracked latency)


