# PG-D8-002 utility

```text
# F: characters/CHR-*.json（goals / beliefs / emotions / relations）
FUNCTION utility(agent, action, percept, memory, goals, relations):
    u  = 0
    u += agent.w_goal     * goal_satisfaction(action, goals)        # 权重 UNKNOWN
    u += agent.w_belief   * belief_consistency(action, agent.beliefs)
    u += agent.w_emotion  * emotion_pressure(action, agent.emotions, percept)
    u += agent.w_relation * relation_pressure(action, relations)
    u += agent.w_memory   * memory_consistency(action, memory)
    u -= agent.w_cost     * action_cost(action, percept)
    RETURN u

# 关键约束：权重不得拍脑袋
FUNCTION load_weights(agent):
    IF agent.w_* has official_value: RETURN official_value
    RETURN Symbolic("UNKNOWN")        # 保持符号，不倒填数字
```

## 测试用例

| 输入 | 期望 |
|---|---|
| CHR-001，action=夺火种 | goal 项为正（阻止再创世） |
| CHR-002，action=继续讲述 | emotion 项为正 |
| 无官方权重 | 返回符号，不返回 0.37 之类 |
