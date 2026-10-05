"""可视化层（A2/A3/A4/A6/A7）＋ 只读红线。

三条要求：
  ① 单文件 HTML 真的把四块内容产出来了（十二席 / 指标曲线 / 时间线轴 / 编年史）；
  ② 交互层（A6）所需的数据与控件都在页面里，且仍是自包含、零外链；
  ③ 可视化层【只读】—— 挂上采样器与不挂，演算逐帧一致（与 LiveStream 同性质）。
"""
from __future__ import annotations

import json
import re
import unittest

from _support import ROOT, load

from engine.viz import Sampler, build_html, build_live_shell, summary_cards

SAMPLE_LINES = [
    (1, "第一行", None, 0),
    (100, "第二行 <不该被当成标签>", "（同类 ×3 · 至帧 300）", 1),
    (200, "恶意 </script><script>alert(1)</script>", None, 2),
]


class VizHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sampler = Sampler(600)
        # 2,500 帧：够撞上 1,200 的外生扰动与 1,999 的初始变量域推进。
        # （原先跑 600 帧也够 —— 那时「世代更迭」是常开机制、第 9 帧就打了一个点；
        #  如今它是【阶段三才装配】的，前两档本来就没有世代更迭。）
        cls.ctx, cls.data, cls.traj = load("plot", frames=2500, watch=cls.sampler)
        cls.html = build_html(cls.ctx, cls.traj, cls.sampler.points,
                              lines=SAMPLE_LINES, title="测试用 dashboard")

    def test_has_all_four_blocks(self):
        for marker in ("十二席状态", "指标曲线", "事件时间线", "编年史"):
            self.assertIn(marker, self.html)

    def test_seats_cover_every_locus(self):
        for locus in self.ctx.loci:
            self.assertIn(locus.id, self.html)
        self.assertIn("证伪进度", self.html)

    def test_stage_cards_and_seat_tooltips_are_wired(self):
        """阶段卡带 `data-start`（可点跳帧）；席位卡带 `data-machine`（悬浮报电信号序列）。"""
        blob = self._blob()
        self.assertEqual(len(blob["machines"]), len(blob["seatnames"]))
        self.assertTrue(any(blob["machines"]), "席位卡该带得出机器编号")
        self.assertIn("data-machine=", self.html)        # 席位卡悬浮
        self.assertIn('id="seattip"', self.html)         # 那张跟随鼠标的小卡
        # 外部变量（预设标了 `external`，含那个由「记忆」承载的席位）⇒ 报 `?`；空席不报
        from engine.viz import _machine_of

        ext = next(int(str(a["key"]).split(":", 1)[1])
                   for a in self.data.anchors if a.get("external"))
        self.assertEqual(_machine_of(self.traj, {}, ext), "?")
        self.assertEqual(_machine_of(self.traj, {}, None), "")
        # 阶段卡要带 `data`（`stage_table` 需要 genesis 的 stages）才摆得出来
        with_stages = build_html(self.ctx, self.traj, self.sampler.points,
                                 lines=SAMPLE_LINES, title="x", data=self.data)
        self.assertIn("data-start=", with_stages)
        self.assertIn("点击跳到这一档开始的帧", with_stages)

    def test_sim_phase_page_lays_out_no_places(self):
        """城邦 / 称号只属于第四阶段 —— 演算期不摆图例、也不摆那两行。

        城邦名仍在数据块里（回放跨过 `mythfrom` 时由前端就地显形），只是不当常驻内容。
        注意：页内嵌的 JS 里当然还留着这两行的模板（回放要用），故这里查的是
        `_seats_html` 的**预渲染结果**，不是整页字符串。
        """
        from engine.viz import _machine_map, _name_map, _seat_cards, _seats_html

        cities = set((self.ctx.lexicon.get("cities") or {}).values())
        self.assertTrue(cities, "词表里应当有 cities")
        cards = _seat_cards(self.ctx, self.traj, _name_map(self.traj),
                            _machine_map(self.traj))
        sim = _seats_html(cards, 1.0, show_places=False)
        self.assertNotIn('class="seat-city"', sim)
        self.assertNotIn('class="seat-region"', sim)
        self.assertNotIn('class="citylegend"', sim)
        myth = _seats_html(cards, 1.0, show_places=True)
        self.assertIn('class="seat-city"', myth)
        self.assertIn('class="citylegend"', myth)
        blob = self._blob()
        self.assertEqual(len(blob["cities"]), len(self.ctx.loci))
        self.assertEqual(sorted(blob["citynames"]), sorted(cities))

    def test_cities_are_rendered_with_legend_and_colors(self):
        """城邦（B4）：进了第四阶段，席位卡带城邦名与配色圆点，出现过的城邦有图例。"""
        ctx, _data, traj = load("plot", frames=12000)
        html_text = build_html(ctx, traj, None, lines=[], title="测试用 dashboard")
        for name in set((ctx.lexicon.get("cities") or {}).values()):
            self.assertIn(name, html_text)                  # 城邦名进了页面
        self.assertIn('class="citylegend"', html_text)      # 图例
        self.assertIn('class="seat-city"', html_text)       # 席位卡那一行
        self.assertIn('class="citydot k0"', html_text)      # 配色圆点
        # 「没有考据的席位」显示破折号，且不画点
        self.assertIn("—", html_text)

    def test_is_self_contained(self):
        """单文件、零外部依赖：不许外链脚本/样式/字体，也不许联网取图。"""
        low = self.html.lower()
        self.assertNotIn("<link", low)
        self.assertNotIn("script src", low)
        self.assertNotIn("http://", low)
        self.assertNotIn("https://", low)
        self.assertIn("<svg", self.html)

    def test_html_is_escaped(self):
        html = build_html(self.ctx, self.traj, None,
                          title="<b>不该被当成标签</b>")
        self.assertNotIn("<b>不该被当成标签</b>", html)
        self.assertIn("&lt;b&gt;", html)

    def test_html_is_escaped_in_chronicle_rows(self):
        """编年史走 JS 渲染：文本以【数据】形态进 JSON，不由服务端拼成 HTML。"""
        blob = self._blob()
        rows = [r for r in blob["lines"] if r[1] == "第二行 <不该被当成标签>"]
        self.assertEqual(len(rows), 1)                  # 原样是数据，不是标签
        # 静态 HTML 里不该有预渲染的编年史行 —— 结构全在 JS 里建，注入面为零。
        self.assertNotIn('<li class="ln"', self.html)

    def test_script_tag_in_data_cannot_break_out(self):
        """编年史里混进 `</script>` 也不许把数据块提前闭合 —— `</` 一律转义。"""
        self.assertNotIn("</script><script>alert(1)", self.html)
        self.assertIn("<\\/script>", self.html)
        blob = self._blob()
        self.assertTrue(any("</script>" in r[1] for r in blob["lines"]))

    def test_no_points_still_renders(self):
        """没有采样数据（比如没走 --export 那条路）也要能出页面，不能崩。"""
        html = build_html(self.ctx, self.traj, None)
        self.assertIn("十二席状态", html)

    def test_interactive_controls_present(self):
        """A6：过滤框 / 跳帧输入 / 定位与清除按钮 / 悬停读数框 / 缩放按钮 / 回放台。"""
        for marker in ('id="q"', 'id="jf"', 'id="jump"', 'id="clear"',
                       'id="chron"', 'id="near"', 'id="win"',
                       'id="z-in"', 'id="z-out"', 'id="z-reset"',
                       'id="play"', 'id="rewind"', 'id="prev"', 'id="next"',
                       'id="toend"', 'id="scrub"', 'id="speed"',
                       'id="listmode"', 'id="evlist"'):
            self.assertIn(marker, self.html)

    def test_playback_buttons_are_unambiguous(self):
        """五颗按钮语义写清：回到开始 / 前一帧 / 播放 / 后一帧 / 跳到末尾。"""
        for label in ("回到开始", "前一帧", "播放", "后一帧", "跳到末尾"):
            self.assertIn(label, self.html)
        body = self.html.split('<script type="application/json"')[0]
        self.assertEqual(body.count('id="prev"'), 1)
        self.assertEqual(body.count('id="next"'), 1)
        self.assertEqual(body.count('id="toend"'), 1)

    def test_zoom_binds_to_stable_containers(self):
        """拖动必须绑在【重绘不会替换】的容器上，否则拖动一帧就断。"""
        self.assertIn("function bindZoom(box)", self.html)
        self.assertIn("box.__zoomBound", self.html)
        self.assertIn("bindZoom($('cv1'))", self.html)
        self.assertIn("bindZoom($('tl-box'))", self.html)
        # 滑块按对数帧比例走（与横轴一致），不再按采样下标。
        self.assertIn("tOfFrame", self.html)
        self.assertIn("nearestIndex(frameOfT(", self.html)

    def test_tooltip_lives_inside_each_chart_box(self):
        """读数框必须是【图表框自己的】子元素（.chart-box 是 relative），
        否则它会被定位到整个页面上，悬停时根本看不见。"""
        self.assertEqual(self.html.count('<div class="chart-box"><div class="tip"></div>'), 2)

    def test_seat_cards_carry_names_for_filtering(self):
        """点席位卡要能按人过滤 —— 故每张卡都得带 data-name（只数服务端渲染的那部分）。"""
        body = self.html.split('<script type="application/json"')[0]
        self.assertEqual(body.count('data-name="'), len(self.ctx.loci))

    def test_seat_pick_can_be_cancelled(self):
        """点空白处要能取消席位选中（并把那次过滤一并撤掉）。"""
        self.assertIn('function clearPicked()', self.html)
        self.assertIn("closest('.toolbar')", self.html)   # 工具栏内不算「点别处」
        self.assertIn("classList.add('picked')", self.html)

    def test_is_readonly_layer_static(self):
        """静态页面里 live 标志为 false —— 轮询那套虽在，但不会被触发。"""
        self.assertIn('"live":false', self.html)
        self.assertIn('if (live) poll();', self.html)

    def test_summary_cards_shared(self):
        """顶部摘要卡与静态导出口径一致（实时看板演完替换的是同一份）。"""
        cards = summary_cards(self.ctx, self.traj, self.data.genesis)
        keys = [k for k, _v, _m in cards]
        self.assertEqual(keys[0], "命题")
        # 「命题」是【提问】（取自 genesis），「结论」才是【回答】—— 两者不再混为一谈
        self.assertEqual(keys[1], "结论")
        self.assertIn("结论编号", keys)
        prop = dict((k, v) for k, v, _m in cards)["命题"]
        self.assertIn(self.data.genesis["proposition"]["note"], prop)
        self.assertNotEqual(prop, dict((k, v) for k, v, _m in cards)["结论"])
        for k, v, _m in cards:
            self.assertIsInstance(v, str) and self.assertTrue(v)
            self.assertIn(k, self.html)
        # 结论编号（英文 id）在页面里以等宽字体呈现，长串也不再溢出卡片。
        self.assertIn('<div class="v mono">', self.html)

    # ---- 嵌在页面里的那份数据 -------------------------------------------------
    def _blob(self):
        m = re.search(r'<script type="application/json" id="viz-data">(.*?)</script>',
                      self.html, re.S)
        self.assertIsNotNone(m, "页面里没有 viz-data 数据块")
        return json.loads(m.group(1).replace("<\\/", "</"))

    def test_data_blob_shape(self):
        blob = self._blob()
        self.assertEqual(blob["geo"]["w"] > 0, True)
        self.assertEqual(blob["total"], self.traj.reached_frame)
        self.assertEqual(len(blob["labels"]), 6)
        # 采样序列以【真终局】收尾：至少覆盖全部采样点，且末点是最后一帧。
        self.assertGreaterEqual(len(blob["samples"]), len(self.sampler.points))
        self.assertEqual(blob["samples"][-1][0], self.traj.reached_frame)
        self.assertEqual(len(blob["lines"]), len(SAMPLE_LINES))
        self.assertTrue(blob["marks"])                  # 时间线事件供「最接近的事件」
        # 行与打点各多带一个【事件号】(末位)：双击节点靠它精确回跳，而非同帧取第一条。
        self.assertTrue(all(len(r) == 4 for r in blob["lines"]))
        self.assertTrue(all(len(m) == 5 for m in blob["marks"]))
        self.assertEqual(len(blob["duties"]), len(self.ctx.loci))
        self.assertEqual(len(blob["regions"]), len(self.ctx.loci))
        # 换代刻度：用【真实记录】给出（不从采样序列推断），每条是 [帧, 轮次]
        self.assertIsInstance(blob["promos"], list)
        self.assertTrue(all(len(p) == 2 for p in blob["promos"]))

    def test_data_blob_matches_samples(self):
        blob = self._blob()
        first, sample = blob["samples"][0], self.sampler.points[0]
        self.assertEqual(first[0], sample[0])
        self.assertEqual(first[1:6], [sample[1], sample[2], sample[3], sample[4], sample[5]])
        self.assertEqual(len(first), 7)                 # 5 个读数 + 席位下标数组
        self.assertEqual(len(first[6]), len(self.ctx.loci))


