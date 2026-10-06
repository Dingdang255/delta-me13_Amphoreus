"""L6：可视化层（只读）。

把一次演算的产物装配成一份【自包含】的 HTML —— 十二席状态、指标曲线、事件
时间线、可检索的编年史，外加一个可暂停 / 播放 / 跳到任意时刻的回放控制台。
全部只【读】Trajectory 与状态读数，绝不写回任何状态：删掉这个文件，演算逐帧不变。

只依赖标准库：内联 CSS + 原生 JS（图表也由 JS 现场绘制，故能缩放平移），
零外部前端依赖、不联网。

两种用法：
  build_html(...)        静态导出（run.py --export）
  build_live_shell(...)  实时看板的空壳（run.py --serve）—— 页面持续向 /state 取增量
"""
from __future__ import annotations

import html
import json

from .operators import consensus
from .render import (Renderer, advance_label, cycle_frames, myth_phase_frame,
                     renewal_switch_frame, stage_starts, stage_table)

# 时间线：值得打点的事件类别与配色
_TIMELINE_COLORS = {
    "DISTURBANCE": "#e8c06a",
    "PROMOTION": "#7fd0ff",
    "DEADLOCK_LOOP": "#ff8a8a",
    "DEADLOCK_END": "#ff8a8a",
    "VERDICT": "#b28dff",
    "CONCLUSION_REACHED": "#b28dff",
    "CONVERGED": "#7fe0a0",
    "PROTOCOL_REWRITTEN": "#ff9ed6",
    "SOLVER_CHANGED": "#ffd27f",
    "DOMAIN_ADVANCE": "#8ab4ff",
    "ASCENSION": "#ff6b6b",
}

# 画布几何（JS 侧照这份读数绘制）
_W, _PAD = 920, 36
# 编年史最多往静态页面里塞多少条 —— 兜底，免得超长轨道把页面撑爆。
_CHRON_LIMIT = 20000
# 时间线打点：同类事件最多保留多少条（plot 有 201 次换代，全画会糊成一片）
_MARKS_PER_KIND = 40


def _cos(a, b) -> float:
    """两向量的余弦相似度（纯 Python，便于本层不依赖 numpy）。"""
    na = nb = ab = 0.0
    for x, y in zip(a, b):
        fx, fy = float(x), float(y)
        na += fx * fx
        nb += fy * fy
        ab += fx * fy
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return ab / ((na ** 0.5) * (nb ** 0.5))


def _components(vecs, thr: float) -> int:
    """已承位席之间「相似度图」的连通分量数：两席向量余弦 ≥ thr 即连边。

    对应「区域连通分量」—— 世界被分成几块彼此不像的区域。座位最多十二个，故
    直接 O(n²) 建图 + 并查集/深搜，够用且好读。
    """
    n = len(vecs)
    if n == 0:
        return 0
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if _cos(vecs[i], vecs[j]) >= thr:
                adj[i].append(j)
                adj[j].append(i)
    seen = [False] * n
    comp = 0
    for s in range(n):
        if seen[s]:
            continue
        comp += 1
        stack = [s]
        seen[s] = True
        while stack:
            u = stack.pop()
            for w in adj[u]:
                if not seen[w]:
                    seen[w] = True
                    stack.append(w)
    return comp


