# 更新记录

> 每个版本的发布说明。发 GitHub Release 时，正文直接取对应小节即可。

## 未发布 — 独立终端窗口与叙事面板修复

> 只读层修复：`kernel/` 一个字节没动，指纹与 `tests/baseline.json` 不变（`0 drift`）。

### 修复

- **独立 CLI 窗口 10 秒后静默退出（关键）**：`apps/terminal_window.py` 连上主进程后没有取消
  `create_connection(timeout=10)` 留下的读超时，`for line in rf` 在两帧之间超过 10 秒就抛
  `TimeoutError`，窗口打印「无法连接主进程：timed out」后退出 —— 于是窗口只剩开头的几行，
  后面的 `>>>` 全落在主终端；`prompt` 也再没人问（主进程等满 `--terminal-window-timeout`
  后回落默认答案）。现在连上即 `settimeout(None)`。
- **场景面板整框可折叠**：`narrative_block_html` 外面再套一层
  `<details class="panel scene-panel" open>`（逐条仍是折叠的 `<details class="scene">`）；
  实时看板整块替换 `#narrative-block` 时会保留这一层的展开状态。
- **看板「对话阅读」→「终端记录」**：原来那框读的是 `CanonBundle` 里随便挑的一个
  `scene`（与本场演算无关），文字对不上任何东西。现在改为列本轨道**真的播过**的
  `messages.jsonl` 消息（新只读函数 `apps/terminal.py::played`：帧已到 +
  `require_event` / `suppress_if_event` 两条过滤），逐条带帧号。
- **原初小节不再画空图**：
  - 「锚点借还刻度」在没有 `nodes.json` 的 13 席剧情根上，改用 `traj.records` 里真实执行过的
    `origin_anchor` 事件（`plot` 一手 @33,594,510；`plot-full` 三手，另两手在 42,500 / 42,600）；
  - 「记忆阶段泳道」在没有记忆片段时不再摆空画布，直接写明缺的是哪种真实写入；
  - 「忆灵生命线」在没有忆灵时写明原初停在哪个形态、创世几次。

### 新增（`plot-full` 的原初内容）

- **内核新动作 `origin_anchor: bind_companion`**：把池里一个**既有个体**认作忆灵 ——
  不新占池位（`plot-full` 的池在 42,000 帧已满 416/416），形态抬到 2，此后转印 / 成长 /
  守席与「凝成的忆灵」完全同规；指名编号优先，缺省取池里适应度最高的非在席者。
  该个体打上 `origin_companion` 标记、寿命从这一刻另算（`origin_companion_span`）。
- **`plot-full` 的两手原初事件**：42,500 写入「救世主记忆」（初凝 / 同行 / 承忆 / 忆者
  四阶段）；42,600 认作忆灵、48,000 再认一次（第一任忆灵在 46,909 散掉）。于是看板的记忆
  阶段泳道有真实阶段、忆灵生命线有「凝 → 散 → 再凝」三段，报告【八】里
  `记忆片段 … 阶段4/4:忆者`、`忆灵 #…（在）· 认作忆灵 2 次`。
- **预设级参数**：`origin_create_min_form: 3`（忆灵形态不再触发创世，岁月那一席仍留空等回望）、
  `origin_companion_span: 3500`（忆灵寿命另算一条：第一任能活到 46,909 散掉，第二任活到冻结）。
  断言随之把 `origin_borrowed` / `origin_repaid` 从 1 改成 **4**（四手锚点）。
- **看板两处可读性**：锚点刻度在挤到同一像素时按顺序右移（42,500 / 42,600 现在各占一根刻度）；
  生命线的「凝 / 散 / 再凝」标签同样按 26 单位顺次让位，不再叠成一团；图下多一行
  `生命线：凝 @… · 散 @… · 凝 @… · 忆者 @… · 至今`。
- **回望节点表（只读清单）**：锚点图下面新增一块可折叠的「回望节点表 · 原著映射」，
  从原初世界的 `nodes.json` 读 20 个节点（帧 · 缺什么 · 修什么），并标明
  「本轨道不跑这套节点（只有 `--preset origin` 会执行）」—— 清单不是读数，不冒充。
- **实测**：全量 **67 秒**跑完、复用 33,545,001 帧（永劫回归没破）、18/18 断言 + 43/43 时间线、
  裁决 `origin_closed` @33,594,547。**不要**在该世界投 `seed_memory(factor_basis)`：写满十二行
  记忆会破掉死循环复用（实测两千万帧还没走到节点）。

