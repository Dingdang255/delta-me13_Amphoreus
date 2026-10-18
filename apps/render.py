"""L5：表象层。

引擎内部全是 locus / slot / agent / vacancy / overflow；世界内的人不会这么说话。
渲染器只做一次查表替换，不参与运算——换一套 lexicon.json，同一段演算
就被讲成另一个世界的神话。
"""
from __future__ import annotations

from bisect import bisect_right


class Renderer:
    def __init__(self, ctx, spans=(), cycles=(), myth_from=None):
        """`spans` 是【沿参考轨道复用】的区间（`traj.spans` 的形状 `(kind, start, end)`）——
        历法要用它把"重放的时间"扣掉，见 `_cal_frame`。不传即视为没有复用。

        `myth_from` 是【世界内（第四阶段）从哪一帧起】（见 `myth_phase_frame`）；`None` 表示
        「还没走到世界内」⇒ 整段都按演算期的语汇讲。`cycles` 是历代换代的帧（升序）——
        演算期没有世界内历法，时间按【第 N 次循环】计量（见 `locale`）。

        这三样都是**构造时拷一份**（演算结束后已定型）。实时路径拿不到定型的结果，
        靠 `add_reuse` / `add_cycle` / `add_myth_from` 边跑边登记，口径相同。
        """
        self.ctx = ctx
        self.lex = ctx.lexicon
        self._reuse = [(int(s), int(e)) for _k, s, e in (spans or ())]
        self._cycles = sorted(int(f) for f in (cycles or ()))
        self._myth_from = None if myth_from is None else int(myth_from)

    def add_reuse(self, start, end=None):
        """登记一段【沿参考轨道复用】的时间；`end=None` 表示"还在复用中"。

        实时路径用：`DEADLOCK_LOOP` 打开时先记 start，`DEADLOCK_END` 再补 end。
        补 end 时**换掉**同一 start 的那条开区间（不是再添一条）—— 否则同一段
        时间会被算两遍。不这么做，循环期那些到访帧（几何刻度）会被历法讲成
        "过了几万年"。
        """
        start = int(start)
        self._reuse = [r for r in self._reuse if not (r[0] == start and r[1] is None)]
        self._reuse.append((start, None if end is None else int(end)))

    # ---- 阶段语汇：前三个阶段（因子演算）与第四阶段（人类古典文明）是两套词 ----
    def add_cycle(self, frame):
        """实时路径：登记一次换代（演算期的「第 N 次循环」要用它数）。"""
        f = int(frame)
        if f not in self._cycles:
            self._cycles = sorted(self._cycles + [f])

    def add_myth_from(self, frame):
        """实时路径：登记「世界内」的起点（`DOMAINS_EXHAUSTED` 那一帧）。"""
        if self._myth_from is None:
            self._myth_from = int(frame)

    def phase_of(self, frame) -> str:
        """这一帧属于哪套语汇：`sim`（前三个阶段 = 因子演算）/ `myth`（第四阶段 = 世界内）。

        据 wiki：十二因子以无机 / 有机 / 人类为初始变量跑了三个阶段，此时它们是
        【电信号 / 生命原动力的简化模型】；到第四阶段才把背景设为【人类古典文明】，
        那批因子从此才有了世界内的身份与职称（moegirl 第 47 行）—— 职位名 / 圣所 /
        城邦 / 历法这一套世界内的词，都只属于第四阶段。**还没走到第四阶段（含没配
        阶段的世界）⇒ 一律 sim** —— 宁可讲成演算，也不把世界内的词提前贴上去。
        """
        if self._myth_from is None:
            return "sim"
        return "myth" if int(frame) >= self._myth_from else "sim"

    def text(self, section: str, key: str, frame=None) -> str:
        """查一层词表，带【阶段覆盖】：`phase_terms.<阶段>.<section>.<key>` 优先。

        `frame=None` 表示这次查表与帧无关（一律按顶层 = 第四阶段那套）。
        """
        base = (self.lex.get(section) or {}).get(key)
        if frame is not None:
            over = ((self.lex.get("phase_terms") or {})
                    .get(self.phase_of(frame), {}) or {})
            hit = (over.get(section) or {}).get(key)
            if hit is not None:
                return str(hit)
        return str(base) if base is not None else str(key)

    def term(self, key: str, frame=None) -> str:
        return self.text("terms", key, frame)

    def tpl(self, key: str, frame=None) -> str:
        """编年史那句模板（`lexicon.chronicle`），同样带阶段覆盖。"""
        return self.text("chronicle", key, frame)

    def seat(self, namer, frame, locus_id) -> str:
        """某一位在【该帧所属阶段】里的叫法。

        第四阶段（及没配 stages 的世界）：世界内的职位名（负世 / 岁月…）。
        前三个阶段：它还没有职位 —— 按 `lexicon.sim_slot_naming` 给「第 N 号原动力」、
        「因子 <词根>」或两者（词根取 `phonology.machine_stems`，按位次取模 —— 不新增专名）。
        """
        if self.phase_of(frame) != "sim":
            return namer.title_by_id(locus_id)[1]
        order = next((int(l.order) for l in self.ctx.loci if l.id == locus_id), 0)
        mode = str(self.lex.get("sim_slot_naming") or "ordinal")
        out = []
        if mode in ("ordinal", "both"):
            out.append(self.tpl("seat_ordinal", frame).format(n=order))
        if mode in ("stem", "both"):
            stems = (self.ctx.phonology or {}).get("machine_stems") or ["?"]
            s = str(stems[order % len(stems)])
            out.append(self.tpl("seat_stem", frame).format(stem=s[:1].upper() + s[1:]))
        return " · ".join(out) or str(order)

    def region(self, locus_id: str) -> str:
        """该位的称号 / 圣所（与位一一对应，12 项）。"""
        return self.lex["regions"].get(locus_id, locus_id)

    def city(self, locus_id: str) -> str:
        """该位所属的城邦。**可空缺** —— 没有考据的席位返回空串，由调用方显示「—」。"""
        return (self.lex.get("cities") or {}).get(locus_id, "")

    def event(self, key: str) -> str:
        return self.lex["events"].get(key, key)

    def capability(self, key: str) -> str:
        return self.lex.get("capabilities", {}).get(key, key)

    def domain(self, key: str) -> str:
        return self.lex["domains"].get(key, key)

    def stage_conclusion(self, index: int) -> str:
        """第 index 档的「结论」（wiki 口径）。缺项退回空串 —— 渲染层据此不写这一行。"""
        table = self.lex.get("stage_conclusions") or []
        if isinstance(table, dict):
            return str(table.get(str(index), ""))
        return str(table[index]) if 0 <= int(index) < len(table) else ""

    # ---- 裁决与停因的显示名：一律来自配置，不写死在报告里 ----------------
    def verdict_label(self, key: str) -> str:
        """裁决枚举 → 短名（报告与编年史里那个括注）。

        取自 conclusions.json 的 label；没写就退回枚举本身。于是新增一个结论
        维度只需在配置里补 label，报告层不必改一个字符。
        """
        entry = (self.ctx.conclusions or {}).get(str(key)) or {}
        return entry.get("label") or str(key)

    def stop_label(self, reason: str) -> str:
        """停止原因 → 一句人话。先查结论表的 stop，再查词表的 stop_reasons。"""
        for entry in (self.ctx.conclusions or {}).values():
            if not isinstance(entry, dict):        # 表里的 `_comment` 之类
                continue
            if entry.get("stop") and str(entry["stop"]) == str(reason):
                return entry.get("stop_label") or str(reason)
        return (self.lex.get("stop_reasons") or {}).get(str(reason), str(reason))

    # ---- 历法：帧 → (纪元, 年, 月)。一律以【帧】为刻度，world_clock 只是轮回计数 ----
    def _cal_frame(self, frame: int) -> int:
        """历法时间 = 帧号 −【被复用的帧】。

        永劫回归期沿参考轨道复用：那 3300 多万帧是**同一段时间在轮回**（wiki：永劫回归
        即时间不断轮回），历法不该跟着往前走 —— 否则末日那一刻会被讲成"过了九万年"。
        故落在复用区间里的帧，历法一律停在【进入复用之前的那一帧】。
        """
        f = int(frame)
        skipped = 0
        for s, e in self._reuse:
            if s > f:                       # 这段复用还没开始
                continue
            hi = f if e is None else min(int(e), f)
            skipped += hi - s + 1
        return max(0, f - skipped)

    def _eras(self):
        return self.ctx.calendar.get("eras") or []

    def _cal_base(self):
        """光历的起算帧与元年：第一个 `calendar: true` 的纪元的起始帧及其 `origin`。

        纪元按帧划分，于是"历法从哪一帧起才有"可以先于年份存在；`origin` 取 1 ⇒
        **年份恒为正整数**（此前那套 `origin_offset` 会让前期整段变成负年）。
        """
        start = 0
        for e in self._eras():
            if e.get("calendar"):
                return start, int(e.get("origin", 1))
            if e.get("until_frame") is None:
                break
            start = int(e["until_frame"]) + 1
        return None, 0

    def _cal(self, frame: int):
        """帧 → (年序 | None, 月序 1..mpy | None, 纪元 dict)。纯渲染，不参与演算。

        一年 = months_per_year 月 × days_per_month 日，1 帧 = 1 日。
        `None` 表示"这个纪元还没有历法"（历法是【黄金世】才测定的，此前无年号）。
        """
        cal = self.ctx.calendar
        f = self._cal_frame(frame)
        eras = self._eras()
        era = eras[-1] if eras else {}
        for e in eras:
            if e.get("until_frame") is None or f <= int(e["until_frame"]):
                era = e
                break
        if not era.get("calendar"):
            return None, None, era
        base, origin = self._cal_base()
        if base is None:
            return None, None, era
        dpm = max(1, int(cal.get("days_per_month", 1)))
        mpy = max(1, int(cal.get("months_per_year", 1)))
        d = max(0, f - base)
        return origin + d // (dpm * mpy), (d // dpm) % mpy + 1, era

    def month(self, frame: int) -> str:
        cal = self.ctx.calendar
        keys = cal.get("month_keys") or []
        _y, m, _era = self._cal(frame)
        if not keys or m is None:
            return ""
        key = keys[(m - 1) % len(keys)]
        return self.lex.get("months", {}).get(key, key)

    def year(self, clock: int) -> str:
        cal = self.ctx.calendar
        y, _m, _era = self._cal(clock)
        return "" if y is None else f"{cal['unit']}{y}年"

    def epoch(self, clock: int) -> str:
        _y, _m, era = self._cal(clock)
        key = era.get("lexicon_key")
        return self.lex["epochs"].get(key, key) if key else ""

    def locale(self, clock: int) -> str:
        """这一帧的「时间」。

        第四阶段起（人类古典文明）用世界内的历法：纪元 · 月 · 年。
        前三个阶段是因子演算，**还没有历法** —— 按 wiki 的口径报【第 N 次循环】
        （biligame「进行的第 1 至 50121 次循环」）。故这里按阶段分岔。
        """
        if self.phase_of(clock) == "sim":
            n = bisect_right(self._cycles, int(clock) - 1) + 1
            return self.tpl("cycle_label", clock).format(n=n)
        return "·".join(p for p in (self.epoch(clock), self.month(clock),
                                    self.year(clock)) if p)


