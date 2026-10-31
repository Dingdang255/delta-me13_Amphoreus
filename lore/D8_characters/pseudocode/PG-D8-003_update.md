# PG-D8-003 update_belief_and_emotion

```text
# F: characters/CHR-*.json（beliefs / emotions）
FUNCTION update_belief(agent, observation):
    IF observation.contradicts(agent.beliefs):
        MATCH agent.revision_mode:
            CASE "deny":     agent.beliefs.unchanged = TRUE
            CASE "revise":   agent.beliefs = revise(agent.beliefs, observation)
            DEFAULT:         agent.beliefs.flags.append("revision_mode_UNKNOWN")
    RETURN agent.beliefs

FUNCTION update_emotion(agent, percept):
    FOR e IN agent.emotions:
        IF e.trigger.matches(percept):
            e.intensity = clamp(e.intensity + e.response, 0, 1)
        ELSE:
            e.intensity = e.intensity * e.decay      # decay 可为 UNKNOWN
    RETURN agent.emotions
```

## 测试用例

| 输入 | 期望 |
|---|---|
| CHR-001 看到同伴死亡 | 提高『避免牺牲』权重（对应 R-002） |
| CHR-003 收到无法解析的情感词 | 输出错误进程，intensity 不变 |
| decay=UNKNOWN | 强度保持，不衰减、不臆造 |