class VizLiveShell(unittest.TestCase):
    """实时看板（--serve）的空壳：一切数据由页面自己向 state 取。"""

    @classmethod
    def setUpClass(cls):
        ctx, _data, traj = load("plot", frames=300)
        cls.ctx = ctx
        cls.html = build_live_shell(ctx, 300, title="实时测试看板")

    def test_is_live_and_empty(self):
        self.assertIn('"live":true', self.html)
        blob = json.loads(re.search(
            r'<script type="application/json" id="viz-data">(.*?)</script>',
            self.html, re.S).group(1).replace("<\\/", "</"))
        self.assertEqual(blob["samples"], [])
        self.assertEqual(blob["lines"], [])
        self.assertTrue(blob["live"])
        self.assertTrue(blob["autoreload"])          # 默认：演完自动重载成完整页
        self.assertIn('id="done-toast"', self.html)  # 关掉自动重载时用的右下角提示

    def test_no_serve_reload_bakes_the_flag(self):
        """`--no-serve-reload` 把 autoreload=false 烙进数据块（页面据此改弹提示、不重载）。"""
        html = build_live_shell(self.ctx, 300, title="x", autoreload=False)
        blob = json.loads(re.search(
            r'<script type="application/json" id="viz-data">(.*?)</script>',
            html, re.S).group(1).replace("<\\/", "</"))
        self.assertFalse(blob["autoreload"])

    def test_polls_state_endpoint(self):
        self.assertIn("fetch('state?", self.html)
        self.assertIn("id=\"liveflag\"", self.html)

    def test_make_watch_is_readonly(self):
        """实时旁路也必须只读：挂了它，演算逐帧不变。"""
        from engine.live import LiveState, make_watch

        _c0, _d0, plain = load("plot", frames=600)
        board = LiveState()
        sampler = Sampler(600)
        _c1, _d1, watched = load("plot", frames=600,
                                 watch=make_watch(board, sampler))
        self.assertEqual(plain.final.digest(), watched.final.digest())
        self.assertEqual(plain.reached_frame, watched.reached_frame)
        self.assertTrue(board.samples)                  # 数据真的流进来了
        self.assertTrue(board.seatnames)
        self.assertTrue(board.machines)                 # 机器编号表跟着一起长
        self.assertEqual(len(board.machines), len(board.seatnames))
        self.assertGreater(board.frame, 0)


