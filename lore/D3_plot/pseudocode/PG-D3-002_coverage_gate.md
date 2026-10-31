# PG-D3-002 coverage_gate

```text
# F: coverage_matrix.md
FUNCTION coverage_gate(row):
    # 『已补全』必须同时满足：有逐字、有过程、有后续
    has_verbatim = row.verbatim IN {"A","B","C"}
    has_process  = row.expansion.during.length >= 2
    has_after    = row.expansion.after != NULL

    IF has_verbatim AND has_process AND has_after:
        RETURN "已补全"
    IF has_verbatim AND (has_process OR has_after):
        RETURN "部分"
    RETURN "UNKNOWN"

FUNCTION assert_no_fake_completion(matrix):
    FOR row IN matrix:
        IF row.status == "已补全" AND row.verbatim == "无":
            RAISE FakeCompletion(row.version, row.chapter)
    RETURN PASS

PRECONDITION : 每行至少有一个 source
POSTCONDITION: 不允许出现『已补全 + 无逐字』
ASSERT       : 3.0–3.7 每版本至少 1 行
```

## 测试用例

| 输入 | 期望 |
|---|---|
| 3.7 主线（有概述+结局） | 部分 |
| 3.4（无过程） | UNKNOWN |
| 声称已补全但 verbatim=无 | 抛 FakeCompletion |
