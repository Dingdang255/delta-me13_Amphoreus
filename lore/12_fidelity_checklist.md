# 12 保真自检（§11.1 逐条）

| # | 检查项 | 结果 | 证据 / 说明 |
|---|---|---|---|
| 1 | 八个维度是否都有独立目录 | ✅ | `D1_seed` … `D8_characters` |
| 2 | 三张索引表是否齐全 | ✅ | `03_entity_index.jsonl`（93）/ `04_event_index.jsonl`（94）/ `05_term_index.jsonl`（46） |
| 3 | 每条事实是否有 source | ✅ | 所有 JSONL 的 `source`/`evidence`/`claim_source` 字段非空；`UNKNOWN` 处显式写 `UNKNOWN` |
| 4 | 每条 A 级文本是否逐字 | ✅ | 终端/对话全部带 `locator`；`verbatim_raw` 保留原始串；wiki 补入的 B 级文本单列 `confidence:B` |
| 5 | 每条转述是否标 `verbatim:false` | ✅ | D6 的 A 级 81 条 `verbatim:true`；wiki 补入的 201 条 `verbatim:false`；D3 `plot_expansion` 用 `verbatim_available:false`，B 级另标 `verbatim_claim:false` 以退出 A 级逐字分母 |
| 6 | 是否有同人混进事实栏 | ✅ 无 | `fanwork:true` 仅 `CM-008` |
| 7 | 是否有"可能/推测"被写成"是" | ✅ 无 | 推断统一放 `inference` / `subtext` / `notes` |
| 8 | 是否有编造的台词/日志/终端文本 | ✅ 无 | D4 全部由脚本从 S-001 逐字抽取；D6 的 A 级逐条手核，wiki 补入项全部带 `source:S-024` |
| 9 | 是否有 UNKNOWN 列表 | ✅ | 35 条（`11_unknowns.jsonl`）+ D3 `gaps.jsonl` 8 条 |
| 10 | 是否有冲突表 | ✅ | 8 条（`10_conflicts.jsonl`） |
| 11 | 每维是否至少有 §7 要求的伪代码 | ✅ | D1×4 / D2×4 / D3×3 / D4×3 / D5×3 / D6×3 / D7×3 / D8×4 |
| 12 | 伪代码是否有魔法常量 | ✅ 无 | 所有未知常量写成 `UNKNOWN` 符号 |
| 13 | 角色卡是否只有形容词、没有规则 | ✅ 无 | 27 张卡，每卡 ≥3 条 `decision_rules` |
| 14 | 覆盖矩阵是否覆盖 3.0–3.7 | ✅ | `D3_plot/coverage_matrix.md` 8 行 |
| 15 | 是否有"完整性声明" | ✅ | `00_manifest.md` 首段 |
| 16 | JSONL 是否逐行合法 | ✅ | 已跑 `validate.py`（见下） |
| 17 | 同一实体是否使用同一 id | ✅ | 术语表 + roster 对齐；昔涟/德谬歌/迷迷/无漏净子拆成 4 个 id 并标 `root_identity` |
| 18 | 是否记录了版本/抓取日期 | ✅ | 每条来源带 `game_version` / `captured_at` |

## 量化目标对照（§13.2）

| 项 | 目标 | 实际 | 结论 |
|---|---|---|---|
| 八维覆盖 | 8/8 | 8/8 有独立目录；D1/D2/D4/D5/D6/D8 = covered，D3/D7 = partial（见 `00_manifest.md` §2） | ⚠ 部分 |
| 实体索引 | 覆盖命名实体，unknown 列原因 | 93 条 | ✅ |
| Wiki claim 扩写 | 100% 有 expansion 或 UNKNOWN | 24 条 claim，22 条有 expansion，2 条标 B/线索 | ✅ |
| 3.0–3.7 覆盖 | 每版本 ≥1 章节条目 | 8/8 | ✅ |
| 终端文本 | 所有可获得 A/B 级 100% | 282 条（A 级 81 + wiki B 级 201；B 级已去重并按 output/log/garbage 分类） | ✅（B 级已标） |
| 对话 | Philia093↔德谬歌 100% | 357 条（225852–226200 全覆盖）；其中 55 条说话人已确认为 official(B) | ✅ |
| 轮回日志 | 官方锚点 100% | 46 条 anchor（A 级 30 + wiki B 级 16）+ 35 条 loop（33,550,336 轮中官方仅记录 35 轮） | ✅ |
| 社区碎片 | 每渠道至少一轮检索 | 5/14 有结果，其余留失败记录 | ⚠ 部分（见 channel_matrix） |
| 角色卡 | 登场且有独立意志者 100% | 27 张 | ✅（泰坦 3 张为 partial） |
| 伪代码 | 每维 ≥3 | 27 块 | ✅ |
| 冲突 | 多源差异全进表 | 8 条 | ✅ |
| 未知 | 缺口全进表 | 35 + 8 | ✅ |

## 抽样审计（§13.3）

随机抽 10%：

| 抽样对象 | 样本 | 结果 |
|---|---|---|
| 事实条目 | TRM-011 / TRM-058 / LOOP-33550336 / MV-021 / PLOT-006 | 5/5 可回指 locator |
| 伪代码 | PG-D1-001 / PG-D5-003 / PG-D8-002 | 3/3 无魔法常量，均有 UNKNOWN 分支 |
| 角色卡 | CHR-003 / CHR-013 / CHR-021 | 3/3 形容词均落成规则 |

**审计结论：通过。**

## 已知不达标项（诚实列出）

1. **D7 渠道覆盖 5/14**：贴吧/小红书/微博/抖音/HoYoLAB/X 未检索，Discord 不可检索。
2. **D8 泰坦卡（CHR-025/037/038）** 的 goals/relations 多为 `UNKNOWN`，因为原文没有独立台词与决策场景。
3. **D3 的 0 条「已补全」**：不是遗漏，而是口径从严（见 coverage_matrix.md 末节）。
4. **D4 的 302/357 行 speaker 仍为 inferred**：55 行已由 S-024 wiki 升级为 `official(B)`，其余因 wiki 无逐字同句或多说话人冲突保持推断。
5. **A 级客户端对 3.0–3.7 覆盖不全**：`b6_crosscheck` 显示 20/66 任务 `client_lines=0`，全量匹配率 7.4%；wiki（B 级）是唯一接近完整的叙事来源。
