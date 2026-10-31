#!/usr/bin/env python3
"""Lint terminal message files, including branch structure (ADR-0004).

    python tools/messages_lint.py
    python tools/messages_lint.py --check
    python tools/messages_lint.py presets/plot/messages.jsonl
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps import terminal  # noqa: E402


def default_files():
    patterns = [
        os.path.join(ROOT, "presets", "*", "messages.jsonl"),
        os.path.join(ROOT, "worlds", "*", "presets", "*", "messages.jsonl"),
    ]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    return sorted(files)


def lint_file(path):
    errors, warnings = [], []
    try:
        messages = terminal.load_messages(path)
    except (ValueError, OSError) as exc:
        return [str(exc)], []

    index = {m.get("id"): i for i, m in enumerate(messages) if m.get("id")}
    for i, msg in enumerate(messages):
        if msg["kind"] != "prompt":
            continue
        mid = msg.get("id", f"<line {i + 1}>")
        if not msg.get("default"):
            warnings.append(f"{mid}: prompt 没有 default（非交互时无法继续）")
        branches = msg.get("on_choice") or {}
        for choice, branch in branches.items():
            jump = branch.get("jump")
            rejoin = branch.get("rejoin")
            if jump:
                if jump not in index:
                    errors.append(f"{mid}: 分支 {choice} 的 jump 目标 {jump} 不存在")
                elif index[jump] <= i:
                    errors.append(f"{mid}: 分支 {choice} 的 jump 目标不在前方")
            if rejoin:
                if rejoin not in index:
                    errors.append(f"{mid}: 分支 {choice} 的 rejoin 目标 {rejoin} 不存在")
                elif jump and rejoin in index and jump in index and index[rejoin] < index[jump]:
                    errors.append(f"{mid}: 分支 {choice} 的 rejoin 在 jump 之前")
            elif branches:
                warnings.append(f"{mid}: 分支 {choice} 未声明 rejoin（主线回归点）")
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="terminal message lint")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    files = args.files or default_files()
    total_errors = 0
    total_warnings = 0
    for path in files:
        errors, warnings = lint_file(path)
        rel = os.path.relpath(path, ROOT)
        total_errors += len(errors)
        total_warnings += len(warnings)
        print(f"{rel}: errors {len(errors)} · warnings {len(warnings)}")
        for line in errors:
            print(f"  ERROR {line}")
        for line in warnings:
            print(f"  WARN  {line}")

    print()
    print(f"files {len(files)} · errors {total_errors} · warnings {total_warnings}")
    if total_errors:
        return 1
    if args.check:
        print("messages ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
