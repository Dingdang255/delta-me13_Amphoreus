"""Read-only loop ledger over the compiled corpus.

The corpus stores only the cycles the game text actually records. A record
carries an ``evidence`` label:

    official       -- quoted from the client text
    reconstructed  -- rebuilt from official data by a deterministic rule
    inferred       -- interpolated; never presented as fact

This module groups, labels and counts; it does not invent missing cycles.
"""
from __future__ import annotations

LABELS = ("official", "reconstructed", "inferred")


class LogError(RuntimeError):
    """Raised when a ledger record is malformed."""


def load(bundle) -> list[dict]:
    rows = []
    for entry in bundle.of_kind("loop"):
        row = dict(entry.data)
        label = str(row.get("evidence", "") or "")
        if label not in LABELS:
            raise LogError(f"{row.get('id')}: unknown evidence label {label!r}")
        if not row.get("source"):
            raise LogError(f"{row.get('id')}: no source")
        rows.append(row)
    rows.sort(key=lambda r: int(r.get("loop", 0)))
    return rows


def labels(rows: list[dict]) -> dict:
    out = {label: 0 for label in LABELS}
    for row in rows:
        out[str(row.get("evidence", ""))] = out.get(str(row.get("evidence", "")), 0) + 1
    return out


def coverage(rows: list[dict]) -> dict:
    counts = labels(rows)
    total = len(rows)
    return {
        "total": total,
        "counts": counts,
        "official_ratio": round(counts["official"] / total, 4) if total else 0.0,
        "first": rows[0]["loop"] if rows else None,
        "last": rows[-1]["loop"] if rows else None,
    }


def by_loop(rows: list[dict], loop: int) -> dict | None:
    for row in rows:
        if int(row.get("loop", -1)) == int(loop):
            return dict(row)
    return None


def phases(rows: list[dict]) -> dict:
    out: dict[str, int] = {}
    for row in rows:
        key = str(row.get("phase", "") or "")
        out[key] = out.get(key, 0) + 1
    return out


def explain(row: dict) -> dict:
    """The minimum a renderer needs; keeps the evidence label explicit."""
    return {
        "id": row.get("id"),
        "loop": row.get("loop"),
        "phase": row.get("phase"),
        "evidence": row.get("evidence"),
        "source": row.get("source"),
        "locator": row.get("locator", ""),
        "verbatim": row.get("verbatim", ""),
    }
