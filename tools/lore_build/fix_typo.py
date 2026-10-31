# -*- coding: utf-8 -*-
import io
p = r"d:\文档\Amphoreus\lore\D5_loops\loops.jsonl"
s = io.open(p, encoding="utf-8").read()
print("before", s.count("翁帕罗斯"))
s = s.replace("翁帕罗斯", "翁法罗斯")
io.open(p, "w", encoding="utf-8").write(s)
print("after", s.count("翁帕罗斯"))
