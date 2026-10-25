"""独立 CLI 窗口：连接主进程的本地 socket，渲染 `>>>` 消息并处理 `prompt`。

这个脚本只负责“显示与提问”，不参与演算；所有文案都来自主进程发来的
`msg` / `prompt` 记录，本文件不写死任何剧情名词。

由 `apps/terminal_bridge.py` 用 `CREATE_NEW_CONSOLE`（Windows）或常见终端
模拟器（POSIX）拉起：

    python -m apps.terminal_window --port <port> --token <token>
"""
from __future__ import annotations

import argparse
import json
import socket
import sys


def render_msg(rec) -> str:
    """把一条 `msg` 记录渲染成 CLI 行。"""
    return ">>> " + str(rec.get("text", ""))


def parse_answer(raw, options, default):
    """把输入解析成选项之一；空输入用默认值；非法输入返回 None。"""
    raw = (raw or "").strip()
    if not raw:
        return default
    for opt in options:
        if raw.lower() == str(opt).lower():
            return opt
    return None


def _ask(rec):
    """在真实控制台里问一次；非法输入重问一次，仍非法则回落默认。"""
    options = [str(o) for o in (rec.get("options") or ["Y", "n"])]
    default = str(rec.get("default") or options[0])
    label = ">>> " + str(rec.get("text", ""))
    if rec.get("ask"):
        label += " " + str(rec.get("ask"))
    label += " [" + "/".join(options) + "]"
    for _ in range(2):
        try:
            raw = input(label + " ")
        except (EOFError, KeyboardInterrupt):
            return default
        answer = parse_answer(raw, options, default)
        if answer is not None:
            return answer
    return default


def run(port, token, stream=None, writer=None):
    """连接主进程并进入消息循环。测试可注入 `stream` / `writer`。"""
    stream = stream or sys.stdout
    writer = writer or stream

    sock = socket.create_connection(("127.0.0.1", int(port)), timeout=10)
    rf = sock.makefile("r", encoding="utf-8", newline="\n")
    wf = sock.makefile("w", encoding="utf-8", newline="\n")

    def write(line=""):
        print(line, file=writer, flush=True)

    def send(obj):
        wf.write(json.dumps(obj, ensure_ascii=False) + "\n")
        wf.flush()

    try:
        write("δ-me13 终端")
        write("─" * 48)
        send({"t": "ready", "token": token})
        for line in rf:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = rec.get("t")
            if kind == "msg":
                write(render_msg(rec))
            elif kind == "prompt":
                answer = _ask(rec)
                send({"t": "answer", "id": rec.get("id"), "answer": answer})
                write(">>> " + answer)
            elif kind == "end":
                write("─" * 48)
                verdict = rec.get("verdict") or "—"
                write(f"演算结束 · 帧 {rec.get('frame', '—')} · 裁决 {verdict}")
                break
            elif kind == "error":
                write("终端错误：" + str(rec.get("text", "")))
    finally:
        try:
            wf.close()
        except OSError:
            pass
        try:
            rf.close()
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="δ-me13 独立 CLI 窗口")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--token", required=True)
    args = ap.parse_args(argv)
    try:
        run(args.port, args.token)
    except OSError as exc:
        print(f"无法连接主进程：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
