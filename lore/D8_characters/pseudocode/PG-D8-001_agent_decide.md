# PG-D8-001 agent_decide

```text
# F: characters/CHR-*.json（decision_rules）
FUNCTION agent_decide(agent, percept, memory, goals, relations):
    candidates = enumerate_actions(agent, percept)
    scored = []
    FOR action IN candidates:
        IF violates_red_line(agent, action): CONTINUE      # ooc_guards.jsonl
        s = utility(agent, action, percept, memory, goals, relations)
        scored.append((s, action))
    IF scored is EMPTY: RETURN Action.WAIT
    RETURN argmax(scored).action

FUNCTION violates_red_line(agent, action):
    FOR g IN agent.ooc_guards:
        IF g.severity == "hard" AND g.matches(action): RETURN TRUE
    RETURN FALSE
```

## 测试用例

| 输入 | 期望 |
|---|---|
| CHR-001 面对『完成再创世』 | 被 R-001 排除（red line：不得主动完成） |
| CHR-013 面对『直接杀死变量』 | 不选（他借系统与协议） |
| 无候选 | WAIT |
