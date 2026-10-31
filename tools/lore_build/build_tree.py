import json, io, collections
p = r"d:\文档\Amphoreus\lore\D4_dialogue\dialogues.jsonl"
scenes = collections.OrderedDict()
for line in io.open(p,encoding="utf-8"):
    d=json.loads(line)
    s=scenes.setdefault(d["scene_id"], {"scene_id":d["scene_id"],"entry":d["id"],"nodes":[]})
    s["nodes"].append({"id":d["id"],"order":d["order"],"speaker_inferred":d["speaker_inferred"],"next":d["next"],"locator":d["locator"],"condition":"linear"})
tree = {"version":"1.0","note":"对话树只表达『顺序 + 条件』；branch 未在数据源中标注，故全部为 linear。player 选项节点见 D6/triggers.json。","scenes":list(scenes.values())}
out=r"d:\文档\Amphoreus\lore\D4_dialogue\dialogue_tree.json"
io.open(out,"w",encoding="utf-8").write(json.dumps(tree,ensure_ascii=False,indent=1))
print("scenes",len(scenes),"nodes",sum(len(v["nodes"]) for v in scenes.values()))
