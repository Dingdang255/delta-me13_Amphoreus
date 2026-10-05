"""历法与阶段时刻（帧 → 时间）的刻度映射。

时间轴是纯渲染：它只【读】帧号。这里既查真实配置下的取值，也用假 ctx 精确地
验换算规则 —— 特别是这两件事：
  ① 世界内的历法（纪元 · 月 · 年）只属于**第四阶段**；
  ② 前三个阶段（因子演算）**还没有历法**，时间按【第 N 次循环】计量。

「世界内从哪一帧起」由 `myth_from` 传进来（`myth_phase_frame(traj)`）；假 ctx 用
`myth_from=0` 表示"打头就是世界内"，于是能单独验历法换算。
"""
from __future__ import annotations

import json
import os
import types
import unittest

from _support import ROOT  # noqa: F401  （把仓库根挂上 sys.path）

from engine.render import Renderer


def _fake(calendar, lexicon=None):
    """造一个只有 calendar / lexicon 的假 ctx —— 历法只读这两样（外加 myth_from）。"""
    return types.SimpleNamespace(
        calendar=calendar,
        lexicon=lexicon or {"epochs": {"E1": "甲纪元", "E2": "乙纪元"},
                            "months": {"M1": "一月", "M2": "二月"}},
    )


def _open(unit="光历", dpm=10, mpy=12, origin=1, keys=("M1", "M2")):
    """一个自打元年起就有历法的世界（单纪元）—— 年份/月份的换算基准。"""
    return {
        "unit": unit, "days_per_month": dpm, "months_per_year": mpy,
        "month_keys": list(keys),
        "eras": [{"until_frame": None, "lexicon_key": "E1",
                  "calendar": True, "origin": origin}],
    }


def _R(ctx, **kw):
    """默认按【世界内】解释（myth_from=0）—— 历法那些换算只在世界内才有。"""
    kw.setdefault("myth_from", 0)
    return Renderer(ctx, **kw)


class CalendarMapping(unittest.TestCase):
    def test_month_cycles_within_year(self):
        R = _R(_fake(_open(keys=["M1"] + ["M2"] * 11)))
        self.assertEqual(R.month(0), "一月")      # 第 1 月
        self.assertEqual(R.month(10), "二月")     # 第 2 月
        self.assertEqual(R.month(110), "二月")    # 第 12 月
        self.assertEqual(R.month(120), "一月")    # 翻年 → 回到第 1 月

    def test_year_from_frame_and_always_positive(self):
        """一年 = 月数 × 日数。年份由【帧】推出，且必须是正整数。"""
        R = _R(_fake(_open()))
        self.assertEqual(R.year(0), "光历1年")     # 元年 = 1，不是 0，更不是负
        self.assertEqual(R.year(119), "光历1年")   # 未满一年
        self.assertEqual(R.year(120), "光历2年")   # 满 120 帧 = 一年
        for f in range(0, 5000, 37):
            self.assertGreaterEqual(int(R.year(f)[2:-1]), 1, f)

    def test_origin_sets_the_first_year(self):
        R = _R(_fake(_open(origin=5)))
        self.assertEqual(R.year(0), "光历5年")

    def test_epoch_without_calendar_has_no_year_or_month(self):
        """`calendar: false` 的纪元【还没有历法】—— 只渲染纪元名，不写月与年。"""
        R = _R(_fake({
            "unit": "光历", "days_per_month": 10, "months_per_year": 12,
            "month_keys": ["M1", "M2"],
            "eras": [{"until_frame": 4, "lexicon_key": "E1", "calendar": False},
                     {"until_frame": None, "lexicon_key": "E2",
                      "calendar": True, "origin": 1}],
        }))
        self.assertEqual(R.epoch(0), "甲纪元")
        self.assertEqual(R.year(0), "")
        self.assertEqual(R.month(0), "")
        self.assertEqual(R.locale(0), "甲纪元")            # 只有纪元名
        self.assertEqual(R.epoch(5), "乙纪元")             # 边界：第 5 帧起换纪元
        self.assertEqual(R.year(5), "光历1年")             # 新纪元自元年起算
        self.assertEqual(R.month(5), "一月")

    def test_era_without_name_renders_nothing(self):
        """纪元允许【没有名字】（真实配置里"演算期"那一段就是）—— 不写纪元、不崩。"""
        R = _R(_fake({"unit": "光历", "days_per_month": 10, "months_per_year": 12,
                      "month_keys": ["M1"],
                      "eras": [{"until_frame": 9, "calendar": False},
                               {"until_frame": None, "lexicon_key": "E2",
                                "calendar": True, "origin": 1}]}))
        self.assertEqual(R.epoch(0), "")
        self.assertEqual(R.locale(9), "")
        self.assertEqual(R.epoch(10), "乙纪元")

    def test_no_month_keys_falls_back(self):
        """没给 month_keys 的配置不该崩，也不该硬塞一个月份进去。"""
        R = _R(_fake({"unit": "光历", "days_per_month": 10, "months_per_year": 12,
                      "eras": [{"until_frame": None, "lexicon_key": "E1",
                                "calendar": True, "origin": 1}]}))
        self.assertEqual(R.month(12345), "")
        self.assertIn("年", R.locale(12345))
        self.assertEqual(R.locale(0), "甲纪元·光历1年")


