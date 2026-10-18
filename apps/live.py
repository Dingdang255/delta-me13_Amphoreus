"""L6：实时看板（只读）。

`run.py --serve` 用它起一台【只用标准库】的小服务器：先把一张空看板交给浏览器，
再照常开始演算；页面每 0.7 秒向 `state` 取一次**增量**，于是世界一边跑、图一边长。

它是纯附加层：删掉它（或不用 --serve），演算逐帧不变。

线程分工：
  主线程  演算本体 —— 通过 watch 钩子与实时回调把读数写进 LiveState（加锁）
  服务线程 应答 /（页面）与 /state（增量 JSON）
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .render import _stage_at, stage_rows
from .viz import (Sampler, _TIMELINE_COLORS, _event_label, _machine_map,
                  _machine_of, _name_map, _resolve, _stages_html)

# 实时看板一次最多回多少条增量 —— 页面拿得住，也不至于一帧一堵墙
_MAX_CHUNK = 4000


class LiveState:
    """演算进行中的那份「可展示状态」。演算侧写、服务侧读，全程加锁。"""

    def __init__(self, ctx=None, data=None):
        self.lock = threading.Lock()
        self.ctx = ctx             # 阶段目录要用（词表 / loci / params）
        self.data = data           # 阶段目录要用（stage_profiles / genesis）
        self.samples = []        # [frame, 熵, 溢出, 种群, 换代, 在位, [席位下标]]
        self.seatnames = []      # 名字表（下标 1 起，0 = 空席）
        self.machines = []       # 与 seatnames **同下标**：机器编号（席位卡悬浮报「电信号序列」）
        self.rows = []           # [frame, 文本, 徽标]
        self.promos = []         # [frame, 轮次]
        self.marks = []          # [frame, 类别, 文案, 配色]
        self.mythfrom = None     # 「世界内」（第四阶段）从哪一帧起；None = 还没走到
        self.frame = 0
        self.done = False
        self.verdict = None
        self.cards = None
        self._names = {}
        self._seen_kind = {}
        self.switch = None       # 「自动更替 → 再创世」的切换帧（见 add_event）
        # 阶段目录：边跑边累计（与 render.stage_table 同源，交给 stage_rows 装配）。
        self.stage_starts = [0]
        self.stage_counts = [[0, 0, 0]]     # 每档 [涌现, 换代, 陨落]
        self._seen_fell = 0
        self.exhausted = False
        # 演算结束、完整静态页备好之后由 run.py 填进来；此后 `/` 一律给这一份。
        self.final_page = None

    # ---- 演算侧 ----------------------------------------------------------
    def put_name(self, name, machine=""):
        """名字 → 下标（1 起）。机器编号跟着名字一起登记，两张表严格同下标。"""
        if name is None:
            return 0
        key = str(name)
        if key not in self._names:
            self._names[key] = len(self.seatnames) + 1
            self.seatnames.append(key)
            self.machines.append(str(machine or ""))
        return self._names[key]

    def add_point(self, point, resolve):
        """收一组采样（与 viz.Sampler 同形）：席位在位者编成名字下标，省得人名重复上千遍。

        `resolve(serial)` 返回 `(人名, 机器编号)` —— 两张表同下标一起长。
        """
        with self.lock:
            seats = []
            for serial in point[6]:
                hit = resolve(serial)
                seats.append(0 if hit is None else self.put_name(hit[0], hit[1]))
            self.samples.append([int(point[0]), point[1], point[2], point[3],
                                 point[4], point[5], seats])
            self.frame = max(self.frame, int(point[0]))

    def add_row(self, frame, text, badge, rid):
        with self.lock:
            # 第 4 位是【事件号】(rid)，与 marks 末尾那个同源 —— 双击时间线节点精确回跳用。
            self.rows.append([int(frame), str(text), badge, int(rid)])

    def add_event(self, R, frame, kind, payload, rid, per_kind=40):
        """时间线上的一个点（与静态导出同一套配色 / 文案口径）。

        顺带把【阶段目录】的读数累计起来（`stage_starts` / `stage_counts`）—— 这份
        与打点无关，故放在最前（`DOMAINS_EXHAUSTED` 不在时间线配色里，放后面就漏了）。
        """
        f = int(frame)
        with self.lock:
            # 世代更迭的三档名字：`renewal.mode` 落进覆盖表那一刻起叫「主动更替」；
            # 「再创世」要跨过 `DOMAINS_EXHAUSTED`（第四阶段）—— 见 advance_label。
            if kind == "PROTOCOL_REWRITTEN" and self.switch is None \
                    and "renewal.mode" in (payload.get("changed") or {}):
                self.switch = f
            # 阶段边界 / 读数：与 `render.stage_table` 同一套口径（换档帧 · 涌现 · 换代 · 陨落）
            if kind in ("DOMAIN_ADVANCE", "DOMAINS_EXHAUSTED"):
                if self.mythfrom is None and kind == "DOMAINS_EXHAUSTED":
                    self.mythfrom = f           # 世界内起点（看板据此切语汇）
                if kind == "DOMAINS_EXHAUSTED":
                    self.exhausted = True
                    # 让这条 R 也跟上「演算期 ⇄ 世界内」：`advance_label` 要靠
                    # `R.phase_of(frame)` 才分得出第三阶段的「主动更替」与第四阶段的「再创世」。
                    R.add_myth_from(f)
                self.stage_starts.append(f)
                self.stage_counts.append([0, 0, 0])
            elif kind == "EMERGENCE" and self.stage_starts:
                self.stage_counts[_stage_at(self.stage_starts, f)][0] += 1
            elif kind == "PROMOTION" and self.stage_starts:
                i = _stage_at(self.stage_starts, f)
                self.stage_counts[i][1] += 1
                cur = int((payload.get("burden") or {}).get("fell", self._seen_fell))
                self.stage_counts[i][2] += max(0, cur - self._seen_fell)   # 累加值 ⇒ 取差
                self._seen_fell = max(self._seen_fell, cur)
            if kind not in _TIMELINE_COLORS:
                return
            n = self._seen_kind.get(kind, 0) + 1
            self._seen_kind[kind] = n
            if n > per_kind:
                return
            self.marks.append([f, kind,
                               _event_label(R, kind, payload, f, self.switch),
                               _TIMELINE_COLORS[kind], int(rid)])
            if kind == "PROMOTION":
                self.promos.append([f, int(payload.get("round", 0))])

    def finish(self, traj, cards, verdict_label=None):
        with self.lock:
            self.frame = int(traj.reached_frame)
            self.done = True
            self.verdict = verdict_label or traj.verdict
            self.cards = cards

    def set_final_page(self, html):
        """演算结束、完整静态页备好后调用 —— 此后 `/` 一律提供这一份。

        它由 `run.py` 用与 `--export` 完全相同的那次 `build_html(...)` 生成，故页面
        重载后与导出的单文件逐字一致；不依赖导出文件是否落盘。
        """
        with self.lock:
            self.final_page = html

    # ---- 服务侧 ----------------------------------------------------------
    def _stage_view(self):
        """阶段目录（时间线用的轻量列表 + 预渲染 HTML）。没给 ctx/data 时给空。"""
        if self.ctx is None or self.data is None or not self.stage_starts:
            return [], ""
        rows = stage_rows(
            self.ctx, self.data,
            starts=self.stage_starts,
            born=[c[0] for c in self.stage_counts],
            prom=[c[1] for c in self.stage_counts],
            fell=[c[2] for c in self.stage_counts],
            reached_frame=self.frame, exhausted=self.exhausted,
            switch=self.switch, myth_from=self.mythfrom)
        light = [{"name": r["name"], "start": r["start"], "end": r["end"]}
                 for r in rows]
        return light, _stages_html(rows)

    def snapshot(self, rows_since, samples_since, names_since):
        with self.lock:
            stages, stages_html = self._stage_view()
            out = {
                "frame": self.frame,
                "done": self.done,
                "verdict": self.verdict,
                "cards": self.cards,
                # 增量三样：编年史行、采样点、名字表
                "rows": self.rows[rows_since:rows_since + _MAX_CHUNK],
                "samples": self.samples[samples_since:samples_since + _MAX_CHUNK],
                "seatnames": self.seatnames[names_since:],
                # 与 seatnames **同下标、同步长**的机器编号表（席位卡悬浮用）
                "machines": self.machines[names_since:],
                # 打点与换代刻度很小，每次全量给，客户端整份替换即可
                "marks": list(self.marks),
                "promos": list(self.promos),
                # 换档帧：看板据此在【演算期 ⇄ 世界内】两套语汇之间切（席卡尤其）
                "mythfrom": self.mythfrom,
                # 阶段目录：边界 + 读数（边跑边累计）—— 列表给时间线的阶段带，HTML 给卡片块
                "stages": stages,
                "stageshtml": stages_html,
                # 完整静态页是否已就绪：就绪即触发页面重载（换成与 export 一致的那张）
                "final": self.final_page is not None,
            }
        return out


def _handler_factory(state: LiveState, page: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body: bytes, ctype: str):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") in ("/state",):
                q = parse_qs(parsed.query)
                pick = lambda k: int((q.get(k) or ["0"])[0] or 0)
                data = state.snapshot(pick("rows"), pick("samples"), pick("names"))
                body = json.dumps(data, ensure_ascii=False,
                                  separators=(",", ":")).replace("</", "<\\/")
                self._send(body.encode("utf-8"), "application/json; charset=utf-8")
            else:
                # 演算跑完后服务端已备好完整静态页（与 --export 同一份）⇒ 此后 `/`
                # 就返回它；页面检测到快照里的 `final` 会重载，于是与导出的单文件逐字一致。
                body = state.final_page or page
                self._send(body.encode("utf-8"), "text/html; charset=utf-8")

        def log_message(self, *args):        # 别把终端刷成一堵墙
            pass

    return Handler


def serve(state: LiveState, page: str, host="127.0.0.1", port=8765,
          open_browser=True):
    """在后台线程起服务器。返回 (server, url)。"""
    httpd = ThreadingHTTPServer((host, int(port)), _handler_factory(state, page))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    return httpd, url


def make_watch(state: LiveState, sampler: Sampler):
    """把采样器与实时状态接在一起，得到一个可以交给 run(watch=...) 的钩子。

    只读：返回值恒 True（从不剪枝），故加了它与不加，演算逐帧一致。
    名字解析带缓存：涌现者名单只在人数变化时重建（否则每采一个点都要摊一遍全名单）。
    """
    cache = {"n": -1, "names": {}, "machines": {}}

    def resolve(traj, serial):
        if serial is None:
            return None
        if len(traj.personas) != cache["n"]:
            cache["names"] = _name_map(traj)
            cache["machines"] = _machine_map(traj)
            cache["n"] = len(traj.personas)
        return (_resolve(traj, cache["names"], serial),
                _machine_of(traj, cache["machines"], serial))

    def watch(frame, st, traj):
        before = len(sampler.points)
        sampler(frame, st, traj)
        if len(sampler.points) > before:
            state.add_point(sampler.points[-1], lambda s: resolve(traj, s))
        else:
            with state.lock:
                state.frame = max(state.frame, int(frame))
        return True

    return watch
