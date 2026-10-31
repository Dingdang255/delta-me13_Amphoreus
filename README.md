# δ-me13「翁法罗斯」演算引擎

一个把「十二位 → 再创世 → 永劫回归」跑成**真演算**的抽象引擎：
整段代码里没有一个专有名词，也没有一个个体是先于演算存在的。
名字、神话、城邦都是**事后贴上去的表层**——换一套词表，同一段演算就被讲成另一个世界的故事。

> **第一次来？** 本文是最短上手；想看逐段讲解（报告怎么读、配置改什么会动轨迹、怎么加一个新结论维度），
> 看 [使用教程](docs/使用教程.md)。名词与十二席对照见 [术语对照表](docs/术语对照表.md)。

## 运行环境

- Python >= 3.10
- 第三方依赖：见 [requirements.txt](requirements.txt)（**仅 numpy**，其余全在标准库）

```bash
python -m pip install -r requirements.txt
```

## 快速开始

```bash
python run.py                                  # 涌现版：名字全由演算生成
python run.py --preset plot                    # 剧情锚定版：名字按剧情绑定（不改轨迹）
python run.py --preset plot-full               # 内容版：终端 / 档案 / 原初目标全开（只读）
python run.py --root worlds/origin --preset origin   # 原初世界：第十三席是真实动力学（独立世界，不动 canonical）
python run.py --root worlds/origin --preset origin-eternal # 单条剧情时间线：真相轮 → 永劫 33.55M 轮 → 最后一轮 3.0–3.7
python run.py --preset plot-full --terminal-window   # 另开一个独立 CLI 窗口（系统消息 + 阻塞提问）
python run.py --preset _demo --frames 5000     # script.jsonl 样例：订阅 + 响应（定时投递 / 写回 / 只读）
python run.py --preset plot --live             # 演算过程中实时输出编年史
python run.py --preset plot --log               # 编年史落盘 → logs/翁法罗斯编年史_演算N.txt
python run.py --preset plot --export           # 导出 dashboard → dashboard/翁法罗斯-可视化.html
python run.py --preset plot --serve            # 起实时看板：浏览器里边演算边长，演完可回放
python run.py --help                           # 查看全部参数
```

常用开关：