### 终端去向

- **`--terminal-window` 时 `>>>` 只去窗口**：主控制台不再重复终端消息（`--log` 仍照常落盘），
  窗口起不来才回退同控制台。实测：主终端 `>>>` 0 行、窗口 73 行、日志 73 行。
- **演算结束窗口不自己关**：收到 `end` 后打一行「按回车关闭」就停住等人翻看；
  `TerminalBridge.close()` 也不再 `terminate` 已通知过结束的子进程（只有从没连上的才清掉）。

### CI 修复

- **`worlds/plot` 从未入过库**：`.gitignore` 只放行了 `worlds/origin` / `worlds/scepter`，
  于是 `世界根 → worlds/plot（nullify）` 在本机有、在 CI 没有 —— 指纹 job 与
  `test_snapshot` / `test_origin_plot` 全红。现在放行 `worlds/plot/`（`config/` 11 个文件）
  并随之提交，`dashboard/` / `logs/` 仍挡在外面。
- **依赖不入库语料的测试改为跳过**：`lore/story/`（原著卷与 `wiki_structured`）按设计不入库，
  CI 没有它 —— `test_scepter_dossier` 的逐行对账、`test_terminal_authority` 的两条
  （逐字覆盖 / 构建器幂等）改成「语料不在就 `skipTest`」，不再把「没有语料」判成失败。
- **判据 3（替代世界）卡在轮内配额**：`worlds/plot` 的 base `params.json` 带了 12 席口径的
  `round_succession_quota: 12`，替代世界只有 5 席，一轮内 5 次接掌后席位被冻住 ——
  再创世停在 10 次、走不到第四阶段（`converged=False`）。替代世界的数据现在写明
  `round_emergence_quota: 5`（按席位）、席间接掌不设上限（实测 19 次再创世、收敛 True）。
- **本地 `tools/selfcheck.py` 9/9 通过**（397.8s），`tools/snapshot.py --fast --no-digest`
  与记录一致。
- **分发包补齐 `worlds/` 与 `lore/`**：`tools/export.py` 的清单原来只有
  `kernel/apps/config/presets/tools/tests` —— 解压后 `--preset plot` 会静默退回 12 席、
  `--fidelity` 没语料、包内 `tools/selfcheck.py` 必红。现在把 `worlds/` 与 `lore/` 一并打进
  （按路径排除 `lore/_probe`、`lore/story`、`lore/export/data`、`worlds/generated` 与各世界根的
  `dashboard/`、`logs/`），并把 `CHANGELOG.md` 也放进包（`tests/test_packaging.py` 要读它）。
  实测：**649 个文件 · 6.2 MB**，解压后 `--preset plot` 是 13 席，包内单测
  **735 条全过**（1 条因缺 `CHANGELOG.md` 的错已修）。
- **删掉未使用的对话阅读器**：`apps/dialogue.py`、`tests/test_dialogue.py`、
  `TerminalFeed.play_dialogue`、`run.py` 的 `narrative.dialogue_scene` 分支（没有任何预设用过；
  看板那块早已换成「终端记录」）。baseline 重算：apps 29→28 模块、tests 62→61。
- **`_lookback_nodes` 不再写死预设名**：改为扫 `worlds/*/presets/*/nodes.json`（优先 `origin`，
  否则排序第一份），改名或换世界根都不会让看板那块清单静默消失。

## 未发布 — 剧情预设迁入十三席世界根

> **BREAKING（世界根 + 指纹）**：`plot` / `plot-full` 默认跑在 `worlds/origin`
> （`dim=13`、L12 是 meta 席、回望驱动 + 原初四态），不再默认跑项目根的 12 席世界。
> `tests/golden_fingerprints.json` 11 条按新世界根**整体重写**，`tests/baseline.json` 随之重写。
> 默认根 `config/`（12 席）与 `worlds/origin/config/` 的既有数值**一个字节都没动**。

### 破坏性变更

- **世界根解析规则**（`run.py::resolve_world_root` / `kernel.loader.preset_world_root`）：
  显式 `--root` 永远优先；不给时若 `worlds/origin/presets/<预设>/preset.json` 存在 ⇒
  `worlds/origin`；否则剧情预设 ⇒ `worlds/plot`，其余（含无预设的 `emergent`）⇒ 项目根 12 席。
  `python run.py --root . --preset plot` 可回到旧行为。