class VizIsReadOnly(unittest.TestCase):
    """红线 3：可视化层不得反向写状态 —— 挂了采样器，演算必须逐帧不变。"""

    def test_sampler_does_not_change_trajectory(self):
        ctx_a, data_a, plain = load("plot", frames=600)
        ctx_b, data_b, watched = load("plot", frames=600, watch=Sampler(600))

        self.assertEqual(plain.iterations, watched.iterations)
        self.assertEqual(plain.reached_frame, watched.reached_frame)
        self.assertEqual(plain.verdict, watched.verdict)
        self.assertEqual(plain.final.digest(), watched.final.digest())
        self.assertTrue(watched.records)

    def test_chronicle_rows_do_not_touch_state(self):
        """编年史行是从 Telemetry 事后翻译出来的：翻译两遍，状态摘要不变。"""
        from run import chronicle_rows

        ctx, _data, traj = load("plot", frames=600)
        before = traj.final.digest()
        first = chronicle_rows(ctx, traj)
        second = chronicle_rows(ctx, traj)
        self.assertEqual(first, second)
        self.assertEqual(traj.final.digest(), before)
        for frame, text, badge, rid in first[:20]:
            self.assertIsInstance(frame, int)
            self.assertIsInstance(text, str)
            self.assertTrue(badge is None or isinstance(badge, str))
            self.assertIsInstance(rid, int)

    def test_sampler_returns_true_and_collects(self):
        sampler = Sampler(600)
        _ctx, _data, traj = load("plot", frames=600, watch=sampler)
        self.assertTrue(sampler.points)
        for point in sampler.points:
            self.assertEqual(len(point), 7)      # 帧/熵/溢出/种群/再创世/在位 + 席位
            self.assertEqual(len(point[6]), len(_ctx.loci))
        frames = [p[0] for p in sampler.points]
        self.assertEqual(frames, sorted(frames))  # 单调
        self.assertLessEqual(len(sampler.points), 600)   # 再密也密不过帧数
        self.assertEqual(traj.reached_frame, 599)


