# PG-D6-003 format_garbage

```text
# F: TERM-019 黑潮 / S-001:425072 / S-001:225967（『檓Qf』类残字）
FUNCTION render_text(text, entropy, encoder):
    # 乱码不是装饰，是『渲染失败』的可观测形式
    IF encoder.failed(text):
        RETURN {shown: corrupt(text, ratio=entropy / RENDER_LIMIT),
                kind: "garbage", recoverable: FALSE}
    IF entropy >= RENDER_LIMIT:
        RETURN {shown: corrupt(text, ratio=entropy / RENDER_LIMIT),
                kind: "garbage", recoverable: TRUE}
    RETURN {shown: text, kind: "clean", recoverable: TRUE}

FUNCTION corrupt(text, ratio):
    # 不做逐字节模拟：官方没有给出算法；只保证输出长度不变、可辨识率随 ratio 下降
    out = ""
    FOR ch IN text:
        IF hash(ch, ratio) < ratio: out += REPLACEMENT_CHAR
        ELSE:                       out += ch
    RETURN out

PRECONDITION : RENDER_LIMIT is UNKNOWN            # 不得填魔法常量
POSTCONDITION: len(shown) == len(text)
ASSERT       : kind == "garbage" -> shown != text
```

## 常量表

| 名称 | 值 | 来源 | 说明 |
|---|---|---|---|
| `RENDER_LIMIT` | `UNKNOWN` | 无官方文本 | 只在伪代码中出现符号，不给数值 |
| `REPLACEMENT_CHAR` | `UNKNOWN` | 客户端未见固定替换符 | 中文 TextMap 的残字是解码产物，不是游戏内乱码 |

## 测试用例

| 输入 | 期望 |
|---|---|
| 正常文本，entropy=0 | `kind=clean`，原样输出 |
| 同一文本，entropy=RENDER_LIMIT | `kind=garbage`，长度不变 |
| encoder 失败 | `kind=garbage`，`recoverable=FALSE` |
