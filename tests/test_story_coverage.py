"""剧情覆盖率：至少 90% 的剧情节拍必须由【真实读数】证明，而不是 emit 标签。

清单在 `worlds/origin/story.jsonl`：每一行是一个 plot 节拍，`proof` 是它落在哪条
真实断言上，`how` 是它靠哪一种能力参与演算（`world` = 世界自己长出来的读数）。

这条测试做三件事：
  1. 动态节拍 / 全部节拍 ≥ 90%；
  2. 每个动态节拍的 `proof` 必须是引擎登记过的断言，且该断言真的写进了这个预设；
  3. 凡是靠外生能力参与演算的节拍，事件表里必须真有那一帧、那种能力。
     —— 「写了一个 emit，却宣称它是剧情」这种事故会当场被抓出来。
"""
from __future__ import annotations

import json
import os
import unittest

from _support import ROOT

from kernel.vocabulary import ASSERTION_KINDS, split_kind

WORLD = os.path.join(ROOT, "worlds", "origin")
STORY = os.path.join(WORLD, "story.jsonl")

#: 真的会改世界的那些能力。`emit` 只记账、不改状态，故不在名单里。
STATE_CHANGING = frozenset({
    "bind_participant", "suppress_slot", "release_slot", "evict_holder",
    "gaze", "write_memory", "interstice", "revise_protocol",
    "overwrite_operator", "overwrite_conclusion", "modify_operator",
    "origin_anchor", "raise_noise", "recreate", "entry", "hint",
    "checkpoint", "name_factor",
})
#: 只证明「事件发生过」的读数，不能当作动态证明。
RENDER_ONLY_PROOFS = frozenset({"emitted_events"})


def _jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _preset_dir(name):
    return os.path.join(WORLD, "presets", name)


def _preset_frames(name):
    p = os.path.join(_preset_dir(name), "preset.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            frames = (json.load(f).get("params") or {}).get("frames")
        if frames:
            return int(frames)
    p = os.path.join(WORLD, "config", "params.json")
    with open(p, encoding="utf-8") as f:
        return int(json.load(f)["frames"])


class StoryCoverageTest(unittest.TestCase):
    def setUp(self):
        self.beats = _jsonl(STORY)
        self.assertGreater(len(self.beats), 0, "story.jsonl 不能为空")

    def test_dynamic_ratio_is_at_least_ninety_percent(self):
        dynamic = sum(1 for b in self.beats if b.get("dynamic"))
        ratio = dynamic / float(len(self.beats))
        self.assertGreaterEqual(
            ratio, 0.9,
            f"动态剧情只有 {dynamic}/{len(self.beats)} = {ratio:.1%}")

    def test_dynamic_proof_is_a_real_reading_and_is_checked(self):
        for b in self.beats:
            if not b.get("dynamic"):
                self.assertFalse(
                    str(b.get("how")) in STATE_CHANGING,
                    f"{b.get('id')} 标为渲染，却写了会改状态的能力 {b.get('how')}")
                continue
            proof = str(b.get("proof") or "")
            base, _op = split_kind(proof)
            self.assertIn(base, ASSERTION_KINDS,
                          f"{b.get('id')} 的证明 {proof} 不是登记过的断言")
            self.assertNotIn(base, RENDER_ONLY_PROOFS,
                             f"{b.get('id')} 拿事件标签当动态证明")
            kinds = {split_kind(str(a.get("assert")))[0]
                     for a in _jsonl(os.path.join(
                         _preset_dir(str(b["preset"])), "assertions.jsonl"))}
            self.assertIn(base, kinds,
                          f"{b['preset']} 没有核对 {b.get('id')} 的断言 {proof}")

    def test_state_changing_beats_have_a_real_event(self):
        for b in self.beats:
            how = str(b.get("how") or "")
            if not b.get("dynamic") or how not in STATE_CHANGING:
                continue
            events = _jsonl(os.path.join(
                _preset_dir(str(b["preset"])), "events.jsonl"))
            hit = any(int(e.get("frame", -1)) == int(b["frame"])
                      and str(e.get("capability")) == how for e in events)
            self.assertTrue(
                hit, f"{b['preset']} 在 {b['frame']} 帧没有 {how} 事件"
                     f"（{b.get('id')}）")

    def test_every_beat_fits_its_preset(self):
        for b in self.beats:
            self.assertTrue(os.path.isdir(_preset_dir(str(b["preset"]))),
                            f"{b.get('id')} 指向不存在的预设 {b.get('preset')}")
            self.assertLess(int(b["frame"]), _preset_frames(str(b["preset"])),
                            f"{b.get('id')} 的帧超出了预设范围")

    def test_render_beats_are_honest_dialogues(self):
        render = [b for b in self.beats if not b.get("dynamic")]
        for b in render:
            self.assertEqual(b["how"], "emit")
            self.assertTrue(str(b.get("note") or ""),
                            f"{b['id']} 标为渲染，必须写清为什么")
