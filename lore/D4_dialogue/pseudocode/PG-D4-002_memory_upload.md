# PG-D4-002 memory_upload

```text
# F: S-001:424957 / S-001:424955 / S-001:162192
FUNCTION memory_upload(speaker, listener, world):
    # 每一世：小昔涟被杀 → 记忆入剑 → 大墓 → 讲给德谬歌
    dump = serialize(world.memory_of(speaker))          # 内容粒度 UNKNOWN
    sword = world.item("仪式剑")                        # F: S-001:30414
    sword.buffer.append(dump)
    tomb  = world.location("无名泰坦大墓")              # F: S-001:424962
    tomb.receive(dump, filter=speaker.empathy_filter)   # filter = 哀怜（原动力）
    listener.absorb(tomb.latest)                        # 德谬歌累积『记忆的种子』
    RETURN {id: tomb.latest.id, bytes: "UNKNOWN"}

PRECONDITION : speaker.form == "小昔涟"
POSTCONDITION: tomb.latest 单调递增（每世至少 1 条）
ASSERT       : listener.memory_mass 不回退
```

## 测试用例

| 输入 | 期望 |
|---|---|
| 第 1 世上传 | tomb.latest.id 存在，内容为 UNKNOWN |
| 第 1 次成功上传 | 后续 dialogue_step 出现『未定义的记录#6』等编号 |
| speaker.form=大昔涟 | 前置条件不满足，返回 UNKNOWN |
