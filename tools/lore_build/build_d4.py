# -*- coding: utf-8 -*-
"""D4 对话生成器：从 CN TextMap 串池抽取 Philia093 ↔ 德谬歌 的整段对话。

只做三件事：
  1. 按 locator 取逐字；
  2. 保守清理抽取残字（保留 verbatim_raw）；
  3. 分配 ID / 场景 / 顺序 / next。

不产生任何原文里没有的句子。

注意：本脚本只生成 inferred 说话人；生成后需按 `D4_dialogue/speaker_map.json`
重新应用 `S-024` 的说话人升级（见 13_changelog v1.7），否则 55 行 official 溯源会丢失。
"""
import json, io, os, re

SRC = r"d:\文档\Amphoreus\lore\_probe\textmap_zh_cn.jsonl"
OUT = r"d:\文档\Amphoreus\lore\D4_dialogue\dialogues.jsonl"

# 场景 → 记录区间（左闭右闭）
SCENES = [
    ("SCN-001", 225852, 225866),
    ("SCN-002", 225867, 225887),
    ("SCN-003", 225888, 225905),
    ("SCN-004", 218713, 218725),
    ("SCN-005", 225906, 225945),
    ("SCN-006", 225946, 226010),
    ("SCN-007", 226011, 226060),
    ("SCN-008", 226061, 226161),
    ("SCN-009", 226162, 226200),
]
SKIP = {225893, 225894, 225899, 225901, 225905}   # 选项/按钮，已在 D6 收录

KEEP_PREFIX = (">>>", "<color", "<i>", "【", "{NICKNAME}", "{RUBY", "{F#", "{M#", "{TEXTJOIN")

# 抽取残字的人工覆盖（只删残字，不删正文）
OVERRIDE = {
    225953: "如果到头来，每一次提笔，都只能写下相同的结局。那这篇沉甸甸的史诗……",
}

def clean(s, idx=None):
    if idx in OVERRIDE:
        return OVERRIDE[idx], True

    # 1) 优先保留 >>> / <color> 等标记，即使前面粘着残字
    pc = s.find("<color")
    if 0 <= pc <= 40:
        gt = s.find(">", pc)
        if gt != -1:
            rest = s[gt + 1:]
            if rest.startswith(">>>"):
                return rest, True
        return s[pc:], True

    for tag in (">>>", "<i>", "【"):
        p = s.find(tag)
        if 0 <= p <= 40 and p > 0:
            return s[p:], True

    if s.startswith(KEEP_PREFIX):
        return s, False

    # 2) 去掉开头的 ASCII 控制/标记字节，直到第一个中文或全角标点
    m = re.match(r"^[^\u3400-\u9fff\u3000-\u303f\uff00-\uffef「『（【《]+", s)
    if m and m.end() < len(s):
        return s[m.end():], True
    return s, False

def guess_speaker(s):
    if s.startswith(">>>"):
        return "CHR-003"
    if len(s) <= 14 and "，" not in s and "。" not in s and "？" not in s:
        return "CHR-003"
    return "CHR-002"

rows = []
raw = {}
for line in io.open(SRC, encoding="utf-8"):
    d = json.loads(line)
    raw[d["i"]] = d["s"]

n = 0
for sid, a, b in SCENES:
    seq = [i for i in range(a, b + 1) if i in raw and i not in SKIP]
    for k, i in enumerate(seq):
        text, trimmed = clean(raw[i], i)
        sp = guess_speaker(text)
        n += 1
        rows.append({
            "id": f"DLG-{n:03d}",
            "scene_id": sid,
            "order": k + 1,
            "speaker": None,
            "speaker_inferred": sp,
            "speaker_source": "inferred_low",
            "form": "昔涟" if sp == "CHR-002" else "德谬歌(权杖)",
            "verbatim": text,
            "verbatim_available": True,
            "verbatim_raw": raw[i],
            "extraction_trimmed": trimmed,
            "stage_direction": None,
            "subtext": None,
            "mechanism": {"system_op": "record|format|query" if text.startswith(">>>") else "narrate",
                          "input": None, "output": None},
            "next": [f"DLG-{n+1:03d}"] if k + 1 < len(seq) else [],
            "condition": "linear",
            "source": "S-001",
            "locator": f"S-001:{i}",
            "confidence": "A",
            "note": "speaker 未在数据源中标注，speaker_inferred 由句法启发式给出，仅供建树，不得作为逐字归因",
        })

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with io.open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("dialogues:", len(rows))
print("trimmed:", sum(1 for r in rows if r["extraction_trimmed"]))