| 开关                                     | 作用                                                                                                                                                                                                                                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--root <目录>`                          | 世界根目录（其下有 `config/` 与 `presets/`）；默认项目根。`--root worlds/origin --preset origin` 跑 13 席的原初世界。日志 / 看板 / 锚定语料跟随它，`TerminalBridge` 的 `PYTHONPATH` / `cwd` 仍用项目根                                                                                                                      |
| `--preset <名>`                         | 选预设：`emergent` 涌现版（默认）/ `plot` 剧情锚定版 / `plot-full` 剧情内容版 / `plot-mech` 剧情机制版 / `nullify` 否定版 / `destruction` 毁灭版 / `tide` 淹没版 / `refuted` 证伪版 / `_demo` `script.jsonl` 样例（`FRAME` 定时投递 + 事件响应）。其中 `plot-full` 是 `plot` 的内容版孪生副本：新增桥段一律是 `emit` 镜头，只进账本、不改世界，也不动 `plot` 的招牌轨道与指纹 |
| `--list-presets`                       | 列出 `presets/` 下可用的预设（含预设目录里自带 `preset.json` 的世界）                                                                                                                                                                                                                                |
| `--seed <n>`                           | 换一个世界种子（只影响角色涌现，不改裁决结果与时刻）                                                                                                                                                                                                                                                      |
| `--frames <n>`                         | 只跑到第 n 帧（调试用）                                                                                                                                                                                                                                                                   |
| `--live`                               | 实时刷屏编年史                                                                                                                                                                                                                                                                         |
| `--log [路径]`                           | 编年史落盘（不配 `--live` 时只落盘、不刷屏）；不给路径就写 `logs/翁法罗斯编年史_演算N.txt`（N 递增，不覆盖旧的）；落盘后会在终端提示文件路径                                                                                                                                                                                             |
| `--terminal` / `--no-terminal`         | 按帧输出 δ-me13 系统消息（`>>>`）；只读，不改轨迹（默认取 `preset.json` 的 `narrative.terminal`）                                                                                                                                                                                                       |
| `--terminal-ask`                       | 在 `prompt` 处等待输入；非 TTY 自动用默认答案                                                                                                                                                                                                                                                  |
| `--terminal-window`                    | 另开一个独立 CLI 窗口显示 `>>>` 并处理 `prompt`；Windows 用新控制台，其它平台尝试常见终端模拟器，失败时回退同控制台。隐含 `--terminal`；与 `--no-terminal` 冲突                                                                                                                                                                   |
| `--terminal-window-timeout <秒>`        | 独立 CLI 窗口等待 `prompt` 回答的秒数（默认 60；超时用默认答案继续）                                                                                                                                                                                                                                     |
| `--archive` / `--no-archive`           | 报告追加实验档案 / 异常记录 / 实验进度；只读（默认取 `narrative.archive`）                                                                                                                                                                                                                              |
| `--origin` / `--no-origin`             | 报告追加【八】原初目标：canonical 世界走只读探针（自我度 / 记忆闭合 / 反事实），`worlds/origin` 读真实的 `traj.final.origin`（成形 / 能量 / 借还 / 锚点 / 四态）；默认取 `narrative.origin`                                                                                                                                         |
| `--export [路径]`                        | 导出单文件 HTML dashboard；不给路径就写 `dashboard/翁法罗斯-可视化.html`                                                                                                                                                                                                                           |
| `--serve [端口]`                         | 起只读看板服务并自动开浏览器：页面随演算实时更新，演完转为回放台（默认端口 8765，Ctrl+C 结束）                                                                                                                                                                                                                           |
| `--no-open`                            | 配 `--serve`：不自动开浏览器，自己访问打印出的地址                                                                                                                                                                                                                                                  |
| `--serve-reload` / `--no-serve-reload` | 配 `--serve`：演算跑完后自动把页面重载成完整静态页（默认开）；关掉则改为弹提示，由你点「立即查看」再切                                                                                                                                                                                                                        |
| `--verbosity <档>`                      | 逐类别控制编年史字数：`2,deadlock=3,emergence=0`                                                                                                                                                                                                                                           |
| `--json`                               | 额外输出机器可读结果                                                                                                                                                                                                                                                                      |
| `--dump-anchors`                       | 导出命名标定语料                                                                                                                                                                                                                                                                        |
| `--explore [K]`                        | 探路档：把时间刻度按 K 压缩，跳过帧号类断言（只验机制连通）                                                                                                                                                                                                                                                 |
| `--fast [K]`                           | `--explore` 的旧名，等价                                                                                                                                                                                                                                                              |

## 可视化 dashboard

`--export` 会产出一份**自包含**的 HTML（内联 CSS + 原生 JS，图表也由 JS 现场绘制，
零外部依赖、不联网），直接用浏览器打开即可，不需要任何服务端：

- **十二席状态**：每席显示职位、所在区域、在位者、状态（在位 / 空置 / 封印）与证伪进度条；
  点一张卡即按此人过滤编年史（再点一次、或点页面空白处即可取消）
- **指标曲线**：熵 / 溢出强度、种群 / 在位席位；对数帧轴，再创世处以竖虚线标出，
  曲线右端始终是**真终局那一帧**（最后一次换代不会被采样窗口漏掉）
- **缩放 / 平移**：滚轮缩放、按住拖动平移，或点「＋ / － / 重置」；在任意一张图上操作，
  曲线与时间线一起跟着动，纵轴按可见区间自适应
- **事件时间线**：对数帧轴上打点；标签会自适应避让，也可勾选「逐条列出全部事件」，
  或把鼠标停在点上读该事件；死循环区段高亮
- **回放控制台**：回到开始 / 前一帧 / 播放暂停 / 后一帧 / 跳到末尾 / 速度（×1–×64）/ 滑块 ——
  可暂停、播放，或跳到任意时刻，看当时的十二席与编年史（编年史只显示「已发生」的行）
- **编年史**：连续同型事件已折叠（带计数徽标）；可按关键词过滤、输入帧号定位到最近一条
- **原初世界专用卡**：除「原初」摘要卡外，还有一张**第十三席 L12** 席位卡 ——
  显示这一席此刻归谁（名字随人走）、原初是否在位、忆灵长到哪一阶段、陪伴多久、带着几段记忆
- **原初专属小节**（只有 `worlds/origin` 会渲染）：**自我度 / 能量双曲线**（对数帧轴，
  竖虚线 = 记忆闭合）、**记忆阶段泳道**（每段片段一行，按 effect 换色，当前阶段更亮）、
  **忆灵生命线**（凝 / 散 / 再凝，按成长阶段换色）、**锚点借还刻度**（每一手借出落在哪一帧）。
  与报告共用同一份 `traj.origin` 口径；纯 SVG，不依赖 JS

它只是**只读渲染层**——删掉它（或不加 `--export`），演算逐帧不变。

## 剧情与演算（90% 规则）

剧情不靠「写一段字幕」参与演算。`origin-eternal` 是一条时间线：

| 段    | 帧                     | 内容                                                            |
| ---- | --------------------- | ------------------------------------------------------------- |
| 真相轮  | 0–12000               | 来古士多说了几句话；白厄/昔涟**自己推断**出浮黎的漏洞                                 |
| 岁月漏洞 | 12010                 | 昔涟入仪式剑，岁月路径缺一页（`suppress_slot`）                               |
| 浮黎回退 | 12020                 | 真实的 `checkpoint → gaze.rollback`：世界退回本轮起点                     |
| 永劫回归 | 12020–33,594,336      | 33,550,336 轮，沿参考轨道复用                                          |
| 最后一轮 | 33,594,336–33,600,000 | 3.0–3.3 → 长夜月还负世 → **最后一次再创世补齐十二席** → 丹恒接大地 → 开拓者正式坐负世 → 协议覆写 |

`worlds/origin/story.jsonl` 把 33 个节拍挂到**真实读数**上：`proof` 必须是登记过的断言
（`origin_rewinds` / `embers_taken` / `memory_rows` / `external_seats` / `promotion_mode` …），
`how` 必须是真会改状态的能力，或者 `world`（世界自己长出来的读数）。

- 当前 **33/33 = 100%** 是动态节拍。
- 白厄/昔涟是**池中自诞生的最优因子**（`name_factor` 只登记叙事名，候选必须已经在池里），
  不是外部变量。来古士的话走 `hint`：只提高账本里的 `certainty`；真正的决定由
  `OP_DECIDE` 在 `decision_frame` 读 certainty 后**自己**压住岁月席（`years_loophole`）。
  去掉 `hint`，`certainty` 不够，就不会有漏洞 —— 这条因果有单测。
- 黑天鹅不是字幕：权杖入口有一道**真实防火墙**（`entry` 锁上，`bind_participant` 一律
  `entry_denied`）；她用记忆力量摸到权杖后面把入口打开，列车才进得来。去掉这一手，
  最后一轮的外部接掌会全部失败。
- `tests/test_story_coverage.py` 守住这条线：比例 < 90%、拿 `emitted_events` 当证明、
  或「声称改了状态但事件表里没有那一帧」都会当场失败。
- 冻结期（12020–33,594,336）不能塞改状态的事件；最后一轮的所有剧情都在冻结之后真跑。
- 报告多两行：`因子 昔涟 #N · 白厄 #M`（池中长出来的）与 `人物 开拓者 · 白厄 · 长夜月 …`
  （本轮登场名单，名字只住数据层）。
