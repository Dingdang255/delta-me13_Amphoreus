"""只读世界探针：把七层结构映射到既有内核原语。

它只读、不参与演算 —— 不写状态、不改账本、也不碰指纹。`summary()` 从
`traj.final` 与 `traj.records` 取数，任何一层拿不到就把 `value` 写成 `None`
并给出 `unavailable_reason`，绝不用常量回填。

七层与原语的对应关系写在 `worlds/scepter/README.md`；本模块不含任何专有名词，
展示用的层名 / 单位 / 锚点刻度全部来自世界根的 `config/scepter.json`。
"""
from __future__ import annotations

import html
import json
import os

#: 缺省文案（不含专有名词）。世界根可以在 `config/scepter.json` 里整表覆盖。
DEFAULTS = {
    "title": "权杖状态",
    "panel_title": "权杖",
    "labels": {
        "kernel_layer": "内核层",
        "authority_layer": "权限层",
        "seed_slots": "槽位余量",
        "regen_count": "再创世计数",
        "entropy": "熵",
        "memory_store": "记忆存储",
        "external_injection": "外部注入",
    },
    "units": {
        "kernel_layer": "written_cells",
        "authority_layer": "holders",
        "seed_slots": "slots",
        "regen_count": "rounds",
        "entropy": "index",
        "memory_store": "rows",
        "external_injection": "injections",
    },
}

#: 报告里的固定顺序。
LAYER_ORDER = ("kernel_layer", "authority_layer", "seed_slots", "regen_count",
               "entropy", "memory_store", "external_injection")

#: 权杖档案（只读语料）：一行一条原文，标题行已在构建期转成 section 路径。
DOSSIER = os.path.join("lore", "D6_terminal", "scepter_dossier.jsonl")

#: 档案里「对话日志」段的段落名（中性词，不含专名）。
DIALOG_SECTION = "对话日志"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_spec(root=None, preset=None) -> dict:
    """读世界根的 `config/scepter.json`，再把预设里的 `scepter` 表并上去。

    层名 / 单位 / 面板上限属于【世界根】；再创世刻度属于【预设】——
    后者由 `preset` 传入（`DataSet.preset`），保持单一来源。
    """
    path = os.path.join(str(root or _ROOT), "config", "scepter.json")
    spec = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            spec = dict(raw)
    extra = preset.get("scepter") if isinstance(preset, dict) else None
    if isinstance(extra, dict):
        spec.update(extra)
    return spec


def _spec_meta(spec, key):
    block = (spec or {}).get("layers") or {}
    item = block.get(key) if isinstance(block, dict) else None
    item = item if isinstance(item, dict) else {}
    label = item.get("label") or DEFAULTS["labels"][key]
    unit = item.get("unit") or DEFAULTS["units"][key]
    return str(label), str(unit)


def _layer(key, spec, value, source, confidence, detail=None, reason=None):
    label, unit = _spec_meta(spec, key)
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "source": source,
        "confidence": confidence,
        "detail": dict(detail or {}),
        "unavailable_reason": reason,
    }


def _state(traj):
    final = getattr(traj, "final", None)
    return final if final is not None else traj


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None          # 排除 NaN


def _kernel_layer(st, spec):
    mat = getattr(st, "rule_matrix", None)
    if mat is None:
        return _layer("kernel_layer", spec, None, "st.rule_matrix", "low",
                      reason="state has no rule_matrix")
    shape = [int(x) for x in getattr(mat, "shape", [])]
    try:
        written = int((mat != 0).sum())
    except (AttributeError, TypeError, ValueError):
        return _layer("kernel_layer", spec, None, "st.rule_matrix", "low",
                      reason="rule_matrix is not array-like")
    gates = sorted(str(g) for g in (getattr(st, "gates", None) or ()))
    return _layer(
        "kernel_layer", spec, written, "st.rule_matrix", "high",
        detail={"shape": shape, "solver": str(getattr(st, "solver", "")),
                "gates": gates, "gate_count": len(gates)})


def _authority_layer(st, spec):
    actors = getattr(st, "actors", None)
    grants = getattr(st, "grants", None)
    authorities = getattr(st, "authorities", None)
    if actors is None and grants is None and authorities is None:
        return _layer("authority_layer", spec, None,
                      "st.actors[*].grants + st.grants + st.authorities", "low",
                      reason="state has no actor / grant tables")
    actors = actors or {}
    grants = grants or {}
    authorities = authorities or {}
    granted_actors = sorted(
        str(k) for k, rec in actors.items()
        if isinstance(rec, dict) and rec.get("grants"))
    authority_holders = sorted(str(k) for k, v in authorities.items() if v)
    value = len(granted_actors) + len(grants)
    return _layer(
        "authority_layer", spec, value,
        "st.actors[*].grants + st.grants + st.authorities", "high",
        detail={"actors": len(actors), "granted_actors": granted_actors,
                "authority_holders": authority_holders,
                "emanator_grants": len(grants),
                "entry_locked": bool(getattr(st, "entry_locked", False))})


