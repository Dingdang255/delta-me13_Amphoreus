"""Read-only scene catalogue built from the compiled plot expansions.

Each plot record already carries the corpus' own account of a chapter segment:
``before / during / after`` plus references to dialogue lines, other scenes and
mechanism records. This module only orders them, links them and reports
coverage -- it never writes new prose.

The DAG is deliberately thin: edges come from version order (3.0 -> 3.7), which
is the only ordering the corpus actually attests.
"""
from __future__ import annotations


class SceneError(RuntimeError):
    """Raised when a scene record cannot be ordered or resolved."""


def _version_key(version: str) -> tuple:
    try:
        major, minor = str(version).split(".")
        return (int(major), int(minor))
    except (ValueError, AttributeError):
        return (99, 99)


def load(bundle) -> list[dict]:
    scenes = [dict(entry.data) for entry in bundle.of_kind("plot")]
    scenes.sort(key=lambda s: (_version_key(s.get("version", "")), s.get("id", "")))
    return scenes


def chapter_order(scenes: list[dict]) -> list[str]:
    seen = []
    for scene in scenes:
        version = str(scene.get("version", ""))
        if version and version not in seen:
            seen.append(version)
    return sorted(seen, key=_version_key)


def dag(scenes: list[dict]) -> dict:
    """Linear chapter chain: every scene points at the next one in order."""
    nodes = [s.get("id") for s in scenes]
    edges = [[nodes[i], nodes[i + 1]] for i in range(len(nodes) - 1)]
    return {"nodes": nodes, "edges": edges}


def coverage(scenes: list[dict]) -> dict:
    out: dict[str, int] = {}
    for scene in scenes:
        version = str(scene.get("version", ""))
        out[version] = out.get(version, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: _version_key(kv[0])))


def narrate(scene: dict) -> dict:
    """Flatten one scene into ordered acts plus the references a renderer needs."""
    expansion = scene.get("expansion") or {}
    acts = []
    before = expansion.get("before")
    if before:
        acts.append({"phase": "before", "text": before})
    for item in expansion.get("during") or []:
        acts.append({"phase": "during", "text": item})
    after = expansion.get("after")
    if after:
        acts.append({"phase": "after", "text": after})
    return {
        "id": scene.get("id"),
        "version": scene.get("version"),
        "chapter": scene.get("chapter"),
        "title": scene.get("scene"),
        "acts": acts,
        "dialogue_refs": list(scene.get("dialogue_refs") or []),
        "scene_refs": list(scene.get("scene_refs") or []),
        "mechanism_refs": list(scene.get("mechanism_refs") or []),
        "verbatim_available": bool(scene.get("verbatim_available")),
        "gap": scene.get("gap", ""),
        "sources": list(scene.get("sources") or []),
        "confidence": scene.get("confidence", ""),
    }


def unresolved(scene: dict, known: dict[str, set]) -> list[str]:
    """References that do not resolve inside the bundle."""
    problems = []
    for ref in scene.get("dialogue_refs") or []:
        if ref not in known["dialogue"]:
            problems.append(f"{scene.get('id')}: dialogue {ref}")
    for ref in scene.get("scene_refs") or []:
        if ref not in known["scene"]:
            problems.append(f"{scene.get('id')}: scene {ref}")
    for ref in scene.get("mechanism_refs") or []:
        if not (ref in known["micro_event"] or ref in known["trend"] or ref in known["worldgen"]):
            problems.append(f"{scene.get('id')}: mechanism {ref}")
    return problems
