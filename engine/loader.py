"""L5：装载 config/ 与 data/。

配置只描述【规则与阈值】，数据只描述【命题、扰动、断言】——
没有一个文件里躺着某个角色的名字。
"""
from __future__ import annotations

import json
import os

import numpy as np

from .state import Locus, SOLVER_NAMES, State

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ---- 启动校验：字段缺失 / 越界 / 跨文件不自洽，一次报清 ---------------------
# 只查【会真的坏事】的东西：引擎读不到的键、长度对不上的表、查不到的词、
# 认不出的算子与能力名。引擎本来就会当场 KeyError 的，这里提前聚合成一张单子，
# 免得跑了几百万帧才在最后一帧炸出来。
class ConfigError(ValueError):
    """配置 / 数据不自洽（消息里逐条列出问题）。"""


def _report(scope: str, problems: list):
    if problems:
        raise ConfigError(
            f"{scope} 校验未通过（{len(problems)} 处）：\n  - "
            + "\n  - ".join(problems)
        )


def _num(problems, scope, mapping, key, lo=None, hi=None):
    """取一个数值键并查范围。缺失或不是数就报一条。"""
    if key not in mapping:
        problems.append(f"{scope}.{key} 缺失")
        return None
    v = mapping[key]
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        problems.append(f"{scope}.{key} 应为数字，实为 {type(v).__name__}")
        return None
    if lo is not None and v < lo:
        problems.append(f"{scope}.{key} = {v} 越界（应 ≥ {lo}）")
    if hi is not None and v > hi:
        problems.append(f"{scope}.{key} = {v} 越界（应 ≤ {hi}）")
    return v


def _check_params(p, problems):
    for key in ("dim", "observables", "pool_capacity", "frames",
                "tau_falsify", "capability_names", "verbosity"):
        if key not in p:
            problems.append(f"params.{key} 缺失")
    _num(problems, "params", p, "dim", lo=1)
    _num(problems, "params", p, "observables", lo=1)
    _num(problems, "params", p, "pool_capacity", lo=1)
    _num(problems, "params", p, "frames", lo=1)
    _num(problems, "params", p, "tau_falsify", lo=0.0)
    for key in ("mutation", "promotion_gain", "capacity_inherit",
                "min_population", "life_span", "attempt_period",
                "ablation_period", "freeze_dwell"):
        if key in p:
            _num(problems, "params", p, key, lo=0.0)
    # 主动更替的共识门槛：共识落在 0～1，>1 会让换代永远等不到共识（世界再无更替）。
    if "renewal_consensus" in p:
        _num(problems, "params", p, "renewal_consensus", lo=0.0, hi=1.0)
    verb = p.get("verbosity")
    if verb is not None:
        if not isinstance(verb, dict):
            problems.append("params.verbosity 应为对象（{{类别: 档位}}）")
        else:
            for k, v in verb.items():
                if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 3:
                    problems.append(
                        f"params.verbosity.{k} = {v!r} 越界（只接受 0～3 的整数）")


def _check_capability_names(p, problems, lex=None):
    """capability_names 的长度与逐项取值。

    长度须等于 dim。逐项是【能力标签】—— 它挂在个体身上，供报告与断言读，
    并不要求有可投递的实现（`bind_locus` 就是只有词条、没有扰动实现的一个）。
    故取值只要求「名字认得出来」：要么是已注册的能力，要么在渲染词表里声明过。
    """
    names = p.get("capability_names")
    if names is None:
        return
    dim = p.get("dim")
    if not isinstance(names, list):
        problems.append("params.capability_names 应为数组（按位次给出能力名或 null）")
        return
    if isinstance(dim, int) and len(names) != dim:
        problems.append(
            f"params.capability_names 长度 {len(names)} ≠ dim {dim}")
    from .disturbance import CAPABILITIES
    declared = set((lex or {}).get("capabilities") or {})
    for i, nm in enumerate(names):
        if nm is not None and nm not in CAPABILITIES and nm not in declared:
            problems.append(
                f"params.capability_names[{i}] = {nm!r} 既不是已注册的能力，"
                f"也不在 lexicon.capabilities 里")


def _check_loci(loci_raw, dim, problems):
    if not isinstance(loci_raw, list) or not loci_raw:
        problems.append("loci.loci 应为非空数组")
        return []
    ids, orders = [], []
    for i, l in enumerate(loci_raw):
        for key in ("id", "order", "capacity", "decay", "couplings"):
            if key not in l:
                problems.append(f"loci.loci[{i}].{key} 缺失")
        ids.append(l.get("id"))
        if "order" in l:
            orders.append(l["order"])
        if "capacity" in l:
            _num(problems, f"loci.loci[{i}]", l, "capacity", lo=0.0)
        if "decay" in l:
            _num(problems, f"loci.loci[{i}]", l, "decay", lo=0.0)
        if "couplings" in l and not isinstance(l["couplings"], list):
            problems.append(f"loci.loci[{i}].couplings 应为数组")
    if len(set(ids)) != len(ids):
        problems.append("loci.loci 的 id 有重复")
    if orders and sorted(orders) != list(range(len(loci_raw))):
        problems.append(
            f"loci.loci 的 order 应为 0..{len(loci_raw) - 1} 的一个排列，实为 {orders}")
    if isinstance(dim, int) and len(loci_raw) != dim:
        problems.append(f"位表长度 {len(loci_raw)} 必须等于 params.dim {dim}")
    for i, l in enumerate(loci_raw):
        c = l.get("couplings")
        if isinstance(c, list) and isinstance(dim, int) and len(c) != dim:
            problems.append(
                f"loci.loci[{i}].couplings 长度 {len(c)} ≠ dim {dim}")
    return ids


