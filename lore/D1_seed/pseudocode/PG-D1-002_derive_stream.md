# PG-D1-002 derive_stream

```text
# F: random_streams.json（official_randomness RND-001..003）
FUNCTION derive_stream(world, tag):
    # 官方只承认『继承的随机性』，不承认『生成的随机性』
    MATCH tag:
        CASE "signal_behavior":  RETURN rng_from(RND-001)   # C
        CASE "organic_variance": RETURN rng_from(RND-002)   # C
        CASE "myth_distortion":  RETURN rng_from(RND-003)   # C
        DEFAULT:                 RETURN UNKNOWN             # 不发明新流

FUNCTION rng_from(rule):
    IF rule.entropy == "UNKNOWN": RETURN DeterministicStub(rule.id)
    RETURN PRNG(rule.seed)
```

## 测试用例

| 输入 | 期望 |
|---|---|
| tag=signal_behavior | 返回带 RND-001 标注的流 |
| tag=geography | `UNKNOWN`（官方没有地理随机性表述） |
| 任何需要具体 entropy 的调用 | 返回 Stub，不返回数值 |