- **新增 13 席副本**：`worlds/origin/presets/plot/`、`worlds/origin/presets/plot-full/`
  （预设 / 事件 / 断言 / 时间线 / 消息 / 档案 / 锚定 / 词表 / 外部实体表）。
  `anchors.jsonl` 按 13 席**重新实测**：12 席的 curr / prev 编号全部换新，`serial:24997`（旧昔涟）
  与 `serial:26241`（旧负世执行人，本项目里另测的编号）不再保留 —— 前者改钉第十三席，
  后者由 `stall_seat:L00` 的受难之名承担；新增 `locus:L12` 与 `serial:29250 昔涟（CHR-002 /
  PhiLia093，L12 末态承载者）`。
- **裁决改变**：13 席根的结论词表只有「原初四态」，故 `plot` 的终局从 `overwritten`
  变为 `origin_closed`（@33,594,547）；`events.jsonl` 里那一手 `overwrite_conclusion`
  的目标随之改为 `origin_closed`（目标名必须存在于该世界的 `conclusions.json`，否则内核
  在结论里程碑处 KeyError）。断言 15/15 → **18/18**、时间线 29/29 → **30/30**；
  `plot-full` 同样 18/18 + 43/43。
- **回望 / 锚定落地**：`plot` 的 13 席副本**故意不写 `nodes.json`**（实测两条硬理由：
  ① 在 44,048 投 `seed_memory(factor_basis)` 会写满十二行记忆，原初的记忆承载 / 创世机制
  此后每帧改结构 ⇒ 世界不再冻结，33.59M 帧的永劫复用消失；② `kernel/core.py` 的死循环复用
  在 `inbox` 非空时 `cand = n + 1` ⇒ 只要收件箱里压着未到期的锚点就一帧都不跳，节点在冻结
  之后等于把全量运行拖成小时级）。回望改由 `events.jsonl` 的显式 `origin_anchor`
  （33,594,510，`bind_memory` L01）承担，锚定由浮黎的 `gaze.effect.anchor_past`
  （33,594,545）承担 —— 两者都实测生效：原初「借出 1 / 还上 1」，`emitted_fuli_anchor_past` 落账。
- **基线读数**（13 席根，seed 0）：`plot` 全量 世代更迭 **156** · 涌现 **2,166** · 迭代 52,411
  （复用 33,550,334 帧）· 13 席；`plot@3000` 换代 15 · 涌现 275；`plot@3000 seed 7` 换代 15 · 涌现 269。
  `nullify` 仍走 `worlds/plot`（13 席、canonical 动力学）：全量换代 36、涌现 425。
- **文档**：`README.md` / `docs/使用教程.md` 补「剧情预设默认跑在 13 席根」「回望 / 锚定在哪触发」
  与「`--root` 优先级」三节。

## 未发布 — 轮内配额与轮末结算

> **BREAKING（轨迹侧）**：涌现 / 接掌从「每帧自动刷新」改为**一轮之内陆续发生、轮末再创世时结算**。
> `tests/golden_fingerprints.json` 与 `tests/baseline.json` **重写**（11 条指纹的 digest 全部变化，
> plot / emergent / tide / nullify / destruction 的结构读数亦变；origin 三条只有 digest 变）。

### 破坏性变更

- **轮内配额**：`State` 新增 `round_emergence` / `round_successions` /
  `round_emergence_last` / `round_start_frame`；`config/params.json` 新增
  `round_emergence_quota`(12) / `round_succession_quota`(12) / `emergence_min_gap`(8) /
  `round_min_frames`(180)。一轮内涌现数、席间接掌数各自封顶；`PROMOTION` 须两条配额
  都满足（或已过 `round_min_frames`）才 +1 轮，并在轮末把两个计数清零。
- **涌现登记器**（`kernel/emergence.py`）：满配额即停、两次涌现至少隔
  `emergence_min_gap` 帧；续跑时用 `prime()` 把已登记过的人记为已登记，避免重放旧账。
- **剧情约束**：`presets/plot` / `plot-full` / `plot-mech` 在 3.0 起点帧 42000 投一手
  `recreate`（`payload.halt_emergence: true`）—— 只停涌现、不动席位动力学，此后只剩
  既定十二人。`recreate` 的默认语义（`seats_frozen`，全停）保持不变。