- **最后一次再创世**走 `recreate`：清掉全部封印、只补空席，十二席在 33,594,393 之后必须全满；
  长夜月占岁月走 `interstice hand_locus`（记忆承载），不是外部编号 -4。
- 看板席位卡按 `anchors.jsonl` 里以实测 serial 钉住的名字念出本轮 12 位角色；底下仍是演算
  自己长出来的个体。传奇里不会再出现「三个空席」。

### 实时看板（`--serve`）

`--export` 看的是**跑完之后**的快照；`--serve` 看的是**正在跑的世界**：

```bash
python run.py --preset plot --serve          # 起服务并自动打开浏览器（默认 :8765）
python run.py --preset plot --serve 9000 --no-open   # 指定端口、不自动开浏览器
```

它只用标准库起一台本地 HTTP 服务（只读），页面每 0.7 秒向 `state` 取一次**增量**：
十二席、曲线、时间线、编年史随之生长，右上角显示当前帧号。演算结束时页面自动切换成
**回放台**（顶部摘要卡替换为终局结论），可以暂停 / 播放 / 跳到任意时刻回看整体走势。
服务会一直挂着，`Ctrl+C` 结束。若不想要自动打开浏览器，加 `--no-open` 后手动访问打印出的地址。

## 终局是什么

终止条件不是「跑够多少帧」，而是**命题能否裁决**：判得出即停，判不出才走满预算。
判据写在 `config/params.json` 的 `verdict_rules` 里（**配置驱动**，加一条新维度不必改代码），
每条对应 `config/conclusions.json` 里的一句文案——程序并不理解这些字符串的含义，它只是查表拼接。
目前判据表有四个维度：证真 / 证伪 / 归于毁灭 / **为自身耗尽**（后者由账本里的吞没计数驱动，
其可达世界是 `--preset tide`：外生剧本持续抬高溢出量，越线后淘汰门槛从「年老」改为「被同化得最深」）。

