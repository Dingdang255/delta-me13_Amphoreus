#!/usr/bin/env python3
"""把配置里的渲染映射翻成一张可读对照表（F1）。

    python tools/lexicon_table.py            # 打表到标准输出
    python tools/lexicon_table.py --write    # 写入 docs/术语对照表.md
    python tools/lexicon_table.py --check    # 与 docs/术语对照表.md 比对（CI 用）

表是【生成】的，不是手写的：内容全部来自 config/lexicon.json、config/phonology.json、
config/loci.json、config/conclusions.json。于是「换一套词表就被讲成另一个世界」
这件事有一张随时可刷新的对照表；单测会核对文档与配置不许漂移。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "术语对照表.md")

# 打印中文前把 stdio 钉成 UTF-8（英文 Windows 默认 cp1252，打印会 UnicodeEncodeError）。
# 与 engine/__init__.py 的同一处兜底一致；本脚本刻意不 import engine，故自带一份。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def _load(*parts):
    with io.open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def build() -> str:
    lex = _load("config", "lexicon.json")
    ph = _load("config", "phonology.json")
    loci = _load("config", "loci.json")["loci"]
    concl = _load("config", "conclusions.json")
    params = _load("config", "params.json")
    genesis = _load("data", "genesis.json")

    out = []
    A = out.append
    A("# 术语对照表")
    A("")
    A("> 本文件由 `python tools/lexicon_table.py --write` **生成**，请勿手改；")
    A("> 单测会核对它与配置是否一致（`tests/test_lexicon_table.py`）。")
    A("")
    A("引擎内核里没有专有名词：它只认 `locus / slot / agent / overflow / promotion`。")
    A("下面这些词是**渲染层**（`config/lexicon.json` 与各预设的覆盖）贴上去的 ——")
    A("换一套词表，同一段演算就被讲成另一个世界的神话。")
    A("")

    A("## 一、十二席")
    A("")
    A("| 位次 | 职位（拉丁 / 汉） | 称号 / 圣所 | 城邦 | 该位的原生因子 |")
    A("|---|---|---|---|---|")
    cities = lex.get("cities") or {}
    for l in sorted(loci, key=lambda x: x["order"]):
        cal = ph.get("title_calibration", {}).get(l["id"], ["", l["id"]])
        A(f'| `{l["id"]}` | {cal[0]} / {cal[1]} | '
          f'{lex["regions"].get(l["id"], "—")} | {cities.get(l["id"], "—")} | '
          f'{l["order"]} |')
    A("")
    A("「称号 / 圣所」是 `regions`（与位一一对应）；「城邦」是 `cities`（更粗、**可空缺**）。")
    A("")

    A("## 二、抽象术语 → 世界内说法")
    A("")
    A("| 引擎里的名字 | 渲染词 | 它是什么 |")
    A("|---|---|---|")
    for k, v in lex["terms"].items():
        A(f'| `{k}` | {v} | — |')
    A("")

    A("## 三、初始变量域")
    A("")
    A("| 域 | 渲染词 |")
    A("|---|---|")
    for k, v in lex["domains"].items():
        A(f"| `{k}` | {v} |")
    A("")

    A("## 四、演算方向与机制名")
    A("")
    A("| 枚举 | 渲染词 |")
    A("|---|---|")
    for k, v in lex["events"].items():
        A(f"| `{k}` | {v} |")
    A("")

    A("## 五、扰动能力")
    A("")
    A("| 能力名 | 渲染词 |")
    A("|---|---|")
    for k, v in sorted(lex["capabilities"].items()):
        A(f"| `{k}` | {v} |")
    A("")

    A("## 六、纪元与月份（光历）")
    A("")
    A("纪元（`config/calendar.json` 的 `eras`）按【帧】划分：`calendar: false` 的纪元")
    A("【还没有历法】，只渲染纪元名；第一个 `calendar: true` 的纪元带 `origin`（光历元年），")
    A("此后沿用同一套年序 —— 故年份恒为正整数。据 wiki：光历由刻法勒在【黄金世】测定。")
    A("")
    A("| 帧区间 | 键 | 渲染词 | 有历法 | 元年 |")
    A("|---|---|---|---|---|")
    cal = _load("config", "calendar.json")
    eras = cal.get("eras", [])
    start = 0
    for e in eras:
        until = e.get("until_frame")
        end = "—" if until is None else f"{int(until):,}"
        key = e.get("lexicon_key", "")
        A(f'| {start:,}–{end} | `{key}` | {lex.get("epochs", {}).get(key, key)} | '
          f'{"是" if e.get("calendar") else "否"} | '
          f'{e.get("origin", "") if e.get("calendar") else ""} |')
        start = 0 if until is None else int(until) + 1
    A("")
    A(f'一年 = {cal.get("days_per_month", 1)} 日 × '
      f'{cal.get("months_per_year", 1)} 月；1 帧 = 1 日。月份名：')
    A("")
    A("| 月序 | 键 | 渲染词 |")
    A("|---|---|---|")
    for i, key in enumerate(cal.get("month_keys", []), 1):
        A(f'| {i} | `{key}` | {lex.get("months", {}).get(key, key)} |')
    A("")

    A("## 七、结论与停因")
    A("")
    A("| 裁决枚举 | 文案 id | 短名 | 停因短码 | 文案 |")
    A("|---|---|---|---|---|")
    for k, e in concl.items():
        if not isinstance(e, dict):
            continue
        A(f'| `{k}` | `{e.get("id", "")}` | {e.get("label", "")} | '
          f'`{e.get("stop", "")}` | {e.get("template", "")} |')
    A("")
    A("非裁决类停因（预算 / 安全阀 / 剪枝）在 `config/lexicon.json` 的 `stop_reasons` 里。")
    A("")

    A("## 八、判据表")
    A("")
    A("内层结论照 `config/params.json` 的 `verdict_rules` 逐条求值，第一条成立者即答案。")
    A("`when` 是情形、`require` 是附加条件（各自的注册表在 `engine/verdicts.py`）。")
    A("")
    A("| 裁决 | 情形 | 附加条件 | 未改写时升格 |")
    A("|---|---|---|---|")
    for r in params.get("verdict_rules", []):
        extra = []
        for spec in (r.get("require") or []):
            if "solver" in spec:
                extra.append(f'solver = `{spec["solver"]}`')
            elif "counter" in spec:
                extra.append(f'{spec["counter"]} ≥ {spec.get("min")}')
        A(f'| `{r.get("id")}` | `{r.get("when")}` | {"；".join(extra) or "—"} | '
          f'{"是" if r.get("ascends") else "—"} |')
    A("")

    A("## 九、城邦与地理")
    A("")
    A("**城邦已在词表里**：`config/lexicon.json` 的 `cities`（一位一城、**可空缺**）。")
    A("它只进**渲染层**（报告的一列 + 看板席位卡与图例），不参与演算 —— 删掉它，轨迹逐帧不变。")
    A("本表**只填有考据的席位**，其余留空（界面显示「—」）：")
    A("")
    A("| 席位 | 城邦 |")
    A("|---|---|")
    for lid in sorted(cities):
        A(f"| `{lid}` | {cities[lid]} |")
    A("")
    A("依据：`docs/wiki/moegirl.md` 的「地理 · 城邦」与十二泰坦表（该表把 `晨昏之眼` 等")
    A("列为圣所/地标，与 `regions` 的称号同名，故不重复计入城邦）。")
    A("")
    A("`regions` 与 `cities` 是两层：前者是泰坦的**称号 / 圣所**（与位一一对应，12 项）；")
    A("后者是**城邦**（更粗、允许空缺）。**更细的地理**（地图、区域划分、移动要塞的路线）")
    A("仍未建模 —— 那需要一层独立的地理维度（见改进方案 B4），收益在叙事、不在机制。")
    A("")

    A("## 十、初始变量域 · 四个阶段")
    A("")
    A("阶段顺序取自 `data/genesis.json` 的 `domain.initial_variable`（前三档）+ **多出来的")
    A("那一项**（变量域穷尽之后的阶段四）；名字取本表的 `domains` 与 `terms.domain_exhausted`；")
    A("`stage_conclusions` 是每一档的**结论**（wiki 口径）。同 `cities` 一样，它们只进")
    A("**渲染层**（报告的「阶段目录」+ 看板的阶段卡与时间线上的阶段带），**删掉它们")
    A("轨迹逐帧不变**。每一档跑满自己的 `domain_dwell` 帧预算才换下一档（`OP_DOMAIN`）。")
    A("")
    A("| 档 | 名字 | 结论（wiki 口径） |")
    A("|---|---|---|")
    dom_names = lex.get("domains") or {}
    terms = lex.get("terms") or {}
    variables = list((genesis.get("domain") or {}).get("initial_variable") or [])
    stage_names = [dom_names.get(v, v) for v in variables]
    stage_names.append(terms.get("domain_exhausted", "—"))
    conc = lex.get("stage_conclusions") or []
    for i, nm in enumerate(stage_names):
        A(f"| {i + 1} | {nm} | {conc[i] if i < len(conc) else '—'} |")
    A("")
    A("另外 `stage_promotion_labels` 给世代更迭那个机制分了**三档**名字，跟着 wiki 的两处")
    A("改名走：更早叫**自动更替**（循环自始就有）；**第三阶段**内、协议改写那一刻起叫")
    A("**主动更替**（biligame 第 19,110,218 次循环「将自动更替循环修改为电信号主动更替」；")
    A("moegirl 第 41 行「第三阶段…完成了主动更替循环的行为」）；**第四阶段**起才叫**再创世**")
    A("（moegirl 第 47 行「第四阶段…利用「再创世」进行世代更迭」）。两处界都不靠配置猜 ——")
    A("前者取 Telemetry 里 `renewal.mode` 落进规则覆盖表的那一帧，后者取 `DOMAINS_EXHAUSTED`。")
    A("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="生成术语对照表")
    ap.add_argument("--write", action="store_true", help="写入 docs/术语对照表.md")
    ap.add_argument("--check", action="store_true", help="与文档比对，不一致则退出码 1")
    args = ap.parse_args()

    text = build()
    if args.write:
        with io.open(DOC, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {DOC}")
        return 0
    if args.check:
        cur = io.open(DOC, encoding="utf-8").read() if os.path.exists(DOC) else ""
        if cur.strip() == text.strip():
            print("✓ 术语对照表与配置一致")
            return 0
        print("✗ 术语对照表与配置不一致 —— 跑 python tools/lexicon_table.py --write 刷新")
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