- **基线重写**：golden 11 条的 digest 全变；`plot` 全量换代 82→97、`nullify` 全量
  81→96，两者涌现都从 1,58x 降到 1,098（3.0 起不再增长）；`destruction@8000` 涌现
  202→132、`emergent@1500` 166→108、`tide@6000` 吞没 552→468。
  `baseline.json` 已按当前工作区重算（其中也包含上一节「权杖级叙事重建」尚未提交的
  文件 / 语料计数）。

## 未发布 — 权杖级叙事重建

> **BREAKING（叙事侧）**：叙事面板从「跑完一次性渲染」改为**随演算逐轮增量出现**；
> `tests/baseline.json` 按新增语料与模块**重写**（`canon_entries` 1,429 → 31,140）。
> **内核与 golden 指纹零变化** —— `kernel/` 与 `tests/golden_fingerprints.json` 一个字节没动。

### 破坏性变更

- **初始变量集语义收敛（BREAKING）**：世界形态由 `--init-set` 的初始变量集决定，
  `seed` 只是抽样键并写进 `init-*.json`；`--init-set` 与 `--seed` 同用**直接报错**。
  同时给 `config/generation.json` 增两项结构性 knob：`succession_floor`（承位稳定帧）
  与 `stage_budget`（阶段帧预算；按同一倍率缩放 genesis 里逐档的 `domain_dwell`）。
- **移除 `--fast` 别名**：`run.py` 只保留 `--explore`（两者本来就等价，别名已无意义）。
  注意：`tools/*.py` 里的 `--fast` 是另一个东西（内核 `load(fast=K)` 的提速因子），保留。
- **叙事由一次性改为逐轮**：`--serve` 时场景在 `PROMOTION` / `DOMAIN_ADVANCE` /
  `DOMAINS_EXHAUSTED` 三个推进点按差集推送，同一 id 只推一次；终稿与实时共用
  `scenes.load_all` + `narrative_block_html`，不再有两套渲染路径。
- **基线重写**：`canon_entries` 1,429 → **31,140**、`lore.files` 183 → **192**、
  `apps` 文件 28 → **30** / 模块 27 → **29**、`tests` 52 → **56**；`canon_digest` 随语料更新。
  `presets`(11) / `tools`(36) / `golden_fingerprints` 不变。

### 八项能力

1. **趋势面板 13 字段全接线**：可见 4 项（`trend` / `channel` / `value` / `active`）+
   元数据 9 项（`type` / `target` / `observable` / `source` / `confidence` / `inferred` /
   `driver` / `driver_value` / `note`）。复用既有 `.bar` 组件；缺值一律 `—`、条留空，
   未接线趋势单独列出并写明原因，不隐藏、不补零。
2. **wiki 全量语料入库**：`scenes_wiki.jsonl` 66 · `dialogues_wiki.jsonl` 26,612 ·
   `options_wiki.jsonl` 2,167 · `terminals_from_wiki.jsonl` 294 · `battle_line` 572；
   构建器 `tools/lore_build/build_wiki_scenes.py`。
3. **场景带帧**：`apps/scenes.py` 的 `load_all(upto_frame=)` 合并剧情目录与任务场景，
   首帧取预设节拍；无节拍佐证的 wiki 场景按章节区间**投影**，标
   `first_frame_source:"projected"`、`confidence:"C"`，`gap` 注明「非原文时序」。
4. **实时叙事**：`apps/live.py` 新增 `narrative` 快照，`apps/viz.py` 提供
   `narrative_block_html` / `#narrative-block`，`run.py` 的 `_scene_pusher` 只在三个推进点推差集。
5. **心智层 shadow**：`apps/mind.py`（`MindState` / `decide` / `MindShadow`）只读、默认不装；
   `apps/agents.py` 的 `Card.decide` 委托给 `mind.decide`（中性 persona，评分并列 ⇒ 仍按
   `(priority, rule id)` 决定），返回形状不变。
6. **初始变量 A/B**：`config/generation.json` 增 6 个可覆盖 knob（含结构性的
   `succession_floor` / `stage_budget`）；
   `presets/scepter/init-A.json` / `init-B.json` 含 `seed` 与六项倍率；`run.py --init-set A|B`
   只在内存覆盖并受 clamp（与 `--seed` 互斥）；
   `tools/init_diff.py` 找第一处分叉帧、事件差与末帧读数差。