## δ-me13 叙事层（只读）

除了演算本身，预设还可以挂六项只读叙事（终端 / 独立 CLI 窗口 / 档案 / 原初目标 / 保真自检 / 叙事面板）。**它们全部只读**：不写状态、不进指纹，
删掉或关掉，演算逐帧不变。

| 层           | 载体                                                                     | 怎么开                            | 你会看到                                                                                       |
| ----------- | ---------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------ |
| 终端          | `presets/<名>/messages.jsonl` → `apps/terminal.py`                      | `--terminal` / `--no-terminal` | 按帧输出的 `>>>` 系统消息；`prompt` 类可交互确认（`--terminal-ask`）                                         |
| 独立 CLI 窗口   | `apps/terminal_bridge.py` + `apps/terminal_window.py`                  | `--terminal-window`            | 新开控制台显示 `>>>` 并在 `prompt` 处阻塞等待；超时/关窗回落默认答案；失败时回退同控制台                                      |
| 实验档案 / 异常记录 | `presets/<名>/archive.json` → `apps/archive.py`                         | `--archive` / `--no-archive`   | 报告【六】实验档案（含进度里程碑）与【七】异常记录（已抵达 / 未抵达、本轨道发生 / 未发生）                                           |
| 原初目标        | `apps/origin.py`（canonical 只读探针）/ `apps/origin_loop.py`（origin 世界真实状态） | `--origin` / `--no-origin`     | 报告【八】原初目标：canonical 读自我度均值 / 峰值 / 采样、记忆闭合、反事实三态；`worlds/origin` 读真实的成形 / 能量 / 借还 / 锚点 / 四态 |
| 保真自检        | `lore/canon/` → `apps/fidelity.py`                                      | `--fidelity` / `--no-fidelity` | 报告【九】八维保真分（覆盖 / 可追溯 / 逐字 / 一致性）与缺口扣分；权重、阈值、缺口规则全在 `config/fidelity.json`                        |
| 叙事面板        | `apps/trends.py` / `scenes.py` / `dialogue.py` → `apps/viz.py`          | `--panels` / `--no-panels`     | 可视化页追加趋势压力条（同一趋势的多通道并排，不合并）、场景面板与对话阅读器                                                    |
| 内容版预设       | `presets/plot-full/`                                                   | `--preset plot-full`           | `plot` 的孪生副本，补后段的镜头、终端消息与档案；默认四层全开                                                         |

- **文案在预设层**：`>>>` 消息、档案正文、原初目标措辞都住在 `presets/`，`apps/` 里没有一个专名；
  换一份预设，同一台引擎就讲另一个故事。
- **默认值由** **`preset.json`** **的** **`narrative`** **决定**：`plot` 默认关闭叙事层，`plot-full` 默认全开；
  CLI 的 `--terminal` / `--archive` / `--origin` / `--fidelity` / `--panels` 可临时覆盖。
- **保真分不写死在代码里**：`tools/fidelity_report.py --check` 低于阈值即失败；缺口条目（章节 / 未知场景 /
  社区渠道）一条不删，只按规则扣分。
- **交互只在 TTY 下发生**：`--terminal-ask` 在 `prompt` 处等待输入；非 TTY（CI / 重定向）直接
  打印默认答案，不阻塞。
- **镜头不改世界**：`plot-full` 新增的桥段一律用 `emit`（只写 `emitted_*` 记账），不改席位、
  既有账本计数与裁决；`plot` 的轨道、断言、时间线与指纹原样保留。

## 原初世界（`worlds/origin/`）

