# PG-D7-001 grade_fragment

```text
# F: fragments.jsonl / crosscheck.jsonl
FUNCTION grade_fragment(f):
    IF f.fanwork == TRUE:                 RETURN "E"
    IF f.platform IN {"miyoushe","wikiwiki"} AND f.type=="wiki": RETURN "B"
    IF f.type IN {"datamine","screenshot","video"} AND f.raw_preserved:  RETURN "C"
    IF f.type == "post":                  RETURN "D"
    RETURN "E"

PRECONDITION : f.url 可访问且已捕获日期
POSTCONDITION: 返回值只能是 B/C/D/E（社区永不产生 A）
ASSERT       : grade != "A"
```

## 测试用例

| 输入 | 期望 |
|---|---|
| 米游社 wiki | B |
| 玩家解析帖 | D |
| 同人 | E |
