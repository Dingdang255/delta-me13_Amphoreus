# -*- coding: utf-8 -*-
import io, re
p = r"d:\文档\Amphoreus\lore\D5_loops\official_anchors.jsonl"
s = io.open(p, encoding="utf-8").read()
n = len(re.findall(r'"id":"OA-\d{3},', s))
s2 = re.sub(r'"id":"(OA-\d{3}),', r'"id":"\1",', s)
io.open(p, "w", encoding="utf-8").write(s2)
print("fixed", n)