7. **终端权限分层**：`presets/plot-full/messages.jsonl` 扩到 **271 条**，每条带
   `authority`（`guest` / `user` / `admin` / `kernel`）；`run.py --terminal-authority` 只显示选定层。
   **来源修正**：终端只取自剧情卷里的 `>>>` 行（3.4 / 3.5 / 3.6 / 3.7 = 61 / 1 / 54 / 80 条）
   与 `Δ-me13.exe` 权杖档案页；3.0–3.3 原卷一条 `>>>` 都没有，该段只保留手写的
   6 / 0 / 1 / 1 条，**删掉了先前「借帧凑到每章 12 条」的编造接线**。每条带
   `source`（`S-024:amphoreus_3.4.md#L2981`）与 `frame_source`（`anchor` / `projected` / `loop`）。
8. **权杖世界根**：新增 `worlds/scepter/`（13 席 config + `presets/scepter/`）与 `apps/scepter.py`；
   `run.py --scepter` 输出报告【九】（与保真同开顺延【十】）七层读数；看板追加权杖块。
   读不到的字段写 `null` + `unavailable_reason`；`regen` 的 17 个锚点与上限来自语料，不是演算读数。
9. **权杖档案**：新增 `lore/D6_terminal/scepter_dossier.jsonl`（`Δ-me13.exe` 的 467 行原文 →
   361 条正文 + 106 条标题转 section 路径；`进度：N%` 标 `kind: "progress"`）；
   `apps/scepter.py` 增加只读统计并让报告【九】多一行「档案 … 行 / … 段 / 进度里程碑 …」。

### 测试

- 新增 9 组契约：`test_viz_trend_panel` / `test_wiki_corpus` / `test_scene_timeline` /
  `test_live_narrative` / `test_mind` / `test_init_diff` / `test_terminal_authority` / `test_scepter` /
  `test_scepter_dossier`。

### 验证

- `python tools/baseline.py --check` → **0 drift**（重写前后唯一变化见上「破坏性变更」）。
- `python -m unittest discover -s tests -q` → **Ran 692 tests in 260.1s, OK**。
- `lore_lint` 0/0 · `lore_compile --check` canon ok · `fidelity_report --check` 通过。
- `layer_lint` / `grep_forbidden` 全过；`kernel/` 与 `apps/` 零专名。
- 保真分 **0.9135**（与上一节逐维一致）：D1 0.9048 · D2 0.9440 · D3 0.9353 · D4 0.9927 ·
  D5 0.9806 · D6 0.9898 · D7 0.6153 · D8 0.9453；缺口按实测，未调权重。
- 短帧冒烟：`run.py --preset plot-full --frames 200` 与
  `run.py --root worlds/scepter --preset scepter --frames 50 --scepter` 均可运行。

---

## 未发布 — 原初世界与叙事层（第十三席真实动力学）

> **非破坏性（对 canonical）**：`config/`、`presets/plot` 零改动，`snapshot --fast` 六条指纹逐位一致；
> `presets/plot-full` 是新增内容版，不纳入旧基线；所有新动力学都住在独立世界根 `worlds/origin/`。

### 独立世界根与第十三席

- `run.py` 新增 `--root <dir>`：`Config` / `DataSet` 从该根的 `config/`、`presets/` 读取；
  日志 / 看板 / anchors 路径跟随 root，`TerminalBridge` 的程序路径仍用项目根。
- 新增 `worlds/origin/`：13 席配置（`dim=13`、`mapping` 13×6、`capability_names` 13 项），
  `L12` 标记 `"meta": true` —— 普通个体可占据，但 `Register.complete()` / `Promotion` /
  `Ablation` / `Verdicts` / `Invariants` 一律跳过它，12 因子判据不受污染。
- `State.origin` 与 `OP_ORIGIN`：自我度 / 能量 / 生命周期 / 消散；创世、爱、开拓三面都是真实反馈。
  `world_signature()` 只放 `filled` / `closure` 结构标志，连续量只进 `digest`。
- 结论四态：`origin_closed` / `origin_open` / `origin_unstable` / `origin_absent`；
  报告【八】在 origin 世界读真实 `traj.final.origin`，canonical `plot-full` 仍走只读探针。

### 回望：锚点注入 + 固定点重演

- `nodes.json` 列出关键节点（`frame / seat / missing / repair / cost`）；第一遍正向扫描，
  第二遍从帧 0 重演并在缺失帧投递 `origin_anchor`，新缺失并入锚点继续迭代（`origin_max_iters` 上限）。
- 每一遍严格单向、逐帧可复现；**没有**逐帧反向因果，也没有回写历史帧。
- 锚点稳定、无缺失、`repaid >= borrowed`、selfhood 达标 ⇒ `origin_closed`。

