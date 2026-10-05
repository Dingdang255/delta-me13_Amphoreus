"""编年史折叠（A5）：连续同型事件折成一条 + 计数徽标。

折叠是纯渲染：它只攒【已经渲染好的文本】，不碰任何状态。这里只验折叠口径：
同型且相邻才折，中间插进别的事件就得断开，末尾必须吐出来。
"""
from __future__ import annotations

import unittest

from _support import ROOT  # noqa: F401

from run import ChronicleFolder


class ChronicleFolderTest(unittest.TestCase):
    def _fold(self, records):
        out = []

        def emit(rid, line_frame, text, badge):
            out.append((rid, line_frame, text, badge))

        folder = ChronicleFolder(emit)
        for rid, (frame, kind, payload) in enumerate(records):
            folder.feed(rid, frame, kind, payload, f"t{frame}")
        folder.close()
        return out

    def test_same_kind_adjacent_collapses(self):
        recs = [(i, "ATTEMPT_VAIN",
                 {"stage": "obsession", "routine": True, "approach": "suppress_slot"})
                for i in range(1, 6)]
        out = self._fold(recs)
        self.assertEqual(len(out), 1)
        rid, frame, text, badge = out[0]
        self.assertEqual(rid, 0)                   # 折叠取【首条】的事件号
        self.assertEqual(frame, 1)                 # 报首帧
        self.assertEqual(text, "t1")
        self.assertIn("×5", badge)                 # 计数
        self.assertIn("至帧 5", badge)              # 折到哪一帧

    def test_single_event_has_no_badge(self):
        out = self._fold([(1, "ATTEMPT_VAIN",
                           {"stage": "hope", "routine": False, "approach": "plead"})])
        self.assertEqual(out, [(0, 1, "t1", None)])

    def test_different_signature_breaks_the_run(self):
        """换段位 / 换能力 ⇒ 不是同型，必须另起一条。"""
        recs = [(1, "ATTEMPT_VAIN", {"stage": "hope", "routine": False,
                                     "approach": "plead"}),
                (2, "ATTEMPT_VAIN", {"stage": "hope", "routine": False,
                                     "approach": "plead"}),
                (3, "ATTEMPT_VAIN", {"stage": "disillusion", "routine": False,
                                     "approach": "plead"})]
        out = self._fold(recs)
        self.assertEqual(len(out), 2)
        self.assertIn("×2", out[0][3])
        self.assertIsNone(out[1][3])

    def test_other_kind_flushes_pending(self):
        """中间插进一条别的事件，前面那条串必须先吐出来（保序）。"""
        recs = [(1, "ATTEMPT_VAIN", {"stage": "hope", "routine": False,
                                     "approach": "plead"}),
                (2, "PROMOTION", {}),
                (3, "ATTEMPT_VAIN", {"stage": "hope", "routine": False,
                                     "approach": "plead"})]
        out = self._fold(recs)
        self.assertEqual([t for _r, _f, t, _b in out], ["t1", "t2", "t3"])

    def test_promotion_is_never_collapsed(self):
        """世代刻度是不可折叠的：再来一百次也要逐条照报。"""
        recs = [(i, "PROMOTION", {}) for i in range(3)]
        out = self._fold(recs)
        self.assertEqual(len(out), 3)
        self.assertEqual([r for r, _f, _t, _b in out], [0, 1, 2])   # 各自带自己的事件号
        self.assertTrue(all(b is None for _r, _f, _t, b in out))


if __name__ == "__main__":
    unittest.main()
