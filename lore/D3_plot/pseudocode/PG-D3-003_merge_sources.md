# PG-D3-003 merge_sources

```text
# F: S-001（文本表）/ S-002（剧情表）/ S-010（wiki）
FUNCTION merge_sources(claims):
    groups = group_by(claims, key=(version, chapter, scene))
    merged = []
    FOR g IN groups:
        A = [c for c in g if c.source_grade == "A"]
        B = [c for c in g if c.source_grade == "B"]
        D = [c for c in g if c.source_grade in {"D","E"}]

        IF A is NOT EMPTY:
            merged.append(pick_longest(A))          # A 优先，冲突进 conflicts
            IF B is NOT EMPTY AND differs(B, A):
                conflicts.append({a:A, b:B, resolution:"A 优先，B 记差异"})
        ELSE IF B is NOT EMPTY:
            merged.append(pick_longest(B))
        ELSE:
            merged.append({status:"UNKNOWN", clues:D})   # 只有二手 → 只作线索
    RETURN merged

PRECONDITION : 每条 claim 带 source_grade
POSTCONDITION: 每组合并结果只有一个主条目
ASSERT       : 不存在 D/E 条目被提升为事实
```

## 测试用例

| 输入 | 期望 |
|---|---|
| A + B 同组且一致 | 取 A |
| A + B 冲突 | 取 A，写 conflicts |
| 仅 D | status=UNKNOWN |
