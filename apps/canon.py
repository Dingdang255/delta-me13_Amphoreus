"""Read-only loader for the compiled lore corpus.

The bundle is *data*, not story: it knows ids, kinds and provenance only.
No title, name or line of prose lives in this module -- callers pass ids and
receive records; rendering belongs to the presentation layer.

Ids are namespaced by kind: the same identifier may appear both in the entity
catalog and as an agent card, and those are two different views, not a clash.

Layout produced by ``tools/lore_compile.py``::

    lore/canon/
        manifest.json          schema version, counts, per-file sha256
        index.json             id -> [{kind, file, line, label}, ...]
        traceability.jsonl     {kind, id, source, locator, confidence}
        <kind>.jsonl           one file per kind
        characters/CHR-*.json  agent cards
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Iterable, Iterator

SCHEMA_VERSION = "1"

DEFAULT_CANON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lore", "canon"
)

#: kinds that are loaded lazily as line-delimited JSON
JSONL_KINDS = (
    "entity", "event", "term", "conflict", "unknown", "worldgen",
    "trend", "micro_event", "causal",
    "wiki_claim", "plot", "gap",
    "scene", "dialogue", "loop", "anchor",
    "terminal", "multilingual",
    "fragment", "crosscheck", "debunked",
    "relation", "scenario", "guard",
)

#: when an id exists in several kinds, these win in this order
KIND_PRIORITY = (
    "character", "scene", "dialogue", "terminal", "loop", "anchor",
    "worldgen", "micro_event", "trend", "causal", "scenario", "guard",
    "relation", "plot", "wiki_claim", "gap", "event", "term",
    "fragment", "crosscheck", "debunked", "multilingual",
    "conflict", "unknown", "entity",
)


class CanonError(RuntimeError):
    """Raised when the bundle is missing, stale or inconsistent."""


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str
    data: dict

    def get(self, key, default=None):
        return self.data.get(key, default)


class CanonBundle:
    """Immutable, verifiable view over one compiled bundle."""

    def __init__(self, root: str, manifest: dict, index: dict,
                 records: dict, trace: dict):
        self.root = root
        self.manifest = manifest
        self._index = index
        self._records = records
        self._trace = trace

    # -- construction -----------------------------------------------------
    @classmethod
    def load(cls, root: str | None = None, verify: bool = True) -> "CanonBundle":
        root = os.path.abspath(root or DEFAULT_CANON_DIR)
        manifest_path = os.path.join(root, "manifest.json")
        if not os.path.exists(manifest_path):
            raise CanonError(f"no compiled bundle at {root}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise CanonError(
                f"schema version {manifest.get('schema_version')!r} != {SCHEMA_VERSION!r}"
            )

        if verify:
            for rel, digest in manifest.get("files", {}).items():
                path = os.path.join(root, rel.replace("/", os.sep))
                if not os.path.exists(path):
                    raise CanonError(f"missing bundle file {rel}")
                with open(path, "rb") as f:
                    got = hashlib.sha256(f.read()).hexdigest()
                if got != digest:
                    raise CanonError(f"bundle file {rel} does not match manifest")

        with open(os.path.join(root, "index.json"), "r", encoding="utf-8") as f:
            index = json.load(f).get("ids", {})

        records: dict[tuple[str, str], Entry] = {}
        kind_files = manifest.get("kind_files") or {k: f"{k}.jsonl" for k in JSONL_KINDS}
        for kind, rel in kind_files.items():
            path = os.path.join(root, str(rel).replace("/", os.sep))
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    records[(kind, obj["id"])] = Entry(obj["id"], kind, obj)

        char_dir = os.path.join(root, "characters")
        if os.path.isdir(char_dir):
            for name in sorted(os.listdir(char_dir)):
                if not name.endswith(".json"):
                    continue
                with open(os.path.join(char_dir, name), "r", encoding="utf-8") as f:
                    obj = json.load(f)
                records[("character", obj["id"])] = Entry(obj["id"], "character", obj)

        trace: dict[tuple[str, str], dict] = {}
        trace_path = os.path.join(root, "traceability.jsonl")
        if os.path.exists(trace_path):
            with open(trace_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    trace[(row["kind"], row["id"])] = row

        return cls(root, manifest, index, records, trace)

    # -- queries ----------------------------------------------------------
    @property
    def kinds(self) -> dict:
        return dict(self.manifest.get("kinds", {}))

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, rid: object) -> bool:
        return isinstance(rid, str) and rid in self._index

    def get(self, rid: str, kind: str | None = None) -> Entry | None:
        if kind is not None:
            return self._records.get((kind, rid))
        for candidate in KIND_PRIORITY:
            entry = self._records.get((candidate, rid))
            if entry is not None:
                return entry
        return None

    def get_all(self, rid: str) -> list[Entry]:
        return [entry for (kind, rid2), entry in self._records.items() if rid2 == rid]

    def require(self, rid: str, kind: str | None = None) -> Entry:
        entry = self.get(rid, kind)
        if entry is None:
            raise CanonError(f"unknown id {rid!r} (kind={kind!r})")
        return entry

    def of_kind(self, kind: str) -> Iterator[Entry]:
        for (k, _rid), entry in self._records.items():
            if k == kind:
                yield entry

    def ids_of_kind(self, kind: str) -> set[str]:
        return {e.id for e in self.of_kind(kind)}

    def trace(self, rid: str, kind: str | None = None) -> dict:
        if kind is not None:
            return dict(self._trace.get((kind, rid), {}))
        for candidate in KIND_PRIORITY:
            row = self._trace.get((candidate, rid))
            if row is not None:
                return dict(row)
        return {}

    def label(self, rid: str, kind: str | None = None) -> str:
        rows = self._index.get(rid, [])
        if kind is not None:
            for row in rows:
                if row.get("kind") == kind:
                    return row.get("label", "")
            return ""
        for candidate in KIND_PRIORITY:
            for row in rows:
                if row.get("kind") == candidate and row.get("label"):
                    return row["label"]
        return rows[0].get("label", "") if rows else ""

    # -- integrity --------------------------------------------------------
    def unresolved_refs(self) -> list[str]:
        """Dangling references that would break scene rendering."""
        problems: list[str] = []
        scenes = self.ids_of_kind("scene")
        lines = self.ids_of_kind("dialogue")
        chars = self.ids_of_kind("character")
        for entry in self.of_kind("dialogue"):
            sid = entry.get("scene_id")
            if sid and sid not in scenes:
                problems.append(f"{entry.id}: scene {sid}")
            for nxt in entry.get("next") or []:
                if nxt not in lines:
                    problems.append(f"{entry.id}: next {nxt}")
        for entry in self.of_kind("scenario"):
            ch = entry.get("character")
            if ch and ch not in chars:
                problems.append(f"{entry.id}: character {ch}")
        for entry in self.of_kind("character"):
            for rel in entry.get("relations") or []:
                target = rel.get("target")
                if target and target not in chars:
                    problems.append(f"{entry.id}: relation {target}")
        return problems

    def validate(self) -> None:
        problems = self.unresolved_refs()
        if problems:
            raise CanonError(f"{len(problems)} dangling reference(s): {problems[:5]}")

    def entries(self) -> Iterable[Entry]:
        return self._records.values()
