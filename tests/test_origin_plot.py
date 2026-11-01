"""剧情预设跑在 13 席世界根：世界根解析 / 13 席 / 回望与锚定的机制。

三件事必须钉住：

1. **默认世界根**：未显式给 `--root` 时，`plot` / `plot-full` 落在 `worlds/origin`
   （13 席 + 回望驱动）；显式 `--root` 永远优先 —— 于是旧行为（12 席）一条都没破。
2. **第十三席是真的**：会话 `dim == 13`、位表 13 项、L12 是 meta 席。
3. **回望 / 锚定落到机制上**：剧情副本故意不写 `nodes.json`（两条实测原因见
   `NodesAndEventsTest`），回望改由 `events.jsonl` 的 `origin_anchor` 承担；它与浮黎的
   `gaze.anchor_past` 载荷直接喂给内核也必须真的生效（不跑满 3,355 万帧 —— 那样单测会
   变成分钟级）。

全量轨迹的口径由 `tests/golden_fingerprints.json` 钉住（`tools/snapshot.py`）。
"""
from __future__ import annotations

import json
import os
import unittest

from _support import ROOT, state

ORIGIN_ROOT = os.path.join(ROOT, "worlds", "origin")
PLOT_DIR = os.path.join(ORIGIN_ROOT, "presets", "plot")
PLOT_FULL_DIR = os.path.join(ORIGIN_ROOT, "presets", "plot-full")

#: 回望 / 锚定两处节拍的帧号（lore/D3_plot/preset_beats.jsonl 的 PB-027 / PB-033）。
#: 写死在这里是有意的：帧号不许随手漂 —— 它们同时是 events.jsonl 的依据。
ANCHOR_FRAME = 33594510        # 德谬歌回望，因果闭合
FULI_FRAME = 33594545          # 「一页永恒」：浮黎把走过的这一段锚进记忆
#: 造空状态用的初始变量域（与 genesis 的三档一致）。
DOMAIN = ["inorganic", "organic", "human"]


def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class WorldRootTest(unittest.TestCase):
    """`--root` 的优先级：显式永远优先，否则按预设所在的世界根解析。"""

    @classmethod
    def setUpClass(cls):
        from run import resolve_world_root
        cls.resolve = staticmethod(resolve_world_root)

    def test_plot_defaults_to_origin_world(self):
        self.assertEqual(self.resolve(None, "plot"), ORIGIN_ROOT)
        self.assertEqual(self.resolve(None, "plot-full"), ORIGIN_ROOT)

    def test_explicit_root_always_wins(self):
        self.assertEqual(self.resolve(".", "plot"), os.path.abspath("."))
        self.assertEqual(self.resolve(ROOT, "plot"), os.path.abspath(ROOT))
        # 显式给默认根 ⇒ 12 席旧行为，一字不改
        self.assertEqual(self.resolve(ORIGIN_ROOT, "plot"), ORIGIN_ROOT)

    def test_other_presets_keep_their_roots(self):
        # 无预设 / 涌现版仍是项目根的 12 席世界
        self.assertEqual(self.resolve(None, "emergent"), ROOT)
        self.assertEqual(self.resolve(None, None), ROOT)
        # 未迁进 origin 根的剧情预设仍走 worlds/plot
        self.assertEqual(self.resolve(None, "plot-mech"),
                         os.path.join(ROOT, "worlds", "plot"))
        # 独立世界根的同名预设不能被截走
        self.assertEqual(self.resolve(ORIGIN_ROOT, "origin"), ORIGIN_ROOT)

    def test_preset_resolves_inside_the_world(self):
        from kernel.loader import preset_dir

        self.assertEqual(preset_dir(ORIGIN_ROOT, "plot"), PLOT_DIR)


