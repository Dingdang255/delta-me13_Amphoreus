"""导出的看板 HTML 必须是配置的镜像（**静态**检查，不开浏览器）。

`dashboard/翁法罗斯-可视化.html` 是【生成】的 —— 由 `python run.py --preset plot --export`。
它把「十二席的职位 / 称号 / 城邦」连同一次演算的结果一起塞进页面里。其中职位、称号、城邦
**来自配置**（`phonology.title_calibration` / `lexicon.regions` / `lexicon.cities`）：
改了配置却忘了重导，页面就会拿旧词表讲故事 —— 例如把某席的城邦一直显示成已经删掉的旧值。

这里只做**静态**比对：正则抠出 `#viz-data` 里那份 JSON，再读一遍预渲染的席位卡，
与 `config/` 逐项对照。不启动浏览器、不跑演算、秒级完成。

浏览器级检查（点选、回放、颜色、控制台报错）只在**改渲染层**或**用户报告了显示问题**时
才做，不进日常回归 —— 静态检查能覆盖的，就不再去开浏览器。
"""
from __future__ import annotations

import html as _html
import io
import json
import os
import re
import unittest

from _support import ROOT

DASH = os.path.join(ROOT, "dashboard", "翁法罗斯-可视化.html")


def _load(*parts):
    with io.open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def _blob(text):
    """抠出内联数据。blob 里 `</` 被生成时转义成 `<\\/`（防提前闭合），JSON 原生支持。"""
    m = re.search(r'<script type="application/json" id="viz-data">(.*?)</script>',
                  text, re.S)
    if m is None:
        raise AssertionError("看板里找不到 #viz-data —— 页面结构变了？")
    return json.loads(m.group(1))


def _seat_cards(text):
    """预渲染的十二席卡：{位次: {"duty":…, "region":…, "city":…}}。"""
    box = re.search(r'<div class="seats" id="seats">(.*?)</div>\s*<h2>指标曲线',
                    text, re.S)
    if box is None:
        raise AssertionError("看板里找不到席位卡区块 —— 页面结构变了？")
    out = {}
    for m in re.finditer(r'<div class="seat[^"]*"[^>]*data-id="(L\d\d)"[^>]*>(.*?)'
                         r'<div class="seat-name">', box.group(1), re.S):
        lid, body = m.group(1), m.group(2)

        def cell(name):
            # 职位是 <span>，称号 / 城邦是 <div> —— 两种都收。
            hit = re.search(r'<(?:div|span) class="seat-%s">(.*?)</(?:div|span)>' % name,
                            body, re.S)
            # 城邦格里可能带一个配色圆点（<i class="citydot …"></i>），剥掉。
            return _html.unescape(re.sub(r"<i[^>]*></i>", "", hit.group(1))) \
                if hit else None

        out[lid] = {"duty": cell("duty"), "region": cell("region"),
                    "city": cell("city")}
    return out


def _city_legend(text):
    """城邦图例里的城邦名（按渲染顺序）。"""
    m = re.search(r'<div class="citylegend">(.*?)</div>', text, re.S)
    if m is None:
        return []
    return [p for p in re.findall(r'<span class="lgd">.*?</i>(.*?)</span>',
                                  m.group(1), re.S)]


@unittest.skipUnless(os.path.exists(DASH),
                     "还没有导出的看板；先跑 python run.py --preset plot --export")
