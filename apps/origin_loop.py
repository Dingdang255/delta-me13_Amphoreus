"""回望驱动：锚点注入 + 固定点重演。

叙事里「回到几个缺失节点、补上那一手」在这里落成一条**严格单向**的算法：

1. 第一遍正向跑，扫 `nodes.json` 的每个节点是否缺失；同时记下原初首次成形的帧。
2. 若缺失，第二遍从帧 0 重演，在缺失帧投递 `origin_anchor`（普通外生能力，
   exact frame；只在原初已成形且能量足够时生效）。
3. 重演后重新扫描；新缺失并入锚点继续迭代 —— 锚点集合按 `(frame, order, node)`
   排序，固定点最多 `origin_max_iters` 次。
4. 锚点稳定、无缺失、`repaid >= borrowed`、自我度达标 ⇒ `origin_closed`；
   仍有缺失 ⇒ `origin_unstable`；无缺失但借还/自我度不达标 ⇒ `origin_open`；
   第一遍原初未成形 ⇒ `origin_absent`，不跑锚点。

**不做逐帧反向因果**：每一遍都从帧 0 单向重演，历史帧从不被回写。叙事上的
「回到过去」= 带着未来的记忆，在【重演的过去节点】上重新行动。

本模块不含任何专有名词；节点文案（含角色名）只出现在
`worlds/origin/presets/<name>/nodes.json`。
"""
from __future__ import annotations

import json
import os

from apps.conditions import evaluate
from apps.services import default as default_services
from kernel.api import load
from kernel.operators import meta_indices, seat_index

#: 节点文件缺省名。
NODES_FILE = "nodes.json"


def nodes_path(root, preset_name: str) -> str:
    return os.path.join(str(root), "presets", str(preset_name), NODES_FILE)


def load_nodes(root, preset_name: str) -> list:
    path = nodes_path(root, preset_name)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = raw if isinstance(raw, list) else list(raw.get("nodes") or [])
    return sorted(out, key=lambda n: int(n.get("frame", 0)))


def _snapshot(st) -> dict:
    return {
        "filled": tuple(bool(s.filled()) for s in st.register.slots),
        "memory_rows": int(st.memory_bank.shape[0]),
        "gates": frozenset(str(g) for g in st.gates),
        "events": frozenset(str(k)[len("emitted_"):] for k in st.score
                            if str(k).startswith("emitted_")),
        "selfhood": float(getattr(getattr(st, "origin", None), "selfhood", 0.0)),
        "solver": str(st.solver),
    }


class _Scanner:
    """逐帧只读采样器：只在节点帧与「原初首次成形」上留读数。"""

    def __init__(self, nodes):
        self.nodes = list(nodes)
        self._scan_frames = {int(n.get("frame", 0)) + 1 for n in self.nodes}
        self.snaps = {}
        self.first_origin = None

    def __call__(self, frame, st, traj=None) -> bool:
        o = getattr(st, "origin", None)
        if self.first_origin is None and o is not None and bool(o.ever):
            self.first_origin = int(frame)
        f = int(frame)
        if f in self._scan_frames:
            for i, node in enumerate(self.nodes):
                if f == int(node.get("frame", 0)) + 1:
                    self.snaps[i] = _snapshot(st)
        return True


def _missing_of(node, snap, first_origin, st, tau_low) -> tuple:
    """返回 `(是否缺失, 说明)`。节点早于原初首次成形 ⇒ `unreachable`。"""
    frame = int(node.get("frame", 0)) + 1
    if first_origin is None or frame < int(first_origin):
        return True, "unreachable"
    kind = str(node.get("missing") or "vacant")
    if kind == "vacant":
        i = seat_index(st, node.get("seat"))
        if i < 0 or i >= len(snap["filled"]):
            return True, "unknown_seat"
        return (not snap["filled"][i]), "vacant"
    if kind == "no_memory":
        return snap["memory_rows"] == 0, "no_memory"
    if kind == "not_seen":
        gate = node.get("gate")
        event = node.get("event")
        ok = True
        if gate:
            ok = ok and (str(gate) in snap["gates"])
        if event:
            ok = ok and (str(event) in snap["events"])
        if gate is None and event is None:
            ok = False
        return (not ok), "not_seen"
    if kind == "low_selfhood":
        tau = float(node.get("tau", tau_low))
        return snap["selfhood"] < tau, "low_selfhood"
    return True, "unknown_condition"