class AdvanceLabelSplit(unittest.TestCase):
    """世代更迭的【三个】名字，跟 wiki 的两处改名走：

      ① 更早 = 自动更替；② 第三阶段内（协议改写那一刻起）= 主动更替；③ 第四阶段起 = 再创世。

    这条曾经漏过：时间线打点图省事，一律拿 `terms.promotion` 当名字（那时它就写着「再创世」），
    于是整张图上「自动更替」一次都不出现。现改为按两处界分档 —— 与报告、编年史同一把尺子。
    """

    @staticmethod
    def _labels(records):
        import types

        from engine.loader import Config
        from engine.render import Renderer
        from engine.viz import _timeline_marks

        traj = types.SimpleNamespace(records=list(records))
        R = Renderer(Config(ROOT))
        return [(f, lab) for f, k, lab, _c, _rid in _timeline_marks(traj, R)
                if k == "PROMOTION"]

    def test_split_at_the_switch(self):
        """协议改写那一刻起是【第三阶段】—— 叫「主动更替」，还不到「再创世」。"""
        recs = [(9, "PROMOTION", {"round": 1}),
                (6000, "PROTOCOL_REWRITTEN",
                 {"changed": {"renewal.mode": "decision_ledger"}}),
                (6100, "PROMOTION", {"round": 2})]
        self.assertEqual(self._labels(recs),
                         [(9, "第 1 次自动更替"), (6100, "第 2 次主动更替")])

    def test_renewal_only_from_the_fourth_stage(self):
        """「再创世」是【第四阶段】的名字：跨过 `DOMAINS_EXHAUSTED` 之后才启用。"""
        from engine.loader import Config
        from engine.render import Renderer, advance_label

        R = Renderer(Config(ROOT), myth_from=10000)
        self.assertEqual(advance_label(R, 6000, 5000), "自动更替")     # 协议改写之前
        self.assertEqual(advance_label(R, 6000, 9000), "主动更替")     # 第三阶段内
        self.assertEqual(advance_label(R, 6000, 10000), "再创世")      # 第四阶段起
        self.assertEqual(advance_label(R, None, 10000), "再创世")      # 没改写也是第四阶段的叫法

    def test_rename_clause_only_when_the_names_differ(self):
        """切词说明那句「更替之名也从 A 改为 B」只在两档不同名时才拼（tide 一路同名 ⇒ 不拼）。"""
        from engine.render import stage_rows

        def myth_note(preset):
            ctx, data, _traj = load(preset, frames=1)
            rows = stage_rows(ctx, data, starts=[0, 100], born=[0, 0], prom=[0, 0],
                              fell=[0, 0], reached_frame=200, exhausted=False,
                              switch=None, myth_from=100)
            return rows[-1]["myth_note"]

        self.assertIn("改为「再创世」", myth_note("plot"))
        self.assertNotIn("改为", myth_note("tide"))

    def test_no_switch_means_all_automatic(self):
        recs = [(9, "PROMOTION", {"round": 1}), (6100, "PROMOTION", {"round": 2})]
        self.assertEqual([lab for _f, lab in self._labels(recs)],
                         ["第 1 次自动更替", "第 2 次自动更替"])

    def test_aggregate_name_is_the_umbrella(self):
        """聚合读数（最终状态 / 曲线图例 / 背负）用的是【不分档】的统称。"""
        from engine.loader import Config
        from engine.render import Renderer

        R = Renderer(Config(ROOT))
        labels = R.lex.get("stage_promotion_labels") or {}
        self.assertEqual(R.term("promotion"), "世代更迭")
        self.assertNotIn(R.term("promotion"), set(labels.values()))

    def test_live_board_tracks_the_switch_too(self):
        """实时看板拿不到 traj，得自己从 `PROTOCOL_REWRITTEN` / `DOMAINS_EXHAUSTED` 认那两处界。"""
        from engine.live import LiveState
        from engine.loader import Config
        from engine.render import Renderer

        board = LiveState()
        R = Renderer(Config(ROOT))
        board.add_event(R, 9, "PROMOTION", {"round": 1}, 0)
        board.add_event(R, 6000, "PROTOCOL_REWRITTEN",
                        {"changed": {"renewal.mode": "decision_ledger"}}, 1)
        board.add_event(R, 6100, "PROMOTION", {"round": 2}, 2)
        board.add_event(R, 9000, "DOMAINS_EXHAUSTED", {}, 3)
        board.add_event(R, 9100, "PROMOTION", {"round": 3}, 4)
        labels = [m[2] for m in board.marks if m[1] == "PROMOTION"]
        self.assertEqual(labels, ["第 1 次自动更替", "第 2 次主动更替", "第 3 次再创世"])


