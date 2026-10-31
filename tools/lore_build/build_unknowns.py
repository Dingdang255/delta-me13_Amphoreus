# -*- coding: utf-8 -*-
import io, json, glob, os

root = r"d:\文档\Amphoreus\lore"
out = []
for f in sorted(glob.glob(os.path.join(root, "D*_*/unknowns.jsonl"))):
    dim = os.path.basename(os.path.dirname(f))
    for line in io.open(f, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        d["source_file"] = f"D*/{dim}/unknowns.jsonl"
        out.append(d)

GLOBAL = [
    {"id":"U-G-001","dimension":"ALL","question":"英文/日文文本表","why":"本轮只抽取 cn；en/jp 缓存未处理","queries":["Amphoreus Demiurge dialogue","δ-me13 日本語"],"sites":["S-001","S-015"],"attempted_at":"2026-10-31","impact":"所有多语言差异表为空","fallback":"S-015 日文 wiki"},
    {"id":"U-G-002","dimension":"ALL","question":"旁白/场景叙述","why":"剧情编排表只含台词，不含 narration","queries":["翁法罗斯 旁白"],"sites":["S-002"],"attempted_at":"2026-10-31","impact":"D3 的所有『过程』只能靠任务概述","fallback":"S-001:30370-30433"},
    {"id":"U-G-003","dimension":"ALL","question":"说话人字段","why":"TalkSentenceConfig 的 SpeakerID 未在客户端明文中定位","queries":["SpeakerID TalkSentenceConfig"],"sites":["S-001","S-002"],"attempted_at":"2026-10-31","impact":"D4/D8 的逐字归因受限","fallback":"D6 中带 >>> 的可确定"},
    {"id":"U-G-004","dimension":"ALL","question":"声音/画面/演出细节","why":"无录屏、无截图、无音频提取","queries":["翁法罗斯 剧情 录屏"],"sites":["S-017","S-020"],"attempted_at":"2026-10-31","impact":"D3 的『是否有截图/视频』全部为无","fallback":"无"},
    {"id":"U-G-005","dimension":"ALL","question":"3.0–3.7 的官方版本号映射","why":"章节表只给章节名顺序，未给版本号","queries":["3.0 落木逐火英雄纪","3.7 记忆是梦的开场白"],"sites":["S-001","S-012"],"attempted_at":"2026-10-31","impact":"coverage_matrix 的版本列是 B/C 级","fallback":"S-001:107169-107178"},
]
out.extend(GLOBAL)

with io.open(os.path.join(root, "11_unknowns.jsonl"), "w", encoding="utf-8") as f:
    for d in out:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
print("unknowns", len(out))
