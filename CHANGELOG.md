# 更新记录

> 每个版本的发布说明。发 GitHub Release 时，正文直接取对应小节即可。

## 未发布 — A 线维护（`script.jsonl` 样例 · 发版纪律 · 去重）

> **非破坏性**：不触碰任何既有世界的轨迹 —— 指纹 6/6 逐位不变，`v0.1.1` 的全部读数仍然成立。

### 新增 `presets/_demo/` —— `script.jsonl` 的可运行样例

§D2 落地后，仓库里其实一个 `script.jsonl` 都没有（契约只活在测试的内联规则里）。
现在补一个真正能跑的：

```bash
python run.py --preset _demo --frames 5000
```

三条规则分别演示三种写法：`on: "FRAME"` + `at`（定时投递，与 `events.jsonl` 一行逐字同形）、
`on: <事件类别>` + `if` + `permit`（写回响应，下一帧生效、只触发一次）、只 `emit` 的只读响应。
`tests/test_script.py::DemoPreset` 真跑 1300 帧，断言三件事都真的发生。

### 发版纪律：版本号不许只改一处

`tests/test_packaging.py::ReleaseDiscipline` 新增两条：
`pyproject.toml` 的 `version` 必须在 CHANGELOG 有对应的 `## vX.Y.Z` 小节；
`capabilities()["api_version"]` 必须等于 `kernel.api.API_VERSION`。

### 去重（不改变任何行为）

- 死因清单改由 `apps.conditions.known_names()` 单一提供（`tests/test_conditions.py` 不再手抄一份）。
- 锚定键 `serial:<n>` 的解析统一到 `apps.namer.serial_of`（`tools/_harness.py` 转出）。
- `tools/anomaly_check.py` 改用 `kernel.core.initial_state`，不再维护一份影子 `State` 构造。

## v0.1.1 — 2026-10-07 · 内核/用户态分层与八个系统调用（§3.1/§3.2/§D2/§D5）

> **补丁版（非破坏性）**：裁决帧、结论与 `digest` **一个都没变** —— `snapshot --fast` 6/6
> 逐位一致，全量 `selfcheck` 9 步全绿。故 **v0.1.0 的全部读数在本版仍然逐位成立，可以混引**；
> 本次**不触发** v0.1.0 指纹的重基线，`v0.2.0` 这个版本位仍然留给日后的破坏性变更。

### 目录：内核与用户态分成两个包（§3.1）

`engine/` 一分为二 —— 分层从"同一个目录里打标签"升级为**两个物理包 + 一条依赖方向**：

```
kernel/   纯逻辑内核（9 个模块）：位 / 变量域 / 个体 / 算子 / 帧 / 外生扰动 / 账本
apps/     用户态（12 个模块）：系统服务（裁决 / 消融 / 断言 / 不变量 / 特征 / 时间线 / 条件 / 服务束）
                             + 界面（命名 / 渲染 / 看板 / 可视化）
```

- 依赖方向只有一条：**`apps → kernel`**。三个红线工具随之改了扫描集合：
  - 红线 1（`grep_forbidden.py`）扫 `kernel/` **与** `apps/` —— 扫描集合与改造前**逐字相同**
    （原 21 个模块 = 现 9 + 12），「代码里写死剧情名词」的防线强度一分未减。
  - 红线 2（`stepwise_lint.py`）同样两层都扫：用户态也**不许预读未来**。
  - 红线 3（`layer_lint.py`）重写为**跨包方向检查** + **模块登记簿**：`kernel/` 里出现一行
    `from apps…` 即越界；两个包里冒出一个没登记的 `.py` 也要报出来（棘轮基线仍是 0）。
- 全仓 50 个文件、255 处 import 路径随之改写（`run.py` / `tools/*` / `tests/*` / CI / 打包清单）。

### 内核：控制流倒置，分层基线归零

内核（`kernel/`）不再 import 服务层。不变量检查 / 消融探针 / 裁决全部由应用层经
`run(..., rules=, runtime=, namer=)` 交入，内核只按名调用、不认识其逻辑：

- `runtime.checks` —— 不变量检查（原 `core → invariants`）
- `runtime.probe` —— 消融探针（原 `core → ablation`）
- `runtime.judge` / `runtime.inner_verdict` —— 裁决（原 `core → verdicts`）

`tools/layer_lint.py` 的棘轮基线由 **6 条收敛到 0**：内核一行 import 都不再往上。

### 预设：世界与剧情归一

