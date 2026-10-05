#!/usr/bin/env python3
"""判据 2：特例扫描。

词法扫描 engine/ ，若命中任何【专有名词】（角色名 / 泰坦名 / 城邦名 / 命途名 / 派系名），
即视为"源程序写死了剧情"，CI 失败。

**注释同样在扫描范围内** —— 引擎里的考据引用只写「第 N 次循环 / 第 N 行」，
专名（编号与称谓）一律留在 docs/ 与 presets/。

    python3 tools/grep_forbidden.py        # 命中数 > 0 则退出码 1
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 打印中文前把 stdio 钉成 UTF-8（英文 Windows 默认 cp1252，打印会 UnicodeEncodeError）。
# 与 engine/__init__.py 的同一处兜底一致；本脚本刻意不 import engine，故自带一份。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

# 只允许出现在 data/ 与 config/ 渲染层；engine/ 里一个字都不许有。
FORBIDDEN = {
    "角色": [
        "白厄", "昔涟", "刻法勒", "阿格莱雅", "缇宝", "万敌", "遐蝶", "风堇",
        "那刻夏", "塞飞儿", "海瑟音", "星期日", "知更鸟", "黑塔", "赞达尔",
        "来古士", "波尔卡", "卡卡", "开拓者", "三月七", "丹恒", "姬子", "瓦尔特",
    ],
    "泰坦/神名": ["翁法罗斯", "翁法", "泰坦", "雅努斯", "摩纳", "菲莱", "戈厄"],
    "城邦/地名": ["奥赫玛", "悬锋城", "斯缇科西亚", "塔兰图"],
    "命途": ["毁灭", "智识", "强袭", "巡猎", "丰饶", "虚无", "同谐",
             "存护", "欢愉", "贪饕", "纯美", "终末"],
    "世界观词汇": ["黑潮", "金血", "黄金裔", "半神", "火种", "绝灭大君"],
    # 个别角色以【机器编号】的形式被考据引用过（注释里那种「xxNNN」）：同样是专名，
    # 只许出现在 docs/ 与 presets/。
    "机器编号": ["Nammou320"],
}

# 机制名：属于引擎自己的词汇（策略键 / 算子语义），允许出现在 engine/。
# 它们不指向任何一个具体角色或城邦，换一份 data/ 依然成立。
ALLOW = {"再创世", "记忆"}


def scan_file(path):
    hits = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            for cat, words in FORBIDDEN.items():
                for w in words:
                    if w in ALLOW:
                        continue
                    if w in line:
                        hits.append((ln, cat, w, line.strip()))
    return hits


def main():
    engine = os.path.join(ROOT, "engine")
    total = 0
    for name in sorted(os.listdir(engine)):
        if not name.endswith(".py"):
            continue
        hits = scan_file(os.path.join(engine, name))
        if hits:
            print(f"✗ engine/{name}")
            for ln, cat, w, line in hits:
                print(f"    L{ln:<4} [{cat}] 「{w}」  →  {line[:70]}")
            total += len(hits)
    if total == 0:
        print("✓ engine/ 专有名词命中数 = 0")
        return 0
    print(f"\n命中 {total} 处：源程序混入了剧情名词，构建失败。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())