class PhaseClock(unittest.TestCase):
    """前三个阶段没有世界内历法 —— 时间按【第 N 次循环】计量（wiki 口径）。"""

    def _lex(self):
        return {
            "terms": {}, "months": {"M1": "一月"}, "epochs": {"E1": "甲纪元"},
            "chronicle": {"cycle_label": "第 {n} 次循环"},
            "phase_terms": {"sim": {"chronicle": {"cycle_label": "第 {n} 次循环"}}},
        }

    def _cal(self):
        return {"unit": "光历", "days_per_month": 10, "months_per_year": 12,
                "month_keys": ["M1"],
                "eras": [{"until_frame": 99, "calendar": False},
                         {"until_frame": None, "lexicon_key": "E1",
                          "calendar": True, "origin": 1}]}

    def test_sim_phase_counts_cycles(self):
        # 世界内从 100 帧起；换代帧 = 10 / 40
        R = Renderer(_fake(self._cal(), self._lex()), cycles=[10, 40], myth_from=100)
        self.assertEqual(R.phase_of(0), "sim")
        self.assertEqual(R.phase_of(100), "myth")
        self.assertEqual(R.locale(0), "第 1 次循环")      # 还没换代 ⇒ 第 1 次
        self.assertEqual(R.locale(10), "第 1 次循环")     # 换代那一帧仍算本轮
        self.assertEqual(R.locale(11), "第 2 次循环")
        self.assertEqual(R.locale(99), "第 3 次循环")
        self.assertEqual(R.locale(100), "甲纪元·一月·光历1年")   # 迈进世界内 ⇒ 换用历法

    def test_not_reached_means_always_sim(self):
        """没走到第四阶段（含没配阶段的世界）⇒ 整段都按演算期讲，不贴世界内的词。"""
        R = Renderer(_fake(self._cal(), self._lex()))
        self.assertEqual(R.phase_of(10 ** 9), "sim")
        self.assertEqual(R.locale(10 ** 9), "第 1 次循环")


class CalendarReuse(unittest.TestCase):
    """沿参考轨道复用的帧不算历法时间（那时是同一段时间在轮回）。"""

    def test_closed_span_freezes_the_calendar(self):
        plain = _R(_fake(_open(origin=1)))
        frozen = _R(_fake(_open(origin=1)), spans=[("deadlock", 5, 1000)])
        self.assertEqual(plain.year(1000), "光历9年")      # 不扣复用 ⇒ 900 帧 ≈ 7 年
        self.assertEqual(frozen.year(1000), "光历1年")     # 复用区里历法停在入区前
        self.assertEqual(frozen.year(1120), "光历2年")     # 走出复用即续上（不回溯）

    def test_open_span_is_replaced_when_closed(self):
        """实时路径：先 `add_reuse(start)`，走出时再补 end —— 同一段只算一遍。"""
        R = _R(_fake(_open(origin=1)))
        R.add_reuse(5)
        self.assertEqual(R.year(1000), "光历1年")
        R.add_reuse(5, 1000)                               # 补 end：换掉那条开区间
        self.assertEqual(R.year(1000), "光历1年")          # 没有被算两遍
        self.assertEqual(R.year(1120), "光历2年")


