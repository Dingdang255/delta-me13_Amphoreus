"""只读终端层：把预设里的系统消息按帧输出成 `>>>` 行。

它只读、不参与演算 —— 不写状态、不改账本、也不返回剪枝信号
（`TerminalFeed.__call__` 恒为 True）。消息文案全部来自
`presets/<name>/messages.jsonl`，本模块不写死任何剧情名词。

除静态帧外，消息还可以带 `period` / `until` / `cycle_from` / `vars`：
`period` 让**系统遥测**按周期重复（例如「第 N 轮记录已归档」），
`vars` 只允许一组白名单变量，用 `str.format` 渲染（绝不 `eval`）。
剧情节拍不开 `period` —— 一条剧情只在该帧出现一次。
"""
from __future__ import annotations

import json
import os
import string
import sys

#: 允许的消息类别。`prompt` 会带选项与默认答案，其余类别只输出正文。
KINDS = ("boot", "log", "warn", "error", "prompt", "status", "output")

#: `prompt` 未写 options 时的默认选项（与预设层的约定一致）。
_DEFAULT_OPTIONS = ("Y", "n")

#: 模板变量的白名单。只读、只暴露数值，不暴露任何状态对象。
VARS = (
    "frame", "cycle", "tomb_cycles", "tomb_rows", "tomb_volume",
    "memory_rows", "origin_energy", "origin_selfhood", "companion_stage",
)

#: 展开 `period` 后的消息总数上限（防止 period=1 把日志刷爆）。
MAX_MESSAGES = 500


def _bad(path, ln, why):
    """统一的不合法消息异常：带上文件与行号，便于直接改预设。"""
    return ValueError(f"{path}:L{ln} 终端消息不合法：{why}")