- **取消 `data/` 目录**：默认机器规格迁到 `presets/_default/`。
- **取消「两层同名 + 隐式递归覆盖」**：预设自带 `genesis.json` 时，要么是一份**完整**规格，
  要么在 `preset.json` 里显式写 `"extends": "_default"` 声明继承（`refuted` 用后者）。
- 无预设 / `emergent` 显式回落到 `presets/_default/`。

### 剧情：六幕串成因果链

- `presets/plot` 的第 2–6 幕各加 `&& event("上一幕")` ⇒ 无论种子快慢，六幕必定按叙事顺序发生
  （原先各自独立，慢种子上可能乱序）。
- **仍然非破坏性**：seed 0 满预算轨道与 `digest` 逐位不变（8/8 指纹一致）。
- 顺带修掉 `apps/conditions.py` 的一个潜伏 off-by-one：`check()` 剥 `"event:"` 前缀时多剥一位，
  会把每个事件名的首字母切掉、误判为「未登记事件」（此前无预设用过 `event(...)`，故未暴露）。

### 其他

- 判据 6 的只读探针由守 `data/` 改为守 `presets/`（并改为递归指纹）。
- `--dump-anchors` 导出到本次运行所用预设的目录。

### 内核：8 个带版本号的系统调用（§3.2）

`kernel/api.py` 把"跑一次演算"拆成**可寻址的会话**：`load` / `step` /
`snapshot`·`restore` / `inject` / `observe` / `events` / `capabilities` / `version`。
`version()` 返回 `API_VERSION = "1"`。

- `core.run()` **退化为** `load(...).step(n)` 的组合，不是第二套实现 —— 演化语义一个比特都不加。
- `Session.step(n)` 可分段调用：世界状态走判据 4（帧截断复现）那条已证明过的路径。
  带 `when` 的投递由 `Session` 自己持有「待触发清单」（`Snapshot.armed` 一并封存），
  于是分段 `step()` 不会把已经触发过的条目重新武装。
- `step()` 执行期间，`observe()` 读的是内核当帧递来的**活状态镜像** ⇒ 事件回调里的条件
  与预设的 `when` 读到同一帧的同一份数。
- 应用仍通过 `runtime` / `namer` / `rules` 三个不透明句柄交入服务；内核一行都不 import `apps/`。

### 应用模型：`script.jsonl` 订阅 + 响应（§D2）

预设可以用 `script.jsonl` 把同一批投递写成**程序**，而不是日程表：

```json
{"on": "PROMOTION", "if": "promotions >= 8", "permit": "preset",
 "do": [{"emit": "…"}, {"inject": "suppress_slot:order:1"}]}
```

- `on: "FRAME"` + `at` ⇒ 编译成与 `events.jsonl` **逐字同形**的定时投递，走 `DataSet.add()`
  进世界；`from_events()` 是它的逆变换，故「脚本的退化形式 ≡ 旧日程表」是**可断言的等式**
  而不是"跑一遍看着像"。
- 其余 `on`（内核事件类别，见 `kernel/vocabulary.py::EVENT_KINDS`）⇒ 反应：条件成立就
  `Session.inject()`，**下一帧生效**，每条只触发一次。
- 三条硬闸门（启动即报，绝不静默）：订阅名必须是 `FRAME` 或已登记的事件类别；条件只许用
  `apps/conditions.py` 那门语言（构造上不可能预读未来）；非 `emit` 的写回必须申报 `permit`
  （`actors.json` 里的实体 id，或保留值 `"preset"`）。
- `events.jsonl` 与 `script.jsonl` **只许留一个**（同一条时间线的两种写法，同时存在即 `ConfigError`）。
- `run.py` 改用 `load().step()` 并把脚本接进事件回调；`--fast` 之前安装，脚本那些帧一并压缩。

### 接口纪律：ADR-0001（§D5）

- 新增 `docs/adr/0001-内核接口冻结与版本纪律.md`：8 个调用是全集；加第 9 个必须先写一页 ADR
  回答"现有 8 个为什么组合不出来"；破坏性变更升 `API_VERSION` major 并在本文件写明。
- 随 `.gitignore` 白名单与 `tools/export.py` 的打包清单放行 `docs/adr/`。

### 修复

- `kernel/api.py::Session.observe()` 用了 `CAPABILITIES` / `DEATH_CAUSES` 却没 import，一调即
  `NameError`（8 个调用的冒烟测试此前没覆盖到这一步）。
- `apps/conditions.py::check()` 拿 `event:<名>`（带前缀）去和裸事件名相减，导致**任何**
  `event("…")` 条件都被误判成「未登记事件」；恢复 `len()` 剥离前缀后，预设闸门重新成立。

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
