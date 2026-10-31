# -*- coding: utf-8 -*-
"""从 biligame wiki（wiki.biligame.com/sr）抓取翁法罗斯开拓任务完整剧情。

产出按版本（3.0–3.7）分卷的 Markdown，含：任务描述、出场人物、任务流程、
剧情梗概、以及逐字对话（说话人 / 旁白 / 玩家选项 / 场景标题）。

用法：python fetch_wiki_amphoreus.py
输出：lore/story/amphoreus_wiki/amphoreus_3.X.md + README.md
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "story", "amphoreus_wiki")
API = "https://wiki.biligame.com/sr/api.php"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://wiki.biligame.com/sr/",
    "Accept": "application/json,text/plain,*/*",
}


def http_get(params, timeout=40, retries=4):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2.0 * (attempt + 1))


VERSIONS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8")


def ask_tasks():
    """SMW 查询翁法罗斯所有开拓任务，返回 [{name, ver, chapter, no}]。

    注意：该站 action=ask 单次最多只返回 50 条，offset 又被忽略，无法分页；
    因此改为按版本逐次查询（每版本任务数 < 50），再合并。"""
    tasks = []
    seen = set()
    for ver in VERSIONS:
        params = {
            "action": "ask",
            "query": "[[任务地区::翁法罗斯]][[所属版本::%s]]"
                     "|?任务类型|?任务编号|?系列任务" % ver,
            "format": "json",
            "api_version": "2",
            "limit": "500",
        }
        try:
            d = http_get(params)
        except Exception:
            continue
        res = d.get("query", {}).get("results", {})
        if not isinstance(res, dict):
            continue
        for name, v in res.items():
            po = v.get("printouts", {})
            typ = (po.get("任务类型") or [""])[0]
            no = (po.get("任务编号") or [""])[0]
            chap = (po.get("系列任务") or [""])[0]
            if typ != "开拓任务" or not no:  # 章节总览页没有任务编号
                continue
            if name in seen:
                continue
            seen.add(name)
            chap = re.sub(r"\[\[(.*?)\]\]", r"\1", chap)
            tasks.append({"name": name, "ver": ver, "chapter": chap, "no": no})
    tasks.sort(key=lambda t: (t["ver"], t["no"], t["name"]))
    return tasks


def fetch_wikitext(page):
    d = http_get({
        "action": "parse", "page": page, "format": "json",
        "prop": "wikitext", "redirects": "1",
    })
    if "error" in d:
        raise RuntimeError(f"{page}: {d['error'].get('info')}")
    return d["parse"]["wikitext"]["*"]


# ---------- 内联模板清理 ----------

def clean_inline(s):
    """把内联模板还原为纯文本：颜色/注音/图标/角色对话/黑幕/短信警告。"""
    # HTML 实体解码：&gt; -> >、&nbsp; -> 空格、&#...; 等
    s = html.unescape(s).replace("\xa0", " ")
    # wiki 链接：[[目标|显示]] -> 显示；[[目标]] -> 目标；粗体/斜体标记剔除；HTML 注释剔除
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = s.replace("'''", "").replace("''", "")
    # HTML → Markdown 语义：强调转 **/*、居中/对齐容器转引用块、<br> 转段落换行
    s = re.sub(r"<span[^>]*>(.*?)</span>", r"\1", s, flags=re.S | re.I)
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s, flags=re.S | re.I)
    s = re.sub(r"<strong>(.*?)</strong>", r"**\1**", s, flags=re.S | re.I)
    s = re.sub(r"<big>(.*?)</big>", r"**\1**", s, flags=re.S | re.I)
    s = re.sub(r"<i>(.*?)</i>", r"*\1*", s, flags=re.S | re.I)
    s = re.sub(r"<em>(.*?)</em>", r"*\1*", s, flags=re.S | re.I)
    s = re.sub(r"<nowiki>(.*?)</nowiki>", r"\1", s, flags=re.S | re.I)
    # <center>/<div> 是块级容器，由 _render_fold 统一包成引用块；这里仅剥掉标签、保留内容
    s = re.sub(r"<(?:center|div)[^>]*>(.*?)</(?:center|div)>", r"\1", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    # 颜色：{{颜色|样式|文本}} -> 文本（可嵌套）；注音：{{注音|正文|注音}} -> 正文
    for _ in range(8):
        s2 = re.sub(r"\{\{颜色\|[^|}]*\|([^{}]*)\}\}", r"\1", s)
        s2 = re.sub(r"\{\{注音\|([^|}]*)\|[^{}]*\}\}", r"\1", s2)
        if s2 == s:
            break
        s = s2
    # 角色对话：{{角色对话|位置|说话人|文本|内容}} 或 {{角色对话|模板开始|说话人|内容}} -> *说话人：内容
    s = re.sub(r"\{\{角色对话\|[^|{}]*\|([^|{}]*)\|(?:[^|{}]*\|)?([^{}]*)\}\}",
               lambda m: f"*{m.group(1)}：{m.group(2)}", s)
    # 图标：{{图标|名称|数量}} -> 名称×数量
    s = re.sub(r"\{\{图标\|([^|}]*)(?:\|([^}]*))?\}\}",
               lambda m: m.group(1) + (("×" + m.group(2)) if m.group(2) else ""), s)
    # 黑幕：{{黑幕|文本}} -> （文本）；短信警告 -> 〔系统〕文本
    s = re.sub(r"\{\{黑幕\|([^{}]*)\}\}", r"（\1）", s)
    s = re.sub(r"\{\{短信警告\|([^{}]*)\}\}", r"〔系统〕\1", s)
    # 其余未知「单行」模板：保留最后一个 | 后的文本（多行块级模板不在此处理）
    s = re.sub(r"\{\{[^{}\n]*\|([^{}\n]*)\}\}", r"\1", s)
    s = re.sub(r"\{\{[^{}\n]*\}\}", "", s)
    return s


# ---------- 元数据解析 ----------

def parse_meta(w):
    m = re.search(r"\{\{任务\b(.*?)\n\}\}", w, re.S)
    if not m:
        return {}
    body = m.group(1)
    meta = {}
    for k in ("任务名称", "所属版本", "任务描述", "出场人物", "任务流程",
              "剧情梗概", "系列任务", "任务编号", "任务地区"):
        mm = re.search(r"\|%s=(.*?)(?=\n\|[A-Za-z\u4e00-\u9fff]+=|\n\}\}|\Z)" % k, body, re.S)
        if mm:
            meta[k] = clean_inline(mm.group(1).strip())
    return meta


# ---------- 剧情内容解析 ----------

# 块级模板（多行、需括号配平提取）
BLOCK_TEMPLATES = ("剧情选项", "短信选项", "折叠", "折叠框", "任务描述", "提示", "提示消息")


def parse_plot(w):
    """解析 ==剧情内容== 之后的正文，返回已渲染的 Markdown 行列表。"""
    i = w.find("==剧情内容==")
    if i < 0:
        return []
    return _parse_body(w[i + len("==剧情内容=="):])


def _parse_body(body):
    """递归解析一段正文（可含任意嵌套的块级/内联模板），返回 Markdown 行列表。"""
    md = []
    buf = []

    def flush():
        if buf:
            md.extend(_render_text_lines("".join(buf)))
            buf.clear()

    n = len(body)
    i = 0
    while i < n:
        if body.startswith("{{", i):
            depth = 0
            j = i
            while j < n:
                if body.startswith("{{", j):
                    depth += 1
                    j += 2
                elif body.startswith("}}", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            inner = body[i + 2:j - 2]
            name = re.split(r"[|\s]", inner.strip(), maxsplit=1)[0].strip()
            if name in BLOCK_TEMPLATES:
                flush()
                md.extend(_render_block(name, inner))
            else:
                buf.append(body[i:j])  # 内联模板，交由 _render_text_lines 统一清洗
            i = j
        elif body[i:i + 8].lower() == "<tabber>":
            j = body.find("</tabber>", i)
            if j < 0:
                j = n
            else:
                j += len("</tabber>")
            flush()
            md.extend(_render_tabber(body[i + len("<tabber>"):j - len("</tabber>")]))
            i = j
        else:
            buf.append(body[i])
            i += 1
    flush()
    return md


def _render_text_lines(text):
    """把一段正文文本（*台词 / :旁白 / ===小节=== / ---- 分隔 / 引用块）渲染成 Markdown 行。"""
    text = clean_inline(text)
    out = []
    for raw in text.split("\n"):
        rl = raw.strip()
        if not rl:
            if out and out[-1] != "":
                out.append("")  # 保留段落分隔（<br> 转行而来）
            continue
        if re.match(r"^===\s*.*\s*===\s*$", rl):
            out.append("### " + rl.strip("= \t"))
        elif rl == "----":
            out.append("---")
        elif rl.startswith(">"):
            out.append(rl)  # 引用块（居中/对齐容器）
        elif rl.startswith("**") and rl.endswith("**"):
            out.append(rl)  # 粗体
        elif rl.startswith("*") and rl.endswith("*"):
            out.append(rl)  # 斜体
        elif rl.startswith("*"):
            out.append("- " + rl.lstrip("*").strip())  # wiki 无序列表 → md
        elif rl.startswith(":"):
            out.append("*（旁白）" + rl.lstrip(":").strip() + "*")
        else:
            out.append(rl)
    while out and out[-1] == "":
        out.pop()
    return out


def _render_block(name, inner):
    if name in ("剧情选项", "短信选项"):
        return _render_option(inner)
    if name in ("折叠", "折叠框"):
        return _render_fold(inner)
    if name == "任务描述":
        return [_render_scene(inner)]
    if name == "提示":
        return _blockquote(_render_hint(inner))
    if name == "提示消息":
        return _blockquote(_render_notice(inner))
    return []


def _blockquote(text):
    """把（可能多行的）文本渲染为引用块；每行之间补 `>` 空行，避免被合并成一段。"""
    return _quote_lines(text.split("\n"))


def _render_tabber(inner):
    """<tabber> 分支容器：分支以「标签=」开头（后续分支以 |-| 分隔），渲染为分支小标题 + 内容。"""
    out = []
    for part in inner.split("|-|"):
        part = part.strip("\n")
        if not part.strip():
            continue
        nl = part.find("\n")
        first = part if nl < 0 else part[:nl]
        rest = "" if nl < 0 else part[nl + 1:]
        m = re.match(r"^\s*([^=\n]+?)\s*=", first)
        label = ""
        if m:
            label = m.group(1).strip()
            after = first[m.end():].strip()
            if after:
                rest = (after + "\n" + rest).strip("\n")
        else:
            rest = part
        if label:
            out.append(f"**〔分支：{label}〕**")
        if rest.strip():
            out.extend(_parse_body(rest))
    return out


def _render_option(inner):
    """{{剧情选项|选项1=X|剧情1=...|选项2=Y|图标2=Z|...}} -> 选项列表。
    字段仅在括号深度 0 处切分，剧情分支内可嵌套折叠/选项。"""
    fields = {}
    order = []
    cur = None
    cur_val = []
    depth = 0
    for ln in inner.split("\n"):
        m = re.match(r"\|(选项\d+|剧情\d+|图标\d+)\s*=\s*(.*)$", ln)
        if m and depth == 0:
            if cur is not None:
                fields[cur] = "\n".join(cur_val).strip()
            cur = m.group(1)
            order.append(cur)
            cur_val = [m.group(2)]
        else:
            cur_val.append(ln)
        depth += ln.count("{{") - ln.count("}}")
    if cur is not None:
        fields[cur] = "\n".join(cur_val).strip()

    opts = {k: clean_inline(v) for k, v in fields.items() if k.startswith("选项")}
    plots = {k: v for k, v in fields.items() if k.startswith("剧情")}
    out = []
    for k in sorted(opts):
        n = k.replace("选项", "")
        out.append(f"- **〔选项〕** {opts[k]}")
        pk = "剧情" + n
        if pk in plots and plots[pk].strip():
            for pl in _parse_body(plots[pk]):
                if pl.strip():  # 分支内容整体挂在选项下，跳空行避免缩进被误判
                    out.append("    " + pl)
    return out


def _render_fold(inner):
    """{{折叠|标题=...|内容=...|折叠=...}} -> 标题 + 内容行（内容可嵌套块级模板）。"""
    title = ""
    mt = re.search(r"\|标题\s*=\s*", inner)
    if mt:
        ts = mt.end()
        te = ts
        while te < len(inner) and inner[te] not in "|\n":
            te += 1
        title = clean_inline(inner[ts:te].strip())
    content = ""
    mc = re.search(r"\|内容\s*=\s*", inner)
    if mc:
        cs = mc.end()
        ce = cs
        depth = 0
        while ce < len(inner):
            if inner.startswith("{{", ce):
                depth += 1
                ce += 2
            elif inner.startswith("}}", ce):
                depth -= 1
                ce += 2
            elif depth == 0 and inner[ce] == "|":
                break  # 深度 0 的下一个字段（如 |折叠=）
            else:
                ce += 1
        content = inner[cs:ce]
    out = []
    if title:
        out.append(f"**〔{title}〕**")
    if content.strip():
        if title:
            out.append("")
        rendered = _parse_body(content)
        if re.search(r"<(?:center|div)\b", content):
            out.extend(_quote_lines(rendered))
            out.append("")
        else:
            out.extend(rendered)
    return out


def _quote_lines(lines):
    """渲染引用块：每行独立成段（行间插一行 `>`），否则 Markdown 会把它们并成同一段。"""
    out = []
    for ln in lines:
        if not ln.strip():
            continue
        if out:
            out.append(">")
        out.append("> " + ln.strip())
    return out


def split_top(inner, sep="|"):
    """按括号深度 0 的位置切分模板参数，避免把嵌套模板（{{黑幕|…}}）内部的 | 当分隔符。"""
    parts = []
    cur = []
    depth = 0
    i = 0
    n = len(inner)
    while i < n:
        if inner.startswith("{{", i):
            depth += 1
            cur.append("{{")
            i += 2
        elif inner.startswith("}}", i):
            depth = max(0, depth - 1)
            cur.append("}}")
            i += 2
        elif depth == 0 and inner[i] == sep:
            parts.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(inner[i])
            i += 1
    parts.append("".join(cur))
    return parts


def _render_scene(inner):
    """{{任务描述|描述|场景名}} -> 场景行。"""
    parts = [p for p in split_top(inner) if p.strip()]
    if len(parts) >= 3:
        desc = clean_inline(parts[-2]).replace("\n", " ").strip()
        scene = clean_inline(parts[-1]).strip()
        return f"**【{scene}】** {desc}"
    return clean_inline(inner)


def _render_hint(inner):
    """{{提示|颜色|宽度=100%|正文|标题}} -> 正文（剔除颜色/宽度参数，标题单独成行）。"""
    parts = [p.strip() for p in split_top(inner)]
    body = [p for p in parts[2:] if p and not p.startswith("宽度")]
    title = ""
    if len(body) >= 2:
        title = clean_inline(body[-1])
        body = body[:-1]
    text = clean_inline(" ".join(body))
    if title:
        text = f"**{title}**\n" + text
    return text


def _render_notice(inner):
    """{{提示消息|颜色|正文}} -> 正文。"""
    parts = [p.strip() for p in split_top(inner)]
    body = [p for p in parts[2:] if p]
    return clean_inline(" ".join(body))


_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")


def _line_kind(ln):
    """判定一行的 Markdown 块类型，用于决定是否需要在行间补空行。"""
    s = ln.strip()
    if s.startswith(">"):
        return "quote"
    if s in ("---", "***", "___"):
        return "hr"
    if s.startswith("#"):
        return "heading"
    if _LIST_RE.match(ln):
        return "list"
    return "para"


def _normalize(lines):
    """保证不同类型的块之间有空行：Markdown 里单换行会被合并成同一段，
    只有同为「列表」或同为「引用块」的相邻行才可以紧贴其它情况下每行独立成段。"""
    out = []
    for ln in lines:
        if not ln.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        if out and out[-1] != "":
            prev = _line_kind(out[-1])
            cur = _line_kind(ln)
            if not (prev == cur and cur in ("list", "quote")):
                out.append("")
        out.append(ln)
    while out and out[-1] == "":
        out.pop()
    return out


def render_task(task, meta, plot):
    ver = meta.get("所属版本", task["ver"]) or task["ver"]
    chap = meta.get("系列任务", task["chapter"]) or task["chapter"]
    title = f"## {task['name']}（{ver} · {chap}）"
    out = [title, ""]
    if meta.get("任务描述"):
        out += [f"**任务描述**：{meta['任务描述']}", ""]
    if meta.get("出场人物"):
        out += [f"**出场人物**：{meta['出场人物']}", ""]
    if meta.get("任务流程"):
        flow = " → ".join(x.strip("* ") for x in meta["任务流程"].split("\n") if x.strip())
        out += [f"**任务流程**：{flow}", ""]
    if meta.get("剧情梗概"):
        syn = meta["剧情梗概"]
        items = [x.strip("# ") for x in syn.split("\n") if x.strip()]
        out += ["**剧情梗概**", ""]
        for idx, it in enumerate(items, 1):
            out.append(f"{idx}. {it}")
        out.append("")
    if plot:
        out += ["**剧情内容**", ""]
        out += _normalize(plot)
        out.append("")
    return "\n".join(out)


def main():
    tasks = ask_tasks()
    print(f"发现 {len(tasks)} 个翁法罗斯开拓任务")

    by_ver = {}
    for t in tasks:
        by_ver.setdefault(t["ver"], []).append(t)

    os.makedirs(OUT, exist_ok=True)
    index = ["# 翁法罗斯剧情原文（wiki 全量）· 分卷索引", "",
             "来自 [崩坏：星穹铁道 BWIKI](https://wiki.biligame.com/sr/开拓任务)，",
             "含说话人、旁白、玩家选项、剧情梗概与任务描述，补全本地客户端文本缺的三样。", "",
             "| 版本 | 分卷 | 任务数 |", "|---|---|---|"]

    for ver in sorted(by_ver):
        vtasks = by_ver[ver]
        parts = []
        for t in vtasks:
            try:
                w = fetch_wikitext(t["name"])
                meta = parse_meta(w)
                plot = parse_plot(w)
                parts.append(render_task(t, meta, plot))
                print(f"  [{ver}] {t['name']} OK")
            except Exception as e:
                print(f"  [{ver}] {t['name']} 失败: {e}", file=sys.stderr)
            time.sleep(0.5)
        text = f"# 翁法罗斯 {ver} 剧情原文（wiki 全量）\n\n> 版本 {ver} · 共 {len(vtasks)} 个任务\n\n" + "\n\n---\n\n".join(parts) + "\n"
        open(os.path.join(OUT, f"amphoreus_{ver}.md"), "w", encoding="utf-8").write(text)
        index.append(f"| {ver} | amphoreus_{ver}.md | {len(vtasks)} |")
        print(f"已写入 amphoreus_{ver}.md（{len(vtasks)} 任务）")

    index += ["", "## 说明", "",
              "- 台词、说话人、旁白、选项、梗概均取自 wiki 原文（社区整理，非官方逐字），引用时以客户端文本表为准。",
              "- `〔选项〕` 为玩家可选对话；`（旁白）` 为场景叙述；`<梗概>` 为该步骤折叠梗概。"]
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write("\n".join(index) + "\n")
    print("完成 →", OUT)


if __name__ == "__main__":
    main()
