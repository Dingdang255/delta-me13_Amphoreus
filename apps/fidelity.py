"""Read-only fidelity scoring over the compiled corpus.

Eight dimensions are scored from the bundle alone -- no titles, no prose, no
engine state. Each dimension reports four metrics:

``coverage``      how many records are actually usable (partial / unknown marks
                  and acknowledged-gap records pull it down);
``traceability``  how many records carry a source, a locator or an evidence
                  reference (a literal ``UNKNOWN`` counts as missing);
``verbatim``      among records that carry a grade, the share graded ``A``;
``consistency``   scenarios that reproduce their expected rule, or scenes whose
                  references all resolve inside the bundle.

Metrics without evidence in a dimension (for example ``verbatim`` where no
record carries a grade) are reported as ``None`` and dropped from the weighted
mean instead of being counted as zero or one.

A gap rule then subtracts a capped penalty for the gaps the corpus already
admits: the one chapter whose ownership is still unknown, the scenarios whose
trigger is unknown, and the community channels that returned nothing. Weights,
thresholds, marks and gap rules all live in ``config/fidelity.json`` -- this
module contains no scores and no proper nouns.

    report = evaluate()
    print(report["weighted_score"], report["pass"])
"""
from __future__ import annotations

import json
import os

DEFAULT_SPEC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "fidelity.json"
)
SCHEMA = 1
UNKNOWN = "UNKNOWN"


class FidelityError(RuntimeError):
    """Raised when the spec is malformed or the bundle cannot be read."""


