# PG-D4-001 dialogue_step

```text
# F: D4_dialogue/dialogues.jsonl（DLG-001..DLG-357）
FUNCTION dialogue_step(node, state):
    IF node is NULL: RETURN NONE
    IF NOT node.condition(state): RETURN NONE          # 本包全部为 linear
    OUTPUT node.verbatim                                # 逐字，不改写
    state.log.append(node.id)

    IF node.stage_direction is NOT NULL:
        state = apply_stage_direction(state, node.stage_direction)

    # speaker 未标注：只在模拟层用推断值，不回写事实
    state.last_speaker_inferred = node.speaker_inferred

    FOR nxt IN node.next:
        RETURN dialogue_step(look_up(nxt), state)       # 线性链
    RETURN NONE

PRECONDITION : node.verbatim_available == TRUE
POSTCONDITION: state.log 严格递增，不跳号
ASSERT       : 每个 node 至少被访问一次（用 dialogue_tree.json 校验）
```

## 测试用例

| 输入 | 期望 |
|---|---|
| DLG-001 | 输出『可「我」的故事，该从哪里说起呢？』，进入 DLG-002 |
| 链尾 DLG-357 | 输出后返回 NONE |
| 节点缺失 | 返回 NONE，不抛错、不补台词 |
