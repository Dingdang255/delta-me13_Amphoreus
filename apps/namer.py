"""L5：命名器。

名字不参与运算。删掉这个文件、换一套音位表，Trajectory 逐帧不变（判据五）。

三层：
  音位层  onset+nucleus(+coda) 拼出 2~3 个音节；韵尾只挂末音节（拉丁层即此层）。
  汉字层  每个音节取【一个】字，同音多字由个体指纹择一；全名 2~4 字、
          不重复用字、不堆韵尾字。这是让名字"像人起的"而不是"批量拼的"。
  机器层  Neikos123 这样的编号，只用于日志。
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from types import SimpleNamespace

import numpy as np


def _split_machine(machine):
    """`NeiKos496` → `("neikos", 496)`；认不出（没尾号）就给 None。

    用来把预设预分配的机器编号拆成「哪个因子下、几号」—— 发号时据此跳过。
    """
    if not machine:
        return None
    m = re.match(r"^([A-Za-z]+?)(\d+)$", str(machine))
    if not m:
        return None
    return m.group(1).lower(), int(m.group(2))


class Namer:
    def __init__(self, ctx, anchors=None):
        self.ctx = ctx
        self.ph = ctx.phonology
        self.seed = int(getattr(ctx, "seed", 0))
        # 锚定层：外部给定的渲染绑定。它只改名字，不改轨迹（判据五）。
        # 键形如 fingerprint:<hex> / locus:<LXX> / emerge:<n>
        self.anchors = {}
        for a in (anchors or []):
            key = a.get("key")
            if not key and a.get("fingerprint"):
                key = "fingerprint:" + str(a["fingerprint"])
            if not key:
                continue
            self.anchors[str(key)] = (
                str(a.get("latin", "")), str(a.get("hanzi", "")), a.get("machine"))
        # 预设按 `machine` 钉死的编号：记下【哪个因子下、哪些号已被占】——
        # 演算发号时跳过它们（同因子下不撞号）。按词干归并、大小写不敏感。
        self._reserved = {}
        for a in (anchors or []):
            hit = _split_machine(a.get("machine"))
            if hit:
                self._reserved.setdefault(hit[0], set()).add(hit[1])
        self._seq = {}           # 每个词干发到几号了 —— 按因子各自一条序列
        # 已经发出去的号，按个体记忆：`machine_name()` 会推进上面那条序列，故
        # **同一个体只能发一次**。键 =(指纹, 编号, 涌现次序, 因子位次) —— 四项一齐才唯一。
        self._machines = {}
        # 「外部变量」标记（预设 anchors 里的 `external: true`）：这几位不是从池子里长出来的
        # 电信号序列，故不领机器编号 —— 看板席位卡悬浮报「?」。
        self.external = set()
        for a in (anchors or []):
            if not a.get("external"):
                continue
            key = str(a.get("key", ""))
            if key.startswith("serial:"):
                try:
                    self.external.add(int(key.split(":", 1)[1]))
                except ValueError:
                    pass
        self._corpus = self._corpus_weights()
        self.style = self._style()

    # ---- 种子风格：换一个种子，名字的【生成方式】也变，而不只是结果变 --------
    def _style(self):
        """由种子导出的全局音位风格。只影响渲染层，不改轨迹（判据五）。

        long_period  每 long_period 个名字里出一个三音节名（其余两音节）
        coda_tilt    >0 偏好闭音节（-s/-n/-r…），<0 偏好开音节
        onset_tilt   >0 偏好复辅音声母（kl-/th-/ph-…），<0 偏好单辅音
        """
        b = hashlib.blake2b(f"style|{self.seed}".encode("utf-8"), digest_size=16).digest()
        lo, hi = self.ph["syllables"]
        return {
            "syllables": [int(lo), int(hi)],
            "long_period": 3 + int(b[0] % 3),      # 三音节约占 1/3~1/5
            "coda_tilt": float((b[1] / 255.0 - 0.5) * 0.8),
            "onset_tilt": float((b[2] / 255.0 - 0.5) * 0.8),
        }

    # ---- 语料标定：用原作人名统计字频，让生成结果"像"这门语言 ----------
    def _corpus_weights(self):
        cnt = Counter()
        for w in self.ph.get("corpus", []):
            for ch in w:
                cnt[ch] += 1
        return cnt

    def _stream(self, key: str, size: int = 32) -> bytes:
        return hashlib.blake2b(
            f"{key}|{self.seed}".encode("utf-8"), digest_size=size
        ).digest()

    # ---- 权重 --------------------------------------------------------
    def _onset_w(self):
        t = self.style["onset_tilt"]
        w = np.array([(self._corpus.get(s[0], 0) + 0.5) * (1.0 + t * (len(s) - 1))
                      for s in self.ph["onsets"]], dtype=float)
        np.clip(w, 1e-6, None, out=w)
        return w / w.sum()

    def _nucleus_w(self, order: int):
        bias_tab = self.ph.get("nucleus_bias_by_order", [])
        bias = bias_tab[order % len(bias_tab)] if bias_tab else {}
        w = np.array([self._corpus.get(n[0], 0) + 0.5 + bias.get(n, 0.0)
                      for n in self.ph["nuclei"]], dtype=float)
        return w / w.sum()

    def _coda_w(self):
        t = self.style["coda_tilt"]
        w = []
        for c in self.ph["codas"]:
            base = 1.0 if c == "" else 0.25 + self._corpus.get(c[0], 0)
            w.append(max(base * (1.0 - t) if c == "" else base * (1.0 + t), 1e-6))
        w = np.array(w, dtype=float)
        return w / w.sum()

    @staticmethod
    def _pick(seq, weights, u: float):
        c = np.cumsum(weights)
        return seq[int(np.searchsorted(c, u, side="right")) % len(seq)]

    # ---- 音位层 ------------------------------------------------------
    def syllables(self, key: str, order: int):
        """2~3 个音节；韵尾只挂在最后一个音节上（更接近希腊式人名的节奏）。"""
        ph = self.ph
        buf = self._stream(key, 48)
        n = 3 if buf[0] % self.style["long_period"] == 0 else 2
        ow, nw, cw = self._onset_w(), self._nucleus_w(order), self._coda_w()
        out = []
        for i in range(n):
            coda = self._pick(ph["codas"], cw, buf[3 + 3 * i] / 255.0) if i == n - 1 else ""
            out.append((
                self._pick(ph["onsets"], ow, buf[1 + 3 * i] / 255.0),
                self._pick(ph["nuclei"], nw, buf[2 + 3 * i] / 255.0),
                coda,
            ))
        return out

    def latin(self, syls) -> str:
        return "".join(o + n + c for o, n, c in syls)

    # ---- 汉字层 ------------------------------------------------------
    def _grapheme(self, onset, nucleus, key, i, used: str) -> str:
        """一个音节 → 一个字。同音多字由指纹择一；已用过的字跳开。"""
        t = self.ph["translit"]
        opts = t.get(onset + nucleus) or t.get(nucleus) or t.get(onset) or []
        if isinstance(opts, str):
            opts = [opts]
        if not opts:
            return ""
        b = self._stream(f"{key}|g{i}", 8)
        start = b[0] % len(opts)
        for j in range(len(opts)):
            ch = opts[(start + j) % len(opts)]
            if ch and ch not in used:
                return ch
        return opts[start]

    def hanzi(self, syls, key: str = "") -> str:
        out = []
        for i, (o, n, _c) in enumerate(syls):
            ch = self._grapheme(o, n, key, i, "".join(out))
            if ch:
                out.append(ch)
        # 韵尾字只缀在末尾，且仅在名字本来就只有 2 字时 —— 避免汉名越堆越长。
        if len(out) <= 2 and syls and syls[-1][2]:
            b = self._stream(f"{key}|z", 8)
            if b[0] % 3 == 0:
                cc = self.ph["translit_coda"].get(syls[-1][2], "")
                if cc and cc not in "".join(out):
                    out.append(cc)
        return "".join(out)

    # ---- 锚定层 ------------------------------------------------------
    def name_by_serial(self, serial):
        """按【个体编号】取锚定之名。返回 None = 这个体没被点名。

        编号是【人】的身份（席位会换手，编号不会），所以它是「名随人走」的稳定键：
        预设要把一个名字钉给某个个体，就钉在这一键上，此后他坐到哪一席都叫这个名字。
        """
        if serial is None:
            return None
        a = self.anchors.get(f"serial:{int(serial)}")
        return (a[0], a[1]) if a is not None else None

    def is_external(self, serial) -> bool:
        """这个编号是不是预设标记的「外部变量」—— 他们不属电信号序列（自天外而来）。"""
        return serial is not None and int(serial) in self.external

    def machine_by_serial(self, serial):
        """按【编号】取锚定钉死的机器编号（预设没钉就 None）。与 `name_by_serial` 一对。

        与 `machine_name()` 的区别：那个还要指纹 / 涌现次序才认得出来，这个只认
        `serial:<n>` 这一键 —— 看板的席位卡要报「电信号序列」，拿不到指纹时用得上。
        """
        if serial is None:
            return None
        a = self.anchors.get(f"serial:{int(serial)}")
        return str(a[2]) if (a and a[2]) else None

    def stall_seat_id(self):
        """预设选定的【承载者那一席】（`stall_seat:<LXX>`）。None = 没有指定。"""
        for key in self.anchors:
            if key.startswith("stall_seat:"):
                return key.split(":", 1)[1]
        return None

    def stall_alt_name(self):
        """承载者的受难之名 —— 预设把它绑在【承载者那一席】上，谁占那一席就是谁。"""
        lid = self.stall_seat_id()
        if lid is None:
            return None
        a = self.anchors.get(f"stall_seat:{lid}")
        return (a[0], a[1]) if a and a[1] else None

    def stall_seat_index(self):
        """承载者那一席的【位次】。渲染层据此在位表里找到当下的承载者。"""
        lid = self.stall_seat_id()
        if lid is None:
            return None
        for i, l in enumerate(self.ctx.loci):
            if l.id == lid:
                return i
        return None

    # ---- 三层名字 ----------------------------------------------------
    def machine_name(self, fingerprint: bytes, serial: int, rank: int = -1,
                     order=None) -> str:
        """机器编号（`词干 + 序号`）。锚定钉死的优先；否则**按因子发号**。

        词干取【这个体所属因子】的（`order` = 它占的那一席的 `loci.order`）—— 与席位名
        （`render.seat` 同样按 `loci.order` 取词干）是**同一把尺子**，否则会出现
        「坐在第 2 号原动力上、机器名却是别的因子」这种对不上号的情况。没有因子（未占席）
        时才退回指纹字节。

        发号是【按因子（词干）各自一条序列】：同一因子的第 1、2、3… 位依次领 1、2、3…，
        并跳过预设按 `machine` 预分配掉的号（该因子下）—— 于是不会和剧情编号撞车。
        """
        fp = fingerprint.hex()
        cand = [f"fingerprint:{fp}", f"serial:{int(serial)}"]
        if rank is not None and int(rank) >= 0:
            cand.append(f"emerge:{int(rank)}")
        for k in cand:
            a = self.anchors.get(k)
            if a and a[2]:
                return str(a[2])
        stems = self.ph["machine_stems"]
        i = int(order) if (order is not None and int(order) >= 0) else int(fingerprint[0])
        s = str(stems[i % len(stems)])
        return s[0].upper() + s[1:] + str(self._take_number(s))

    def _take_number(self, stem: str) -> int:
        """该因子（词干）下的下一个可用序号：跳过预分配掉的号，并把计数推进一位。"""
        key = str(stem).lower()
        n = self._seq.get(key, 1)
        reserved = self._reserved.get(key) or ()
        while n in reserved:
            n += 1
        self._seq[key] = n + 1
        return n

    def title(self, locus):
        a = self.anchors.get("locus:" + locus.id)
        if a and a[1]:
            return a[0], a[1]
        cal = self.ph.get("title_calibration", {}).get(locus.id)
        if cal:
            return cal[0], cal[1]
        syls = self.syllables("title:" + locus.id, locus.order)
        return self.latin(syls), self.hanzi(syls, "title:" + locus.id)

    def title_by_id(self, locus_id: str):
        for l in self.ctx.loci:
            if l.id == locus_id:
                return self.title(l)
        return str(locus_id), str(locus_id)

    def persona_name(self, persona):
        """个体的名字。【名随人走】：名字钉在人身上，不钉在席位上 —— 换手就换名。

        前三者是【身份键】，预设靠它点名某一个人；末路才由音位层现生成：
          指纹 fingerprint:<hex> → 编号 serial:<n> → 涌现次序 emerge:<rank> → 现生成。

        席位本身的名字是【职位】（负世 / 岁月 / 门径…，见 title()），永远不当作人名。
        """
        fp = persona.fingerprint.hex()
        a = self.anchors.get(f"fingerprint:{fp}")
        if a is not None:
            return a[0], a[1]
        a = self.name_by_serial(getattr(persona, "serial", None))
        if a is not None:
            return a
        rank = getattr(persona, "rank", -1)
        if rank is not None and int(rank) >= 0:
            b = self.anchors.get(f"emerge:{int(rank)}")
            if b is not None:
                return b[0], b[1]
        order = getattr(persona, "locus_order", None)
        style_order = order if order is not None else 0
        key = "persona:" + fp
        syls = self.syllables(key, style_order)
        return self.latin(syls), self.hanzi(syls, key)

    def _machine_for(self, fp: bytes, serial: int, rank: int, order) -> str:
        """机器编号 —— **按个体记忆**，同一个体只发一次号。

        `machine_name()` 会推进「按因子各自一条序列」的计数器，同一个体被问两次就会
        领到两个号（实测：先问得 `Polla1`、再问得 `Polla2`）。故这里必须记忆。
        """
        key = (bytes(fp), int(serial), int(rank), order)
        got = self._machines.get(key)
        if got is None:
            got = self.machine_name(fp, int(serial), int(rank), order=order)
            self._machines[key] = got
        return got

    def bind_machines(self, personas) -> None:
        """按【登记次序】给一批个体各钉一个机器编号 —— 幂等。

        发号随次序推进，故**必须按登记次序、且每个个体只发一次**。把「什么时候发号」
        从渲染时刻提前到「拿到轨迹的那一刻」，同一批个体领到的号就与迁移前逐字相同。
        """
        for p in personas:
            self.machine_name_of(p)

    def machine_name_of(self, persona) -> str:
        """给一个【内核侧】的个体现取机器名。

        内核的 `Persona` 不再持有名字（那是表现层的东西），故名字在这里按需取 ——
        输入与迁移前逐项相同（同样的 fingerprint / serial / rank / locus_order），
        且按个体记忆，多次读取不会重新发号。
        """
        return self._machine_for(
            persona.fingerprint, getattr(persona, "serial", -1),
            getattr(persona, "rank", -1), getattr(persona, "locus_order", None))

    def named_payload(self, payload) -> dict:
        """把内核发来的 EMERGENCE 数字载荷补成可渲染的词。

        内核只发 `{serial, rank, fingerprint, locus?, locus_order?}`；词汇全在这一层补。
        """
        fp = bytes.fromhex(str(payload["fingerprint"]))
        serial = int(payload.get("serial", -1))
        rank = int(payload.get("rank", -1))
        order = payload.get("locus_order")
        shim = SimpleNamespace(fingerprint=fp, serial=serial, rank=rank,
                               locus_order=order)
        latin, hanzi = self.persona_name(shim)
        out = dict(payload)
        out["latin"], out["hanzi"] = latin, hanzi
        out["machine"] = self._machine_for(fp, serial, rank, order)
        return out

    def export_anchors(self, personas):
        out = []
        for p in personas:
            latin, hanzi = self.persona_name(p)
            out.append({
                "fingerprint": p.fingerprint.hex(),
                "name": (latin, hanzi),
                "latin": latin,
                "hanzi": hanzi,
            })
        return out