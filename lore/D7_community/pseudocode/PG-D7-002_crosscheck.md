# PG-D7-002 crosscheck

```text
# F: crosscheck.jsonl
FUNCTION crosscheck(fragment, a_index):
    hits = a_index.search(fragment.claim_keywords)
    IF hits is EMPTY:
        RETURN {result:"unverified", action:"keep_in_community"}
    IF hits.verbatim == fragment.verbatim:
        RETURN {result:"confirmed", action:"promote_crossref"}
    IF semantic_distance(hits, fragment) < NEAR:
        RETURN {result:"supported", action:"keep_with_note"}
    RETURN {result:"unsupported", action:"demote_to_E"}

PRECONDITION : a_index 只含 S-001/S-002
POSTCONDITION: 任何 fragment 不得因 crosscheck 进入事实栏
ASSERT       : result=="confirmed" -> 仍保留 source_grade<=B
```

## 测试用例

| 输入 | 期望 |
|---|---|
| CM-003 vs S-001:425053 | confirmed |
| CM-006 vs S-001:424955 | unsupported → E |
| CM-009 无命中 | unverified |
