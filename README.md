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
python run.py --preset plot --live             # 演算过程中实时输出编年史
python run.py --preset plot --log               # 编年史落盘 → logs/翁法罗斯编年史_演算N.txt
python run.py --preset plot --export           # 导出 dashboard → dashboard/翁法罗斯-可视化.html
python run.py --preset plot --serve            # 起实时看板：浏览器里边演算边长，演完可回放
python run.py --help                           # 查看全部参数
```

常用开关：

| 开关 | 作用 |
|---|---|
| `--preset <名>` | 选预设：`emergent` 涌现版（默认）/ `plot` 剧情锚定版 / `plot-mech` 剧情机制版 / `nullify` 否定版 / `destruction` 毁灭版 / `tide` 淹没版 / `refuted` 证伪版 |
| `--list-presets` | 列出 `presets/` 下可用的预设（含预设目录里自带 `preset.json` 的世界） |
| `--seed <n>` | 换一个世界种子（只影响角色涌现，不改裁决结果与时刻） |
| `--frames <n>` | 只跑到第 n 帧（调试用） |
| `--live` | 实时刷屏编年史 |
| `--log [路径]` | 编年史落盘（不配 `--live` 时只落盘、不刷屏）；不给路径就写 `logs/翁法罗斯编年史_演算N.txt`（N 递增，不覆盖旧的）；落盘后会在终端提示文件路径 |
| `--export [路径]` | 导出单文件 HTML dashboard；不给路径就写 `dashboard/翁法罗斯-可视化.html` |
| `--serve [端口]` | 起只读看板服务并自动开浏览器：页面随演算实时更新，演完转为回放台（默认端口 8765，Ctrl+C 结束） |
| `--no-open` | 配 `--serve`：不自动开浏览器，自己访问打印出的地址 |
| `--serve-reload` / `--no-serve-reload` | 配 `--serve`：演算跑完后自动把页面重载成完整静态页（默认开）；关掉则改为弹提示，由你点「立即查看」再切 |
| `--verbosity <档>` | 逐类别控制编年史字数：`2,deadlock=3,emergence=0` |
| `--json` | 额外输出机器可读结果 |
| `--dump-anchors` | 导出命名标定语料 |
| `--explore [K]` | 探路档：把时间刻度按 K 压缩，跳过帧号类断言（只验机制连通） |
| `--fast [K]` | `--explore` 的旧名，等价 |

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

它只是**只读渲染层**——删掉它（或不加 `--export`），演算逐帧不变。

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

## 目录

```
run.py              入口：命令行、编年史渲染、报告、可视化导出
engine/             L0–L6：主循环 / 算子 / 状态 / 消融 / 命名 / 渲染 / 可视化 / 实时看板
config/             规则与阈值：params / loci / mapping / operators / calendar / lexicon / phonology
data/               命题（genesis）、初始变量域与阶段装配
presets/            外生绑定：种子、名字锚定、额外事件、期望时间线
tools/              自检与诊断脚本（见下）
tests/              单元测试与轨迹指纹
docs/               考据材料、术语对照表、外部变量规格
dashboard/          导出的可视化看板（`--export` 的默认去处，运行时生成）
logs/               落盘的编年史（`--log` 的默认去处，运行时生成）
pyproject.toml      元数据（依赖 / Python 版本；安装仍走 requirements.txt）
```

## 三条红线

1. **引擎零专有名词**：角色 / 泰坦 / 城邦名只能进 `presets/`、`config/lexicon.json` 与报告层。
   `python tools/grep_forbidden.py` 命中不为 0 即判失败。
2. **改轨道配置必重测**：动 `config/loci.json`、`config/params.json`、`data/genesis.json`
   会改变轨迹，必须重跑 `presets/plot/assertions.jsonl` 与 `presets/plot/timeline.json` 的全部期望。
3. **可视化层只读**：`engine/viz.py` 与 `engine/live.py` 只消费 `Trajectory` / 状态读数，
   绝不回写状态 —— 删掉它们（或不加 `--export` / `--serve`），演算逐帧不变。

## 自检与诊断

```bash
python tools/selfcheck.py                   # 一次跑完全部自检（快档，几十秒）
python tools/selfcheck.py --full            # 连四个世界的全量演算一起跑（数分钟）
python tools/selfcheck.py --list            # 只列出会跑哪些步骤

