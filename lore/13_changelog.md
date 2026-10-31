# 13 Changelog

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