class DashboardMatchesConfig(unittest.TestCase):
    """只比对【来自配置】的那几项，不碰一次演算的结果（帧号 / 人名 / 事件）。"""

    @classmethod
    def setUpClass(cls):
        with io.open(DASH, encoding="utf-8") as f:
            cls.text = f.read()
        cls.blob = _blob(cls.text)
        cls.loci = _load("config", "loci.json")["loci"]
        cls.lex = _load("config", "lexicon.json")
        cls.ph = _load("config", "phonology.json")
        # 预设的 lexicon.json 只覆盖 terms / capabilities / deadlock 模板，
        # 不动 regions 与 cities —— 故直接拿基础配置比对是安全的。
        cls.cities = [cls.lex.get("cities", {}).get(l["id"], "") for l in cls.loci]
        cls.regions = [cls.lex.get("regions", {}).get(l["id"], "") for l in cls.loci]
        cal = cls.ph.get("title_calibration", {})
        cls.duties = [cal.get(l["id"], ["", l["id"]])[1] or l["id"] for l in cls.loci]
        # 阶段目录：名字取 domains + terms.domain_exhausted，结论取 stage_conclusions
        cls.gen = _load("presets", "_default", "genesis.json")
        dom = cls.lex.get("domains") or {}
        terms = cls.lex.get("terms") or {}
        variables = (cls.gen.get("domain") or {}).get("initial_variable") or []
        cls.stage_profiles = (cls.gen.get("domain") or {}).get("stages") or []
        cls.stage_names = ([dom.get(v, v) for v in variables]
                           + [terms.get("domain_exhausted", "—")])
        cls.stage_conc = cls.lex.get("stage_conclusions") or []

    # ---- 内联数据（回放换人时不变的那几列） ------------------------------------

    def test_duties_match_phonology(self):
        self.assertEqual(self.blob["duties"], self.duties)

    def test_regions_match_lexicon(self):
        self.assertEqual(self.blob["regions"], self.regions)

    def test_cities_match_lexicon(self):
        self.assertEqual(self.blob["cities"], self.cities)

    def test_city_legend_index_is_consistent(self):
        """配色编号按城邦名字典序给定 —— 与席位卡上的圆点必须同一套。"""
        names = sorted({c for c in self.cities if c})
        self.assertEqual(self.blob["citynames"], names)
        self.assertEqual(self.blob["cityidx"],
                         [names.index(c) if c else -1 for c in self.cities])

    def test_no_city_outside_the_lexicon(self):
        """页面里出现的城邦，只准是词表里登记过的那几个。"""
        self.assertLessEqual(set(self.blob["citynames"]),
                             set(self.lex.get("cities", {}).values()))

    # ---- 预渲染的席位卡（用户真正看见的那一排） --------------------------------

    def test_prefilled_seat_cards_match_config(self):
        cards = _seat_cards(self.text)
        self.assertEqual(sorted(cards), [f"L{i:02d}" for i in range(len(self.loci))],
                         "席位卡不是十二张 —— 页面结构变了？")
        for i, lid in enumerate(f"L{i:02d}" for i in range(len(self.loci))):
            c = cards[lid]
            self.assertEqual(c["duty"], self.duties[i], f"{lid} 职位与配置不符")
            self.assertEqual(c["region"], self.regions[i], f"{lid} 称号与配置不符")
            self.assertEqual(c["city"], self.cities[i] or "—",
                             f"{lid} 城邦与配置不符（改了 lexicon.cities 要重导看板）")

    def test_city_legend_matches_config(self):
        want = sorted({c for c in self.cities if c})
        self.assertEqual(_city_legend(self.text), want,
                         "城邦图例与配置不符 —— 改了 lexicon.cities 要重导看板")

    # ---- 阶段目录（阶段卡 + 时间线上的阶段带） ---------------------------------

    def test_stage_rows_match_config(self):
        """档数 = `genesis.domain.stages`；名字取自 domains / terms.domain_exhausted；
        结论逐条取 `lexicon.stage_conclusions`。"""
        rows = self.blob["stages"]
        self.assertEqual(len(rows), len(self.stage_profiles),
                         "阶段目录的档数与 genesis.domain.stages 不符")
        for i, row in enumerate(rows):
            self.assertEqual(row["name"], self.stage_names[i],
                             f"第 {i + 1} 档名字与词表不符")
            if i < len(self.stage_conc):
                self.assertEqual(row["conclusion"], self.stage_conc[i],
                                 f"第 {i + 1} 档结论与词表不符")

    def test_stage_ranges_are_contiguous_and_cover_the_run(self):
        """阶段带必须是连续的帧区间，且末档收到「走到帧」—— 否则带子会开天窗。"""
        rows = self.blob["stages"]
        self.assertEqual(rows[0]["start"], 0)
        for a, b in zip(rows, rows[1:]):
            self.assertEqual(b["start"], a["end"] + 1, "阶段区间不连续")
        self.assertEqual(rows[-1]["end"], max(s[0] for s in self.blob["samples"]))

    def test_stage_cards_are_rendered(self):
        """每档都要有一张阶段卡（名字与结论都要落进 HTML）。"""
        # 卡片还带 `data-start`（可点跳帧），故只认 class 前缀 + 空白/收尾
        self.assertEqual(len(re.findall(r'<div class="stage"[\s>]', self.text)),
                         len(self.blob["stages"]))
        for name in self.stage_names:
            self.assertIn(name, self.text)


if __name__ == "__main__":
    unittest.main()
