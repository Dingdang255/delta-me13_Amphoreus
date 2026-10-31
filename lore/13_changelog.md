# 13 Changelog

## v1.22 — 2026-10-31（`preset_beat` 注册为 canon kind；新增 PLOT→节拍 只读反查）

### 入库

- `D3_plot/preset_beats.jsonl` 正式注册为 canon kind **`preset_beat`**：
  - `tools/lore_lint.py`：KINDS 增加 `preset_beat`（必填 `frame/label/lore_refs/source`，来源必填），ID 规则 `PB-###`；
  - `tools/lore_compile.py`：OUT_NAMES 增加 `preset_beat → preset_beats.jsonl`；
  - `apps/canon.py`：`JSONL_KINDS` 与 `KIND_PRIORITY` 纳入 `preset_beat`。

### 查询

- 新增只读查询 `CanonBundle.beats_for(ref, *, preset=None)`：
  返回 `lore_refs` 含 `ref` 的节拍，按 `frame` 升序；可按 `presets` 再筛；查不到返回空列表（不抛错）。
  例：`beats_for("PLOT-011")` → PB-014/024/026/028/031/032。

### 测试

- `tests/test_canon_contract.py` 新增 `PresetBeatQueryTest`（3 个用例）：反查命中且升序、`preset` 过滤、未知 id 返回空。

### 影响

- canon 条目 **1,392 → 1,429**（+37 节拍）；`baseline.json` 随条目数重写。
- 八维保真分不变：`preset_beat` 不属于任何维度。

### 校验

- `lore_lint` **0 errors / 0 warnings**（`preset_beat` 37 条，必填 `frame/label/lore_refs/source`）。
- `lore_compile` **1,429 条 / 57 文件**（新增 `preset_beats.jsonl`）；`--check` canon ok；`baseline --check` 0 drift。
- 反查自检：`beats_for("PLOT-011")` → PB-014/024/026/028/031/032；`beats_for("PLOT-014")` → PB-034/PB-004/PB-018。
- `python -m unittest discover -s tests -q` → **Ran 615 tests in 232.3s, OK**（新增 `PresetBeatQueryTest` 3 例）。
- 保真分仍 **0.9135**（`preset_beat` 不进任何维度）。

> 注：中途两次全量测试被残留的 python 进程拖死（exit -1），清掉后重跑通过，代码本身无问题。

---

## v1.21 — 2026-10-31（删掉「权杖爆炸」：wiki 侧复核确认 3.0–3.7 无此剧情）

### 依据（wiki 侧复核，全文 8 卷）

- **3.7 魔女的孤诣课题**：螺丝咕姆「"赞达尔"引爆了一颗星核，只为彻底"清洗"权杖系统」——这是**背景事件**，
  同一任务梗概写「内核层严重损毁，宛如废墟」，玩家看到的是爆炸后的废墟。
- **3.7 星路长驰，穹宇远征**：黑塔称将从外部攻击德谬歌矩阵，「一定能让这台铁疙瘩彻底报废」——**计划，未写成功**。
- **3.6 重逢啊，笑泪相拥的约定**：三月七「只要黑塔女士愿意，她随时可以掏出虚数武器，把这台'权杖'炸个灰飞烟灭」——**玩笑**。
- 3.4「巨大的爆炸粉碎了世界」指演算出的世界崩坏；3.3 艾格勒胸口爆炸生成黑潮核心；3.4 来古士的「一场爆炸后基本粒子诞生」是宇宙起源比喻。**均非权杖本体**。
- 结局（3.7 落英）：铁墓静默、昔涟逆时收束因果，**权杖没有被炸掉**。

### 变更

- `presets/plot-full/events.jsonl`：`33594530` 的 `wand_explosion` → **`core_siege`**，
  文案改为「黑塔与螺丝咕姆自外部持续攻击德谬歌矩阵，誓让权杖报废（是计划，原文未写成功）」，补 `lore_ref:["PLOT-011"]`。
- `presets/plot-full/timeline.json`：断言 `N41_WAND` → **`N41_CORE_SIEGE`**（`value: core_siege`，`by: 33594535`），标签同步。
- `D3_plot/preset_beats.jsonl`：`PB-031` 由 `match:none` 升为 **`partial`**、`lore_refs:["PLOT-011"]`，`note` 记录上述四处原文。
- 此前 v1.17 里「唯一没有映射的是 wand_explosion」的表述，由本条取代。

### 校验

- `plot-full` 37 行 `compile_rules(from_events(rows)) == rows` → True；`PB-031` 的 `lore_ref` 可解析。
- `lore_lint` 0/0 · canon 1,392 条 / 56 文件 · `baseline --check` 0 drift。
- `python -m unittest discover -s tests -q` → **Ran 612 tests in 238.2s, OK**。
- 保真分不变（preset 内容不进八维评分）。

---

## v1.20 — 2026-10-31（D7 第 2 轮补检索：渠道 5→7，碎片 13→27）

### 入库

- `D7_community/fragments.jsonl`：新增 **CM-014..CM-027**（14 条）。
  平台分布：TapTap 4、贴吧 3、B 站 2、YouTube 2（仅标题/ID）、攻略站 2（Fandom / Moyens）、NGA 1。
  `supported` 5 条、`unverified` 9 条；来源等级 C 10 / D 4；无同人二创。
- `D7_community/crosscheck.jsonl`：新增 **CC-014** —— CM-022「逆时闭合因果」vs CM-023「永恒循环」的术语分歧。
- `D7_community/debunked.jsonl`：新增 **DB-006..008**
  - DB-006（CM-014）德谬歌不是昔涟制造的 NPC，而是权杖原本的演算目标／翁法罗斯之心；
  - DB-007（CM-016）永劫回归已进入最终阶段（33550337），不是「无限轮回继续」；
  - DB-008（CM-027）「402,604,032 颗火种」是 12×33,550,336 的自算值，A 级只有概数（同 CF-001）。
- `D7_community/channel_matrix.md`：重写为两轮合并视图。

