# 00_manifest —— 翁法罗斯全维考据语料库

> 依据：`.trae/documents/信息采集提示词-翁法罗斯全维考据-v1.md`（v1.0）
> 数据版本：崩坏：星穹铁道 **4.6.0**（构建线 `V4.6Live` / `20260917-0139`）
> 建库日期：**2026-10-31**
> 语料来源：本地客户端只读抽取（见 `01_sources.csv`）

---

## 完整性声明

> 完整性声明：本包覆盖 D1–D8 全部八个维度；实体索引 **93** 条、事件索引 **94** 条、术语索引 **46** 条；其中 covered **169**、partial **17**、unknown **1**、out_of_scope **0**（实体 + 事件合计 187）。未知与缺口逐条列于各维度 `unknowns.jsonl` 与根目录 `11_unknowns.jsonl`（共 35 条）；未取得的部分一律标 `UNKNOWN`，不以推测填充。
>
> 2026-10-31 追加：事件索引新增 **66 条任务级**条目（EVT-030..EVT-095），来源 `S-024`（BWIKI 剧情原文，**B 级社区整理**），覆盖 3.0–3.7 的 66 个开拓任务；3.4 的章节归属由 CF-007 关闭。

---

## 0. 本包与原提示词的差异（必须先读）

原提示词假设执行者是"联网 AI"，可抓取三份 wiki、B 站录屏、米游社截图等。本次执行环境能直接读到**客户端原始文本**，因此语料结构做了如下调整（全部为**增强**，不降低证据等级）：

| 项 | 原要求 | 本包做法 | 理由 |
|---|---|---|---|
| A 级来源 | 游戏截图 / 官方阅读物 | **客户端文本表（TextMap）+ 剧情编排表** 直读 | 逐字、可定位、可复现，等级不低于截图 |
| D3 三份 wiki | 逐句扩写 | 以**官方任务概述 + 官方阅读物 + 逐字台词**为主干，wiki 仅作交叉线索 | 一手优先（§5.2 站点分层） |
| D7 社区 | 14 个渠道逐一抓取 | 仅完成可稳定访问的检索（米游社 / bilibili / wikiwiki / 百科），其余标 `UNKNOWN` 并留检索记录 | 反爬与登录墙；不编造帖子 |
| D5 逐轮日志 | 每轮 | 官方明示轮次逐字收录，其余用**确定性重建规则**（标 `reconstructed`） | 官方只记录少数轮次，不得声称"每轮都真跑" |

---

## 1. 证据分级执行情况

| 级别 | 本包来源 | 用途 |
|---|---|---|
| A 官方逐字 | `S-001` 客户端中文文本表、`S-002` 剧情编排表、`S-004` 本地化名表 | 事实栏唯一主干 |
| B 官方概述 | 游戏内任务概述（同属 `S-001`，但为概述体）、`S-010`/`S-011` 米游社 wiki、`S-015` wikiwiki、`S-024` BWIKI 剧情原文 | 交叉、补语境 |
| C 一手社区实录 | `S-012` 玩家整理的「如我所书」存档 | 交叉验证 A 级归档文本 |
| D 二手解析 | `S-013`、`S-014`、`S-017` | 只进 `inference` / `线索` |
| E 推断/同人 | `S-016`、`S-018`，以及本包所有 `inference` 字段 | 永不进事实栏 |

**同人零混入检查**：`grep -r "\"fanwork\": true"` 仅出现在 `D7_community/fragments.jsonl`，事实栏（D1–D6、D8）无 `fanwork`。

---

## 2. 目录与完成度

| 维度 | 目录 | 文件 | 状态 | 说明 |
|---|---|---|---|---|
| D1 种子/世界生成 | `D1_seed/` | seed_terms.md, worldgen_dimensions.jsonl(20), random_streams.json, inheritance.json, pseudocode/(4), unknowns.jsonl | covered（生成规则 6 条 unknown） | 官方只给"机制描述"，未给数值域 |
| D2 趋势/微变量 | `D2_trends/` | trends.jsonl(8), micro_variables.jsonl(31), causal_links.jsonl(18), pseudocode/(4), unknowns.jsonl | covered | 微变量全部有官方首次出现轮次 |
| D3 剧情 | `D3_plot/` | wiki_claims.jsonl(24), plot_expansion.jsonl(26), battle_lines.jsonl(572), preset_beats.jsonl(37), coverage_matrix.md, gaps.jsonl(8), pseudocode/(3) | partial | 主线 3.0–3.7 有 A 级概述+台词；任务级 66 条由 S-024（B 级）补足；3.4 主线归属已确认（CF-007 关闭） |
| D4 对话 | `D4_dialogue/` | scenes.jsonl(12), dialogues.jsonl(357), dialogue_tree.json, speaker_map.json, pseudocode/(3), unknowns.jsonl(6) | covered（终章场景 A 级） | Philia093↔德谬歌 逐字取自 `S-001` 记录簇 225852–226200；55 行说话人由 `S-024`（B 级）确认为 `official` |
| D5 轮回日志 | `D5_loops/` | loops.jsonl(35), official_anchors.jsonl(46), rebuild_rules.json, pseudocode/(3), unknowns.jsonl(5) | covered（官方锚点 + 16 条 B 级） | 官方明示轮次：1/2/3/15/42/133/134/…/33550336/33550337；另 16 条来自 S-024 wiki |
| D6 终端 | `D6_terminal/` | terminals.jsonl(282), triggers.json, multilingual.jsonl(8), pseudocode/(3), unknowns.jsonl(5) | covered（A 级 81 + B 级 201） | `>>>`/`【】`/错误/prompt/归档/乱码；wiki 补充 201 条标 B 级 |
| D7 社区 | `D7_community/` | fragments.jsonl(27), channel_matrix.md, crosscheck.jsonl(14), debunked.jsonl(8), pseudocode/(3) | partial | 7/14 渠道有结果；其余 5 个为登录墙/反爬，2 个不可行 |
| D8 角色 | `D8_characters/` | roster.json, characters/(27), relations.jsonl(47), scenarios.jsonl(81), pseudocode/(4), ooc_guards.jsonl(35) | covered | 12 泰坦+12 黄金裔+外部变量+派生体；16 卡补 `stories`，15 卡补 `ruwoshuo`（S-024，B 级） |