# ---- 阶段目录：把「四个阶段」显式摆出来 --------------------------------------
def _stage_at(starts, frame: int) -> int:
    """frame 落在第几档（starts 是各档的起始帧，升序）。"""
    return max(0, bisect_right(starts, int(frame)) - 1)


def renewal_switch_frame(traj):
    """「自动更替循环」被改成「主动更替（再创世）」的那一帧；没改过则 None。

    不靠配置猜：取 Telemetry 里 `renewal.mode` 落进覆盖表的那一刻 —— 报告、看板、
    编年史共用这一个口径，于是三处对「第几帧起该叫再创世」永远一致。
    """
    for frame, kind, payload in traj.records:
        if kind != "PROTOCOL_REWRITTEN":
            continue
        if "renewal.mode" in (payload.get("changed") or {}):
            return int(frame)
    return None


def stage_starts(traj) -> list:
    """各【阶段】的起始帧（升序，第 0 项恒为 0）。

    取 `DOMAIN_ADVANCE` / `DOMAINS_EXHAUSTED` 两条事件的帧号（`OP_DOMAIN` 换档那一刻
    发出来的）—— 与阶段目录同源，于是续跑与参考轨道复用都不会改动它。
    """
    starts = [0]
    for frame, kind, _payload in traj.records:
        if kind in ("DOMAIN_ADVANCE", "DOMAINS_EXHAUSTED"):
            starts.append(int(frame))
    return sorted(set(starts))


