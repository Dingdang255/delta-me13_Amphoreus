# PG-D8-004 speak_and_relation

```text
# F: characters/CHR-*.json（speech / relations）
FUNCTION speak(agent, listener, context):
    text = render_intent(agent, listener, context)
    ASSERT style_check(text, agent.speech) == PASS
    RETURN text

FUNCTION style_check(text, speech):
    IF speech.tone == "UNKNOWN": RETURN "UNKNOWN"        # 不判定
    IF violates(speech.taboo_topics, text): RETURN "FAIL"
    IF speech.sentence_style == "破碎短句" AND has_complex_clause(text): RETURN "FAIL"
    RETURN "PASS"

FUNCTION relation_update(agent, target, action):
    r = agent.relations[target]
    r.intensity = clamp(r.intensity + delta(action, r.type), -1, 1)
    RETURN r

PRECONDITION : target 在 agent.relations 中
POSTCONDITION: intensity ∈ [-1,1]
ASSERT       : 关系变化必须有触发场景（evidence 非空）
```

## 测试用例

| 输入 | 期望 |
|---|---|
| CHR-003 说长复合句 | style_check FAIL |
| CHR-001 对敌人说『伙伴』 | 视 address 规则判 FAIL |
| 关系目标不存在 | 抛 KeyError，不静默创建 |
