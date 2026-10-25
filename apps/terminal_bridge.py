"""主进程与独立 CLI 窗口之间的本地 socket 桥。

它是**只读叙事层**的一部分：只搬运 `>>>` 消息与 `prompt` 的问答，
不写世界状态、不改账本、也不参与内核的剪枝判定。

协议是逐行 JSON（NDJSON），只绑 `127.0.0.1` 的临时端口：

    子窗口 → 主进程   {"t": "ready", "token": "..."}
    主进程 → 子窗口   {"t": "msg", "frame": 1, "kind": "boot", "text": "..."}
    主进程 → 子窗口   {"t": "prompt", "id": 0, "frame": 42001, ...}
    子窗口 → 主进程   {"t": "answer", "id": 0, "answer": "Y"}
    主进程 → 子窗口   {"t": "end", "frame": 33594547, "verdict": "overwritten"}

`prompt` 会阻塞等待回答；超时 / 子窗口关闭 / 连接断开时返回 `None`，
调用方据此回落到默认答案。子窗口不存在时，`start()` 返回 False，主进程
可以退回同控制台模式，演算不受影响。
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time


class TerminalBridge:
    """父进程侧：监听本地端口、拉起子窗口、收发 NDJSON。"""

    def __init__(self, timeout=60.0, ready_timeout=10.0, host="127.0.0.1",
                 token=None, spawn=None):
        self.timeout = float(timeout)
        self.ready_timeout = float(ready_timeout)
        self.host = str(host)
        self.token = token or os.urandom(12).hex()
        self._spawn = spawn
        self._srv = None
        self._conn = None
        self._rf = None
        self._wf = None
        self._proc = None
        self._reader = None
        self._inbox = queue.Queue()
        self._closed = False
        self._ended = False
        self.port = None

    # ---- 生命周期 -----------------------------------------------------------
    def start(self, root=None) -> bool:
        """建监听、拉起子窗口、等 `ready`。成功返回 True；失败时已清理干净。"""
        if self._closed:
            return False
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, 0))
            srv.listen(1)
            srv.settimeout(self.ready_timeout)
        except OSError:
            return False
        self._srv = srv
        self.port = int(srv.getsockname()[1])

        try:
            self._proc = (self._spawn(self.port, self.token) if self._spawn
                          else self._spawn_default(root))
        except OSError:
            self._proc = None
        if self._proc is None:
            self.close()
            return False

        try:
            conn, _ = srv.accept()
        except OSError:
            self.close()
            return False
        conn.settimeout(None)
        self._conn = conn
        try:
            self._rf = conn.makefile("r", encoding="utf-8", newline="\n")
            self._wf = conn.makefile("w", encoding="utf-8", newline="\n")
        except OSError:
            self.close()
            return False

        self._reader = threading.Thread(target=self._read_loop, args=(self._rf,),
                                        daemon=True)
        self._reader.start()
        try:
            ready = self._inbox.get(timeout=self.ready_timeout)
        except queue.Empty:
            self.close()
            return False
        if ready.get("t") != "ready" or ready.get("token") != self.token:
            self.close()
            return False
        return True

    def close(self):
        """幂等收尾：补发 `end`、关连接、等子进程退出（超时则终止）。"""
        if self._closed:
            return
        if self._conn is not None and not self._ended:
            try:
                self._send({"t": "end"})
                self._ended = True
            except OSError:
                pass
        self._closed = True
        for f in (self._wf, self._rf):
            try:
                if f is not None:
                    f.close()
            except OSError:
                pass
        for s in (self._conn, self._srv):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass
        if self._proc is not None:
            try:
                self._proc.wait(timeout=2)
            except (subprocess.TimeoutExpired, AttributeError):
                try:
                    self._proc.terminate()
                except (OSError, AttributeError):
                    pass

    # ---- 发消息 -------------------------------------------------------------
    def msg(self, record):
        """一条 `>>>` 消息；连接不在时静默丢弃（只读层，不制造异常）。"""
        rec = dict(record or {})
        rec.pop("t", None)
        rec["t"] = "msg"
        self._send(rec)

    def prompt(self, record):
        """发 `prompt` 并阻塞等回答；超时 / 断连 / 非法回答返回 None。"""
        rec = dict(record or {})
        rec.pop("t", None)
        rec["t"] = "prompt"
        pid = rec.get("id")
        if not self._send(rec):
            return None
        deadline = time.monotonic() + self.timeout
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None
            try:
                obj = self._inbox.get(timeout=remain)
            except queue.Empty:
                return None
            if obj.get("t") == "eof":
                return None
            if obj.get("t") == "answer" and obj.get("id") == pid:
                answer = obj.get("answer")
                return None if answer is None else str(answer)
            # 其它消息（迟到的 answer / error）一律忽略。

    def end(self, frame, verdict=None):
        """通知子窗口演算结束；幂等。"""
        if self._ended or self._closed:
            return
        self._send({"t": "end", "frame": int(frame),
                    "verdict": None if verdict is None else str(verdict)})
        self._ended = True

    # ---- 内部 ---------------------------------------------------------------
    def _send(self, obj) -> bool:
        if self._wf is None or self._closed:
            return False
        try:
            self._wf.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._wf.flush()
            return True
        except (OSError, ValueError):
            return False

    def _read_loop(self, f):
        try:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    self._inbox.put(obj)
        except (OSError, ValueError):
            pass
        finally:
            self._inbox.put({"t": "eof"})

    def _spawn_default(self, root):
        """拉起子窗口：Windows 新控制台；POSIX 尝试常见终端模拟器。"""
        root = root or os.getcwd()
        py = _console_python()
        cmd = [py, "-m", "apps.terminal_window",
               "--port", str(self.port), "--token", self.token]
        env = dict(os.environ)
        env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"]
                                    if env.get("PYTHONPATH") else "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        kwargs = {"cwd": root, "env": env}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess,
                                              "CREATE_NEW_CONSOLE", 0)
            return subprocess.Popen(cmd, **kwargs)
        for exe, sep in (("x-terminal-emulator", ["-e"]),
                         ("gnome-terminal", ["--"]),
                         ("konsole", ["-e"]),
                         ("xterm", ["-e"])):
            if shutil.which(exe):
                return subprocess.Popen([exe, *sep, *cmd], **kwargs)
        return None


def _console_python():
    """`sys.executable` 若是 pythonw.exe，换成同目录的 python.exe（否则没有控制台）。"""
    exe = sys.executable or "python"
    base = os.path.basename(exe).lower()
    if base.startswith("pythonw"):
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(cand):
            return cand
    return exe
