"""Shared metric helpers for test_plugin stress/compare reporting."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

LATENCY_FIELDS: tuple[tuple[str, str | None], ...] = (
    ('avg_latency_ms', None),
    ('p95_latency_ms', None),
    ('p99_latency_ms', 'p95_latency_ms'),
    ('p99_9_latency_ms', 'p95_latency_ms'),
    ('p99_99_latency_ms', 'p95_latency_ms'),
)

STAGE_KEYS: tuple[str, ...] = ('standardize_ms', 'compress_ms', 'fuse_ms')

PERCENTILE_KEYS: tuple[tuple[str, str | None, float], ...] = (
    ('p95', None, 0.95),
    ('p99', 'p95', 0.99),
    ('p99_9', 'p95', 0.999),
    ('p99_99', 'p95', 0.9999),
)


def round4(value: Any) -> float:
    return round(float(value or 0.0), 4)


def empty_stats() -> dict[str, float]:
    return {
        'avg': 0.0,
        'p95': 0.0,
        'p99': 0.0,
        'p99_9': 0.0,
        'p99_99': 0.0,
        'min': 0.0,
        'max': 0.0,
    }


def empty_stage_stats() -> dict[str, dict[str, float]]:
    return {key: empty_stats() for key in STAGE_KEYS}


def stats_from_values(values: Iterable[float]) -> dict[str, float]:
    seq = sorted(float(v or 0.0) for v in values)
    if not seq:
        return empty_stats()

    length = len(seq)

    def _idx(quantile: float) -> int:
        return min(length - 1, int(length * quantile))

    out = {
        'avg': round4(sum(seq) / length),
        'min': round4(seq[0]),
        'max': round4(seq[-1]),
    }
    for key, _, quantile in PERCENTILE_KEYS:
        out[key] = round4(seq[_idx(quantile)])
    return out


def series_values(series: Sequence[dict[str, Any]], key: str, fallback_key: str | None = None) -> list[float]:
    out: list[float] = []
    for item in series:
        value = item.get(key, 0.0)
        if fallback_key is not None and key != fallback_key:
            value = item.get(key, item.get(fallback_key, 0.0))
        out.append(float(value or 0.0))
    return out


def series_mean(series: Sequence[dict[str, Any]], key: str, fallback_key: str | None = None) -> float:
    values = series_values(series, key, fallback_key=fallback_key)
    return round4((sum(values) / len(values)) if values else 0.0)


def series_max(series: Sequence[dict[str, Any]], key: str) -> float:
    values = series_values(series, key)
    return round4(max(values) if values else 0.0)


def weighted_avg(pairs: Iterable[tuple[float, float]]) -> float:
    num = 0.0
    den = 0.0
    for value, weight in pairs:
        w = max(0.0, float(weight or 0.0))
        if w <= 0.0:
            continue
        den += w
        num += float(value or 0.0) * w
    return (num / den) if den > 0.0 else 0.0


def weighted_series_value(
    series: Sequence[dict[str, Any]],
    weights: Sequence[float],
    key: str,
    fallback_key: str | None = None,
) -> float:
    pairs = []
    for item, weight in zip(series, weights):
        value = item.get(key, 0.0)
        if fallback_key is not None and key != fallback_key:
            value = item.get(key, item.get(fallback_key, 0.0))
        pairs.append((float(value or 0.0), float(weight or 0.0)))
    return weighted_avg(pairs)


def latency_mean_map(series: Sequence[dict[str, Any]], suffix: str) -> dict[str, float]:
    return {
        f'{key}{suffix}': series_mean(series, key, fallback_key=fallback)
        for key, fallback in LATENCY_FIELDS
    }

