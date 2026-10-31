# PG-D2-003 apply_effect

```text
# F: micro_variables.jsonl.effect / causal_links.jsonl
FUNCTION apply_effect(world, effect):
    MATCH effect.type:
        CASE "state_change":
            IF world[effect.target] is UNKNOWN: RETURN UNKNOWN
            world[effect.target] += effect.magnitude      # magnitude 可能是 UNKNOWN
        CASE "event":
            emit_event(effect.magnitude)
        CASE "trend_shift":
            world.trends[effect.target] += effect.magnitude
        CASE "inherit":
            world.inherit_queue.append(effect)
        DEFAULT:
            RAISE UnknownEffect(effect.type)               # 不静默忽略

    FOR link IN CAUSAL_LINKS.where(from == effect.id):
        propagate(link)                                    # 见 causal_links.jsonl
    RETURN world

PRECONDITION : effect.magnitude 为数值或 "UNKNOWN"
POSTCONDITION: 任何 UNKNOWN 参与运算后结果仍为 UNKNOWN
ASSERT       : 不允许 UNKNOWN 被当作 0
```

## 测试用例

| 输入 | 期望 |
|---|---|
| magnitude=UNKNOWN | 目标值变为 UNKNOWN |
| type=foobar | 抛 UnknownEffect |
| 存在 CL-004 | 触发黑潮阈值检查 |