### 口径修正

- `config/fidelity.json` 的 `channel_missing`：`observed` 5 → **7**（有结果的渠道：B 站、米游社、贴吧、NGA、YouTube〔部分〕、攻略站、其他）。
  登录墙/反爬的 5 个渠道（小红书、微博、Reddit、HoYoLAB、X）仍计为缺口，**不当成「无内容」**。
- `lore/00_manifest.md`：D7 条数与 D3 的 `preset_beats(37)` 同步。

### 结果

- canon 条目 **1,374 → 1,392**（+14 碎片、+1 交叉核对、+3 证伪）。
- **D7 0.58 → 0.62**：缺口罚分从 9/14×0.30 = −0.193 降到 7/14×0.30 = −0.150；
  代价是覆盖从 0.58 降到 0.55（新增 9 条 `unverified` 计入 0.25 分），这是如实计入，不刷分。
- **加权保真分 0.9092 → 0.9135**。

### 校验

- `lore_lint` 0/0 · `lore_compile` 1,392 条 / 56 文件 · `--check` canon ok · `baseline --check` 0 drift。
- `python -m unittest discover -s tests -q` → **Ran 612 tests in 232.6s, OK**。
  其中 `test_fidelity.py` 的 D7 期望值随口径更新：`channel_missing.count` 9→7、`fragment` 13→27。

---

## v1.19 — 2026-10-31（CF-008 纠正：3.8 归属；plot-full 补齐 4 段未演剧情）

### CF-008 纠正

用户指出：**「记忆是梦的开场白」是匹诺康尼 3.8 的终末任务**，不是翁法罗斯 3.7 的章节名，也不是 3.7 的别名。
已改写 CF-008 的 `assessment`：3.7＝成为昨日的明天（用户确认）；`S-001:107177` 归 3.8；
107169–107178 的 10 条章节名不能按 8 个版本一一对齐，映射仍需逐条核对。

### plot-full 补齐 4 段此前未演的剧情（纯 emit 镜头，不改动力学）

| frame | 新事件 | 对应 lore |
|---|---|---|
| 17000 | `grove_falls` 黑潮倾覆神悟树庭（瑟希斯火种三分、缇安开百界门） | PLOT-014 |
| 21000 | `anaxa_bargain` 那刻夏与元老院交易、登泰坦断崖 | PLOT-015 |
| 33594270 | `kleodra_council` 同盟会议与讨伐法吉娜的战令 | PLOT-020 |
| 33594310 | `undersea_500` 海底五百黄金裔与「律法」真相 | PLOT-021 |

- 只加到 `plot-full`（其定位本就是「plot + 纯 emit 镜头」），**plot / plot-mech / nullify 一字未动**，
  因此 `plot` 的 golden 指纹不受影响。
- `preset_beats.jsonl` 追加 `PB-034..037`（37 条），每条带 `lore_ref`。
- `plot-full/preset.json` 的 `_comment`：13 条镜头 → **17 条**。

### 校验

- `compile_rules(from_events(rows)).scheduled == rows`（plot-full 37 行）→ True。
- 37 条 `preset_beats` 的 `lore_refs` 全部可在 canon index 解析；`frame+payload` 与三个预设逐条一致。
- 事件帧号单调不减。

---

## v1.18 — 2026-10-31（CF-008 关闭：3.7 章节名定为「成为昨日的明天」）

### 依据

用户确认：游戏内 3.7 的章节名就是「成为昨日的明天」。S-001 章节表（107169–107178，10 条名对 8 个版本）
中的「记忆是梦的开场白」(107177) 当时被误判为 3.7 的相邻别名；**该判断已由 v1.19 纠正**——
107177 属匹诺康尼 3.8 的终末任务，与翁法罗斯 3.7 无关。

### 变更

- `04_event_index.jsonl`：`EVT-008` 名称 → 「成为昨日的明天（主线 3.7）」；
  `EVT-071/072/073/074/093/094/095` 的 `chapter` → 成为昨日的明天，移除重复的 `wiki_chapter`，保留 `conflict_refs:["CF-008"]`。
- `D3_plot/wiki_claims.jsonl`：`WC-020..022` 的 `chapter` 同步。
- `D3_plot/plot_expansion.jsonl`：`PLOT-011/012/024` 的 `chapter` 同步。
- `10_conflicts.jsonl`：CF-008 `pending` → **`resolved`**，`versions` 追加用户判定，`assessment` 重写。
- `D3_plot/coverage_matrix.md`：3.7 行章节名与「版本归属证据强度」表同步。

### 结果

9 条冲突现已 **9 resolved / 0 pending**（CF-001..009；CF-003 是分层解释，不是矛盾）。

### 校验

- `lore_lint` 0/0 · `lore_compile` 1,374 条 / 56 文件 · `--check` canon ok · `baseline --check` 0 drift。
- `fidelity_report` 0.9092 / 0.85 / 通过（章节名不参与评分）。
- `python -m unittest discover -s tests -q` → **Ran 612 tests in 229.8s, OK**
  （含 `test_script.py` 的双轨等价断言，确认 apps/script.py 的 `lore_ref` 改造未破坏往返）。

---

## v1.17 — 2026-10-31（方案 B：preset 事件带 lore_ref，双向可 join）

### 变更

- `presets/{plot,plot-mech,plot-full,nullify}/events.jsonl`：每条节拍新增 `lore_ref`（字符串数组），
  值取自 `D3_plot/preset_beats.jsonl` 的 `lore_refs`。共注入 **86 条**：
  plot 20 / plot-mech 21 / plot-full 32 / nullify 13。
  唯一没有映射的是 `frame 33594530 wand_explosion`（lore 无对应记录），保持无字段。
- `apps/script.py`：把 `lore_ref` 纳入脚本双轨的**无损往返**——
  `from_events` 搬运 `lore_ref`、`_norm_rule` 校验其为非空字符串数组、`_record` 原样写回。
  这是通用溯源字段，不含任何专名（`grep_forbidden` 仍为 0）。