def _validate(raw, path, ln):
    """校验一行消息并返回一份副本；缺省字段在这里补齐。"""
    if not isinstance(raw, dict):
        raise _bad(path, ln, "每行必须是 JSON 对象")
    frame = raw.get("frame")
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise _bad(path, ln, f"frame 必须是非负整数（得到 {frame!r}）")
    kind = raw.get("kind", "log")
    if not isinstance(kind, str) or kind not in KINDS:
        raise _bad(path, ln, f"kind 必须是 {' / '.join(KINDS)} 之一（得到 {kind!r}）")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise _bad(path, ln, "text 必须是非空字符串")

    options = raw.get("options")
    labels = {}
    if options is not None:
        if not isinstance(options, list) or not options:
            raise _bad(path, ln, "options 必须是非空列表")
        ids = []
        for opt in options:
            if isinstance(opt, str) and opt.strip():
                ids.append(opt)
                labels[opt] = opt
            elif isinstance(opt, dict) and str(opt.get("id", "")).strip():
                oid = str(opt["id"])
                ids.append(oid)
                labels[oid] = str(opt.get("label") or oid)
            else:
                raise _bad(path, ln, "options 的每项必须是字符串，或带 id 的对象")
        if len(set(ids)) != len(ids):
            raise _bad(path, ln, "options 里有重复 id")
        options = ids
    default = raw.get("default")
    if default is not None:
        allowed = options if options is not None else list(_DEFAULT_OPTIONS)
        if default not in allowed:
            raise _bad(path, ln, f"default 必须是 options 之一（得到 {default!r}）")

    # ---- 分支（ADR-0004）---------------------------------------------------
    on_choice = raw.get("on_choice")
    if on_choice is not None:
        if not isinstance(on_choice, dict) or not on_choice:
            raise _bad(path, ln, "on_choice 必须是非空对象")
        allowed = set(options or ())
        for key, branch in on_choice.items():
            if allowed and key not in allowed:
                raise _bad(path, ln, f"on_choice 的键 {key!r} 不在 options 里")
            if not isinstance(branch, dict):
                raise _bad(path, ln, f"on_choice[{key!r}] 必须是对象")
            for field in ("jump", "rejoin"):
                if field in branch and (not isinstance(branch[field], str)
                                        or not branch[field].strip()):
                    raise _bad(path, ln, f"on_choice[{key!r}].{field} 必须是非空字符串")
            if "inject" in branch and not isinstance(branch["inject"], dict):
                raise _bad(path, ln, f"on_choice[{key!r}].inject 必须是对象")
        if default is None:
            raise _bad(path, ln, "带 on_choice 的 prompt 必须写 default")

    for key in ("require_event", "suppress_if_event", "branch"):
        val = raw.get(key)
        if val is not None and (not isinstance(val, str) or not val.strip()):
            raise _bad(path, ln, f"{key} 必须是非空字符串")

    # ---- 周期 / 模板（可选） ------------------------------------------------
    period = raw.get("period")
    if period is not None:
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            raise _bad(path, ln, f"period 必须是正整数（得到 {period!r}）")
    until = raw.get("until")
    if until is not None:
        if (isinstance(until, bool) or not isinstance(until, int)
                or until < int(frame)):
            raise _bad(path, ln, f"until 必须是不小于 frame 的整数（得到 {until!r}）")
    if period is not None and until is None:
        raise _bad(path, ln, "period 必须与 until 一起使用（否则不知道重复到哪一帧）")
    cycle_from = raw.get("cycle_from")
    if cycle_from is not None and (isinstance(cycle_from, bool)
                                   or not isinstance(cycle_from, int)
                                   or cycle_from < 0):
        raise _bad(path, ln, f"cycle_from 必须是非负整数（得到 {cycle_from!r}）")

    names = raw.get("vars")
    if names is not None:
        if (not isinstance(names, list) or not names
                or not all(isinstance(v, str) and v.strip() for v in names)):
            raise _bad(path, ln, "vars 必须是非空的字符串列表")
        bad = [v for v in names if v not in VARS]
        if bad:
            raise _bad(path, ln, f"vars 里有未登记的变量：{bad}（允许 {list(VARS)}）")
        names = list(names)
        for _lit, field, _spec, _conv in string.Formatter().parse(text):
            if field is None:
                continue
            if field not in names:
                raise _bad(path, ln, f"模板变量 {{{field}}} 不在 vars 里")
    else:
        # 没有 vars 就不允许出现模板字段，避免把 `{...}` 当普通文本误留。
        for _lit, field, _spec, _conv in string.Formatter().parse(text):
            if field is not None:
                raise _bad(path, ln, f"模板变量 {{{field}}} 需要 vars 白名单")

    msg = dict(raw)
    msg["frame"] = int(frame)
    msg["kind"] = kind
    msg["text"] = text
    if options is not None:
        msg["options"] = options
        msg["option_labels"] = labels
    return msg


def _expand(msg, path, ln, max_messages):
    """把一条带 `period` 的消息展开成若干条具体帧的消息；无 period 原样返回。"""
    period = msg.get("period")
    if not period:
        return [msg]
    until = int(msg["until"])
    out = []
    frame = int(msg["frame"])
    while frame <= until:
        one = dict(msg)
        one["frame"] = frame
        out.append(one)
        frame += int(period)
        if len(out) > max_messages:
            raise _bad(path, ln,
                       f"period 展开后消息数超过上限 {max_messages}（缩小 until 或加大 period）")
    return out


def load_messages(path, max_messages=MAX_MESSAGES):
    """读 `messages.jsonl`，返回按 `frame` 升序排好的消息列表副本。

    文件不存在 ⇒ `[]`（预设可以没有终端消息）。空行忽略；任何一行不合法
    都立刻抛 `ValueError`，消息里带文件行号与原因。

    `period` 在这里展开成具体帧；展开后的总数不得超过 `max_messages`，
    以免把三千万轮的循环逐帧写成日志。
    """
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise _bad(path, ln, f"不是合法 JSON（{exc.msg}）") from exc
            msg = _validate(raw, path, ln)
            out.extend(_expand(msg, path, ln, int(max_messages)))
            if len(out) > int(max_messages):
                raise _bad(path, ln,
                           f"消息总数超过上限 {max_messages}（检查 period / 行数）")
    out.sort(key=lambda m: m["frame"])
    seen = {}
    for msg in out:
        mid = msg.get("id")
        if not mid:
            continue
        if mid in seen:
            raise ValueError(f"{path}: 终端消息 id {mid!r} 重复")
        seen[mid] = True
    return out