def _check_mapping(mp, dim, observables, problems):
    mat = mp.get("matrix")
    obs = mp.get("observables")
    if not isinstance(obs, list) or not obs:
        problems.append("mapping.observables 应为非空数组")
    if not isinstance(mat, list) or not mat:
        problems.append("mapping.matrix 应为非空二维数组")
        return
    if isinstance(dim, int) and len(mat) != dim:
        problems.append(f"mapping.matrix 行数 {len(mat)} ≠ params.dim {dim}")
    if isinstance(obs, list):
        for i, row in enumerate(mat):
            if not isinstance(row, list) or len(row) != len(obs):
                problems.append(
                    f"mapping.matrix 第 {i} 行长度应为 {len(obs)}（= observables 个数）")
    if isinstance(observables, int) and isinstance(obs, list) and len(obs) != observables:
        problems.append(
            f"mapping.observables 个数 {len(obs)} ≠ params.observables {observables}")


def _check_operators(ops, problems):
    from .operators import OPERATORS
    pipe = ops.get("pipeline")
    if not isinstance(pipe, list) or not pipe:
        problems.append("operators.pipeline 应为非空数组")
        return
    for nm in pipe:
        if nm not in OPERATORS:
            problems.append(f"operators.pipeline 里的 {nm!r} 不是已注册的算子")
    for nm in (ops.get("gated") or []):
        if nm not in pipe:
            problems.append(f"operators.gated 里的 {nm!r} 不在 pipeline 里")


def _check_conclusions(concl, problems, rules=None):
    """三个基础结论必须齐 —— 判据任何时候都可能落到它们身上。

    （其余枚举由配置自行决定：替代世界的 conclusions.json 就只有这三条。）
    若给了判据表，还要逐条核对：表里每条结论都得在 conclusions.json 里查得到文案，
    否则那条判据一旦成立，`cfg.conclusions[id]` 会当场 KeyError。
    """
    for key in ("proved", "refuted", "undecided"):
        entry = concl.get(key)
        if not isinstance(entry, dict):
            problems.append(f"conclusions.{key} 缺失（判据可能落到它身上）")
            continue
        for f in ("id", "template"):
            if not entry.get(f):
                problems.append(f"conclusions.{key}.{f} 缺失或为空")
    for i, rule in enumerate(rules or []):
        rid = rule.get("id")
        if not rid:
            problems.append(f"params.verdict_rules[{i}].id 缺失")
            continue
        entry = concl.get(str(rid))
        if not isinstance(entry, dict):
            problems.append(
                f"params.verdict_rules[{i}].id = {rid!r} 在 conclusions.json 里没有文案")
            continue
        # 报告层不再维护写死的裁决短名 —— 故判据表用到的每一条都得自带 label。
        if not entry.get("label"):
            problems.append(
                f"conclusions.{rid}.label 缺失（报告要用它当裁决短名）")


def _check_verdict_rules(p, problems):
    """判据表：情形与附加条件都必须在注册表里，且取值要认得出来。

    过去这些字段是【平铺】的，判定逻辑写死在求值函数里，名字写错就静默失效
    （`getattr(st, counter, 0)` 取 0、`solver` 比对恒为假）。现在它们进 `require`
    列表，逐项照注册表校验，写错即启动报错。
    """
    from .verdicts import known_require, known_when
    rules = p.get("verdict_rules")
    if not isinstance(rules, list) or not rules:
        problems.append("params.verdict_rules 应为非空数组（内层判据表）")
        return
    whens, keys = known_when(), known_require()
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            problems.append(f"params.verdict_rules[{i}] 应为对象")
            continue
        when = rule.get("when")
        if when not in whens:
            problems.append(
                f"params.verdict_rules[{i}].when = {when!r} 不是引擎认得的判据情形"
                f"（可选：{'、'.join(whens)}）")
        for j, spec in enumerate(rule.get("require") or []):
            where = f"params.verdict_rules[{i}].require[{j}]"
            if not isinstance(spec, dict):
                problems.append(f"{where} 应为对象")
                continue
            hits = [k for k in spec if k in keys]
            if len(hits) != 1:
                problems.append(
                    f"{where} 应恰好含一个已知条件键（可选：{'、'.join(keys)}），"
                    f"实为 {sorted(spec)}")
                continue
            if hits[0] == "solver":
                v = spec.get("solver")
                if v not in SOLVER_NAMES:
                    problems.append(
                        f"{where}.solver = {v!r} 不是已登记的演算方向"
                        f"（可选：{'、'.join(SOLVER_NAMES)}）")
            else:                                   # counter
                f = spec.get("counter")
                if f not in State.COUNTER_FIELDS:
                    problems.append(
                        f"{where}.counter = {f!r} 不是可比的账本计数"
                        f"（可选：{'、'.join(State.COUNTER_FIELDS)}）")
                if "min" not in spec:
                    problems.append(f"{where} 给了 counter 却没给 min")
                else:
                    _num(problems, where, spec, "min", lo=0.0)