- `worlds/origin/story.jsonl`、`worlds/origin/presets/origin-eternal/events.jsonl`（**经授权解冻**）：
  「理性与岁月两位泰坦先后陨落」→「先后退场」；`N24_ARC_3_3B` 的「万敌缇宝缇宁牺牲」→「万敌与缇宁牺牲」。

### 校验

- 四个 `events.jsonl` 的 `compile_rules(from_events(rows)).scheduled == rows` **全部为 True**（逐字往返不变）。
- 与 `HEAD` 对比：四个文件的 `(frame, payload)` 序列**完全一致**，只多了 `lore_ref`、只改了 label。
- `presets/**/*.json*` 全部可解析；`lore_lint` 0/0；`baseline --check` 0 drift；`canon ok`；
  `grep_forbidden` 0；保真分 0.9092 不变。
- 未跑测试套件（按你的选择）。

---

## v1.16 — 2026-10-31（修正 preset 的 4 处叙事错误）

### 变更（只改 label / why 文案，payload 与 selector 一字未动）

| 位置 | 原文 | 改为 |
|---|---|---|
| 18400 | 理性与岁月两位泰坦先后**陨落** | 先后**退场** |
| 36000 | 万敌、**缇宝**、缇宁相继牺牲 | 万敌、缇宁相继牺牲 |
| 42000 | 此后每一世白厄杀死**新生的小昔涟** | 此后每一世**新生的白厄杀死旧的自己** |
| 33594447 | 丹恒借**纳努克的神血**呼唤白厄英魂，「毁灭」洞开忆域 | 白厄的倾力一击驱散忆潮，丹恒接住「大地」火种，在层岩中找到开拓者 |

落点：`presets/plot/`、`plot-full/`、`plot-mech/`、`nullify/` 的 `events.jsonl`；
四个 preset 的 `timeline.json` 里同名章节标签；`plot-mech/preset.json` 的两条 `why`。

依据：3.3 黎明（万敌负创、缇宁耗尽力量；缇宝在 3.7 列车仍在，PLOT-024）、
3.1 门扉（欧洛尼斯「消失不见」）、3.4 粉碎（轮回中是新生白厄杀旧我，PLOT-019）、3.6 大地（荒笛让渡大地火种）。

### 未动

- `worlds/origin/story.jsonl` 与 `worlds/origin/presets/origin-eternal/events.jsonl` 当时仍有「理性与岁月两位泰坦先后陨落」的旧写法——
  `worlds/origin` 属于冻结边界，**本条当时未改**；后来获授权，已在 **v1.17** 一并修掉。
- 33594530「权杖爆炸」仍无 lore 出处（`preset_beats` 里 `match:none`），未改文案。

### 校验

- 四个 `events.jsonl` + 全部 `presets/**/*.json*` 解析通过；`grep` 四条错误表述在 `presets/` 已归零。
- `lore_lint` 0/0 · `baseline --check` 0 drift · 保真分 0.9092 不变。
- 指纹（`state.digest()`）只吃 payload/状态，label 不入摘要；payload 未改，故 golden 指纹预期不变（待测试套件复核）。

---

## v1.15 — 2026-10-31（P-G 方案 A：preset 节拍 → lore 只读映射）

### 变更

- 新增 `D3_plot/preset_beats.jsonl`（33 条，`PB-001..PB-033`）：
  把 `presets/plot*` 的每个事件节拍（frame + payload）映射到 `PLOT-*` / `EVT-*` / `TRM-*`，
  字段为 `frame` / `beat` / `presets` / `label` / `lore_refs` / `match`（exact·partial·none）/ `source` / `note`。
  **presets 一字未改**，这是单向的只读对照表。
- 校验：33 条 id 唯一；全部 `lore_refs` 能在 `lore/canon/index.json` 中解析；
  `frame + payload` 与三个预设的实际节拍逐条一致（`presets` 字段零偏差）。

### 核对结论（写进各条 `note`）

| 节拍 | 问题 |
|---|---|
| frame 42000 昔涟入剑 | **错**：轮回中死的是旧的白厄；昔涟只被杀死一次以抹除「岁月」（PLOT-019） |
| frame 36000 赛飞儿之死 | **「缇宝牺牲」无依据**：3.3 黎明只记万敌负创、缇宁耗尽力量；缇宝在 3.7 列车仍在（PLOT-024） |
| frame 18400 两泰坦陨落 | 「岁月」欧洛尼斯是「消失不见」，无死亡表述 → 陨落为推断 |
| frame 33594447 | 「纳努克的神血」在 1,374 条语料中检索不到 |
| frame 33594530 权杖爆炸 | `match:none`，本包无对应记录，暂无法溯源 |

另有 4 个 lore 场景没有对应节拍：PLOT-014（树庭覆灭）、PLOT-015（那刻夏与元老院）、
PLOT-020/021（同盟会议、海底五百黄金裔）、PLOT-023（忆潮追逐）。

### 说明

- 该文件**不注册为 canon kind**（不进 compile / fidelity），属于人工维护的对照表；
  若以后要在 apps 里消费，再单独决定是否注册。
- 未改 `presets/`、`kernel/`。

### 校验

- `python tools\lore_compile.py --check` → canon ok。
- `python tools\baseline.py --write` → `lore.files` 181 → **182**，其余不变；`--check` → 0 drift。

---

## v1.14 — 2026-10-31（P-F：重新基线化）

### 变更

- `tests/baseline.json` 重新写入。漂移只有语料面三项，**内核 / 应用 / golden 指纹零变化**：

| 项 | 旧 | 新 |
|---|---|---|
| `lore.canon_entries` | 1,075 | **1,374** |
| `lore.files` | 167 | **181** |
| `lore.canon_digest` | `542e4a5c…` | `b1a795e4…` |

- `python tools\baseline.py --check` → **0 drift**。
- `python tools\fidelity_report.py` → **0.9092** / 阈值 0.85 / 通过。

