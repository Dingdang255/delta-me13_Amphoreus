"""只读终端层：把预设里的系统消息按帧输出成 `>>>` 行。

它只读、不参与演算 —— 不写状态、不改账本、也不返回剪枝信号
（`TerminalFeed.__call__` 恒为 True）。消息文案全部来自
`presets/<name>/messages.jsonl`，本模块不写死任何剧情名词。
"""
from __future__ import annotations

import json
import os
import sys

#: 允许的消息类别。`prompt` 会带选项与默认答案，其余类别只输出正文。
KINDS = ("boot", "log", "warn", "error", "prompt", "status", "output")

#: `prompt` 未写 options 时的默认选项（与预设层的约定一致）。
_DEFAULT_OPTIONS = ("Y", "n")


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
    if options is not None:
        if (not isinstance(options, list) or not options
                or not all(isinstance(o, str) and o.strip() for o in options)):
            raise _bad(path, ln, "options 必须是非空的字符串列表")
        options = list(options)
    default = raw.get("default")
    if default is not None:
        allowed = options if options is not None else list(_DEFAULT_OPTIONS)
        if default not in allowed:
            raise _bad(path, ln, f"default 必须是 options 之一（得到 {default!r}）")

    for key in ("require_event", "suppress_if_event"):
        val = raw.get(key)
        if val is not None and (not isinstance(val, str) or not val.strip()):
            raise _bad(path, ln, f"{key} 必须是非空字符串")

    msg = dict(raw)
    msg["frame"] = int(frame)
    msg["kind"] = kind
    msg["text"] = text
    if options is not None:
        msg["options"] = options
    return msg


def load_messages(path):
    """读 `messages.jsonl`，返回按 `frame` 升序排好的消息列表副本。

    文件不存在 ⇒ `[]`（预设可以没有终端消息）。空行忽略；任何一行不合法
    都立刻抛 `ValueError`，消息里带文件行号与原因。
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
            out.append(_validate(raw, path, ln))
    out.sort(key=lambda m: m["frame"])
    return out


class TerminalFeed:
    """按帧顺序回放系统消息。只读钩子：`__call__` 恒返回 True。

    `write(text)` 决定消息去向（stdout 或实时编年史的同一条落盘通道）；
    `ask` 为真且标准输入是 TTY 时，`prompt` 类消息会等待输入，否则直接用默认答案。
    `st` 只用来查 `score["emitted_*"]`，这里不写任何字段。
    """

    def __init__(self, messages, write=print, ask=False, source=None, sink=None):
        self.messages = list(messages or ())
        self.write = write
        self.ask = bool(ask)
        self.source = source
        self.sink = sink
        self._cursor = 0
        self._prompt_id = 0
        self._last_frame = None
        self._last_st = None
        self._closed = False

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
            self._cursor += 1
            if not self._visible(msg, st):
                continue
            self._emit(msg)

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

    def _emit(self, msg):
        text = msg["text"]
        if msg["kind"] != "prompt":
            self.write(">>> " + text)
            self._sink_msg(msg)
            return
        options = list(msg.get("options") or _DEFAULT_OPTIONS)
        default = msg.get("default") or options[0]
        ask = msg.get("ask")
        label = f">>> {text} {ask}" if ask else f">>> {text}"
        prompt = f"{label} [{'/'.join(options)}]"
        # 独立 CLI 窗口：提问发生在子窗口，主进程阻塞等回答；这里只把
        # 最终答案镜像到 stdout / 日志，避免两边都读 stdin。
        if self.sink is not None and hasattr(self.sink, "prompt"):
            answer = self._sink_prompt(msg, options, default)
            self.write(f"{prompt} → {answer}"
                       + ("（默认）" if answer == default else ""))
            return
        answer, fallback = default, True
        if self.ask and sys.stdin.isatty():
            answer, fallback = self._ask(prompt, options, default)
        self.write(f"{prompt} → {answer}" + ("（默认）" if fallback else ""))

    # ---- 只读 sink（独立 CLI 窗口）-----------------------------------------
    def _sink_msg(self, msg):
        """把消息镜像给子窗口；sink 失败不影响演算。"""
        fn = getattr(self.sink, "msg", None) if self.sink is not None else None
        if fn is None:
            return
        try:
            fn(dict(msg))
        except (OSError, ValueError, TypeError):
            pass

    def _sink_prompt(self, msg, options, default):
        """阻塞等子窗口回答；超时 / 断连 / 非法答案一律回落默认。"""
        rec = dict(msg)
        rec["id"] = self._prompt_id
        self._prompt_id += 1
        try:
            answer = self.sink.prompt(rec)
        except (OSError, ValueError, TypeError):
            answer = None
        if answer not in options:
            return default
        return answer

    @staticmethod
    def _ask(prompt, options, default):
        """交互确认：非法输入重问一次，仍非法就用默认答案（绝不阻塞在死循环里）。"""
        for _ in range(2):
            try:
                raw = input(prompt + " ")
            except (EOFError, KeyboardInterrupt):
                return default, True
            raw = raw.strip()
            if not raw:
                return default, True
            for opt in options:
                if raw.lower() == opt.lower():
                    return opt, opt == default
        return default, True
