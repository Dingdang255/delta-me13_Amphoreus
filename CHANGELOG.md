# 更新记录

> 每个版本的发布说明。发 GitHub Release 时，正文直接取对应小节即可。

## 未发布 — 内核/用户态分层（P0–P4）· 预设目录归一（P2）

> **非破坏性**：裁决帧、结论与 `digest` **一个都没变** —— `snapshot --fast` 6/6 逐位一致，
> 全量 `selfcheck` 9 步全绿。因此本次**不触发** v0.1.0 指纹的重基线。

### 内核：控制流倒置，分层基线归零

内核（`engine/`）不再 import 服务层。不变量检查 / 消融探针 / 裁决全部由应用层经
`run(..., rules=, runtime=, namer=)` 交入，内核只按名调用、不认识其逻辑：

- `runtime.checks` —— 不变量检查（原 `core → invariants`）
- `runtime.probe` —— 消融探针（原 `core → ablation`）
- `runtime.judge` / `runtime.inner_verdict` —— 裁决（原 `core → verdicts`）

`tools/layer_lint.py` 的棘轮基线由 **6 条收敛到 0**：`engine/` 里内核一行 import 都不再往上。

### 预设：世界与剧情归一

- **取消 `data/` 目录**：默认机器规格迁到 `presets/_default/`。
- **取消「两层同名 + 隐式递归覆盖」**：预设自带 `genesis.json` 时，要么是一份**完整**规格，
  要么在 `preset.json` 里显式写 `"extends": "_default"` 声明继承（`refuted` 用后者）。
- 无预设 / `emergent` 显式回落到 `presets/_default/`。

### 其他

- 判据 6 的只读探针由守 `data/` 改为守 `presets/`（并改为递归指纹）。
- `--dump-anchors` 导出到本次运行所用预设的目录。

## v0.1.0 — 2026-10-05

首次发布。把《崩坏：星穹铁道》翁法罗斯「真相层」做成**可复现、可证伪的逐帧演算**的引擎。
引擎代码**零专有名词**——名字、城邦、历法全在外部（`presets/` 与 `config/lexicon.json`）。

### 关键读数

**参考平台**（`digest` 逐位可比的前提，见 `tests/golden_fingerprints.json` 的 `_reference_platform`）：
`Windows / AMD64 / Python 3.14.0 / numpy 2.5.1`

| 预设 | 结论 | 停帧 | 停因 | 迭代 |
|---|---|---|---|---|
| `destruction` | 归于毁灭 `C_UNIVERSAL_DESTRUCTION` | 2,000 | `DESTRUCTION` | 2,001 |
| `tide` | 被湮灭吞没 `C_CONSUMED_BY_ANNIHILATION` | 5,999 | `BUDGET`（预算兜底） | 6,000 |
| `emergent` | 未决 `C_UNDECIDED` | 1,499 | `BUDGET`（预算兜底） | 1,500 |
| `nullify` | 归于毁灭 `C_UNIVERSAL_DESTRUCTION` | 33,594,547 | `DESTRUCTION` | 52,407 |
| `plot` | 结论被改写 `C_CONCLUSION_OVERWRITTEN` | 33,594,547 | `OVERWRITTEN` | 52,411 |

> `stop_reason=BUDGET` 的两行是**跑满预算后的兜底**，不是被判定得出的结论——如实标出，不作美化。

**招牌世界 `plot`（种子 0）的结论链**：

```
归于毁灭 @2,000  →  证真 @33,594,383  →  结论被改写 @33,594,527
```

- 永劫回归 **33,550,336 轮**；其中沿参考轨道复用 **33,550,334 帧**
- 换代 82 次 · 涌现者 1,582 位 · 尝试 8,191 次 · 火种累积 402,604,020
- 终局「结论被改写」@33,594,547（门在 33,594,548 翻开）

### 怎么跑

```bash
python -m pip install -r requirements.txt
python tools/selfcheck.py        # 红线 / 单测 / 世界连通 / 指纹，一次跑完（几十秒）
python run.py --preset plot      # 跑招牌世界（数分钟，打印完整报告）
```

### 本版资产

`Amphoreus-v0.1.0.zip` —— 由仓库自带的 `tools/export.py` 打出，**打包时已自检**：
zip 完整性（含 `docs/` 该带的文件与 `LICENSE`）→ 解压后能 `import engine`、装载
`config`/`data` 并跑通 128 帧 → 依赖 `docs/` 的单测通过。
解压后顶层目录为 `Amphoreus/`，按包内 `README.md` 装依赖即可运行。

### 它是什么

- **零专名的引擎**：`engine/` 里没有任何角色名 / 泰坦名 / 城邦名——`tools/grep_forbidden.py` 在 CI 里守着这条红线
- **禁止作弊**：`tools/stepwise_lint.py` 禁掉「解析求解 / 预读未来」这类写法，保证世界是**一步步演化**出来的，而不是被公式算出来的
- **可证伪**：引擎对「每一位是否都能独立驱动失序」给出 `proved / refuted / undecided`，结论由 `config/conclusions.json` 驱动（程序不理解字符串含义）
- **可复现**：RNG 按 `(seed, n)` 派生；轨迹指纹分层（结构层逐位 / 数值层容差 / digest 限参考平台）

MIT License（见 `LICENSE`）。