### 说明

- 基线只存 canon 的条目数、文件数与 `source_digest`，不存 `compiled_at`，因此重编译不会造成假漂移。
- `python -m unittest discover -s tests -q` → **Ran 612 tests in 239.8s, OK**。

---

## v1.13 — 2026-10-31（P-D：终端 ↔ 循环 ↔ 任务的关联补齐）

### 变更

- `D6_terminal/terminals.jsonl`：
  - 14 条 `trigger.event = "同上"` 全部展开为最近一条显式事件（TRM-004 / 037 / 044 / 046 / 049 / 061–066 / 068–070），
    现在 282 条的 `trigger.event` 都可直接解析。
  - 27 条补 `loop_refs`（如 TRM-186 → `[134]`、TRM-197 → `[108642]`、TRM-258 → `[33550336]`）。
- `D6_terminal/triggers.json`：新增 `loop_index`（17 个循环号 → 终端 id，A/B 级并列不删重复）
  与 `range_mentions`（#83 只在「#83 至 #133」的区间表述里出现，单列，不当作独立日志）。
- `D5_loops/official_anchors.jsonl`：OA-031..046 补 `mission` / `mission_id`（`1040501` 兑现那染血的冀望、
  `1040503` 粉碎那悲哀的造像、`1043659` 大墓深藏轮回的秘密；OA-046 为「丹恒·如我所书」，无 mission_id）。
  这样「循环号 → 任务 → PLOT」可以机器 join，不必再靠 `note` 里的中文任务名。
- `D3_plot/gaps.jsonl`：GAP-D3-007（游戏内历法）标 `partial` —— 32 个光历年份散点已可定位，
  但官方没有统一纪年口径，仍不建立完整历法年表。

### 未做

- 未新增 canon kind（没有新文件类型）；所有关联都加在既有记录的字段上。
- 未删除任何 A/B 重复终端：同一循环的 A 级 `S-001` 与 B 级 `S-024` 两条并列保留。

### 校验

- `python tools\lore_lint.py` → 0 errors / 0 warnings。
- `python tools\lore_compile.py` → 1,374 entries / 56 files；`--check` → canon ok。
- `python tools\fidelity_report.py` → 0.9092 / 0.85 / 通过（D5 0.98 · D6 0.99）。

---

## v1.12 — 2026-10-31（P-E：关闭 CF-009，事件/概述统一改号）

### 背景

CF-009：既有 EVT/WC/PLOT 的版本号是按 `S-001:303xx` 概述序号「每约十条切一段」推的，与 wiki 分卷 + 任务 ID 段位整体错位一档。
用 `missions.jsonl` 复核：10401xx=3.0、10402xx=3.1、10403xx=3.2、10404xx=3.3、10405xx=3.4，
且章节名与内容吻合（3.3「在黎明升起时坠落」正对白厄黎明赴涡心、赛飞儿身故；3.4「因为太阳将要毁伤」正对白厄与烈阳的戏剧）。

### 改号（旧值全部记入 CF-009）

- `04_event_index.jsonl`：EVT-010/011/012 3.0→**3.1**；EVT-013/014/015 3.1→**3.2**；EVT-016/017/018/019 3.2→**3.3**；EVT-020 3.2→**3.4**。
- `D3_plot/wiki_claims.jsonl`：WC-005/006 3.0→**3.1**；WC-007/008/009 3.1→**3.2**；WC-010/011/012 3.2→**3.3**；WC-013/014/015 3.3→**3.4**。
- `D3_plot/plot_expansion.jsonl`：PLOT-003 3.0→**3.1**；PLOT-004/005 3.1→**3.2**；PLOT-006/007 3.2→**3.3**；PLOT-008 3.3→**3.4**；
  并新增 **PLOT-025**（3.0 远客与晚星：奥赫玛的试探与结盟）、**PLOT-026**（3.1 门扉与来路：缇安的牺牲与雅努萨波利斯的往世），
  使每个章节仍有 ≥3 条场景（总计 **26** 条）。
- CF-009 状态 `pending` → **`resolved`**，`resolved_by` 写明证据与旧号。

### 未动

- `EVT-001..009`、`EVT-021..095` 与 `3.5–3.7` 的条目经复核与新口径一致，未改。

### 冲突收口

| 冲突 | 处理 |
|---|---|
| CF-001 火种精确总数 | resolved：不采用任何精确总数；旧值降级为 DB-005，`R-LOOP-002` 禁止回填，事实层只留「四亿枚」 |
| CF-002 进度百分比 | resolved：三套分母分列，不设单一 progress；wiki 未给百分比的保持 null + `progress_source:UNKNOWN` |
| CF-004 「种子」 | resolved：已按 inferred 落地（`generation.json` `_honesty`、推断流 confidence=E、ADR-0002），事实层仍标 U-D1-001 |
| CF-006 NeiKos496 目的 | resolved：一律「目的未知」，替接动机只放 inference，由 OOC-003 约束 |
| CF-008 3.7 章节名 | **仍 pending**：A 级只有一条章节表，无法判定「成为昨日的明天」是别名还是并列章节 |

### 口径说明

- 项目验收口径只有 `config/fidelity.json` 的 `threshold=0.85`。v1.10/v1.11 里出现的 0.93 / 0.95
  是本会话内部的观察值，**不是用户设定的目标**，不再作为待办。

### 校验

- `python tools\lore_lint.py` → 0 errors / 0 warnings（plot 26 · conflict 9）。
- `python tools\lore_compile.py` → 1,374 entries / 56 files；`--check` → canon ok。
- `python tools\fidelity_report.py` → 0.9092 / 0.85 / 通过（D3 0.94 · D8 0.95 · D7 0.58）。

---

## v1.11 — 2026-10-31（P-C：场景扩写 13 → 24，每章节 3 条）

### 变更