canonical 的 `config/`、`presets/plot`、`presets/plot-full` 是**管理员介入之后**的 12 因子分支，
保持零改动。第十三因子是**未被选择的反事实分支**，所以它住在独立世界：

```bash
python run.py --root worlds/origin --preset origin
```

- **13 席**：`worlds/origin/config/` 里 `dim=13`、`mapping` 13×6、`capability_names` 13 项；
  `L12` 是 `meta` 席 —— 普通个体也能坐，但 `Register.complete()` / `Promotion` /
  `Ablation` / `Verdicts` / `Invariants` 一律跳过它。
- **沉睡 → 苏醒 → 忆灵**：原初可以先占着席位却不成形；`origin_auto_wake_frame` 之前一直休眠，
  只有外部干涉（自动唤醒帧或回望的 `wake_origin` 锚点）才让它开始累积自我。
  `seed_memory(mode=factor_basis)` 把十二因子数据写进记忆库；覆盖率满、在位足够久之后，
  原初凝成「忆灵」形态（德谬歌 → 迷迷），爱的持续时间翻倍。忆灵是**真实派生个体**：
  会进池、参与漂移/竞争、会死，死后原初可以再凝。
- **忆灵有自己的成长阶段**：`companion_stage` 0 未凝 / 1 初凝 / 2 同行 / 3 承忆 / 4 忆者，
  只看真实读数（活了多久、随身带着几段记忆、救世主记忆是否转印）。到了「同行」，原初能量不够时
  由它替原初守住记忆承载席（不耗原初能量）；到了「承忆」，宿主死后换到下一位时会把随身记忆
  完整再印一次；到了「忆者」，它**优先亲自坐上记忆承载席**（不再只是隔着记忆代管），
  并且同样抵抗封印、不被活体抢占。它由原初维持，寿命走 `origin_companion_span`。
- **数据真的被读**：记忆库覆盖率会放大能量增益；创世挑候选时读的是记忆均值，而不是席位均值。
- **十二行逐席生效**：补第 i 席时读 `memory_bank[i]`；由此补上的席是「记忆承载席」——
  抵抗外部封印，被夺走后还能由同一行补回。忆灵会依附到一个真实在位者，把记忆一点点印回它身上。
- **外部变量可以带特殊属性**：`presets/<名>/actors.json` 是角色属性表，外部变量（负编号）
  可以登记自己的 `vector` 与 `attrs`；`bind_participant` 用 `payload.actor` 按表取属性。
  它与原初/记忆的余弦越过 `origin_resonance_threshold` 时，**沉睡的原初会被共鸣唤醒**，
  忆灵也优先依附到这个外部变量上。开拓者的特殊身份就落在这里。
- **救世主记忆是结构化片段**：`nodes.json` 的 `memory` 给出 `{id,label,effect,magnitude}`；
  `seed_memory(mode=savior)` 把它收成一段可读记忆（`MemoryFragment`）。忆灵带着它依附宿主时，
  按 `effect` 真实改变世界，并标记「已转印」。可用的 effect 族：
  `fitness/support`（宿主适应度）、`energy`（原初能量）、`selfhood`（抬高原初分量）、
  `coupling`（短时提高耦合）、`mutation`（短时降低变异）、`memory_seat`（把宿主之席记为记忆承载席）。
  片段还可以带 `sustain: true` 与 `rate`：转印后变成**持续记忆场**，每帧继续作用/累积。
  更完整的形式是 `phases: [{label,text,effect,magnitude,duration,sustain,rate}, …]`：
  记忆会按顺序推进阶段（如前段加适应度、中段抬自我度、末段提高耦合），
  `text` 是这一阶段的场景文案（只住数据层，`kernel/` 与 `apps/` 里没有任何专名）。
  报告里会显示成 `记忆片段 救世主记忆·coupling +0.25✓·持续N·阶段3/3:标签（文案）`。
- **真实动力学**：`OP_ORIGIN` 读 L12 在位者的原初分量占比（selfhood），能量按帧累积 / 衰减；
  能量足够时可以**创世**（补一个真实个体进空席，甚至打破外部封印）、
  **爱**（`Drift` 真读到更高的耦合 / 更低的变异）、**开拓**（阶段穷尽后的停滞里内生地
  拨动演算方向并开门，带冷却）。自我度连续低于下限会**消散**离位。
