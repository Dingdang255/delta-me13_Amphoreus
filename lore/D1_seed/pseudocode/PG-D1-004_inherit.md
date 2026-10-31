# PG-D1-004 inherit

```text
# F: inheritance.json（carry 7 项 / reset 3 项）
FUNCTION inherit(prev_world, cycle):
    next = clone_structure(prev_world)

    FOR item IN CARRY:
        IF item.rule == "carry":
            next[item.key] = prev_world[item.key]
        IF item.rule == "carry_partial":
            next[item.key] = partial(prev_world[item.key], lost="UNKNOWN")
        IF item.rule == "carry_with_distortion":
            next[item.key] = distort(prev_world[item.key], rate="UNKNOWN")  # RND-003

    FOR item IN RESET:
        next[item.key] = RESET_VALUE[item.key]

    # 继承的随机性：官方承认存在，但未给作用域
    IF RND-001.applies_to(next):
        next = perturb_unknown(next)
        next.flags.append("inheritance_randomness_unquantified")

    next.loop = cycle
    ASSERT next.loop == cycle
    ASSERT "seed" NOT IN next          # 官方无此键
    RETURN next
```

## 测试用例

| 输入 | 期望 |
|---|---|
| cycle=2 | 记忆/火种/神话/协议继承；黄金裔记忆重置 |
| 需要精确随机扰动 | 标记 `inheritance_randomness_unquantified`，不填数值 |
| 试图继承 `seed` | 断言失败 |
