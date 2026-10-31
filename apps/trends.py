"""Read-only trend evaluator.

A trend is a set of channels; each channel binds one *reading* (a number the
caller already has) to one *observable*, and turns it into a bounded pressure.

Nothing here mutates the world: the evaluator takes a plain dict of readings and
returns suggestions. Two channels of the same trend do **not** cancel each
other -- they are reported side by side, because some mechanisms really do have
two simultaneous effects (delay a process while reinforcing a tendency).

All coefficients come from ``config/trends.json``; this module contains no
constants and no titles.
"""
from __future__ import annotations

import json
import math
import os

DEFAULT_SPEC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "trends.json"
)
SCHEMA = 1

#: channel kinds -> formula family
KINDS = ("saturating", "threshold", "linear_capped")


class TrendError(RuntimeError):
    """Raised when the spec is malformed or a channel references an unknown driver."""


def load_spec(path: str | None = None) -> dict:
    path = path or DEFAULT_SPEC
    with open(path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    if spec.get("schema") != SCHEMA:
        raise TrendError(f"trends schema {spec.get('schema')!r} != {SCHEMA}")
    return spec


def _reading(view: dict, name: str) -> float | None:
    value = view.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evaluate(kind: str, channel: dict, x: float) -> float:
    if kind == "saturating":
        rate = float(channel["rate"])
        cap = float(channel.get("cap", 1.0))
        value = 1.0 - math.exp(-rate * max(0.0, x))
        return min(cap, value)
    if kind == "threshold":
        threshold = float(channel["threshold"])
        ceiling = float(channel["ceiling"])
        if x <= threshold:
            return 0.0
        span = max(1e-9, ceiling - threshold)
        return min(1.0, (x - threshold) / span)
    if kind == "linear_capped":
        value = float(channel["rate"]) * max(0.0, x)
        return min(float(channel.get("cap", 1.0)), value)
    raise TrendError(f"unknown channel kind {kind!r}")


def evaluate_channel(channel: dict, view: dict, epsilon: float = 0.05) -> dict:
    """One channel -> one suggestion row. Missing readings are reported, not guessed."""
    driver = channel["driver"]
    x = _reading(view, driver)
    row = {
        "channel": channel["id"],
        "type": channel["type"],
        "target": channel["target"],
        "observable": channel.get("observable", ""),
        "source": channel.get("source", ""),
        "confidence": channel.get("confidence", ""),
        "inferred": bool(channel.get("inferred", False)),
        "driver": driver,
        "driver_value": None if x is None else round(x, 6),
        "value": 0.0,
        "active": False,
        "note": "",
    }
    if x is None:
        row["note"] = "driver_missing"
        return row
    row["value"] = round(_evaluate(channel["kind"], channel, x), 6)
    row["active"] = row["value"] >= epsilon
    return row


def evaluate_trend(trend_id: str, channel: dict | list, view: dict, epsilon: float = 0.05) -> list[dict]:
    channels = channel if isinstance(channel, list) else [channel]
    out = []
    for ch in channels:
        row = evaluate_channel(ch, view, epsilon)
        row["trend"] = trend_id
        out.append(row)
    return out


def evaluate_all(spec: dict, view: dict) -> list[dict]:
    epsilon = float(spec.get("epsilon", 0.05))
    rows = []
    for trend_id, trend in spec["trends"].items():
        if trend.get("status") != "wired":
            continue
        rows.extend(evaluate_trend(trend_id, trend["channels"], view, epsilon))
    return rows


def coverage(spec: dict) -> dict:
    wired = [t for t, v in spec["trends"].items() if v.get("status") == "wired"]
    unwired = {t: v.get("reason", "") for t, v in spec["trends"].items()
               if v.get("status") != "wired"}
    channels = sum(len(spec["trends"][t]["channels"]) for t in wired)
    return {
        "trends": len(spec["trends"]),
        "wired": wired,
        "unwired": unwired,
        "channels": channels,
    }


def view_from_features(features: dict) -> dict:
    """Map an existing feature snapshot onto trend readings.

    Snapshot values (``final_entropy`` / ``final_noise``) are accepted so the
    evaluator can be exercised today; a per-frame caller should pass live
    readings under ``entropy`` / ``noise`` instead.
    """
    def pick(*names):
        for name in names:
            if name in features and features[name] is not None:
                return features[name]
        return None

    return {
        "cycle_count": pick("cycle_count", "iterations", "origin_tomb_cycles"),
        "embers_taken": pick("embers_taken"),
        "memory_rows": pick("memory_rows", "origin_tomb_rows"),
        "entropy": pick("entropy", "final_entropy"),
        "noise": pick("noise", "final_noise"),
    }


def summarize(rows: list[dict]) -> dict:
    active = [r for r in rows if r["active"]]
    by_trend: dict[str, list[dict]] = {}
    for row in rows:
        by_trend.setdefault(row["trend"], []).append(row)
    strongest = max(rows, key=lambda r: r["value"]) if rows else None
    return {
        "channels": len(rows),
        "active": len(active),
        "by_trend": by_trend,
        "strongest": None if strongest is None else {
            "trend": strongest["trend"],
            "channel": strongest["channel"],
            "value": strongest["value"],
        },
    }
