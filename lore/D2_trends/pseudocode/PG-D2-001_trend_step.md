# PG-D2-001 trend_step

```text
# F: trends.jsonl（TREND-001..008）
FUNCTION trend_step(world, dt):
    world.entropy      += trend_entropy(world) * dt       # TREND-001，系数 UNKNOWN
    world.civ_level     = max(world.civ_level, trend_civ(world))  # TREND-002，不可逆
    world.destruction  += trend_destruction(world) * dt   # TREND-003
    world.black_tide    = update_black_tide(world, dt)    # TREND-004，阈值型
    world.renewal_rate  = update_renewal_rate(world)      # TREND-005
    world.memory_mass  += memory_inflow(world)            # TREND-006，单调不减
    world.causal_gap    = update_causal_gap(world)        # TREND-007
    world.external      = update_external(world)          # TREND-008

    ASSERT world.entropy >= 0
    ASSERT world.civ_level <= CLASSICAL                   # 官方硬上限
    ASSERT world.memory_mass >= PREVIOUS.memory_mass      # 不得回退
    RETURN world

FUNCTION update_black_tide(world, dt):
    IF world.entropy < THRESHOLD: RETURN world.black_tide  # THRESHOLD = UNKNOWN
    RETURN world.black_tide + spike(world)                 # 阈值后尖峰
```

## 测试用例

| 输入 | 期望 |
|---|---|
| civ_level=有机，推进 1 步 | 不超过古典文明 |
| entropy < 阈值 | 黑潮不变 |
| memory_mass 回退 | 断言失败 |
