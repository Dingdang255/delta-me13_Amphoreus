# -*- coding: utf-8 -*-
"""抓取《如我所书》归档全文（逐角色、逐页）。

来源：wiki 的 `角色名/如我所书` 页面，正文在 {{如我所书|页码N=|左页N=|右页N=}} 模板里。
产出：lore/story/wiki_structured/ruwoshuo.jsonl
用法：python fetch_wiki_book.py
"""
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw
import fetch_wiki_structured as fs

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
SITE = "https://wiki.biligame.com/sr/"
TEMPLATE = "Template:如我所书"


def list_pages():
    d = fw.http_get({"action": "query", "list": "embeddedin", "eititle": TEMPLATE,
                     "eilimit": "500", "format": "json"})
    pages = [p["title"] for p in d.get("query", {}).get("embeddedin", [])]
    pages = [p for p in pages if not p.startswith(("模板:", "Template:", "沙盒"))]
    # 补充搜索到但未走模板的变体页
    for extra in ("荒笛/如我所书", "无/如我所书", "如我所书/昔涟", "如我所书/三月七"):
        if extra not in pages:
            pages.append(extra)
    return pages


def clean_page_text(s):
    """左页/右页文本：去文件引用、<br /> 转换行、清模板。"""
    s = re.sub(r"\[\[(?:文件|File|Image):[^\]]*\]\]", "", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = fw.clean_inline(s)
    return "\n".join(ln.strip() for ln in s.split("\n") if ln.strip())


def parse_sections(w):
    """按 == 标题 == 切段，返回 [(段名, 段内容)]。"""
    parts = re.split(r"^==\s*([^=\n]+?)\s*==\s*$", w, flags=re.M)
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


def parse_template(inner):
    """{{如我所书|页码1=..|左页1=..|右页1=..}} -> {n: {page, left, right}}"""
    fields = {}
    cur = None
    buf = []
    depth = 0
    for ln in inner.split("\n"):
        m = re.match(r"\|(页码\d+|左页\d+|右页\d+)\s*=\s*(.*)$", ln)
        if m and depth == 0:
            if cur:
                fields[cur] = "\n".join(buf).strip()
            cur = m.group(1)
            buf = [m.group(2)]
        else:
            buf.append(ln)
        depth += ln.count("{{") - ln.count("}}")
    if cur:
        fields[cur] = "\n".join(buf).strip()

    recs = {}
    for k, v in fields.items():
        m = re.match(r"(页码|左页|右页)(\d+)$", k)
        if not m:
            continue
        kind, num = m.group(1), int(m.group(2))
        recs.setdefault(num, {})[{"页码": "page_no", "左页": "left", "右页": "right"}[kind]] = v
    return recs


def main():
    os.makedirs(OUT, exist_ok=True)
    pages = list_pages()
    print(f"归档页 {len(pages)} 个")
    out_path = os.path.join(OUT, "ruwoshuo.jsonl")
    total = 0
    seen = set()
    with open(out_path, "w", encoding="utf-8") as fo:
        for page in pages:
            try:
                w = fw.fetch_wikitext(page)
            except Exception as e:
                print(f"  失败 {page}: {e}", file=sys.stderr)
                continue
            url = SITE + urllib.parse.quote(page.replace(" ", "_"))
            character = page.split("/")[1] if page.startswith("如我所书/") else page.split("/")[0]
            n_page = 0
            sections = parse_sections(w) or [("", w)]
            for sec_idx, (sec_name, sec_body) in enumerate(sections, 1):
                for m in re.finditer(r"\{\{如我所书\b", sec_body):
                    depth = 0
                    j = m.start()
                    while j < len(sec_body):
                        if sec_body.startswith("{{", j):
                            depth += 1
                            j += 2
                        elif sec_body.startswith("}}", j):
                            depth -= 1
                            j += 2
                            if depth == 0:
                                break
                        else:
                            j += 1
                    inner = sec_body[m.start() + 2:j - 2]
                    recs = parse_template(inner)
                    for num in sorted(recs):
                        r = recs[num]
                        left = clean_page_text(r.get("left", ""))
                        right = clean_page_text(r.get("right", ""))
                        text = "\n".join(x for x in (left, right) if x)
                        if not text:
                            continue
                        key = (character, sec_name, r.get("page_no", ""), text)
                        if key in seen:  # 如我所书/昔涟 这类镜像页，跳过重复
                            continue
                        seen.add(key)
                        n_page += 1
                        total += 1
                        rec = {
                            "archive_id": f"RW-{character}-{n_page:03d}",
                            "character": character,
                            "part": sec_name or "UNKNOWN",
                            "part_index": sec_idx,
                            "page_no": r.get("page_no", ""),
                            "record_no": n_page,
                            "progress": None,
                            "left": left,
                            "right": right,
                            "text": text,
                            "source_page": page,
                            "source_url": url,
                            "captured_at": "2026-10-31",
                            "grade": "B",
                        }
                        fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  {page}：{n_page} 页")
            time.sleep(0.4)

    print(f"\n合计 {total} 页 → {out_path}")


if __name__ == "__main__":
    main()
