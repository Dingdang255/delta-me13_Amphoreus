# PG-D6-002 prompt_write_permission

```text
# F: TRM-003 / TRM-004 / TRM-006 / TRM-007 / S-001:122514
FUNCTION prompt_write_permission(program, state):
    OUTPUT ">>>来自未知发布者的程序 " + program        # 原文末尾带空格
    OUTPUT ">>>是否允许写入？"
    options = ["保持沉默", "（成像）"]                   # F: S-001:225893-225894
    IF NOT is_tty(): RETURN state.default_answer        # 默认值 UNKNOWN
    answer = read_line(timeout=UNKNOWN)                 # 超时行为 UNKNOWN
    IF answer NOT IN options: RETURN UNKNOWN
    IF answer == "（成像）":
        state.write_granted = TRUE
    IF answer == "保持沉默":
        state.write_granted = FALSE
    RETURN answer

PRECONDITION : program == "Philia093.exe"
POSTCONDITION: state.write_granted is BOOLEAN OR UNKNOWN
ASSERT       : IF state.write_granted THEN 后续必出现 "Philia093.exe 运行中…"

# 证据边界：
# 原文只给出两个选项与后续『运行中』状态，
# 但没有一句话说明『（成像）』= 允许。
# 因此 write_granted 的赋值是 inferred，不是 fact。
```

## 测试用例

| 输入 | 期望 |
|---|---|
| answer=`（成像）` | 返回 `（成像）`，write_granted=TRUE（inferred） |
| answer=`保持沉默` | 返回 `保持沉默`，write_granted=FALSE（inferred） |
| answer=`允许`（不在选项内） | 返回 `UNKNOWN` |