def _render_text(msg, frame, st):
    """按白名单变量渲染正文；没有 `vars` 时原样返回。

    只读 `st` 的数值字段，不写任何东西；缺字段按 0 处理，模板错误则退回原文
    （校验阶段已经挡住了未登记变量）。
    """
    names = msg.get("vars") or []
    if not names:
        return msg["text"]
    o = getattr(st, "origin", None)
    mem = getattr(st, "memory_bank", None)
    try:
        rows = int(mem.shape[0]) if mem is not None else 0
    except (AttributeError, TypeError):
        rows = 0
    cycle_from = int(msg.get("cycle_from", frame))
    values = {
        "frame": int(frame),
        "cycle": int(frame) - cycle_from + 1,
        "tomb_cycles": int(getattr(o, "tomb_cycles", 0) or 0),
        "tomb_rows": int(getattr(o, "tomb_rows", 0) or 0),
        "tomb_volume": float(getattr(o, "tomb_volume", 0.0) or 0.0),
        "memory_rows": rows,
        "origin_energy": float(getattr(o, "energy", 0.0) or 0.0),
        "origin_selfhood": float(getattr(o, "selfhood", 0.0) or 0.0),
        "companion_stage": int(getattr(o, "companion_stage", 0) or 0),
    }
    try:
        return str(msg["text"]).format(**values)
    except (KeyError, IndexError, ValueError):
        return msg["text"]