class DownsampleKeepsNamedFrames(unittest.TestCase):
    """抽稀必须留住【点名要留】的帧（阶段起点）—— 否则看板点阶段卡落不准。"""

    def test_keep_frames_survive_downsampling(self):
        from engine.viz import _downsample

        pts = [(f, 0, 0, 0, 0, 0, ()) for f in range(0, 6000)]
        out = _downsample(pts, cap=100, keep={1999, 5999})
        frames = [p[0] for p in out]
        self.assertLessEqual(len(out), 104)          # 仍是抽稀过的（cap + 点名的几帧）
        self.assertEqual(frames[0], 0)               # 首
        self.assertEqual(frames[-1], 5999)           # 末
        self.assertIn(1999, frames)                  # 点名的帧必留


class SamplerKeepsStageBoundaries(unittest.TestCase):
    """换档帧必须进采样序列（靠「档位变了」回推补采）—— 看板点阶段卡才落得准。"""

    def test_boundary_frames_are_sampled(self):
        from engine.render import stage_starts
        from engine.viz import Sampler

        s = Sampler(2600)
        _ctx, _data, traj = load("plot", frames=2600, watch=s)
        frames = {p[0] for p in s.points}
        starts = stage_starts(traj)
        self.assertGreaterEqual(len(starts), 2)          # 这一段至少跨过一次换档
        for f in starts:
            self.assertIn(f, frames, f"换档帧 {f} 没进采样序列")