def cycle_frames(traj) -> list:
    """历代换代的帧（升序）—— 演算期的「第 N 次循环」靠它数。"""
    return [int(f) for f, k, _p in traj.records if k == "PROMOTION"]


def myth_phase_frame(traj):
    """「世界内」（第四阶段 = 人类古典文明）从哪一帧起；还没走到则 None。

    取 `DOMAINS_EXHAUSTED`（变量域走完 = 人科人属那一档跑满）那一帧 —— 据 wiki，
    到第四阶段背景才改为【人类古典文明】（moegirl 第 47 行）。
    没走到 ⇒ 整段都按演算期讲。不靠配置算档界：那条事件就是引擎自己报的换档时刻，
    续跑与复用都不会改动它。
    """
    for frame, kind, _payload in traj.records:
        if kind == "DOMAINS_EXHAUSTED":
            return int(frame)
    return None


def renderer_for(ctx, traj):
    """按一次【已跑完】的演算装配 Renderer —— 把三个口径统一在一处。

    等价于 `Renderer(ctx, traj.spans, cycle_frames(traj), myth_phase_frame(traj))`。
    报告、看板与各只读诊断工具都要这一份；抽出来是为了避免每个调用点各写一遍、
    口径漂移（少传一个参数就会静默退化成"没有复用 / 还没到世界内"）。
    """
    return Renderer(ctx, traj.spans, cycle_frames(traj), myth_phase_frame(traj))