- `D3_plot/plot_expansion.jsonl`：新增 `PLOT-014..PLOT-024`（11 条），场景级条数 13 → **24**，
  3.0–3.7 每个章节均为 3 条。全部取自 `S-024` 分卷任务摘要（B 级），标 `confidence:B` / `verbatim_claim:false`，
  每条都写明 `gap`，未虚构任何对白。
- `PLOT-013` 补 `verbatim_claim:false`（原为 B 级却进了 A 级逐字分母）。
- 新增冲突 **CF-009（pending）**：wiki 分卷版本与既有「概述序号每十条切段」的归档版本整体错位约一档
  （树庭覆灭 3.0→3.1、阿格莱雅/赛飞儿/艾格勒 3.2→3.3、沉浸式戏剧 3.3→3.4）。
  旧 `EVT-016..020` / `PLOT-006..008` **不改号**，留待 P-E 统一复核；新条目按 wiki 分卷 + 任务 ID 段位归档并加 `note`。
- `D3_plot/coverage_matrix.md`：场景级统计改为 24 条，新增「场景级扩写」分版本表与 CF-009 说明。
- `lore/00_manifest.md`：D3 条数同步为 `plot_expansion.jsonl(24)`。
- `D8_characters/ooc_guards.jsonl`：35 条 guard 全部补 `source`——指向该卡真实存在的字段
  （`CHR-xxx#decision_rules` / `#speech` / `#identity` / `#goals` / `#beliefs` / `#emotions`），
  其中 OOC-003 直接用其正文里的 `S-001:75058`。已逐条校验目标卡片确有此字段。

### 结果

- D3 的覆盖分母由 13 条 A 级为主变为 24 条（11 条 B 级），**A 级逐字占比下降**；这是如实计入 wiki 的结果，不使用 B 级充 A。
- D3 **0.90 → 0.93**（覆盖 0.82 → 0.86）；D8 **0.90 → 0.95**（可追溯 0.78 → 0.97）。
- 加权保真分 **0.8986 → 0.9090**。
- D3 的上限：8 条已承认的 gap 记为 0 分，覆盖最高只能到 0.86，故 D3 天花板约 **0.933**；
  这是语料边界，不通过删 gap 去换分。
- 「已补全」仍为 0 条：没有 A 级过程逐字就不写已补全。

### 校验

- `python tools\lore_lint.py` → 0 errors / 0 warnings（plot 24 · conflict 9 · guard 35）。
- `python tools\lore_compile.py` → 1,372 entries / 56 files；`--check` → canon ok。
- `python tools\fidelity_report.py` → 0.9090 / 0.85 / 通过。

---

## v1.10 — 2026-10-31（保真逐字口径修正）

### 变更

- `config/fidelity.json`：`verbatim` 增加 `scope_field: "verbatim_claim"` / `scope_value: true`。
  只有自称逐字的记录进入 A 级逐字分母；B 级 wiki 记录标 `verbatim_claim:false`，只影响 `coverage`。
- `apps/fidelity.py`：`_score_dimension` 按 `scope_field` 过滤 `graded`；无该字段的记录保持原行为。
- `D5_loops/official_anchors.jsonl` / `D6_terminal/terminals.jsonl`：补 `verbatim_claim`
  （A 级 30 / 81 条为 true，B 级 16 / 201 条为 false）。

### 结果

- 加权保真分 **0.8544 → 0.8986**（阈值 0.85，通过）。
- D5 **0.86 → 0.98**；D6 **0.75 → 0.99**；其余维度不变。
- 距 0.93 的剩余空间：D1 0.90（覆盖 0.71）· D3 0.90（覆盖 0.82 + 缺口罚分）· D7 0.58（固定）· D8 0.90（guard 缺 source）。
  在 D7 固定 0.58 的前提下，其余 7 维平均需约 0.98 才能到 0.93。

### 校验

- `python tools\lore_compile.py --check` → canon ok: 56 files。
- `python tools\fidelity_report.py` → 0.8986 / 0.85 / 通过。

---

## v1.9 — 2026-10-31（wiki_structured 入库：D3 / D5 / D6 / D8）

### 入库

- `D5_loops/official_anchors.jsonl`：新增 `OA-031..OA-046`（16 条），锚点 30 → **46**。
  来源 `S-024` wiki 任务页，`verified:false`、`confidence:B`。
- `D6_terminal/terminals.jsonl`：新增 `TRM-082..TRM-282`（201 条），终端 81 → **282**。
  去重后按内容重新分类：output 98 · log 85 · garbage 18（新增里没有真正的交互 prompt，旧的 7 条 prompt 保留）；
  `confidence:B`、`verbatim:false`。
- `D8_characters/characters/`：16 张卡新增 `stories`（CHR-001 为 original+revised 共 8 段，其余 15 人各 4 段）；
  15 张卡新增 `ruwoshuo`（573 条《如我所书》，按角色分卷）。全部 `source:S-024`、`grade:B`。
- `D3_plot/battle_lines.jsonl`：复制 572 条战斗/过场台词作为**证据文件**；尚未注册为 canon kind，
  等 P-C 折叠进 `plot_expansion`。

### 未入库（留给后续）

- `options.jsonl` → P-C 对话树；`side_missions.jsonl` → P-C 支线；`books/lightcones/relics` → P-E/P7；
  `enemy_pages.jsonl` 3 条 `none_in_wiki` 接受为事实；`b6_crosscheck.jsonl` 仅作证据。

### 证据口径（重要）

- `b6_crosscheck` 复核：wiki 18,272 行对客户端 1,360 行匹配（7.4%）；**20 个任务 `client_lines=0`**。
  因此 3.0–3.7 的 A 级逐字覆盖不是 100%，wiki 是唯一接近完整的叙事来源（B 级）。
- D6 的 A 级逐字占比由 100% 降到 **81/282 = 28.7%**；这是把 B 级终端如实计入的结果，P-F 重评时不得再宣称 D6 全 A。

### 校验

- `python tools\lore_lint.py` → **0 errors / 0 warnings**（anchor 46 · terminal 282）。

---

## v1.8 — 2026-10-31（P-A 扩展：45 → 66 任务）