### 忆灵、记忆、命途与剧情接线

- 忆灵是真实派生个体：四段成长（初凝 / 同行 / 承忆 / 忆者）、独立寿命、独立守席、再印。
- 记忆：十二行逐席、effect 族、持续记忆场、多阶段、每阶段场景文案。
- 命途 / 星神 / 令使：`State.paths` / `authorities` / `grants` + `OP_PATH`，只在启用世界里跑。
- `worlds/origin/story.jsonl` 把 **33 个 plot 节拍**挂到登记断言与真实读数上（33/33 动态）；
  `tests/test_story_coverage.py` 守住 ≥90%、拒绝把 `emitted_events` 当证明。

### 只读叙事层（canonical 也可用）

- `apps/terminal.py` / `terminal_bridge.py` / `terminal_window.py`：`messages.jsonl` 的 `>>>` 终端层，
  非 TTY 自动用默认答案；`apps/archive.py`：实验档案 / 异常记录 / 进度里程碑（报告【六】【七】）；
  `apps/origin.py`：canonical 的原初只读探针（报告【八】）。
- 新增内容版预设 `presets/plot-full/`：补齐 3.0–3.3 / 3.5–3.7 镜头与终端消息、档案；
  新增桥段一律 `emit`，`plot` 的轨道、断言、时间线与指纹原样保留。

### 指纹覆盖扩展到独立世界根

- `tools/snapshot.py` 的条目支持 `root` 字段：缺省走项目根，带值时 `DataSet` / `Config` 从该根的
  `config/`、`presets/` 读取；条目键在带 root 时写成 `root@preset@seed@frames`，旧键原样兼容。
- 新增三条独立世界指纹：`origin@0@6000`（快，开局到唤醒）、`origin@0@None`（全量，约 12s）
  与 `origin-eternal@0@None`（全量，约 21s）。此前 `worlds/` 下的原初世界完全不在指纹覆盖内，
  改 `nodes.json` / `params.json` 不会被自动拦截。
- 指纹总数 8 → 11；`tests/baseline.json` 随之更新。

### 初始变量与世界生成（P3）

- `config/generation.json`：声明 20 个生成维度，其中 **8 维可采样**（物理 / 地理 / 聚落 / 人口 /
  文明 / 政治 / 黑潮 / 协议）、12 维继承；10 个旋钮各自带取值域、夹取区间与流标签。
- `apps/worldgen.py`：`derive_stream`（每旋钮独立流）/ `bootstrap_world`（从冻结模板派生）/
  `build_files` / `write_world` / `diff_dimensions`。所有抽样一律标 `inferred`：
  官方文本没有随机种子机制，`--seed` 只是初始变量的抽样键。
- `tools/worldgen_probe.py`：生成、种子分叉报告、`--check` 重建比对。
- `tests/test_worldgen.py`：7 项契约（20 维声明、同键确定性、异键分叉、模板哈希稳定、
  约束成立、canonical 不被写、抽样项标 inferred）。
- 生成世界只写入 `worlds/generated/`（已被 `.gitignore` 挡住），不回到 `config/` 与 `presets/`。

### 趋势与通道（P4）

- `config/trends.json`：8 条趋势；**4 条已接线**（`TREND-001` 熵、`TREND-003` 双通道、
  `TREND-004` 噪声、`TREND-006` 记忆），共 5 条通道；另 4 条显式 `unwired` 并写明缺什么读数。
- `apps/trends.py`：多通道求值，三种形态（饱和 / 阈值 / 线性截断）；只读、无内部状态，
  缺读数时返回 `driver_missing` 而不是猜 0。
- **通道不互相抵消**：`TREND-003` 同时挂「延迟破壳」与「强化倾向」两条通道，并排上报；
  强化通道读账本里的 `embers_taken`，不写死「每轮十二枚」。
- `tools/trend_audit.py`：规格审计（驱动量 / 目标 / 形态 / 来源 / 置信度）+ `--demo` 演示。
- `tests/test_trends.py`：11 项契约（双通道独立性、单调有界、阈值、缺读数、确定性、覆盖率）。

### 角色心智（P5）

- `apps/agents.py`：从编译语料载入 27 张角色卡；`decide(card, percept)` 按 `when` **精确匹配**
  （不做语义猜测），同一条触发命中多条规则时回报 `ambiguous` 与全部候选；`when` 为 `UNKNOWN`
  的规则**不可执行**，不会被当成通配符。另提供关系增减（纯函数、带夹取）、情绪查表、说话画像。