def advance_label(R, switch, frame) -> str:
    """这一次世代更迭该叫什么 —— 按帧查档，**三段式**（wiki 里这机制恰好跨两处改名）：

      · **第四阶段起**（世界内）：`renewal` = 「再创世」—— moegirl 第 47 行：第四阶段
        「**利用「再创世」**进行世代更迭」；
      · **第三阶段内**（协议改写那一刻起）：`active` = 「主动更替」—— moegirl 第 41 行：
        第三阶段「诱导电信号完成了**主动更替循环**的行为」；biligame 第 564 行：把该世界
        的**自动更替循环**改成**电信号主动更替**。此档**主体仍是因子 / 电信号**（十二因子
        到第四阶段才成为世界内的身份）—— 故机制名先走一步、主体名留在演算期，正是这一档
        该有的样子；
      · **更早**：`auto` = 「自动更替」—— 自动更替循环自始就有。

    `switch` = `renewal_switch_frame(traj)`（`renewal.mode` 进覆盖表的那一帧）；
    「世界内」由 `R.phase_of(frame)` 定（与席卡 / 历法 / 编年史同一把尺子：取
    `DOMAINS_EXHAUSTED` 那一帧）。报告 / 看板 / 编年史共用它，三处对「第几帧起叫什么」
    永远一致；没配 `stage_promotion_labels` 的世界退回机制名（`terms.promotion`）。
    """
    labels = R.lex.get("stage_promotion_labels") or {}
    if R.phase_of(frame) != "sim":
        key = "renewal"                       # 第四阶段：世界内给这个机制起了新名字
    elif switch is not None and int(frame) >= int(switch):
        key = "active"                        # 第三阶段：更替由「自动」改为「主动」
    else:
        key = "auto"
    return str(labels.get(key) or R.term("promotion"))