def _check_calendar(cal, lex, problems):
    """历法配置：月份表 + 纪元表（按【帧】划分）。

    纪元表的两条硬约束：① 最后一项的 `until_frame` 必须是 null（兜底纪元，否则
    后面就没有纪元可查）；② `until_frame` 严格递增。另外 —— 第一个 `calendar: true`
    的纪元必须给出 ≥1 的 `origin`，否则「光历从黄金世起算、年份恒为正整数」这条口径
    就落不了地（过去那套 `origin_offset` 正是前期整段负年的病根）。
    """
    _num(problems, "calendar", cal, "days_per_month", lo=1)
    mpy = _num(problems, "calendar", cal, "months_per_year", lo=1)
    keys = cal.get("month_keys") or []
    if not isinstance(keys, list):
        problems.append("calendar.month_keys 应为数组")
        keys = []
    if isinstance(mpy, (int, float)) and keys and len(keys) != int(mpy):
        problems.append(
            f"calendar.month_keys 个数 {len(keys)} ≠ months_per_year {int(mpy)}")
    months = lex.get("months") or {}
    for k in keys:
        if k not in months:
            problems.append(f"calendar.month_keys 的 {k!r} 在 lexicon.months 里查不到")

    eras = cal.get("eras")
    if not isinstance(eras, list) or not eras:
        problems.append("calendar.eras 应为非空数组（纪元按帧划分）")
        return
    names = lex.get("epochs") or {}
    prev = -1
    seen_calendar = False
    for i, e in enumerate(eras):
        if not isinstance(e, dict):
            problems.append(f"calendar.eras[{i}] 应为对象")
            continue
        key = e.get("lexicon_key")
        if key is not None and key not in names:
            problems.append(f"calendar.eras[{i}] 的 {key!r} 在 lexicon.epochs 里查不到")
        # `lexicon_key` 允许**缺省**：那表示"这一段还没有纪元名"（演算期没有世界内历法，
        # 渲染层改显「第 N 次循环」—— 见 lexicon.phase_terms.sim.chronicle.cycle_label）。
        if "calendar" in e and not isinstance(e["calendar"], bool):
            problems.append(f"calendar.eras[{i}].calendar 应为布尔")
        until = e.get("until_frame", "__missing__")
        if until is None:
            if i != len(eras) - 1:
                problems.append(
                    f"calendar.eras[{i}].until_frame 为 null ⇒ 只能是最后一项（兜底纪元）")
        elif until == "__missing__" or not isinstance(until, (int, float)) \
                or isinstance(until, bool):
            problems.append(f"calendar.eras[{i}].until_frame 应为整数或 null")
        else:
            if int(until) <= prev:
                problems.append(
                    f"calendar.eras[{i}].until_frame = {int(until)} 未严格递增"
                    f"（上一项 {prev}）")
            prev = int(until)
        if e.get("calendar"):
            if not seen_calendar:
                ori = e.get("origin")
                if not isinstance(ori, (int, float)) or isinstance(ori, bool) \
                        or int(ori) < 1:
                    problems.append(
                        f"calendar.eras[{i}].origin 应为 ≥1 的整数"
                        f"（第一个有历法的纪元，年份须恒为正整数）")
            seen_calendar = True
    last = eras[-1]
    if isinstance(last, dict) and last.get("until_frame") is not None:
        problems.append("calendar.eras 最后一项的 until_frame 须为 null（兜底纪元）")
    if not seen_calendar:
        problems.append("calendar.eras 里没有 calendar=true 的纪元 ⇒ 永远渲染不出年号")


_CHRONICLE_KEYS = ("emergence", "seat_taken", "seat_none", "promotion",
                   "complete", "rise", "seat_ordinal", "seat_stem",
                   "cycle_label", "myth_onset", "converged", "born_unit",
                   "fell_word", "fell_unit")


