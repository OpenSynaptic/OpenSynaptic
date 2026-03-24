# Phase-2 Perf Playbook (Second 5 Steps)

Script: `scripts/phase2_perf_playbook.py`

## Covers

6. Stability regression on phase-1 winner.
7. Core vs e2e split on same shape.
8. Concurrency neighborhood check.
9. `collector_flush_every` sweep (256/512/1024).
10. Gate evaluation + recommendation.

## Quick smoke

```bash
python -u scripts/phase2_perf_playbook.py --total 50000 --repeats 1
```

## Full run

```bash
python -u scripts/phase2_perf_playbook.py --total 300000 --repeats 3
```

## Use specific phase1 summary

```bash
python -u scripts/phase2_perf_playbook.py --phase1-summary data/benchmarks/phase1/phase1_summary_YYYYMMDD_HHMMSS.json --total 300000 --repeats 3
```

## Output

`data/benchmarks/phase2/phase2_summary_<timestamp>.json`


