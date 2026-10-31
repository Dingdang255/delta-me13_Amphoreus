# PG-D4-003 rewind_anchor

```text
# F: S-001:424961『空缺的「原因」被「结果」补全，因果闭合』
FUNCTION rewind_anchor(node, world):
    PRECONDITION : node.target IN world.timeline
    # 回望不是改写历史，而是补『因』；每一遍严格单向（逆时）
    IF node.cause_is_missing(world):
        world.inject_memory_signature(node.target, source="德谬歌(伪浮黎)")
        world.mark_cause(node.id, cause="result")        # 用结果反向填因
    ASSERT world.causal_check(node.id) IN {"PASS","UNKNOWN"}
    RETURN world

FUNCTION causal_check(world, node_id):
    # 官方只说明『闭合』，未给判定算法
    IF world.cause_of(node_id) == "UNKNOWN": RETURN "UNKNOWN"
    IF world.cause_of(node_id) == world.effect_of(node_id): RETURN "PASS"
    RETURN "FAIL"

PRECONDITION : 回望方向单一（只能向过去）
POSTCONDITION: 每条被补的因都带 source=德谬歌(伪浮黎)
ASSERT       : 不存在『从过去改未来』的写操作
```

## 测试用例

| 输入 | 期望 |
|---|---|
| target=NeiKos496，cause 缺失 | 注入『救世主』记忆签名，cause=result |
| target 的 cause 已存在 | 不注入，直接返回 |
| causal_check 无法判定 | 返回 `UNKNOWN`，不强行 PASS |