def _check_lexicon(lex, problems):
    for table in ("terms", "domains", "events", "epochs", "capabilities",
                  "regions"):
        if not isinstance(lex.get(table), dict):
            problems.append(f"lexicon.{table} 缺失或不是对象")
    if not isinstance(lex.get("months"), dict):
        problems.append("lexicon.months 缺失或不是对象")
    # 编年史句式：报告与看板逐键取用，缺一个就是一处静默的 KeyError ⇒ 启动即报。
    for key in _CHRONICLE_KEYS:
        v = (lex.get("chronicle") or {}).get(key)
        if not isinstance(v, str) or not v:
            problems.append(f"lexicon.chronicle.{key} 缺失或不是非空字符串")
    # 阶段词表：结构与顶层一致，**只列要改的叶子**；键必须真的在顶层那张表里，
    # 否则就是一层永远读不到的覆盖（比照 STAGE_TUNABLE 的白名单口径）。
    phase = lex.get("phase_terms")
    if phase is not None:
        if not isinstance(phase, dict):
            problems.append("lexicon.phase_terms 应为对象（{{阶段: {{表名: {{键: 值}}}}}}）")
        else:
            for name, over in phase.items():
                if not isinstance(over, dict):
                    problems.append(f"lexicon.phase_terms.{name} 应为对象")
                    continue
                for section, table in over.items():
                    if not isinstance(lex.get(section), dict):
                        problems.append(
                            f"lexicon.phase_terms.{name}.{section} 在顶层词表里没有这张表")
                        continue
                    if not isinstance(table, dict):
                        problems.append(f"lexicon.phase_terms.{name}.{section} 应为对象")
                        continue
                    for k, v in table.items():
                        if k not in lex[section]:
                            problems.append(
                                f"lexicon.phase_terms.{name}.{section}.{k} "
                                f"在 lexicon.{section} 里没有这个键")
                        elif not isinstance(v, str) or not v:
                            problems.append(
                                f"lexicon.phase_terms.{name}.{section}.{k} 应为非空字符串")
    mode = lex.get("sim_slot_naming")
    if mode is not None and mode not in ("ordinal", "stem", "both"):
        problems.append(
            f"lexicon.sim_slot_naming = {mode!r} 越界（可选 ordinal / stem / both）")
    # 世代更迭的三档名：逐档都要有（缺一档，那一档就会静默退回统称 —— 见 advance_label）。
    plabels = lex.get("stage_promotion_labels")
    if plabels is not None:
        if not isinstance(plabels, dict):
            problems.append("lexicon.stage_promotion_labels 应为对象"
                            "（{{auto / active / renewal: 名字}}）")
        else:
            for k in ("auto", "active", "renewal"):
                v = plabels.get(k)
                if not isinstance(v, str) or not v:
                    problems.append(
                        f"lexicon.stage_promotion_labels.{k} 缺失或不是非空字符串"
                        "（三档 = 自动更替 / 主动更替 / 再创世）")


def _check_phonology(ph, problems):
    syl = ph.get("syllables")
    if (not isinstance(syl, list) or len(syl) != 2
            or not all(isinstance(x, int) for x in syl)):
        problems.append("phonology.syllables 应为 [最少音节, 最多音节] 两个整数")
    elif not 1 <= syl[0] <= syl[1]:
        problems.append(f"phonology.syllables = {syl} 越界（应 1 ≤ 少 ≤ 多）")
    for table in ("onsets", "nuclei", "codas"):
        v = ph.get(table)
        if not isinstance(v, list) or not v:
            problems.append(f"phonology.{table} 应为非空数组")
    # title_calibration / translit 都是【查表】：多出的键只是用不到，少了的键
    # 会退回音位层现生成（设计如此）。故这里只查表在不在，不查键配不配得齐 ——
    # 替代世界的 5 位世界就复用着 12 位的表。
    for table in ("translit", "title_calibration"):
        if not isinstance(ph.get(table), dict):
            problems.append(f"phonology.{table} 缺失或不是对象")
    if not isinstance(ph.get("machine_stems"), list) or not ph.get("machine_stems"):
        problems.append("phonology.machine_stems 应为非空数组")


def _check_seeding(sd, problems):
    per = sd.get("per_locus")
    if not isinstance(per, dict) or "min" not in per or "max" not in per:
        problems.append("seeding.per_locus 应为 {{min, max}}")
        return
    _num(problems, "seeding.per_locus", per, "min", lo=0)
    _num(problems, "seeding.per_locus", per, "max", lo=0)
    if per["min"] > per["max"]:
        problems.append("seeding.per_locus.min 不能大于 max")
    _num(problems, "seeding", sd, "alpha", lo=0.0)


def validate_config_raw(params, loci_raw, seeding, operators, mapping,
                        conclusions, calendar, lexicon, phonology, problems):
    """config/ 侧的自洽校验。就地往 problems 追加问题，不抛异常。

    它吃【原始字典】而不是 Config —— 因为装配过程本身就会用到下标取值
    （`mp["observables"]` 之类），必须先校验、后装配，才谈得上「启动即报」。
    """
    _check_params(params, problems)
    _check_capability_names(params, problems, lexicon)
    _check_verdict_rules(params, problems)
    _check_loci(loci_raw, params.get("dim"), problems)
    _check_mapping(mapping, params.get("dim"), params.get("observables"), problems)
    _check_operators(operators, problems)
    _check_conclusions(conclusions, problems, params.get("verdict_rules"))
    _check_calendar(calendar, lexicon, problems)
    _check_lexicon(lexicon, problems)
    _check_phonology(phonology, problems)
    _check_seeding(seeding, problems)


def validate_data_raw(genesis, assertions, anchors, disturbances, actors,
                      timeline_nodes, problems):
    """data/ + 预设侧的自洽校验。就地往 problems 追加问题，不抛异常。"""
    _check_genesis(genesis, problems)
    _check_assertions(assertions, problems)
    _check_anchors(anchors, problems)
    _check_disturbances(disturbances, problems)
    _check_actors(actors, problems)
    _check_timeline(timeline_nodes, problems)


