# -*- coding: utf-8 -*-
import io, json, os, glob, sys

root = r"d:\文档\Amphoreus\lore"
errors = []
counts = {}
files = 0

for dirpath, _, names in os.walk(root):
    if "_probe" in dirpath or "_work" in dirpath or "export" in dirpath or "story" in dirpath:
        continue
    for n in names:
        p = os.path.join(dirpath, n)
        rel = os.path.relpath(p, root)
        files += 1
        try:
            if n.endswith(".json"):
                json.load(io.open(p, encoding="utf-8"))
            elif n.endswith(".jsonl"):
                k = 0
                for i, line in enumerate(io.open(p, encoding="utf-8"), 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                    except Exception as e:
                        errors.append(f"{rel}:{i} {e}")
                    k += 1
                counts[n] = counts.get(n, 0) + k
        except Exception as e:
            errors.append(f"{rel} {e}")

print("files", files)
print("counts")
for k, v in sorted(counts.items()):
    print(" ", k, v)
print("errors", len(errors))
for e in errors[:30]:
    print("  !", e)
