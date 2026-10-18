"""预设时间线：把「哪些事件、在什么帧之前发生」写成一份可核对的清单。

它只是【观测层的期望】，不是输入 —— 引擎从不读它，也没有任何一条演算规则
依赖它。它有且只有三个用途：

  1. 核对：跑完一次后逐条比对（run.py 的报告）。
  2. 筛选：把它当要素约束，去种子空间里检索符合的世界（tools/seed_probe.py）。
  3. 剪枝：节点可带 `by`（最晚帧）。到点还没发生即判否，提前停下省时间。
     剪枝只【提前结束】运行，不写任何状态，因此停下之前的每一帧与全程一致。

节点写法（一条一行，字段与断言同构）：

    {"id": "N01", "feature": "domains_exhausted", "op": "eq", "value": true,
     "by": 4000, "label": "变量域依序走完后被穷尽"}

`by` 只在被观察的特征能【边跑边取】时才生效（见 _LIVE）；取不到的特征
照样参与事后核对，只是不参与剪枝。
"""
from __future__ import annotations


class NodeResult:
    __slots__ = ("id", "label", "ok", "expect", "got", "deadline")

    def __init__(self, id, label, ok, expect, got, deadline=None):
        self.id = id
        self.label = label
        self.ok = bool(ok)
        self.expect = expect
        self.got = got
        self.deadline = deadline

    def __repr__(self):
        mark = "PASS" if self.ok else "FAIL"
        return f"[{mark}] {self.id}  expect={self.expect!r} got={self.got!r}"


def compare(got, op, value) -> bool:
    """把「取到的值」与节点的算子/阈值比一比。取不到（None）一律不成立。"""
    if got is None:
        return False
    try:
        if op == "eq":
            return got == value
        if op == "ne":
            return got != value
        if op == "gt":
            return got > value
        if op == "ge":
            return got >= value
        if op == "lt":
            return got < value
        if op == "le":
            return got <= value
        if op == "in":
            return got in value
        if op == "contains":
            return value in got
        if op == "between":
            return value[0] <= got <= value[1]
    except TypeError:
        return False
    raise KeyError(f"未知算符: {op}")


def nodes_to_constraints(nodes) -> list:
    """把时间线节点摊成要素约束（给种子检索用）。"""
    return [{"feature": n["feature"], "op": n.get("op", "eq"),
             "value": n.get("value"), "id": n.get("id")} for n in nodes]


def check(nodes, feat) -> list:
    """跑完之后逐条核对。只读，不改任何东西。"""
    out = []
    for n in nodes:
        got = feat.get(n["feature"])
        ok = compare(got, n.get("op", "eq"), n.get("value"))
        out.append(NodeResult(n.get("id") or n["feature"],
                              n.get("label") or n["feature"],
                              ok, n.get("value"), got, n.get("by")))
    return out


# 能【边跑边取】的特征 —— 只有单调量才可以用来剪枝。
_LIVE = {
    "domains_exhausted": lambda st, traj: bool(st.domains_exhausted),
    "promotion_count": lambda st, traj: int(st.promotions),
    "round": lambda st, traj: int(st.round),
    "converged": lambda st, traj: bool(st.converged),
    "deadlock": lambda st, traj: bool(traj.deadlock),
    "vacancy_ever": lambda st, traj: traj.violation_counts.get("VACANT", 0) > 0,
    "black_tide_ever": lambda st, traj: traj.violation_counts.get("OVERFLOW", 0) > 0,
    "solver_final": lambda st, traj: st.solver,
    "destruction_ever": lambda st, traj: any(
        c == "destruction" for _f, c in traj.conclusion_trail),
    "protocol_rewritten": lambda st, traj: any(
        k == "PROTOCOL_REWRITTEN" for _f, k, _p in traj.records),
    "override_rules": lambda st, traj: ",".join(sorted(st.overrides)),
    "emitted_events": lambda st, traj: ",".join(
        sorted(k[len("emitted_"):] for k in st.score if k.startswith("emitted_"))),
    "destruction_events": lambda st, traj: int(st.destruction_events),
}


def make_watch(nodes, trace=True):
    """把带 `by` 的节点编成逐帧观察钩子；没有可剪枝的节点就返回 None。"""
    rules = []
    for n in nodes:
        by = n.get("by")
        if by is None:
            continue
        get = _LIVE.get(n["feature"])
        if get is None:
            continue
        rules.append((n.get("id") or n["feature"], int(by), get,
                      n.get("op", "eq"), n.get("value")))
    if not rules:
        return None

    def watch(frame, st, traj):
        for rid, by, get, op, value in rules:
            if frame > by and not compare(get(st, traj), op, value):
                if trace and traj.records is not None:
                    traj.records.append((frame, "PRUNE", {"node": rid, "by": by}))
                return False
        return True

    return watch