def _seed_slots(st, spec):
    register = getattr(st, "register", None)
    slots = getattr(register, "slots", None)
    if slots is None:
        return _layer("seed_slots", spec, None, "st.register.slots[*].owner", "low",
                      reason="state has no register slots")
    slots = list(slots)
    total = len(slots)
    suppressed = {int(i) for i in (getattr(st, "suppressed", None) or ())}
    filled = 0
    vacant = 0
    available = 0
    normal_total = normal_vacant = 0
    meta_total = meta_vacant = 0
    for i, slot in enumerate(slots):
        occupied = bool(slot.filled()) if hasattr(slot, "filled") else \
            getattr(slot, "owner", None) is not None
        meta = bool(getattr(slot, "meta", False))
        if meta:
            meta_total += 1
        else:
            normal_total += 1
        if occupied:
            filled += 1
            continue
        vacant += 1
        if meta:
            meta_vacant += 1
        else:
            normal_vacant += 1
        if i not in suppressed:
            available += 1
    return _layer(
        "seed_slots", spec, vacant, "st.register.slots[*].owner", "high",
        detail={"total": total, "filled": filled, "vacant": vacant,
                "available": available, "suppressed": len(suppressed),
                "normal_total": normal_total, "normal_vacant": normal_vacant,
                "meta_total": meta_total, "meta_vacant": meta_vacant})


def _regen_layer(st, spec):
    promotions = _int(getattr(st, "promotions", None))
    if promotions is None:
        return _layer("regen_count", spec, None, "st.promotions", "low",
                      reason="state has no promotions counter")
    regen = (spec or {}).get("regen") or {}
    initial = _int(regen.get("initial")) or 0
    anchors = [a for a in (_int(x) for x in (regen.get("anchors") or []))
               if a is not None]
    index = promotions + initial
    passed = [a for a in anchors if a <= index]
    upcoming = [a for a in anchors if a > index]
    return _layer(
        "regen_count", spec, index,
        "st.promotions + config.scepter.regen.initial",
        "high" if initial == 0 else "medium",
        detail={"state_promotions": promotions, "initial": initial,
                "index": index,
                "cap": _int(regen.get("cap")), "final": _int(regen.get("final")),
                "anchor": max(passed) if passed else None,
                "next_anchor": min(upcoming) if upcoming else None,
                "anchors": anchors, "anchor_count": len(anchors),
                "anchor_source": regen.get("anchor_source")})


def _entropy_layer(st, spec):
    value = _float(getattr(st, "entropy", None))
    if value is None:
        return _layer("entropy", spec, None, "st.entropy", "low",
                      reason="state has no numeric entropy")
    noise = _float(getattr(st, "noise", None))
    return _layer(
        "entropy", spec, value, "st.entropy", "high",
        detail={"noise": noise, "noise_source": "st.noise"})


def _memory_layer(st, spec):
    bank = getattr(st, "memory_bank", None)
    if bank is None:
        return _layer("memory_store", spec, None, "st.memory_bank.shape[0]", "low",
                      reason="state has no memory bank")
    shape = getattr(bank, "shape", None)
    if not shape:
        return _layer("memory_store", spec, None, "st.memory_bank.shape[0]", "low",
                      reason="memory_bank has no shape")
    rows = int(shape[0])
    seats = len(getattr(st, "memory_seats", None) or ())
    repaired = _int((getattr(st, "score", None) or {}).get("memory_repaired")) or 0
    origin = getattr(st, "origin", None)
    closure = bool(getattr(origin, "closure", 0)) if origin is not None else False
    closed = bool(rows > 0 or repaired > 0 or closure)
    return _layer(
        "memory_store", spec, rows, "st.memory_bank.shape[0]", "high",
        detail={"memory_seats": seats, "repaired": repaired,
                "closure": closure, "closed": closed,
                "closure_ratio": 1.0 if closed else 0.0,
                "seats_source": "st.memory_seats",
                "closure_source": "st.origin.closure"})


def _external_layer(traj, st, spec):
    records = getattr(traj, "records", None)
    if records is None:
        return _layer("external_injection", spec, None,
                      "traj.records[kind == 'DISTURBANCE']", "low",
                      reason="trajectory records unavailable")
    injected = []
    for rec in records:
        if not isinstance(rec, tuple) or len(rec) < 3:
            continue
        frame, kind, payload = rec[0], rec[1], rec[2]
        if str(kind) != "DISTURBANCE":
            continue
        payload = payload if isinstance(payload, dict) else {}
        injected.append((frame, payload))
    channels = sorted({str(p.get("channel")) for _, p in injected
                       if p.get("channel")})
    capabilities = sorted({str(p.get("capability")) for _, p in injected
                           if p.get("capability")})
    return _layer(
        "external_injection", spec, len(injected),
        "traj.records[kind == 'DISTURBANCE']", "high",
        detail={"channels": channels, "channel_count": len(channels),
                "capabilities": capabilities,
                "actors": len(getattr(st, "actors", None) or {})})


