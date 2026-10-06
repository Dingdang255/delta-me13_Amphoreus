"""角色涌现。

谁算「角色」？两条路径任取其一，对全体个体统一求值：
  ① 本世逐火承位 —— 世代之内夺下那一席的人（引擎只认「本世承位」这个事实）；
  ② 四条全称判据（年龄 / 稳定 / 影响 / 曾承位）—— 让角色也能从人海里自行长出。
角色【只写进 Telemetry】，永不写回 data/ —— 这是判据六。
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Persona:
    """一个被演算跑出来的角色。它是只读的观测结果，不是输入。"""

    serial: int
    surfaced_frame: int
    locus_order: int | None
    capabilities: frozenset
    fingerprint: bytes
    vector: tuple
    rank: int = -1          # 第几个被登记（0 起）；用作锚定层的稳定键


def fingerprint(vec, locus_order: int, serial: int, seed: int) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    q = np.rint(np.asarray(vec, dtype=np.float64) * 100000).astype(np.int64)
    h.update(q.tobytes())
    h.update(struct.pack("<iiq", int(locus_order), int(serial), int(seed)))
    return h.digest()


class EmergenceRegistrar:
    """遍历全部个体，登记所有「本世逐火承位」或「满足四条全称判据」者。不点名。"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.registered = {}
        self.personas = []

    # ---- 四判据 ------------------------------------------------------
    def _p1_age(self, st, k, frame):
        return (frame - int(st.pool.born[k])) >= self.ctx.params["tau_age"]

    def _p2_stable(self, st, k, frame):
        return int(st.pool.stable[k]) >= self.ctx.params["tau_stable"]

    def _p3_influence(self, st, k, frame):
        return float(st.pool.support[k]) >= self.ctx.params["tau_influence"]

    def _p4_holds(self, st, k, frame):
        return bool(st.pool.held[k])

    def _p5_pilgrim(self, st, k, frame):
        """本世逐火承位者 —— 世代之内夺下那一席的人。

        这是「角色」的直接定义：逐火本身就是定义，不再依赖年龄 / 稳定 / 影响
        这些代理判据。每世恰好换出十二位这样的人。

        逐火是在再创世那一帧发生的（world_clock 随即 +1），故他的承位世数记的是
        【刚结束的那一世】——所以这里同时认「本世」与「上一世」承位者。
        """
        clock = int(st.world_clock)
        return int(st.pool.seated_clock[k]) in (clock, clock - 1)

    def passes(self, st, k, frame) -> bool:
        # ① 本世逐火承位（正解）；或 ② 四条全称判据（角色也能自人海长出）。
        return (self._p5_pilgrim(st, k, frame)
                or (self._p1_age(st, k, frame) and self._p2_stable(st, k, frame)
                    and self._p3_influence(st, k, frame) and self._p4_holds(st, k, frame)))

    def _passes_mask(self, st, idx, frame):
        """把 `passes()` 的四条判据对全体一次算完，返回布尔掩码。

        与逐个体调用 `passes()` 逐位等价：`support` 是 float32，故先无损升到
        float64 再与阈值（可能不是 float32 可精确表示的）比较，与 Python 侧
        「float(support) >= float(tau)」完全一致；其余三条都是整数/布尔比较。
        """
        p = self.ctx.params
        pool = st.pool
        clock = int(st.world_clock)
        seated = pool.seated_clock[idx]
        p5 = (seated == clock) | (seated == clock - 1)
        p1 = (frame - pool.born[idx]) >= p["tau_age"]
        p2 = pool.stable[idx] >= p["tau_stable"]
        p3 = pool.support[idx].astype(np.float64) >= float(p["tau_influence"])
        p4 = pool.held[idx]
        return p5 | (p1 & p2 & p3 & p4)

    # ---- 扫描 --------------------------------------------------------
    def _held_order(self, st, serial):
        for i, slot in enumerate(st.register.slots):
            if slot.owner == serial:
                return st.loci[i].order
        return None

    def scan(self, st, frame):
        if not self.ctx.params.get("emergence", True):
            return []
        idx = st.pool.index()
        if idx.size == 0:
            return []
        # 判据先用 numpy 一次算完全体，再只对【通过者】做登记 —— 逐个体跑四条判据
        # 是每帧最贵的一段（实测占全量约一成半）。逐位等价：掩码取的还是同一批人，
        # 且登记仍按 index() 的升序进行（rank 的顺序不能变，锚定编号依赖它）。
        ok = self._passes_mask(st, idx, frame)
        fresh = []
        for k in idx[ok]:                               # ← 只剩通过者
            k = int(k)
            serial = int(st.pool.serial[k])
            if serial in self.registered:
                continue
            if not self.passes(st, k, frame):
                continue
            order = self._held_order(st, serial)
            caps = frozenset(
                t.split(":", 1)[1] for t in st.pool.tags[k] if t.startswith("capability:")
            )
            fp = fingerprint(st.pool.vec[k], order if order is not None else -1,
                             serial, getattr(self.ctx, "seed", 0))
            locus_id = self.ctx.loci[order].id if order is not None else None
            rank = len(self.personas)
            per = Persona(
                serial=serial,
                surfaced_frame=int(frame),
                locus_order=order,
                capabilities=caps,
                fingerprint=fp,
                vector=tuple(float(x) for x in st.pool.vec[k]),
                rank=rank,
            )
            self.registered[serial] = per
            self.personas.append(per)
            fresh.append(per)
        return fresh

    # ---- 输出 --------------------------------------------------------
    def describe(self, persona) -> dict:
        """内核视角的「这个人是谁」：**只有编号，没有任何名字**。

        名字由表现层拿这份载荷去查（`Namer.named_payload`）。内核既不认识命名，
        也不知道 `rank` 会被渲染层当作锚定键（`emerge:N`）来用。
        """
        out = {"serial": int(persona.serial), "rank": int(persona.rank),
               "fingerprint": persona.fingerprint.hex()}
        if persona.locus_order is not None:
            out["locus"] = self.ctx.loci[persona.locus_order].id
            out["locus_order"] = int(persona.locus_order)
        return out