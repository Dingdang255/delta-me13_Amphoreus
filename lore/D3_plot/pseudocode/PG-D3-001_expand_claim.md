# PG-D3-001 expand_claim

```text
# F: wiki_claims.jsonl / plot_expansion.jsonl
FUNCTION expand_claim(claim):
    IF claim.source_grade NOT IN {"A","B"}:
        RETURN {status:"UNKNOWN", reason:"only secondary source"}   # §5.1

    exp = {before:NULL, during:[], after:NULL}
    exp.before = lookup_summary(claim.id, "before")     # 官方概述
    exp.during = lookup_summary(claim.id, "during")
    exp.after  = lookup_summary(claim.id, "after")
    exp.dialogue_refs = find_dialogue(claim.scene)      # D4
    exp.mechanism_refs = map_to_mechanism(claim.scene)  # D1/D2

    IF exp.during is EMPTY:
        RETURN {status:"partial", expansion:exp, gap:"no process text"}
    RETURN {status:"covered", expansion:exp}

PRECONDITION : claim.claim_source 可定位
POSTCONDITION: status=="covered" -> exp.during 非空且每条有源
ASSERT       : 不存在 status=="covered" 而 dialogue_refs 全空且无概述的情况
```

## 测试用例

| 输入 | 期望 |
|---|---|
| WC-001（A 级概述） | partial（无逐字战斗过程） |
| WC-023（B 级 wiki） | 可扩写，但 confidence=B |
| 仅 D 级来源 | UNKNOWN |