def dossier_stats(root=None, path=None) -> dict:
    """只读统计权杖档案：行数 / 条目数 / 段数 / 进度里程碑 / 对话日志条数。

    读不到就整块写 `null` 并给出 `unavailable_reason`，绝不用常量回填。
    """
    path = path or os.path.join(str(root or _ROOT), DOSSIER)
    out = {"rows": None, "entries": None, "sections": None,
           "progress_milestones": [], "dialog_log_count": None,
           "unavailable_reason": None}
    if not os.path.isfile(path):
        out["unavailable_reason"] = "dossier file not found"
        return out
    rows, sections, milestones, dialog = 0, set(), [], 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                rows += 1
                section = str(row.get("section") or "")
                if section:
                    sections.add(section.split(" / ")[0])
                if DIALOG_SECTION in section:
                    dialog += 1
                if row.get("kind") == "progress":
                    value = _int(str(row.get("text") or "")
                                 .replace("进度：", "").split("%")[0].strip())
                    if value is not None and value not in milestones:
                        milestones.append(value)
    except (OSError, ValueError) as exc:
        out["unavailable_reason"] = "dossier unreadable: %s" % exc
        return out
    out.update({
        "rows": rows,
        "entries": rows,
        "sections": len(sections),
        "progress_milestones": sorted(milestones),
        "dialog_log_count": dialog,
    })
    return out


def summary(traj, spec=None) -> dict:
    """七层读数 + 再创世刻度。只读；拿不到就 `null`，不编造。"""
    spec = spec if isinstance(spec, dict) else {}
    st = _state(traj)
    layers = [
        _kernel_layer(st, spec),
        _authority_layer(st, spec),
        _seed_slots(st, spec),
        _regen_layer(st, spec),
        _entropy_layer(st, spec),
        _memory_layer(st, spec),
        _external_layer(traj, st, spec),
    ]
    mapping = {layer["key"]: layer for layer in layers}
    regen = dict(mapping["regen_count"].get("detail") or {})
    regen.pop("anchors", None)
    regen["anchor_count"] = len(mapping["regen_count"]["detail"].get("anchors") or [])
    dossier = dossier_stats()
    return {
        "title": str(spec.get("title") or DEFAULTS["title"]),
        "panel_title": str(spec.get("panel_title") or DEFAULTS["panel_title"]),
        "frame": _int(getattr(traj, "reached_frame", 0)) or 0,
        "entropy_cap": _float(spec.get("entropy_cap")) or 1.0,
        "anchor_source": str((spec.get("regen") or {}).get("anchor_source") or ""),
        "layers": layers,
        "layer_map": mapping,
        "regen": regen,
        "dossier": dossier,
        "dossier_entries": dossier["entries"],
        "dossier_sections": dossier["sections"],
        "progress_milestones": list(dossier["progress_milestones"]),
        "dialog_log_count": dossier["dialog_log_count"],
    }


def _line(layer) -> str:
    """一层的单行读数；所有文案都是中性词，专名只在世界根的配置里。"""
    key = layer.get("key")
    detail = layer.get("detail") or {}
    value = layer.get("value")
    if key == "kernel_layer":
        shape = detail.get("shape") or []
        dims = "×".join(str(x) for x in shape) if shape else "—"
        return (f"矩阵 {value} 格已写 / {dims} · 方向 {detail.get('solver') or '—'}"
                f" · 机制门 {detail.get('gate_count', 0)}")
    if key == "authority_layer":
        holders = detail.get("granted_actors") or []
        return (f"写入权限 {value} 人"
                + (f"（{'、'.join(holders)}）" if holders else "")
                + f" · 管辖 {len(detail.get('authority_holders') or [])}"
                + f" · 入口{'锁' if detail.get('entry_locked') else '开'}")
    if key == "seed_slots":
        return (f"余量 {detail.get('vacant', value)}/{detail.get('total', '—')}"
                f"（可用 {detail.get('available', '—')}，"
                f"封 {detail.get('suppressed', '—')}）"
                f" · 正席 {detail.get('normal_vacant', '—')}/"
                f"{detail.get('normal_total', '—')}"
                f" · 元席 {detail.get('meta_vacant', '—')}/"
                f"{detail.get('meta_total', '—')}")
    if key == "regen_count":
        cap = detail.get("cap")
        anchor = detail.get("anchor")
        nxt = detail.get("next_anchor")
        return (f"第 {value} 轮" + (f" / {cap}" if cap else "")
                + f" · 已过锚点 {('#' + str(anchor)) if anchor is not None else '—'}"
                + f" · 下一锚点 {('#' + str(nxt)) if nxt is not None else '—'}")
    if key == "entropy":
        noise = detail.get("noise")
        return f"{float(value):.4f}" + (f" · 强度 {noise:.4f}" if noise is not None else "")
    if key == "memory_store":
        return (f"{value} 行 · 闭合 {'是' if detail.get('closed') else '否'}"
                f" · 记忆席 {detail.get('memory_seats', 0)}"
                f" · 再补 {detail.get('repaired', 0)}")
    if key == "external_injection":
        return (f"{value} 次 · 通道 {detail.get('channel_count', 0)}"
                + (f"（{'、'.join(detail.get('channels') or [])}）"
                   if detail.get("channels") else ""))
    return str(value)


