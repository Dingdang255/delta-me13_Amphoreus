"""剧情即机制（B6 的 L2）实验预设 `plot-mech` —— 分类自洽 + 机制真咬人 + plot 不受影响。

五条要求：
  ① **plot 原样保留**：它的 `events.jsonl` 里没有逐出（招牌轨道的逐帧不变另有
     `tools/snapshot.py` 的指纹门禁守着，那条比在这里跑一遍强）；
  ② **升级条目真的执行**：`disturb:evict_holder` 与 `evicted` 都等于「已到帧的升级条数」，
     emit 计数按「被升级掉的**不同**事件名」等量减少（双陨一拆二，故条数 ≠ 事件数）；
  ③ **分类表与事件表逐条对得上**：`preset.json` 的 `_classification` 漏写一条就红；
  ④ **留下的仍是镜头**：`kept_as_l1` 那些名字在两个预设里都还是 emit；
  ⑤ **机制确实咬人**：临时预设里把逐出放在第 300 帧 —— 席位真的被清掉、账目 +1。

**关于开销**：`plot-mech` 的第一条升级在第 12,000 帧，而这个世界跑到那里的代价约 13 秒
（人口随时间超线性增长）。故本文件**只跑一次**真实世界，其余全部走文件级比对与临时预设 ——
别再加第二遍。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from _support import ROOT, load, temp_root_with_copy

from engine.conditions import evaluate
from engine.core import run
from engine.loader import Config, DataSet
from engine.services import default as default_services

#: 跑到 12,001 帧：正好覆盖第一条升级（纷争那一席，第 12,000 帧）。
FRAMES = 12001


def _emits_upto(data, frames):
    """该预设到 `frames` 为止【会真的投递】的 emit 条数（persist 的重复投递不算新的一条）。"""
    recs = (list(data.preset.get("disturbances") or [])
            + list(data.preset.get("events") or []))
    return sum(1 for r in recs
               if r.get("capability") == "emit"
               and int(r["frame"]) <= frames
               and not (r.get("payload") or {}).get("persist"))


class PlotMechClassification(unittest.TestCase):
    """文件级：分类表与两份 events.jsonl 必须逐条对得上。不跑引擎，快。"""

    @classmethod
    def setUpClass(cls):
        cls.cls = DataSet(ROOT, preset="plot-mech").preset["_classification"]
        cls.upgraded = cls.cls["upgraded"]
        cls.kept = cls.cls["kept_as_l1"]
        cls.events_p = DataSet(ROOT, preset="plot").preset["events"]
        cls.events_m = DataSet(ROOT, preset="plot-mech").preset["events"]

    def test_plot_carries_no_eviction(self):
        caps = {r.get("capability") for r in self.events_p}
        self.assertNotIn("evict_holder", caps)
        self.assertIn("emit", caps)

    def test_every_upgrade_exists_in_both_files(self):
        for u in self.upgraded:
            with self.subTest(event=u["event"], selector=u["selector"]):
                hit = [r for r in self.events_m if r["frame"] == u["frame"]
                       and r.get("capability") == u["capability"]
                       and (r.get("selector") or {}).get("expr") == u["selector"]]
                self.assertEqual(len(hit), 1, "plot-mech 事件表里找不到这条升级")
                was = [r for r in self.events_p if r["frame"] == u["frame"]
                       and r.get("capability") == "emit"
                       and (r.get("payload") or {}).get("event") == u["event"]]
                self.assertEqual(len(was), 1,
                                 f"plot 在 {u['frame']} 没有对应的镜头条目")

    def test_no_mechanism_sneaks_in_unlisted(self):
        """相对 plot 新增的机制投递，条数与分类表**完全相等** —— 没有偷偷多加的。"""
        def mech(events):
            return [r for r in events if r.get("capability") != "emit"]
        self.assertEqual(len(mech(self.events_m)) - len(mech(self.events_p)),
                         len(self.upgraded))

    def test_kept_as_l1_are_emit_in_both(self):
        for name in self.kept:
            with self.subTest(event=name):
                for events, who in ((self.events_p, "plot"),
                                    (self.events_m, "plot-mech")):
                    hit = [r for r in events
                           if (r.get("payload") or {}).get("event") == name]
                    self.assertTrue(hit, f"{who} 里没有 {name}")
                    self.assertTrue(all(r.get("capability") == "emit" for r in hit),
                                    f"{who} 里 {name} 不该被升级")

    def test_the_peace_means_is_wired(self):
        """L2 不止一种手段：至少有一条桥段走【交涉归还】（和平），而不是清一色逐出。

        「黄金裔不一定只能杀死泰坦取火种」—— 引擎为此新增了 `parley`（谈成则自愿让位、
        不死人），与 `evict_holder`（必死）成对。这条钉住它确实接进了预设。
        """
        caps = [u["capability"] for u in self.upgraded]
        self.assertIn("parley", caps)
        self.assertIn("evict_holder", caps)
        self.assertEqual(len([r for r in self.events_m
                              if r.get("capability") == "parley"]), 1)

    def test_classification_partitions_the_emit_events(self):
        """plot 的 emit 事件名，恰好被分成「升级」与「保持 L1」两组，不重不漏。"""
        in_plot = {(r.get("payload") or {}).get("event") for r in self.events_p
                   if r.get("capability") == "emit"}
        upgraded = {u["event"] for u in self.upgraded}
        kept = set(self.kept)
        self.assertEqual(upgraded | kept, in_plot)
        self.assertEqual(upgraded & kept, set())


class EvictionBites(unittest.TestCase):
    """机制真的咬人：临时预设把逐出放在第 300 帧，看席位是否真被清掉、账目是否 +1。

    这条不跑招牌世界（省十几秒），只证明「`evict_holder` 经真实装载路径会执行、而且
    真的把在位者清掉」。有了它，`plot-mech` 在第 12,000 帧那一次升级**必然**让轨迹分叉
    ——因为前 12,000 帧两个预设逐帧相同（升级全在第 12,000 帧之后）。
    """

    def _run_with(self, record, frames=400):
        with tempfile.TemporaryDirectory() as tmp:
            root = temp_root_with_copy(tmp)
            d = os.path.join(root, "presets", "t")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "preset.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "t", "seed": 0}, f)
            with open(os.path.join(d, "events.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            ctx = Config(root)
            data = DataSet(root, preset="t")
            return run(ctx, data, seed=0, max_frames=frames, rules=evaluate,
                       runtime=default_services())

    def test_eviction_clears_the_seat_and_counts(self):
        traj = self._run_with({"frame": 300, "channel": "world",
                               "capability": "evict_holder",
                               "selector": {"expr": "order:3"},
                               "payload": {}})
        self.assertEqual(float(traj.final.score.get("disturb:evict_holder", 0)), 1.0)
        # `evicted` 只有真的把在位者从池子里 kill 掉才会 +1 —— 空席上的逐出不算数。
        self.assertEqual(float(traj.final.score.get("evicted", 0)), 1.0)

    def test_emit_leaves_the_world_alone(self):
        """对照组：同一条记录换成 emit —— 世界不该被碰（这正是 L1 与 L2 的差别）。"""
        traj = self._run_with({"frame": 300, "channel": "world",
                               "capability": "emit", "selector": None,
                               "payload": {"event": "x"}})
        self.assertEqual(float(traj.final.score.get("disturb:evict_holder", 0)), 0.0)
        self.assertEqual(float(traj.final.score.get("evicted", 0)), 0.0)
        self.assertEqual(float(traj.final.score.get("emitted_x", 0)), 300.0)


class PlotMechRuns(unittest.TestCase):
    """跑一次真实世界，钉住「升级真的发生」。"""

    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("plot-mech", frames=FRAMES, seed=0)
        cls.cls = DataSet(ROOT, preset="plot-mech").preset["_classification"]
        cls.data_p = DataSet(ROOT, preset="plot")

    def test_every_due_upgrade_fires(self):
        due = [u for u in self.cls["upgraded"] if u["frame"] <= FRAMES]
        self.assertEqual(len(due), 1, "窗口内该恰好覆盖第一条升级")
        self.assertEqual(float(self.traj.final.score.get("disturb:evict_holder", 0)),
                         float(len(due)))
        self.assertEqual(float(self.traj.final.score.get("evicted", 0)), float(len(due)))

    def test_emit_count_drops_by_the_distinct_event_names(self):
        due = [u for u in self.cls["upgraded"] if u["frame"] <= FRAMES]
        gone = len({u["event"] for u in due})
        self.assertEqual(
            _emits_upto(self.data_p, FRAMES) - _emits_upto(self.data, FRAMES), gone)
        self.assertEqual(float(self.traj.final.score.get("disturb:emit", 0)),
                         float(_emits_upto(self.data, FRAMES)))

    def test_run_reaches_the_budget(self):
        self.assertEqual(self.traj.reached_frame, FRAMES - 1)
        self.assertFalse(self.traj.truncated)

    def test_features_expose_the_mechanism_ledger(self):
        """L2 之后机制不再走 emit，单看 `emitted_*` 会以为它没跑 —— 故另记一份能力账本。"""
        from engine.features import extract
        f = extract(self.traj, self.ctx)
        self.assertIn("evict_holder", f["disturb_capabilities"])
        self.assertGreaterEqual(f["disturb_total"], 1)
        # 对照：plot 短跑一趟，同一字段里【没有】逐出 —— 该字段确实能区分两个预设。
        ctx_p, _d, traj_p = load("plot", frames=3001, seed=0)
        self.assertNotIn("evict_holder",
                         extract(traj_p, ctx_p)["disturb_capabilities"])

    def test_mechanism_keeps_the_event_ledger(self):
        """机制化**不该丢掉可核对性**：`emitted_<事件名>` 在机制形态下照样要登记。

        `dispatch` 对任何带 `payload.event` 的能力统一登记 —— 于是「这条桥段有没有真的
        执行过」在【镜头】与【机制】两种形态下口径一致。
        """
        due = [u for u in self.cls["upgraded"] if u["frame"] <= FRAMES]
        self.assertTrue(due)
        for u in due:
            with self.subTest(event=u["event"]):
                self.assertIn("emitted_" + u["event"], self.traj.final.score)

    def test_arc_timeline_node_now_passes(self):
        """端到端：`plot` 那条按事件名核对的剧情节点，在机制版里**照样命中**。

        这正是「机制与剧情口径一致」的可核对证据 —— 之前它 FAIL 不是因为情节没发生，
        而是因为账本漏登记。
        """
        from engine.features import extract
        from engine.timeline import check as check_timeline
        feats = extract(self.traj, self.ctx)
        got = {r.id: r.ok for r in check_timeline(self.data_p.timeline_nodes, feats)}
        self.assertTrue(got["N19_ARC_3_0"], "升级为机制后这条剧情节点必须仍然命中")


if __name__ == "__main__":
    unittest.main()