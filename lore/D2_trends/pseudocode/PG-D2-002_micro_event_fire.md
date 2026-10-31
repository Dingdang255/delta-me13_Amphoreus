# PG-D2-002 micro_event_fire

```text
# F: micro_variables.jsonl（MV-001..031）
FUNCTION micro_event_fire(world, event, rng):
    IF NOT event.precondition(world): RETURN NONE

    IF event.first_seen.loop != "UNKNOWN" AND world.loop < event.first_seen.loop:
        RETURN NONE

    IF event.probability is UNKNOWN:
        # 官方从不给概率：改用确定性条件
        IF event.is_deterministic(world): apply_effect(world, event.effect)
        RETURN UNKNOWN

    IF rng.roll() >= event.probability: RETURN NONE
    apply_effect(world, event.effect)
    schedule_persistence(world, event)
    RETURN event.id

PRECONDITION : event.id 可在 micro_variables.jsonl 中找到
POSTCONDITION: 触发后 first_seen 被写入 world.timeline
ASSERT       : 不使用任何未登记的概率常数
```

## 测试用例

| 输入 | 期望 |
|---|---|
| MV-017 在 loop=50121 | 触发，毁灭行为首次形成 |
| MV-017 在 loop=50000 | 不触发（未到首次出现轮次） |
| 概率未知的 MV | 返回 UNKNOWN，不随机 |