def render(summary_) -> list:
    """把 `summary()` 渲染成报告【九】的缩进行。"""
    lines = []
    for layer in summary_.get("layers") or []:
        label = str(layer.get("label") or layer.get("key"))
        if layer.get("value") is None:
            reason = layer.get("unavailable_reason") or "unavailable"
            lines.append(f"  {label:<10} —  （{reason}）")
            continue
        lines.append(f"  {label:<10} {_line(layer)}")
    regen = summary_.get("regen") or {}
    if regen.get("anchor_count"):
        source = summary_.get("anchor_source") or "—"
        lines.append(f"  {'刻度':<10} {regen.get('anchor_count')} 个锚点"
                     f" · 上限 {regen.get('cap') or '—'}"
                     f" · 来源 {source}")
    dossier = summary_.get("dossier") or {}
    if dossier.get("entries") is None:
        reason = dossier.get("unavailable_reason") or "unavailable"
        lines.append(f"  {'档案':<10} —  （{reason}）")
    else:
        marks = dossier.get("progress_milestones") or []
        span = f"{marks[0]}%…{marks[-1]}%" if marks else "—"
        lines.append(f"  {'档案':<10} {dossier.get('rows')} 行 / "
                     f"{dossier.get('sections')} 段 / 进度里程碑 {span}"
                     f" · 对话日志 {dossier.get('dialog_log_count')} 行")
    return lines


def _bar_ratio(value, cap):
    if value is None:
        return None
    if not cap:
        return None
    return max(0.0, min(1.0, float(value) / float(cap)))


def _bar_row(label, value_text, source_text, ratio) -> str:
    track = ('<div class="bar"></div>' if ratio is None else
             f'<div class="bar"><i style="width:{ratio * 100.0:.1f}%"></i></div>')
    return (
        '<div class="trow"><div class="trow-main">'
        f'<div class="tlabel">{html.escape(str(label))}'
        f'<span class="tch">{html.escape(str(source_text))}</span></div>'
        f'<div class="tbar">{track}</div>'
        f'<div class="tval">{html.escape(str(value_text))}</div>'
        '</div></div>')


def panels_html(summary_, title=None) -> str:
    """权杖面板：复用既有的 `.bar` / `.bar i`，只为余量与熵各画一根条。"""
    mapping = (summary_ or {}).get("layer_map") or {}
    if not mapping:
        return ""
    seed = mapping.get("seed_slots") or {}
    ent = mapping.get("entropy") or {}
    seed_detail = seed.get("detail") or {}
    total = _int(seed_detail.get("total")) or 0
    vacant = _int(seed_detail.get("vacant"))
    seed_ratio = (vacant / total) if total and vacant is not None else None
    seed_text = (f"{vacant}/{total}" if vacant is not None and total else "—")
    ent_value = _float(ent.get("value"))
    ent_ratio = _bar_ratio(ent_value, (summary_ or {}).get("entropy_cap"))
    ent_text = "—" if ent_value is None else f"{ent_value:.4f}"
    regen = (summary_ or {}).get("regen") or {}
    mem = mapping.get("memory_store") or {}
    ext = mapping.get("external_injection") or {}
    head = title or (summary_ or {}).get("panel_title") or DEFAULTS["panel_title"]
    parts = [
        f"<h2>{html.escape(str(head))}</h2>",
        '<div class="panel">',
        _bar_row(seed.get("label") or DEFAULTS["labels"]["seed_slots"],
                 seed_text, seed.get("source") or "st.register.slots",
                 seed_ratio),
        _bar_row(ent.get("label") or DEFAULTS["labels"]["entropy"],
                 ent_text, ent.get("source") or "st.entropy", ent_ratio),
        f'<div class="sub">七层读数 · 第 {regen.get("index", "—")} 轮'
        f' · 记忆 {mem.get("value", "—")} 行'
        f' · 外部注入 {ext.get("value", "—")} 次</div>',
        "</div>",
    ]
    return "\n".join(parts)
