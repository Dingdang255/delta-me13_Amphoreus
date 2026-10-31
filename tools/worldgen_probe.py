#!/usr/bin/env python3
"""Probe the world generator.

    python tools/worldgen_probe.py                      # summary for seed 0
    python tools/worldgen_probe.py --seed 7 --out worlds/generated/s7
    python tools/worldgen_probe.py --seeds 0,7,42       # divergence table
    python tools/worldgen_probe.py --check worlds/generated/s7

`--check` rebuilds the world from `world_manifest.json` and compares bytes, so
a drifted generator or a hand-edited world both show up.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps import worldgen  # noqa: E402


def _summary(world):
    m = world["manifest"]
    sampled = [k for k, v in world["dimensions"].items() if v["status"] == "sampled"]
    inherited = [k for k, v in world["dimensions"].items() if v["status"] == "inherited"]
    return {
        "seed": m["seed"],
        "world_digest": m["world_digest"],
        "template_digest": m["template_digest"],
        "sampled": sampled,
        "inherited": inherited,
        "dimensions": len(world["dimensions"]),
    }


def cmd_write(seed, out):
    spec = worldgen.load_spec()
    world = worldgen.bootstrap_world(seed, spec, ROOT)
    files = worldgen.build_files(world, spec, ROOT)
    worldgen.write_world(files, out)
    print(f"world written: {out}")
    print(f"  seed {seed} · {len(files)} files · world_digest {world['manifest']['world_digest'][:16]}")
    return 0


def cmd_report(seeds):
    spec = worldgen.load_spec()
    worlds = {s: worldgen.bootstrap_world(s, spec, ROOT) for s in seeds}
    base_seed = seeds[0]
    base = worlds[base_seed]
    print(f"{'dimension':<14}{'status':<10}{'differs vs seed ' + str(base_seed)}")
    for key in sorted(base["dimensions"]):
        status = base["dimensions"][key]["status"]
        if status != "sampled":
            print(f"  {key:<12}{status:<10}-")
            continue
        marks = []
        for seed in seeds[1:]:
            changed = key in worldgen.diff_dimensions(base, worlds[seed])
            marks.append("yes" if changed else "NO")
        print(f"  {key:<12}{status:<10}{', '.join(marks)}")
    print()
    for seed in seeds:
        s = _summary(worlds[seed])
        print(f"  seed {seed:<4} dims {s['dimensions']} · sampled {len(s['sampled'])}"
              f" · digest {s['world_digest'][:16]}")
    pairs = list(itertools.combinations(seeds, 2))
    if len(pairs) > 1:
        print()
        for a, b in pairs:
            common = worldgen.diff_dimensions(worlds[a], worlds[b])
            print(f"  {a} vs {b}: {len(common)} dimension(s) differ -> {', '.join(common)}")
    return 0


def cmd_check(path):
    manifest_path = os.path.join(path, "world_manifest.json")
    if not os.path.exists(manifest_path):
        print(f"no world_manifest.json under {path}")
        return 1
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    seed = int(manifest["seed"])
    spec = worldgen.load_spec()
    world = worldgen.bootstrap_world(seed, spec, ROOT)
    files = worldgen.build_files(world, spec, ROOT)
    drift = []
    for rel, data in sorted(files.items()):
        target = os.path.join(path, rel.replace("/", os.sep))
        if not os.path.exists(target):
            drift.append(f"missing  {rel}")
            continue
        with open(target, "rb") as f:
            if f.read() != data:
                drift.append(f"differs  {rel}")
    if drift:
        print(f"world drift: {len(drift)} file(s)")
        for line in drift[:40]:
            print(f"  {line}")
        return 1
    print(f"world ok: {len(files)} files · seed {seed}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="world generator probe")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seeds", default=None, help="comma separated, e.g. 0,7,42")
    ap.add_argument("--check", default=None, metavar="DIR")
    args = ap.parse_args(argv)

    if args.check:
        return cmd_check(args.check)
    if args.seeds:
        seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
        return cmd_report(seeds)
    if args.out:
        return cmd_write(args.seed, args.out)

    spec = worldgen.load_spec()
    world = worldgen.bootstrap_world(args.seed, spec, ROOT)
    s = _summary(world)
    print(f"seed {s['seed']} · {s['dimensions']} dimensions"
          f" · sampled {len(s['sampled'])} · inherited {len(s['inherited'])}")
    print(f"  world_digest    {s['world_digest']}")
    print(f"  template_digest {s['template_digest']}")
    print(f"  sampled    {', '.join(s['sampled'])}")
    print(f"  inherited  {', '.join(s['inherited'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