def _check_genesis(gen, problems):
    prop = gen.get("proposition")
    if not isinstance(prop, dict) or not prop.get("id"):
        problems.append("genesis.proposition.id 缺失")
    rt = gen.get("runtime") or {}
    solver = rt.get("solver")
    if solver is not None and solver not in SOLVER_NAMES:
        problems.append(
            f"genesis.runtime.solver = {solver!r} 不是已登记的演算方向"
            f"（可选：{'、'.join(SOLVER_NAMES)}）")
    dom = gen.get("domain")
    if not isinstance(dom, dict):
        problems.append("genesis.domain 缺失")
        return
    iv = dom.get("initial_variable")
    if not isinstance(iv, list) or not iv:
        problems.append("genesis.domain.initial_variable 应为非空数组")
    dis = dom.get("disorder")
    if dis is not None:
        if not isinstance(dis, list):
            problems.append("genesis.domain.disorder 应为数组")
        elif isinstance(iv, list) and len(dis) != len(iv):
            problems.append(
                f"genesis.domain.disorder 长度 {len(dis)} ≠ "
                f"initial_variable 长度 {len(iv)}（消融会据此取失序度）")
    _check_stages(dom, iv, problems)


def _check_stages(dom, iv, problems):
    """阶段装配（可选）：长度与变量域对齐，门名须已登记。

    它允许比 initial_variable 多一项 —— 多出来的那项是「变量域穷尽之后（阶段四）」。
    """
    raw = dom.get("stages")
    if raw is None:
        return
    if not isinstance(raw, list):
        problems.append("genesis.domain.stages 应为数组")
        return
    from .operators import GATE_NAMES
    n = len(iv) if isinstance(iv, list) else None
    if n and len(raw) not in (n, n + 1):
        problems.append(
            f"genesis.domain.stages 长度 {len(raw)} 应为 {n}"
            f"（与 initial_variable 一一对应）或 {n + 1}"
            f"（再多一项＝变量域穷尽之后的阶段）")
    for i, s in enumerate(raw):
        where = f"genesis.domain.stages[{i}]"
        if not isinstance(s, dict):
            problems.append(f"{where} 应为对象")
            continue
        on = s.get("on") or []
        if not isinstance(on, list):
            problems.append(f"{where}.on 应为数组")
        else:
            for g in on:
                if g not in GATE_NAMES:
                    problems.append(
                        f"{where}.on 里的 {g!r} 不是已登记的机制门"
                        f"（可选：{'、'.join(GATE_NAMES)}）")
        if s.get("params"):
            # 不静默忽略：只允许覆盖【运行时真会读】的旋钮（白名单在 engine/operators.py），
            # 否则写了也没人读 —— 那正是这类项目最容易烂掉的地方。
            from .operators import STAGE_TUNABLE
            params = s.get("params")
            if not isinstance(params, dict):
                problems.append(f"{where}.params 应为对象")
                continue
            for k, v in params.items():
                if k not in STAGE_TUNABLE:
                    problems.append(
                        f"{where}.params 里的 {k!r} 不是阶段可覆盖的旋钮"
                        f"（可选：{'、'.join(STAGE_TUNABLE)}）")
                elif not isinstance(v, (int, float)) or isinstance(v, bool):
                    problems.append(
                        f"{where}.params.{k} 应为数字，实为 {type(v).__name__}")


def normalize_stages(gen) -> list:
    """把 genesis.domain.stages 归一成 [{"on": (门名, …), "params": {…}}, …]。

    缺省（没写 stages）返回 [] —— 调用方据此完全退回"只用 disorder"的历史行为。
    """
    dom = gen.get("domain") or {}
    raw = dom.get("stages")
    if raw is None:
        return []
    return [{"on": tuple(s.get("on") or ()),
             "params": dict(s.get("params") or {})} for s in raw]


def stage_gates(profiles, index) -> tuple:
    """阶段 0..index 累积开启的门。

    装配是**累积**的：后一阶段保留前一阶段的机制（wiki 里阶段三正是在阶段二的
    基础上"加入记忆继承机制"）。index 会被夹到合法范围内。
    """
    if not profiles:
        return ()
    index = max(0, min(int(index), len(profiles) - 1))
    out = []
    for p in profiles[:index + 1]:
        for g in p["on"]:
            if g not in out:
                out.append(g)
    return tuple(out)


def stage_params(profiles, index) -> dict:
    """阶段 0..index 累积的【参数覆盖】（后一阶段覆盖前一阶段）。

    它只进消融 —— 与 `disorder` 同一条通路：阶段定义的是**探针条件**，不是主世界。
    """
    if not profiles:
        return {}
    index = max(0, min(int(index), len(profiles) - 1))
    out = {}
    for p in profiles[:index + 1]:
        out.update(p["params"])
    return out


def _check_assertions(assertions, problems):
    """断言的字段与【名字】。名字写错过去只会静默记一条 FAIL，现在启动即报。"""
    from .assertions import known as assertion_known
    for i, a in enumerate(assertions):
        kind = a.get("assert")
        if not isinstance(kind, str) or not kind:
            problems.append(f"assertions[{i}].assert 缺失或不是字符串")
        elif not assertion_known(kind):
            problems.append(
                f"assertions[{i}].assert = {kind!r} 不是引擎认得的断言名"
                f"（这类名字过去只会静默记 FAIL）")
        if "expect" not in a:
            problems.append(f"assertions[{i}].expect 缺失")
        if "where" in a and not isinstance(a["where"], dict):
            problems.append(f"assertions[{i}].where 应为对象")