class ThirteenSeatsTest(unittest.TestCase):
    """13 席是真的：dim / 位表 / meta 席 / 旧行为不破。"""

    @staticmethod
    def _ctx(root, preset="plot"):
        from kernel.loader import Config, DataSet

        data = DataSet(root, preset=preset)
        ctx = Config(root, lex_overlay=data.preset.get("lexicon"))
        data.apply_params(ctx)
        return ctx, data

    def test_plot_on_origin_has_thirteen(self):
        ctx, _data = self._ctx(ORIGIN_ROOT)
        self.assertEqual(int(ctx.params["dim"]), 13)
        self.assertEqual(len(ctx.loci), 13)
        self.assertTrue(ctx.loci[-1].meta)
        self.assertEqual(ctx.mapping.shape, (13, int(ctx.params["observables"])))
        st = state(ctx, domain=DOMAIN)
        self.assertEqual(len(st.register.slots), 13)

    def test_plot_on_default_root_stays_twelve(self):
        ctx, _data = self._ctx(ROOT)
        self.assertEqual(int(ctx.params["dim"]), 12)
        self.assertEqual(len(ctx.loci), 12)
        self.assertFalse(any(l.meta for l in ctx.loci))
        st = state(ctx, domain=DOMAIN)
        self.assertEqual(len(st.register.slots), 12)

    def test_session_reports_thirteen_seats(self):
        """真跑一小段：终局位表 13 项，且 L12 由某个个体占着（原初成形）。"""
        from apps.conditions import evaluate
        from apps.services import default as default_services
        from kernel.core import run

        ctx, data = self._ctx(ORIGIN_ROOT)
        ctx.params["ablation_period"] = 10 ** 9        # 测试不跑消融探针
        traj = run(ctx, data, seed=0, max_frames=600,
                   rules=evaluate, runtime=default_services())
        self.assertEqual(len(traj.final.register.slots), 13)
        self.assertEqual(len(traj.final.register.slots[12].vector), 13)