# ---- spec -------------------------------------------------------------------
def load_spec(path: str | None = None) -> dict:
    path = path or DEFAULT_SPEC
    with open(path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    if spec.get("schema") != SCHEMA:
        raise FidelityError(f"fidelity schema {spec.get('schema')!r} != {SCHEMA}")
    dims = spec.get("dimensions") or {}
    if not dims:
        raise FidelityError("fidelity spec declares no dimensions")
    weights = spec.get("metric_weights") or {}
    missing = [k for k in ("coverage", "traceability", "verbatim", "consistency")
               if k not in weights]
    if missing:
        raise FidelityError(f"metric_weights missing {missing}")
    total = sum(float(d.get("weight", 0.0)) for d in dims.values())
    if total <= 0:
        raise FidelityError("dimension weights sum to zero")
    return spec


# ---- helpers ----------------------------------------------------------------
def _is_ref(value) -> bool:
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text != UNKNOWN
    if isinstance(value, (list, tuple)):
        return any(_is_ref(item) for item in value)
    return False


def _traceable(entry, fields) -> bool:
    return any(_is_ref(entry.get(field)) for field in fields)


def _coverage_mark(entry, spec, gap_kinds) -> float:
    if entry.kind in gap_kinds:
        return 0.0
    marks = spec.get("coverage_marks") or {}
    for field in spec.get("coverage_fields") or ():
        value = entry.get(field)
        if isinstance(value, str) and value.lower() in marks:
            return float(marks[value.lower()])
    return 1.0


def _records(bundle, kinds) -> list:
    return [entry for kind in kinds for entry in bundle.of_kind(kind)]


def _dimension_records(bundle, spec, config) -> list:
    records = _records(bundle, config.get("kinds") or ())
    prefix = str(config.get("unknown_prefix") or "")
    if not prefix:
        return records
    unknown_cfg = spec.get("unknown") or {}
    kind = unknown_cfg.get("kind")
    field = unknown_cfg.get("field", "dimension")
    if not kind:
        return records
    records.extend(entry for entry in bundle.of_kind(kind)
                   if str(entry.get(field, "")).upper() == prefix.upper())
    return records


def _counts(records) -> dict:
    out: dict[str, int] = {}
    for entry in records:
        out[entry.kind] = out.get(entry.kind, 0) + 1
    return dict(sorted(out.items()))


def _consistency(records, bundle) -> float | None:
    """Scenarios first (rule reproduction), then scenes (reference resolution)."""
    from apps import agents, scenes

    scenario_rows = [entry for entry in records if entry.kind == "scenario"]
    if scenario_rows:
        cards = {entry.id: agents.from_dict(entry.data)
                 for entry in bundle.of_kind("character")}
        graded = 0
        passed = 0
        for entry in scenario_rows:
            card = cards.get(entry.get("character"))
            if card is None:
                continue
            result = agents.scenario_check(card, entry.data)
            if result["status"] == "unknown":
                continue
            graded += 1
            if result["status"] == "pass":
                passed += 1
        return None if not graded else passed / graded

    scene_rows = [entry for entry in records if entry.kind == "scene"]
    if scene_rows:
        known = {
            "dialogue": bundle.ids_of_kind("dialogue"),
            "scene": bundle.ids_of_kind("scene"),
            "micro_event": bundle.ids_of_kind("micro_event"),
            "trend": bundle.ids_of_kind("trend"),
            "worldgen": bundle.ids_of_kind("worldgen"),
        }
        good = sum(1 for entry in scene_rows if not scenes.unresolved(entry.data, known))
        return good / len(scene_rows)
    return None


def _gap_penalty(bundle, spec, dimension) -> list[dict]:
    out = []
    for rule in spec.get("gap_rules") or ():
        if rule.get("dimension") != dimension:
            continue
        if "kind" in rule:
            kind = rule["kind"]
            field = rule.get("field", "")
            wanted = rule.get("equals")
            count = sum(1 for entry in bundle.of_kind(kind)
                        if str(entry.get(field, "")) == str(wanted))
            denominator = int(rule.get("denominator") or 0)
        else:
            total = int(rule.get("total") or 0)
            observed = int(rule.get("observed") or 0)
            count = max(0, total - observed)
            denominator = total
        ratio = (count / denominator) if denominator > 0 else 0.0
        amount = float(rule.get("cap") or 0.0) * ratio
        out.append({
            "id": rule.get("id", ""),
            "count": count,
            "denominator": denominator,
            "cap": float(rule.get("cap") or 0.0),
            "amount": round(amount, 4),
        })
    return out


def _score_dimension(bundle, spec, dimension, config) -> dict:
    records = _dimension_records(bundle, spec, config)
    gap_kinds = set(spec.get("gap_kinds") or ())

    coverage = (sum(_coverage_mark(e, spec, gap_kinds) for e in records) / len(records)
                if records else 0.0)
    traceability = (sum(1 for e in records if _traceable(e, spec.get("provenance_fields") or ()))
                    / len(records) if records else 0.0)

    field = (spec.get("verbatim") or {}).get("field", "confidence")
    grade = (spec.get("verbatim") or {}).get("grade", "A")
    graded = [e for e in records if field in e.data]
    verbatim = (sum(1 for e in graded if str(e.get(field, "")) == grade) / len(graded)
                if graded else None)

    consistency = _consistency(records, bundle)

    metrics = {
        "coverage": round(coverage, 4),
        "traceability": round(traceability, 4),
        "verbatim": None if verbatim is None else round(verbatim, 4),
        "consistency": None if consistency is None else round(consistency, 4),
    }
    weights = {name: float((spec.get("metric_weights") or {}).get(name, 0.0))
               for name, value in metrics.items() if value is not None}
    total_weight = sum(weights.values())
    base = (sum(metrics[name] * weight for name, weight in weights.items()) / total_weight
            if total_weight > 0 else 0.0)

    penalties = _gap_penalty(bundle, spec, dimension)
    penalty = sum(row["amount"] for row in penalties)
    score = max(0.0, base - penalty)
    return {
        "weight": float(config.get("weight", 0.0)),
        "entries": len(records),
        "counts": _counts(records),
        "metrics": metrics,
        "metric_weights": weights,
        "base": round(base, 4),
        "penalties": penalties,
        "penalty": round(penalty, 4),
        "score": round(score, 4),
    }


def _unassigned_unknowns(bundle, spec) -> list[str]:
    unknown_cfg = spec.get("unknown") or {}
    kind = unknown_cfg.get("kind")
    if not kind:
        return []
    field = unknown_cfg.get("field", "dimension")
    prefixes = {str(config.get("unknown_prefix") or "").upper()
                for config in (spec.get("dimensions") or {}).values()}
    prefixes.discard("")
    return sorted(entry.id for entry in bundle.of_kind(kind)
                  if str(entry.get(field, "")).upper() not in prefixes)


# ---- public -----------------------------------------------------------------
def evaluate(bundle=None, spec=None) -> dict:
    """Score the whole corpus. Pure: reads the bundle, writes nothing."""
    from apps import canon

    spec = spec or load_spec()
    if bundle is None:
        try:
            bundle = canon.CanonBundle.load()
        except canon.CanonError as exc:
            return {"ok": False, "error": str(exc), "dimensions": {},
                    "weighted_score": None, "pass": False, "failures": [str(exc)]}

    rows = {}
    for dimension, config in (spec.get("dimensions") or {}).items():
        rows[dimension] = _score_dimension(bundle, spec, dimension, config)

    weight_total = sum(row["weight"] for row in rows.values())
    weighted = (sum(row["score"] * row["weight"] for row in rows.values()) / weight_total
                if weight_total > 0 else 0.0)
    threshold = float(spec.get("threshold", 0.0))
    floor = float(spec.get("dimension_floor", 0.0))

    failures = []
    if weighted < threshold:
        failures.append(f"weighted score {weighted:.4f} < threshold {threshold:.4f}")
    for dimension, row in rows.items():
        if row["score"] < floor:
            failures.append(f"{dimension} score {row['score']:.4f} < floor {floor:.4f}")
    passed = not failures

    return {
        "ok": True,
        "schema": SCHEMA,
        "threshold": threshold,
        "dimension_floor": floor,
        "manifest": {
            "schema_version": bundle.manifest.get("schema_version"),
            "entry_count": bundle.manifest.get("entry_count"),
            "source_digest": bundle.manifest.get("source_digest"),
        },
        "dimensions": rows,
        "unassigned_unknowns": _unassigned_unknowns(bundle, spec),
        "weighted_score": round(weighted, 4),
        "pass": passed,
        "failures": failures,
    }


def render(report: dict) -> list[str]:
    """Human-readable lines for the report / CLI. Read-only, no scores added."""
    if not report.get("ok"):
        return [f"  语料不可用：{report.get('error')}"]
    out = []
    out.append(f"  加权保真分 {report['weighted_score']:.4f}"
               f" · 阈值 {report['threshold']:.2f}"
               f" · {'通过' if report['pass'] else '未通过'}")
    out.append(f"  {'维度':<14}{'条数':>6}{'覆盖':>8}{'可追溯':>9}{'逐字':>8}"
               f"{'一致性':>9}{'缺口':>8}{'得分':>8}")

    def fmt(value):
        return "—" if value is None else f"{value:.2f}"

    for name, row in report["dimensions"].items():
        metrics = row["metrics"]
        out.append(f"  {name:<14}{row['entries']:>6}{fmt(metrics['coverage']):>8}"
                   f"{fmt(metrics['traceability']):>9}{fmt(metrics['verbatim']):>8}"
                   f"{fmt(metrics['consistency']):>9}{row['penalty']:>8.2f}"
                   f"{row['score']:>8.2f}")
        for penalty in row["penalties"]:
            out.append(f"    - {penalty['id']}: {penalty['count']}/{penalty['denominator']}"
                       f" × {penalty['cap']:.2f} = -{penalty['amount']:.4f}")
    if report.get("unassigned_unknowns"):
        out.append("  跨维未知（不计入维度分）：" + "、".join(report["unassigned_unknowns"]))
    if report.get("failures"):
        for line in report["failures"]:
            out.append(f"  ✗ {line}")
    return out


if __name__ == "__main__":
    print("\n".join(render(evaluate())))