def _check_anchors(anchors, problems):
    for i, a in enumerate(anchors):
        if not a.get("key") and not a.get("fingerprint"):
            problems.append(f"anchors[{i}] 既没有 key 也没有 fingerprint")


#: 扰动 payload 里哪些字段其实是「演算方向」—— 按能力分派，逐个校验。
#: 它们过去只会在运行时静默失效（方向比对恒为假，或写进一个谁也认不出的名字）。
_SOLVER_PAYLOAD = {
    "modify_operator": ("to", "from"),
    "overwrite_operator": ("to",),
}


def _check_solver_value(val, problems, where):
    if val is not None and val not in SOLVER_NAMES:
        problems.append(
            f"{where} = {val!r} 不是已登记的演算方向"
            f"（可选：{'、'.join(SOLVER_NAMES)}）")


def _check_solver_payload(cap, payload, problems, where):
    """扰动 payload 里凡是要写进 / 比作「演算方向」的地方，都必须已登记。"""
    for field in _SOLVER_PAYLOAD.get(str(cap), ()):
        _check_solver_value(payload.get(field), problems, f"{where}.{field}")
    if cap == "gaze":
        _check_solver_value((payload.get("effect") or {}).get("solver"),
                            problems, f"{where}.effect.solver")
    elif cap == "revise_protocol":
        for k, rw in enumerate(payload.get("rewrites") or []):
            if isinstance(rw, dict) and str(rw.get("rule")) == "solver.direction":
                _check_solver_value(rw.get("value"), problems,
                                    f"{where}.rewrites[{k}].value")


def _check_disturbances(disturbances, problems):
    """扰动流：帧号须是非负整数，能力 / 选择器 / 方向名都须已注册。"""
    from .disturbance import CAPABILITIES
    from .selector import known as selector_known
    for i, rec in enumerate(disturbances):
        f = rec.get("frame")
        if not isinstance(f, int) or isinstance(f, bool) or f < 0:
            problems.append(f"disturbances[{i}].frame 应为非负整数，实为 {f!r}")
        cap = rec.get("capability")
        if cap not in CAPABILITIES:
            problems.append(f"disturbances[{i}].capability = {cap!r} 不是已注册的能力")
        sel = rec.get("selector")
        if sel is not None:
            expr = sel.get("expr") if isinstance(sel, dict) else None
            if not selector_known(expr):
                problems.append(
                    f"disturbances[{i}].selector.expr = {expr!r} 不是引擎认识的选择器")
        payload = rec.get("payload") or {}
        if isinstance(payload, dict):
            _check_solver_payload(cap, payload, problems, f"disturbances[{i}].payload")
        cond = rec.get("active_if")
        if isinstance(cond, dict) and str(cond.get("field")) == "solver":
            _check_solver_value(cond.get("equals"), problems,
                                f"disturbances[{i}].active_if.equals")


def _check_actors(actors, problems):
    for i, a in enumerate(actors or []):
        if not a.get("id"):
            problems.append(f"actors[{i}].id 缺失")
        if "grants" in a and not isinstance(a["grants"], list):
            problems.append(f"actors[{i}].grants 应为数组")


def _check_timeline(nodes, problems):
    for i, n in enumerate(nodes):
        if not n.get("id"):
            problems.append(f"timeline.nodes[{i}].id 缺失")
        if not n.get("feature"):
            problems.append(f"timeline.nodes[{i}].feature 缺失")