---

## 3. 关键数字锚点（逐字核对结果）

| 锚点 | 官方原文 | 位置 | 与项目旧值的关系 |
|---|---|---|---|
| 死循环总次数 | `33550336` | `S-001:425068`、`S-001:75058` | 一致 |
| 最终循环 | `第33550337次死循环` | `S-001:425005`、`S-001:159372` | 一致 |
| 阶段切分 | `第1至50121次` / `第50122至176199次` / `第176200至28371273次` / `28371274起` | `S-001:424993`–`425001` | 一致；**旧值 402,604,020 枚火种未在任何官方文本中出现**，见 `10_conflicts.jsonl` CF-001 |
| 火种数量 | `四亿枚火种`（`S-001:425102`）、`数亿枚火种的瞬时共振`（`S-001:75058`） | 同上 | 官方为概数，非精确值 |
| 进度百分比 | `0% / 19% / 55% / 99%`（`S-012` 玩家存档）；`99%`（`S-001:432719`）、`32.47%`（`S-001:159374`）、`99.81%`（`S-001:159377`）、`96.75%`（`S-001:159364`）、`0.096%/1.34%/2.89%`（`S-001:159372`） | — | 项目旧值 3%/70%/100% **未在 A 级文本中直接命中**，见 CF-002 |

---

## 4. 复现方式

```powershell
# 1) 抽取客户端中文文本表（只读，约 3 秒）
python tools\hsr_probe\lib\static_analysis\p64_cn_extract.py
#    → lore\_probe\textmap_zh_cn.jsonl（457,301 条）

# 2) 剧情编排表导出（已有产物，未在本轮重跑）
#    → lore\export\data\story_full.jsonl

# 3) 重建本包的可提交语料（无单一入口，按维度分别运行）
python tools\lore_build\build_d4.py          # → D4_dialogue/
python tools\lore_build\build_d8.py          # → D8_characters/characters/
python tools\lore_build\build_d8_relations.py
python tools\lore_build\build_tree.py        # → dialogue_tree.json
python tools\lore_build\build_unknowns.py    # → 各维 unknowns.jsonl + 11_unknowns.jsonl
python tools\lore_build\validate.py          # 逐行 JSONL 合法性

# 4) 一次性修补脚本（已执行，保留备查）
#    fix_anchors.py / fix_scenes.py / fix_typo.py
```

`tools\lore_build\` 只做"排版与 ID 分配"，不生成任何未经人工核对的事实；所有 claim 均带 `source` + `locator`。

### 4.1 入库范围（重要）

仓库**只收派生语料**（本文件、三张索引、冲突/未知、D1–D8、方法报告），**不收原始 dump**：

| 不入库 | 原因 |
|---|---|
| `_probe/textmap_zh_cn.jsonl`（48.8 MB） | 整份客户端中文文本表，版权与体积 |
| `export/data/story_full.jsonl`（8.6 MB） | 剧情编排表全量导出（29,044 段 / 18,218 句） |
| `export/data/names.json`（274 KB） | 全量名字表 |
| `story/story_all.md`（2.2 MB） | **全游戏 712 卷**剧本，远超本项目范围 |
| `story/amphoreus_wiki/*.md`（约 1.58 MB） | BWIKI 翁法罗斯 3.0–3.7 剧情原文分卷；只保留派生的 EVT/PLOT 条目，原文不入库 |

以上文件都可由 §4 的脚本在本地重新生成；`01_sources.csv` 记录了来源路径与版本，足以复核对齐。
`PROBE_REPORT.md` 提到的中间产物（`textmap_keyed.jsonl` / `talk_textmap.jsonl` / `story_dialogue.jsonl` / `cn_textmap_hits.txt`）本轮未保留，同样可由脚本重跑，报告结论不依赖它们存在于仓库。

---

## 5. 已知缺陷（不影响 A 级事实）

1. **文本表是"串池"**：记录边界由抽取器按字符集切分，部分条目首尾夹 1–3 个二进制解码残字（如 `檓Qf`），已在 `terminals.jsonl` 的 `extraction_note` 标注；引用时以 `verbatim` 为准，不据残字推断语义。
2. **`δ` 不在抽取字符集内**：凡原文含 `δ-me13` 的记录，会被切成 `…权杖` / `-me13…` 两段。本包用 `continuation_of` 字段显式连接，不静默拼接。
3. **说话人覆盖率**：剧情编排表只对 19.9% 的台词保留了角色资源名，翁法罗斯段更低。2026-10-31 的 P-B 用 `S-024`（BWIKI，B 级）把 55 / 357 行升级为 `speaker_source=official`；其余仍为 `inferred`，**不得用于逐字归因**。映射见 `D4_dialogue/speaker_map.json`。
4. **无旁白**：`S-002` 只有台词，没有场景叙述。所有"过程"扩写均写明依据（概述 / 阅读物 / 台词）。