class Planner:
    """第一遍扫描 → 第二遍（及以后）带锚点重演，直到固定点。"""

    def __init__(self, ctx, data, seed: int, frames=None, max_iters=None):
        self.ctx = ctx
        self.data = data
        self.seed = int(seed)
        p = ctx.params
        self.frames = int(frames if frames is not None
                          else p.get("frames", 20000))
        self.max_iters = max(1, int(p.get("origin_max_iters",
                                          max_iters if max_iters is not None else 4)))
        name = str(data.preset.get("name") or "")
        # 只把【这次重演范围内】的节点纳入扫描：扫描发生在 frame+1，
        # 因此节点的 frame 必须 < frames；否则它永远 unreached，锚点迭代不收敛。
        self.nodes = [n for n in load_nodes(getattr(ctx, "root", ""), name)
                      if int(n.get("frame", 0)) < self.frames]
        self.anchors = []
        self.missing = []
        self.summary = None
        self._tau_low = float(p.get("tau_origin_low", 0.05))
        self._scanner = _Scanner(self.nodes)

    # ---- 单遍 ---------------------------------------------------------------
    def _run_pass(self, anchors):
        scanner = _Scanner(self.nodes)
        sess = load({
            "config": self.ctx, "data": self.data, "seed": self.seed,
            "runtime": default_services(), "rules": evaluate,
            "namer": None, "trace": False, "watch": scanner,
            "inbox": [dict(a) for a in anchors],
        })
        traj = sess.step(self.frames)
        return traj, scanner

    def _scan(self, traj, scanner):
        out = []
        for i, node in enumerate(self.nodes):
            snap = scanner.snaps.get(i)
            if snap is None:
                out.append({"id": node.get("id"), "node": node,
                            "why": "unreached", "unreachable": True})
                continue
            miss, why = _missing_of(node, snap, scanner.first_origin,
                                    traj.final, self._tau_low)
            if miss:
                out.append({"id": node.get("id"), "node": node, "why": why,
                            "unreachable": why == "unreachable"})
        return out

    # ---- 锚点 ---------------------------------------------------------------
    @staticmethod
    def _anchor_record(node, action, order, cost):
        return {
            "frame": int(node.get("frame", 0)),
            "channel": "origin",
            "capability": "origin_anchor",
            "selector": None,
            "label": node.get("label"),
            "payload": {
                "action": str(action),
                "seat": node.get("seat"),
                "gate": node.get("gate"),
                "mode": node.get("mode"),
                "memory": node.get("memory"),
                # 只有「把这件事真的带来」的动作才记事件：写入记忆 / 打开那道门。
                # 其余动作（唤醒等）不该顺手把 not_seen 的判据满足掉。
                "emit_event": (node.get("event")
                               if str(action) in ("seed_memory", "open_gate")
                               else None),
                "cost": float(cost),
                "node": node.get("id"),
                "order": int(order),
                # `keep`：这一手是叙事上【必须存在】的借出（哪怕还不上），
                # 精简阶段不许把它当成冗余锚点删掉。
                "keep": bool(node.get("keep", False)),
            },
        }

    def _build(self, missing, allow_event=True):
        """把缺失节点翻成一手锚点。

        `allow_event=False`（第一遍）：先只补【结构性】缺位（补席 / 写数据 / 开门）。
        事件类节点要等这些补上之后再扫描一轮 —— 很多事件本来就会随之自然发生，
        先给它投锚点只会多出一笔根本不需要的借出。
        """
        out = []
        unreach = [m for m in missing if m.get("unreachable")]
        if unreach:
            # 所有早期节点共用一个唤醒锚点：放在最早那个不可达节点上，
            # 原初一旦醒来，后面所有节点就都可达了（不必每个节点都唤醒一次）。
            first = min(unreach, key=lambda m: int(m["node"].get("frame", 0)))
            cost = float(first["node"].get("cost", 1.0))
            out.append(self._anchor_record(first["node"], "wake_origin", 0, cost + 1.0))
        for m in missing:
            node = m["node"]
            if not allow_event and node.get("event"):
                continue
            repair = str(node.get("repair") or "bind_memory")
            if m.get("unreachable") and repair == "wake_origin":
                continue                      # 已由上面那个唤醒锚点覆盖
            cost = float(node.get("cost", 1.0))
            out.append(self._anchor_record(node, repair, 1,
                                           cost + 1.0 if repair == "wake_origin"
                                           else cost))
        return out

    @staticmethod
    def _key(rec):
        p = rec.get("payload") or {}
        return (int(rec.get("frame", 0)), str(p.get("node")), str(p.get("action")))

    @staticmethod
    def _sort(anchors):
        return sorted(anchors, key=lambda a: (
            int(a.get("frame", 0)),
            int((a.get("payload") or {}).get("order", 0)),
            str((a.get("payload") or {}).get("node", ""))))

    # ---- 固定点 -------------------------------------------------------------
    def plan(self) -> list:
        """跑第一遍并迭代锚点；返回最终锚点脚本（可能为空）。"""
        traj, scanner = self._run_pass([])
        if not bool(getattr(traj.final.origin, "ever", False)):
            # 第一遍原初未成形：不跑锚点（origin_absent）。
            self.anchors = []
            self.missing = self._scan(traj, scanner)
            self._scanner = scanner
            return []

        anchors = []
        seen = set()
        for _ in range(self.max_iters):
            missing = self._scan(traj, scanner)
            if not missing:
                break
            # 第一遍只在【还有结构性缺位可补】时压住事件类节点：
            # 若这一遍剩下的全是事件类节点，就没有「先补结构、再看事件」可言了。
            allow_event = bool(anchors) or all(
                m["node"].get("event") for m in missing)
            new = [a for a in self._build(missing, allow_event=allow_event)
                   if self._key(a) not in seen]
            if not new:
                break                     # 锚点集合已稳定，但仍有缺失
            seen.update(self._key(a) for a in new)
            anchors = self._sort(anchors + new)
            traj, scanner = self._run_pass(anchors)

        self.anchors = self._sort(anchors)
        self.missing = self._scan(traj, scanner)
        if self.anchors and not self.missing:
            # 精简：有些节点在后来的重演里会【自然发生】（例如创世打破封印），
            # 早期那一遍给它投的锚点就成了多余的一手。逐个试删，删掉后仍无缺失才生效。
            self.anchors, traj, scanner = self._minimize(self.anchors,
                                                         traj, scanner)
            self.missing = self._scan(traj, scanner)
        self._scanner = scanner
        return self.anchors

    def _minimize(self, anchors, traj, scanner):
        """从后往前逐个试删锚点：删掉后仍无缺失才接受。

        只试删【事件类】锚点（`emit_event` 非空）—— 只有这类节点会被后来的重演
        自然满足；结构性补席 / 开门本来就是唯一的一手，试删只会白跑一遍。
        """
        current = list(anchors)
        for idx in range(len(current) - 1, -1, -1):
            payload = current[idx].get("payload") or {}
            if bool(payload.get("keep", False)) or not payload.get("emit_event"):
                continue
            trial = current[:idx] + current[idx + 1:]
            t2, s2 = self._run_pass(trial)
            if not self._scan(t2, s2):
                current, traj, scanner = trial, t2, s2
        return current, traj, scanner

    # ---- 最终一遍（由 run.py 带着锚点跑） ------------------------------------
    def begin_final(self):
        """重置扫描器：随后 run.py 会把 `watch` 挂到真正产报告的那一遍上。"""
        self._scanner = _Scanner(self.nodes)

    def watch(self, frame, st, traj=None) -> bool:
        return self._scanner(frame, st, traj)

    def _path_labels(self) -> dict:
        """命途 id → 显示名（文案住在 config/paths.json，报告层只取）。"""
        conf = getattr(self.ctx, "paths", None) or {}
        return {str(p.get("id")): str(p.get("label") or p.get("id"))
                for p in (conf.get("paths") or [])}

    @staticmethod
    def _path_counts(st) -> dict:
        out = {}
        for v in getattr(st, "paths", {}).values():
            pid = str(v.get("id"))
            out[pid] = out.get(pid, 0) + 1
        return out

    @staticmethod
    def _grant_counts(st) -> dict:
        out = {}
        for v in getattr(st, "grants", {}).values():
            pid = str(v.get("path"))
            out[pid] = out.get(pid, 0) + 1
        return out

    def finalize(self, traj):
        """按最终一遍的真实读数写四态、借还、closure，并给出裁决。"""
        scanner = self._scanner
        missing = self._scan(traj, scanner)
        o = traj.final.origin
        ever = bool(o.ever)
        tau_min = float(self.ctx.params.get("tau_origin_min",
                                            self.ctx.params.get("tau_origin", 0.12)))
        closed = (ever and not missing
                  and int(o.repaid) >= int(o.borrowed)
                  and float(o.selfhood) >= tau_min)
        if not ever:
            state, unstable = "origin_absent", False
        elif closed:
            state, unstable = "origin_closed", False
        elif missing:
            state, unstable = "origin_unstable", True
        else:
            state, unstable = "origin_open", False

        o.closure = 1 if closed else 0
        o.unstable = bool(unstable)
        o.final = True

        meta = meta_indices(traj.final)
        occupant = (traj.final.register.slots[int(meta[0])].owner
                    if meta else None)
        score = traj.final.score
        self.summary = {
            "state": state,
            "ever": ever,
            "awake": bool(o.awake),
            "form": int(o.form),
            "coverage": float(o.coverage),
            "factor_rows": int(o.factor_rows),
            "selfhood": float(o.selfhood),
            "energy": float(o.energy),
            "age": int(o.age),
            "occupant": occupant,
            "closure": bool(o.closure),
            "borrowed": int(o.borrowed),
            "repaid": int(o.repaid),
            "anchors": len(self.anchors),
            # 每一手锚点落在哪一帧、做了什么 —— 只读，供看板画「借还刻度」。
            "anchor_frames": [
                {"frame": int(a.get("frame", 0)),
                 "action": str((a.get("payload") or {}).get("action") or ""),
                 "node": str((a.get("payload") or {}).get("node") or ""),
                 "cost": float((a.get("payload") or {}).get("cost", 0.0)),
                 "keep": bool((a.get("payload") or {}).get("keep", False))}
                for a in self.anchors],
            "missing": len(missing),
            "create": int(score.get("origin_create", 0.0)),
            "love": int(score.get("origin_love", 0.0)),
            "trailblaze": int(score.get("origin_trailblaze", 0.0)),
            "dissolved": int(score.get("origin_dissolved", 0.0)),
            "companion": int(score.get("origin_companion", 0.0)),
            "companion_serial": int(o.companion_serial),
            "companion_alive": bool(
                int(o.companion_serial) >= 0
                and traj.final.pool.index_of_serial(int(o.companion_serial)) >= 0),
            "companion_spawn": int(score.get("origin_companion_spawn", 0.0)),
            "companion_host": int(o.companion_host),
            "companion_stage": int(o.companion_stage),
            "companion_age": int(o.companion_age),
            "companion_carry": int(o.companion_carry),
            "companion_bond": int(o.companion_bond),
            "companion_grow": int(score.get("origin_companion_grow", 0.0)),
            "companion_rebind": int(score.get("origin_companion_rebind", 0.0)),
            "companion_rebond": int(score.get("origin_companion_rebond", 0.0)),
            "companion_seat": int(score.get("origin_companion_seat", 0.0)),
            "attach": int(score.get("origin_attach", 0.0)),
            "resonance": float(o.resonance),
            "resonance_host": int(o.resonance_host),
            "resonated": bool(o.resonated),
            "resonance_wake": int(score.get("origin_resonance_wake", 0.0)),
            "savior_active": bool(o.savior_active),
            "gazed": bool("emitted_origin_gazed" in score),
            "seat_seized": bool("emitted_seat_seized" in score),
            "seat_reclaimed": bool("emitted_origin_seat_reclaimed" in score),
            # 权柄层：命途（canonical 世界没有 paths.json ⇒ 恒为空）
            "path_joined": int(score.get("path_joined", 0.0)),
            "path_defected": int(score.get("path_defected", 0.0)),
            "path_members": len(getattr(traj.final, "paths", {})),
            "path_counts": self._path_counts(traj.final),
            "path_labels": self._path_labels(),
            "emanators": len(getattr(traj.final, "grants", {})),
            "emanator_paths": self._grant_counts(traj.final),
            "path_revoked": int(score.get("path_revoked", 0.0)),
            # 具名因子：角色名只来自数据层的 name_factor 事件；候选是池中个体。
            "factors": [{"role": k[len("factor_"):], "serial": int(v)}
                        for k, v in sorted(score.items())
                        if k.startswith("factor_")
                        and k not in ("factor_named", "factor_unnamed",
                                      "factor_decided")],
            "savior": int(score.get("origin_savior", 0.0)),
            "savior_transfer": int(score.get("origin_savior_transfer", 0.0)),
            "memory_fragments": [
                {"id": f.id, "label": f.label, "effect": f.effect,
                 "magnitude": float(f.magnitude), "transferred": bool(f.transferred),
                 "until": int(f.until), "sustain": bool(f.sustain),
                 "rate": float(f.rate), "ticks": int(f.ticks),
                 # 起点与逐段时长：看板据此画「记忆阶段泳道」（不重算，只读）。
                 "start_frame": int(f.start_frame),
                 "phases": [{"label": str(ph.get("label") or f.label),
                             "effect": str(ph.get("effect") or f.effect),
                             "duration": int(ph.get("duration", 0) or 0)}
                            for ph in f.phases],
                 "phase_index": int(f.phase_index),
                 "phase_count": len(f.phases),
                 "phase_label": (f.phases[f.phase_index]["label"]
                                 if f.phases else ""),
                 "phase_text": (f.phases[f.phase_index].get("text", "")
                                if f.phases else ""),
                 "phase_effect": (f.phases[f.phase_index]["effect"]
                                  if f.phases else f.effect),
                 "phase_magnitude": (float(f.phases[f.phase_index]["magnitude"])
                                     if f.phases else float(f.magnitude))}
                for f in o.memory_fragments],
            "memory_fragment": int(score.get("origin_memory_fragment", 0.0)),
            "memory_transfer": int(score.get("origin_memory_transfer", 0.0)),
            "memory_tick": int(score.get("origin_memory_tick", 0.0)),
            "memory_phase": int(score.get("origin_memory_phase", 0.0)),
            "memory_coupling": float(o.memory_coupling_gain),
            "memory_mutation": float(o.memory_mutation_damp),
            "memory_seats": len(traj.final.memory_seats),
            "rebind": int(score.get("origin_rebind", 0.0)),
            # 浮黎锚定过去：把已经走过的那一段写进记忆（真实写入，不只是标签）。
            "anchor_past": int(score.get("fuli_anchor_past", 0.0)),
            "first_origin": scanner.first_origin,
            # 时间尺度：帧钟真的走到哪一帧、其中多少帧是真算的、多少帧是沿参考轨道复用的。
            "reached_frame": int(traj.reached_frame),
            "frames_simulated": int(traj.iterations),
            "frames_skipped": int(traj.skipped_frames),
            "deadlock": bool(traj.deadlock),
            "recurrence_target": int(self.ctx.params.get(
                "origin_recurrence_target", 0)),
            "nodes": missing,
        }
        traj.origin = self.summary

        # 裁决与结论：origin 世界不靠逐帧判据停世界，而由这一轮重演的收尾给出。
        traj.verdict = state
        traj.verdict_frame = traj.reached_frame
        traj.stop_reason = str((self.ctx.conclusions.get(state) or {})
                               .get("stop", state.upper()))
        entry = (self.ctx.conclusions or {}).get(state)
        if entry:
            traj.conclusion = entry
        return self.summary
