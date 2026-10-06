"""内层判据表（C4）的求值器。

判据表来自 `config/params.json` 的 `verdict_rules`；「情形」与「附加条件」各自是一张
**注册表** —— 加一种新的情形 / 条件，只需在这两张表里补一项，不必改求值逻辑。

一条规则长这样：

    {"id": "annihilation", "when": "all_falsified", "ascends": true,
     "require": [{"counter": "destruction_events", "min": 240}]}

`require` 里每项【恰好含一个已知条件键】，该键的值是它的入参：
  `{"solver": "OP_..."}`                    —— 当前演算方向须等于它
  `{"counter": "destruction_events", "min": 240}` —— 某个账本计数须达阈值

本文件不应出现任何专有名词。若出现，构建失败（tools/grep_forbidden.py）。
"""
from __future__ import annotations

from .vocabulary import REQUIRE_NAMES, WHEN_NAMES


# ---- 情形：{名字: (st, cfg, sig) -> bool} -----------------------------------
def _when_all_falsified(st, cfg, sig):
    """十二位全部被证伪 —— 全称域上的反例已穷尽。"""
    return sig["falsified"]


def _when_stalled_and_exhausted(st, cfg, sig):
    """结构冻结且变量域已穷尽 —— 状态不再产生新状态，反例却仍未穷尽。"""
    return sig["stalled"] and st.domains_exhausted


WHEN = {
    "all_falsified": _when_all_falsified,
    "stalled_and_exhausted": _when_stalled_and_exhausted,
}


# ---- 附加条件：{键: (st, cfg, spec) -> bool} --------------------------------
def _req_solver(st, cfg, spec):
    return st.solver == str(spec["solver"])


def _req_counter(st, cfg, spec):
    return float(getattr(st, str(spec["counter"]), 0.0)) >= float(spec.get("min", 0))


REQUIRE = {
    "solver": _req_solver,
    "counter": _req_counter,
}

# 名字表的【唯一来源】在内核侧的 `vocabulary`；这里核对实现与它一一对应 ——
# 加了实现却忘了登记名字，会在导入时当场报错，而不是等某份配置校验时才发现。
assert set(WHEN) == set(WHEN_NAMES), "WHEN 的实现与 vocabulary.WHEN_NAMES 不一致"
assert set(REQUIRE) == set(REQUIRE_NAMES), "REQUIRE 的实现与 vocabulary.REQUIRE_NAMES 不一致"


def known_when():
    """引擎认得的 `when` 名。"""
    return WHEN_NAMES


def known_require():
    """引擎认得的 `require` 名。"""
    return REQUIRE_NAMES


# ---- 求值 -------------------------------------------------------------------
def _falsified(st, cfg) -> bool:
    """全称域上的反例是否已穷尽 —— **两路探针一致**才算。

    · 路 A（`progress`，**独留**口径）：单独留下这一席，它能否自己把迷你世界推向失序；
      达标线是 `tau_falsify`（= 消融熵达到 `tau_ablation_entropy`）。
    · 路 B（`progress2`，**剔除**口径）：拿掉这一席，其余十一席是否照样失序。
      达标线是 `tau_falsify_band`，**不是** τ —— 这个比值（剔除后熵 / 全在时熵）的
      期望本就在 1 以下（实测 0.96–0.99），用 τ=1 在期望上就是假的。现行语义是
      「删掉任一席，失序度损失不超过 (1 − band)」= **没有哪一席是瓶颈**。

    两路都要达标才算这一席被证伪 —— 单一探针的偏置因此不容易骗过判据，
    这就是 R3「提升区分度」的落点。两路的读数都不进 digest / world_signature，
    故加它们本身不改轨迹；改的是**裁决**（因而会动结论时刻）。
    """
    tau = float(cfg.params["tau_falsify"])
    band = float(cfg.params.get("tau_falsify_band", tau))
    return all(l.progress >= tau and l.progress2 >= band for l in st.loci)


def _rule_holds(st, cfg, rule, sig) -> bool:
    """判据表里的一条是否成立。认不出的情形 / 条件一律不成立（配置侧会先报错）。"""
    pred = WHEN.get(str(rule.get("when", "")))
    if pred is None or not pred(st, cfg, sig):
        return False
    for spec in (rule.get("require") or []):
        if not isinstance(spec, dict):
            return False
        keys = [k for k in spec if k in REQUIRE]
        if len(keys) != 1:
            return False
        if not REQUIRE[keys[0]](st, cfg, spec):
            return False
    return True


def inner_conclusion(st, cfg, stalled: bool):
    """不看外生闸门，纯按当前状态、照判据表逐条求值，第一条成立者即答案。

    返回结论枚举；None = 此刻还得不出结论。**不套用外生改写** —— 那是
    `evaluate()` 的事（兜底路径要的正是「内层答案」）。
    """
    sig = {"falsified": _falsified(st, cfg), "stalled": bool(stalled)}
    for rule in (cfg.params.get("verdict_rules") or []):
        if _rule_holds(st, cfg, rule, sig):
            return str(rule["id"])
    return None


def ascends_of(cfg, verdict) -> bool:
    """这条结论是否意味着「演算主体升格外溢」（判据表里用 ascends 标出）。"""
    for rule in (cfg.params.get("verdict_rules") or []):
        if str(rule.get("id")) == str(verdict):
            return bool(rule.get("ascends"))
    return False


def evaluate(st, cfg, stalled: bool):
    """一次遍历同时给出 (结论, 是否升格) —— 结论里程碑与裁决共用它。

    外生变量一旦载入，结论即被改写 —— 改写优先于一切内层判定。
    """
    verdict = inner_conclusion(st, cfg, stalled)
    if st.conclusion_override:
        verdict = str(st.conclusion_override)
    if verdict is None:
        return None, False
    return verdict, ascends_of(cfg, verdict)
