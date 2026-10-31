import io
p = r"d:\文档\Amphoreus\lore\D4_dialogue\scenes.jsonl"
s = io.open(p, encoding="utf-8").read()
reps = {
 '"DLG-016","DLG-033"': '"DLG-016","DLG-036"',
 '"DLG-034","DLG-047"': '"DLG-037","DLG-049"',
 '"DLG-048","DLG-060"': '"DLG-050","DLG-062"',
 '"DLG-061","DLG-113"': '"DLG-063","DLG-102"',
 '"DLG-114","DLG-168"': '"DLG-103","DLG-167"',
 '"DLG-169","DLG-218"': '"DLG-168","DLG-217"',
 '"DLG-219","DLG-270"': '"DLG-218","DLG-318"',
 '"DLG-271","DLG-357"': '"DLG-319","DLG-357"',
}
for a,b in reps.items():
    s = s.replace(a,b)
io.open(p,"w",encoding="utf-8").write(s)
print("ok")
