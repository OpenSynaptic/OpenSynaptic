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


def _item_value(item: dict[str, Any], key: str, fallback_key: str | None = None) -> float:
    if fallback_key is not None and key != fallback_key:
        return float(item.get(key, item.get(fallback_key, 0.0)) or 0.0)
    return float(item.get(key, 0.0) or 0.0)


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
        out.append(_item_value(item, key, fallback_key=fallback_key))
    return out


def series_mean(series: Sequence[dict[str, Any]], key: str, fallback_key: str | None = None) -> float:
    total = 0.0
    count = 0
    for item in series:
        total += _item_value(item, key, fallback_key=fallback_key)
        count += 1
    return round4((total / count) if count > 0 else 0.0)


def series_max(series: Sequence[dict[str, Any]], key: str) -> float:
    best = None
    for item in series:
        value = float(item.get(key, 0.0) or 0.0)
        best = value if best is None else max(best, value)
    return round4(best if best is not None else 0.0)


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
    num = 0.0
    den = 0.0
    for item, weight in zip(series, weights):
        w = max(0.0, float(weight or 0.0))
        if w <= 0.0:
            continue
        num += _item_value(item, key, fallback_key=fallback_key) * w
        den += w
    return (num / den) if den > 0.0 else 0.0


def summary_latency_values(summary: dict[str, Any]) -> dict[str, float]:
    return {
        key: _item_value(summary, key, fallback_key=fallback)
        for key, fallback in LATENCY_FIELDS
    }


def aggregate_header_probe(series: Sequence[dict[str, Any]]) -> dict[str, float | int]:
    attempted = 0
    parsed = 0
    crc16_ok = 0
    for item in series:
        probe = item.get('header_probe')
        if not isinstance(probe, dict):
            continue
        attempted += int(probe.get('attempted', 0) or 0)
        parsed += int(probe.get('parsed', 0) or 0)
        crc16_ok += int(probe.get('crc16_ok', 0) or 0)
    return {
        'attempted': attempted,
        'parsed': parsed,
        'crc16_ok': crc16_ok,
        'parse_hit_rate': round4(parsed / attempted) if attempted > 0 else 0.0,
        'crc16_ok_rate': round4(crc16_ok / attempted) if attempted > 0 else 0.0,
    }


def latency_mean_map(series: Sequence[dict[str, Any]], suffix: str) -> dict[str, float]:
    return {
        f'{key}{suffix}': series_mean(series, key, fallback_key=fallback)
        for key, fallback in LATENCY_FIELDS
    }


def aggregate_run_series(
    series: Sequence[dict[str, Any]],
    *,
    suffix: str,
    include_variance: bool = False,
    include_worst: bool = False,
) -> dict[str, Any]:
    if not series:
        out: dict[str, Any] = {
            'runs': 0,
            'ok': 0,
            'fail': 0,
            f'throughput_pps{suffix}': 0.0,
            **{f'{key}{suffix}': 0.0 for key, _ in LATENCY_FIELDS},
            'max_latency_ms_worst': 0.0,
        }
        if include_variance:
            out['throughput_pps_var'] = 0.0
        if include_worst:
            out['throughput_pps_worst'] = 0.0
        return out

    tpp_count = 0
    tpp_sum = 0.0
    tpp_sum_sq = 0.0
    tpp_min = None
    for item in series:
        tpp = _item_value(item, 'throughput_pps')
        tpp_count += 1
        tpp_sum += tpp
        tpp_sum_sq += tpp * tpp
        tpp_min = tpp if tpp_min is None else min(tpp_min, tpp)
    mean_tpp = (tpp_sum / tpp_count) if tpp_count > 0 else 0.0
    out = {
        'runs': len(series),
        'ok': int(sum(int(it.get('ok', 0) or 0) for it in series)),
        'fail': int(sum(int(it.get('fail', 0) or 0) for it in series)),
        f'throughput_pps{suffix}': round4(mean_tpp),
        **latency_mean_map(series, suffix=suffix),
        'max_latency_ms_worst': series_max(series, 'max_latency_ms'),
    }
    if include_variance:
        var = ((tpp_sum_sq / tpp_count) - (mean_tpp * mean_tpp)) if tpp_count > 1 else 0.0
        out['throughput_pps_var'] = round4(max(0.0, var))
    if include_worst:
        out['throughput_pps_worst'] = round4(tpp_min if tpp_min is not None else 0.0)
    return out