### 背景

8 卷 wiki 全文在 P-A 之后扩充到 **66 个任务**（3.0:10 · 3.1:9 · 3.2:9 · 3.3:9 · 3.4:6 · 3.5:7 · 3.6:9 · 3.7:7）；
`wiki_structured/missions.jsonl` 66/66 与 8 卷逐条对齐。

### 变更

- `04_event_index.jsonl`：新增 `EVT-075..EVT-095`（21 条），任务级事件 **45 → 66**，事件总数 **73 → 94**。
- 为 **58 / 66** 个任务级事件补 `mission_id` / `mission_ids`（从 `S-002` 反查）。
  缺 8 条：3.0-07 金缕荡污浊、3.0-10 英雄啊且握住那枚火种、3.1-09 来路啊、3.2-01 纺锤啊、
  3.3-06/07 诗者上下、3.5-01 流年啊、3.6-05 烈阳啊。
- `大黑塔` 手工映射 `CHR-010`；`阮•梅`、`卡芙卡`、`流萤`、`黄泉` 等无卡者进 `unmapped_participants`。
- 3.7 新事件沿用 `chapter=记忆是梦的开场白` + `wiki_chapter=成为昨日的明天` + `conflict_refs:["CF-008"]`。
- `D3_plot/coverage_matrix.md`：任务级 66/66；3.0/3.1/3.2/3.3/3.6/3.7 行更新；新增 Mission ID 证据行。
- `00_manifest.md`：事件 94、covered 169、实体+事件 187。

### 校验

- `python tools\lore_lint.py` → **0 errors / 0 warnings**（event 94）。

---

## v1.7 — 2026-10-31（P-B 说话人补全）

### 新增

- `D4_dialogue/speaker_map.json`：`S-024`（BWIKI，B 级）说话人标签 → 语料实体 id。
  `resolved` **81** 条（`CHR-*` 与 `SYS-*`），`unresolved` **310** 条（`？？？`、合称、回声/形态、无角色卡）。
  `unresolved` 一律不回填 `speaker`。
- `lore/schema/dialogue.schema.json`：新增 `speaker_grade` / `speaker_evidence` / `speaker_wiki` 三个可选字段。

### 变更

- `D4_dialogue/dialogues.jsonl`：**55 / 357** 行 `speaker_source` 由 `inferred_low` → **`official`**（B 级）。
  写入 `speaker` / `speaker_grade=B` / `speaker_evidence=S-024:<分卷>:<行号>` / `speaker_wiki`；原推断保留在 `speaker_inferred`。
  - 分布：`SYS-014` 往昔的涟漪 **41** · `SYS-001` 权杖δ-me13 **10** · `CHR-002` 昔涟 **3** · `CHR-001` 白厄 **1**。
  - 未升级 **302** 行：wiki 无逐字同句，或同句出现多说话人（`往昔的涟漪|？？？` 2、`往昔的涟漪|昔涟` 2），或 wiki 也只标 `？？？`（11）、`「记忆的花」`（1）。
- `apps/dialogue.py`：`line_from_dict` 改为 **official speaker 优先于 `speaker_inferred`**；仅影响已升级的 55 行。
- `tests/test_dialogue.py`：新增「official speaker 必须带 B 级来源」与「official 优先于 inferred」两项契约。
- `D4_dialogue/unknowns.jsonl` U-D4-001：更新为 55 / 357 已确认、302 行仍 inferred，并指向 `speaker_map.json`。
- `00_manifest.md`：D4 行补 `speaker_map.json`；§5 已知缺陷第 3 条更新为 55 / 357。

### 口径

- 只做**逐字同句**的精确匹配（去掉 ruby/color 标签、空白与标点后比对）；**未做模糊匹配**，避免把不同语境的话按说话人合并。
- `S-024` 是 B 级社区整理，因此 `speaker_source=official` 配 `speaker_grade=B`，**不冒充 A 级**；A 级逐字仍以 `S-001` / `S-002` 为准。
- `form` 字段保留数据源原值（可能是错误的资源名），权威说话人以 `speaker` + `speaker_source` 为准。

### 校验

- `python tools\lore_lint.py` → **0 errors / 0 warnings**（dialogue 357 不变）。
- `python tools\grep_forbidden.py` → **0** 命中。
- `python tools\layer_lint.py` → 通过（apps 27 模块，无新增越界）。
- 单元测试待授权后运行。

---

## v1.6 — 2026-10-31（P-A 语料入库：wiki 45 任务）

### 新增

- `04_event_index.jsonl` EVT-030..EVT-074：BWIKI 3.0–3.7 共 **45 个任务**，来源 `S-024`（**B 级社区整理**）。
  `participants` 只写已有的 `CHR/ORG/SYS` id；未建卡的出场者写入 `unmapped_participants`，不新造实体、不猜映射。
- `01_sources.csv` S-024：BWIKI 翁法罗斯剧情原文。分卷在 `lore/story/amphoreus_wiki/`（`.gitignore` 挡住，不入库），
  派生条目按 `S-024:<分卷>#<任务名>` 定位。
- `D3_plot/plot_expansion.jsonl` PLOT-013：3.4「沉浸式戏剧：白厄的童年与最初的逐火」，B 级。

### 变更

- `D3_plot/coverage_matrix.md`：3.4 由 `UNKNOWN` 改 `covered`；任务级 45/45；`UNKNOWN` 0 条；新增 3.7 章节名冲突行。
- `00_manifest.md`：事件索引 28 → **73**；D3 行 12 → 13；补 S-024 与 wiki 分卷的不入库说明。
- `10_conflicts.jsonl`：CF-007 `pending` → **`resolved`**（wiki 6 任务确认 3.4 主线归属，B 级）；
  新增 **CF-008**（3.7 章节名「记忆是梦的开场白」vs「成为昨日的明天」，`pending`）。
