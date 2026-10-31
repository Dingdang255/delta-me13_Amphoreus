# PG-D2-004 propagate_inheritance

```text
# F: D1_seed/inheritance.json + D2/trends.jsonl
FUNCTION propagate_inheritance(world, next_world):
    FOR item IN world.inherit_queue:
        MATCH item.rule:
            CASE "carry":            next_world[item.key] = world[item.key]
            CASE "carry_partial":    next_world[item.key] = partial(world[item.key])
            CASE "carry_with_distortion":
                                     next_world[item.key] = distort(world[item.key], rate="UNKNOWN")
            CASE "drop":             next_world[item.key] = RESET
            CASE "random":           next_world[item.key] = perturb(world[item.key], rng="UNKNOWN")
            DEFAULT:                 RAISE UnknownRule(item.rule)

    # 趋势量跨轮的方向性
    next_world.entropy     = max(next_world.entropy, world.entropy)      # 单调
    next_world.memory_mass = next_world.memory_mass + world.memory_mass  # 只增

    ASSERT next_world.memory_mass >= world.memory_mass
    ASSERT next_world.destruction >= world.destruction OR is_reset(world)
    RETURN next_world
```

## 测试用例

| 输入 | 期望 |
|---|---|
| carry 记忆档案 | 下一轮保留 |
| drop 黄金裔记忆 | 下一轮清空 |
| random 且 rng=UNKNOWN | 标记 unquantified，不填数值 |
