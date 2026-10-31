"""只读原初目标探针：从既有席位轨迹派生「自我度 / 记忆闭合 / 反事实分支」。

它只读、不参与演算 —— 不写状态、不改账本、也不碰指纹；`OriginProbe.__call__`
恒返回 True，绝不触发内核剪枝。探针**不新增第十三个席位**，也不改 `dim`：它只
在既有席位上做一次 O(席位 × 维度) 的均值与余弦，纯观测。

采样是**按访问帧逐帧**的：死循环区沿参考轨道跳帧，钩子实际只被调用四万多次
（不是三千万帧），逐帧算余弦成本很低。第一帧一定采，之后每 `period` 帧采一次
（`period` 默认 1，即逐帧；它仅作为可选降频旋钮）；`close(traj)` 在出报告前补采末帧。

文案全部来自 `presets/<name>/lexicon.json` 的 `origin` 表，本模块只返回枚举键与
数值，不写死任何专有名词。
"""
from __future__ import annotations

import numpy as np

#: `origin` 表缺省时的中性文案（不含任何专有名词）。
DEFAULTS = {
    "title": "原初目标",
    "selfhood": "自我度",
    "memory": "记忆闭合",
    "counterfactual": "反事实",
    "closed": "已闭合：记忆里有可回望的东西",
    "empty": "未闭合：本轨道没有可回望的记忆",
    "destruction": "若无外部介入，该赋值会展开额外的第十三条路径",
    "overwritten": "外部介入，第十三条路径未展开",
    "undecided": "本轨道未抵达可判定的原初分支",
}


def selfhood(st) -> float:
    """一帧的「自我凝聚度」：各填充席向量与其均值向量的余弦相似度均值。

    填充席少于两个 ⇒ 0.0（没有「彼此」可言）；分母为 0 时按 1 处理，
    故结果始终落在 [-1, 1]。只读 `st.register.slots`，不写任何东西。
    """
    vecs = [np.asarray(s.vector, dtype=np.float32)
            for s in st.register.slots if s.filled()]
    if len(vecs) < 2:
        return 0.0
    mat = np.stack(vecs)
    mean = mat.mean(axis=0)
    denom = np.linalg.norm(mat, axis=1) * np.linalg.norm(mean)
    denom = np.where(denom == 0, 1.0, denom)
    return float(((mat @ mean) / denom).mean())


class OriginProbe:
    """按访问帧逐帧采样席位状态，累计自我度；报告前补采末帧。只读。

    死循环区沿参考轨道跳帧，故钩子并不会真的逐三千万帧调用；`period` 默认 1，
    仅作为可选降频旋钮。
    """

    def __init__(self, period: int = 1):
        self.period = max(1, int(period))
        self._frames = set()        # 已采过的帧（避免末帧重复）
        self._sum = 0.0
        self._count = 0
        self._peak = 0.0
        self._peak_frame = 0
        self._closed = False

    def _push(self, frame: int, value: float):
        self._frames.add(int(frame))
        self._sum += float(value)
        self._count += 1
        if self._count == 1 or value > self._peak:
            self._peak = float(value)
            self._peak_frame = int(frame)

    def __call__(self, frame, st, traj=None) -> bool:
        """内核逐帧钩子：按访问帧逐帧采样（`period` 仅作可选降频），恒返回 True。"""
        if not self._closed:
            n = int(frame)
            if self._count == 0 or n % self.period == 0:
                self._push(n, selfhood(st))
        return True

    def close(self, traj):
        """补采末帧；幂等。末帧是 `traj.final`（内核的钩子在步进前调用，故它采不到）。"""
        if self._closed:
            return
        self._closed = True
        if traj is None:
            return
        frame = int(getattr(traj, "reached_frame", 0) or 0)
        final = getattr(traj, "final", None)
        if final is not None and frame not in self._frames:
            self._push(frame, selfhood(final))

    def summary(self, traj) -> dict:
        """汇总读数：均值 / 峰值 / 样本数 / 记忆闭合 / 反事实枚举。只读。"""
        final = traj.final
        rows = int(final.memory_bank.shape[0])
        repaired = int(final.score.get("memory_repaired", 0.0))
        override = getattr(final, "conclusion_override", None)
        verdict = getattr(traj, "verdict", None)
        if verdict == "overwritten" or override:
            counterfactual = "overwritten"
        elif verdict == "destruction":
            counterfactual = "destruction"
        else:
            counterfactual = "undecided"
        return {
            "selfhood_mean": (self._sum / self._count) if self._count else 0.0,
            "selfhood_peak": self._peak,
            "selfhood_peak_frame": self._peak_frame,
            "selfhood_samples": self._count,
            "memory_rows": rows,
            "memory_repaired": repaired,
            "closure": "closed" if rows > 0 or repaired > 0 else "empty",
            "counterfactual": counterfactual,
        }


