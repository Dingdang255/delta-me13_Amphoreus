"""Deterministic world generation from a frozen template.

Given one integer sampling key ("initial variables"), this module
  * derives independent random streams per knob,
  * perturbs a small, declared set of config files within their bounds,
  * reports which of the declared dimensions were sampled and which were inherited,
  * emits a complete, runnable world root.

Nothing here knows any title or name: dimensions and knobs come from
``config/generation.json``; the template comes from the project root. The
generated world is written only to the caller's output directory, never back
into the tracked ``config/`` or ``presets/``.

All sampling is *modelling inference* -- the game text has no random-seed
mechanism (see ``lore/D1_seed/seed_terms.md``).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os

import numpy as np

DEFAULT_SPEC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "generation.json"
)
SCHEMA = 1


class WorldGenError(RuntimeError):
    """Raised when the template or the spec is inconsistent."""


def derive_stream(seed: int, tag: str) -> np.random.Generator:
    """Independent stream per (seed, tag). Same inputs -> same stream."""
    digest = hashlib.blake2b(f"{int(seed)}|{tag}".encode("utf-8"), digest_size=8).digest()
    return np.random.default_rng(int.from_bytes(digest, "little"))


def load_spec(path: str | None = None) -> dict:
    path = path or DEFAULT_SPEC
    with open(path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    if spec.get("schema") != SCHEMA:
        raise WorldGenError(f"generation schema {spec.get('schema')!r} != {SCHEMA}")
    return spec


def _walk(node, path):
    """Yield the container that holds the leaf addressed by `path` (supports '*')."""
    if not path:
        yield node
        return
    head, rest = path[0], path[1:]
    if head == "*":
        if not isinstance(node, list):
            raise WorldGenError(f"'*' expects a list, got {type(node).__name__}")
        for item in node:
            yield from _walk(item, rest)
    else:
        if not isinstance(node, dict) or head not in node:
            raise WorldGenError(f"missing key {head!r} while walking {path}")
        yield from _walk(node[head], rest)


def _apply(node, path, knob, rng):
    """Write perturbed leaves in place; '*' addresses each element."""
    if not path:
        return
    head, rest = path[0], path[1:]
    if isinstance(node, dict):
        if head not in node:
            raise WorldGenError(f"missing key {head!r}")
        if len(rest) == 1 and rest[0] == "*":
            items = node[head]
            if not isinstance(items, list):
                raise WorldGenError(f"{head!r} is not a list")
            node[head] = [_perturb(v, knob, rng) for v in items]
            return
        if not rest:
            node[head] = _perturb(node[head], knob, rng)
            return
        _apply(node[head], rest, knob, rng)
        return
    if isinstance(node, list):
        if head != "*":
            raise WorldGenError(f"expected '*' at {head!r}")
        if not rest:
            for i in range(len(node)):
                node[i] = _perturb(node[i], knob, rng)
            return
        for item in node:
            _apply(item, rest, knob, rng)
        return
    raise WorldGenError(f"cannot descend into {type(node).__name__}")


def _perturb(value, knob, rng):
    mode = knob["mode"]
    lo, hi = knob["low"], knob["high"]
    if mode == "relative":
        new = float(value) * (1.0 + float(rng.uniform(lo, hi)))
        new = round(new, int(knob.get("round", 6)))
    elif mode == "absolute":
        new = float(value) + float(rng.uniform(lo, hi))
        new = round(new, int(knob.get("round", 6)))
    elif mode == "int_delta":
        new = int(value) + int(rng.integers(int(lo), int(hi) + 1))
    else:
        raise WorldGenError(f"unknown knob mode {mode!r}")
    clamp = knob.get("clamp")
    if clamp:
        new = max(clamp[0], min(clamp[1], new))
        if mode != "int_delta":
            new = round(float(new), int(knob.get("round", 6)))
    return int(new) if mode == "int_delta" else new


def _collect(node, path):
    """Leaf values addressed by `path`, in a stable order."""
    out = []
    for holder in _walk(node, path[:-1]):
        key = path[-1]
        if key == "*":
            out.extend(holder)
        else:
            out.append(holder[key])
    return out


def _symmetrize(loci):
    n = len(loci)
    for i in range(n):
        row = loci[i]["couplings"]
        row[i] = 0.0
        for j in range(i + 1, n):
            avg = round((float(row[j]) + float(loci[j]["couplings"][i])) / 2.0, 3)
            row[j] = avg
            loci[j]["couplings"][i] = avg


def _fix_pairs(seeding):
    pair = seeding["per_locus"]
    if pair["max"] < pair["min"]:
        pair["max"] = pair["min"]


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _digest(obj) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bootstrap_world(seed: int, spec: dict | None = None, template_root: str | None = None) -> dict:
    """Return the full generated world: config docs, dimension report, manifest."""
    spec = spec or load_spec()
    template_root = os.path.abspath(template_root or os.path.dirname(DEFAULT_SPEC))
    docs = {}
    for rel in spec["perturbed"]:
        docs[rel] = _read_json(os.path.join(template_root, rel.replace("/", os.sep)))

    for name, knob in spec["knobs"].items():
        rng = derive_stream(seed, knob.get("stream", name))
        doc = docs[knob["file"]]
        _apply(doc, knob["path"], knob, rng)
        if knob.get("symmetrize"):
            _symmetrize(doc["loci"])

    _fix_pairs(docs["config/seeding.json"])

    dimensions = {}
    for dim in spec["dimensions"]:
        key = dim["key"]
        if dim["status"] == "sampled":
            signatures = {}
            for knob_name in dim["knobs"]:
                knob = spec["knobs"][knob_name]
                signatures[knob_name] = _digest(_collect(docs[knob["file"]], knob["path"]))
            dimensions[key] = {
                "status": "sampled",
                "knobs": list(dim["knobs"]),
                "signatures": signatures,
                "inferred": True,
            }
        else:
            dimensions[key] = {
                "status": "inherited",
                "reason": dim.get("reason", ""),
                "inferred": True,
            }

    manifest = {
        "schema": SCHEMA,
        "seed": int(seed),
        "template_root": os.path.basename(template_root) or ".",
        "template_digest": _digest({rel: _read_json(os.path.join(template_root, rel.replace("/", os.sep)))
                                    for rel in spec["perturbed"]}),
        "world_digest": _digest(docs),
        "streams": list(spec["streams"]),
        "sampled": sorted(k for k, v in dimensions.items() if v["status"] == "sampled"),
        "inherited": sorted(k for k, v in dimensions.items() if v["status"] == "inherited"),
        "note": "sampling is modelling inference; the game text has no random-seed mechanism",
    }
    return {"seed": int(seed), "config": docs, "dimensions": dimensions, "manifest": manifest}


def build_files(world: dict, spec: dict | None = None, template_root: str | None = None) -> dict:
    """Return {relative posix path: bytes} for a complete world root."""
    spec = spec or load_spec()
    template_root = os.path.abspath(template_root or os.path.dirname(DEFAULT_SPEC))
    out = {}

    cfg_dir = os.path.join(template_root, "config")
    for name in sorted(os.listdir(cfg_dir)):
        if not name.endswith(".json"):
            continue
        rel = f"config/{name}"
        if rel in world["config"]:
            text = json.dumps(world["config"][rel], ensure_ascii=False, indent=2, sort_keys=True)
            out[rel] = (text + "\n").encode("utf-8")
        else:
            with open(os.path.join(cfg_dir, name), "rb") as f:
                out[rel] = f.read()

    for preset in spec["template"].get("preset_dirs", []):
        base = os.path.join(template_root, "presets", preset)
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                out[f"presets/{preset}/{name}"] = f.read()

    manifest = json.dumps(world["manifest"], ensure_ascii=False, indent=2, sort_keys=True)
    out["world_manifest.json"] = (manifest + "\n").encode("utf-8")
    return out


def write_world(files: dict, out_dir: str) -> None:
    for rel, data in files.items():
        path = os.path.join(out_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def diff_dimensions(a: dict, b: dict) -> list[str]:
    """Dimension keys whose sampled signatures differ between two worlds."""
    changed = []
    for key in sorted(set(a["dimensions"]) | set(b["dimensions"])):
        da, db = a["dimensions"].get(key, {}), b["dimensions"].get(key, {})
        if da.get("status") != db.get("status"):
            changed.append(key)
        elif da.get("signatures") != db.get("signatures"):
            changed.append(key)
    return changed
