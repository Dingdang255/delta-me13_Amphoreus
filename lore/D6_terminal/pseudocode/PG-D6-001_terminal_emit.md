# PG-D6-001 terminal_emit

```text
# F: TRM-001..TRM-081 / R: D6/triggers.json
FUNCTION terminal_emit(event, state):
    # 终端不是装饰：每条输出都由 event.kind 决定模板，并写入归档
    TEMPLATE = {
        "boot":     ">>>系统运行中…",
        "status":   ">>>{program}.exe 运行中…",
        "error":    ">>>发生了未经处理的异常({n}/3) 对象名:\"{obj}\"",
        "warn":     ">>>{message}",
        "archive":  ">>>{owner}的记录#{id}，已归档。",
        "output":   ">>>{key} = {value}",
        "annotation":" >>>注释：{label}。",
        "prompt":   ">>>{ask}"
    }                                                   # F: S-001:225888..225917
    IF event.kind NOT IN TEMPLATE: RETURN UNKNOWN       # 显式 UNKNOWN 分支
    text = format(TEMPLATE[event.kind], event.fields)
    OUTPUT text
    archive = state.logbook.append({text, event.id, state.loop})
    IF event.kind == "prompt":
        answer = ask_user(event.ask, event.options, event.default, event.timeout)
        state.last_answer = answer                       # F: S-001:225891
        RETURN answer
    RETURN NONE

PRECONDITION : event.kind != UNKNOWN
POSTCONDITION: state.logbook.length == PRE + 1
ASSERT       : text.startswith(">>>") OR event.kind == "annotation"
```

## 测试用例

| 输入 | 期望 |
|---|---|
| `{kind:"boot"}` 且 loop=33550336 | 输出 `>>>系统运行中…`，logbook +1 |
| `{kind:"prompt", ask:"是否允许写入？", options:["保持沉默","（成像）"]}` | 输出提示后阻塞，返回二者之一 |
| `{kind:"foo"}` | 返回 `UNKNOWN`，不输出、不写 logbook |