def apply_fast(cfg, data, k: int):
    """测试提速：把所有【时间刻度】按 k 压缩，但 attempt_period 保持不动 ——
    于是死循环的轮回轮次也按 k 缩减，全流程由数分钟降到数秒。

    它只压缩时长、不删机制：位表 / 算子 / 断言 / 时间线全都不变。
    仅用于冒烟回归（机制是否连通）；帧号类断言与时间线仍须用完整预算验收。
    """
    k = int(k)
    if k <= 1:
        return
    p = cfg.params
    for key in ("frames", "promotion_cooldown", "promotion_dwell", "domain_dwell",
                "ablation_period", "ablation_frames", "tau_age", "life_span"):
        if key in p:
            p[key] = max(1, int(p[key]) // k)
    p["freeze_dwell"] = max(64, int(p.get("freeze_dwell", 256)) // k)
    p["tick_marks"] = [max(1, int(t) // k) for t in (p.get("tick_marks") or [])]
    cfg.fast = k
    data.rescale(k)


def load_preset(root, name):
    """预设 = 一批【外生绑定】。

    它只提供四样东西，全都在演算之外：
      seed      可选的固定种子
      anchors   名字的渲染绑定（locus:* 给席位，emerge:* 给涌现次序）
      events    外生扰动（可定时、可带状态条件）—— 与 data/ 的扰动流合并
      timeline  期望清单（哪些事件在什么帧之前发生）—— 引擎【从不读它】

    name 为空 / "emergent" 表示"涌现版"：不出锚定、不加扰动、不带期望，
    名字与轨迹全部由演算自己长出来。
    """
    if not name or name in ("none", "emergent"):
        return {"name": name or "emergent", "seed": None,
                "anchors": [], "events": [], "timeline": {"nodes": []}}
    d = os.path.join(root, "presets", name)
    meta_path = os.path.join(d, "preset.json")
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"找不到预设 {name!r}（缺 {meta_path}）")
    meta = _json(meta_path)
    meta["name"] = name
    meta.setdefault("anchors", _jsonl(os.path.join(d, "anchors.jsonl")))
    meta.setdefault("events", _jsonl(os.path.join(d, "events.jsonl")))
    meta.setdefault("disturbances", _jsonl(os.path.join(d, "disturbances.jsonl")))
    meta.setdefault("assertions", _jsonl(os.path.join(d, "assertions.jsonl")))
    # 世界命题覆盖（可选）：预设自带 genesis.json 时，递归并到 data/genesis.json 上。
    # 这是一条【世界级】覆盖 —— 预设据此声明一个「初始变量域 / 阶段装配不同」的世界。
    g_path = os.path.join(d, "genesis.json")
    if os.path.exists(g_path):
        meta.setdefault("genesis", _json(g_path))
    actors_path = os.path.join(d, "actors.json")
    if os.path.exists(actors_path):
        meta.setdefault("actors", list(_json(actors_path).get("actors") or []))
    lex_path = os.path.join(d, "lexicon.json")
    if os.path.exists(lex_path):
        meta.setdefault("lexicon", _json(lex_path))
    tl_path = os.path.join(d, "timeline.json")
    meta.setdefault("timeline", _json(tl_path) if os.path.exists(tl_path)
                    else {"nodes": []})
    return meta


def _deep_merge(base: dict, over: dict) -> dict:
    """递归合并（dict 递归、其余含数组整块替换）—— 预设的 genesis 覆盖用。"""
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _merge_lex(base: dict, over) -> dict:
    """把预设的渲染词表覆盖到基础词表上（只合并一层子表）。

    词表是 L5 表层：换一套它，同一段演算就被讲成另一个世界的神话。
    同一件事，默认叫「死循环」，预设可以叫成别的。
    """
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


class Config:
    """θ：参数与算子装配。"""

    def __init__(self, root=ROOT, lex_overlay=None):
        self.root = root
        self.fast = 0          # 测试提速的压缩因子（0/1 = 未启用，见 run.py --fast）
        cfg = os.path.join(root, "config")
        # 先把原始文件读齐、校验通过，再装配 —— 否则装配时的下标取值会先炸，
        # 报出来的是一处 KeyError，而不是「哪几个文件哪里对不上」的整张单子。
        self.params = _json(os.path.join(cfg, "params.json"))
        loci_raw = _json(os.path.join(cfg, "loci.json"))["loci"]
        self.seeding = _json(os.path.join(cfg, "seeding.json"))
        ops = _json(os.path.join(cfg, "operators.json"))
        mapping = _json(os.path.join(cfg, "mapping.json"))
        self.conclusions = _json(os.path.join(cfg, "conclusions.json"))
        self.phonology = _json(os.path.join(cfg, "phonology.json"))
        self.lexicon = _merge_lex(_json(os.path.join(cfg, "lexicon.json")),
                                  lex_overlay)
        self.calendar = _json(os.path.join(cfg, "calendar.json"))

        problems = []
        validate_config_raw(self.params, loci_raw, self.seeding, ops, mapping,
                            self.conclusions, self.calendar, self.lexicon,
                            self.phonology, problems)
        _report("config/", problems)

        self.pipeline = list(ops["pipeline"])
        self.gated = set(ops.get("gated", []))

        self.invariant_names = _json(os.path.join(cfg, "invariants.json"))["enabled"]
        self.policies = _json(os.path.join(cfg, "policies.json"))
        # 帧初快照的唯一用途是「原地重放」（把世界退回帧首）。只有配置里存在
        # REPLAY_SAME_FRAME 策略时它才可能被读到 —— 否则每帧深拷贝整个状态纯属
        # 白做。主循环据此决定要不要留快照；世界演算一个比特都不受影响。
        self.needs_snapshot = any(
            isinstance(pol, dict) and pol.get("strategy") == "REPLAY_SAME_FRAME"
            for pol in self.policies.values())

        self.obs_names = list(mapping["observables"])
        self.mapping = np.asarray(mapping["matrix"], dtype=np.float32)

        self.loci = [
            Locus(l["id"], l["order"], l["capacity"], l["decay"], l["couplings"])
            for l in loci_raw
        ]
        self.coupling = np.stack([l.couplings for l in self.loci])

    def policy(self, code: str) -> dict:
        return self.policies.get(code, {"strategy": "CONTINUE"})


class DataSet:
    """E：外部扰动流 + 断言 + 预设期望清单。"""

    def __init__(self, root=ROOT, preset=None):
        d = os.path.join(root, "data")
        self.preset = load_preset(root, preset)
        # 世界命题：data/ 的基础 genesis，可被预设自带的 genesis 递归覆盖。
        self.genesis = _deep_merge(_json(os.path.join(d, "genesis.json")),
                                   self.preset.get("genesis") or {})
        # 断言：data/ 的通用判据 + 预设自带的剧情判据。两者都只是【核对】，不参与演算。
        self.assertions = (_jsonl(os.path.join(d, "assertions.jsonl"))
                           + list(self.preset.get("assertions") or []))
        # 锚定层：data/ 里的通用锚 + 预设里的剧情锚。两者都只是渲染绑定。
        self.anchors = (_jsonl(os.path.join(d, "anchors.jsonl"))
                        + list(self.preset.get("anchors") or []))
        # 外部实体表：谁在操作这个世界、各自握有哪些修改权限。它是【外生】的 ——
        # 引擎只认「已登记的实体」，不认任何一个名字。
        self.actors = list(self.preset.get("actors") or [])
        # 扰动流：data/ 的通用剧本 + 预设自带的剧本与事件。都是【外部】投递，
        # 不参与演算规则 —— 换一个预设，同一个世界的走向可以完全不同。
        raw_dist = (_jsonl(os.path.join(d, "disturbances.jsonl"))
                    + list(self.preset.get("disturbances") or [])
                    + list(self.preset.get("events") or []))
        # 时间线：期望清单。引擎从不读它，只有报告与种子检索会用到。
        self.timeline_nodes = list((self.preset.get("timeline") or {}).get("nodes") or [])

        # 校验必须排在排序【之前】：frame 一缺，下面按 frame 排序就会当场 KeyError。
        problems = []
        validate_data_raw(self.genesis, self.assertions, self.anchors, raw_dist,
                          self.actors, self.timeline_nodes, problems)
        _report(f"data/ + 预设 {preset!r}", problems)

        # 阶段装配（可选）：变量域每一档要装哪些机制。空列表 = 完全不装配（与历史一致）。
        self.stage_profiles = normalize_stages(self.genesis)

        self.disturbances = sorted(raw_dist, key=lambda r: int(r["frame"]))

        self._by_frame = {}
        self._persist = []
        for rec in self.disturbances:
            self._by_frame.setdefault(int(rec["frame"]), []).append(rec)
            if rec.get("payload", {}).get("persist"):
                self._persist.append(rec)
        self.onsets = sorted({int(r["frame"]) for r in self.disturbances})
        # 带 `when` 的投递：最先触发帧仍记在上面（用作"不许跳过去"的锚），但实际触发要看
        # 条件 —— 由内核的条件槽按"条件首次成立"触发（见 core.run 的 ①'）。内核只把它们
        # 当【数据】拿着，不认识条件的写法（谓词由应用层传进来）。今天的预设一条都没有。
        self.conditioned = [r for r in self.disturbances if r.get("when")]

    def stage_gates(self, index: int):
        """阶段 0..index 累积开启的门（装配是累积的）。没配 stages 时恒为空。"""
        return stage_gates(self.stage_profiles, index)

    def stage_params(self, index: int):
        """阶段 0..index 累积的参数覆盖。没配 stages 时恒为空。"""
        return stage_params(self.stage_profiles, index)

    def at(self, n: int):
        """取第 n 帧应投递的扰动。persist 的从起始帧起每帧重复投递。

        带 `when` 的记录**不在这里**返回 —— 它们由内核的条件槽在"条件首次成立"那一帧
        触发（见 core.run 的 ①'）。今天没有任何记录带 when，故与历史逐位相同。
        """
        out = [r for r in self._by_frame.get(n, ()) if not r.get("when")]
        for rec in self._persist:
            if int(rec["frame"]) < n and not rec.get("when"):
                out.append(rec)
        return out

    def next_onset(self, n: int):
        """下一个【首次出现】扰动的帧。用于周期跳跃（不改变语义，只省时间）。"""
        for f in self.onsets:
            if f > n:
                return f
        return None

    def rescale(self, k: int):
        """把整条外部时间线按 k 压缩。只用于测试提速 —— 不改任何一条规则。

        与 params 侧的时间刻度压缩配套使用（见 run.py 的 --fast）。
        **阶段的帧预算也是"时长"，一并压缩**：`genesis.domain.stages[i].params`
        里逐档写死的 `domain_dwell` 会**盖住** params 侧被压缩的那个值 —— 不压它，
        阶段推进就拖后，而永劫回归期帧是跳过的、帧基时钟在那里会饿死，
        于是复用与逐帧真跑会算出不同的 `domain_index`（判据 5 直接红）。
        """
        if k <= 1:
            return
        for prof in self.stage_profiles:
            budget = prof.get("params", {}).get("domain_dwell")
            if budget is not None:
                prof["params"]["domain_dwell"] = max(1, int(budget) // k)
        for rec in self.disturbances:
            rec["frame"] = max(1, int(rec["frame"]) // k)
        self.disturbances.sort(key=lambda r: int(r["frame"]))
        self._by_frame = {}
        self._persist = []
        for rec in self.disturbances:
            self._by_frame.setdefault(int(rec["frame"]), []).append(rec)
            if rec.get("payload", {}).get("persist"):
                self._persist.append(rec)
        self.onsets = sorted({int(r["frame"]) for r in self.disturbances})
        # 带 `when` 的投递：最先触发帧仍记在上面（用作"不许跳过去"的锚），但实际触发要看
        # 条件 —— 由内核的条件槽按"条件首次成立"触发（见 core.run 的 ①'）。内核只把它们
        # 当【数据】拿着，不认识条件的写法（谓词由应用层传进来）。今天的预设一条都没有。
        self.conditioned = [r for r in self.disturbances if r.get("when")]