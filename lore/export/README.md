# HSR 4.6 剧情文本导出工具

从《崩坏：星穹铁道》4.6.0 客户端本地数据提取的剧情对话，按章节/任务导出为可读文本。

**自包含**：`export_story.py` + `data/` 一起拷走就能用，只需 Python 3.8+。

## 目录

```
export/
├─ export_story.py        导出脚本（无第三方依赖）
├─ README.md              本文件
└─ data/
   ├─ story_full.jsonl    剧情结构 + 台词（712 任务 / 18,218 句）
   ├─ name_by_role.json   角色资源名 -> 中文名（63 个主要角色）
   └─ names.json          全量名字 key -> 中文（5,360 条）
```

## 用法

```powershell
python export_story.py --list                       # 列出所有任务（ID / 名称 / 台词数）
python export_story.py --mission 2021901            # 导出单个任务到屏幕
python export_story.py --mission 2021901 --out 铸剑为犁.md
python export_story.py --mission 2021901,1030101    # 多任务
python export_story.py --all --out ./out            # 全部导出，每任务一个 md
python export_story.py --mission 2021901 --json     # 机器可读
python export_story.py --grep 卡芙卡                 # 按台词内容搜索
python export_story.py --all --out ./out --no-empty # 跳过无对白节点
```

## 输出格式

```markdown
# 长日入夜行（Mission 1030101）

- 台词 13 句（有译文 11，85%）
- 在场角色：三月七、姬子、帕姆、丹恒、瓦尔特•杨、米沙

## DS10301010201

- 对啊对啊，什么事这么重要？
- 啊？我才刚刚收拾好行李欸！

## Story100010109

### 主线　Story10001010901.playable

- 这…是…哪里？
- 卡芙…卡？
- …你是…谁？

### 变体 1　Story10001010905.playable

- 喜欢…大概。
```

| 记号 | 含义 |
|---|---|
| `## Story<M><NN>` | 剧情节点（按编号推进） |
| `## DS<...>` | 支线/对话片段 |
| `### 主线` | 该节点台词最多的走向 |
| `### 变体 N` | 其他走向（通常是选了某选项后） |
| `**角色名**：` | 有识别到说话人时显示中文名 |
| `⟨缺译文 / 玩家选项⟩` | 该句没有解析到中文（多为玩家选择文本） |

## 数据说明

- **剧情树**：`Story<MissionID><NN>.prefab` 是节点，节点下多个 `.playable` 是分支走向。
- **台词**：`.playable` 里的 `TalkSentence_<id>` 引用，经 `TalkSentenceConfig_TalkSentenceText_<id>` 反查中文。
- **说话人**：取 `TalkSentence_<id>` 之后 400 字节内出现的第一个角色资源名（启发式，19.9% 覆盖）。
- **中文名**：角色资源名 → `NPCName_Avatar_<英文名>` → 中文（63/343 个角色有）。

## 覆盖情况

| 项 | 数值 |
|---|---|
| 任务 | 712（593 个有中文任务名） |
| 剧情节点 | 778 |
| 台词 | 18,218 |
| 有中文 | 15,847（87.0%） |
| 有说话人 | 3,246 句（19.9%） |

## 已知限制

1. **13% 台词没有中文**：这些 ID 在客户端文本表里不存在，多为 NPC 闲话。
2. **说话人覆盖 19.9%**：客户端未保留 `TalkSentenceConfig` 的说话人字段，只能用"句子后紧跟的角色名"启发式。
3. **路人 NPC 显示资源名**（如 `NPC_W3_Male_30`）：它们没有独立名字 key，游戏里也是通用称谓。
4. **台词保留游戏富文本标签**（`<unbreak>`、`<color=#...>`、`{NICKNAME}`、`{RUBY_B#...}`），渲染前需自行处理。
5. **"主线/变体"按台词数排序判定**，不保证等于游戏默认走向。

## 数据来源

客户端 `StarRail_Data\Persistent\DesignData\Windows\` 下的本地文件，只读提取，未联网、未运行游戏。
详细逆向过程见 `d:\文档\Amphoreus\lore\_probe\PROBE_REPORT.md`。