python -m unittest discover -s tests        # 单元测试
python tools/grep_forbidden.py              # 红线 1：引擎里不许有专有名词
python tools/snapshot.py                    # 轨迹指纹：改了引擎就看这里
python tools/snapshot.py --structural       # 只比【结构层】（跨平台用：跳过数值层与 digest）
python tools/snapshot.py --write            # 确认轨迹该变时，重写指纹
python tools/export.py --check-only         # 环境自检（解释器 / 依赖 / 数据）
python tools/export.py                      # 打包成可分发的 zip（含解压后自检）
```

> **指纹是分层的**（R1+R2）：**结构层**（裁决 / 结论 / 停因 / 帧号 / 换代 / 人数 / 席位 …，全整数与枚举，**逐位严格、跨平台可比**）、**数值层**（`entropy` / `noise`，走**容差** 1e-6）、**摘要层**（`digest`，量化 float32 向量的哈希，**只在同一参考环境上逐位可比**）。
> `tests/golden_fingerprints.json` 顶层的 `_reference_platform` 记着指纹是在什么环境里写的（`system` / `machine` / `python` / `numpy` 四项）；**任一项不同**，`selfcheck` 就**自动降级**为 `--structural`（只比结构层）。CI 因此在 `ubuntu-latest` 上跑。

> 下面这些已**收进 `selfcheck` 各档**，不必再手动跑一遍：
> `grep_forbidden`、`stepwise_lint` 与 `writeback_probe`（判据 6：全程零写入 `data/`）在**快档**；
> `reuse_equivalence`（判据 5：复用是否伪造世界状态）与 `checkpoint_replay`（判据 4：帧截断复现，存档点落在复用区间内）都在 **`--full`**。
> `python tools/selfcheck.py --list` 可列出当前的全部步骤。CI 跑的就是快档
> （`.github/workflows/ci.yml`）。

其余诊断脚本按用途分组：

| 脚本 | 用途 |
|---|---|
| `tools/shuffle_loci.py` | **判据 1 重标定不变性**：把席的 **id 随机置换**后重跑，可观测量必须逐项不变（证明引擎没有"认名字 / 认编号"的分支） |
| `tools/checkpoint_replay.py` | 帧截断复现：从第 k 帧续跑，是否与全程逐帧一致 |
| `tools/reuse_equivalence.py` | 参考轨道复用是否伪造了世界状态（**已进 `selfcheck --full`**） |
| `tools/naming_orthogonality.py` | 换命名器 / 音位表，轨迹是否逐帧不变 |
| `tools/seed_probe.py` | 按要素约束在种子空间里检索（`--preset plot`） |
| `tools/seat_incumbents.py` | 重新测量各席在位者的编号，用于刷新 `anchors.jsonl` |
| `tools/emergence_audit.py` | 涌现登记的审计 |
| `tools/stepwise_lint.py` | 逐帧演化链路的静态检查（**已进 `selfcheck` 快档**） |
| `tools/writeback_probe.py` | 是否有角色信息写回 `data/`（判据 6，**已进 `selfcheck` 快档**，应为无） |
| `tools/excavation.py` | **遗迹勘测**：逐席的诞生 / 消亡 / 在位帧数 / 易主次数 / 承位个体数 / 峰值承载，外加三段式考古报告（`--json` 出机器可读档案） |
| `tools/roll_call.py` | **逐火点名录**：登场与陨落总账、外生干预下的伤亡（谁被逐出 / 谁自愿让位）、承位链 |
| `tools/mech_align.py` | **机制对齐**：每个点名角色各自在哪些帧坐在哪个席 —— 用来判断桥段帧号该往哪挪 |
| `tools/mech_control.py` | **同等噪声对照**：把扰动换成同数量、同能力的无关席位，判断效果是「结构性的」还是「混沌噪声」 |
| `tools/sensitivity.py` | **参数敏感性热力图**：跨参数 × 种子出热力图 + HTML + JSON。只认运行时真会读的旋钮（`operators.STAGE_TUNABLE`），写死键当场报错 |
| `tools/parallels.py` | **平行世界对照**：五块面板（对照表 / 熵曲线 / 黑潮强度 / 遗迹分布 / 涌现时序），纯 Python 生成 SVG、零外链 |
| `tools/blacktide.py` | **黑潮爆发探测**（区域级，把帧级 `OVERFLOW` 粗判细化）。零命中时会报「最接近的一次差在哪」 |
| `tools/anomaly_check.py` | 死循环相关的诊断 |
| `tools/alt_world/run_alt.py` | 数据替换判据：换一整套世界，同一台引擎照跑 |
| `tools/lexicon_table.py` | 生成 `docs/术语对照表.md`（`--write` / `--check`） |
| `tools/actors_from_spec.py` | 由 `docs/外部变量.json` 派生预设的外部实体表 |

## 许可

[MIT](LICENSE)。

> 引擎代码（`engine/`）本身不含任何专有名词；`presets/`、`config/lexicon.json` 与 `docs/` 下的
> 考据材料含《崩坏：星穹铁道》原作的专有名词与文本，仅作同人性质的机制化演示之用。
