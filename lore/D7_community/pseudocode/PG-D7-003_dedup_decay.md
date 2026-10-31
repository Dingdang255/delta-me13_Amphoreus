# PG-D7-003 dedup_and_decay

```text
# F: channel_matrix.md / debunked.jsonl
FUNCTION dedup(fragments):
    groups = group_by(fragments, key=normalize(verbatim))
    FOR g IN groups:
        keep earliest(published_at, captured_at)     # 保留最早来源
        mark others as repost_of(keep.id)
    RETURN groups

FUNCTION decay(fragment, now):
    # 官方后续确认 → 升级 crossref；被证伪 → debunked
    IF exists_official_confirmation(fragment): fragment.canon_status = "confirmed"
    IF exists_counter_evidence(fragment):      fragment.canon_status = "debunked"
    IF now - fragment.captured_at > STALE:     fragment.flags.append("stale")
    RETURN fragment

PRECONDITION : published_at 可能为 UNKNOWN（按 captured_at 排序）
POSTCONDITION: 转载不产生新事实
ASSERT       : debunked 条目不删除，只改状态
```

## 测试用例

| 输入 | 期望 |
|---|---|
| 同一截图两次转载 | 合并，保留最早 |
| 官方证伪 | status=debunked，保留原文 |
| 无发布日期 | 以捕获日期排序 |
