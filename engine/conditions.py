"""投递条件的最小求值器（**服务层**，不是内核）。

只认三类词 —— 与设计稿 §8.5 的决定一致：

  ① 观测量比较      `frame >= 12000` / `order < 0.9` / `entropy > 3`
  ② 账本计数比较    `promotions >= 8` / `attempts > 100`
  ③ 事件是否发生过  `event("nikador_felled")`

连接词只有 `&&` `||` `!` 与括号。就这么点语法 —— 别的字符一个都不认。

三条硬规矩：

  · **不用 `eval`** —— 词法即全部语法。表达式是【数据】，不是代码。
  · **不碰世界** —— 能读到的量只能来自调用方传进来的观测快照 `obs`。
    故"预读未来"在构造上就做不到 —— 词法里根本没有「按下标取未来帧」这类形状，
    与红线 2（`tools/stepwise_lint.py`）是同一个口径。
  · **读不到就报错** —— `obs` 里没有的名字一律抛 `ConditionError`，
    绝不静默当 False（静默会让"条件写错了"变成"这条永远不触发"，最难查的那种）。

用法：

    tree = parse('promotions >= 8 && event("nikador_felled")')
    evaluate(tree, {"promotions": 9, "events": {"nikador_felled": True}})   # True
    terms(tree)            # {'promotions'} ∪ 事件名另算
"""
from __future__ import annotations

import re

__all__ = ["ConditionError", "parse", "evaluate", "terms", "check"]


class ConditionError(ValueError):
    """条件写错了：语法不认、名字读不到、类型对不上。"""


# ---- 词法 -------------------------------------------------------------------
# 只认这四类记号；出现别的字符（`[`、`;`、`.`、单引号…）直接报错。
_TOKEN = re.compile(r"""
    \s*(?:
        (?P<num>\d+(?:\.\d+)?)
      | (?P<str>"[^"]*")
      | (?P<op><=|>=|==|!=|&&|\|\||[<>!(),])
      | (?P<name>[A-Za-z_][A-Za-z_0-9]*)
    )
""", re.X)

_CMP_OPS = {">=", "<=", "==", "!=", ">", "<"}


def _tokenize(expr: str):
    out, i, n = [], 0, len(expr)
    while i < n:
        m = _TOKEN.match(expr, i)
        if not m or m.end() == m.start():
            if expr[i:].strip() == "":        # 只剩余量空白：正常收尾
                break
            raise ConditionError(f"条件里有不认识的字符：{expr[i:i + 12]!r}")
        i = m.end()
        kind = m.lastgroup
        text = m.group(kind)
        if kind == "num":
            out.append(("num", float(text)))
        elif kind == "str":
            out.append(("str", text[1:-1]))
        else:
            out.append((kind, text))
    return out


# ---- 语法（递归下降）--------------------------------------------------------
# 语法树是不可变嵌套元组 —— 可比较、可缓存，配合 RNG 那套"纯函数"的口径。
#
#   or   := and ('||' and)*
#   and  := not ('&&' not)*
#   not  := '!' not | cmp
#   cmp  := atom (比较符 atom)?
#   atom := '(' or ')' | 数字 | 字符串 | event '(' 字符串 ')' | 名字

class _Parser:
    def __init__(self, toks, expr):
        self.toks, self.i, self.expr = toks, 0, expr

    def _peek(self):
        if self.i < len(self.toks):
            return self.toks[self.i]
        return None

    def _eat(self, text):
        t = self._peek()
        if t is not None and t[0] == "op" and t[1] == text:
            self.i += 1
            return True
        return False

    def _need(self, text):
        if not self._eat(text):
            raise ConditionError(f"条件语法不完整，缺少 {text!r}：{self.expr!r}")

    def parse(self):
        node = self._or()
        if self._peek() is not None:
            raise ConditionError(f"条件尾部有多余内容：{self.expr!r}")
        return node

    def _or(self):
        node = self._and()
        while self._eat("||"):
            node = ("or", node, self._and())
        return node

    def _and(self):
        node = self._not()
        while self._eat("&&"):
            node = ("and", node, self._not())
        return node

    def _not(self):
        if self._eat("!"):
            return ("not", self._not())
        return self._cmp()

    def _cmp(self):
        left = self._atom()
        t = self._peek()
        if t is not None and t[0] == "op" and t[1] in _CMP_OPS:
            self.i += 1
            return ("cmp", t[1], left, self._atom())
        return left

    def _atom(self):
        t = self._peek()
        if t is None:
            raise ConditionError(f"条件语法不完整：{self.expr!r}")
        kind, text = t
        if kind == "op" and text == "(":
            self.i += 1
            node = self._or()
            self._need(")")
            return node
        if kind == "num":
            self.i += 1
            return ("num", text)
        if kind == "str":
            self.i += 1
            return ("str", text)
        if kind == "name":
            self.i += 1
            if text == "event":
                self._need("(")
                arg = self._peek()
                if arg is None or arg[0] != "str":
                    raise ConditionError(f"event(...) 只收字符串字面量：{self.expr!r}")
                self.i += 1
                self._need(")")
                return ("event", arg[1])
            return ("name", text)
        raise ConditionError(f"条件语法不完整：{self.expr!r}")