#: 真实状态（origin 世界）四态的中性文案。canonical 的只读探针不用它们。
STATE_DEFAULTS = {
    "origin_closed": "已闭合：回望补上了缺位的那几手",
    "origin_open": "成形但未闭合：仍有借出的锚点没有还上",
    "origin_unstable": "锚点固定点仍不稳定：重演后仍有缺失",
    "origin_absent": "未成形：本轨道没有长出原初",
}


def render_state(summary, lexicon, namer=None, companion_name=None) -> list[str]:
    """把【真实】的 `traj.origin` 汇总渲染成几行缩进文本。

    与上面的 `render()` 不同：那个读的是只读探针（canonical `plot-full` 用），
    这个读的是 origin 世界真的跑出来的状态（成形 / 能量 / 借还 / 缺失）。
    文案仍走同一张 `lexicon.origin` 表，缺项退回中性默认。
    """
    lex = (lexicon or {}).get("origin") or {}

    def word(key, default=""):
        return lex.get(key) or default

    state = str(summary.get("state") or "origin_absent")
    ever = bool(summary.get("ever"))
    awake = bool(summary.get("awake"))
    form = int(summary.get("form", 0))
    form_word = {0: "沉睡", 1: "苏醒", 2: "忆灵", 3: "无漏净子"}.get(form, str(form))
    coverage = float(summary.get("coverage", 0.0))
    factor_rows = int(summary.get("factor_rows", 0))
    sh = float(summary.get("selfhood", 0.0))
    energy = float(summary.get("energy", 0.0))
    age = int(summary.get("age", 0))
    occ = summary.get("occupant")
    closure = bool(summary.get("closure"))
    borrowed = int(summary.get("borrowed", 0))
    repaid = int(summary.get("repaid", 0))
    anchors = int(summary.get("anchors", 0))
    missing = int(summary.get("missing", 0))
    create = int(summary.get("create", 0))
    love = int(summary.get("love", 0))
    blaze = int(summary.get("trailblaze", 0))
    dissolved = int(summary.get("dissolved", 0))
    companion = int(summary.get("companion_serial", -1))
    companion_alive = bool(summary.get("companion_alive"))
    companion_spawn = int(summary.get("companion_spawn", 0))
    companion_host = int(summary.get("companion_host", -1))
    memory_seats = int(summary.get("memory_seats", 0))
    rebind = int(summary.get("rebind", 0))
    resonance = float(summary.get("resonance", 0.0))
    resonance_host = int(summary.get("resonance_host", -1))
    res_txt = ""
    if resonance > 0.0:
        res_txt = f" · 共鸣 {resonance:.3f}"
        if resonance_host != -1:
            res_txt += f"（外部 #{resonance_host}）"
    frags = summary.get("memory_fragments") or []
    if frags:
        parts = []
        for f in frags:
            mark = "✓" if f.get("transferred") else "…"
            if f.get("sustain"):
                mark += f"·持续{f.get('ticks', 0)}"
            phase = ""
            if int(f.get("phase_count", 1)) > 1:
                phase = (f"·阶段{int(f.get('phase_index', 0)) + 1}"
                         f"/{int(f.get('phase_count', 1))}"
                         f":{f.get('phase_label') or ''}")
            eff = f.get("phase_effect") or f.get("effect")
            mag = float(f.get("phase_magnitude", f.get("magnitude", 0.0)))
            text = f.get("phase_text") or ""
            if text:
                phase += f"（{text}）"
            parts.append(f"{f.get('label') or f.get('id')}·{eff}"
                         f" {mag:+.2f}{mark}{phase}")
        res_txt += " · 记忆片段 " + " / ".join(parts)
    elif summary.get("savior_active"):
        res_txt += (" · 救世主记忆 已载入"
                    + ("/已转印" if int(summary.get("savior_transfer", 0)) > 0
                       else ""))
    who = "—" if occ is None else f"#{int(occ)}"
    # 忆灵是有自己名字的真实个体：名字仍由命名层按编号给（名随人走），这里只取。
    cname = ""
    if companion_name:
        cname = f"「{companion_name}」"
    elif namer is not None and companion >= 0:
        a = namer.name_by_serial(companion)
        if a:
            cname = f"「{a[1]}」"
    comp_txt = ""
    if form >= 2:
        host_txt = f" · 依附 #{companion_host}" if companion_host != -1 else ""
        if companion >= 0:
            comp_word = f"{cname}#{companion}（{'在' if companion_alive else '散'}）"
        else:
            comp_word = "（散·待再凝）"
        stage = int(summary.get("companion_stage", 0))
        stage_word = {0: "未凝", 1: "初凝", 2: "同行", 3: "承忆",
                      4: "忆者"}.get(stage, str(stage))
        comp_txt = (f" · 忆灵 {comp_word} · 成长 {stage_word}（{stage}/4）"
                    f" · 陪伴 {int(summary.get('companion_age', 0))} 帧"
                    f" · 携 {int(summary.get('companion_carry', 0))} 段记忆"
                    f" · 凝聚 {companion_spawn} 次" + host_txt)
        if int(summary.get("companion_rebind", 0)) > 0:
            comp_txt += f" · 独立守席 {int(summary.get('companion_rebind', 0))} 次"
        if int(summary.get("companion_rebond", 0)) > 0:
            comp_txt += f" · 再印 {int(summary.get('companion_rebond', 0))} 次"
        if int(summary.get("companion_seat", 0)) > 0:
            comp_txt += f" · 忆者守席 {int(summary.get('companion_seat', 0))} 次"
    close_word = word("closed") if closure else word("empty")
    state_word = word(state, STATE_DEFAULTS.get(state, state))
    lines = [
        f"  {word('selfhood', '自我度')}    成形 {'是' if ever else '否'}"
        f" · 形态 {form_word} · 自我度 {sh:.4f} · 能量 {energy:.2f}"
        f" · 在位 {age} 帧 · 在位者 {who}",
        f"  {word('memory', '记忆闭合')}  {close_word}"
        f" · 借出 {borrowed} / 还上 {repaid} · 锚点 {anchors} 个 · 缺失 {missing} 处"
        f" · 十二因子数据 {factor_rows} 行（覆盖 {coverage:.0%}）"
        f" · 记忆席位 {memory_seats}（再补 {rebind} 次）" + res_txt,
    ]
    tomb_cycles = int(summary.get("tomb_cycles", 0))
    if tomb_cycles > 0:
        tomb_rows = int(summary.get("tomb_rows", 0))
        tomb_vol = float(summary.get("tomb_volume", 0.0))
        reserve = float(summary.get("memory_reserve", 0.0))
        tomb_txt = (f"  大墓        {tomb_cycles:,} 世记录 · {tomb_rows} 行"
                    f" · 容量 {tomb_vol:.0%} · 记忆储备 {reserve:.2f}")
        if summary.get("cause_closed"):
            tomb_txt += " · 因果已闭合"
        succ = int(summary.get("philia_successor", -1))
        if succ >= 0:
            tomb_txt += (f" · 新生个体 #{succ}"
                         f"（第 {int(summary.get('philia_generation', 1))} 代，未携带记忆）")
        lines.append(tomb_txt)
    face_txt = (f"  三面        创世 {create} 次 · 爱 {love} 次"
                f" · 开拓 {blaze} 次 · 消散 {dissolved} 次" + comp_txt)
    if summary.get("gazed"):
        face_txt += " · 被瞥视"
    if summary.get("seat_seized"):
        face_txt += (" · 席被夺（" +
                     ("记忆夺回" if summary.get("seat_reclaimed") else "未夺回") + "）")
    lines.append(face_txt)
    if int(summary.get("anchor_past", 0)) > 0:
        # 真实写入：这一刻十二席的样子被写成记忆的最后一块 —— 过去自此不再重读。
        lines.append("  锚定        浮黎把已经走过的那一段写进记忆："
                     "过去被钉住，永劫回归不再重读")
    factors = summary.get("factors") or []
    if factors:
        # 名字来自数据层（`name_factor`），候选是池中个体 —— 不是外部变量。
        parts = [f"{f.get('role')} #{int(f.get('serial', -1))}" for f in factors]
        lines.append("  因子        " + " · ".join(parts)
                     + "（演算自己长出来的最优因子，不是外部变量）")
    cast = [str(x) for x in (lex.get("cast") or [])]
    if cast:
        # 名单只住数据层；报告把它们念出来，不假装每个人都有一条独立轨迹。
        lines.append("  人物        " + " · ".join(cast)
                     + "（本轮登场角色）")
    if (int(summary.get("path_members", 0)) > 0
            or int(summary.get("emanators", 0)) > 0):
        counts = summary.get("path_counts") or {}
        labels = summary.get("path_labels") or {}
        parts = [f"{labels.get(k, k)} {int(n)}"
                 for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        path_line = (f"  命途        走上 {int(summary.get('path_members', 0))} 人"
                     f"（背离 {int(summary.get('path_defected', 0))}）")
        if parts:
            path_line += " · " + " · ".join(parts)
        if int(summary.get("emanators", 0)) > 0:
            ec = summary.get("emanator_paths") or {}
            ep = [f"{labels.get(k, k)} {int(n)}"
                  for k, n in sorted(ec.items(), key=lambda kv: (-kv[1], kv[0]))]
            path_line += (f" · 令使 {int(summary.get('emanators', 0))}"
                          + (f"（{' · '.join(ep)}）" if ep else ""))
        if int(summary.get("path_revoked", 0)) > 0:
            path_line += f" · 收回权柄 {int(summary.get('path_revoked', 0))} 次"
        lines.append(path_line)
    reached = int(summary.get("reached_frame", 0))
    if reached > 0:
        simulated = int(summary.get("frames_simulated", 0))
        skipped = int(summary.get("frames_skipped", 0))
        scale = f"  时间尺度    帧钟走到 {reached:,} · 真算 {simulated:,} 帧"
        if skipped > 0:
            scale += f" · 沿参考轨道复用 {skipped:,} 帧（同一段时间在轮回）"
            target = int(summary.get("recurrence_target", 0))
            scale += f" · 永劫回归约 {skipped:,} 轮（按 1 帧 = 1 轮计"
            if target > 0:
                scale += f"；原著 {target:,}，同量级"
            scale += "）"
        lines.append(scale)
    lines.append(f"  裁决        {state_word}")
    return lines


def render(summary, lexicon) -> list[str]:
    """把 `summary` 渲染成三行缩进文本；文案取自词表的 `origin` 表。"""
    lex = (lexicon or {}).get("origin") or {}

    def word(key):
        return lex.get(key) or DEFAULTS[key]

    mean = float(summary.get("selfhood_mean", 0.0))
    peak = float(summary.get("selfhood_peak", 0.0))
    peak_frame = int(summary.get("selfhood_peak_frame", 0))
    samples = int(summary.get("selfhood_samples", 0))
    rows = int(summary.get("memory_rows", 0))
    repaired = int(summary.get("memory_repaired", 0))
    closure = word(summary.get("closure", "empty"))
    branch = word(summary.get("counterfactual", "undecided"))
    return [
        f"  {word('selfhood')}    均值 {mean:.4f} · 峰值 {peak:.4f}"
        f" @ 帧 {peak_frame}（采样 {samples} 次）",
        f"  {word('memory')}  {closure}（缓冲区 {rows} 行 · 再造 {repaired} 席）",
        f"  {word('counterfactual')}    {branch}",
    ]