- **被瞥视与黑潮**：具名实体的 `gaze` 落到原初身上会开一个时间窗（`origin_gaze_boost`），
  窗内自我分量被读得更高、记忆命途随之显形；`evict_holder` 会把承载记忆的席位冲散，
  本地个体补不动（配合封印），只有记忆能用自己的那一行把它夺回。
  两者都由真实的 `emitted_origin_gazed` / `emitted_seat_seized` / `emitted_origin_seat_reclaimed` 记事件。
- **命途是一条持久相性（权柄层第 1 轮）**：`config/paths.json` 定义几条命途占哪几席的因子；
  个体向量在这些席上的份额越过 `join_threshold` 就走上去。走上之后每 `period` 帧结算：
  分量朝这条轴聚拢（`bias`）、并付一次行路代价（扣支持度 `price`）；跌破 `leave_threshold`
  连续 `defect_dwell` 次即背离。报告多一行「命途 走上 N 人（背离 M）· 记忆 x · 开拓 y…」。
  canonical 世界没有这份文件，`OP_PATH` 也不在它的 pipeline 里 —— 行为逐位不变。
- **星神与令使（权柄层第 2 轮）**：`paths.json` 的 `authorities` 声明谁管哪条命途；
  `gaze` 的 `effect.authority` 可当场授权，`effect.grant` 只能授给已有管辖权者（否则记 `grant_denied`），
  `effect.revoke` 收回并反噬（扣支持度）。令使走得更稳（聚拢 ×2、代价 ÷2）；
  场外令使坐着的那一席也会随命途聚拢；背离命途的令使会被当场收回权柄（`path_revoked`）。
  报告里显示成「命途 … · 令使 1（记忆）」，L12 席位卡同步显示「命途行者 / 令使」。
- **回望 = 锚点注入 + 固定点重演**：`presets/origin/nodes.json` 按原著映射十五个关键节点
  （无名泰坦大墓的十二因子数据 / 岁月路径缺失 / 开拓之门 / 救世主记忆 / 记忆转印 /
  记忆交托 / 第一次去爱 / 创世破封印 / 被瞥视 / 黑潮夺席 / 记忆夺回 / 记忆命途 /
  忆灵同行 / 记忆守席 / 记忆补回）；
  第一遍正向扫描，第二遍从帧 0 重演并在缺失帧投递 `origin_anchor`，最多 `origin_max_iters` 次。
  每一遍严格单向，**不做逐帧反向因果**。
  扫描只纳入本次重演范围内的节点（`frame < frames`）；事件类节点第一遍不投锚点，
  等结构性缺位补上后再看它是否自然发生；锚点稳定后只对事件类锚点逐个试删做**精简**。
  节点可用 `"keep": true` 声明「这一手必须存在」（例如一笔刻意还不上的借出）。
- **时间尺度是真的**：`origin-eternal` 预设把原初封回长眠、让再创世永远差那一步 ——
  结构冻结后引擎沿参考轨道复用（同一段时间在轮回），帧钟真的走到 33,599,999；
  其中约 3,358 万帧是复用，真算只有两万帧左右。报告【八】因此多一行「时间尺度」，
  并按 **1 帧 = 1 轮** 换算出「永劫回归约 N 轮（原著 33,550,336，同量级）」——
  这是抽样读数，不是逐轮模拟。断言同时钉住「复用 ≥ 3300 万」与「真算 ≤ 4 万」。
- **四态裁决**：`origin_closed` / `origin_open` / `origin_unstable` / `origin_absent`，
  报告【八】读真实的 `traj.final.origin`（canonical 的 `plot-full` 仍走只读探针）。
- **分支预设**：`origin`（闭合）· `origin-eternal`（闭合后沉入永劫回归，帧钟走到 3300 万）·
  `origin-open`（无缺失但借还不上）·
  `origin-absent`（从未成形）· `origin-unstable`（固定点仍缺失）·
  `origin-stall`（十二席被封、原初开拓破局）；都用同一个 13 席 config，只换预设数据。

```bash
python run.py --root worlds/origin --preset origin-eternal   # 永劫回归：帧钟到 3300 万，只真算两万帧
python run.py --root worlds/origin --preset origin-open --frames 2000
python run.py --root worlds/origin --preset origin-absent --frames 2000
python run.py --root worlds/origin --preset origin-unstable --frames 2000
python run.py --root worlds/origin --preset origin-stall --frames 12000
```