class SimPhaseVocabulary(unittest.TestCase):
    """前三个阶段（因子演算）不许出现世界内（第四阶段）的词 —— wiki 口径的硬约束。

    据 moegirl 第 47 行：到**第四阶段**背景才设为人类古典文明，「十二因子便成为十二泰坦/
    黄金裔」；在此之前它们只是【电信号 / 生命原动力的简化模型】（biligame）。故
    「黄金裔 / 接掌 / 十二位齐备 / 火种 / 半神」这一套在演算期的编年史里一个都不该有
    —— 它们曾经**全都出现过**：帧 0 就在讲「黄金裔涌现：X · 接掌「负世」之位」。
    """

    WORLD_IN = ("黄金裔", "泰坦", "半神", "火种", "接掌", "退位", "神位", "逐火")

    @classmethod
    def setUpClass(cls):
        import run

        cls.chronicle_rows = staticmethod(run.chronicle_rows)   # 免得被当成方法
        cls.ctx, cls.data, cls.traj = load("plot", frames=2500)

    def test_sim_phase_speaks_the_simulation_vocabulary(self):
        rows = self.chronicle_rows(self.ctx, self.traj)
        text = " ".join(t for _f, t, _b, _r in rows)
        for w in self.WORLD_IN:
            self.assertNotIn(w, text, f"演算期的编年史里混进了世界内的词「{w}」")
        self.assertIn("电信号涌现", text)            # 该用的是演算期那套
        self.assertIn("原动力", text)

    def test_sim_phase_clock_is_the_cycle_count(self):
        """演算期没有历法 —— 时间报【第 N 次循环】，不报纪元 / 年份。"""
        from engine.render import renderer_for, myth_phase_frame

        R = renderer_for(self.ctx, self.traj)
        self.assertIsNone(myth_phase_frame(self.traj))     # 2,500 帧还没走到第四阶段
        loc = R.locale(self.traj.reached_frame)
        self.assertIn("循环", loc)
        self.assertNotIn("年", loc)
        self.assertEqual(R.phase_of(self.traj.reached_frame), "sim")

    def test_sim_slots_are_all_distinct(self):
        """演算期那 12 位「原动力」的名字必须两两不同。

        wiki（δ-me13「12の因子」）：「実験におけるコア変数、**12種類の生命原動力**の
        簡略化モデルである」—— 12 个因子是互异的。词干若少于 12 个，`order % len`
        会让第 8 位与第 0 位撞名（曾经如此）。
        """
        from engine.viz import _sim_slots

        labels = _sim_slots(self.ctx)
        self.assertEqual(len(labels), 12)
        self.assertEqual(len(set(labels)), 12, f"演算期十二席撞名了：{labels}")

    def test_sim_overlay_leaves_carry_no_world_words(self):
        """演算期覆盖里的**每一句**（含死循环 / 停滞那些当前跑不到的）都不许带世界内的词。

        死循环只发生在世界内阶段，编年史那条路径在演算期摸不到它 ⇒ 这里按【词表】查：
        把 `phase_terms.sim` 的每个叶子拼出来扫一遍，免得日后哪个叶子漏改又冒出来。
        另附几个只在世界内句子里出现的词（轮回 / 当世 / 世上 / 负担）——
        「升格」不在此列：演算期的 `chronicle.rise` 本来就用它（「十二因子原位升格」）。
        """
        extra = ("轮回", "当世", "世上", "负担")
        over = (self.ctx.lexicon.get("phase_terms") or {}).get("sim") or {}
        text = " ".join(str(v) for table in over.values() for v in table.values())
        for w in self.WORLD_IN + extra:
            self.assertNotIn(w, text, f"演算期覆盖里混进了世界内的词「{w}」")