- `D3_plot/gaps.jsonl` GAP-D3-001：`status=resolved`；**条目保留，不删缺口**。
- `tools/scene_lint.py`：删除 `EXPECTED_GAPS`（3.4 已有场景，缺口不再是例外）。

### 未做（留给后续）

- canon 未重编译：`lore_compile --check` 会显示 events / plot / gaps / conflicts 漂移，统一在 P-F 处理。
- 说话人升级（P-B）、场景扩容（P-C）、终端与轮回（P-D）未开始。
- A 级逐字率未受影响：wiki 只进 B 级，`S-001` / `S-002` 仍是逐字主干。

### 校验

- `python tools\lore_lint.py` → **0 errors / 0 warnings**；计数：event 73 · plot 13 · conflict 8 · gap 8 · unknown 35。
- 未运行 `lore_compile` / `scene_lint` / `baseline`（canon 重编译按计划留到 P-F）。

---

## v1.5 — 2026-10-31（CF-003 补证）

### 变更

- `10_conflicts.jsonl` CF-003 增加第三条证据：`S-001:30406`（3.3「英雄啊，回返那安宁的家乡」章节概述）——
  『其人在三千万世轮回中，为避免再创世完成而一味地夺取火种，以敌人立场面对昔日同伴，
  最终逐渐失却自我的经历。』
- `sources` 追加 `S-001:30406`、`S-001:159428`（三千万世收集记忆是徒劳、记忆是毁灭的薪柴）。
- `assessment` 明确切分：①结果层（延迟破壳，A 级 424954）；②过程层（反复夺火种 → 失却自我，
  A 级概述 30406；据此判定倾向被强化，A 级批注 75013）。

### 仍为推断（官方未逐字写出）

1. 每轮固定背负十二枚火种；
2. 来古士当面劝说并说漏嘴；
3. 昔涟自毁「岁月」存在以引来瞥视、并回退该轮。

这三条保留在 `assessment` 的推断段，不进事实栏，也不作为趋势权重来源。

---

## v1.4 — 2026-10-31（CF-003 裁决）

### 变更

- `10_conflicts.jsonl` CF-003：`pending` → **`resolved`**。结论不是"两说矛盾"，而是**两层描述**：
  ①结果层——每轮回溯把再创世推回起点，铁墓无法破壳（时点延后）；
  ②过程层——每轮回溯多背负十二枚火种，理智损耗累积，毁灭倾向被强化。
- `D2_trends/causal_links.jsonl`：
  - `CL-010` 由 `inhibits` 改为 **`reinforces`**（目标 `TREND-003` 是"毁灭倾向"，不是"破壳"）；
  - 新增 `CL-019`：`SYS-006 → WG-020`，`type=delays`，承接"延误破壳"这一层。
- 因果数 18 → 19，编译条数 1074 → **1075**。

### 证据边界

- ①有 A 级直证（`S-001:424954`）；②有 A 级批注（`S-001:75013`）。
- 中间因果链（说漏嘴 → 二人推断 → 自毁岁月 → 瞥视 → 回退）由项目所有者补充，
  官方未在一处完整写出，记为 `inferred`，不进入事实栏。

---

## v1.3 — 2026-10-31（P0 基线与纪律）

### 新增

- `tests/baseline.json` + `tools/baseline.py`：项目数字的唯一来源。每个字段带 `method`（怎么数出来的），`--check` 只读比对、`--write` 才重写。
- `docs/adr/0002-原著还原层与零专名边界.md`：考据层与零专名的边界、冻结清单、三个运行档位、证据与诚实条款。
- `tools/fidelity_report.py`：还原度报告骨架（8 维计数与覆盖率；评分留到 P7）；`--check` 故意退出 2，防止被误当成门禁。
- `tests/test_lore_contract.py`：原始语料的契约骨架（8 维目录、顶层文件、逐行可解析、ID 存在、冲突/未知非空）。

### 修正

- `lore/canon/manifest.json` 增加 `kind_files`（种类 → 文件名）。此前 `CanonBundle` 按 `{kind}.jsonl` 猜名字，导致除 `multilingual` / `debunked` / `character` 外的种类全部读成 0 条；现由 manifest 声明，`fidelity_report` 八维恢复为 1.00。

### 校验结果

| 项 | 结果 |
|---|---|
| `python tools/baseline.py --check` | `baseline ok: 0 drift` |
| `python -m unittest tests.test_lore_contract tests.test_canon_contract` | 14/14 OK |
| `python tools/lore_compile.py --check` | `canon ok: 56 files` |
| `python tools/fidelity_report.py` | D1 20 / D2 57 / D3 44 / D4 369 / D5 65 / D6 89 / D7 31 / D8 190，覆盖率均 1.00 |
| `python tools/grep_forbidden.py` | 0 命中 |
| `python tools/layer_lint.py` | 通过 |

---

## v1.2 — 2026-10-31（P2 编译）

### 新增

- `schema/`：9 份 JSON Schema（fact / scene / dialogue / loop / terminal / character / worldgen / trend / micro_event）+ `canon_manifest.schema.json`。
- `tools/lore_lint.py`：逐行解析、ID 唯一、必填字段、置信度枚举、来源字段、跨类引用（对话→场景、场景→角色、场景测试→角色、因果→微变量/趋势）。
- `tools/lore_compile.py`：确定性编译到 `lore/canon/`；`--check` 做幂等校验。
- `apps/canon.py`：`CanonBundle` 只读加载器（校验 manifest 哈希、按种类查询、引用自检；代码内零专名）。
- `tests/test_canon_contract.py`：8 条契约测试。
- `lore/canon/`：**1074 条 / 56 个文件**（含 `manifest.json`、`index.json`、`traceability.jsonl`、`worldgen.json`、`characters/` 27 张）。

### 数据修正（结构，不改事实）

- `D2_trends/causal_links.jsonl`：`CL-011` 的 `to` 由 `MV-003(德谬歌)`、`CL-015` 的 `to` 由 `MV-012(丹恒)` 改为纯 ID（括注不是 ID）。
- `D3_plot/plot_expansion.jsonl`：`PLOT-010` 的 `SCN-009` 从 `dialogue_refs` 移到新增的 `scene_refs`（它是场景，不是台词）。