def stage_rows(ctx, data, *, starts, born, prom, fell, reached_frame,
               exhausted, switch=None, myth_from=None, spans=()) -> list:
    """按【显式给出的】阶段边界与读数装配阶段目录 —— `stage_table` 与实时看板共用。

    静态路径从 `traj.records` 现算一遍（见 `stage_table`）；实时路径边跑边累计
    （见 `live.LiveState`）。两条路都归到这里，模板 / 量词 / 注脚才不会各写一套。
    """
    profiles = list(getattr(data, "stage_profiles", None) or [])
    if len(profiles) < 2 or not starts:
        return []
    R = Renderer(ctx, spans, (), myth_from)
    variables = list((data.genesis.get("domain") or {}).get("initial_variable") or [])
    ends = [s - 1 for s in starts[1:]] + [int(reached_frame)]

    rows = []
    last = len(starts) - 1
    note_text = str(R.lex.get("stage_promotion_note") or "")
    myth_note_text = str(R.lex.get("stage_myth_note") or "")
    # 切词说明里那句「更替之名也从 A 改为 B」：A / B 取【本世界自己的】三档名，
    # 且只在两档**确实不同名**时才拼 —— 一路同名的世界（如 tide 都叫「换代」）不拼，免得混词。
    labels = R.lex.get("stage_promotion_labels") or {}
    was, now = labels.get("active"), labels.get("renewal")
    rename_tpl = str(R.lex.get("stage_myth_rename_note") or "")
    if myth_note_text and was and now and was != now and rename_tpl:
        myth_note_text += "；" + rename_tpl.format(was=was, now=now)
    for i, start in enumerate(starts):
        prof = profiles[i] if i < len(profiles) else {}
        params = dict(prof.get("params") or {})
        budget = int(params.pop("domain_dwell", ctx.params["domain_dwell"]))
        # 末档若已「域穷尽」，就没有"下一档"可言 —— 预算不适用，记 None 由渲染层写「—」。
        if i == last and exhausted:
            budget = None
        # 本档该叫哪一档（自动更替 / 主动更替 / 再创世）：按本档【末帧】所在阶段算；
        # 「自动 → 主动」的界落在本档之内时，另附一句注脚把这件事点出来（此后各档不再重复）。
        active = switch is not None and int(ends[i]) >= int(switch)
        promo_note = ""
        if active and i > 0 and int(ends[i - 1]) < int(switch):
            promo_note = note_text
        rows.append({
            "index": i,
            # 前三档用变量域里那一档的名字；域穷尽之后（阶段四）用词表里的名字
            "name": (R.domain(variables[i]) if i < len(variables)
                     else R.term("domain_exhausted")),
            "start": int(start), "end": int(ends[i]), "budget": budget,
            "gates": [R.event(g) for g in (prof.get("on") or [])],
            "params": params,
            "conclusion": R.stage_conclusion(i),
            "promotion_label": advance_label(R, switch, ends[i]),
            "promotion_note": promo_note,
            # 本档若正是【世界内】起点，补一句「称谓为何而换」（演算期 ⇄ 世界内）。
            "myth_note": (myth_note_text
                          if (myth_from is not None and int(start) == int(myth_from))
                          else ""),
            # 读数的量词也随阶段（「涌现 202 位 / 陨落 502 人」 vs 「…个」）
            "born_unit": R.tpl("born_unit", ends[i]),
            "fell_word": R.tpl("fell_word", ends[i]),
            "fell_unit": R.tpl("fell_unit", ends[i]),
            "born": int(born[i]), "promotions": int(prom[i]), "fell": int(fell[i]),
        })
    return rows


def stage_table(ctx, data, traj) -> list:
    """四个阶段的目录：帧区间 · 本档新装的机制 / 参数覆盖 · 期间读数 · 该档的「结论」。

    纯渲染：只读 `traj.records` 与 `data.stage_profiles`，不碰任何状态 ——
    删掉它，演算逐帧不变。

    阶段边界取 `DOMAIN_ADVANCE` / `DOMAINS_EXHAUSTED` 两条事件的帧号（`OP_DOMAIN`
    换档那一刻发出来的），于是续跑与参考轨道复用都不会改动这份目录。

    没配 `stages`（装配位 < 2）时返回空表 —— 渲染层据此整块略过，
    「无阶段」的世界不摆这张表。
    """
    profiles = list(getattr(data, "stage_profiles", None) or [])
    if len(profiles) < 2:
        return []
    starts = stage_starts(traj)
    born = [0] * len(starts)
    prom = [0] * len(starts)
    fell = [0] * len(starts)
    seen_fell = 0
    for frame, kind, payload in traj.records:
        i = _stage_at(starts, frame)
        if kind == "EMERGENCE":
            born[i] += 1
        elif kind == "PROMOTION":
            prom[i] += 1
            cur = int((payload.get("burden") or {}).get("fell", seen_fell))
            fell[i] += max(0, cur - seen_fell)      # 背负里的陨落是累加值 ⇒ 取差
            seen_fell = max(seen_fell, cur)
    return stage_rows(ctx, data, starts=starts, born=born, prom=prom, fell=fell,
                      reached_frame=int(traj.reached_frame),
                      exhausted=bool(getattr(traj.final, "domains_exhausted", False)),
                      switch=renewal_switch_frame(traj),
                      myth_from=myth_phase_frame(traj),
                      spans=getattr(traj, "spans", ()))
