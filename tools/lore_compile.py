#!/usr/bin/env python3
"""Compile the raw lore corpus into `lore/canon/` (deterministic, idempotent).

Input  : lore/03_*.jsonl, lore/D1_seed/..., lore/D8_characters/...
Output : lore/canon/{manifest,index,glossary,...}.json|jsonl + characters/

Rules:
  * never invents facts: fields are copied as-is, only `id` is normalised
    (entity_id / event_id / term_id -> id) and relations get `REL-nnn`.
  * no wall-clock timestamps: `compiled_at` is the newest source mtime, so two
    runs over an unchanged tree are byte-identical.
  * `--check` compiles in memory and diffs against the existing output.

    python tools/lore_compile.py            # write
    python tools/lore_compile.py --check    # verify, exit 1 on drift
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LORE = os.path.join(ROOT, "lore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lore_lint  # noqa: E402  (same-directory helper, keeps the kind map in one place)

SCHEMA_VERSION = "1"

OUT_NAMES = {
    "entity": "entities.jsonl",
    "event": "events.jsonl",
    "term": "terms.jsonl",
    "conflict": "conflicts.jsonl",
    "unknown": "unknowns.jsonl",
    "worldgen": "worldgen_dimensions.jsonl",
    "trend": "trends.jsonl",
    "micro_event": "micro_events.jsonl",
    "causal": "causal_links.jsonl",
    "wiki_claim": "plot_claims.jsonl",
    "plot": "plot_expansions.jsonl",
    "gap": "gaps.jsonl",
    "scene": "scenes.jsonl",
    "dialogue": "dialogues.jsonl",
    "loop": "loops.jsonl",
    "anchor": "loop_anchors.jsonl",
    "terminal": "terminals.jsonl",
    "multilingual": "multilingual.jsonl",
    "fragment": "community.jsonl",
    "crosscheck": "crosschecks.jsonl",
    "debunked": "debunked.jsonl",
    "relation": "relations.jsonl",
    "scenario": "scenarios.jsonl",
    "guard": "ooc_guards.jsonl",
}

ID_ALIASES = {"entity": "entity_id", "event": "event_id", "term": "term_id"}

LABEL_KEYS = ("name", "zh", "title", "text", "dimension", "question", "summary")


def sha256_bytes(data: bytes) -> str:
    # line endings are not content: the repo stores LF, Windows checkouts may hold CRLF
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def read_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            out.append((lineno, json.loads(line)))
    return out


def dump_line(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def dump_pretty(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def first_source(obj) -> str:
    for key in lore_lint.SOURCE_KEYS:
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, list) and val:
            return ",".join(str(x) for x in val)
    return ""


def label_of(obj) -> str:
    for key in LABEL_KEYS:
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def build():
    """Return {relpath: bytes} for the whole canon tree."""
    files: dict[str, bytes] = {}
    index: dict[str, list] = {}
    trace = []
    kinds: dict[str, int] = {}
    unresolved: list[str] = []

    for kind, (rel, id_field, _required, _need_src, _) in lore_lint.KINDS.items():
        path = os.path.join(LORE, rel.replace("/", os.sep))
        if not os.path.exists(path):
            raise SystemExit(f"missing source file: {rel}")
        rows = read_jsonl(path)
        kinds[kind] = len(rows)
        buf = []
        rel_n = 0
        for lineno, obj in rows:
            if id_field:
                rid = obj.get(id_field)
            else:
                rel_n += 1
                rid = f"REL-{rel_n:03d}"
            if not rid:
                raise SystemExit(f"{rel}:{lineno} record has no usable id")
            record = {"id": rid}
            for key, val in obj.items():
                if key == "id":
                    continue
                record[key] = val
            buf.append(dump_line(record))
            index.setdefault(rid, []).append({
                "kind": kind,
                "file": OUT_NAMES[kind],
                "line": lineno,
                "label": label_of(obj),
            })
            trace.append({
                "id": rid,
                "kind": kind,
                "source": first_source(obj),
                "locator": obj.get("locator", ""),
                "confidence": obj.get("confidence", ""),
            })
        files[OUT_NAMES[kind]] = b"".join(buf)

    # character cards: copy verbatim, but keep the id -> file mapping
    cdir = os.path.join(LORE, "D8_characters", "characters")
    cards = {}
    if os.path.isdir(cdir):
        for name in sorted(os.listdir(cdir)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(cdir, name), "rb") as f:
                raw = f.read()
            cards[f"characters/{name}"] = raw
            card = json.loads(raw.decode("utf-8"))
            index.setdefault(card["id"], []).append({
                "kind": "character",
                "file": f"characters/{name}",
                "line": 1,
                "label": label_of(card),
            })
            trace.append({
                "id": card["id"],
                "kind": "character",
                "source": first_source(card),
                "locator": "",
                "confidence": card.get("confidence", ""),
            })
        kinds["character"] = len(cards)
    files.update(cards)

    # glossary
    gl_path = os.path.join(LORE, "02_glossary.json")
    if os.path.exists(gl_path):
        with open(gl_path, "r", encoding="utf-8") as f:
            files["glossary.json"] = dump_pretty(json.load(f))

    # world generation bundle: dimensions + random streams + inheritance
    def _load(rel):
        p = os.path.join(LORE, rel.replace("/", os.sep))
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    worldgen = {
        "dimensions": [obj for _, obj in
                       read_jsonl(os.path.join(LORE, "D1_seed", "worldgen_dimensions.jsonl"))],
        "random_streams": _load("D1_seed/random_streams.json"),
        "inheritance": _load("D1_seed/inheritance.json"),
    }
    files["worldgen.json"] = dump_pretty(worldgen)

    trace.sort(key=lambda r: (r["kind"], r["id"]))
    files["traceability.jsonl"] = b"".join(dump_line(r) for r in trace)
    files["index.json"] = dump_pretty({"ids": index})

    # digest over the emitted payload (excluding manifest itself)
    payload = sorted(files.items())
    digest = hashlib.sha256()
    for rel, data in payload:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_bytes(data).encode("ascii"))
        digest.update(b"\n")

    newest = 0.0
    for base, _dirs, names in os.walk(LORE):
        if os.sep + "canon" in base:
            continue
        for name in names:
            newest = max(newest, os.path.getmtime(os.path.join(base, name)))
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.isdigit():
        newest = float(epoch)
    stamp = datetime.fromtimestamp(newest, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "compiled_at": stamp,
        "source_digest": digest.hexdigest(),
        "entry_count": sum(kinds.values()),
        "kinds": dict(sorted(kinds.items())),
        "kind_files": {kind: OUT_NAMES[kind] for kind in sorted(kinds) if kind in OUT_NAMES},
        "files": {rel: sha256_bytes(data) for rel, data in payload},
        "unresolved": unresolved,
    }
    files["manifest.json"] = dump_pretty(manifest)
    return files


def write(files, out_dir):
    os.makedirs(os.path.join(out_dir, "characters"), exist_ok=True)
    for rel, data in files.items():
        path = os.path.join(out_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def check(files, out_dir):
    drift = []
    for rel, data in sorted(files.items()):
        path = os.path.join(out_dir, rel.replace("/", os.sep))
        if not os.path.exists(path):
            drift.append(f"missing  {rel}")
            continue
        with open(path, "rb") as f:
            if f.read().replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                drift.append(f"differs  {rel}")
    if os.path.isdir(out_dir):
        expected = {rel.replace("/", os.sep) for rel in files}
        for base, _dirs, names in os.walk(out_dir):
            for name in names:
                rel = os.path.relpath(os.path.join(base, name), out_dir)
                if rel not in expected:
                    drift.append(f"extra    {rel.replace(os.sep, '/')}")
    return drift


def main(argv=None):
    ap = argparse.ArgumentParser(description="compile lore -> lore/canon")
    ap.add_argument("--out", default=os.path.join(LORE, "canon"))
    ap.add_argument("--check", action="store_true", help="verify without writing")
    args = ap.parse_args(argv)

    files = build()
    if args.check:
        drift = check(files, args.out)
        if drift:
            print(f"canon drift: {len(drift)} file(s)")
            for line in drift[:40]:
                print(f"  {line}")
            return 1
        print(f"canon ok: {len(files)} files")
        return 0

    write(files, args.out)
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    print(f"compiled {manifest['entry_count']} entries into {args.out}")
    for kind, count in manifest["kinds"].items():
        print(f"  {kind:<12} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
