# PG-D5-003 fire_ledger

```text
# F: S-001:425102（四亿枚）/ S-001:75058（数亿枚）/ S-001:218704（十二枚/轮）
FUNCTION fire_ledger(loops, official_facts):
    ledger = {total:"UNKNOWN", taken:"UNKNOWN", returned:"UNKNOWN", burden:"UNKNOWN"}

    # 每轮固定量：官方只给『十二枚火种』的仪式量
    IF official_facts.per_loop_ritual == TRUE:
        ledger.returned = 12 * loops

    # 峰值：官方给的是概数，不是精确值
    ledger.peak = "四亿枚（S-001:425102）/ 数亿枚（S-001:75058）"

    # 项目旧值 402,604,020 未在 A 级文本中出现 → 不得写入 total
    IF EXISTS(project_legacy_value) AND NOT FOUND_IN_OFFICIAL:
        ledger.conflict = "CF-001"

    ASSERT ledger.total == "UNKNOWN" OR has_official_source(ledger.total)
    ASSERT ledger.returned 未溢出（<= 12 * 33550336）
    RETURN ledger

PRECONDITION : loops >= 1
POSTCONDITION: 任何精确整数必须带 locator
ASSERT       : 输出中不出现无来源的 402604020
```

## 测试用例

| 输入 | 期望 |
|---|---|
| `loops=33550336` | returned=402,604,032（=12×33,550,336），并注明这是**推算**而非官方读数 |
| 传入项目旧值 402,604,020 | 只写入 `conflict=CF-001`，不覆盖官方 |
| 无 per_loop_ritual 证据 | returned=UNKNOWN |

> 注：12×33,550,336 = 402,604,032，与项目旧值 402,604,020 **相差 12**。这解释了旧值的来源（推算），也说明它是 reconstructed 而非 official。