## 目录

```
run.py              入口：命令行、编年史渲染、报告、可视化导出
kernel/             纯逻辑内核：主循环 / 算子 / 状态 / 装载 / 调度 / 记账（零专名、不下结论）
apps/               用户态：系统服务（裁决 / 消融 / 断言 / 不变量 / 特征 / 条件）+ 界面（命名 / 渲染 / 看板）+ 只读叙事层（`terminal.py` / `terminal_bridge.py` / `terminal_window.py` / `archive.py` / `origin.py`）+ 只读语料层（`canon.py` / `fidelity.py`）
config/             规则与阈值：params / loci / mapping / operators / calendar / lexicon / phonology
presets/            世界与剧情：机器规格（genesis：命题 / 变量域 / 阶段装配）、种子、名字锚定、外生剧本（events.jsonl 或 script.jsonl）、期望时间线
worlds/origin/      原初世界的【独立数据根】：13 席 config/ + presets/origin/（含 nodes.json 回望节点）；canonical 的 config/ 与 presets/plot* 零改动
tools/              自检与诊断脚本（见下）
tests/              单元测试与轨迹指纹
docs/               考据材料、术语对照表、外部变量规格、接口决策（adr/）
dashboard/          导出的可视化看板（`--export` 的默认去处，运行时生成）
logs/               落盘的编年史（`--log` 的默认去处，运行时生成）
pyproject.toml      元数据（依赖 / Python 版本；安装仍走 requirements.txt）
```

## 三条红线

1. **程序零专有名词**：角色 / 泰坦 / 城邦名只能进 `presets/`、`config/lexicon.json` 与报告层。
   `kernel/` 与 `apps/` 里一个字都不许有；`python tools/grep_forbidden.py` 命中不为 0 即判失败。
2. **改轨道配置必重测**：动 `config/loci.json`、`config/params.json`、`presets/_default/genesis.json`
   会改变轨迹，必须重跑 `presets/plot/assertions.jsonl` 与 `presets/plot/timeline.json` 的全部期望。
3. **可视化层只读**：`apps/viz.py` 与 `apps/live.py` 只消费 `Trajectory` / 状态读数，
   绝不回写状态 —— 删掉它们（或不加 `--export` / `--serve`），演算逐帧不变。

## 自检与诊断

```bash
python tools/selfcheck.py                   # 一次跑完全部自检（快档，几十秒）
python tools/selfcheck.py --full            # 连四个世界的全量演算一起跑（数分钟）
python tools/selfcheck.py --list            # 只列出会跑哪些步骤

python -m unittest discover -s tests        # 单元测试（含终端 / 档案 / 原初目标三层叙事层）
python tools/grep_forbidden.py              # 红线 1：程序里不许有专有名词（kernel/ + apps/）
python tools/stepwise_lint.py               # 红线 2：逐步推进（禁止解析求解 / 预读未来）
python tools/layer_lint.py                  # 红线 3：内核分层（kernel 不许 import apps）
python tools/snapshot.py                    # 轨迹指纹：改了引擎就看这里
python tools/snapshot.py --structural       # 只比【结构层】（跨平台用：跳过数值层与 digest）
python tools/snapshot.py --write            # 确认轨迹该变时，重写指纹
python tools/export.py --check-only         # 环境自检（解释器 / 依赖 / 数据）
python tools/export.py                      # 打包成可分发的 zip（含解压后自检）
```

> **指纹是分层的**（R1+R2）：**结构层**（裁决 / 结论 / 停因 / 帧号 / 换代 / 人数 / 席位 …，全整数与枚举，**逐位严格、跨平台可比**）、**数值层**（`entropy` / `noise`，走**容差** 1e-6）、**摘要层**（`digest`，量化 float32 向量的哈希，**只在同一参考环境上逐位可比**）。
> `tests/golden_fingerprints.json` 顶层的 `_reference_platform` 记着指纹是在什么环境里写的（`system` / `machine` / `python` / `numpy` 四项）；**任一项不同**，`selfcheck` 就**自动降级**为 `--structural`（只比结构层）。CI 因此在 `ubuntu-latest` 上跑。