class TerminalFeed:
    """按帧顺序回放系统消息。只读钩子：`__call__` 恒返回 True。

    `write(text)` 决定消息去向（stdout 或实时编年史的同一条落盘通道）；
    `ask` 为真且标准输入是 TTY 时，`prompt` 类消息会等待输入，否则直接用默认答案。
    `st` 只用来查 `score["emitted_*"]`，这里不写任何字段。
    """

    def __init__(self, messages, write=print, ask=False, source=None, sink=None,
                 ask_fn=None, max_jumps=64):
        self.messages = list(messages or ())
        self.write = write
        self.ask = bool(ask)
        self.source = source
        self.sink = sink
        self.ask_fn = ask_fn
        self.max_jumps = int(max_jumps)
        self._cursor = 0
        self._prompt_id = 0
        self._last_frame = None
        self._last_st = None
        self._closed = False
        self._jumps = 0
        self.answers = []
        self._branch = None
        self._rejoin = None
        self._by_id = {m.get("id"): i for i, m in enumerate(self.messages) if m.get("id")}

    def __call__(self, frame, st, traj=None):
        if self._closed:
            return True
        self._last_frame = int(frame)
        self._last_st = st
        self._drain(self._last_frame, st)
        return True

    def close(self):
        """收尾：把最后一帧上仍未消费的消息补吐出来。没有未消费消息也安全。"""
        if self._closed:
            return
        if self._last_frame is not None:
            self._drain(self._last_frame, self._last_st)
        self._closed = True

    # ---- 内部 ---------------------------------------------------------------
    def _drain(self, frame, st):
        while self._cursor < len(self.messages):
            msg = self.messages[self._cursor]
            if int(msg["frame"]) > frame:
                break
            index = self._cursor
            self._cursor += 1
            if self._branch and msg.get("branch") and msg["branch"] != self._branch:
                continue
            if not self._visible(msg, st):
                continue
            answer, fallback = self._emit(msg, frame, st)
            if self._rejoin and msg.get("id") == self._rejoin:
                self._branch = None
                self._rejoin = None
            if msg["kind"] != "prompt":
                continue
            self.answers.append({
                "frame": int(frame),
                "message": msg.get("id"),
                "option": answer,
                "source": "default" if fallback else "user",
            })
            branch = (msg.get("on_choice") or {}).get(answer) or {}
            target = branch.get("jump")
            if not target:
                continue
            target_index = self._by_id.get(target)
            if target_index is None or target_index <= index:
                self.write(f"    · 分支跳转被忽略（目标 {target} 不存在或不在前方）")
                continue
            if self._jumps >= self.max_jumps:
                self.write("    · 分支跳转次数达上限，回到顺序播放")
                continue
            self._jumps += 1
            self._cursor = target_index
            self._branch = answer
            self._rejoin = branch.get("rejoin")

    def ledger(self):
        """作答复盘：`[{frame, message, option, source}]`，只读。"""
        return [dict(row) for row in self.answers]

    @staticmethod
    def _visible(msg, st):
        score = getattr(st, "score", None) or {}
        need = msg.get("require_event")
        if need and f"emitted_{need}" not in score:
            return False
        skip = msg.get("suppress_if_event")
        if skip and f"emitted_{skip}" in score:
            return False
        return True

    def _emit(self, msg, frame, st):
        text = _render_text(msg, frame, st)
        if msg["kind"] != "prompt":
            self.write(">>> " + text)
            self._sink_msg(msg, frame, text)
            return None, True
        options = list(msg.get("options") or _DEFAULT_OPTIONS)
        labels = dict(msg.get("option_labels") or {})
        default = msg.get("default") or options[0]
        ask = msg.get("ask")
        label = f">>> {text} {ask}" if ask else f">>> {text}"
        shown = [labels.get(opt, opt) for opt in options]
        prompt = f"{label} [{'/'.join(shown)}]"
        # 独立 CLI 窗口：提问发生在子窗口，主进程阻塞等回答；这里只把
        # 最终答案镜像到 stdout / 日志，避免两边都读 stdin。
        if self.sink is not None and hasattr(self.sink, "prompt"):
            answer = self._sink_prompt(msg, options, default, frame, text)
            fallback = answer == default
            self.write(f"{prompt} → {labels.get(answer, answer)}"
                       + ("（默认）" if fallback else ""))
            return answer, fallback
        answer, fallback = default, True
        if self.ask and (self.ask_fn is not None or sys.stdin.isatty()):
            answer, fallback = self._ask(prompt, options, default, labels)
        self.write(f"{prompt} → {labels.get(answer, answer)}"
                   + ("（默认）" if fallback else ""))
        return answer, fallback

    # ---- 只读 sink（独立 CLI 窗口）-----------------------------------------
    def _sink_msg(self, msg, frame, text):
        """把消息镜像给子窗口；sink 失败不影响演算。"""
        fn = getattr(self.sink, "msg", None) if self.sink is not None else None
        if fn is None:
            return
        try:
            rec = dict(msg)
            rec["frame"] = int(frame)
            rec["text"] = text
            fn(rec)
        except (OSError, ValueError, TypeError):
            pass

    def _sink_prompt(self, msg, options, default, frame, text):
        """阻塞等子窗口回答；超时 / 断连 / 非法答案一律回落默认。"""
        rec = dict(msg)
        rec["id"] = self._prompt_id
        rec["frame"] = int(frame)
        rec["text"] = text
        self._prompt_id += 1
        try:
            answer = self.sink.prompt(rec)
        except (OSError, ValueError, TypeError):
            answer = None
        if answer not in options:
            return default
        return answer

    def _ask(self, prompt, options, default, labels=None):
        """交互确认：非法输入重问一次，仍非法就用默认答案（绝不阻塞在死循环里）。

        `ask_fn` 存在时不读 stdin（测试与子窗口用）；否则走内置 `input`。
        """
        labels = labels or {}
        reader = self.ask_fn or input
        for _ in range(2):
            try:
                raw = reader(prompt + " ")
            except (EOFError, KeyboardInterrupt):
                return default, True
            raw = str(raw or "").strip()
            if not raw:
                return default, True
            for opt in options:
                if raw.lower() == opt.lower() or raw == labels.get(opt):
                    return opt, opt == default
        return default, True
