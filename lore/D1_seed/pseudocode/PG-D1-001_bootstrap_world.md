# PG-D1-001 bootstrap_world

```text
# F: worldgen_dimensions.jsonl（WG-001..020）
FUNCTION bootstrap_world(input):
    # 注意：官方没有『seed』这一输入。input = {initial_variable, factors, protocol}
    PRECONDITION : input.initial_variable IN {无机, 有机, 人科人属, 古典文明}
    IF input.seed IS PRESENT: RETURN UNKNOWN        # S-A 无官方依据，拒绝建模

    world = empty_world()
    world.cosmology    = sample(WG-001, CONSTRAINTS.cosmology)
    world.calendar     = sample(WG-003, CONSTRAINTS.calendar)
    world.geography    = sample(WG-004, CONSTRAINTS.geography)
    world.civilization = input.initial_variable          # 官方：由阶段决定，非随机
    world.factors      = bind_twelve_factors(input.factors)
    world.protocol     = CONSTRAINTS.protocol            # 终极协议 / 嵌合协议

    ASSERT world.factors.length == 12
    ASSERT world.civilization <= 古典文明
    RETURN world
```

## 测试用例

| 输入 | 期望 |
|---|---|
| `initial_variable=无机` | 生成 12 因子、古典文明上限 |
| 传入 `seed=12345` | 返回 `UNKNOWN`（拒绝伪机制） |
| `initial_variable=星际文明` | 违反上限，拒答 |
