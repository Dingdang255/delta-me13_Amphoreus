# PG-D5-001 loop_iteration

```text
# F: 424957 / 218705 / 225913 / 425075
FUNCTION loop_iteration(i, prev_state, world):
    PRECONDITION : i >= 1
    state = inherit(prev_state, world.rng, i)          # 继承规则见 D1/inheritance.json
    newborn = fork_philia(template=PHILIA_TEMPLATE, memory=CLEARED)   # F: 424957
    state = run_flame_chase(newborn, world)            # F: 218705『严格按原定设计顺序』
    state = kill_at_vortex(state, killer=NEIKOS, weapon=RITUAL_SWORD) # 证据仅覆盖部分轮次 → UNKNOWN 分支
    state = upload_memory(state, to=TOMB, filter=EMPATHY)             # F: 424955
    state = format_and_recycle(state, target=newborn)  # F: 225913
    state = maybe_external_intervention(state, world, i)              # F: 424963
    RETURN state

FUNCTION kill_at_vortex(state, killer, weapon):
    IF state.loop IN OFFICIAL_KILL_RECORDS: RETURN apply_official(state)
    # 无官方记录：不得默认使用仪式剑
    RETURN state.with_unknown("kill.by","kill.weapon","kill.location")

PRECONDITION : state.loop == i
POSTCONDITION: state.logbook.entry(i).evidence IN {official, reconstructed}
ASSERT       : fire.taken + fire.burden == fire.total OR fire.total == UNKNOWN
```

## 测试用例

| 输入 | 期望 |
|---|---|
| `i=1, prev=空` | 产出 official 条目（对照 OA-001/OA-002） |
| `i=100, 无记录` | 产出 reconstructed，`kill.weapon=UNKNOWN` |
| `i=33550336` | 产出 official，`seats.vacant=["岁月","负世"]` |