class CalendarRealConfig(unittest.TestCase):
    """真实 config/calendar.json 与 data/genesis.json。"""

    @classmethod
    def setUpClass(cls):
        from engine.loader import Config
        cls.ctx = Config(ROOT)
        with open(os.path.join(ROOT, "config", "calendar.json"),
                  encoding="utf-8") as f:
            cls.cal = json.load(f)
        with open(os.path.join(ROOT, "data", "genesis.json"),
                  encoding="utf-8") as f:
            cls.gen = json.load(f)
        cls.myth_from = cls._last_stage_boundary()

    @classmethod
    def _last_stage_boundary(cls):
        """阶段④（人类古典文明）的起始帧：各档 dwell 的累计 − 2。"""
        cum = 0
        for prof in cls.gen["domain"]["stages"][:-1]:
            cum += int((prof.get("params") or {})["domain_dwell"])
        return cum - 2 + 1

    def R(self, **kw):
        kw.setdefault("myth_from", self.myth_from)
        return Renderer(self.ctx, **kw)

    def test_all_twelve_months_resolvable(self):
        cal = self.ctx.calendar
        dpm, mpy = cal["days_per_month"], cal["months_per_year"]
        self.assertEqual(mpy, 12)
        self.assertEqual(len(cal["month_keys"]), mpy)
        R = self.R()
        base = self.myth_from + 7000                      # 取世界内的一段
        seen = {R.month(base + i * dpm) for i in range(mpy)}
        self.assertEqual(len(seen), mpy)                  # 十二个月各不同
        self.assertNotIn("MONTH_", "".join(seen))         # 没有漏查表的键

    def test_world_calendar_belongs_to_the_fourth_stage(self):
        """世界内的历法（纪元 · 月 · 年）只属于第四阶段；前三阶段报【第 N 次循环】。

        据 wiki：十二因子以无机/有机/人类为初始变量跑了三个阶段（biligame「进行的
        第 1 至 50121 次循环」），到第四阶段背景才设为人类古典文明、才有翁法罗斯的
        历史与光历（moegirl 第 47 行；光历由刻法勒在黄金世测定）。
        """
        eras = self.cal["eras"]
        self.assertFalse(eras[0]["calendar"])             # 演算期：没有历法
        self.assertNotIn("lexicon_key", eras[0])          # 且【连纪元名都没有】
        self.assertTrue(eras[-1]["calendar"])             # 世界内：有历法
        self.assertEqual(eras[-1]["lexicon_key"], "ERA_FADING")
        self.assertEqual(eras[-1]["origin"], 1)           # 元年取 1 ⇒ 年份恒正

        R = self.R()
        self.assertEqual(R.phase_of(0), "sim")
        self.assertNotIn("年", R.locale(0))               # 演算期不写年份
        self.assertEqual(R.epoch(0), "")                  # 也不写纪元名
        self.assertIn("循环", R.locale(0))                # 只报循环次数
        self.assertEqual(R.locale(self.myth_from).split("·")[-1], "光历1年")

    def test_year_never_negative_across_the_run(self):
        """年份恒为正整数 —— 过去那套 `origin_offset` 会让前期整段变成负年。"""
        R = self.R()
        for f in range(0, 60000, 101):
            y = R.year(f)
            if y:
                self.assertGreaterEqual(int(y[2:-1]), 1, f)

    def test_myth_era_starts_at_the_last_stage_boundary(self):
        """有历法的纪元必须起于阶段④ —— 与 genesis 的最后一道档界对齐。

        档界 = 各档 `domain_dwell` 的累计 − 2（第一档从第 0 帧起算，故实际覆盖
        dwell−1 / dwell / dwell 帧）。改 `domain.stages` 的 dwell 就会红 —— 这正是
        「改轨道配置后必须重跑核对」的一个落点。
        """
        got = [int(e["until_frame"]) for e in self.cal["eras"]
               if e.get("until_frame") is not None]
        self.assertEqual(got, [self.myth_from - 1])


if __name__ == "__main__":
    unittest.main()