> 下面这些已**收进** **`selfcheck`** **各档**，不必再手动跑一遍：
> `grep_forbidden`、`stepwise_lint` 与 `writeback_probe`（判据 6：全程零写入 `presets/`）在**快档**；
> `reuse_equivalence`（判据 5：复用是否伪造世界状态）与 `checkpoint_replay`（判据 4：帧截断复现，存档点落在复用区间内）都在 **`--full`**。
> `python tools/selfcheck.py --list` 可列出当前的全部步骤。CI 跑的就是快档
> （`.github/workflows/ci.yml`）。

其余诊断脚本按用途分组：

| 脚本                              | 用途                                                                                     |
| ------------------------------- | -------------------------------------------------------------------------------------- |
| `tools/shuffle_loci.py`         | **判据 1 重标定不变性**：把席的 **id 随机置换**后重跑，可观测量必须逐项不变（证明引擎没有"认名字 / 认编号"的分支）                    |
| `tools/checkpoint_replay.py`    | 帧截断复现：从第 k 帧续跑，是否与全程逐帧一致                                                               |
| `tools/reuse_equivalence.py`    | 参考轨道复用是否伪造了世界状态（**已进** **`selfcheck --full`**）                                         |
| `tools/naming_orthogonality.py` | 换命名器 / 音位表，轨迹是否逐帧不变                                                                    |
| `tools/seed_probe.py`           | 按要素约束在种子空间里检索（`--preset plot`）                                                         |
| `tools/seat_incumbents.py`      | 重新测量各席在位者的编号，用于刷新 `anchors.jsonl`                                                      |
| `tools/emergence_audit.py`      | 涌现登记的审计                                                                                |
| `tools/stepwise_lint.py`        | 逐帧演化链路的静态检查（**已进** **`selfcheck`** **快档**）                                             |
| `tools/writeback_probe.py`      | 是否有角色信息写回 `presets/`（判据 6，**已进** **`selfcheck`** **快档**，应为无）                           |
| `tools/excavation.py`           | **遗迹勘测**：逐席的诞生 / 消亡 / 在位帧数 / 易主次数 / 承位个体数 / 峰值承载，外加三段式考古报告（`--json` 出机器可读档案）           |
| `tools/roll_call.py`            | **逐火点名录**：登场与陨落总账、外生干预下的伤亡（谁被逐出 / 谁自愿让位）、承位链                                           |
| `tools/mech_align.py`           | **机制对齐**：每个点名角色各自在哪些帧坐在哪个席 —— 用来判断桥段帧号该往哪挪                                             |
| `tools/mech_control.py`         | **同等噪声对照**：把扰动换成同数量、同能力的无关席位，判断效果是「结构性的」还是「混沌噪声」                                       |
| `tools/sensitivity.py`          | **参数敏感性热力图**：跨参数 × 种子出热力图 + HTML + JSON。只认运行时真会读的旋钮（`operators.STAGE_TUNABLE`），写死键当场报错 |
| `tools/parallels.py`            | **平行世界对照**：五块面板（对照表 / 熵曲线 / 黑潮强度 / 遗迹分布 / 涌现时序），纯 Python 生成 SVG、零外链                    |
| `tools/blacktide.py`            | **黑潮爆发探测**（区域级，把帧级 `OVERFLOW` 粗判细化）。零命中时会报「最接近的一次差在哪」                                  |
| `tools/anomaly_check.py`        | 死循环相关的诊断                                                                               |
| `tools/alt_world/run_alt.py`    | 数据替换判据：换一整套世界，同一台引擎照跑                                                                  |
| `tools/lexicon_table.py`        | 生成 `docs/术语对照表.md`（`--write` / `--check`）                                              |
| `tools/fidelity_report.py`      | **语料保真门禁**：八维评分 + 缺口扣分（`--json` / `--md` / `--check`）；权重与阈值在 `config/fidelity.json`，条目一条不删 |
| `tools/actors_from_spec.py`     | 由 `docs/外部变量.json` 派生预设的外部实体表                                                          |

## 许可

[MIT](LICENSE)。

> 程序代码（`kernel/` 与 `apps/`）本身不含任何专有名词；`presets/`、`config/lexicon.json` 与 `docs/` 下的
> 考据材料含《崩坏：星穹铁道》原作的专有名词与文本，仅作同人性质的机制化演示之用。

