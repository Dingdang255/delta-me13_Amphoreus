# HSR 4.6 中文 TextMap 探针报告

> 结论先行（2026-10-31 更新）：**中文文本表已定位并抽出 —— 5 个锚点在抽出的文本里全部命中（5/5）。**
>
> **D（文本表）**：`.block` 不是文本表本体。CN 文本表在**下载缓存**里：
> `E:\Star Rail\Game\StarRail_Data\Persistent\DesignData\Windows\cn\f96da886…bytes`（53.9 MB）。
> 它是 mhy 的"表 + 明文串池"格式（**不加密、不二次压缩**），抽取出 **457,301 条文本 / 1474 万字符**
> → `lore\_probe\textmap_zh_cn.jsonl`（48.8 MB）；锚点证据见 `lore\_probe\cn_textmap_hits.txt`。
> 锚点全中：`系统运行中`2、`运行时错误`2、`管理员批注`17、`Philia093.exe`3（原文带 `<unbreak>` 标签，去标签后命中）、`【载入核心变量`2。
>
> **D 严格映射（2026-10-31 追加，已破）**：CN 表每条 = `<tag><varint A><varint B><len><utf8>`
> ，且 **`B == xxh64(本地化 key 名) & 0x7FFF…`**。用它把配置表的明文 key 反查回文本，
> 得到 `lore\_probe\textmap_keyed.jsonl`（9,937 条 `key→text`）与 `talk_textmap.jsonl`（11,724 条台词，§11.3）。
>
> **块负载**：仍然成立 —— `.block` 块负载 = Oodle 流，用 `UnityPlayer.dll` 内嵌
> `oo2::OodleLZ_Decompress`（RVA `0x14c47a0`）可解（`5fd55f5e` 1106/1109 块 → 34.9 MB 明文）。
> 但**它不是文本表的来源**，只是 mod/UI 资源；做 TextMap 不必全库解 7~9 小时。
>
> **D 下半场 —— 对话树（2026-10-31 新增）**：`Persistent\DesignData\Windows` 下那几个大哈希 `.bytes`
> 全是"表 + 明文串池"。其中 `4ce18f6b…bytes`（5.27 MB）是**剧情编排表**，`1efaad7a…bytes`（33 MB）是**配置总表**。
> 用"`Story/...playable` 段起点 + 顺序归属"直接解出 **29,044 个剧情段 / 26,508 条台词引用**，
> 合并文本后 **19,022 句有中文（71.8%）** → `lore\_probe\story_dialogue.jsonl`（§13）。
>
> **E（补齐 3%~17% 解不开的块）**：本轮用日志回调把 Oodle 的 `verbosity=3` 日志接出来并自己格式化变参，
> 拿到每个块声明的**压缩器名**：能解的都是 **Kraken**，解不开的是 **Leviathan / Mermaid**。
> 再排除 rawLen 全扫、尾部截断、起点偏移、verbosity、11 种 XOR 变体 → **失败与参数、XOR 均无关**，
> 是 Unity 内置 Oodle 为裁剪版（`.rdata` 里只有 `newlz/newlzhc/newlzf/lzb`，无 Leviathan 实现）。
> 另确认一个坑：**`ret == us` 不等于解压正确**（§12）。

---

## 1. 结论速览

| 项 | 结果 |
|---|---|
| 工具链是否可用 | **可用**。ENCR 解析、blocksInfo(LZ4) 解压、目录/节点表解析、**块负载 Oodle 解压** → 全部跑通；单文件成功率 99.7%（`5fd55f5e`）/ 83%（`4c7c`） |
| 是否拿到中文 TextMap | **是**。CN 文本表在下载缓存 `Persistent\DesignData\Windows\cn\f96da886…bytes`（53.9 MB，不加密、不二次压缩），抽出 **457,301 条 / 1474 万字符** → `lore\_probe\textmap_zh_cn.jsonl`（§11）；`.block` 只是 mod/UI 资源 |
| 是否有严格 `key→text` 映射 | **是**（2026-10-31）。`B == xxh64(本地化 key 名) & 0x7FFF…` → `textmap_keyed.jsonl` 9,937 条、`talk_textmap.jsonl` 11,724 条（§11.3） |
| 是否有对话树 | **是**（2026-10-31）。`4ce18f6b…bytes` 剧情编排表 → **29,044 段 / 26,508 条台词引用 / 71.8% 有中文** → `story_dialogue.jsonl`（§13） |
| 卡点分类 | ~~④ 块负载~~ / ~~⑤ TextMap 定位~~ / ~~⑥ 严格映射~~ / ~~⑦ 对话树~~ → **均已解决**；唯一遗留 = 约 3%~17% 的块（Leviathan/Mermaid）**用游戏内置解码器解不开**（§12），**不影响文本侧** |
| 块解压入口（本轮实测） | **`oo2::OodleLZ_Decompress` @ `UnityPlayer.dll` RVA `0x14c47a0`**（VA `0x1814c47a0`）；`0x14c3820` 是它调用的内部 helper（签名不同，别用）；头部解析 `0x14c5980`、入口校验 `0x14c3740` |
| 是否运行过构建 | **否**（没有任何 `dotnet build` / cargo / npm / gcc；只跑了 Python） |
| 版本号 | `game_version=4.6.0`；构建线 `V4.6Live` / `20260917-0139` / `520260917-0139-V4.6Live-16566615-CNPRODWin4.6.0-CnLive` |
| 锚点（精确） | **5 / 5 达成**（基于 CN 文本表、去富文本标签后：`系统运行中` 2、`运行时错误` 2、`管理员批注` 17、`Philia093.exe` 3、`【载入核心变量` 2）；证据 `lore\_probe\cn_textmap_hits.txt`（§11） |
| 全库扫描成本（实测） | 19889 个 `.block` / **130,192,896,833 B（121.3 GiB，十进制 130.2 GB）** / **3247 s（54.1 min）** / 平均 **38 MB/s** |
| 解压吞吐（实测） | 单文件 5 MB → 34.9 MB 明文（1084 段 / 1109 块）耗时 **1.0 s**（约 5 MB/s 输入、35 MB/s 输出） |

一句话：**壳开了，块也开了**。`.block` = ENCR 容器（LZ4 压缩的 blocksInfo + `CAB-<hash>` 节点表），
块负载 = **Oodle（oo2）流**：`0x06` 直接是 Oodle 流、`0x07/0x05` 先 `mr0k` 去掉 0x14 字节再是 Oodle 流、`0x00` 原样。
用游戏自带的 `UnityPlayer.dll` 内嵌解码器即可逐块解出（`lib\oodle_call.py`）。



---

## 2. 环境与版本（全部从文件读出，非猜测）

| 来源 | 内容 |
|---|---|
| `E:\Star Rail\Game\config.ini` | `game_version=4.6.0`、`game_biz=hkrpg_cn`、`sub_channel=1` |
| `StarRail_Data\StreamingAssets\BinaryVersion.bytes`（246 B） | `V4.6Live`、`20260917-0139`、`PROD`、`520260917-0139-V4.6Live-16566615-CNPRODWin4.6.0-CnLive`、`fb7d74e443`、`e5239110b1f611f1b741a59d70a519d3` |
| `pkg_version` | 与上述 4.6 线路一致 |
| `.block` 内明文 | Unity 版本串 `2019.4.34f1.2`（亦见 `2019.4.34f.2`） |

> 数据日期与描述一致（2026-09 构建）。另注意：多个块内明文出现 `\amphoreus\Irontomb.exe`、
> `来自未知发布者的程序 … Philia0912`、`管理员批注.wav` 等，说明该客户端内含一个 **mod / 私服性质的 UI 资源**，
> 这就是锚点所在的来源。

---

## 3. 工具链选型与理由

