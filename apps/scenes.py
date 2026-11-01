"""Read-only scene catalogue built from the compiled plot expansions.

Each plot record already carries the corpus' own account of a chapter segment:
``before / during / after`` plus references to dialogue lines, other scenes and
mechanism records. This module only orders them, links them and reports
coverage -- it never writes new prose.

The DAG is deliberately thin: edges come from version order (3.0 -> 3.7), which
is the only ordering the corpus actually attests.

``load`` keeps the original plot-only view. ``load_all`` merges the plot
catalogue with the per-mission scenes into one frame-ordered timeline: the
first frame of a record is the smallest ``frame`` among the preset beats that
reference it (directly, or through the event of the same mission). When no
beat attests a frame the value stays ``None`` and the reason is appended to
``gap`` -- for plot records. Per-mission scenes whose event is referenced by
no beat are projected inside their version's frame interval instead, in
reading order; such frames are marked ``first_frame_source="projected"`` with
``confidence="C"`` and the caveat is appended to ``gap``.
"""
from __future__ import annotations

import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: 预设投递事件表 —— 只用来读每个版本的帧区间（只读，不参与演算）。
_PRESET_EVENTS = os.path.join(_ROOT, "presets", "plot-full", "events.jsonl")

_FRAME_GAP_PLOT = "预设节拍未引用该剧情，无法确定首次出现帧（first_frame），记 null"
_FRAME_GAP_MISSION = "缺少 mission_id，无法定位同任务事件，first_frame 记 null"
_FRAME_GAP_EVENT = "mission_id 在事件索引中找不到同任务事件，first_frame 记 null"
_FRAME_GAP_BEAT = "同任务事件未被任何预设节拍引用，first_frame 记 null"
_LOOP_GAP = "预设节拍未标注再创世轮次（loop），无法从 beat 上下文确定，记 null"
_FRAME_GAP_PROJECTED = "帧为按章节区间投影，非原文时序"
_FRAME_GAPS = {_FRAME_GAP_PLOT, _FRAME_GAP_MISSION, _FRAME_GAP_EVENT,
               _FRAME_GAP_BEAT}


class SceneError(RuntimeError):
    """Raised when a scene record cannot be ordered or resolved."""


def _version_key(version: str) -> tuple:
    try:
        major, minor = str(version).split(".")
        return (int(major), int(minor))
    except (ValueError, AttributeError):
        return (99, 99)


def _min_frame(rows) -> int | None:
    """`frame` 字段的最小值；没有可用的帧就返回 None。"""
    frames = [row.get("frame") for row in rows]
    frames = [f for f in frames if isinstance(f, int) and not isinstance(f, bool)]
    return min(frames) if frames else None