#: 解析缓存 —— 纯函数，同一条表达式永远得到同一棵树。
_CACHE: dict = {}


def parse(expr):
    """字符串 → 语法树。已经解析过的（或本来就是树）直接返回。"""
    if not isinstance(expr, str):
        return expr                      # 已是语法树
    got = _CACHE.get(expr)
    if got is None:
        got = _Parser(_tokenize(expr), expr).parse()
        _CACHE[expr] = got
    return got


# ---- 求值 -------------------------------------------------------------------

def _lookup(obs, key):
    if key not in obs:
        raise ConditionError(
            f"条件读不到 {key!r} —— 观测快照里没有这个名字。"
            f"（可选：{sorted(k for k in obs if not str(k).startswith('_'))}）")
    return obs[key]


def _truth(v):
    return bool(v)


def evaluate(expr, obs) -> bool:
    """求值。`expr` 可以是字符串或 `parse()` 过的树；`obs` 是调用方给的观测快照。"""
    return _truth(_ev(parse(expr), obs))


def _ev(node, obs):
    kind = node[0]
    if kind == "num" or kind == "str":
        return node[1]
    if kind == "name":
        return _lookup(obs, node[1])
    if kind == "event":
        seen = obs.get("events")
        if seen is None:
            raise ConditionError("条件用了 event(...)，但观测快照里没有 events 表")
        if node[1] not in seen:
            raise ConditionError(f"条件问了一个没登记的事件：{node[1]!r}")
        return _truth(seen[node[1]])
    if kind == "not":
        return not _truth(_ev(node[1], obs))
    if kind == "and":
        return _truth(_ev(node[1], obs)) and _truth(_ev(node[2], obs))
    if kind == "or":
        return _truth(_ev(node[1], obs)) or _truth(_ev(node[2], obs))
    if kind == "cmp":
        return _cmp(node[1], _ev(node[2], obs), _ev(node[3], obs))
    raise ConditionError(f"不认识的语法树节点：{kind!r}")


def _cmp(op, a, b):
    def cls(v):
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, (int, float)):
            return "num"
        if isinstance(v, str):
            return "str"
        return "other"

    ca, cb = cls(a), cls(b)
    if op in ("==", "!="):
        if ca != cb:
            raise ConditionError(f"比较的两边类型不同：{a!r} {op} {b!r}")
        return (a == b) if op == "==" else (a != b)
    if ca != "num" or cb != "num":
        raise ConditionError(f"大小比较只对数字：{a!r} {op} {b!r}")
    return {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[op]


# ---- 校验 -------------------------------------------------------------------

def terms(expr) -> set:
    """表达式里用到的【名字】与【事件名】（用于配置校验：不许出现未知量）。"""
    out = set()

    def walk(n):
        if n[0] in ("num", "str"):
            return
        if n[0] == "name":
            out.add(n[1])
            return
        if n[0] == "event":
            out.add("event:" + n[1])
            return
        for sub in n[1:]:
            if isinstance(sub, tuple):
                walk(sub)

    walk(parse(expr))
    return out


def check(expr, allowed_names=(), allowed_events=()) -> set:
    """校验一条条件：语法要过，用到的名字 / 事件都必须在允许表里。

    返回用到的名字集合；不合规直接抛 `ConditionError`。**这里刻意不做静默降级**。
    """
    got = terms(expr)
    bad_names = {t for t in got if not t.startswith("event:")} - set(allowed_names)
    bad_events = {t[7:] for t in got if t.startswith("event:")} - set(allowed_events)
    if bad_names:
        raise ConditionError(f"条件用了未知量：{sorted(bad_names)}")
    if bad_events:
        raise ConditionError(f"条件用了未登记的事件：{sorted(bad_events)}")
    return got