| 候选 | 结论 | 理由 |
|---|---|---|
| **Python 3.14 纯自研脚本**（`tools\hsr_probe\`） | **采用** | 零第三方依赖（LZ4 块解码器为手写、已自检），不写 C 盘，全部操作为 `open(...,'rb')` 只读；结构解析用 `struct` + 大端约定，可审计、可复现 |
| **StarRailRepacker**（开源，GPL-3.0，`ref\`） | **采用（仅算法参考/移植）** | 目前唯一公开的 miHoYo `ENCR` + `mr0k` 实现；移植了 `mr0k_decrypt` + AES-128 轮密钥 + 常量表。**但它面向 2023 版**（flags `0x42/0x43`，产出 `0x45`=LZ4+Mr0k），不覆盖本包的 `0x06/0x07/0x03/0x05` |
| **AssetStudioMod v0.19.0**（aelurum，官方 Release，CLI） | **否决** | 对 `.block` 直接报 `No Unity file can be loaded.`——它不识别 `ENCR` 容器；其 `--blockinfo-comp`/`--block-comp` 只对"已解壳的 .unity3d"有效 |
| 来源不明的打包 exe | **不使用** | 违反"优先开源/官方发布页"约束 |
| .NET SDK 10 / Node 22 | 未使用 | 无对应开源实现；且任何构建动作都需先获授权 |

---

## 4. 已打通的链路（含证据）

产物：`d:\文档\Amphoreus\tools\hsr_probe\`（脚本 + `ref\magic_constants.h`）。
`lib\` 与 `ref\` 必须保持同级（`hsr_block.py` 按 `../ref/magic_constants.h` 读取常量）。

### 4.1 ENCR 容器（已确证）

```
"ENCR"(4B) + 0x00(1B) + u64BE totalSize + u32BE blocksInfoCompSize
+ u32BE blocksInfoUncompSize + u32BE flags(0x43) + blocksInfo + blocks...
```
- 单个 `.block` 内**含多个** ENCR 段；遍历：`pos = off + totalSize`（`total<=0` 时 `pos = off+1`）。
- `blocksInfo` 为 **LZ4 block**（`flags & 0x3F ∈ {2,3}`），纯 Python 解压成功。
- 段布局自校验：`total - 25 - blocksInfoCompSize == Σ block.compressedSize`
  （例：seg#240 `total=2871, infoCS=64, cs=2782` → `2871-25-64=2782` ✅）。

### 4.2 blocksInfo 结构（大端）

```
u32 blockCount → 每块 (u32 uncompressedSize, u32 compressedSize, u16 flags)
u32 nodeCount  → 每 node (u64 offset, u64 size, u32 flags, cstring path)   # CAB-<32hex>
```

### 4.3 一致性验证：`node.size == Σ block.uncompressedSize`

| 文件 | 段 | blocks | Σus | node.size | 结论 |
|---|---|---|---|---|---|
| `4c7c230cc476e91b383188906d154252.block` | #93 | `cs=24676/us=262144/0x07` + `cs=6525/us=84165/0x06` | **346309** | **346309** | ✅ |
| `5fd55f5e…block` | #240 | `cs=2782/us=15012/0x06` | 15012 | 15012 | ✅ |
| 同上 | #258 | `cs=2708/us=15348/0x06` | 15348 | 15348 | ✅ |

→ `us` 确实是**解压后大小**，块数据确实被压缩（不是 offset 语义误读）。

### 4.4 LZ4 解码器自检（证明"不是解码器写错"）

`lib\selftest_lz4.py`：人工构造 `30 | "abc" | 03 00 | 00` → 期望 `abcabca`，**通过**。
此后所有"块解不开"的失败都**不是 LZ4 解码器**的 bug。

### 4.5 索引与 Lua 旁证（已排查）

- `Asb\Windows\`：**19889 个 `.block`，130.2 GB**；目录下另有 **24 个索引 `.bytes`**
  （`M_AsbV.bytes`、`M_BlockV.bytes`、`Start_*`、`BlockV_*`(46KB~226KB)、`Start_AsbV_*`(416KB~4MB)、
  `AsbV_*`(9.6MB / 16.5MB / 24.3MB / 30MB / 81.8MB)）。对这 24 个文件扫 `TextMap|textmap|TextAsset|Chinese|zh_CN`
  → **0 命中**（索引里只有哈希，没有可读资源名）。
- `StreamingAssets\Lua\Windows\`：61 个 `.bytes`（116.6 MB），含三种格式：
  LuaJIT 字节码（`\x1bLuaS\x01\x19\x93`）、`\x04\x01\x0f\x01G\rImportCsToLua…` 绑定文件、
  以及一个 JSON manifest（2,178,103 B，**17852 条 Path**，前缀分布 Ui 15303 / Generate 1966 / Logic 468 / …）。
  manifest 中含 `Ui/TextMapAndLocalization/TextmapStatic` → **TextMap 是编译进代码的路径**，文本表本体仍在 `Asb` 里。
  Lua 全量扫锚点 **0 命中**，`TextMap` 出现 37 次。
- 根目录二进制全扫（`GameAssembly.dll` 543.5 MB、`mhypbase.dll` 26.7 MB、`StarRailBase.dll` 21.8 MB、
  `UnityPlayer.dll` 38.8 MB、`StarRail.exe`、`UnityCrashHandler64.exe`），
  8 个模式 × UTF-8 + UTF-16LE → **全部 0 命中**（未触碰 `AntiCheatExpert` / `HoYoKProtect.sys`）。
  → 锚点确实只存在于 AssetBundle 里，不是 DLL 字符串表。

---

## 5. 块负载格式（曾经的卡点，现已解决）

> 结论：**块负载 = Oodle（oo2）流**。`0x06` 整体是 Oodle 流；`0x07/0x05` 先 `mr0k` 去 0x14 字节再是 Oodle 流；`0x00` 原样。
> 下面 5.1~5.5 是求解过程（含走过的弯路），5.6~5.7 是定位与实测。

### 5.1 flags 分布（300 个小文件 / 868 段 / 3456 块）

| flags | 数量 | 负载首字节 | 判定 |
|---|---|---|---|
| `0x06` | 2117（61.3%） | **恒为 `0x8c`** | Oodle 流（8 字节为 Oodle chunk 头） |
| `0x07` | 1243（36.0%） | 恒为 `m`（`mr0k` magic 命中 1700/1700） | mr0k 包装 |
| `0x03` | 90 | — | 名义 LZ4HC |
| `0x05` | 12 | `mr0k` | mr0k 包装 |
| `0x00` | 6 | 原样 | 唯一 `cs == us` |

### 5.2 `0x06` chunk 头（4 个独立样本全部吻合）

```
cs=918   : 8c 06 00 | 03 90 | 88 | 03 8e      → 0x390 = 918-6 , 0x38E = 918-8
cs=6525  : 8c 06 00 | 19 77 | 88 | 19 75      → 0x1977= 6525-6 , 0x1975= 6525-8
cs=524   : 8c 06 00 | 02 06 | 88 | 02 04      → 0x206 = 524-6 , 0x204 = 524-8
cs=2782  : 8c 0a 00 | 0a d8 | 88 | 0a d6      → 0xAD8 = 2782-6 , 0xAD6 = 2782-8
```
即（**已修正**，先前把 `[2:5]` 误读成 `[2]=0x00` + `[3:5]=u16`）：

```
[0]      = 0x8c                        固定
[1]      ∈ {0x06,0x0a,0x0c}            压缩器类型（与 Oodle 分派常量一致，见 §5.6）
[2:5]    = u24BE(cs-6)                 "6 字节头之后剩余长度"
[5]      ∈ {0x80,0x81,0x82,0x88,0x89,0x90,0x98,0x99}
[6:8]    = u16BE(cs-8)                 "8 字节头之后剩余长度"
```

### 5.3 "内层头"的真身：就是 Oodle 的 chunk/quantum 头（含 `us`）

同文件 `5fd55f5e…block` 的 1006 个 `0x06` 块：

```
cs=524  : 8c 06 00 02 06 88 02 04 | 00 00 00 c5(197) | 00 00 13 d0(5072=us)  | 00 01 37 15 | 10 00 00 | "2019.4.34f1.2"…
cs=4749 : 8c 06 00 12 87 88 12 85 | 00 00 00 c5(197) | 00 00 da b0(55984=us) | 00 0b f6 15 | …
cs=2782 : 8c 0a 00 0a d8 88 0a d6 | 00 00 06 35(1589) | 00 00 3a a4(15012=us) | 00 06 24 00 | 15 10 00 | "2019.4.34f1.2"…
```
统计：**`u32@0x0c == us` 命中 995 / 1006（98.9%）**；`u32@0x08` 取值分散（197×285、169×22、2817×7…）。
→ 前 8 字节就是 Oodle chunk 头，紧随其后的字段是 Oodle 的**量子（quantum）头**（其中 `u32@0x0c` 正好是该块解压尺寸 `us`）。
实测（§5.7）：**把整段（含这 8 字节）原样交给 Oodle 就成功**，不需要自己做任何"内层头"剥离。

（**已撤销**上一版的"`4c7c…` 只有 65/142、块起点早 1~2 字节"结论：本轮复核证明**块间不存在 1~2 字节偏差**，
真实起点 `0x3327EE` 处正是 `8c 06 00 19 77 88 19 75`，先前的偏移是我把基线算错了。
全量复核：块首字节 `0x8c` 命中 **2117/2117（100%）**；在本轮普查的 **25206 个块**上 `[2:5]==cs-6` 亦 100% 成立。）

### 5.4 关键旁证：块内可见大段明文（"literal 以原文存储"）

原始字节中可直接读到：`2019.4.34f1.2`、`m_Script`、`Cubebuiltinassets/models/c.fbx.unity3d`、
`BlockEnvExportData`、`SceneLightManager`、`Assembly-CSharp.dll`、`mChap04_MAZ_A801_CloseViewR3_PropADVday_01_Varient_A02_b0`、
`[ErrTextID]:UI_TarotBook_Joystick_Continue`、**`管理员批注.wav`**、`$Appname_Specialfile`、
`>>>系统运行中…`、`发生了未经处理的异常(1/3)`、`对象名:"…"`、`节选信息`、`忽略并继续`、`查看完整日志`。

同时命中区里能看到"被打断"的文本，例如：

```
... >>>系统运行中… | bb 17 | <δ-me<ub>13</ub>:\amphoreus\Irontomb.exe  | c2 a0 | 时错误 ...
... 来自未知发布者的程序 c2 a0 | ddmiuge\Philia0912 | 18 98 | 是否允许 | 86 99 | 入？ ...
```
- `是否允许`、`入？`、`时错误` 都是**完整正确的 UTF-8**；
- 而"运"（`e8 bf 90`）、"载"（`e8 bd bd`）位置变成了 2~3 字节的二进制码（`bb 17`、`86 99`），
  这正是**回溯匹配（match）把重复子串编码掉**的形态。

→ 由此可得两个结论：
1. **块数据没有整体加密**（否则不会有成段明文）；
2. 裸字节扫描之所以拿不到完整锚点，是因为**压缩流没解压**（被 match 编码的部分不在磁盘上）；
   解压之后 `>>>运行时错误`、`>>>Philia<ub>093</ub>.exe` 等都能完整出现（§7）。

### 5.5 历史记录：改用 Oodle 之前已排除的解法

> 下面这些尝试都是在"不知道是 Oodle"的时候做的；现在回看，它们排除 LZ4/LZMA/zstd 是对的，
> 而"裸字节拿不到完整锚点"的原因很简单 —— **压缩流没有解压**（`>>>运行时错误` 解压后就有 4 次）。

| 尝试 | 结果 | 证据 |
|---|---|---|
| 标准 LZ4 block（前缀 0~24 枚举、le/be、nibble swap、offset==0 特判、要求输出长度==us） | 0 成功 | 5 个样本全失败（`bad match offset` 1057 次、`zero offset` 643 次） |
| "8 字节头 + 原样前缀"（前缀长 8~400 全枚举，start_out ∈ {0,8}） | 0 成功（6 样本） | 输出长度始终 ≠ us |
| mr0k 解密 → LZ4 | 0 成功（1700 块） | 移植 AES-128/mr0k 后仍 `bad match offset` |
| zlib / bz2 / lzma / zstd | 全部失败 | 直接抛格式错误 |
| **已知明文 oracle 反推**（新增）：用"解压结果必含 `>>>系统运行中`"当判据，对锚点真实所在块（seg#240 / seg#258）枚举 `skip 0~79 × swap × endian × seed` = 640 变体 | **0 命中**（没有任何变体成功产出数据） | `lib\oracle_probe.py` |
| **zstd 结构性重构**（新增）：`magic(4) + 11 种 FHD × 256 种 windowDesc × 前缀 0~39 × 端序` | **0 命中** | `p33`~`p35` 系列 |
| **小样本穷举**：两个 ≤1KB 的 `0x06` 块（cs=51/us=532、cs=169/us=676），起点 0~39 × 端序全试 | 无任何起点解码 ≥32 字节（最好一次 out=49/532） | `lore\_probe\small_blocks.txt` |
| **插件/子模块排查**（新增）：`abci.dll`、`hpatch.dll`、`xluau`、`Astrolabe.dll` 等 | 全部无块格式线索（只有 OpenSSL/BoringSSL/zstd 通用串） | `lore\_probe\plugins_scan.txt` |
| **托管层（il2cpp）排查**（新增）：`global-metadata.dat` 306717 串 | 只有路径串（`.block`/`BlockV`/`AsbV`/`AssetBundles`），**无任何编解码器类名** | `lore\_probe\metadata_strings.txt` |
| **`ENCR` 立即数扫描**（新增）：四个模块可执行段找 `45 4E 43 52` | **四模块全 0 命中**（说明容器解析发生在高熵保护段/运行期） | `lore\_probe\encr_xrefs.txt` |
| AssetStudioMod CLI 直读 `.block` | 失败 | `No Unity file can be loaded.` |

> 附注：首次 oracle 尝试因我把 `1067125` 误当成 106,125 所在段而扫错了段（seg#35/#36），已修正为 seg#240/#258 并重跑，
> 结果仍为 0 —— 这条弯路本身也说明"前缀枚举"路线不成立。

---

### 5.6 静态定位：块解压器 = `oo2::OodleLZ_Decompress`（UnityPlayer.dll）

**做法（全部只读，无构建、无调试器）**

1. 对四个大模块做 PE 头/导入导出/字符串/段熵统计（`p30_pe_static.py`）→ 发现 `UnityPlayer.dll` 内含 Oodle 全套错误串；
2. 把 Oodle 相关串连同 96B 上下文导出（`p37_oodle_ctx.py` → `oodle_ctx.txt`，202 条）；
3. 纯 Python 扫 **RIP-relative LEA**（`REX + 0x8D + modrm∈{05,0D,15,1D,25,2D,35,3D}`，`target = secVA + i + 7 + disp32`）
   找引用这些串的代码点（`p42_xref.py` / `p43_xref2.py`）→ **56 处命中**，全部落在 `0x1814c3740`~`0x1814c4f00`；
4. 只对这一个 **约 6KB** 的命中区间做 `objdump -d --start-address/--stop-address`（不做全量反汇编）。

**结论（三条互相印证）**

| 证据 | 内容 |
|---|---|
| 字符串 | `OODLE ERROR : OodleLZ_Decompress: first byte is zero; this is likely not valid compressed data!`、`…data is either corrupted, not a valid Oodle stream, or was compressed with an unsupported legacy compressor!`、`…asked to decode legacy compressor; not supported!`、`CHUNK header @ %lld  , compressor %d=%s %s %s`、`QH : %d , %d , %08X`、`OODLE ERROR : LZ corruption : qh.compLen > qh_rawLen!`、`DecodeOneQuantum` 等；压缩器名表 `Kraken / Mermaid / BitKnit / Selkie / Leviathan` 也都在 |
| 函数身份 | `assert` 消息里把函数名 `oo2::OodleLZ_Decompress` 作为参数传入（`0x1814c4b59` 处 `lea r8, "oo2::OodleLZ_Decompress"` + 行号 `0x5af`），即**该函数就是 `oo2::OodleLZ_Decompress`** |
| 地址 | 真正的 `oo2::OodleLZ_Decompress` 主体：**VA `0x1814c47a0` / RVA `0x14c47a0`**（int3 填充定界 `0x47a0..0x4eea`，读取 14 个参数并在 `0x118(%rbp)`/`0x128`/`0x130`/`0x138`/`0x140` 处取 `decBufSize/callbackUserData/decoderMemory/decoderMemorySize/threadPhase`）；`0x1814c3820`（RVA `0x14c3820`）是**它内部调用的 helper**（`call @0x1814c4c83`），签名不同，直接调用会返回垃圾值；入口校验 `0x1814c3740`、头部解析 `0x1814c5980` |

**与我们块头的对应**

函数主体在 `0x1814c4000` 附近出现 `cmp $0x6,%edx` / `cmp $0xc,%edx` / `cmp $0xa,%edx` 的分派，
紧接着取 `0x44(%rbx)` 构造解码参数 —— 这三个常量 **恰好是我们 `0x06` 块头 `[1]` 出现过的全部取值 `{0x06,0x0a,0x0c}`**。
按 Oodle 的压缩器枚举，它们对应 `LZA(6) / BitKnit(10) / Hydra(12)`（注意：**不是** Kraken）。

**同时排除了"外挂 Oodle DLL"这条路**

- 游戏目录 178 个 DLL 里**没有** `oo2core_*.dll` / 任何 `oodle|oo2|kraken|ooz` 命名的文件（`p44_dll_search.py` → `oodle_dll_search.txt`）；
- `mhypbase.dll` 里的 `OO2` 串位于 `.upx0`（13.67MB，熵 7.93）—— **高熵保护段，无法静态使用**；
- `GameAssembly.dll` 的 `il2cpp` 段 343MB、`.upx0` 22.31MB(熵7.30)，导出只有 `il2cpp_get_api_table`，无 Oodle 符号。

→ 也就是说：**唯一的 Oodle 解压实现是 `UnityPlayer.dll` 内的这份（且未导出）**。

---

### 5.7 实测：ctypes 调 `UnityPlayer.dll` 内嵌 Oodle → 整文件解压成功（方案 A）

**调用方式**（`tools\hsr_probe\lib\oodle_call.py`，纯只读，不启动游戏）

```python
_dll = ctypes.WinDLL(r"E:\Star Rail\Game\UnityPlayer.dll")   # 仅把 DLL 映射进本 Python 进程
fn = PROTO(_dll._handle + 0x14C47A0)                          # 直接用 RVA 取函数指针
ret = fn(compBuf, compLen, rawBuf, rawLen, 0,0,0, None,rawLen, None,None, None,None, 0)
# 14 参：compBuf/compSize, rawBuf/rawLen, fuzzSafe, checkCRC, verbosity,
#        decBufBase/decBufSize, fpCallback/callbackUserData, decoderMemory/decoderMemorySize, threadPhase
```

- 成功消息：`ret == rawLen`（精确等于该块 `us`）；失败消息：`ret == 0`。
- 关键坑：`rawLen` 必须**精确等于**流内声明的解压长度，传大（如 2×`us`）也会返回 0。
- 起点偏移：`start=0` 成功（`ret==us`），`start=2/4/6/8` 全部 `ret=0` → 8 字节外层头就是 Oodle 自己的 chunk 头，**不能跳过**。

**整文件结果**（脚本 `p48_oodle_file.py`，逐段逐块解压并拼接）

| 文件（`.block`） | 段数 | 块 ok / fail | 明文字节 | `m_Script` | `CAB-` | 锚点 |
|---|---|---|---|---|---|---|
| `5fd55f5e5454a91a7fd107041f537036` | 1084 | **1106 / 3**（mr0k 103） | **34,922,891** | 2535 | 304 | `系统运行中`×4、`运行时错误`×4 |
| `4c7c230cc476e91b383188906d154252` | 303+ | 205 / 41（mr0k 104） | 28,606,472 | 1 | 3692 | `管理员批注`×2 |
| `952a58f4cfa6e3b0c606ccc491d53134` | 303+ | 391 / 40（mr0k 133） | 34,195,023 | 54 | 2048 | 0（其 `管理员批注` 落在失败块里） |

- 解压后的开头不是 `UnityFS` 明文，而是 `00 00 06 35 | 00 00 3a a4 | 00 00 00 15 | 00 00 10 00 | 0 | "2019.4.34f1\n2" …`
  （HSR 的 bundle 头不是标准 `UnityFS` magic）；`UnityFS` marker 在 3 个文件里都是 0。
- 明文里能看到完整的富文本：`>>>Philia<ub>093</ub>.exe…运行中…`、`>>>﻿-me<ub>13</ub>:\amphoreus\Irontomb.exe…运行时错误`。

**失败块分析（`p49`~`p54`）**

| 项 | 结果 |
|---|---|
| 规模 | 3 个文件共 **1355 块 / 84 失败（6.2%）**；`5fd55f5e` 仅 3/1109（0.27%），`4c7c` 41/246（16.7%） |
| 分布 | `4c7c` 的 41 个失败**全部是 flags `0x07`**（mr0k 块）；按压缩器类型分：`0x06` 3/456、`0x0a` 27/839、`0x0c` 14/60 |
| 头部自洽 | 失败块的 `mr0k` 解密结果是**合法 Oodle chunk 头**（`8c 06/0a/0c 00 <u24BE = len-6> …`），说明 mr0k 解密没错、块边界没错 |
| 变体尝试 | `fuzzSafe∈{0,1}`、`checkCRC∈{0,1}`、`verbosity∈{0..3}`、`threadPhase∈{0,1,2,3}`、`rawLen±1`、`rawLen=2×us`、`src` 偏移 `0..8`、LZ4 兜底 → **全部 `ret=0`**；`verbosity=2/3` 也没有打印任何 OODLE ERROR 串 |
| 跨块窗口 | 用 `decBufBase/decBufSize` 把前一块的解压结果当历史窗口（全历史 / 仅 256 KB）→ **仍 `ret=0`** |
| 结论 | 不是我们解析错了，而是这批流的"某些量子头写法"**超出 `UnityPlayer.dll` 内这份解码器的支持面**（最可能是较新 Oodle 版本/参数产出的流）。这是**目前唯一遗留缺口**，约占全库 3%~17% 视文件而定 |



## 6. 文本规模（当前）

- **CN 文本表已抽出（§11）**：**457,301 条 / 14,743,678 字符**（去富文本标签后 12,478,345 字符），
  产物 `lore\_probe\textmap_zh_cn.jsonl`（48.8 MB）。与社区经验值（15~25 万 key）同量级。
- `.block` 解压明文（另一路旁证）：3 个 `.block` 合计 **97.7 MB**（34.9 + 28.6 + 34.2），
  其中 `m_Script` 共 2590 处、`CAB-` 共 6044 处；但 `TextMap` / `TextAsset` 这两个 marker 在 3 个文件里都是 0
  → **`.block` 只是 mod/UI 资源，不是文本表本体**（本轮 `p56` 有界试点亦证实，见 §11.1）。

---

## 7. 锚点命中情况（解压后明文 + CN 文本表）

| 锚点 | 精确命中 | 证据 |
|---|---|---|
| `>>>系统运行中` | ✅ **4 次** | `5fd55f5e5454a91a7fd107041f537036.block` 解压后偏移 **8659793 / 8695053 / 8735357 / 8868712**（裸字节阶段是 1067125 等，因压缩而错位）；原文 `>>>系统运行中…`，后接 `-me<ub>13</ub>:\amphoreus\Irontomb.exe 运行时错误`、`发生了未经处理的异常(1/3)(2/3)(3/3)`、`对象名:"…"`、`节选信息`、`忽略并继续`、`查看完整日志` |
| `>>>运行时错误` | ✅ **4 次** | 同上文件 **8660459 / 8695719 / 8736023 / 8869378**（裸字节阶段 0 次 → 解压后 4 次，**推翻了旧的"被 match 吃掉"猜测**：那时只是没解压） |
| `管理员批注` | ✅ **2 次** | `4c7c230cc476e91b383188906d154252.block` 解压后 **19704096 / 19724760**（`管理员批注.wav` + `$Appname_Specialfile`，前有 `[ErrTextID]:UI_TarotBook_Joystick_Continue`）；裸字节阶段 `952a58f4…block` @1148209 那次落在**未解码的失败块**里 |
| `Philia093.exe` | ⚠️ 富文本形式命中 | 明文里是 `>>>Philia<ub>093</ub>.exe…`（5 处：8679121 / 8716373 / 8753673 / 8870055 / 8883188）；**去标签后即 `Philia093.exe`**，逐字精确匹配当然为 0 |
| `【载入核心变量` | ❌ 0 次 | 3 个已解文件里 `载入` / `核心变量` 均 0；Asb 全库裸扫、Lua、24 个索引、根目录 DLL 也 **全部 0**（可能在其他 bundle，待定位） |

**硬性判据（≥3 个精确命中）→ 已达成：3/5 精确（去掉富文本标签算 4/5）。** 裸字节阶段的明细见 `lore\_probe\anchor_hits.txt`。

**CN 文本表侧（2026-10-31，`p67` 去富文本标签统计）→ 5/5 全中：**

| 锚点 | 次数 | 证据 |
|---|---|---|
| `系统运行中` | **2** | `>>>系统运行中…` |
| `运行时错误` | **2** | `>>>δ-me<unbreak>13</unbreak>:\amphoreus\Irontomb.exe 运行时错误` |
| `管理员批注` | **17** | 含 `管理员批注.wav` 等 mod/UI 文本 |
| `Philia093.exe` | **3** | 原文 `Philia<unbreak>093</unbreak>.exe`（去标签即精确命中） |
| `【载入核心变量` | **2** | `【载入核心变量：开拓】` / `【载入核心变量：毁灭】` |

明细已写入 `lore\_probe\cn_textmap_hits.txt`（2233 B），抽取脚本 `p64`、校验脚本 `p67`（§11）。

> 说明：`.block` 里的这批命中都属于 UI/mod 资源（异常对话框、音频文件名）——它们证明"解压链路正确、中文文本未整体加密"；
> **真正的文本表在下载缓存里**，本轮已定位并抽出（§11），5 个锚点全部命中。

---

## 8. 磁盘与耗时

| 项 | 数值 |
|---|---|
| 只读源数据 | `Asb\Windows\` 19889 个 `.block` / **130,192,896,833 B（121.3 GiB）** |
| 单文件顺序读 | 实测 **166 MB/s**（126 MB 文件） |
| 全库遍历实测 | **38~49 MB/s**（小文件为主，受 open/close 与碎片限制） |
| 全库裸扫描（1 遍） | **3247 s（54.1 min）**，平均 38 MB/s |
| 工具与缓存（E 盘） | `E:\HSRProbe` 约 **85 MB**（含 AssetStudioMod 24.5 MB zip + 解压件） |
| 产物（d 盘） | `tools\hsr_probe\` 脚本 ~50 KB；`lore\_probe\` 文本产物 ~700 KB（已含 `oodle_file.txt` 63 KB、`oodle_file.5fd55f5e.txt` 63 KB、`fail_probe.txt`、`header_stats.txt`、`param_probe.txt`）；另有一份 34.9 MB 明文样本 `lore\_probe\_dec\5fd55f5e….dec.bin` |
| 本轮新增产物（2026-10-31） | **`textmap_zh_cn.jsonl` 48.8 MB**（457,301 条）、`cn_textmap_hits.txt` 2.2 KB、`textmap_scan.txt` / `textmap_scan.log`、`cab_catalog_dbg.txt`、`lua_textmap.txt`、`mr0k_xorlen.txt` |
| C 盘写入 | **无**（未在 C 盘产生临时文件；Python 的 stdout 持久化日志由 IDE 自己写，不是脚本行为） |
| 探针总耗时（含历次失败试探） | 约 5 小时 |

---

## 9. 全量提取估算

**中文 TextMap 已实测完成，不需要全库解压**：直接读 1 个 53.9 MB 的 `.bytes`，抽取仅 **4.4 s**
（`p64`），产物 48.8 MB（§11）。下表仅用于"若要解 `.block` 里的 mod/UI 资源"时参考。

前提已满足：块负载可解（Oodle）。按实测 5 MB/s 输入（≈35 MB/s 输出）估算：

| 场景 | 时间 | 空间 |
|---|---|---|
| **`.block` 里找 `m_Script`/TextAsset**（已证明**不必做**：`.block` 无 TextMap，`p56`） | 全库 130.2 GB ≈ **7~9 小时**（每块都要过一次 Oodle）；若先用索引/哈希定位目标 `.block`，可压到**分钟级** | 产物 30~80 MB；临时 < 1 GB |
| 全量文本类（多语言 TextMap + Lua + 配置表） | **10~20 小时** | 约 **3~8 GB** |
| 全量资产（模型/贴图/音频，本任务明确不做） | 数十小时~数天 | **远超 E 盘剩余 52 GB**，需外部存储 |

---

## 10. 下一步（按优先级）

**已完成（本轮，按"1→2→3 挨着来" + 方案 A）**

1. ~~修正块对齐~~ → **证实不存在偏差**：`[2:5]=u24BE(cs-6)` 100%、块首 `0x8c` 100%、`0x3327EE` 处字节完全吻合。
2. ~~找 2024+ 开源实现~~ → **没有可用的**：GitHub 7 组查询只捞到 `DNLINYJ/StarRailRepacker`(2023-09)、
   `alexpado/hoyoverse-music-unpacker`(2025-07)，均无 4.6 块格式；Bing/中文检索亦无。
3. ~~静态分析定位块解压函数~~ → **已定位**：`oo2::OodleLZ_Decompress` @ `UnityPlayer.dll` RVA `0x14c3820`（helper），
   真入口 **RVA `0x14c47a0`**（§5.6）。
4. ~~方案 A：ctypes 调内嵌 Oodle~~ → **已跑通**：3 个 `.block` 逐块解压，明文 97.7 MB，锚点 3/5 精确命中（§5.7、§7）。

**后续（都需要你先拍板）**

| 方案 | 状态 | 做法/结果 | 需要授权 |
|---|---|---|---|
| **D. 定位并反序列化 TextMap** | ✅ **已完成（2026-10-31）** | 先做有界试点（`p56`：38 个大 `.block` / 1.23 GB → `TextMap/TextAsset/m_Script` **全 0**）否定"Asb 里有文本表"；转而排查下载缓存 `Persistent\`（12.5 GB），命中 `DesignData\Windows\cn\f96da886…bytes`（53.9 MB，934 万汉字），确认是 mhy"表 + 明文串池"、**不加密不二次压缩**；`p64` 抽出 **457,301 条 / 1474 万字符**，`p67` 校验 **5/5 锚点**（§11） | — |
| **E. 补齐那 3%~17% 失败块** | ⚠️ **本轮已试，未破** | 已排除"`us` 算错"（`Σus == Σnode.size`，`p57` 300 文件 22172 段 `mismatchSegs=0`）；mr0k XOR 长度/密钥表 **6 种变体对失败块全部 `ret=0`**（`p60`）；并发现 **`ret==us` ≠ 解压正确**（`p68`/`p69`）。下一步只有两条：①换较新 Oodle 解码器（`ooz` 源码编译 / 官方 DLL 下载）；②装反汇编器（本机 `objdump`/`capstone` 均缺）限定范围分析 `ret=0` 判定分支 | **是（构建/下载/装工具）** |
| **F. 动态 dump（最后手段）** | 未做 | Frida/调试器挂游戏进程抓解压缓冲 | **是（需明确放行"启动游戏"）** |

**无需授权的收尾（已在本轮完成）**

5. 结论已回写 `PROBE_REPORT.md`（本文件）与 `tools\hsr_probe\README.md`；脚本 `p45`~`p69`、`lib\oodle_call.py` 已复制到 `tools\hsr_probe\lib\`（未做 git 提交，等你确认）。

---

## 11. D：中文 TextMap 定位与抽取（已完成，5/5 锚点）

### 11.1 定位过程（否定 Asb 方案）

| 步骤 | 脚本 | 结果 |
|---|---|---|
| 有界试点：按大小降序扫 38 个最大 `.block`（1.23 GB / 76.2 s） | `p56_textmap_scan.py` | `textmap`=0、`textasset`=0、`m_Script`=0；CJK 首字节占比 ≈ 随机噪声 → **Asb 里没有文本表** |
| 全库 CAB 节点目录（流式只读段头 + blocksInfo） | `p57_cab_catalog.py` | 300 文件 → 22172 段 / 27447 节点 / 30 s；`mismatchSegs=0` |
| Lua manifest 的 Md5 是否等于 `CAB-<hash>` | `p58_manifest_match.py` | 19643 条 Path / 19523 个唯一 Md5 → **命中 0**（否定捷径） |
| Lua 字节码里找 `TextmapStatic` 数据来源 | `p59_lua_textmap.py` | 只有 `CS/RPG/Client/TextmapStatic/GetText` 调用，无 `TextAsset`/`m_Script` → 文本资产不在 Lua 层 |
| 下载缓存体检（`Persistent\` 450 文件 / 12.5 GB） | `p61_text_probe.py` | **`DesignData\Windows\cn\f96da886871b002d752da7a11bf96a14.bytes`（53,981,236 B）** cjk_chars **9,349,731** |
| 该文件格式体检 | `p63_cn_format.py` | 无 ENCR/mr0k/hpatch/zstd/PK/7z/XZ/BZh 魔数；zlib/gzip/raw-deflate/lzma/bz2/LZ4（off 0/4/8/16/32 × 多输出长度）**全 FAIL** → **明文串池，不加密不二次压缩** |
| 字符串前置字节规律 | `p65_prefix_probe.py` | 采样 89236 个 CJK 起点：前 1 字节 == utf8 长度 11%、前 2 字节 == `(0x01, len)` 5% → 记录头为 `<01><len><text>`（部分仅 `<len><text>`），其余是长文本内部子串 |
| 锚点上下文 | `p66_cn_context.py` | `「Philia<unbreak>093</unbreak>.exe」被允许写入并运行`、`>>>系统运行中…`、`【载入核心变量：开拓】`、`δ-me<unbreak>13</unbreak>:\amphoreus\Irontomb.exe 运行时错误` |

### 11.2 抽取与校验

- 抽取脚本：`p64_cn_extract.py` —— 按严格字符集正则取连续串（`TEXT_CHARS` 含 ASCII/拉丁补充/CJK/全角），
  并要求每条至少含 2 个常用汉字（`[4E00-9FFF]`）、短串（<12 字符）需 ≥2 个常用汉字，以压掉"二进制偶发解码成生僻字"的噪声。
- 结果：`runs=457301  chars=14743678  elapsed=4.4s` → `lore\_probe\textmap_zh_cn.jsonl`（48,803,159 B，每行 `{"i":…,"s":"…"}`）。
- 校验脚本：`p67_anchor_verify.py` —— 读 jsonl，先去掉富文本标签 `<[^>]*>`，再数 5 个锚点：
  **`系统运行中` 2 / `运行时错误` 2 / `管理员批注` 17 / `Philia093.exe` 3 / `【载入核心变量` 2 → 5/5**
  （去标签后总字符 12,478,345）。证据：`lore\_probe\cn_textmap_hits.txt`。

### 11.3 严格映射（已破，2026-10-31 追加）

**结论：CN 文本表每条记录 = `<tag(1~3B)><varint A:u32><varint B:63bit><varint len><utf8 text>`，
其中 `B == xxh64(本地化 key 字符串) & 0x7FFF_FFFF_FFFF_FFFF`。**

> **重要修正**：`len` 是 **varint**，不是单字节。早期版本取 `data[i]` 单字节，
> 导致所有 >127 字节的长文本（大量长对白）被漏掉，覆盖率只有 71.8%。修正后 87.0%（§13.6）。

破解过程：

| 步骤 | 脚本 | 结果 |
|---|---|---|
| 按 `<len><utf8>` 锚定记录，统计相邻记录"间隙" | `p86_cn_gap.py` | 498,003 条记录；间隙 16/15/14 为主；col00=tag、col15=0x01 |
| 把前导块按 varint 拆 | `p90_cn_varint.py` | 95.6% 能精确切成两段：A、B 两个哈希 |
| 拿配置表里的明文 key 反查 | `p91_cn_hash_probe.py` | `xxh64("TalkSentenceConfig_TalkSentenceText_<id>")` 命中 **138/386**（随机基线 0/2000）→ **锁定 xxh64** |
| 全量建索引并反查 | `p92_build_textmap.py` | 配置表候选 key 命中 9,937 |
| 直接搜哈希的 varint 字节串 | `p110_option_speaker.py` | 对"缺失"的 id 直接搜哈希字节串 → **全部命中**，发现 `len` 是 varint（如 `cd 01` = 205 字节） |
| 用 varint 长度重建 | `p111_rebuild_talk.py` | 记录 472,287 条、索引 651,715 键；TalkSentence 命中 **14,055/15,991 = 87.9%** |

产出：`lore\_probe\textmap_keyed.jsonl`（`{key,text}`）、`lore\_probe\talk_textmap.jsonl`（`{id,key,text}`）。

> 说明：`A` 字段（u32）语义仍未定，但不影响 key→文本映射（`B` 已足够唯一定位）。

### 11.4 已知局限

- 尾部噪声：极少数串尾夹 1~3 个生僻字（如 `眵绦q`、`霒鑄5`），来自二进制字段被 `utf-8` 宽松解码；不影响正文检索。
- 记录识别率：498,003 条中 325,853 条的 key 块能精确切成 `tag + A + B`，其余 172,149 条因 tag 宽度/额外字段而切分失败；
  但主/副两套索引合并后仍有 494,248 个可用哈希键，覆盖接近全量。
- `textmap_zh_cn.jsonl`（p64，457,301 条）是**无 key 的串池**，仍保留；需要 key 时请用 `textmap_keyed.jsonl`。

---

## 12. E：为什么还剩 3%~17% 的块解不开

| 已排除的假设 | 实验 | 结果 |
|---|---|---|
| `us`（rawLen）算错 | `p53_seg_detail.py` 逐段核对；`p57_cab_catalog.py` 全量校验 | `Σus == Σnode.size`（seg#30 382660、seg#34 2200851）；300 文件 22172 段 `mismatchSegs=0` → **不是长度问题** |
| mr0k XOR 长度/密钥表用错 | `p60_mr0k_xorlen.py` 六种变体（`cur` 1024B / `uncapped` / `full1024` (key[i%1024] 全块) / `fulllast1024` / `seedonly` / `none`） | 成功块 `cur` 与 `none` **都能返回 `us`**；失败块（seg#30 blk#1、seg#34 blk#1/#3、seg#51 blk#0 …）**六种全 `ret=0`** |
| `mr0k` 解密结果非法 | `p49_fail_probe.py` | 失败块 `src[:8]` 都是合法 chunk 头（`8c 0c/06 00 …`），`src` 偏移 0~8 全 0，`us±1` 全 0 |

**关键发现（本轮最有价值的副产物）**：`ret == us` **只代表"解码器返回了请求长度"，不代表输出正确**。
对同一 0x07 块（`4c7c` seg#24 blk#0），mr0k 去 XOR 与不去 XOR **都返回 `ret=197309`**，但输出有 **25,290 字节（12.82%）不同**（首差 @124）；
seg#30 blk#0 差异 9.27%（首差 @113）。→ 后续所有"成功率"统计都应加内容校验（如必含 `CAB-`/`2019.4.34`）。

**本轮（2026-10-31 追加）已把 E 查到底**：

| 手段 | 脚本 | 结论 |
|---|---|---|
| 反汇编器 | `D:\MSYS2\ucrt64\bin\objdump.exe`（**本机已有**，先前"找不到"的结论作废） | 反汇编 `0x1814c47a0`（入口）、`0x1814c4f00`（内层）、`0x1814c5980`（量子头解析）→ `oodle_disasm*.txt` |
| 接出 Oodle 自己的日志 | `p73_capture_log.py` | 把 VA `0x181e693c0` 的日志函数指针临时改成 Python 回调，捕获到 `LZ corruption : DecodeOneQuantum fail!` |
| 还原 printf 变参 | `p76_printf_log.py` / `p77_printf_dump.py` | `verbosity=3` 时 Oodle 会打印 `CHUNK header …, compressor %d=%s`，变参里能拿到**压缩器名字符串** |
| 判定压缩器 | 同上 | 能解的块 = **Kraken**；解不开的 = **Leviathan**（seg#30 blk#1、seg#34 blk#1/#3）与 **Mermaid**（seg#63/#99）；seg#51 是 Kraken 但末段 `bad literals` |
| 内置 Oodle 的模块清单 | `p81_rdata_dump.py` | `.rdata` 里只有 `newlz.cpp` / `newlzhc.cpp` / `newlzf.cpp` / `lzb.cpp` / `rrlzh_lzhlw_shared.cpp`，**没有 Leviathan 的实现文件** → Unity 集成的是裁剪版 |
| rawLen 全扫 | `p75_rawlen_sweep.py` | 0x4000 步长扫到 `us`、加尾部截断 0~11、起点偏移 0~31 → 失败块**全部失败**，成功块只有 `rawLen==us` 成功 |
| verbosity 0~4 | `p75_rawlen_sweep.py` | 错误文本完全不变（除 verbosity≥3 多打诊断） |
| 11 种 XOR 变体 | `p74_xor_variants.py` | 失败块**恒失败**；成功块在"完全不去 XOR"下也成功 → **XOR 不是失败原因** |

> 结论：E 不是"我们解析错"，也不是参数/XOR 问题。失败块声明的压缩器是 **Leviathan / Mermaid**，
> 而 `UnityPlayer.dll` 内置的 Oodle 是 Unity 的裁剪版，**不含这些压缩器的解码实现**。
> 游戏目录也没有 `oo2core*.dll`（已查，只有 `UnityPlayer.dll` 一个 Oodle 来源）。
> → 想补齐只能换一个完整版 Oodle 解码器（需下载/构建，未获授权，未执行）。**它对文本侧无影响**。

---

## 13. D 下半场：剧情编排表 → 对话树（2026-10-31 新增）

### 13.1 `Persistent\DesignData\Windows` 到底是什么

用户观察到"最大的几个哈希 `.bytes` 头部能看到明文路径串"。实测普查（`p85_designtables.py`）
确认它们全是 mhy 的 **"表 + 明文串池"**，不加密、不二次压缩：

| 文件 | 大小 | 内容 |
|---|---|---|
| `98c54c70…bytes` | 128,700,379 B | **Wwise 音频表**：`BK_All_In_One`、`Ev_vo_external_story_play`、`Ev_sfx_cinematic_cutscene`、`Config`×102,439、`Prop`×164,053 |
| `f96da886…bytes`（`cn\`） | 53,981,236 B | **CN 文本表**（§11） |
| `1efaad7a…bytes` | 33,077,813 B | **配置总表**：`TalkSentenceConfig`×470、`TalkSentenceName_`×32,399、`StoryLine`×625、`NPCName`、`AvatarRankName`… |
| `8a92c4af…bytes` | 22,966,149 B | **关卡/场景表**：`HLOD`、`Collider`、`BlockHLOD`、`Chap00/02`、`Stage`、`Prop`×40,519 |
| `1714c48c…bytes` | 19,601,694 B | **角色资源表**：`Characters/CharacterPrefabs/…`×1,704、`ConfigCharacter`×43,290 |
| `4ce18f6b…bytes` | 5,267,113 B | **剧情编排表**：`Story/BattlePerformance|Discussion|Mission/…`、`TalkSentence_`×40,374、`Mission`×29,023 |
| `DesignV_a7312833…bytes` | 2,262,050 B | 索引（`<u32 off><u32 size><16B 文件名哈希>`，含 `98c54c70…`） |

推断依据（不靠猜）：`DesignV` 里 0x4C 起的 16 字节 `98 c5 4c 70 35 b1 31 b7 dc 27 c3 46 63 46 02 1d`
正好等于 128 MB 那个文件名的十六进制，说明它是"哈希文件名 → 表"的目录。

### 13.2 表内记录格式

`1efaad7a` 里能直接读出结构化记录，典型片段：

```
…NPC_DefaultStory_100002701.json
7f 8e d7 d7 2f                     ← <tag=0x7f><u24 记录ID>（连续递增）
08 2d TalkSentenceConfig_TalkSentenceText_501023532   ← <tag=0x08><len><字符串>
00 01 28 14 33 Config/Level/NPC/…/NPC_DefaultStory_100002702.json  ← <tag><varint><len><路径>
```

- `<tag><len><utf8>`：字符串（`0x08`/`0x03`/`0x04` 等，`len` 精确等于字节数）
- `<tag><varint LEB128>`：整数（如 `00 86 b8 f2 03` = 8,166,406）
- `<7f><u24>`：连续递增的记录 ID（`e7 84 3d` → `e8 84 3d` → …）
- `<06><count>`：数组（`StoryLine_Hide_Toast_SubMissionIDs` 后面跟 6 项）

### 13.3 对话树：段 → 台词序列

`4ce18f6b` 用**纯正则 + 顺序归属**即可解（`p88_story_extract.py`），不需要完全反序列化：

```python
PATH_RE = rb"(?:Story|Config|Characters)/[A-Za-z0-9_./]{3,160}?\.(?:playable|prefab|json)"
TALK_RE = rb"((?:[A-Za-z0-9]+_)?)TalkSentence_(\d+)"
```

每个 `Story/...playable` 作为段起点，其后到下一个段起点之间的 `TalkSentence_<id>` 全部归属该段（保持文件内顺序）。

实测（`p88` + `p94_merge_dialogue.py`）：

| 指标 | 数值 |
|---|---|
| 剧情段 | **29,044** |
| 含台词的段 | 16,405 |
| 台词引用 | 26,508（唯一 ID 15,991） |
| 有中文译文 | **19,022 / 26,508 = 71.8%** |
| 整段全有译文 | 10,119 段 |
| 涉及 Mission 目录 | 712 个 |

产出：`lore\_probe\story_nodes.jsonl`（段 → ID 序列）、`lore\_probe\story_dialogue.jsonl`（段 → 中文台词序列，4.7 MB）。

可读样例（原文见 `lore\_probe\story_dialogue.txt`）：

```
Story/Discussion/Mission/2021901/DS20219016401.playable
  [202196407] 你的说法不太严谨，我、银枝还有使团成员也来过工造司。
  [202196440] 呃，也许…等等，让我再考虑一下。
  [202196412] （大毫说的好像没错啊……）
  [202196416] 我和云璃分别后，还特意发消息叮嘱了公输师傅。
  …