- `tools/character_audit.py`：卡片体检（≥3 规则、规则必须有来源）+ 81 条场景全量回放。
- `tests/test_agents_contract.py`、`tests/test_character_consistency.py`：17 项契约。

### 只读叙事层（P6a）

- `apps/dialogue.py`：对话链运行器（`next` 构成的有向链）；多后继必须显式选择，悬空链接报错；
  只读、可重置、保留来源与 locator。
- `apps/logs.py`：轮回账本读取；只接受 `official / reconstructed / inferred` 三种标签，
  缺来源直接拒绝；提供按轮次、按阶段、覆盖率的只读统计。
- `apps/terminal.py` 升到 v2（ADR-0004）：选项可写对象形式（`id` + `label`），兼容旧的字符串；
  新增 `on_choice{jump, inject, rejoin}`、`branch` 标记与 `ledger()` 作答记录；默认路径仍用
  `default` 自动作答，`--terminal-ask` 才停下询问；跳转只允许向前，超限自动回到顺序播放。
- `tools/messages_lint.py`：默认值、分支目标存在性、`rejoin` 位置、分支未声明回归点等检查。
- `presets/_branch-demo/`：可运行的分支演示；**默认走「（成像）」，与原著的玩家选择一致**，
  交互可改选「保持沉默」。两条分支文案均标注「演示用，非原著文本」。
- 测试：`test_dialogue.py`、`test_logs.py`、`test_terminal_branch.py`（共 25 项）。

### 场景过程化（P6b）

- `apps/scenes.py`：把 12 条 `PLOT-*` 扩写编译成场景目录；`narrate()` 展平为
  before / during / after 三段；`dag()` 只按章节顺序连**线性链**（语料只证明了顺序，
  没有证明更多边，故不虚构 DAG）；`unresolved()` 检查台词、场景、机制引用。
- `tools/scene_lint.py`：章节覆盖、引用可解析、DAG 完整性；**3.4 的缺口按 CF-007 保留为
  warning，不补、不猜**。
- `tests/test_scenes.py`：7 项契约。

### 保真评分与呈现（P7）

- `config/fidelity.json`：八维权重、总分阈值、单维下限、覆盖标记、来源字段、缺口规则；
  分数、阈值、扣分上限全部在配置里，代码里不写任何分数。
- `apps/fidelity.py`：只读评分。每维四项指标 —— 覆盖率（部分 / 未知 / 缺口记录一律折分）、
  可追溯率（`UNKNOWN` 视为缺失）、A 级逐字率（只在有 `confidence` 的记录上计算，无证据则记 `—`
  并从加权均值里剔除）、一致性（场景规则回放 / 场景引用解析）。随后按缺口规则扣分：
  章节归属 UNKNOWN（1/8）、触发 UNKNOWN 的场景（6/81）、社区渠道（9/14 缺口，5/14 有结果）。
  缺口条目一条不删，扣分照算。
- `tools/fidelity_report.py`：真门禁。`--json` / `--md` / `--check`，低于阈值或单维低于下限即退出码非 0。
- 呈现（只读）：`apps/render.py` 的趋势压力条（同一趋势的两条通道并排显示，不合并）、
  场景面板（`scenes.narrate`）、对话阅读器（`dialogue.read_scene` + `TerminalFeed.play_dialogue`）；
  `apps/viz.py` 的 `narrative_panels_html` 把三块接进可视化页。全部只读，删掉演算逐帧不变。
- `run.py` 新增 `--fidelity` / `--panels`（也读预设的 `narrative.fidelity` / `narrative.panels`）；
  终端层可用 `narrative.dialogue_scene` 播放一个对话场景。**默认全关，既有报告逐字不变。**
- `tests/test_fidelity.py`：15 项 —— 阈值一致性、缺口计数、只读与幂等、默认关闭时报告不变、
  两条通道并排、对话阅读器不替读者选分支。

### 验证

- 全量单测通过（基线 508 项）；`snapshot --structural` canonical 逐项一致。
- `snapshot`（含 digest）11/11 一致：8 条 canonical + 3 条 `worlds/origin`。
- 世界生成：`--seeds 0,7,42` 两两分叉 8/8/7 维；`worlds/generated/seed000` 15 文件、`--check` 通过，
  可直接 `run.py --root ... --preset _default` 跑通 600 帧（122 位个体）。
