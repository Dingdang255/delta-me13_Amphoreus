"""可复现性与命名正交性。

同一组输入必须演算出同一结果；换一套命名（名字不参与运算）必须逐帧不变。
这两条是项目的硬约束，故各留一条常驻回归。
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

from _support import ROOT, load

from engine.namer import Namer


class Determinism(unittest.TestCase):
    def test_same_input_same_result(self):
        _c1, _d1, a = load("plot", frames=600)
        _c2, _d2, b = load("plot", frames=600)
        self.assertEqual(a.iterations, b.iterations)
        self.assertEqual(a.reached_frame, b.reached_frame)
        self.assertEqual(a.verdict, b.verdict)
        self.assertEqual(a.final.digest(), b.final.digest())

    def test_resume_from_checkpoint_matches(self):
        """从第 k 帧的存档续跑，应与全程跑到那里逐帧一致。"""
        from engine.core import run
        from engine.loader import Config, DataSet

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        full = run(ctx, data, seed=0, max_frames=600)

        data2 = DataSet(ROOT, preset="plot")
        ctx2 = Config(ROOT, lex_overlay=data2.preset.get("lexicon"))
        head = run(ctx2, data2, seed=0, max_frames=300)
        tail = run(ctx2, data2, seed=0, max_frames=600,
                   start_state=head.final, start_frame=300)

        self.assertEqual(full.reached_frame, tail.reached_frame)
        self.assertEqual(full.final.digest(), tail.final.digest())


class ResumeInsideDeadlock(unittest.TestCase):
    """续跑落在【死循环 / 复用区间】内也必须与从头跑一致 —— **包括账本读数**。

    `digest` 与 `world_signature` 都不含轮回序号、取得量（`seeds`）这类账本读数，
    所以「epoch 取成了续跑的那一帧」这种偏差，普通的 digest 比对完全照不出来 ——
    必须显式比这些计数。提速档（时间刻度 ×1/100）让死循环在几百帧内就开始，
    于是存档点 k 必定落在区间内，这条路径才真的被覆盖。
    """

    FAST = 100
    N = 6000
    K = 3000

    @classmethod
    def _load(cls):
        from engine.loader import Config, DataSet, apply_fast

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        apply_fast(ctx, data, cls.FAST)
        return ctx, data

    def test_resume_inside_deadlock_matches(self):
        from engine.core import run

        c1, d1 = self._load()
        full = run(c1, d1, seed=0, max_frames=self.N)

        c2, d2 = self._load()
        head = run(c2, d2, seed=0, max_frames=self.K)

        c3, d3 = self._load()
        tail = run(c3, d3, seed=0, max_frames=self.N,
                   start_state=head.final, start_frame=self.K)

        self.assertTrue(full.deadlock,
                        "存档点该落在死循环区间内，否则这条测试没覆盖目标路径")
        self.assertEqual(full.final.digest(), tail.final.digest())
        for field in ("seeds", "cycles", "attempts", "traces"):
            self.assertEqual(getattr(full.final, field),
                             getattr(tail.final, field), field)


class RelabellingInvariance(unittest.TestCase):
    """判据 1（`tools/shuffle_loci.py`）：把十二席的 **id 重标定**，世界必须逐项不变。

    原先这个工具全仓无自动调用点；补上常驻回归时才发现**它从没通过过** —— 它当时断言
    的是一个更强的命题（「连耦合与位序一起旋转」也该不变），而那条**不成立**：
    `core.run()` 抽初始个体数是按【位置顺序】取同一条随机流，位序一换每个位置拿到的
    个体数就变了，两次跑的根本不是同一个初始世界。工具已改为钉住真正成立的那条
    （改名 / 改编号不改世界），这条测试与它同口径。
    """

    def test_relabelled_loci_keep_every_observable(self):
        from engine.core import run

        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import shuffle_loci                                     # noqa: E402
        from _harness import load as hload, summary             # noqa: E402

        ctx0, data, _ = hload(fast=100)
        base = summary(run(ctx0, data, max_frames=3000), ctx0)

        for s in (1, 2):
            ctx, _, _ = hload(fast=100)
            P = np.random.default_rng(1000 + s).permutation(len(ctx.loci))
            shuffle_loci.relabelled(ctx, P)
            got = summary(run(ctx, data, max_frames=3000), ctx)
            self.assertEqual(got, base, f"重标定 #{s} 后可观测量变了")


class NamingOrthogonality(unittest.TestCase):
    """名字不参与运算：换一套音位风格（换种子即换风格），轨迹必须逐帧不变。"""

    def test_style_does_not_change_trajectory(self):
        from engine.core import run
        from engine.loader import Config, DataSet

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))

        ctx.seed = 0
        namer_a = Namer(ctx, data.anchors)
        ctx.seed = 987654
        namer_b = Namer(ctx, data.anchors)
        self.assertNotEqual(namer_a.style, namer_b.style)   # 风格确实不同

        a = run(ctx, data, seed=0, max_frames=600, namer=namer_a)
        b = run(ctx, data, seed=0, max_frames=600, namer=namer_b)

        self.assertEqual(a.reached_frame, b.reached_frame)
        self.assertEqual(a.final.digest(), b.final.digest())
        self.assertEqual(a.verdict, b.verdict)

    def test_orthogonality_matrix(self):
        """正交性矩阵：换命名风格 × 换渲染词表，轨迹必须逐帧一致。

        命名与词表都只属于表层（L5）：名字不参与运算，词表只改措辞。
        故任意组合跑出来的世界必须【同一个】（digest 相同）。
        """
        from engine.core import run
        from engine.loader import Config, DataSet

        data = DataSet(ROOT, preset="plot")
        overlays = (None, {"terms": {"deadlock": "另一种叫法", "promotion": "另一种叫法2"}})
        seen = []
        for style_seed in (0, 13, 987654):
            for ov in overlays:
                ctx = Config(ROOT, lex_overlay=ov)
                ctx.seed = style_seed
                namer = Namer(ctx, data.anchors)
                traj = run(ctx, data, seed=0, max_frames=800, namer=namer)
                seen.append((style_seed, bool(ov), traj.verdict,
                             traj.reached_frame, traj.final.digest()))
        self.assertEqual(len({s[4] for s in seen}), 1, seen)

    def test_anchored_names_are_stable(self):
        """锚定层把名字钉在【人】身上：编号 → 名字的映射与命名风格无关。

        编号本身是**实测**的、随轨迹漂移（改一次引擎就要用 `tools/seat_incumbents.py`
        重测一遍），故这里从锚定文件里**现取**一条 `serial:` 绑定 —— 写死一个数字
        会让每次重测锚定都假红。
        """
        from engine.emergence import EmergenceRegistrar
        from engine.loader import Config, DataSet

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        ctx.seed = 0
        namer = Namer(ctx, data.anchors)
        registrar = EmergenceRegistrar(ctx)
        # 内核不认识命名：登记器上**根本没有** namer 这个属性。
        # （这条边被 P1 消掉了 —— 换命名器不改轨迹，现在是构造成立的事实，不是待证明的性质。）
        self.assertFalse(hasattr(registrar, "namer"))
        # 现取一条编号绑定，验证「按编号查名字」这条通路。
        entry = next(a for a in data.anchors
                     if str(a.get("key", "")).startswith("serial:") and a.get("hanzi"))
        serial = int(str(entry["key"]).split(":", 1)[1])
        self.assertEqual(namer.name_by_serial(serial),
                         (str(entry.get("latin", "")), str(entry["hanzi"])))
        self.assertIsNone(namer.name_by_serial(999999999))


class MachineNumbering(unittest.TestCase):
    """机器编号【按因子发号】：同一词干自成一条 1,2,3… 的序列，并跳过预分配掉的号。"""

    @staticmethod
    def _namer(anchors=()):
        from engine.loader import Config

        ctx = Config(ROOT)
        ctx.seed = 0
        return Namer(ctx, anchors)

    def test_per_stem_sequence_and_reserved_skip(self):
        # 本测试自注入一条 machine=NeiKos2 的锚定 ⇒ 该因子发号时要跳过已预分配的 2 号
        n = self._namer([{"key": "serial:99", "latin": "X", "hanzi": "X",
                          "machine": "NeiKos2"}])
        neikos = lambda i: n.machine_name(bytes([0] * 16), 100 + i, -1)  # noqa: E731
        philia = lambda i: n.machine_name(bytes([1] * 16), 200 + i, -1)  # noqa: E731
        self.assertEqual(neikos(0), "Neikos1")
        self.assertEqual(neikos(1), "Neikos3")     # 2 被预分配占着 ⇒ 跳过
        self.assertEqual(neikos(2), "Neikos4")
        self.assertEqual(philia(0), "Philia1")     # 另一因子另起一条序列

    def test_anchored_machine_wins(self):
        """锚定钉死的机器编号优先，且不占用该因子的号。"""
        n = self._namer([{"key": "serial:99", "latin": "X", "hanzi": "X",
                          "machine": "NeiKos496"}])
        self.assertEqual(n.machine_name(bytes([0] * 16), 99, -1), "NeiKos496")
        self.assertEqual(n.machine_name(bytes([0] * 16), 100, -1), "Neikos1")

    def test_preset_pins_only_the_evidenced_machines(self):
        """预设只钉【原作有据】的两个编号（白厄 / 昔涟），其余不冒称。"""
        from engine.loader import Config, DataSet

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        n = Namer(ctx, data.anchors)
        self.assertEqual({a.get("machine") for a in data.anchors if a.get("machine")},
                         {"NeiKos496", "PhiLia093"})
        entry = next(a for a in data.anchors if a.get("machine"))
        serial = int(str(entry["key"]).split(":", 1)[1])
        self.assertEqual(n.machine_by_serial(serial), entry["machine"])


    def test_stem_follows_the_locus(self):
        """词干取【所属因子】（`order`）—— 与席位名同一把尺子，否则坐在第 N 号原动力上却报别的因子。"""
        n = self._namer([])
        # order=2 ⇒ 因子 Leoreia（与席位卡「第 2 号原动力 · 因子 Leoreia」一致）
        self.assertEqual(n.machine_name(bytes([7] * 16), 5, -1, order=2), "Leoreia1")
        # 未占席（没有因子）才退回指纹字节：7 % 12 = 7 ⇒ polla
        self.assertEqual(n.machine_name(bytes([7] * 16), 6, -1), "Polla1")

    def test_external_marker_comes_from_the_preset(self):
        """「外部变量」标在锚定层（红线 1：这类判断只能放预设）—— 他们不领机器编号。"""
        from engine.loader import Config, DataSet

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        n = Namer(ctx, data.anchors)
        ext = [int(str(a["key"]).split(":", 1)[1])
               for a in data.anchors if a.get("external")]
        self.assertTrue(ext, "预设里该标了外部变量")
        self.assertTrue(all(n.is_external(s) for s in ext))
        self.assertFalse(n.is_external(0))


if __name__ == "__main__":
    unittest.main()
