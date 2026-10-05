"""测试公共设施。

只做两件事：把仓库根挂上 sys.path，以及提供一个「跑一小段」的便捷装载。
单测一律只跑很短的一段（默认 600 帧）—— 够穿透 装载 / 逐帧演化 / 涌现 /
渲染 这几条链路，又不至于把测试拖进那三千多万帧的死循环里。
"""
from __future__ import annotations

import os
import sys

# 钉住 BLAS 线程数 —— 与 `tools/seed_probe.py` / `tools/sensitivity.py` 同一套变量。
# numpy 的归约在多线程下末位可能与单线程不同，而测试里有「两次跑 digest 一致」这类
# 断言；必须在 import numpy 之前设好才生效（各测试都在导入 engine 之前先导入本模块）。
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_FRAMES = 600


def load(preset="plot", frames=DEFAULT_FRAMES, seed=0, **kw):
    """装载配置与数据，并跑一小段。返回 (ctx, data, traj)。"""
    from engine.core import run
    from engine.loader import Config, DataSet

    data = DataSet(ROOT, preset=preset)
    ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
    traj = run(ctx, data, seed=seed, max_frames=frames, **kw)
    return ctx, data, traj


def temp_root_with_copy(tmpdir, names=("config", "data")):
    """把仓库的 config/ 与 data/ 复制到临时目录，返回该临时根。

    校验类测试要的是「改坏一个文件」—— 绝不能动仓库里的真文件。
    """
    import shutil

    for name in names:
        shutil.copytree(os.path.join(ROOT, name), os.path.join(tmpdir, name))
    return tmpdir


def seat_name(ctx, traj, locus_id):
    """经 Renderer 取某一席在世界内的名字 —— 与报告 / 诊断工具同一条取词路径。

    各测试原先各抄一份「`Renderer(ctx, traj.spans, cycle_frames(traj), …)` +
    `R.seat(...)`」；抽到这里，顺带保证口径与生产代码一致（少传一个参数就会
    静默退化成「没有复用 / 还没到世界内」）。
    """
    from engine.render import renderer_for

    return renderer_for(ctx, traj).seat(traj.namer, traj.reached_frame, locus_id)


def state(ctx, cap=64, domain=None, dim=None, observables=None):
    """造一个【不跑演算】的空状态（判据 / 调度 / 消融测试用）。

    `cap` 是池容量；`domain` 是初始变量域（阶段数 = 它的长度）；`dim` / `observables`
    默认取 `ctx.params`，个别测试要别的形状时才显式传。
    """
    from engine.state import State

    p = ctx.params
    return State(ctx.loci,
                 int(dim if dim is not None else p["dim"]),
                 int(observables if observables is not None else p["observables"]),
                 cap, domain)