def texture_of(frame, st, link_thr: float = 0.5) -> tuple:
    """一帧的「世界纹理」低维统计（只读）：相似度中位 · 能量集中度 · 区域连通分量数。

    纯只读：只读 pool 的支持度、loci 的承载量、已承位席的向量 —— 不碰任何状态、
    也没有随机数，删掉它演算逐帧不变。用途是把「世界演化」压成一条可画的低维曲线
    （后期据此画「演化地形图」），而不是替演算做任何判断。

    · 相似度中位：把各活跃个体的平均相似度（support / (种群−1)）取中位 —— 越高中
      世界越「抱团」；
    · 能量集中度：各席承载量的赫芬达尔指数（1/12 = 完全均摊 → 1 = 全压在一席）；
    · 区域连通分量数：已承位席按向量相似度连边后的连通块数。
    """
    sup = getattr(getattr(st, "pool", None), "support", None)
    vals = [float(s) for s in sup] if sup is not None else []
    live = [v for v in vals if v > 0.0]
    sim_p50 = 0.0
    if len(live) > 1:
        denom = len(live) - 1.0
        rel = sorted(v / denom for v in live)
        sim_p50 = rel[len(rel) // 2]

    loads = [float(getattr(l, "load", 0.0)) for l in getattr(st, "loci", ()) or ()]
    tot = sum(loads)
    conc = sum((v / tot) ** 2 for v in loads) if tot > 0.0 else 0.0

    slots = getattr(getattr(st, "register", None), "slots", ()) or ()
    occ = [s.vector for s in slots if getattr(s, "owner", None) is not None]
    comp = _components(occ, link_thr)
    return (int(frame), round(sim_p50, 4), round(conc, 4), int(comp))


class Sampler:
    """指标采样器（只读）。挂在 run(watch=...) 上，逐【到访帧】收一组读数。

    采用【几何步长】：早期（真正在演化的那几千帧）密，长尾（复用区的千万帧）疏，
    总量封顶在 cap 附近。每条读数含该帧的十二席在位者，故「回放」能还原当时的席位。

    它只读、只往自己的列表里写、返回值恒 True（从不剪枝）—— 删掉它，演算逐帧不变。
    """

    def __init__(self, total, cap: int = 900, texture_every: int = 64):
        self.points = []       # (frame, entropy, noise, population, promotions, filled, owners)
        # 「世界纹理」序列：低频（每 texture_every 个到访帧一组），独立于 points 的几何步长。
        # 形状 (frame, 相似度中位, 能量集中度, 区域连通分量数) —— 供后期画「世界演化地形图」。
        self.texture = []
        self._tex_gap = max(1, int(texture_every))
        self._tex_next = 0
        self._thr = 0.0
        self._step = 1.0
        self._ratio = max(2, int(total)) ** (1.0 / max(1, int(cap)))
        self._dom = None       # 上一帧的档位（换档判定用）
        self._ex = None        # 上一帧的「域穷尽」（同上）
        self._prev = None      # 上一帧的读数缓冲（换档帧要补采）

    def __call__(self, frame, st, traj):
        dom = int(getattr(st, "domain_index", 0))
        ex = bool(getattr(st, "domains_exhausted", False))
        owners = tuple(s.owner for s in st.register.slots)
        point = (int(frame), round(float(st.entropy), 5), round(float(st.noise), 5),
                 len(st.pool), int(st.promotions),
                 sum(1 for o in owners if o is not None), owners)

        # 档位 / 域穷尽一变 ⇒ **上一帧**就是换档帧。它在 watch 时还看不到（换档事件是在
        # 那一帧的演化里才发出的），故靠「档位变了」回推，把上一帧缓冲的读数补采进去 ——
        # 否则看板点阶段卡只能落到邻近的采样点上，读数会差那么几帧。
        changed = ((self._dom is not None and dom != self._dom)
                   or (self._ex is not None and ex != self._ex))
        if changed and self._prev is not None \
                and (not self.points or self.points[-1][0] != self._prev[0]):
            self.points.append(self._prev)
        self._dom, self._ex, self._prev = dom, ex, point

        if changed or frame >= self._thr:
            self.points.append(point)
            self._step *= self._ratio
            self._thr = frame + max(1.0, self._step)

        # 纹理低频采样：与 points 的几何步长解耦，长尾里也留得下几个点。
        if frame >= self._tex_next:
            self.texture.append(texture_of(frame, st))
            self._tex_next = frame + self._tex_gap
        return True


def _final_point(traj):
    """走到最后一帧的读数。曲线与回放的右端必须是【真终局】，不是最后一个采样点 ——
    否则最后一次换代、最后一次裁决都落在采样窗口之外（读者会以为世界停在半路）。"""
    st = traj.final
    owners = tuple(s.owner for s in st.register.slots)
    return (int(traj.reached_frame), round(float(st.entropy), 5),
            round(float(st.noise), 5), len(st.pool), int(st.promotions),
            sum(1 for o in owners if o is not None), owners)


def ensure_final(points, traj):
    """保证采样序列以「最后一帧」收尾；已有则不重复追加。"""
    pts = list(points or [])
    last = _final_point(traj)
    if not pts or int(pts[-1][0]) < last[0]:
        pts.append(last)
    return pts


def _downsample(points, cap: int = 1400, keep=()):
    """均匀抽稀到 cap 点以内（必留首末，以及 `keep` 里点名的那些帧）。

    `keep` 用来钉住【阶段起点】—— 看板点阶段卡要落到那一帧上，抽稀把它抽掉就落不准了。
    """
    n = len(points)
    if n <= cap:
        return points
    idx = {0, n - 1} | {round(i * (n - 1) / (cap - 1)) for i in range(cap)}
    if keep:
        want = {int(f) for f in keep}
        idx |= {i for i, p in enumerate(points) if int(p[0]) in want}
    return [points[i] for i in sorted(idx)]


# ---- 名字解析 ---------------------------------------------------------------

def _name_map(traj):
    return {int(p.serial): traj.namer.persona_name(p) for p in traj.personas}


def _resolve(traj, names, serial):
    """编号 → 人名。名随人走：认不出来就报「无名者#N」，绝不拿职位名顶替。"""
    if serial is None:
        return None
    s = int(serial)
    if s in names:
        return names[s][1]
    a = traj.namer.name_by_serial(s)
    if a:
        return a[1]
    return f"无名者#{s}"


def _machine_map(traj):
    """编号 → 机器编号（`词干+序号`）。只有登记过的个体才有 —— 不硬造。"""
    return {int(p.serial): traj.namer.machine_name_of(p) for p in traj.personas}


def _machine_of(traj, machines, serial):
    """编号 → 机器编号：登记过的用登记的；预设按编号钉死的用钉的；都不认就报裸序号。

    两处例外：
      · **外部变量**（预设标了 `external` 的那几位）⇒ 报 `"?"` —— 他们自天外而来，
        不是从池子里长出来的电信号序列，本就没有「工序号」；
      · 编号为负（= 由「记忆」承载的那一席）⇒ 报空串（不摆悬浮卡）。
    """
    if serial is None:
        return ""
    s = int(serial)
    if traj.namer.is_external(s):
        return "?"
    if s < 0:
        return ""
    if s in machines:
        return machines[s]
    return traj.namer.machine_by_serial(s) or f"#{s}"


# ---- 十二席（A2） -----------------------------------------------------------

def _city_meta(ctx):
    """十二席的城邦名 + 稳定的“配色编号”。

    城邦是可空缺的渲染层绑定（只填有考据的席位）—— 缺席的席位记空串、编号 -1。
    编号按城邦名的字典序给定，于是同一份词表每次都得到同一套配色（与遍历次序无关）。
    """
    cities = ctx.lexicon.get("cities") or {}
    per = [cities.get(locus.id, "") for locus in ctx.loci]
    names = sorted({c for c in per if c})
    idx = [names.index(c) if c else -1 for c in per]
    return per, names, idx


def _seat_cards(ctx, traj, names, machines):
    cal = ctx.phonology.get("title_calibration", {})
    regions = ctx.lexicon.get("regions", {})
    cities, _city_names, city_idx = _city_meta(ctx)
    st = traj.final
    sup = set(getattr(st, "suppressed", ()) or ())
    cards = []
    for i, locus in enumerate(ctx.loci):
        owner = st.register.slots[i].owner
        title = cal.get(locus.id, ["", locus.id])
        cards.append({
            "id": locus.id,
            "duty": title[1] or locus.id,
            "region": regions.get(locus.id, ""),
            "city": cities[i],
            "city_idx": city_idx[i],
            # 「电信号序列 <号>」——悬浮卡用（与席位卡的 data-machine 同源）
            "machine": _machine_of(traj, machines, owner),
            "name": _resolve(traj, names, owner) or "（空置）",
            "vacant": owner is None,
            "suppressed": i in sup,
            "progress": float(getattr(st.loci[i], "progress", 0.0)),
        })
    return cards


def _seat_state(c):
    if c["suppressed"]:
        return "封印（无人在位）", "seat sup"
    if c["vacant"]:
        return "空置", "seat vacant"
    return "在位", "seat"


def _city_dot(idx):
    """城邦配色圆点。idx < 0（无考据的席位）不画点。"""
    return f'<i class="citydot k{idx}"></i>' if idx >= 0 else ""


def _city_legend_html(cards, hidden=False):
    """城邦图例：只列出现过的城邦，按配色编号排开（配色与席位卡上的圆点一致）。

    城邦只属于【第四阶段】（变量域穷尽之后，演算主体才有世界内的身份与职称）——
    前三阶段那 12 位没有城邦，故整块不摆。`hidden=True` 用于实时看板：先把图例备好、
    `display:none`，等 `mythfrom` 到了由页面就地显出来（静态导出则按终局直接决定摆不摆）。
    """
    legend = sorted({(c["city_idx"], c["city"]) for c in cards if c["city_idx"] >= 0})
    if not legend:
        return ""
    chips = "".join(f'<span class="lgd">{_city_dot(i)}{html.escape(n)}</span>'
                    for i, n in legend)
    style = ' style="display:none"' if hidden else ""
    return (f'<div class="citylegend"{style}><span class="lgd-t">城邦</span>'
            f'{chips}</div>')


def _seats_html(cards, tau, show_places=True):
    """十二席卡片。`show_places=False`（还没进第四阶段）时【不摆】称号 / 城邦两行。

    那两样（称号 / 圣所、城邦）都是世界内的东西，见 `_city_legend_html`。
    """
    head = _city_legend_html(cards) if show_places else ""
    out = [head, '<div class="seats" id="seats">']
    for c in cards:
        state, cls = _seat_state(c)
        # progress 是连续量：进度条 = progress / τ，达标即满格。
        pct = max(0.0, min(1.0, c["progress"] / tau if tau else 0.0)) * 100
        done = " done" if c["progress"] >= tau else ""
        name = html.escape(c["name"])
        place = (
            f'<div class="seat-region">{html.escape(c["region"])}</div>'
            f'<div class="seat-city">{_city_dot(c["city_idx"])}'
            f'{html.escape(c["city"]) or "—"}</div>'
        ) if show_places else ""
        out.append(
            f'<div class="{cls}" data-name="{name}" data-id="{html.escape(c["id"])}" '
            f'data-machine="{html.escape(c["machine"])}" '
            f'title="点击按此人过滤编年史；再点一次或点空白处取消">'
            f'<div class="seat-top"><span class="seat-duty">{html.escape(c["duty"])}</span>'
            f'<span class="seat-id">{html.escape(c["id"])}</span></div>'
            f'{place}'
            f'<div class="seat-name">{name}</div>'
            f'<div class="seat-state">{html.escape(state)}</div>'
            f'<div class="bar"><i class="{done.strip()}" style="width:{pct:.1f}%"></i></div>'
            f'<div class="seat-prog">证伪进度 {c["progress"]:.2f} / {tau:g}</div>'
            f'</div>'
        )
    out.append("</div>")
    return "\n".join(out)


# ---- 时间线（A4） -----------------------------------------------------------

def _event_label(R, kind, payload, frame=None, switch=None):
    if kind == "DISTURBANCE":
        return payload.get("label") or (R.capability(payload.get("capability")) or "介入")
    return {
        # 世代更迭分三档（自动更替 / 主动更替 / 再创世）—— 与报告 / 编年史同一把尺子
        # （`advance_label`：按协议改写帧与 `R.phase_of(frame)` 判）。
        "PROMOTION": lambda: f"第 {payload.get('round', '?')} 次"
                             f"{advance_label(R, switch, frame if frame is not None else 0)}",
        "DEADLOCK_LOOP": lambda: f"{R.term('deadlock')}开启",
        "DEADLOCK_END": lambda: f"走出{R.term('deadlock')}",
        "VERDICT": lambda: f"裁决：{payload.get('verdict')}",
        "CONCLUSION_REACHED": lambda: f"结论里程碑：{payload.get('conclusion')}",
        "CONVERGED": lambda: f"因果{R.term('converged')}",
        "PROTOCOL_REWRITTEN": lambda: f"{R.term('protocol')}被改写",
        "SOLVER_CHANGED": lambda: "演算方向改写",
        "DOMAIN_ADVANCE": lambda: f"{R.term('domain')}推进 → {payload.get('value')}",
        "ASCENSION": lambda: "升格·结论外溢",
    }.get(kind, lambda: kind)()


def _timeline_marks(traj, R, per_kind=_MARKS_PER_KIND):
    """时间线上要打点的事件（帧、类别、文案、配色、事件号）。同类过多时只留前 per_kind 条。

    最后那个【事件号】= 该条记录在 `traj.records` 里的下标，与编年史行共用同一把尺子 ——
    于是双击一个节点能回到【它本身】那条编年史，而不是同一帧里排在最前的那条。
    """
    seen, out = {}, []
    switch = renewal_switch_frame(traj)
    for rid, (frame, kind, payload) in enumerate(traj.records):
        if kind not in _TIMELINE_COLORS:
            continue
        seen[kind] = seen.get(kind, 0) + 1
        if seen[kind] > per_kind:
            continue
        out.append((frame, kind, _event_label(R, kind, payload, frame, switch),
                    _TIMELINE_COLORS[kind], rid))
    return out


# ---- 数据（塞给 JS 的那份） -------------------------------------------------

def _seat_table(traj, names, machines, pts, final_point):
    """把「席位在位者」编成两张并行的表（人名 / 机器编号）+ 下标，避免同一串重复上千遍。"""
    table, mach, index = [], [], {}

    def put(serial):
        if serial is None:
            return 0
        key = int(serial)
        if key not in index:
            index[key] = len(table) + 1          # 0 表示空席
            table.append(_resolve(traj, names, key))
            mach.append(_machine_of(traj, machines, key))
        return index[key]

    per_sample = [[put(o) for o in p[6]] for p in pts]
    return table, mach, per_sample, [put(o) for o in final_point[6]]


def _data_blob(R, pts, lines, total, marks, table, seats_per_sample,
               promos, spans, machines=(), stages=(), live=False, mythfrom=None,
               autoreload=True, texture=()):
    """塞给 JS 的那份数据。JSON 里不能出现 `</`（会被当成标签结束），故转义掉。

    十二席的职位 / 称号 / 城邦由 R.ctx 现算 —— 它们只随词表变，与演算无关。
    阶段目录（stages）同理：它来自配置 + 本次记录的换档帧号。
    """
    duties, regions, cities, city_names, city_idx = _seat_meta(R.ctx)
    labels = ["帧", "熵", R.term("overflow"), "种群", R.term("promotion"), "在位席位"]
    blob = {
        "total": int(total),
        "geo": {"w": _W, "pad": _PAD},
        "labels": labels,
        "duties": list(duties),
        "regions": list(regions),
        "cities": list(cities),
        "citynames": list(city_names),
        "cityidx": list(city_idx),
        # 演算期（前三个阶段）里那 12 位还没有世界内的职位 —— 席卡改显这一列
        "simslot": _sim_slots(R.ctx),
        # 「世界内」（第四阶段）从哪一帧起：null = 还没走到 ⇒ 整张图都按演算期讲。
        # 看板的席卡 / 城邦图例据此在回放时 【演算期 ⇄ 世界内】两套语汇之间切。
        "mythfrom": None if mythfrom is None else int(mythfrom),
        "stages": list(stages),
        "seatnames": table,
        # 与 `seatnames` **同下标**的机器编号表 —— 席位卡悬浮时报「电信号序列 <号>」用
        "machines": list(machines),
        "samples": [[int(p[0]), p[1], p[2], p[3], p[4], p[5], seats_per_sample[i]]
                    for i, p in enumerate(pts)],
        # 每行末尾带【事件号】(`rid`)：与 marks 末尾那个同源 —— 双击时间线节点据此精确
        # 命中它自己那条，而不是同一帧里排在最前的那条编年史行。
        "lines": [[int(f), str(t), b, int(rid)] for f, t, b, rid in lines],
        "marks": [[int(f), k, str(lab), c, int(rid)] for f, k, lab, c, rid in marks],
        "promos": [[int(f), int(rd)] for f, rd in promos],
        "spans": [[int(s), int(e)] for s, e in spans],
        # 世界纹理序列 [[帧, 相似度中位, 能量集中度, 区域连通分量数], ...] —— 低频、
        # 只读；当前只随数据下发（供后续画「演化地形图」），页面暂未绘制。
        "texture": [[int(t[0]), float(t[1]), float(t[2]), int(t[3])]
                    for t in (texture or ())],
        "live": bool(live),
        # 演算跑完、服务端备好完整静态页之后：默认自动重载过去；关掉则右下角弹提示
        # （`--no-serve-reload`）。静态页用不到它，留着无害。
        "autoreload": bool(autoreload),
    }
    return json.dumps(blob, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


# ---- 内联样式 ---------------------------------------------------------------

_CSS = """
:root{--bg:#0f1117;--panel:#171a23;--line:#2a2f3d;--fg:#d8dbe6;--dim:#8b93a7;--gold:#e8c06a;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--fg);
 font-family:"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.5;}
.wrap{max-width:1000px;margin:0 auto;padding:28px 20px 60px;}
h1{font-size:20px;margin:0 0 4px;color:var(--gold);font-weight:600;letter-spacing:.5px;}
.sub{color:var(--dim);font-size:13px;margin-bottom:20px;}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px;}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;
 padding:12px 16px;flex:1 1 200px;min-width:170px;overflow:hidden;}
.card .k{color:var(--dim);font-size:12px;}
.card .v{font-size:15px;margin-top:2px;overflow-wrap:anywhere;word-break:break-word;}
.card .v.mono{font-family:ui-monospace,Consolas,monospace;font-size:13px;}
h2{font-size:15px;color:var(--gold);margin:26px 0 10px;font-weight:600;
 border-left:3px solid var(--gold);padding-left:9px;}
.seats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;}
.seat{background:var(--panel);border:1px solid var(--line);border-radius:8px;
 padding:10px 11px;cursor:pointer;}
.seat:hover{border-color:var(--gold);}
.seat.picked{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset;}
.seat.vacant{border-color:#5a4a3a;opacity:.85;cursor:pointer;}
.seat.sup{border-color:#6b3a3a;background:#1d1518;}
.seat-top{display:flex;justify-content:space-between;align-items:baseline;}
.seat-duty{font-size:15px;color:var(--gold);font-weight:600;}
.seat-id{font-size:11px;color:var(--dim);}
.seat-region{font-size:11px;color:var(--dim);margin:1px 0 5px;}
.seat-city{font-size:11px;color:var(--dim);margin:0 0 5px;}
.citydot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:4px;
  vertical-align:middle;background:var(--dim);}
.k0{background:#c8a24a;}.k1{background:#6fa8dc;}.k2{background:#8fbc8f;}.k3{background:#d98cb3;}
.k4{background:#c98f5a;}.k5{background:#9b8fd6;}.k6{background:#7fc7c7;}.k7{background:#b0b0b0;}
.citylegend{font-size:11px;color:var(--dim);margin:0 0 8px;
  display:flex;flex-wrap:wrap;gap:12px;align-items:center;}
.citylegend .lgd{display:inline-flex;align-items:center;}
.citylegend .lgd-t{color:var(--gold);}
.seat-name{font-size:13px;overflow-wrap:anywhere;}
.seat-state{font-size:11px;color:var(--dim);margin:2px 0 5px;}
.bar{height:5px;background:#232733;border-radius:3px;overflow:hidden;}
.bar i{display:block;height:100%;background:#7fd0ff;}
.bar i.done{background:var(--gold);}
.seat-prog{font-size:10px;color:var(--dim);margin-top:3px;}
.stages{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:10px;}
.stage{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 11px;}
.stage-head{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap;}
.stage-mark{color:var(--gold);font-size:13px;}
.stage-name{font-size:14px;color:var(--fg);font-weight:600;}
.stage-span{font-size:11px;color:var(--dim);margin-top:3px;}
.stage-asm{font-size:11px;color:var(--dim);margin-top:3px;overflow-wrap:anywhere;}
.stage-num{font-size:11px;color:var(--dim);margin-top:3px;}
.stage-conc{font-size:11.5px;color:#aeb6c8;margin-top:6px;padding-top:5px;
 border-top:1px dashed var(--line);}
.stage-myth{font-size:11px;color:#8ab4ff;margin-top:5px;}
/* 阶段卡可点：跳回该档开始的帧 */
.stage[data-start]{cursor:pointer;}
.stage[data-start]:hover{border-color:var(--gold);}
.rules{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 11px;}
.obsrow{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px;}
.obs{font-size:12px;color:var(--dim);}
.obs b{color:var(--fg);font-weight:600;margin-right:5px;}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;
 padding:10px 12px;margin-bottom:14px;}
.ctrls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;}
.ctrls button{background:#20242f;border:1px solid var(--line);border-radius:6px;
 color:var(--fg);padding:4px 11px;font-size:12px;font-family:inherit;cursor:pointer;}
.ctrls button:hover{border-color:var(--gold);color:var(--gold);}
.ctrls input[type=range]{flex:1 1 240px;min-width:180px;accent-color:#e8c06a;}
.ctrls select,.toolbar select{background:#0b0d13;border:1px solid var(--line);
 border-radius:6px;color:var(--fg);padding:4px 6px;font-size:12px;font-family:inherit;}
.chart-box{position:relative;background:var(--panel);border:1px solid var(--line);
 border-radius:8px;padding:12px;margin-bottom:14px;}
.chart-title{font-size:13px;color:var(--dim);margin-bottom:6px;}
.chart{width:100%;height:auto;display:block;cursor:crosshair;}
.chart-box{cursor:crosshair;}
.dragging,.dragging .chart{cursor:grabbing;}
.legend{font-size:11px;color:var(--dim);margin-top:6px;}
.legend em{font-style:normal;color:#6b7280;}
.tip{position:absolute;top:6px;left:8px;display:none;z-index:5;pointer-events:none;
 max-width:calc(100% - 20px);background:#0b0d13;border:1px solid var(--line);
 border-radius:6px;padding:4px 8px;font-size:11px;color:var(--fg);white-space:nowrap;}
.dim{color:var(--dim);font-size:11px;}
.near{font-size:11.5px;color:var(--gold);margin:2px 0 6px;min-height:16px;}
.tlbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:4px;}
/* 席位卡悬浮卡：灰字报「电信号序列 <号>」，跟着鼠标走 */
.seattip{position:fixed;z-index:40;pointer-events:none;display:none;background:#0b0d13;
 border:1px solid var(--line);border-radius:6px;padding:3px 8px;font-size:11px;
 color:var(--dim);white-space:nowrap;}
/* 右下角「演算完成」提示：默认收起（透明度 + 轻微下移），出现时过渡到就位。 */
.donetoast{position:fixed;right:20px;bottom:20px;z-index:30;width:290px;
 background:#171a23;border:1px solid var(--line);border-left:3px solid var(--gold);
 border-radius:10px;padding:12px 14px;box-shadow:0 10px 28px rgba(0,0,0,.5);
 opacity:0;transform:translateY(14px);pointer-events:none;
 transition:opacity .35s ease,transform .35s ease;}
.donetoast.show{opacity:1;transform:none;pointer-events:auto;}
.donetoast .dt-h{font-size:13px;color:var(--gold);font-weight:600;margin-bottom:4px;}
.donetoast .dt-b{font-size:12px;color:var(--dim);line-height:1.55;margin-bottom:10px;}
.donetoast button{background:#20242f;border:1px solid var(--line);border-radius:6px;
 color:var(--fg);padding:4px 12px;font-size:12px;font-family:inherit;cursor:pointer;}
.donetoast button:hover{border-color:var(--gold);color:var(--gold);}
.donetoast .dt-x{position:absolute;top:5px;right:6px;padding:0 6px;background:none;
 border:none;color:var(--dim);font-size:16px;line-height:1;}
.donetoast .dt-x:hover{color:var(--gold);}
.chron-box{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px;}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px;}
.toolbar input[type=search]{flex:1 1 220px;min-width:160px;}
.toolbar input{background:#0b0d13;border:1px solid var(--line);border-radius:6px;
 color:var(--fg);padding:5px 8px;font-size:12px;font-family:inherit;}
.toolbar input[type=number]{width:120px;}
.toolbar label{font-size:12px;color:var(--dim);display:flex;gap:5px;align-items:center;}
.toolbar button{background:#20242f;border:1px solid var(--line);border-radius:6px;
 color:var(--fg);padding:5px 12px;font-size:12px;font-family:inherit;cursor:pointer;}
.toolbar button:hover{border-color:var(--gold);color:var(--gold);}
.chron{list-style:none;margin:0;padding:0;max-height:520px;overflow:auto;
 font-size:11.5px;color:#aeb6c8;}
.chron li{padding:2px 4px;border-radius:4px;}
.chron li:nth-child(odd){background:#141822;}
.chron li.hit{background:#2a2413;box-shadow:0 0 0 1px var(--gold) inset;}
.chron .lf{color:#6b7280;}
.chron .lb{color:#e8c06a;}
.chron li.more{color:var(--dim);text-align:center;padding:8px;background:none;}
.chron li.ev{display:flex;gap:8px;}
.chron li.ev .dot{flex:0 0 8px;height:8px;border-radius:50%;margin-top:6px;}
.hint{color:var(--dim);font-size:11px;}
#liveflag{color:#7fe0a0;}
noscript p{font-size:12px;color:var(--dim);}
code{background:#0b0d13;border-radius:4px;padding:1px 5px;font-size:11.5px;}
"""


# ---- 内联 JS：图表绘制 / 缩放平移 / 回放 / 检索 / 实时 ----------------------
_JS = r"""
(function(){
  var D = JSON.parse(document.getElementById('viz-data').textContent);
  var W = D.geo.w, PAD = D.geo.pad;
  var TOTAL = Math.max(2, D.total);
  var L = D.labels;
  var win = {lo: 1, hi: TOTAL};              // 可见时间窗（帧，对数刻度）
  var cur = D.samples.length - 1;            // 回放游标：采样序号
  var rows = D.lines, marks = D.marks, promos = D.promos, spans = D.spans;
  var samples = D.samples, seatNames = D.seatnames;
  var machineNames = D.machines || [];        // 与 seatNames 同下标：机器编号（电信号序列）
  var stages = D.stages || [];
  var seatsHome = null;
  var duties = D.duties || [], regions = D.regions || [];
  var cities = D.cities || [], cityidx = D.cityidx || [];
  var simslot = D.simslot || [];              // 演算期里那 12 位的叫法（无世界内职位）
  // 「世界内」从哪一帧起：null = 还没走到（整张图都按演算期讲）。实时看板会随后补上。
  var mythFrom = (D.mythfrom === undefined ? null : D.mythfrom);
  var playing = false, timer = null, speed = 1, follow = true;
  var autoreload = (D.autoreload !== false);   // --no-serve-reload 时为 false
  var doneShown = false;

  // 这一帧属于哪套语汇：前三个阶段（因子演算）⇄ 第四阶段（人类古典文明/世界内）。
  // `mythfrom` = 世界内从哪一帧起（null = 还没走到 ⇒ 整张图都按演算期讲）——
  // 与报告、编年史同一把尺子（都取 `DOMAINS_EXHAUSTED` 那一帧）。
  function simPhase(f){
    return mythFrom === null || mythFrom === undefined || f < mythFrom;
  }

  function $(id){ return document.getElementById(id); }
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function fmt(n){ return Number(n).toLocaleString('en-US'); }
  function log10(x){ return Math.log(Math.max(1, x))/Math.LN10; }

  // ---------- 时间轴换算（对数帧） ----------
  function xOf(f){
    var a = log10(win.lo), b = log10(win.hi);
    var t = (log10(f) - a) / ((b - a) || 1);
    return PAD + Math.max(0, Math.min(1, t)) * (W - 2 * PAD);
  }
  function frameAt(x){
    var t = (x - PAD) / (W - 2 * PAD);
    var a = log10(win.lo), b = log10(win.hi);
    return Math.pow(10, a + t * (b - a));
  }

  // 进度条按【对数帧】比例走，与图表的对数横轴一致 —— 于是滑块从头移到尾，
  // 游标在图上也是匀速移动，不会在采样密的区段「一格跳很多帧」、在疏的区段又不动。
  var SCRUB_MAX = 1000;
  function tOfFrame(f){
    var a = log10(1), b = log10(TOTAL);
    return Math.max(0, Math.min(1, (log10(f) - a) / ((b - a) || 1)));
  }
  function frameOfT(t){ return Math.pow(10, log10(1) + t * (log10(TOTAL) - log10(1))); }
  function nearestIndex(f){
    var best = 0, bd = Infinity;
    for (var i = 0; i < samples.length; i++){
      var d = Math.abs(log10(samples[i][0]) - log10(f));
      if (d < bd){ bd = d; best = i; }
    }
    return best;
  }
  function nearestSampleLinear(f){
    // 线性最近 —— 阶段卡跳帧用它（`nearestIndex` 按【对数】距离取，长尾处会偏）。
    var best = 0, bd = Infinity;
    for (var i = 0; i < samples.length; i++){
      var d = Math.abs(samples[i][0] - f);
      if (d < bd){ bd = d; best = i; }
    }
    return best;
  }
  function visible(){
    var out = [], i, p;
    for (i = 0; i < samples.length; i++){
      p = samples[i];
      if (p[0] >= win.lo && p[0] <= win.hi){ out.push(p); }
    }
    // 各向外扩一个点，曲线才能接到窗口边缘
    for (i = samples.length - 1; i >= 0; i--){
      if (samples[i][0] < win.lo){ out.unshift(samples[i]); break; }
    }
    for (i = 0; i < samples.length; i++){
      if (samples[i][0] > win.hi){ out.push(samples[i]); break; }
    }
    return out;
  }

  // ---------- 图表 ----------
  var CHARTS = [
    {cv:'cv1', lg:'lg1', h:210,
     series:[[L[1], 1, '#7fd0ff'], [L[2], 2, '#ff8a8a']]},
    {cv:'cv2', lg:'lg2', h:175,
     series:[[L[3], 3, '#7fe0a0'], [L[5], 5, '#e8c06a']]}
  ];

  function drawChart(c){
    var S = visible(), i, k;
    var h = c.h, parts = ['<svg viewBox="0 0 ' + W + ' ' + h +
      '" class="chart" preserveAspectRatio="none">'];
    for (k = 1; k < 5; k++){
      var y = PAD + (h - 2 * PAD) * k / 5;
      parts.push('<line x1="' + PAD + '" y1="' + y.toFixed(1) + '" x2="' + (W - PAD) +
                 '" y2="' + y.toFixed(1) + '" stroke="#2a2f3d" stroke-width="1"/>');
    }
    // 换代刻度：用【真实记录】画，不用采样序列推断 —— 否则最后一次换代常常落在
    // 采样窗口之外，右端看起来像「世界停在半路」。
    for (i = 0; i < promos.length; i++){
      var pf = promos[i][0];
      if (pf < win.lo || pf > win.hi) continue;
      var px = xOf(pf).toFixed(1);
      parts.push('<line x1="' + px + '" y1="' + PAD + '" x2="' + px + '" y2="' +
                 (h - PAD) + '" stroke="#7fd0ff" stroke-width="0.6" ' +
                 'stroke-dasharray="3 4" opacity="0.55"/>');
    }
    var legend = [];
    for (i = 0; i < c.series.length; i++){
      var name = c.series[i][0], idx = c.series[i][1], color = c.series[i][2];
      var vals = S.map(function(p){ return p[idx]; });
      if (!vals.length) continue;
      var vmin = Math.min.apply(null, vals), vmax = Math.max.apply(null, vals);
      if (vmax === vmin){ vmax += 1; vmin -= 1; }
      var poly = S.map(function(p){
        var y = h - PAD - (p[idx] - vmin) / (vmax - vmin) * (h - 2 * PAD);
        return xOf(p[0]).toFixed(1) + ',' + y.toFixed(1);
      }).join(' ');
      parts.push('<polyline points="' + poly + '" fill="none" stroke="' + color +
                 '" stroke-width="1.6"/>');
      legend.push('<span style="color:' + color + '">■</span> ' + esc(name) +
                  ' <em>[' + vmin + ' ~ ' + vmax + ']</em>');
    }
    parts.push('<line class="curline" x1="0" y1="' + PAD + '" x2="0" y2="' + (h - PAD) +
               '" stroke="#e8c06a" stroke-width="1" stroke-dasharray="4 3" opacity="0"/>');
    parts.push('</svg>');
    $(c.cv).innerHTML = parts.join('');
    $(c.lg).innerHTML = legend.join(' &nbsp; ');
    bindChart($(c.cv).firstChild, c);
  }

  function drawAll(){
    for (var i = 0; i < CHARTS.length; i++) drawChart(CHARTS[i]);
    drawTimeline();
    cursorLine();
    if ($('listmode') && $('listmode').checked) renderEventList();
    var txt = fmt(Math.round(win.lo)) + ' – ' + fmt(Math.round(win.hi)) + ' 帧';
    $('win').textContent = (win.lo <= 1 && win.hi >= TOTAL) ? '全部（' + txt + '）' : txt;
  }

  function bindChart(svg, c){
    if (!svg) return;
    var tip = svg.parentNode.parentNode.querySelector('.tip');
    svg.addEventListener('mousemove', function(e){
      if (!tip) return;
      var rect = svg.getBoundingClientRect();
      var f = frameAt((e.clientX - rect.left) / rect.width * W);
      var best = null, bd = Infinity;
      for (var i = 0; i < samples.length; i++){
        var d = Math.abs(samples[i][0] - f);
        if (d < bd){ bd = d; best = samples[i]; }
      }
      if (!best) return;
      var out = [];
      for (var j = 0; j < 6; j++) out.push(L[j] + ' ' + best[j]);
      tip.textContent = out.join(' · ');
      tip.style.display = 'block';
      var b = svg.parentNode.parentNode.getBoundingClientRect();
      var x = e.clientX - b.left + 8;
      if (x > b.width / 2){ tip.style.right = Math.max(8, b.width - x + 16) + 'px';
                            tip.style.left = 'auto'; }
      else { tip.style.left = Math.max(8, x) + 'px'; tip.style.right = 'auto'; }
    });
    svg.addEventListener('mouseleave', function(){ if (tip) tip.style.display = 'none'; });
  }

  // 缩放 / 平移对【两块曲线与时间线】一视同仁 —— 在任意一张图上操作，全部视图一起动。
  //
  // 关键：监听必须挂在【不会被重绘替换】的容器上（#cv1 / #cv2 / #tl-box 这几个 div），
  // 不能在 svg 上 —— 每次拖动都要重绘画布，svg 整个被换掉，挂在它身上的 mousemove
  // 就再也收不到事件，拖动会「走一帧就断」。这里改用容器 + window 级 move/up。
  function bindZoom(box){
    if (!box || box.__zoomBound) return;
    box.__zoomBound = true;
    var dragging = false, lastX = 0;
    function svgRect(){
      var svg = box.querySelector('svg');
      if (!svg) return null;
      var r = svg.getBoundingClientRect();
      return r.width > 0 ? r : null;
    }
    function frameAtX(clientX){
      var r = svgRect();
      return r ? frameAt((clientX - r.left) / r.width * W) : null;
    }
    function spanLog(){ return log10(win.hi) - log10(win.lo); }
    box.addEventListener('mousedown', function(e){
      if (!svgRect()) return;
      dragging = true; lastX = e.clientX;
      box.classList.add('dragging');
      e.preventDefault();                       // 别让它顺手选中文字
    });
    window.addEventListener('mousemove', function(e){
      if (!dragging) return;
      var r = svgRect();
      if (!r) return;
      // 平移量按【像素位移】换算（拖动 = 抓住画布拖），而不是「同一点在新窗口下的帧」——
      // 后者自我参照：平移后同一点对应的帧已经变了，增量会来回翻，表现为隔步生效 / 回跳。
      panBy(-(e.clientX - lastX) / r.width * spanLog());
      lastX = e.clientX;
    });
    window.addEventListener('mouseup', function(){
      if (!dragging) return;
      dragging = false; box.classList.remove('dragging');
    });
    box.addEventListener('wheel', function(e){
      var f = frameAtX(e.clientX);
      if (f == null) return;
      e.preventDefault();
      zoomAround(f, e.deltaY < 0 ? 0.7 : 1.4, true);
    }, {passive:false});
  }

  function centerFrame(){ return Math.pow(10, (log10(win.lo) + log10(win.hi)) / 2); }
  function zoomAround(anchor, factor, redraw){
    var a = log10(win.lo), b = log10(win.hi), c = log10(anchor);
    var lo = c - (c - a) * factor, hi = c + (b - c) * factor;
    lo = Math.max(0, lo); hi = Math.min(log10(TOTAL), hi);
    if (hi - lo < 0.05) return;                       // 别缩成一条线
    win.lo = Math.pow(10, lo); win.hi = Math.pow(10, hi);
    if (win.hi / win.lo > TOTAL) { win.lo = 1; win.hi = TOTAL; }
    if (redraw !== false) drawAll();
  }
  function panBy(deltaLog){
    var top = log10(TOTAL), a = log10(win.lo), b = log10(win.hi);
    var lo = a + deltaLog, hi = b + deltaLog;
    if (lo < 0){ hi -= lo; lo = 0; }
    if (hi > top){ lo -= (hi - top); hi = top; }
    win.lo = Math.pow(10, Math.max(0, lo)); win.hi = Math.pow(10, hi);
    drawAll();
  }

  // ---------- 时间线 ----------
  // 事件节点文字：默认【不显示】—— 只有鼠标靠近某个节点，才把它的引线「伸出」、
  // 文字「裁剪展开」（两者都用 lerp 补间，见 applyMark / tickMarks）。时间线图上方
  // 那个开关（`#showmarks`）打开后，按「放得下才显示」的稀疏规则常显（= 旧行为）。
  var markMid = 0, markEls = [], markT = [], markRoom = [];
  var markHover = -1, showAllMarks = false, markRaf = null;
  var nearSticky = '';   // 定位按钮那种【该留着的】读数；鼠标划走时恢复它，而不是留一句过期的

  function markTarget(i){
    return (i === markHover || (showAllMarks && markRoom[i])) ? 1 : 0;
  }
  function applyMark(i){
    var e = markEls[i];
    if (!e || !e.stem) return;
    var t = markT[i];
    // 引线：外端从「贴轴」长到目标位置
    e.stem.setAttribute('y2', (e.yin + (e.yout - e.yin) * t).toFixed(1));
    if (e.text){
      e.text.setAttribute('opacity', t.toFixed(3));
      if (e.cp && e.tw){          // 文字裁剪展开：起笔那侧固定，宽度随 t 长出来
        if (e.anchor === 'start'){ e.cp.setAttribute('width', (e.tw * t).toFixed(1)); }
        else { e.cp.setAttribute('x', (e.bx + e.tw * (1 - t)).toFixed(1));
               e.cp.setAttribute('width', (e.tw * t).toFixed(1)); }
      }
    }
  }
  function tickMarks(){
    markRaf = null;
    var dirty = false;
    for (var i = 0; i < markT.length; i++){
      var tgt = markTarget(i), t = markT[i];
      if (Math.abs(tgt - t) <= 0.002){
        if (t !== tgt){ markT[i] = tgt; applyMark(i); }
        continue;
      }
      markT[i] = t + (tgt - t) * 0.18;    // lerp：越接近越慢，收尾平滑
      applyMark(i);
      dirty = true;
    }
    if (dirty) markRaf = requestAnimationFrame(tickMarks);
  }
  function kickMarks(){ if (markRaf === null) markRaf = requestAnimationFrame(tickMarks); }

  function drawTimeline(){
    var h = 250, mid = h / 2, i;
    markMid = mid;
    var parts = ['<svg viewBox="0 0 ' + W + ' ' + h +
                 '" class="chart" id="tl-svg" preserveAspectRatio="none">'];
    // 阶段带：初始变量域那几档的帧区间（与曲线同一套对数换算）。没有它，读者的
    // 注意力会被再创世那几百个刻度一个人占满，看不见最前面那一万帧里的三档。
    var bandY = 8, bandH = 20;
    for (i = 0; i < stages.length; i++){
      var sg = stages[i];
      var s0 = Math.max(sg.start, win.lo), s1 = Math.min(sg.end, win.hi);
      if (s1 < win.lo || s0 > win.hi) continue;
      var bx = xOf(s0), bw = Math.max(1.5, xOf(s1) - bx);
      parts.push('<rect x="' + bx.toFixed(1) + '" y="' + bandY + '" width="' +
                 bw.toFixed(1) + '" height="' + bandH + '" fill="' +
                 (i % 2 ? '#26303f' : '#1d2531') + '"/>');
      if (bw > 60){
        parts.push('<text x="' + (bx + 4).toFixed(1) + '" y="' + (bandY + 14) +
                   '" fill="#8ab4ff" font-size="10">' +
                   esc(sg.name + ' ' + fmt(sg.start) + '–' + fmt(sg.end)) + '</text>');
      }
    }
    for (i = 0; i < spans.length; i++){
      var s = spans[i][0], e = spans[i][1];
      if (e < win.lo || s > win.hi) continue;
      var x1 = xOf(Math.max(s, win.lo)), x2 = xOf(Math.min(e, win.hi));
      parts.push('<rect x="' + x1.toFixed(1) + '" y="' + (mid - 8) + '" width="' +
                 Math.max(2, x2 - x1).toFixed(1) + '" height="16" fill="#ff8a8a" ' +
                 'opacity="0.18"/>');
    }
    // 「世界内」分界：演算期 ⇄ 世界内那条线（与报告、编年史同一帧 —— 都取换档事件）。
    if (mythFrom !== null && mythFrom !== undefined &&
        mythFrom >= win.lo && mythFrom <= win.hi){
      var gx = xOf(mythFrom);
      parts.push('<line x1="' + gx.toFixed(1) + '" y1="' + (bandY + bandH) +
                 '" x2="' + gx.toFixed(1) + '" y2="' + (h - PAD) +
                 '" stroke="#8ab4ff" stroke-width="1.2" stroke-dasharray="5 4" opacity="0.75"/>');
      parts.push('<text x="' + (gx + 4).toFixed(1) + '" y="' + (h - PAD - 4) +
                 '" fill="#8ab4ff" font-size="10">世界内 · 第 ' + fmt(mythFrom) +
                 ' 帧起</text>');
    }
    parts.push('<line x1="' + PAD + '" y1="' + mid + '" x2="' + (W - PAD) + '" y2="' +
               mid + '" stroke="#3a4152" stroke-width="1.5"/>');
    // 节点：圆点常显；引线与文字**默认收起**，鼠标靠近才展开（见 applyMark）。
    // `markRoom` = 这一条按稀疏规则「放得下」—— 开关打开时常显的就是这些。
    var shown = [], minGap = 96;
    markRoom = [];
    for (i = 0; i < marks.length; i++){
      var m = marks[i], mf = m[0];
      if (mf < win.lo || mf > win.hi) continue;
      var mx = xOf(mf), up = shown.length % 2 === 0;
      var yin = up ? mid - 6 : mid + 6, yout = up ? mid - 15 : mid + 19;
      var ty = up ? mid - 20 : mid + 28;
      var room = !shown.length || (mx - shown[shown.length - 1] >= minGap);
      markRoom[i] = room;
      parts.push('<g class="mk" data-ev="' + i + '">'
                 + '<line class="ms" data-ev="' + i + '" x1="' + mx.toFixed(1) +
                 '" y1="' + yin + '" x2="' + mx.toFixed(1) + '" y2="' + yin +
                 '" data-yout="' + yout + '" stroke="' + m[3] + '" stroke-width="1"/>'
                 + '<circle class="md" data-ev="' + i + '" cx="' + mx.toFixed(1) +
                 '" cy="' + mid + '" r="3.4" fill="' + m[3] + '"/></g>');
      var label = m[2].length > 30 ? m[2].slice(0, 30) + '…' : m[2];
      var anchor = mx < W - 200 ? 'start' : 'end';
      var tx = mx + (anchor === 'start' ? 4 : -4);
      parts.push('<clipPath id="cpc' + i + '"><rect id="cpr' + i + '" x="' + tx.toFixed(1) +
                 '" y="' + (ty - 9) + '" width="0" height="12"/></clipPath>'
                 + '<text class="ml" data-ev="' + i + '" x="' + tx.toFixed(1) + '" y="' + ty +
                 '" fill="' + m[3] + '" font-size="10" text-anchor="' + anchor +
                 '" clip-path="url(#cpc' + i + ')" opacity="0">' + esc(label) + '</text>');
      if (room) shown.push(mx);
    }
    parts.push('<line class="curline" x1="0" y1="' + PAD + '" x2="0" y2="' + (h - PAD) +
               '" stroke="#e8c06a" stroke-width="1" stroke-dasharray="4 3" opacity="0"/>');
    parts.push('</svg>');
    var box = $('tl-box');
    box.innerHTML = parts.join('');
    var svg = box.firstChild;
    // 收集元素引用 + 量一次标签宽度（裁剪展开要用）—— 只在此处量，动画里不再量。
    var byIdx = {};
    var nodes = svg.querySelectorAll('line.ms, text.ml');
    for (i = 0; i < nodes.length; i++){
      var n = nodes[i], k = n.getAttribute('data-ev');
      var o = byIdx[k] || (byIdx[k] = {});
      if (n.tagName === 'line'){
        o.stem = n;
        o.yin = Number(n.getAttribute('y1'));
        o.yout = Number(n.getAttribute('data-yout'));
      } else {
        o.text = n;
        o.cp = svg.querySelector('#cpr' + k);
        o.anchor = n.getAttribute('text-anchor');
        var bb = n.getBBox();
        o.tw = Math.max(4, bb.width); o.bx = bb.x;
      }
    }
    markEls = []; markT = [];
    for (i = 0; i < marks.length; i++){
      markEls[i] = byIdx[i] || null;
      // 重建后按当前状态【直接就位】—— 免得缩放 / 平移时标签一次次重播动画
      markT[i] = markTarget(i);
      applyMark(i);
    }
    svg.addEventListener('mousemove', function(e){
      var r = svg.getBoundingClientRect();
      var ux = (e.clientX - r.left) / r.width * W;    // 视口像素 → SVG 用户坐标
      // 靠近某个节点（像素阈值内）才把它展开；否则一律收起
      var near = -1, nd = 24;
      for (var j = 0; j < marks.length; j++){
        if (marks[j][0] < win.lo || marks[j][0] > win.hi) continue;
        var dd = Math.abs(xOf(marks[j][0]) - ux);
        if (dd < nd){ nd = dd; near = j; }
      }
      if (near !== markHover){ markHover = near; kickMarks(); }
      // `#near` 那行读数照旧：给最近事件的名字（与像素近邻无关）
      var f = frameAt(ux);
      var best = null, bd = Infinity;
      for (var k2 = 0; k2 < marks.length; k2++){
        var d = Math.abs(log10(marks[k2][0]) - log10(f));
        if (d < bd){ bd = d; best = marks[k2]; }
      }
      if (best){ $('near').textContent = '帧 ' + fmt(best[0]) + ' · ' + best[2]; }
    });
    svg.addEventListener('mouseleave', function(){
      if (markHover !== -1){ markHover = -1; kickMarks(); }
      $('near').textContent = nearSticky;   // 划走就收起 —— 恢复「定位」留下的那句（若有）
    });
    // 双击节点：编年史翻到那一帧那条（滚过去 + 高亮）
    svg.addEventListener('dblclick', function(e){
      var r = svg.getBoundingClientRect();
      var ux = (e.clientX - r.left) / r.width * W;
      var j = -1, jd = Infinity;
      for (var q2 = 0; q2 < marks.length; q2++){
        var dq = Math.abs(xOf(marks[q2][0]) - ux);
        if (dq < jd){ jd = dq; j = q2; }
      }
      if (j < 0 || jd > 24) return;         // 没点在节点上就不管
      e.preventDefault();
      revealInChronicle(marks[j][4], marks[j][0]);   // 事件号优先，帧号兜底
    });
  }

  // ---------- 回放 ----------
  function curSample(){ return samples.length ? samples[Math.max(0, Math.min(cur, samples.length - 1))] : null; }
  function curFrame(){ var s = curSample(); return s ? s[0] : null; }

  function cursorLine(){
    var f = curFrame();
    var lines = document.querySelectorAll('svg .curline');
    for (var i = 0; i < lines.length; i++){
      if (f == null || f < win.lo || f > win.hi){ lines[i].setAttribute('opacity', '0'); continue; }
      var x = xOf(f);
      lines[i].setAttribute('x1', x); lines[i].setAttribute('x2', x);
      lines[i].setAttribute('opacity', '1');
    }
  }

  function renderSeats(idxs){
    var box = $('seats');
    if (!box) return;
    // 服务端预渲染的那份「终局视图」只有静态导出才有；实时看板首屏是空的，
    // 别把空串当成 home —— 否则回放走到末帧会把整排席位抹掉。
    if (seatsHome === null && box.innerHTML.trim()) seatsHome = box.innerHTML;
    // 游标停在最后一帧时恢复终局视图（带封印 / 空置样式与证伪进度）；
    // 中间的任意时刻则用回放视图（只有职位与在位者 —— 那些量没有逐帧存下来）。
    if (cur >= samples.length - 1 && seatsHome){
      box.innerHTML = seatsHome;
    } else {
      // 演算期（前三个阶段）里这 12 位还没有职位 / 称号 / 城邦 —— 改显因子口径。
      var sim = simPhase(curFrame());
      box.innerHTML = idxs.map(function(v, i){
        var name = v ? seatNames[v - 1] : null;
        var machine = v ? (machineNames[v - 1] || '') : '';
        var cls = 'seat' + (v ? '' : ' vacant');
        var duty = sim ? (simslot[i] || ('第 ' + i + ' 号原动力'))
                       : (duties[i] || ('L' + String(i).padStart(2, '0')));
        // 称号 / 城邦两行只属于第四阶段 —— 演算期整两行【不摆】（不是显示「—」）
        var place = sim ? '' :
          ('<div class="seat-region">' + esc(regions[i] || '') + '</div>' +
           '<div class="seat-city">' +
           (cityidx[i] >= 0 ? '<i class="citydot k' + cityidx[i] + '"></i>' : '') +
           esc(cities[i] || '—') + '</div>');
        return '<div class="' + cls + '" data-name="' + esc(name || '（空置）') +
          '" data-machine="' + esc(machine) + '">' +
          '<div class="seat-top"><span class="seat-duty">' +
          esc(duty) +
          '</span><span class="seat-id">' + esc('L' + String(i).padStart(2, '0')) +
          '</span></div>' + place +
          '<div class="seat-name">' + esc(name || '（空置）') + '</div>' +
          '<div class="seat-state">' + (v ? '在位' : '空置') + '</div></div>';
      }).join('');
    }
    // 城邦图例只在第四阶段有意义（演算期那 12 位没有城邦）
    var lg = document.querySelector('.citylegend');
    if (lg) lg.style.display = simPhase(curFrame()) ? 'none' : '';
    bindSeatClicks();
    applyPicked();
  }

  function applyCursor(){
    var s = curSample();
    if (!s) return;
    $('cursor').textContent = '帧 ' + fmt(s[0]) + ' · ' + L[1] + ' ' + s[1] +
      ' · ' + L[2] + ' ' + s[2] + ' · ' + L[3] + ' ' + s[3] +
      ' · ' + L[4] + ' ' + s[4] + ' · ' + L[5] + ' ' + s[5];
    var sc = $('scrub');
    sc.max = SCRUB_MAX;
    sc.value = Math.round(tOfFrame(s[0]) * SCRUB_MAX);   // 与对数横轴对齐
    cursorLine();
    renderSeats(s[6]);
    render();
  }

  function renderCards(list){
    if (!list || !list.length) return;
    $('cards').innerHTML = list.map(function(c){
      return '<div class="card"><div class="k">' + esc(c[0]) + '</div>' +
             '<div class="v' + (c[2] ? ' mono' : '') + '">' + esc(c[1]) + '</div></div>';
    }).join('');
  }

  function tick(){
    if (cur >= samples.length - 1){ setPlaying(false); return; }
    cur++; applyCursor();
  }
  function setPlaying(on){
    playing = on;
    $('play').textContent = on ? '⏸ 暂停' : '▶ 播放';
    if (timer){ clearInterval(timer); timer = null; }
    if (on){ timer = setInterval(tick, Math.max(16, 80 / speed)); }
  }

  // ---------- 编年史 ----------
  var chronLimit = __ROWS__;
  function render(){
    var q = ($('q').value || '').trim();
    var limit = curFrame();
    var frag = document.createDocumentFragment();
    var matched = 0, added = 0, hitIdx = jumpIdx, mi = 0;
    for (var i = 0; i < rows.length; i++){
      var r = rows[i];
      if (limit != null && r[0] > limit) break;          // 回放：只显示已发生的
      if (q && r[1].indexOf(q) < 0) continue;
      matched++;
      if (added >= shown) continue;
      added++;
      var li = document.createElement('li');
      li.className = 'ln';
      li.innerHTML = '<span class="lf">帧 ' + fmt(r[0]) + '</span> ' + esc(r[1]) +
                     (r[2] ? ' <span class="lb">' + esc(r[2]) + '</span>' : '');
      frag.appendChild(li);
      if (mi === hitIdx) hit = li;
      mi++;
    }
    matchedTotal = matched;
    list.innerHTML = '';
    list.appendChild(frag);
    count.textContent = '显示 ' + fmt(added) + ' / 匹配 ' + fmt(matched) +
                        ' / 共 ' + fmt(rows.length) + ' 条' +
                        (limit != null ? '（已发生 ' + fmt(limit) + ' 帧前）' : '');
    if (added < matched){
      var more = document.createElement('li');
      more.className = 'more';
      more.textContent = '… 还有 ' + fmt(matched - added) + ' 条，滚动到底部继续载入';
      list.appendChild(more);
    }
    if (hit){ hit.classList.add('hit'); hit.scrollIntoView({block: 'center'}); }
  }

  // ---------- 席位点击（点空白处取消） ----------
  var pickedName = '';
  function clearPicked(){
    if (!pickedName) return;
    var p = document.querySelectorAll('.seat.picked');
    for (var i = 0; i < p.length; i++) p[i].classList.remove('picked');
    // 取消选中时，连同它填进筛选框的那次过滤一并撤掉（手动敲进去的过滤不动）。
    if ($('q').value === pickedName){
      $('q').value = ''; shown = chronLimit; jumpIdx = -1; render();
    }
    pickedName = '';
  }
  function applyPicked(){
    if (!pickedName) return;
    var seats = document.querySelectorAll('.seat');
    for (var i = 0; i < seats.length; i++){
      if (seats[i].getAttribute('data-name') === pickedName) seats[i].classList.add('picked');
    }
  }
  function bindSeatClicks(){
    var seats = document.querySelectorAll('.seat');
    for (var i = 0; i < seats.length; i++){
      seats[i].onclick = function(ev){
        ev.stopPropagation();
        var name = this.getAttribute('data-name') || '';
        if (!name || name.indexOf('（空置）') >= 0) return;
        var same = (pickedName === name);
        clearPicked();                     // 先撤旧的（含它填进筛选框的过滤）
        if (!same){
          pickedName = name;
          $('q').value = name;
          shown = chronLimit; jumpIdx = -1; render();
          this.classList.add('picked');
        }
      };
    }
  }

  // ---------- 过滤 / 跳帧 ----------
  var shown = chronLimit, matchedTotal = 0, jumpIdx = -1, hit = null;
  var list = $('chron'), count = $('count');

  function hitIndex(){
    var f = $('jf').value === '' ? null : Number($('jf').value);
    if (f === null) return -1;
    var q = ($('q').value || '').trim(), best = -1, bd = Infinity, idx = 0;
    for (var i = 0; i < rows.length; i++){
      var r = rows[i];
      if (q && r[1].indexOf(q) < 0) continue;
      var d = Math.abs(r[0] - f);
      if (d < bd){ bd = d; best = idx; }
      idx++;
    }
    return best;
  }
  // 双击时间线上的节点：编年史翻到那一帧【那一条】，滚过去并高亮（复用「定位」的高亮）。
  // 先按 `rid`（事件号）精确命中 —— 同一帧里往往有好几条（换代 / 变量域推进 / 外生介入…），
  // 只按帧号取会撞上排在最前的那条，选中 A 却高亮 B；命中不到（如该类被详细程度静音）再
  // 退回按帧号取第一条。
  function revealInChronicle(rid, frame){
    var i = -1, a;
    if (rid !== undefined && rid !== null){
      for (a = 0; a < rows.length; a++){
        if (rows[a][3] === rid){ i = a; break; }
      }
    }
    if (i < 0 && frame !== undefined && frame !== null){
      var f = Number(frame);
      for (a = 0; a < rows.length; a++){
        if (rows[a][0] === f){ i = a; break; }
      }
    }
    if (i < 0) return false;
    if (i + 1 > shown) shown = i + 1;    // 先把那条纳入「已载入」，否则压根没渲染
    jumpIdx = i;
    render();
    if (hit && hit.scrollIntoView){
      hit.scrollIntoView({block: 'center', behavior: 'smooth'});
    }
    return true;
  }

  function doJump(){
    jumpIdx = hitIndex();
    if (jumpIdx >= 0 && jumpIdx + 1 > shown) shown = jumpIdx + 1;
    var f = $('jf').value === '' ? null : Number($('jf').value);
    if (f !== null){
      var m = null, bd = Infinity;
      for (var i = 0; i < marks.length; i++){
        var d = Math.abs(marks[i][0] - f);
        if (d < bd){ bd = d; m = marks[i]; }
      }
      nearSticky = m ? ('最接近的事件：帧 ' + fmt(m[0]) + ' · ' + m[2]) : '';
      $('near').textContent = nearSticky;
      // 顺手把时间窗挪到那一带，看得见
      if (f < win.lo || f > win.hi) { win.lo = Math.max(1, f / 4); win.hi = Math.min(TOTAL, f * 4); drawAll(); }
    } else { nearSticky = ''; $('near').textContent = ''; }
    render();
  }

  // ---------- 实时（--serve） ----------
  var live = D.live, sinceRows = rows.length, sinceSamples = samples.length;

  // 演算跑完的那条提示：只在 `--no-serve-reload` 下用得到（默认是直接重载）。
  function showDoneToast(){
    if (doneShown) return;
    doneShown = true;
    var t = $('done-toast');
    if (t) t.classList.add('show');          // .show 负责过渡（透明度 + 位移）
  }

  function poll(){
    fetch('state?rows=' + sinceRows + '&samples=' + sinceSamples +
          '&names=' + seatNames.length)
      .then(function(r){ return r.json(); })
      .then(function(s){
        if (s.rows && s.rows.length){ rows = rows.concat(s.rows); sinceRows = rows.length; }
        if (s.samples && s.samples.length){
          samples = samples.concat(s.samples); sinceSamples = samples.length;
        }
        if (s.seatnames && s.seatnames.length){
          seatNames = seatNames.concat(s.seatnames);
        }
        if (s.machines && s.machines.length){       // 与 seatNames 同步长的机器编号表
          machineNames = machineNames.concat(s.machines);
        }
        // 打点与换代刻度很小，服务端每次全量给 —— 整份替换，别重复拼
        if (s.promos) promos = s.promos;
        if (s.marks) marks = s.marks;
        if (s.mythfrom !== undefined) mythFrom = s.mythfrom;  // 世界内起点（阶段语汇边界）
        if (s.stages) stages = s.stages;            // 阶段带随之长出来（时间线用）
        if (s.stageshtml){                          // 阶段目录：就地补进占位容器
          var sb = $('stages-block');
          if (sb && sb.innerHTML !== s.stageshtml){
            sb.innerHTML = s.stageshtml;
            bindStageClicks();                      // 新卡片要重新挂点击
          }
        }
        TOTAL = Math.max(TOTAL, s.frame || 0); D.total = TOTAL;
        if (follow) cur = samples.length - 1;
        $('liveflag').textContent = s.done
          ? (' ● 已完成 · 裁决 ' + (s.verdict || '') + ' · 帧 ' + fmt(s.frame || 0))
          : (' ● 实时 · 帧 ' + fmt(s.frame || 0));
        if (s.done) renderCards(s.cards);
        drawAll(); applyCursor();
        // 跑完、且服务端已把【完整静态页】备好 —— 两条路：
        //   · 默认：自动重载同一地址（此后这一页就是与 `--export` 一致的那张）；
        //   · `--no-serve-reload`：右下角弹提示，由用户点「立即查看」再切过去。
        if (s.done && s.final){
          if (autoreload){ location.reload(); return; }
          showDoneToast(); return;          // 已到终点，不必再轮询
        }
        if (!s.done || !s.final) setTimeout(poll, 700);
      })
      .catch(function(){ $('liveflag').textContent = ' ● 连接中断'; });
  }

  // ---------- 绑定 ----------
  // 五颗按钮语义写死写清：回到开始 / 前一帧 / 播放暂停 / 后一帧 / 跳到末尾。
  function goto(idx, keepFollow){
    setPlaying(false);
    follow = !!keepFollow;
    cur = Math.max(0, Math.min(samples.length - 1, idx));
    applyCursor();
  }
  $('scrub').max = SCRUB_MAX;
  $('scrub').addEventListener('input', function(){
    follow = false; setPlaying(false);
    cur = nearestIndex(frameOfT(Number(this.value) / SCRUB_MAX));
    applyCursor();
  });
  $('play').addEventListener('click', function(){
    if (playing){ setPlaying(false); return; }
    if (cur >= samples.length - 1) cur = 0;      // 已在末尾：从头放
    follow = false;
    setPlaying(true);
  });
  $('rewind').addEventListener('click', function(){ goto(0); });
  $('prev').addEventListener('click', function(){ goto(cur - 1); });
  $('next').addEventListener('click', function(){ goto(cur + 1); });
  $('toend').addEventListener('click', function(){ goto(samples.length - 1, true); });
  $('speed').addEventListener('change', function(){
    speed = Number(this.value) || 1;
    if (playing) setPlaying(true);
  });
  $('q').addEventListener('input', function(){ shown = chronLimit; jumpIdx = -1; render(); });
  $('jf').addEventListener('input', doJump);
  $('jump').addEventListener('click', doJump);
  $('clear').addEventListener('click', function(){
    $('q').value = ''; $('jf').value = ''; shown = chronLimit; jumpIdx = -1;
    clearPicked(); nearSticky = ''; $('near').textContent = ''; render();
  });
  document.body.addEventListener('click', function(ev){
    // 只在工具栏【之外】点空白才取消选中 —— 在搜索框里改过滤词不算「点别处」。
    if (ev.target && ev.target.closest && ev.target.closest('.toolbar')) return;
    clearPicked();
  });
  $('z-in').addEventListener('click', function(){ zoomAround(curFrame() || centerFrame(), 0.6, true); });
  $('z-out').addEventListener('click', function(){ zoomAround(curFrame() || centerFrame(), 1.7, true); });
  $('z-reset').addEventListener('click', function(){
    win.lo = 1; win.hi = TOTAL; drawAll(); });
  // 「演算完成」提示的两颗按钮：× 收起（带过渡），「立即查看」→ 重载到完整静态页。
  if ($('done-x')) $('done-x').onclick = function(){
    var t = $('done-toast'); if (t) t.classList.remove('show');
  };
  if ($('done-view')) $('done-view').onclick = function(){ location.reload(); };
  $('showmarks').addEventListener('change', function(){
    // 开关只改【默认展开】这一态：打开时常显「放得下」的那些节点，关闭时一律
    // 回到「靠近才展开」。动画由 kickMarks 的补间接管。
    showAllMarks = this.checked; kickMarks();
  });
  $('listmode').addEventListener('change', function(){
    var on = this.checked;
    $('evlist').hidden = !on;
    $('tl-box').parentNode.style.display = on ? 'none' : 'block';
    if (on) renderEventList();
  });
  function renderEventList(){
    var out = [];
    for (var i = 0; i < marks.length; i++){
      var m = marks[i];
      out.push('<li class="ev"><span class="dot" style="background:' + m[3] + '"></span>' +
               '<span><span class="lf">帧 ' + fmt(m[0]) + '</span> ' + esc(m[2]) +
               ' <span class="dim">（' + esc(m[1]) + '）</span></span></li>');
    }
    $('evlist').innerHTML = out.join('');
  }
  list.addEventListener('scroll', function(){
    if (shown >= matchedTotal) return;
    if (list.scrollHeight - list.scrollTop - list.clientHeight < 200){
      shown += chronLimit; render();
    }
  });

  // 席位卡悬浮：灰字报「电信号序列 <机器编号>」。挂在 **document** 上而不是卡片上 ——
  // 回放换人时卡片会整批重建；而且鼠标一离开卡片（甚至离开窗口）就得立刻收起。
  var seattipBound = false;
  function bindSeatHover(){
    if (seattipBound) return;
    seattipBound = true;
    document.addEventListener('mousemove', function(ev){
      var tip = $('seattip');
      var card = ev.target && ev.target.closest ? ev.target.closest('.seat') : null;
      var m = card ? (card.getAttribute('data-machine') || '') : '';
      if (!m){ tip.style.display = 'none'; return; }
      // `?` = 预设标了「外部变量」的那几位（自天外而来、不属电信号序列）
      tip.textContent = (m === '?' ? '外部变量 · ?' : '电信号序列 ' + m);
      tip.style.display = 'block';
      // 摆在鼠标【上方】：先显出来才量得到高度（贴顶时夹住，别跑到屏幕外）
      tip.style.left = (ev.clientX + 14) + 'px';
      tip.style.top = Math.max(4, ev.clientY - tip.offsetHeight - 12) + 'px';
    });
    window.addEventListener('scroll', function(){
      $('seattip').style.display = 'none';           // 滚动后位置就旧了，先收起
    }, {passive: true});
  }

  // 阶段卡可点：跳回该档开始的帧（回放游标 + 时间窗一起过去）。
  function bindStageClicks(){
    var cards = document.querySelectorAll('.stage[data-start]');
    for (var i = 0; i < cards.length; i++){
      cards[i].onclick = function(){
        var f = Number(this.getAttribute('data-start'));
        if (!samples.length || !isFinite(f)) return;   // 注意：0 是合法帧号，别拿 !f 判空
        setPlaying(false); follow = false;
        if (f > 0 && (f < win.lo || f > win.hi)){
          win.lo = Math.max(1, f / 4); win.hi = Math.min(TOTAL, f * 4);
        }
        cur = nearestSampleLinear(f);   // 采样点上「最接近该帧」的那个
        drawAll(); applyCursor();
      };
    }
  }

  bindSeatClicks();
  bindSeatHover();
  bindStageClicks();
  bindZoom($('cv1')); bindZoom($('cv2')); bindZoom($('tl-box'));   // 挂在稳定的 div 上
  drawAll();
  applyCursor();
  if (live) poll();
})();
"""


def _seat_meta(ctx):
    """十二席的职位名 / 称号 / 城邦（回放换人时这些都不变，只有人名在变）。

    城邦是可空缺的：缺席的席位是空串、配色编号 -1（渲染成「—」且不画点）。
    """
    cal = ctx.phonology.get("title_calibration", {})
    regions = ctx.lexicon.get("regions", {})
    duties, regs = [], []
    for locus in ctx.loci:
        duties.append(cal.get(locus.id, ["", locus.id])[1] or locus.id)
        regs.append(regions.get(locus.id, ""))
    cities, city_names, city_idx = _city_meta(ctx)
    return duties, regs, cities, city_names, city_idx


def _sim_slots(ctx):
    """演算期（前三个阶段）里那 12 位分别叫什么 —— 「第 N 号原动力」/「因子 <词根>」/两者。

    与 `Renderer.seat` 同一口径（同一个 `sim_slot_naming` 开关），只是这里不依赖 traj：
    看板的席卡要一张能随回放【就地切换】的备用名，故先整份算好塞进 blob。
    """
    R = Renderer(ctx)
    mode = str(ctx.lexicon.get("sim_slot_naming") or "ordinal")
    stems = (ctx.phonology or {}).get("machine_stems") or ["?"]
    out = []
    for locus in ctx.loci:
        order = int(locus.order)
        parts = []
        if mode in ("ordinal", "both"):
            parts.append(R.tpl("seat_ordinal").format(n=order))
        if mode in ("stem", "both"):
            s = str(stems[order % len(stems)])
            parts.append(R.tpl("seat_stem").format(stem=s[:1].upper() + s[1:]))
        out.append(" · ".join(parts) or str(order))
    return out


def _stages_html(rows):
    """「阶段目录」块：每一档的帧区间 / 预算 / 新装的机制 / 期间读数 / 该档的结论。

    没有 stages（未配装配位、或还没跨过第一档）时整块不渲染。
    """
    if not rows:
        return ""
    circles = "①②③④⑤⑥⑦⑧⑨"
    out = ['<h2>初始变量域 · 四个阶段</h2>', '<div class="stages">']
    for row in rows:
        i = int(row["index"])
        mark = circles[i] if i < len(circles) else f"({i + 1})"
        asm = "、".join(row["gates"]) or "—"
        if row["params"]:
            asm += "　覆盖 " + "、".join(f"{k}={v}" for k, v in sorted(row["params"].items()))
        if row["promotion_note"]:
            asm += f'　（{row["promotion_note"]}）'
        budget = "—" if row["budget"] is None else f'{int(row["budget"]):,}'
        out.append(
            f'<div class="stage" data-start="{int(row["start"])}" '
            f'title="点击跳到这一档开始的帧">'
            f'<div class="stage-head">'
            f'<span class="stage-mark">{mark}</span>'
            f'<span class="stage-name">{html.escape(str(row["name"]))}</span></div>'
            f'<div class="stage-span">帧 {int(row["start"]):,} – {int(row["end"]):,}'
            f'　·　预算 {budget}</div>'
            f'<div class="stage-asm">新装 {html.escape(asm)}</div>'
            f'<div class="stage-num">涌现 {int(row["born"]):,} '
            f'{html.escape(str(row.get("born_unit") or "位"))} · '
            f'{html.escape(str(row["promotion_label"]))} {int(row["promotions"]):,} 次 · '
            f'{html.escape(str(row.get("fell_word") or "陨落"))} '
            f'{int(row["fell"]):,} {html.escape(str(row.get("fell_unit") or "人"))}</div>'
            + (f'<div class="stage-conc">{html.escape(str(row["conclusion"]))}</div>'
               if row["conclusion"] else "")
            + (f'<div class="stage-myth">⇄ {html.escape(str(row["myth_note"]))}</div>'
               if row.get("myth_note") else "")
            + '</div>')
    out.append("</div>")
    return "\n".join(out)


def _rules_html(ctx, traj):
    """「世界规则 · 观测量」块：换代时把什么当成下一世的规则，以及它在 6 个观测量上的投影。

    这两个量（`rule_matrix` / `observables_vec`）**不参与演化**，只在这里与报告里露面 ——
    「主动更替」那道改造的效果就落在这块（来源从席位向量变成决策账本）。
    没有末态（实时空壳）时整块不渲染。
    """
    obs = getattr(getattr(traj, "final", None), "observables_vec", None)
    if obs is None or not len(obs):
        return ""
    switch = renewal_switch_frame(traj)
    src = ("席位向量（自动更替循环）" if switch is None
           else f"决策账本（主动更替 @{switch:,}）")
    ren = {k: v for k, v in (getattr(traj.final, "overrides", {}) or {}).items()
           if k.startswith("renewal.")}
    if "renewal.factor" in ren:
        gate = float((ctx.params or {}).get("renewal_consensus", 0.0))
        now = consensus(traj.final)
        src += (f" · 主导支 {int(ren['renewal.factor'])}"
                f" · 共识 {float(ren.get('renewal.share') or 0.0):.1%}"
                f" · 共识门 ≥ {gate:.3f}（末态 {now:.3f}）")
    names = list(getattr(ctx, "obs_names", []) or [])
    cells = "".join(
        f'<span class="obs"><b>{html.escape(str(names[i] if i < len(names) else i))}</b>'
        f'{float(v):.4f}</span>' for i, v in enumerate(obs))
    return (f'<h2>世界规则 · 观测量</h2>\n<div class="rules">'
            f'<div class="stage-span">换代时把什么当成下一世的规则：{html.escape(src)}'
            f'　（规则本身不参与演化 —— 改它不动轨迹；「共识门」是触发条件，它动轨迹）</div>'
            f'<div class="obsrow">{cells}</div></div>')


def _page(R, title, live, cards_html, seats_html, blob, stages_html="", rules_html=""):
    """把各部分拼成一张完整的页面（静态导出与实时看板共用）。"""
    js = _JS.replace("__ROWS__", "120")
    note = ('<div class="sub" id="sub">实时看板 —— 演算每前进一步，本页自动跟着更新'
            '<span id="liveflag" class="dim"></span></div>' if live else
            '<div class="sub" id="sub">单文件可视化 · 只读渲染层 —— 删掉它，演算逐帧不变 · '
            '曲线可缩放平移与悬停读数 · 控制台可暂停 / 播放 / 跳到任意时刻 · '
            '点席位卡按人过滤（点空白处即可取消）</div>')
    # 右下角「演算完成」提示：只在实时页摆，且只在 --no-serve-reload（关掉自动重载）时用得到
    # —— 默认那条路是直接重载。显隐与过渡见 _JS 的 showDoneToast / 绑定处的两颗按钮。
    toast = ('<div class="donetoast" id="done-toast">'
             '<button class="dt-x" id="done-x" title="关闭">×</button>'
             '<div class="dt-h">演算完成</div>'
             '<div class="dt-b">世界已跑到结论 —— 是否查看最终结果页？'
             '（会替换成与导出一致的完整页面）</div>'
             '<button id="done-view" type="button">立即查看</button></div>') if live else ''
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>{html.escape(title)}</h1>
{note}
<div class="cards" id="cards">{cards_html}</div>
<div class="panel"><div class="ctrls">
  <button id="rewind" title="回到演算开始">⏮ 回到开始</button>
  <button id="prev" title="后退一帧">◀ 前一帧</button>
  <button id="play">▶ 播放</button>
  <button id="next" title="前进一帧">后一帧 ▶</button>
  <button id="toend" title="跳到演算末尾">跳到末尾 ⏭</button>
  <label>速度 <select id="speed">
    <option value="1">×1</option><option value="4">×4</option>
    <option value="16">×16</option><option value="64">×64</option></select></label>
  <input id="scrub" type="range" min="0" max="1000" value="0"
         title="拖动查看任意时刻（按对数时间轴）">
  <span id="cursor" class="dim"></span>
</div></div>
<h2>十二席状态（A2）</h2>
{seats_html}
{stages_html}
{rules_html}
<h2>指标曲线（A3）</h2>
<div class="panel"><div class="ctrls">
  <button id="z-out" title="缩小">－</button>
  <button id="z-in" title="放大">＋</button>
  <button id="z-reset">重置</button>
  <span class="hint">滚轮缩放 · 按住拖动平移 · 悬停读该帧数值 · 缩放后纵轴按可见区间自适应</span>
  <span id="win" class="dim"></span>
</div></div>
<div class="chart-box"><div class="tip"></div>
  <div class="chart-title">指标曲线 · 熵 / {R.term('overflow')}（对数帧轴，竖虚线 = {R.term('promotion')}）</div>
  <div id="cv1"></div><div class="legend" id="lg1"></div></div>
<div class="chart-box"><div class="tip"></div>
  <div class="chart-title">指标曲线 · 种群 / 在位席位（对数帧轴）</div>
  <div id="cv2"></div><div class="legend" id="lg2"></div></div>
<h2>事件时间线（A4）</h2>
<div class="chart-box" id="tl-box-wrap">
  <div class="tlbar"><label class="dim"><input type="checkbox" id="showmarks"> 常显全部节点文字</label>
    <span class="hint">默认不显示 —— 鼠标靠近某个节点才展开它的引线与文字</span></div>
  <div class="near" id="near"></div>
  <div id="tl-box"></div></div>
<label class="dim"><input type="checkbox" id="listmode"> 改为逐条列出全部事件（不打点）</label>
<ol id="evlist" class="chron" hidden></ol>
<h2>编年史（连续同型事件已折叠）</h2>
<div class="chron-box">
  <div class="toolbar">
    <input id="q" type="search" placeholder="按关键词过滤（人名 / 职位 / 事件）">
    <label>跳到帧 <input id="jf" type="number" min="0" placeholder="如 33594383"></label>
    <button id="jump" type="button">定位</button>
    <button id="clear" type="button">清除</button>
    <span id="count" class="dim"></span>
  </div>
  <ol id="chron" class="chron"></ol>
  <noscript><p class="dim">这一页需要 JavaScript。纯文本编年史请用
  <code>--log &lt;路径&gt;</code> 落盘。</p></noscript>
</div>
{toast}
<div class="seattip" id="seattip"></div>
<script type="application/json" id="viz-data">{blob}</script>
<script>{js}</script>
</body></html>"""


def _cards_html(cards):
    return "".join(
        f'<div class="card"><div class="k">{html.escape(k)}</div>'
        f'<div class="v{" mono" if mono else ""}">{html.escape(str(v))}</div></div>'
        for k, v, mono in cards)


def summary_cards(ctx, traj, genesis=None):
    """顶部摘要卡（命题 / 结论 / 结论编号 / 裁决 / 走到帧 / 实际迭代 / 最终状态）。

    静态导出与实时看板【共用同一份口径】—— 实时看板演完时替换的正是这几张卡。
    「命题」取自 genesis（提出的问题），「结论」取自这次演算裁出来的文案（给出的回答）——
    两者是【一问一答】，不是同一句话。
    """
    R = Renderer(ctx, getattr(traj, "spans", ()), cycle_frames(traj),
                 myth_phase_frame(traj))
    st = traj.final
    prop = ((genesis or {}).get("proposition") or {})
    note, pid = str(prop.get("note", "")), str(prop.get("id", ""))
    return [
        ("命题", f"{note}   [{pid}]" if pid else note, False),
        ("结论", traj.conclusion.get("template", ""), False),
        ("结论编号", traj.conclusion.get("id", ""), True),
        ("裁决", f'{R.verdict_label(traj.verdict)}（{traj.stop_reason}）', False),
        ("走到帧", f"{traj.reached_frame:,} · {R.locale(traj.reached_frame)}", False),
        ("实际迭代", f"{traj.iterations:,}（复用 {traj.skipped_frames:,} 帧）", False),
        ("最终状态", f"熵 {st.entropy:.4f} · {R.term('overflow')} {st.noise:.4f} · "
                     f"{R.term('promotion')} {st.promotions} 次", False),
    ]


def build_html(ctx, traj, points, lines=None, title=None, data=None, texture=None):
    """把一次演算装配成单文件 HTML（静态导出）。

    points 来自 Sampler（可为 None）；lines 是编年史行 [(frame, text, badge, rid), ...]
    （`rid` = 事件号，与时间线打点末尾那个同源 —— 供双击节点精确回跳）。
    data 用来摆「阶段目录」（`stage_table` 需要 `genesis.domain.stages`）——
    不给就整块略过（老调用方与实时看板都不受影响）。
    """
    R = Renderer(ctx, getattr(traj, "spans", ()), cycle_frames(traj),
                 myth_phase_frame(traj))
    names = _name_map(traj)
    machines = _machine_map(traj)
    tau = float(ctx.params["tau_falsify"])
    total = max(1, int(traj.reached_frame))

    stages = stage_table(ctx, data, traj) if data is not None else []
    cards = summary_cards(ctx, traj, data.genesis if data is not None else None)
    pts = (_downsample(ensure_final(points, traj), keep=set(stage_starts(traj)))
           if points else [])
    table, mach, seats_per_sample, _ = _seat_table(traj, names, machines, pts,
                                                   _final_point(traj))
    marks = _timeline_marks(traj, R)
    promos = [(f, p.get("round", 0)) for f, k, p in traj.records if k == "PROMOTION"]
    spans = [(s, e) for _k, s, e in traj.spans]
    rows = list(lines or [])[:_CHRON_LIMIT]
    blob = _data_blob(R, pts, rows, total, marks, table, seats_per_sample,
                      promos, spans, machines=mach, stages=stages,
                      mythfrom=myth_phase_frame(traj), texture=texture)
    return _page(R, title or "δ-me13 演算可视化", False, _cards_html(cards),
                 _seats_html(_seat_cards(ctx, traj, names, machines), tau,
                             show_places=myth_phase_frame(traj) is not None),
                 blob, _stages_html(stages), _rules_html(ctx, traj))


def build_live_shell(ctx, total, title=None, autoreload=True):
    """实时看板的【初始页】：数据全空，一切由页面自己向 `state` 取。

    run.py --serve 先把它交给浏览器，再开始演算 —— 于是打开就看到世界在长。
    `autoreload=False`（`--no-serve-reload`）时，跑完不自动重载，改由右下角弹窗提示。

    两处「先备好、后显形」的块（都随 `mythfrom` / 实时快照就地切换）：
      · **城邦图例**：城池只属于第四阶段，故先整份渲染好、`display:none`，页面据
        `simPhase()` 显隐（与静态导出同一份 `_city_legend_html`）。
      · **阶段目录**：先摆一个空容器 `#stages-block`，实时快照带 `stageshtml` 时填入。
    """
    R = Renderer(ctx)
    blob = _data_blob(R, [], [], max(2, int(total)), [], [], [], [], [], live=True,
                      autoreload=autoreload)
    _per, _city_names, city_idx = _city_meta(ctx)
    cities_map = ctx.lexicon.get("cities") or {}
    legend_cards = [{"city_idx": city_idx[i], "city": cities_map.get(locus.id, "")}
                    for i, locus in enumerate(ctx.loci)]
    seats_html = (_city_legend_html(legend_cards, hidden=True)
                  + '<div class="seats" id="seats"></div>')
    return _page(R, title or "δ-me13 演算 · 实时看板", True,
                 _cards_html([("状态", "演算已开始，数据正在流入…", False)]),
                 seats_html, blob, stages_html='<div id="stages-block"></div>')