def _as_loop(value) -> int | None:
    """把记录里的 `loop` 读成整数；不是轮次就返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _loop_from(bundle, beats) -> tuple:
    """节拍及其引用记录里 `loop` 的最小值；取不到返回 (None, 原因)。"""
    rows = list(beats)
    for beat in beats:
        rows.extend(bundle.get(str(ref)) for ref in beat.get("lore_refs") or [])
    loops = [loop for loop in (_as_loop(row) for row in rows if row is not None)
             if loop is not None]
    return (min(loops), "") if loops else (None, _LOOP_GAP)


def _steps(during) -> list[str]:
    """`during` 统一成有序步骤；wiki 文本用「 → 」串起步骤，按同一分隔切开。"""
    if isinstance(during, (list, tuple)):
        return [str(item).strip() for item in during if str(item).strip()]
    return [part.strip() for part in str(during or "").split(" → ") if part.strip()]


def _source_list(scene: dict) -> list[str]:
    value = scene.get("sources") or scene.get("source")
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in (value or []) if str(item).strip()]


def _merge_gap(gap, extra) -> str:
    parts = []
    if isinstance(gap, (list, tuple)):
        parts.extend(gap)
    elif gap:
        parts.append(gap)
    parts.extend(extra)
    return "；".join(str(part).strip() for part in parts if str(part or "").strip())


def _beat_rows(beats) -> list[dict]:
    rows = [
        {"id": beat.id, "frame": beat.get("frame"),
         "presets": list(beat.get("presets") or [])}
        for beat in beats
    ]
    rows.sort(key=lambda row: (row["frame"] is None, row["frame"] or 0, row["id"]))
    return rows


def _evt_index(bundle) -> dict[str, list[str]]:
    """mission_id -> 同任务的事件 id（`mission_id` 与 `mission_ids` 都算）。"""
    out: dict[str, list[str]] = {}
    for entry in bundle.of_kind("event"):
        ids = [entry.get("mission_id")] + list(entry.get("mission_ids") or [])
        for mission in ids:
            mission = str(mission or "")
            if mission and entry.id not in out.setdefault(mission, []):
                out[mission].append(entry.id)
    return {mission: sorted(ids) for mission, ids in out.items()}


def _dialogue_index(bundle) -> dict[str, list[str]]:
    """scene_id -> 该场景的台词 id，按 `order` 升序（同序按 id 稳定）。"""
    rows: dict[str, list[tuple]] = {}
    for entry in bundle.of_kind("wiki_dialogue"):
        scene_id = entry.get("scene_id")
        if not scene_id:
            continue
        order = entry.get("order")
        rank = order if isinstance(order, int) and not isinstance(order, bool) else 0
        rows.setdefault(str(scene_id), []).append((rank, entry.id))
    return {scene: [rid for _order, rid in sorted(items)]
            for scene, items in rows.items()}


def load(bundle) -> list[dict]:
    """剧情条目，附带「哪些预设节拍演到了它」（只读反查 `preset_beat`）。"""
    scenes = [dict(entry.data) for entry in bundle.of_kind("plot")]
    for scene in scenes:
        scene["beats"] = [
            {"id": beat.id, "frame": beat.get("frame"),
             "presets": list(beat.get("presets") or [])}
            for beat in bundle.beats_for(str(scene.get("id")))
        ]
    scenes.sort(key=lambda s: (_version_key(s.get("version", "")), s.get("id", "")))
    return scenes


def _version_of_ref(bundle, ref: str) -> str:
    """canon id 所属版本：先按剧情记录找，再按事件记录找；找不到返回空串。"""
    for kind in ("plot", "event"):
        entry = bundle.get(str(ref), kind)
        if entry is not None:
            return str(entry.get("version") or "")
    return ""


def _version_frames(bundle, path: str | None = None) -> dict[str, tuple[int, int]]:
    """每个版本在预设事件表里的帧区间（该版本事件的 min/max frame）。

    事件本身不带版本，版本取自它引用的剧情 / 事件记录。读不到文件就返回空表
    —— 调用方据此跳过投影，而不是编一个帧。
    """
    path = path or _PRESET_EVENTS
    out: dict[str, list[int]] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                frame = row.get("frame")
                if not isinstance(frame, int) or isinstance(frame, bool):
                    continue
                version = ""
                for ref in row.get("lore_ref") or []:
                    version = _version_of_ref(bundle, ref)
                    if version:
                        break
                if not version:
                    continue
                bounds = out.setdefault(version, [frame, frame])
                bounds[0] = min(bounds[0], frame)
                bounds[1] = max(bounds[1], frame)
    except (OSError, ValueError):
        return {}
    return {version: (lo, hi) for version, (lo, hi) in out.items()}


def _project_frames(bundle, views: list[dict]) -> None:
    """给没有首帧的逐任务场景在【同版本帧区间】内按阅读序线性投影一个首帧。

    只在场景自身没有任何节拍佐证时使用；投影结果写明来源与缺口，不冒充时序。
    """
    intervals = _version_frames(bundle)
    if not intervals:
        return
    groups: dict[str, list[dict]] = {}
    for view in views:
        if view.get("first_frame") is not None:
            continue
        version = str(view.get("version") or "")
        if version in intervals:
            groups.setdefault(version, []).append(view)
    for version, items in groups.items():
        items.sort(key=lambda view: str(view.get("id") or ""))
        lo, hi = intervals[version]
        count = len(items)
        for i, view in enumerate(items):
            frame = lo if count == 1 else int(round(lo + (hi - lo) * i / (count - 1)))
            view["first_frame"] = frame
            view["first_frame_source"] = "projected"
            view["confidence"] = "C"
            kept = [part for part in str(view.get("gap") or "").split("；")
                    if part and part not in _FRAME_GAPS]
            view["gap"] = _merge_gap("；".join(kept), [_FRAME_GAP_PROJECTED])


def _plot_view(bundle, entry) -> dict:
    """一条剧情记录的统一视图：首帧 / 轮次 / 四段文本 / 节拍 / 台词。"""
    data = dict(entry.data)
    beats = bundle.beats_for(entry.id)
    first_frame = data.get("first_frame")
    if first_frame is None:
        first_frame = _min_frame(beats)
    loop, loop_gap = _loop_from(bundle, beats)
    expansion = data.get("expansion") or {}
    reasons = [] if first_frame is not None else [_FRAME_GAP_PLOT]
    if loop is None:
        reasons.append(loop_gap)
    sources = _source_list(data)
    return {
        "id": entry.id,
        "title": data.get("scene"),
        "version": data.get("version"),
        "chapter": data.get("chapter"),
        "first_frame": first_frame,
        "first_frame_source": "beat" if first_frame is not None else "none",
        "loop": loop,
        "before": expansion.get("before"),
        "during": _steps(expansion.get("during")),
        "after": expansion.get("after"),
        "gap": _merge_gap(data.get("gap"), reasons),
        "beats": _beat_rows(beats),
        "dialogue_refs": list(data.get("dialogue_refs") or []),
        "source": sources,
        "sources": sources,
        "confidence": data.get("confidence", ""),
        "kind": "plot",
        "scene_refs": list(data.get("scene_refs") or []),
        "mechanism_refs": list(data.get("mechanism_refs") or []),
        "verbatim_available": bool(data.get("verbatim_available")),
    }


def _wiki_view(bundle, entry, evts) -> dict:
    """一条逐任务场景的统一视图；首帧由同任务事件的节拍给出。"""
    data = dict(entry.data)
    mission = str(data.get("mission_id") or "")
    candidates = list(evts.get(mission, ())) if mission else []
    beats = []
    seen = set()
    for event_id in candidates:
        for beat in bundle.beats_for(event_id):
            if beat.id not in seen:
                seen.add(beat.id)
                beats.append(beat)
    first_frame = data.get("first_frame")
    if first_frame is None:
        first_frame = _min_frame(beats)
    loop, loop_gap = _loop_from(bundle, beats)
    reasons = []
    if first_frame is None:
        if not mission:
            reasons.append(_FRAME_GAP_MISSION)
        elif not candidates:
            reasons.append(_FRAME_GAP_EVENT)
        else:
            reasons.append(_FRAME_GAP_BEAT)
    if loop is None:
        reasons.append(loop_gap)
    sources = _source_list(data)
    return {
        "id": entry.id,
        "title": data.get("title") or data.get("mission"),
        "version": data.get("version"),
        "chapter": data.get("chapter"),
        "first_frame": first_frame,
        "first_frame_source": "beat" if first_frame is not None else "none",
        "loop": loop,
        "before": data.get("before"),
        "during": _steps(data.get("during")),
        "after": data.get("after"),
        "gap": _merge_gap(data.get("gap"), reasons),
        "beats": _beat_rows(beats),
        "dialogue_refs": [],
        "source": sources,
        "sources": sources,
        "confidence": data.get("confidence", ""),
        "kind": "wiki_scene",
        "scene_refs": [],
        "mechanism_refs": [],
        "verbatim_available": False,
    }


def _frame_order(scene: dict) -> tuple:
    frame = scene.get("first_frame")
    return (frame is None, frame or 0,
            _version_key(scene.get("version", "")), scene.get("id", ""))


def load_all(bundle, *, upto_frame: int | None = None) -> list[dict]:
    """剧情 + 逐任务场景的统一视图，按首帧排序（无帧的排在最后）。

    逐任务场景若没有节拍佐证，先在【同版本帧区间】内按阅读序投影一个首帧
    （见 `_project_frames`，带 `first_frame_source="projected"` 与缺口说明）。

    `upto_frame` 非空时只保留「首帧已知且不晚于该帧」的条目 —— 无首帧的
    条目一律不出现在过滤视图里（未过滤时它们的 `gap` 已写明原因）。
    """
    rows = [_plot_view(bundle, entry) for entry in bundle.of_kind("plot")]
    evts = _evt_index(bundle)
    wiki = [_wiki_view(bundle, entry, evts)
            for entry in bundle.of_kind("wiki_scene")]
    _project_frames(bundle, wiki)
    rows.extend(wiki)
    rows.sort(key=_frame_order)

    if upto_frame is not None:
        rows = [row for row in rows
                if row.get("first_frame") is not None
                and row["first_frame"] <= upto_frame]

    refs = None
    for row in rows:
        if row.get("kind") != "wiki_scene":
            continue
        if refs is None:
            refs = _dialogue_index(bundle)
        row["dialogue_refs"] = list(refs.get(str(row.get("id")), []))
    return rows


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
    if any(key in scene for key in ("before", "during", "after")):
        before = scene.get("before")
        during = scene.get("during")
        after = scene.get("after")
    else:
        expansion = scene.get("expansion") or {}
        before = expansion.get("before")
        during = expansion.get("during")
        after = expansion.get("after")
    acts = []
    if before:
        acts.append({"phase": "before", "text": before})
    for item in _steps(during):
        acts.append({"phase": "during", "text": item})
    if after:
        acts.append({"phase": "after", "text": after})
    first_frame = scene.get("first_frame")
    if first_frame is None:
        first_frame = _min_frame(scene.get("beats") or [])
    source = scene.get("first_frame_source")
    if not source:
        source = "beat" if first_frame is not None else "none"
    return {
        "id": scene.get("id"),
        "version": scene.get("version"),
        "chapter": scene.get("chapter"),
        "title": scene.get("scene") or scene.get("title"),
        "first_frame": first_frame,
        "first_frame_source": source,
        "loop": scene.get("loop"),
        "acts": acts,
        "dialogue_refs": list(scene.get("dialogue_refs") or []),
        "scene_refs": list(scene.get("scene_refs") or []),
        "mechanism_refs": list(scene.get("mechanism_refs") or []),
        "beats": list(scene.get("beats") or []),
        "verbatim_available": bool(scene.get("verbatim_available")),
        "gap": scene.get("gap", ""),
        "sources": _source_list(scene),
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