class NodesAndEventsTest(unittest.TestCase):
    """回望节点与两条原初事件：帧号有 lore 依据，载荷能被内核真的执行。"""

    def test_no_nodes_file_on_purpose(self):
        """剧情副本【故意没有 nodes.json】—— 两条实测原因，不是漏了。

        ① 44,048 投 `seed_memory(factor_basis)`（写满十二行记忆）后原初的记忆承载 /
           创世机制每帧都在改结构，世界不再冻结，33.59M 帧的永劫复用消失；
        ② 内核的死循环复用（`kernel/core.py`）在 `inbox` 非空时 `cand = n + 1`：
           只要收件箱里压着任何还没到期的锚点，就一帧都不跳。节点在冻结之后
           （33,594,383）⇒ 整个冻结期都不跳 ⇒ 全量运行从分钟级变小时级。
        于是回望改走 `events.jsonl` 里那条显式 `origin_anchor`（在冻结之后才触发）。
        """
        from apps.origin_loop import load_nodes

        self.assertFalse(os.path.exists(os.path.join(PLOT_DIR, "nodes.json")))
        self.assertFalse(os.path.exists(os.path.join(PLOT_FULL_DIR, "nodes.json")))
        self.assertEqual(load_nodes(ORIGIN_ROOT, "plot"), [])
        # 世界根的 config 仍然声明 origin_world ⇒ 即使没有 nodes.json，
        # 回望驱动照样建起来（收尾仍会给出原初四态）。
        from kernel.loader import Config, DataSet

        data = DataSet(ORIGIN_ROOT, preset="plot")
        ctx = Config(ORIGIN_ROOT, lex_overlay=data.preset.get("lexicon"))
        data.apply_params(ctx)
        self.assertTrue(ctx.params.get("origin_world"))

    def test_events_declare_lookback_and_anchor_past(self):
        events = _jsonl(os.path.join(PLOT_DIR, "events.jsonl"))
        anchor = [e for e in events
                  if e.get("capability") == "origin_anchor"
                  and int(e["frame"]) == ANCHOR_FRAME]
        self.assertEqual(len(anchor), 1)
        self.assertEqual(anchor[0]["payload"]["action"], "bind_memory")
        self.assertEqual(anchor[0]["payload"]["seat"], "L01")
        fuli = [e for e in events
                if e.get("capability") == "gaze"
                and (e.get("payload") or {}).get("effect", {}).get("anchor_past")]
        self.assertEqual(len(fuli), 1)
        self.assertEqual(int(fuli[0]["frame"]), FULI_FRAME)
        self.assertEqual(fuli[0]["payload"]["actor"], "memory")   # 浮黎

    def test_plot_full_declares_the_same_two(self):
        events = _jsonl(os.path.join(PLOT_FULL_DIR, "events.jsonl"))
        self.assertTrue(any(e.get("capability") == "origin_anchor"
                            and int(e["frame"]) == ANCHOR_FRAME for e in events))
        self.assertTrue(any(e.get("capability") == "gaze"
                            and (e.get("payload") or {}).get("effect", {}).get("anchor_past")
                            and int(e["frame"]) == FULI_FRAME for e in events))

    # ---- 载荷直接喂给内核：真的改世界，不只是记账 ---------------------------
    def _state_with_origin(self, cap=16):
        import numpy as np
        from kernel.loader import Config, DataSet

        data = DataSet(ORIGIN_ROOT, preset="plot")
        ctx = Config(ORIGIN_ROOT, lex_overlay=data.preset.get("lexicon"))
        data.apply_params(ctx)
        st = state(ctx, cap=cap, domain=DOMAIN)
        st.actors["memory"] = {"label": "", "grants": (), "state": {}}
        for i in range(12):
            slot = st.register.slots[i]
            slot.owner = 1000 + i
            v = np.full(13, 0.05, dtype=np.float32)
            slot.vector = (v / v.sum()).astype(np.float32)
            slot.value = float(slot.vector[i])
        k = st.pool.alloc()
        st.pool.factor[k] = 12
        st.pool.born[k] = 0
        v = np.zeros(13, dtype=np.float32)
        v[:12] = 0.02
        v[12] = 0.6
        st.pool.vec[k] = (v / v.sum()).astype(np.float32)
        slot = st.register.slots[12]
        slot.owner = int(st.pool.serial[k])
        slot.vector = st.pool.vec[k].copy()
        slot.value = float(slot.vector[12])
        st.origin.awake = True
        st.origin.ever = True
        st.origin.filled = True
        st.origin.form = 1
        st.origin.energy = 10.0
        return ctx, st

    def test_origin_anchor_bind_memory_really_hands_the_seat(self):
        from kernel.disturbance import dispatch
        from kernel.operators import MEMORY_OWNER

        ctx, st = self._state_with_origin()
        st.register.slots[1].owner = None            # 岁月那一席空着（自逝入剑之后）
        events = _jsonl(os.path.join(PLOT_DIR, "events.jsonl"))
        payload = next(e["payload"] for e in events
                       if e.get("capability") == "origin_anchor"
                       and int(e["frame"]) == ANCHOR_FRAME)
        dispatch({"capability": "origin_anchor", "payload": payload},
                 st, ctx, ANCHOR_FRAME)
        self.assertEqual(st.register.slots[1].owner, MEMORY_OWNER)
        self.assertEqual(int(st.origin.borrowed), 1)
        self.assertEqual(int(st.origin.repaid), 1)          # 借一手、还一手

    def test_fuli_anchor_past_writes_the_walked_section(self):
        from kernel.disturbance import dispatch

        ctx, st = self._state_with_origin()
        before = st.memory_bank.shape[0]
        events = _jsonl(os.path.join(PLOT_DIR, "events.jsonl"))
        payload = next(e["payload"] for e in events
                       if e.get("capability") == "gaze"
                       and (e.get("payload") or {}).get("effect", {}).get("anchor_past"))
        dispatch({"capability": "gaze", "payload": payload}, st, ctx, FULI_FRAME)
        self.assertIn("emitted_fuli_anchor_past", st.score)
        self.assertEqual(int(st.score["emitted_fuli_anchor_past"]), FULI_FRAME)
        self.assertGreater(st.memory_bank.shape[0], before)


if __name__ == "__main__":
    unittest.main()
