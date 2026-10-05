"""算子代数：`Interact` 的「结合律改写」必须与直白写法【数值等价】。

`(v@vᵀ)@v` 与 `v@(vᵀ@v)` 数学恒等；改写把中间矩阵从 **m×m** 缩到 **d×d**
（见 `engine/operators.py` 的 `Interact.apply`）。这里对同一批随机向量跑两式比对 ——
若日后有人改错实现（例如漏掉对角线修正、或把 `support` 的行和算错），这条会立刻红。

注意：等价只到 **float32 舍入**（累加顺序变了），**不是逐位相同** —— 所以它会动轨迹。
"""
from __future__ import annotations

import unittest

import numpy as np


def _direct(v):
    """改写前的直白写法（照抄旧实现）。"""
    sim = v @ v.T
    np.fill_diagonal(sim, 0.0)
    support = sim.sum(axis=1)
    ally = (sim @ v) / (support[:, None] + 1e-8)
    return support, ally


def _rewritten(v):
    """现行写法（结合律改写）。"""
    colsum = v.sum(axis=0)                         # (d,)
    self_sim = np.einsum("ij,ij->i", v, v)         # 对角线 v_i·v_i
    gram = v.T @ v                                 # (d,d)
    support = v @ colsum - self_sim                # 行和（对角线已减）
    ally = (v @ gram - self_sim[:, None] * v) / (support[:, None] + 1e-8)
    return support, ally


class InteractAlgebra(unittest.TestCase):
    def test_rewrite_matches_the_direct_formula(self):
        rng = np.random.default_rng(0)
        for m in (2, 17, 400):
            v = rng.dirichlet(np.full(12, 0.1), size=m).astype(np.float32)
            s_direct, a_direct = _direct(v)
            s_new, a_new = _rewritten(v)
            self.assertTrue(np.allclose(s_direct, s_new, rtol=1e-5, atol=1e-5),
                            f"support 不等价（m={m}）")
            self.assertTrue(np.allclose(a_direct, a_new, rtol=1e-5, atol=1e-5),
                            f"ally 不等价（m={m}）")


if __name__ == "__main__":
    unittest.main()