- 趋势：`trend_audit --demo` 得 delay 0.965 / tendency 0.9997 / entropy 0.767 / memory 0.617，
  噪声未越阈（0.000）；`--check` 0 错；11 项契约测试通过。
- 角色：27 张卡 / 81 条规则 / 75 条可执行；81 条场景回放得 **75 pass · 0 mismatch · 6 unknown**，
  可执行部分通过率 100%；`character_audit --check` 0 错；17 项契约测试通过。
- 叙事：`messages_lint --check` 5 个文件 0 错；`_branch-demo` 默认路径输出「（成像）→ 分支 A → 回到主线」；
  对话/日志/分支三组测试 25 项通过。
- 场景：12 条、8 章中 7 章有场景（3.4 按 CF-007 留空）、线性 DAG 11 条边；
  `scene_lint --check` 0 错；7 项契约测试通过。
- `origin`：`origin_closed`；锚点 9 条（节点表扩充后，测试只钉住「≥5 且首条为 seed_memory」，不再写死条数）。
- `origin-eternal`：53 条断言全过 / 40 条时间线全过 / `origin_closed` / 复用 33,580,277 帧。
- `grep_forbidden` / `layer_lint` / `stepwise_lint` 全过；`kernel/` 与 `apps/` 零专名。
- 保真：八维加权 **0.8969**（阈值 0.85，单维下限 0.50），D7 社区 0.58 为最低项；
  缺口按实测计 —— 章节 1/8、未知场景 6/81、渠道 9/14；`fidelity_report --check` 退出码 0。
  （这是本节当时的读数；语料层后续已把总分升到 **0.9135**、渠道缺口降到 7/14，见下一节。）

## 未发布 — 语料层（BWIKI 3.0–3.7 入库 · `preset_beat` 反查）

> **非破坏性**：`kernel/` 零改动；`presets/plot` / `plot-mech` / `nullify` 的动力学与 payload 一个字节没动
> （只改了 label 与新增只读字段）；`plot-full` 仍不在旧指纹基线内。

### 语料

- BWIKI 3.0–3.7 全量入库：**66 个任务 · 94 个事件 · 26 条场景扩写 · 37 个预设节拍 · 282 条终端 · 27 条社区碎片**
  （canon 合计 **1,429 条 / 57 个文件**）。
- 等级口径不变：wiki 是 **B 级**，`verbatim_claim:false`，不进 A 级逐字分母；
  只有 `S-001` / `S-002` 的逐字算 A。**「已补全」仍为 0 条**——没有 A 级过程逐字就不写。

### 新增能力

- **`preset_beat`**：`lore/D3_plot/preset_beats.jsonl` 注册为 canon kind；每条把预设事件
  （`frame + payload`）映射到 `PLOT-* / EVT-* / TRM-*`。
- **反向查询**：`CanonBundle.beats_for(ref, preset=None)`，一条剧情能查出「哪些预设节拍演到了它」。
  场景面板（`--panels`）已接上，会多打印一行「预设节拍：帧·PB-id（哪些预设）」。
- **双向关联**：`presets/plot*/events.jsonl` 的事件带 `lore_ref`，脚本双轨的无损往返仍然成立。

### 修正

- **CF-008**：3.7 章节名是「成为昨日的明天」；「记忆是梦的开场白」属匹诺康尼 **3.8** 终末任务，
  此前归档错误。3.7 的 EVT/WC/PLOT 已统一。
- **CF-009**：事件 / 概述的版本号整体偏移一档，已按任务 ID 段位统一改号（旧值留在冲突表里）。
- **删除「权杖爆炸」**：3.0–3.7 没有这段剧情；最接近的只有「赞达尔引爆星核清洗权杖」的背景事件、
  「让权杖报废」的口头计划与三月七的玩笑。预设事件改为 `core_siege`。
- **D7 社区补检索**：渠道 5/14 → **7/14**，新增 14 条碎片与 3 条证伪（DB-006..008）；
  另外 5 个渠道是登录墙/反爬，如实计为缺口。

### 门槛

- `python tools/fidelity_report.py` → **0.9135**（阈值 0.85）：D1 0.90 · D2 0.94 · D3 0.94 · D4 0.99 ·
  D5 0.98 · D6 0.99 · D7 0.62 · D8 0.95。
- `python -m unittest discover -s tests -q` → **616 tests OK**。

---

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
