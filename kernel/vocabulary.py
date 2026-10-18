"""内核必须知道的**名字表**。

内核对配置做校验时会问："这个判据名 / 断言名，引擎认不认识？"
—— 它必须知道**名字**，但**不需要知道实现**。实现分别住在服务层
（`verdicts.py` 的判据、`assertions.py` 的断言）。

把名字单独放这一层，是为了让内核不必 import 服务层（见 `tools/layer_lint.py`
的分层红线）。服务层反过来 import 本模块，并在导入时**核对**自己的实现
与这里列的名字一一对应 —— 于是"加了实现却忘了登记名字"会当场报错，
而不是等到某份配置校验时才发现。

本模块只放**字符串常量与纯字符串函数**，不含任何领域知识、不碰世界。
"""
from __future__ import annotations

#: 判据的「触发时机」（`verdict_rules[].when`）—— 实现见 `apps/verdicts.py`
WHEN_NAMES = ("all_falsified", "stalled_and_exhausted")

#: 判据的「附加条件」（`verdict_rules[].require[].kind`）—— 实现见 `apps/verdicts.py`
REQUIRE_NAMES = ("solver", "counter")

#: 断言的种类名（不含 `_at_least` / `_at_most` 后缀）—— 实现见 `apps/assertions.py`
ASSERTION_KINDS = frozenset({
    "domains_exhausted", "black_tide_ever", "vacancy_ever", "promotion_count",
    "persona_count", "persona_with_capability", "persona_named", "deadlock_ever",
    "deadlock_length", "converged", "verdict", "stop_reason", "verdict_frame",
    "conclusion", "solver_changed", "population_final", "destruction_ever",
    "conclusion_reached", "ascended", "protocol_rewritten", "promotion_mode",
    "memory_repaired", "destruction_events", "emitted_events",
})

#: 断言名允许的比较后缀 → 比较方式。
SUFFIX_OPS = (("_at_least", "ge"), ("_at_most", "le"))

#: 内核 `emit()` 会用的**事件类别**（`core.py` 里逐个 emit 的那批 kind）。
#: 服务层（`apps/script.py` 的订阅）要在这里查得到 —— 拼错一个订阅名只会变成
#: "这条规则永远不触发"，是最难查的那类事故，故启动即报。
#: 它只登记**类别名**，不含任何领域知识；内核自己也不读这张表（它只管发）。
EVENT_KINDS = frozenset({
    "DISTURBANCE", "PROTOCOL_REWRITTEN", "DOMAIN_ADVANCE", "DOMAINS_EXHAUSTED",
    "SOLVER_CHANGED", "PROMOTION", "CONVERGED", "EMERGENCE", "SUCCESSION",
    "DEADLOCK_LOOP", "DEADLOCK_TICK", "DEADLOCK_END",
    "ATTEMPT_VAIN", "ATTEMPT_TRACE",
    "VERDICT", "CONCLUSION_REACHED", "ASCENSION", "VIOLATION_STATE",
})


def split_kind(kind: str):
    """`xx_at_least` → ("xx", "ge")；`xx` → ("xx", "eq")。纯字符串处理。"""
    for suffix, op in SUFFIX_OPS:
        if kind.endswith(suffix):
            return kind[: -len(suffix)], op
    return kind, "eq"


def know_assertion(kind: str) -> bool:
    """这个名字引擎认不认识（含后缀）。给配置校验用。"""
    return split_kind(str(kind))[0] in ASSERTION_KINDS
