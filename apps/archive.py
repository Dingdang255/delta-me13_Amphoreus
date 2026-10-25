"""只读档案层：把预设里的实验档案 / 异常记录 / 实验进度渲染成报告章节。

它只读、不参与演算 —— 不写状态、不改账本、也不碰指纹。判定「已抵达 / 未抵达」
与「本轨道是否发生」只用三处既有读数：`traj.reached_frame`、`traj.deadlock`、
`traj.final.score`。档案文案全部来自 `presets/<name>/archive.json`，本模块不写死
任何剧情名词。
"""
from __future__ import annotations

import json
import os

#: `titles` 缺省时的三节标题；预设可整表覆盖，也可只改其中一项。
DEFAULT_TITLES = {"archive": "实验档案", "anomalies": "异常记录", "progress": "实验进度"}


def _bad(path, field, why):
    """统一的不合法档案异常：带上文件与字段名，便于直接改预设。"""
    return ValueError(f"{path}:{field} 档案不合法：{why}")


def _text(item, key, path, where):
    """取一个必填的非空字符串字段。"""
    val = item.get(key)
    if not isinstance(val, str) or not val.strip():
        raise _bad(path, f"{where}.{key}", "必须是非空字符串")
    return val


def _frame(item, path, where, required=False):
    """取可选的 `frame`：非负整数；`required` 为真时缺省即报错。"""
    val = item.get("frame")
    if val is None:
        if required:
            raise _bad(path, f"{where}.frame", "必须是非负整数")
        return None
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        raise _bad(path, f"{where}.frame", f"必须是非负整数（得到 {val!r}）")
    return int(val)


def _progress(item, path, where):
    if not isinstance(item, dict):
        raise _bad(path, where, "每项必须是 JSON 对象")
    pct = item.get("percent")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 0 <= pct <= 100:
        raise _bad(path, f"{where}.percent", f"必须是 0–100 的数字（得到 {pct!r}）")
    return {"percent": pct,
            "frame": _frame(item, path, where, required=True),
            "label": _text(item, "label", path, where)}


def _archive(item, path, where):
    if not isinstance(item, dict):
        raise _bad(path, where, "每项必须是 JSON 对象")
    out = {key: _text(item, key, path, where) for key in ("id", "title", "body")}
    out["frame"] = _frame(item, path, where)
    for key in ("stage", "loop"):
        val = item.get(key)
        if val is None:
            continue
        if not isinstance(val, str) or not val.strip():
            raise _bad(path, f"{where}.{key}", "必须是非空字符串")
        out[key] = val
    return out


def _anomaly(item, path, where):
    if not isinstance(item, dict):
        raise _bad(path, where, "每项必须是 JSON 对象")
    out = {key: _text(item, key, path, where) for key in ("id", "title", "body")}
    event = item.get("event")
    if event is not None:
        if not isinstance(event, str) or not event.strip():
            raise _bad(path, f"{where}.event", "必须是非空字符串")
        out["event"] = event
    return out


def load_archive(path):
    """读 `archive.json`，返回补齐缺省值并排好序的档案表。

    文件不存在 ⇒ `{}`（预设可以没有档案层）。任何一处不合法都立刻抛
    `ValueError`，消息里带文件与字段名。
    """
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise _bad(path, "<root>", f"不是合法 JSON（{exc.msg}）") from exc
    if not isinstance(raw, dict):
        raise _bad(path, "<root>", "顶层必须是 JSON 对象")

    titles = dict(DEFAULT_TITLES)
    got = raw.get("titles")
    if got is not None:
        if not isinstance(got, dict):
            raise _bad(path, "titles", "必须是 JSON 对象")
        for key in DEFAULT_TITLES:
            val = got.get(key)
            if val is None:
                continue
            if not isinstance(val, str) or not val.strip():
                raise _bad(path, f"titles.{key}", "必须是非空字符串")
            titles[key] = val

    out = {"titles": titles}
    for key, check in (("progress", _progress), ("archive", _archive),
                       ("anomalies", _anomaly)):
        rows = raw.get(key)
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise _bad(path, key, "必须是列表")
        out[key] = [check(row, path, f"{key}[{i}]") for i, row in enumerate(rows)]

    out["progress"].sort(key=lambda r: r["frame"])
    # frame 缺失 ⇒ 视为 ∞（排在最后），同档再按 id 排。
    out["archive"].sort(key=lambda r: (r["frame"] is None,
                                       r["frame"] if r["frame"] is not None else 0,
                                       r["id"]))
    return out


def _pct(val):
    """百分数的写法：整数就写整数，小数保留原样（3.0 → 3）。"""
    return f"{val:g}"


def _progress_line(progress, reached):
    """wiki 口径的里程碑进度：报告「已抵达哪一档、下一档在哪一帧」。"""
    if not progress:
        return None
    done = [p for p in progress if p["frame"] <= reached]
    if not done:
        nxt = progress[0]
        return f"已抵达 0%（下一档 {_pct(nxt['percent'])}% @ {nxt['frame']}）"
    if len(done) == len(progress):
        return "已抵达 100%"
    nxt = progress[len(done)]
    return (f"已抵达 {_pct(done[-1]['percent'])}%"
            f"（下一档 {_pct(nxt['percent'])}% @ {nxt['frame']}）")


def _archive_lines(item, reached):
    """一条实验档案：状态标记 + 编号 · 阶段/循环 · 标题，正文另起一行缩进六格。"""
    frame = item.get("frame")
    if frame is None:
        mark = "[—]"
    elif frame <= reached:
        mark = "[已抵达]"
    else:
        mark = "[未抵达]"
    where = item.get("loop") or item.get("stage") or "—"
    return [f"{mark} {item['id']} · {where} · {item['title']}",
            "      " + item["body"]]


def _happened(item, traj):
    """异常记录是否在本轨道发生：无 event ⇒ None（写作「—」）。"""
    event = item.get("event")
    if not event:
        return None
    if event == "deadlock":
        return bool(getattr(traj, "deadlock", False))
    score = getattr(getattr(traj, "final", None), "score", None) or {}
    return f"emitted_{event}" in score


def render(ctx, data, traj, arc):
    """渲染两节：`【六】实验档案` 与 `【七】异常记录`。只读，不写任何状态。

    `ctx` / `data` 只为与其它渲染器保持同一签名，本函数不向它们取词 ——
    所有文案都来自 `arc`（即 `presets/<name>/archive.json`）。
    """
    if not arc:
        return []
    titles = dict(DEFAULT_TITLES)
    titles.update(arc.get("titles") or {})
    reached = int(getattr(traj, "reached_frame", 0) or 0)

    lines = []
    head = _progress_line(arc.get("progress") or [], reached)
    if head:
        lines.append(f"{titles['progress']}    {head}")
    for item in arc.get("archive") or []:
        lines.extend(_archive_lines(item, reached))

    anomalies = []
    for item in arc.get("anomalies") or []:
        hit = _happened(item, traj)
        mark = "[—]" if hit is None else ("[本轨道发生]" if hit else "[本轨道未发生]")
        anomalies.append(f"{mark} {item['id']} · {item['title']}")
        anomalies.append("      " + item["body"])

    return [("【六】" + titles["archive"], lines),
            ("【七】" + titles["anomalies"], anomalies)]