class TimelineMarksMatchTheirChronicleRow(unittest.TestCase):
    """时间线打点与编年史行共用【事件号】—— 双击一个节点要回到它自己那条。

    曾经只按帧号匹配：同一帧里往往有好几条（换代 / 变量域推进 / 外生介入…），
    于是选中 A 却高亮排在帧首的 B。这条钉住「每条打点都能唯一命中所属行」。
    """

    def test_every_mark_maps_to_its_own_row(self):
        from engine.render import renderer_for
        from engine.viz import _timeline_marks
        from run import chronicle_rows

        ctx, _data, traj = load("plot", frames=2500)
        R = renderer_for(ctx, traj)
        marks = _timeline_marks(traj, R)
        rows = chronicle_rows(ctx, traj)

        by_rid = {}
        for frame, _text, _badge, rid in rows:
            by_rid.setdefault(rid, frame)

        self.assertTrue(marks)
        rids = [m[4] for m in marks]
        self.assertEqual(len(rids), len(set(rids)), "打点事件号重复了")
        for frame, _kind, _lab, _c, rid in marks:
            self.assertIn(rid, by_rid, f"帧 {frame} 的打点没有对应编年史行")
            self.assertEqual(by_rid[rid], frame)      # 命中【那条】，且同在它该在的帧


if __name__ == "__main__":
    unittest.main()