### 校验结果

| 项 | 结果 |
|---|---|
| `python tools/lore_lint.py` | 0 errors / 0 warnings；25 类、共 1074 条 |
| `python tools/lore_compile.py` | 1074 条 → 56 个文件 |
| `python tools/lore_compile.py --check` | `canon ok: 56 files`（幂等） |
| `python -m unittest tests.test_canon_contract` | 8/8 OK |
| `python tools/grep_forbidden.py` | 0 命中 |
| `python tools/layer_lint.py` | 通过（apps 20 模块） |

> 附带修复：`kernel/disturbance.py:687` 的注释含两个角色名（上一位执行者留下的），已改为不含专名的表述；仅注释，不改行为。

---

## v1.1 — 2026-10-31（复核修订）

> 由主执行方逐条核对行数、locator 与字段后修订；**不新增任何事实**，只改口径与可追溯性。

### 修正

- `00_manifest.md` §4：复现命令由不存在的 `build_lore.py` 改为实际的 `build_d4 / build_d8 / build_d8_relations / build_tree / build_unknowns / validate` 分步脚本。
- `00_manifest.md` 新增 §4.1「入库范围」：原始文本表 / 剧情编排表 / 全量名字表 / 全游戏剧本不入库，并说明未保留的中间产物。
- `12_fidelity_checklist.md`：实体索引 68 → **93**；轮回日志 33 → **35**（全部 `official`）；八维覆盖由「8/8 ✅」改为「8/8 有目录，D3/D7 = partial」；终端 81 条补充原始表 186 条 `>>>` / 30 条翁法罗斯命中 的口径说明。
- `13_changelog.md`：实体索引 68 → 93；`loops.jsonl` 33 → 35。
- `D1_seed/worldgen_dimensions.jsonl`：20 维逐条补 `evidence` 聚合字段（由嵌套 `state_vars[].source` / `rules[].source` 去重汇总，无新增来源）。

### 复核结论（主执行方实测）

- 29 个 JSONL 全部可解析，0 行损坏。
- 抽查 `S-001:225852 / 225855 / 225888 / 225889` 四条 locator，与 `textmap_zh_cn.jsonl` 逐字一致。
- 27 张角色卡全部满足 ≥3 条 `decision_rules`。
- 已知残留：`11_unknowns.jsonl` 为各维度 `unknowns.jsonl` 的聚合，存在 30 组同名 id，P2 编译须按聚合视图去重。

---

## v1.0 — 2026-10-31

### 新增

- **基础层**：`00_manifest.md`、`01_sources.csv`（23 条来源）、`02_glossary.json`（46 条术语）、三张索引表（93 实体 / 28 事件 / 46 术语）。
- **D1 种子/世界生成**：`seed_terms.md`（五义项消歧）、`worldgen_dimensions.jsonl`（20 维）、`random_streams.json`、`inheritance.json`、4 块伪代码、8 条 unknowns。
- **D2 趋势/微变量**：`trends.jsonl`（8 律）、`micro_variables.jsonl`（31 条）、`causal_links.jsonl`（18 条）、4 块伪代码、6 条 unknowns。
- **D3 剧情**：`wiki_claims.jsonl`（24 条）、`plot_expansion.jsonl`（12 条）、`coverage_matrix.md`（3.0–3.7）、`gaps.jsonl`（8 条）、3 块伪代码。
- **D4 对话**：`scenes.jsonl`（12 个场景）、`dialogues.jsonl`（357 条逐字）、`dialogue_tree.json`、3 块伪代码、6 条 unknowns。
- **D5 轮回日志**：`loops.jsonl`（35 条，全部 `evidence=official`）、`official_anchors.jsonl`（30 条）、`rebuild_rules.json`、3 块伪代码、5 条 unknowns。
- **D6 终端**：`terminals.jsonl`（81 条）、`triggers.json`、`multilingual.jsonl`、3 块伪代码、5 条 unknowns。
- **D7 社区**：`fragments.jsonl`（13 条）、`channel_matrix.md`（14 渠道）、`crosscheck.jsonl`（13 条）、`debunked.jsonl`（5 条）、3 块伪代码。
- **D8 角色**：`roster.json`、27 张角色卡、`relations.jsonl`（47 条）、`scenarios.jsonl`（81 条）、`ooc_guards.jsonl`（35 条）、4 块伪代码。
- **收口**：`10_conflicts.jsonl`（7 条）、`11_unknowns.jsonl`（35 条）、`12_fidelity_checklist.md`。
- **工具**：`tools/lore_build/`（build_d4 / build_d8 / build_d8_relations / build_unknowns / validate）。

### 关键发现（相对项目旧文档）

1. **「种子」不是随机种子**：官方 18 条含「种子」的文本全部指「记忆的种子」或花种修辞；`seed → world` 属推断（CF-004）。
2. **火种旧值 402,604,020 无官方来源**：官方只给「四亿枚」概数；12×33,550,336=402,604,032（CF-001）。
3. **进度百分比至少三套体系**：实验阶段 / 铁墓成熟度 / 自我迭代进程（CF-002）。
4. **永劫回归同时抑制与强化铁墓**：官方两处表述并不矛盾但方向相反（CF-003）。
5. **Philia093↔德谬歌 有完整逐字场景**：`S-001:225852-226200` 共 357 条，已全量收入 D4。

### 修复

- `loops.jsonl` 中一处「翁帕罗斯」错字改为「翁法罗斯」。
- D4 抽取脚本的残字清理规则修正（`{` / `'` 开头不再误保留）。

### 未完成 / 下一版

- 英/日文本表抽取（多语言对照）。
- 说话人字段（TalkSentenceConfig SpeakerID）定位。
- D7 剩余 9 个渠道检索。
- 3.4 章节归属确认。
- 泰坦卡（CHR-025/037/038）补剧情。