```

### 13.4 还缺的一半：在场角色 / 说话人

- **说话人**：`4ce18f6b` 里只有个别特效段出现 `<角色>_TalkSentence_<id>` 前缀（实测仅 2 段带 `Sunday_`），
  绝大多数段是裸 `TalkSentence_<id>`；真正的说话人应来自 `1efaad7a` 的 `TalkSentenceConfig` 字段，
  但该表里只有 386 个 `TalkSentenceConfig_TalkSentenceText_<id>` 明文 key，**字段名（如 SpeakerID）暂未在明文里出现**。
- **在场角色**：`BattlePerformance` 段后面确实紧跟 `Avatar_*` / `Monster_*` 列表（可见 §13.2 样本），
  但 `Discussion` 段（占 25,741/29,044）不带角色名，需再解 `1efaad7a` 的 `Config/Level/NPC/*.json` 记录。

这两项是后续可继续推进的方向，**不影响现有"段 → 台词序列"的可用性**。

### 13.5 成品：可直接阅读的剧情分卷（2026-10-31 交付）

输出目录 **`d:\文档\Amphoreus\lore\story\`**（754 个文件 / 9.24 MB）：

| 文件 | 内容 |
|---|---|
| `index.md` | 总目录：750 卷 × 任务名 / 段数 / 台词 / 覆盖率 / 角色 |
| `mission_<ID>.md` | 每卷一份可读剧本（`### DS编号.playable` + 台词行） |
| `story_full.jsonl` | 机器可读全量：`{mission, mission_name, path, characters, lines[{id,speaker,text}]}` |
| `characters.md` | 角色标识出场统计 |
| `README.md` | 数据说明 + 已知局限（给下游写代码用） |

**任务名**：`p99_mission_names.py` 用 `MainMission_Name_<id>` 等 6 种模板反查，**593/750 卷**拿到中文任务名
（如 `2021901 → 铸剑为犁`、`1040204 → 谧林啊，寤思者缘何失语`）。

**角色**：修正了 `p88` 的一个 bug（角色正则参与了匹配却从未加入锚点集），现在每段能带 `Avatar_*/Monster_*/NPC_*`；
卷头区分"主要角色（≥2 段）"与"全部角色标识"。

**说话人**：`TalkSentenceName_<id>` 能反查到少量名字，其余为 `null`（配置表里的 SpeakerID 字段尚未定位）。

**覆盖率已到 key 格式上限**：穷举 28 种 key 模板（`p96_talk_key_templates.py`）只多补 11 个（都是说话人名），
确认 73.4% 是当前可解边界，其余 26.6% 的 key 形态未知。

---

## 附 A：可复现命令（`d:\文档\Amphoreus\tools\hsr_probe\lib`）

```powershell
python selftest_lz4.py                                  # LZ4 解码器自检
python show_nodes.py 5fd55f5e5454a91a7fd107041f537036.block   # 段/块/节点表
python context_dump.py 5fd55f5e5454a91a7fd107041f537036.block 1067125   # 锚点上下文
python header_survey.py                                  # 0x06 内层头普查（u32==us 命中率）
python oracle_probe.py                                   # 已知明文 oracle 反推
python scan_anchors.py                                   # 全库裸扫描（约 54 min，写 lore\_probe\）
python anchor_report.py                                  # 生成 lore\_probe\anchor_hits.txt
```

静态分析 + 实测解压脚本（`d:\文档\Amphoreus\tools\hsr_probe\lib\static_analysis\`，原在 `E:\HSRProbe\work\`）：

```powershell
python p30_pe_static.py     # 四模块 PE 头/导入导出/关键词串/段熵 → static_pe.txt
python p37_oodle_ctx.py     # UnityPlayer.dll 里 Oodle 串 + 96B 上下文 → oodle_ctx.txt
python p42_xref.py          # 纯 Python 扫 RIP-relative LEA，定位 Oodle 串引用点 → oodle_xref.txt
python p43_xref2.py         # 扩充版 xref（56 处命中）→ oodle_xref2.txt
python p44_dll_search.py    # 全游戏目录找 oo2core/oodle DLL → oodle_dll_search.txt
python p45_oodle_call.py    # 方案A 首测（子进程隔离 + 超时）→ oodle_call.txt
python p46_callers.py       # 扫 E8 rel32 调用点，确认 0x14c3820 只是 helper → oodle_callers.txt
python p47_oodle_real.py    # 用真入口 0x14c47a0 解单块（含 mr0k）→ oodle_real.txt
python p48_oodle_file.py <文件名...>   # 整文件逐段逐块解压 + 锚点/marker 统计 → lore\_probe\oodle_file.txt
python p49_fail_probe.py <文件名> [N]  # 诊断失败块（dump 头 + 变体）→ fail_probe.txt
python p50_header_stats.py <文件名...> # 头字段与成功/失败相关性 → header_stats.txt
python p51_param_probe.py <文件名> [N] # fuzzSafe/checkCRC/threadPhase/alloc 变体 → param_probe.txt
python p52_oodle_verbose.py <文件名> <seg#> <blk#>   # verbosity=0..3，看 Oodle 是否打印错误
python p53_seg_detail.py <文件名> <seg#>            # 单段 blocksInfo/节点表核对
python p54_chain_test.py <文件名> <seg#>             # 跨块窗口（decBufBase）假设验证
python p55_verify_lib.py                             # 改动 oodle_call.py 后的回归自检
```

D（文本表定位与抽取，2026-10-31）：

```powershell
python p56_textmap_scan.py --max-files 300 --max-bytes 1200000000 --min-size 2000000 --max-size 40000000 --order size-desc --out ..\..\..\lore\_probe\textmap_scan.txt
python p57_cab_catalog.py --min-size 1000000 --limit 300 --out ..\..\..\lore\_probe\cab_catalog_dbg.txt   # 省略 --limit 即全库（约 33 min）
python p58_manifest_match.py 300                                                  # Lua manifest Md5 vs CAB hash（0 命中）
python p59_lua_textmap.py                                                         # Lua 字节码里找 TextmapStatic 来源
python p61_text_probe.py "E:\Star Rail\Game\StarRail_Data\Persistent\DesignData\Windows\cn\f96da886871b002d752da7a11bf96a14.bytes"
python p62_anchor_in_file.py "E:\Star Rail\Game\StarRail_Data\Persistent\DesignData\Windows\cn\f96da886871b002d752da7a11bf96a14.bytes"
python p63_cn_format.py "E:\Star Rail\Game\StarRail_Data\Persistent\DesignData\Windows\cn\f96da886871b002d752da7a11bf96a14.bytes"
python p64_cn_extract.py --src "<CN .bytes 路径>" --out ..\..\..\lore\_probe\textmap_zh_cn.jsonl   # 457,301 条 / 1474 万字符
python p65_prefix_probe.py                          # "<01><len><text>" 记录头验证（内置同路径）
python p66_cn_context.py                            # 锚点上下文（内置同路径）
python p67_anchor_verify.py                         # 读 jsonl → 5/5 锚点 + 证据文件（路径均内置）
```

E（失败块归因，2026-10-31）：

```powershell
python p60_mr0k_xorlen.py 4c7c230cc476e91b383188906d154252.block 4     # mr0k XOR 长度/密钥表 6 种变体
python p68_correctness.py 4c7c230cc476e91b383188906d154252.block 24    # mr0k vs noXOR 输出差异
python p69_diff_mr0k.py 4c7c230cc476e91b383188906d154252.block 24      # 只看 0x07 块，避免 mr0k 断言
python p73_capture_log.py                                              # 接日志回调，捕获真实错误
python p74_xor_variants.py                                             # 11 种 XOR 变体 × 带日志判据
python p75_rawlen_sweep.py                                             # rawLen/尾部/起点/verbosity 全扫
python p76_printf_log.py                                               # verbosity=3 日志 + 自格式化变参
python p77_printf_dump.py                                              # 原始变参 dump（校准参数位次）
python p78_errstr_va.py                                                # 定位 Oodle 日志串 VA
python p79_log_sites.py                                                # 扫 .text 的 lea→日志串引用点
python p81_rdata_dump.py                                               # dump .rdata 里 Oodle 的模块清单
python p82_xref_msgs.py                                                # 错误串 xref
python p83_chunk_headers.py                                            # chunk 头位置统计（否定 u16@6:8 语义）
```

D 严格映射 + 对话树（2026-10-31）：

```powershell
python p84_cn_hexdump.py        # CN 表结构取样（头部/锚点上下文）→ cn_hexdump.txt
python p85_designtables.py      # 普查 DesignData 全部大 .bytes → designtables.txt
python p86_cn_gap.py            # 记录间隙统计（498,003 条）→ cn_gap.txt
python p87_story_ctx.py         # TalkSentence 上下文 → story_ctx.txt
python p88_story_extract.py     # 剧情段 + 台词 ID 序列 → story_nodes.jsonl
python p89_talkconfig.py        # TalkSentenceConfig 记录结构 → talkconfig_ctx.txt
python p90_cn_varint.py         # 前导块 varint 拆分 → cn_varint.txt
python p91_cn_hash_probe.py     # 哈希函数定位（xxh64 命中 138/386）→ cn_hash_probe.txt
python p92_build_textmap.py     # 全量索引 + 配置表 key 反查 → textmap_keyed.jsonl
python p93_talk_textmap.py      # TalkSentence ID → 中文 → talk_textmap.jsonl（73.3%）
python p94_merge_dialogue.py    # 剧情段 × 台词 → story_dialogue.jsonl
```

`lib\oodle_call.py`（可复用模块）：

```python
from oodle_call import oodle_decompress
out, ret = oodle_decompress(block_payload_after_mr0k, b.usize)   # ret==b.usize 即成功
```

限定范围反汇编（**只对命中区间，约 6KB**）：

```powershell
D:\MSYS2\ucrt64\bin\objdump.exe -d --start-address=0x1814c3740 --stop-address=0x1814c4f00 "E:\Star Rail\Game\UnityPlayer.dll"
```

## 附 B：约束遵守情况

- `E:\Star Rail\` **全程只读**（仅 `open(...,'rb')`），未修改/删除/移动任何文件；
- 未触碰 `AntiCheatExpert`、`HoYoKProtect.sys`（仅列出文件名，未读取）；未启动游戏；
- **未运行任何构建/编译命令**；无管理员权限操、无注册表写入；
- 静态分析阶段只做了**限定范围**反汇编（`UnityPlayer.dll` 的 `0x1814c3740~0x1814c4f00` 约 6KB），
  未做全量反汇编；未用调试器、未注入进程；
- **方案 A 实测阶段**：`ctypes.WinDLL` 把 `UnityPlayer.dll` **映射进 Python 进程**（只读映射，用于取函数指针），
  **未启动游戏、未注入任何游戏进程、未 hook 反作弊**；全过程无网络下载、无编译；
- 未在 C 盘产生临时文件；工具/缓存全部在 `E:\HSRProbe\`，产物全部在 `d:\文档\Amphoreus\`。
- **本轮（2026-10-31）D/E**：只跑 Python（读 `.block` 与 `Persistent\DesignData\Windows`），未下载、未编译、
  未启动游戏、未安装任何工具；`E:\Star Rail\` 仍为只读（仅 `open(...,'rb')`）；产物只写 `lore\_probe\`。
