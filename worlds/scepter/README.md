# 权杖世界根

这是一个**独立世界根**：`--root worlds/scepter --preset scepter`。它复用
`worlds/origin/config/` 的 13 席位表与算子装配（12 正席 + 1 元席），但**不启用**
回望驱动（`params.origin_world = false`）。七层读数全部是 `apps/scepter.py` 的
只读派生，不改 `kernel/`、不改轨迹、也不进指纹。

## 七层 → 既有原语

| 层 | 读什么 | 来源（state 字段 / 推导式） |
| --- | --- | --- |
| 内核层 `kernel_layer` | 内核矩阵已写格数、演算方向、机制门 | `State.rule_matrix` 的 `count_nonzero`；`State.solver`；`State.gates` |
| 权限层 `authority_layer` | 谁握有写权限 | `State.actors[*].grants` + `State.grants` + `State.authorities`；`State.entry_locked` |
| 火种槽 `seed_slots` | 12 + 1 槽的余量 | `State.register.slots[*].owner`（L00–L11 正席、L12 元席）与 `State.suppressed` |
| 再创世计数 `regen_count` | 当前轮次 / 锚点位置 / 上限 | `State.promotions` + `presets/scepter/preset.json::scepter.regen.initial` |
| 黑潮熵 `entropy` | 失序熵与本底强度 | `State.entropy`；`State.noise` |
| 记忆存储 `memory_store` | 记忆规模与闭合度 | `State.memory_bank.shape[0]`；`State.memory_seats`；`State.origin.closure`；`State.score['memory_repaired']` |
| 外部注入 `external_injection` | 外生投递次数与通道 | `traj.records` 里 `kind == "DISTURBANCE"` 的记录数、`channel` 集合 |

每一层在 `apps/scepter.summary()` 里都给出 `value / unit / source / confidence`。
读不到的字段写 `value: null` 并附 `unavailable_reason`，不做回填。

## 再创世刻度对齐

`presets/scepter/preset.json::scepter.regen` 的 17 个锚点直接取自
`lore/D6_terminal/triggers.json::loop_index`（它索引
`lore/D5_loops/official_anchors.jsonl` 的官方轮次）：

```
1, 3, 15, 42, 133, 134, 5297, 12398, 23779, 46645,
71243, 80023, 95575, 108641, 108642, 33550336, 33550337
```

`cap = 33550336`（D5 的回归总数），`final = 33550337`（官方最终轮）。
报告里的轮次 = `State.promotions + regen.initial`；面板只用既有 `.bar` 画
「槽位余量」与「熵」两根条，归一化上限写在 `entropy_cap`。

## 预设

`presets/scepter/preset.json` 把 `narrative` 全开：
`terminal / archive / panels / scepter = true`，`origin / fidelity = false`。
外部注入来自 `presets/scepter/events.jsonl`，权限持有者来自
`presets/scepter/actors.json`，两者都是数据，不是代码常量。

```
python run.py --root worlds/scepter --preset scepter --frames 50 --scepter
```
