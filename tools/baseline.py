#!/usr/bin/env python3
"""Single source of truth for the project's numbers.

Everything the docs quote -- version, API version, module counts, preset list,
golden fingerprints, corpus size -- is recomputed here from the tree and
compared against `tests/baseline.json`.

    python tools/baseline.py --check     # read-only; exit 1 on drift
    python tools/baseline.py --write     # rewrite tests/baseline.json
    python tools/baseline.py --show      # print the computed baseline

The tool never runs the engine: it only reads files and hashes them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "tests", "baseline.json")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_py(directory):
    return len([n for n in os.listdir(directory) if n.endswith(".py")])


def _count_modules(directory):
    return len([n for n in os.listdir(directory)
                if n.endswith(".py") and n != "__init__.py"])


def _entries(path):
    return len([ln for ln in _read(path).splitlines() if ln.strip()])


def collect():
    pyproject = _read(os.path.join(ROOT, "pyproject.toml"))
    version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    requires = re.search(r'^requires-python\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    api = re.search(r'^API_VERSION\s*=\s*"([^"]+)"',
                    _read(os.path.join(ROOT, "kernel", "api.py")), re.M).group(1)

    golden_path = os.path.join(ROOT, "tests", "golden_fingerprints.json")
    golden = json.loads(_read(golden_path))
    golden_entries = []
    for entry in golden.get("entries", []):
        golden_entries.append({
            "preset": entry.get("preset"),
            "seed": entry.get("seed"),
            "frames": entry.get("frames"),
            "verdict": entry.get("verdict"),
            "reached_frame": entry.get("reached_frame"),
            "digest": entry.get("digest"),
        })
    golden_entries.sort(key=lambda e: (str(e["preset"]), e["seed"] or 0,
                                       e["frames"] or 0))

    presets = []
    preset_root = os.path.join(ROOT, "presets")
    for name in sorted(os.listdir(preset_root)):
        folder = os.path.join(preset_root, name)
        if not os.path.isdir(folder):
            continue
        seed = None
        preset_json = os.path.join(folder, "preset.json")
        if os.path.exists(preset_json):
            try:
                seed = json.loads(_read(preset_json)).get("seed")
            except json.JSONDecodeError:
                seed = "UNREADABLE"
        timeline = os.path.join(folder, "timeline.json")
        has_note = False
        if os.path.exists(timeline):
            try:
                has_note = "_observed_seed0" in json.loads(_read(timeline))
            except json.JSONDecodeError:
                has_note = False
        presets.append({"name": name, "seed": seed, "observed_note": has_note})

    lore = {}
    lore_root = os.path.join(ROOT, "lore")
    if os.path.isdir(lore_root):
        # only count files that ship with the repo: raw client dumps and generated
        # chapter volumes are gitignored, so counting them would make the baseline
        # machine-dependent (CI clones do not have them).
        skip_dirs = {"_probe", "story", "__pycache__"}
        files = 0
        for base, dirs, names in os.walk(lore_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            if os.path.basename(base) == "data" and os.path.basename(os.path.dirname(base)) == "export":
                continue
            files += len(names)
        lore["files"] = {"value": files, "method": "walk lore/ excluding _probe, story, export/data, __pycache__"}
        canon = os.path.join(lore_root, "canon")
        if os.path.isdir(canon):
            manifest = json.loads(_read(os.path.join(canon, "manifest.json")))
            lore["canon_entries"] = {
                "value": manifest.get("entry_count"),
                "method": "lore/canon/manifest.json entry_count",
            }
            lore["canon_digest"] = {
                "value": manifest.get("source_digest"),
                "method": "lore/canon/manifest.json source_digest",
            }

    return {
        "schema": 1,
        "version": {"value": version, "method": "pyproject.toml [project] version"},
        "requires_python": {"value": requires,
                            "method": "pyproject.toml requires-python"},
        "api_version": {"value": api, "method": "kernel/api.py API_VERSION"},
        "counts": {
            "kernel_modules": {
                "value": _count_modules(os.path.join(ROOT, "kernel")),
                "method": "count *.py in kernel/ minus __init__.py",
            },
            "kernel_files": {
                "value": _count_py(os.path.join(ROOT, "kernel")),
                "method": "count *.py in kernel/ including __init__.py",
            },
            "apps_modules": {
                "value": _count_modules(os.path.join(ROOT, "apps")),
                "method": "count *.py in apps/ minus __init__.py",
            },
            "apps_files": {
                "value": _count_py(os.path.join(ROOT, "apps")),
                "method": "count *.py in apps/ including __init__.py",
            },
            "config_json": {
                "value": len([n for n in os.listdir(os.path.join(ROOT, "config"))
                              if n.endswith(".json")]),
                "method": "count *.json in config/",
            },
            "presets": {
                "value": len(presets),
                "method": "count directories in presets/",
            },
            "test_files": {
                "value": _count_py(os.path.join(ROOT, "tests")),
                "method": "count *.py in tests/",
            },
            "tool_scripts": {
                "value": _count_py(os.path.join(ROOT, "tools")),
                "method": "count *.py directly under tools/",
            },
            "golden_entries": {
                "value": len(golden_entries),
                "method": "len(tests/golden_fingerprints.json entries)",
            },
        },
        "golden_fingerprints": {
            "path": "tests/golden_fingerprints.json",
            "sha256": {"value": _sha(golden_path), "method": "sha256 of the file"},
            "reference_platform": golden.get("_reference_platform"),
            "entries": golden_entries,
        },
        "presets": presets,
        "lore": lore,
    }


def _diff(expected, actual, prefix="", out=None):
    out = out if out is not None else []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected:
                out.append(f"{prefix}{key}: added")
            elif key not in actual:
                out.append(f"{prefix}{key}: removed")
            else:
                _diff(expected[key], actual[key], f"{prefix}{key}.", out)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(f"{prefix}[]: {len(expected)} -> {len(actual)}")
        else:
            for i, (e, a) in enumerate(zip(expected, actual)):
                _diff(e, a, f"{prefix}[{i}].", out)
    elif expected != actual:
        out.append(f"{prefix}: {expected!r} -> {actual!r}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="project baseline")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="compare with tests/baseline.json")
    group.add_argument("--write", action="store_true", help="rewrite tests/baseline.json")
    group.add_argument("--show", action="store_true", help="print the computed baseline")
    args = ap.parse_args(argv)

    current = collect()

    if args.write:
        with open(BASELINE, "w", encoding="utf-8", newline="\n") as f:
            json.dump(current, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print(f"baseline written: {BASELINE}")
        return 0

    if args.show or not args.check:
        print(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if not os.path.exists(BASELINE):
        print("no tests/baseline.json; run --write")
        return 1
    stored = json.loads(_read(BASELINE))
    drift = _diff(stored, current)
    if not drift:
        print(f"baseline ok: {len(drift)} drift")
        return 0
    print(f"baseline drift: {len(drift)}")
    for line in drift[:60]:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
