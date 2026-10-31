# PG-D1-003 bind_twelve_factors

```text
# F: S-001:425048（十二因子定义）/ 425079-425091（十二条路径与注释）
FUNCTION bind_twelve_factors(factors):
    FACTOR_TABLE = [
        ("负世","憎恨"), ("岁月","哀怜"), ("诡计","渴望"), ("死亡","平和"),
        ("理性","批判"), ("律法","支配"), ("海洋","自否"), ("纷争","约束"),
        ("浪漫","节制"), ("天空","奉献"), ("门径","同理"), ("大地","求存")
    ]                                                # F: 425079-425091 逐条
    PRECONDITION : factors.length == 12

    out = []
    FOR i IN 0..11:
        f = factors[i]
        f.id     = i
        f.path   = FACTOR_TABLE[i].path
        f.motive = FACTOR_TABLE[i].motive
        f.simulated_path = SIM_PATH[i]               # 见 05_term_index TERM-033..044
        out.append(f)

    ASSERT no_two_factors_share_path(out)
    RETURN out

FUNCTION verify_by_contradiction(factors):
    # 官方：『通过反证法，将十二因子投入实验并逐一证伪』
    FOR f IN factors:
        f.refuted = TRUE                             # 目标是把每种原动力都导向毁灭
    RETURN factors
```

## 测试用例

| 输入 | 期望 |
|---|---|
| 12 个空因子 | 依次填入 12 条路径与原动力 |
| 11 个 | 断言失败（PRECONDITION） |
| 检查重复路径 | 无重复 |
