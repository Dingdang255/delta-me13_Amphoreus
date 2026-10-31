# PG-D5-002 rebuild_loop_log

```text
# F: rebuild_rules.json / official_anchors.jsonl
FUNCTION rebuild_loop_log(i):
    IF i IN OFFICIAL_ANCHORS:
        RETURN {loop:i, actions:OFFICIAL_ANCHORS[i], evidence:"official"}

    IF i IN VARIATION_TABLE:
        base = STANDARD_TRACK
        RETURN {loop:i, actions:base, variation:VARIATION_TABLE[i], evidence:"reconstructed"}

    # 官方没有记录的轮次：只允许产出『骨架』，且 variation 必须是 UNKNOWN
    RETURN {
        loop      : i,
        actions   : STANDARD_TRACK,          # 逐字来自官方对默认流程的复述
        variation : "UNKNOWN",
        fire      : "UNKNOWN",
        evidence  : "reconstructed"
    }

PRECONDITION : STANDARD_TRACK 的每一步都有官方 locator
POSTCONDITION: 返回值永不包含官方未给出的具体数值
ASSERT       : variation != "UNKNOWN" -> i IN VARIATION_TABLE
```

## 测试用例

| 输入 | 期望 |
|---|---|
| `i=134` | evidence=reconstructed，variation=第103次攻击 |
| `i=200` | variation=UNKNOWN，fire=UNKNOWN |
| `i=108642` | evidence=official（走 first branch） |
