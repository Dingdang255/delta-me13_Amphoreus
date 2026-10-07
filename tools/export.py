#!/usr/bin/env python3
"""把 δ-me13「翁法罗斯」演算引擎打包成一个可直接分发的 zip。

    python3 tools/export.py                  # 打包到 dist/Amphoreus-<日期>.zip
    python3 tools/export.py --check-only     # 只做依赖自检，不打包
    python3 tools/export.py --dry-run        # 只列出会被打进包的文件
    python3 tools/export.py -o /tmp/out.zip  # 指定输出路径
    python3 tools/export.py --exclude-tools  # 不打包 tools/
    python3 tools/export.py --no-verify      # 跳过打包后的「解压即可用」自检

打包内容 = 仓库里【运行与自检所必需】的那部分：
  run.py / README.md / LICENSE / requirements.txt / pyproject.toml
  engine/ / config/ / presets/ / tools/ / tests/
  以及 docs/ 里真正被用到的那几份（见 DOCS_FILES，不整目录打包）
自动剔除 __pycache__、*.pyc、dist/、.trae/ 与演算产物（编年史 .txt、可视化 .html）。
LICENSE（MIT）必须随包 —— 许可条款要求「版权声明与许可声明须随所有副本或实质部分
一并给出」，故它不只是仓库文件，也是分发包的一部分。

docs/ 只挑必需的那几份 —— 目录里还有给 AI 用的参考料（wiki 抓取、散文考据），
它们不是分发包的一部分：
  * docs/外部变量.json  tests/test_actors_spec.py 与 tools/actors_from_spec.py 要它
  * docs/术语对照表.md  tests/test_lexicon_table.py 与 README 要它
  * docs/使用教程.md    README 的「第一次来？」指向它
  * docs/外部变量.md    使用教程.md 里链到它（免得包内文档自己断链）

自检分两层：
  1) 依赖自检   —— 本机是否具备运行所需的 Python 与第三方库（默认执行）。
  2) 打包后自检 —— 解压到临时目录，用独立解释器导入 engine 并装载一次
                   config/data、跑一小段演算，再跑一遍依赖 docs 的那几个单测，
                   证明「下载解压即可用」。
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 运行所需的 Python 版本下限（与 __pycache__ 里的 3.10 对齐） ------------
PY_MIN = (3, 10)

# ---- 打包清单 ---------------------------------------------------------------
# LICENSE 也在包内：MIT 要求「版权声明与许可声明须随所有副本或实质部分一并给出」，
# 故分发包必须带它，不能只留在仓库里（见模块开头的打包说明）。
TOP_FILES = ["run.py", "README.md", "requirements.txt", "pyproject.toml", "LICENSE"]
# tests/ 也进包：tools/selfcheck.py 会跑单测，缺了它「解压即可自检」就不成立。
TOP_DIRS = ["engine", "config", "presets", "tools", "tests"]

# docs/ 不整目录打包 —— 里面还有给 AI 用的参考料（wiki 抓取、散文考据），
# 不进分发包。这里只列【运行与自检真正用到】的那几份（见模块开头说明）。
DOCS_FILES = ["docs/外部变量.json", "docs/术语对照表.md",
              "docs/使用教程.md", "docs/外部变量.md"]

EXCLUDE_DIRS = {"__pycache__", ".trae", ".git", ".idea", ".vscode", "dist"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".zip")
# 根目录的演算产物（编年史导出 / 可视化 dashboard）不是源码，不进包。
EXCLUDE_RE = re.compile(r"(翁法罗斯编年史.*\.txt|翁法罗斯-可视化.*\.html)$")


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0


# ---- 依赖自检 ---------------------------------------------------------------

def parse_requirements(path):
    """把 requirements.txt 读成 [(名字, 版本约束), ...]。支持 `#` 注释与空行。"""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", line)
            if m:
                out.append((m.group(1), m.group(2).strip()))
    return out


def _ver_tuple(s):
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3]) or (0,)


def _satisfies(version, spec):
    """极简版本比对：只处理 >= <= == != > < 与逗号并列，够 requirements.txt 用。"""
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        for op in (">=", "<=", "==", "!=", ">", "<"):
            if part.startswith(op):
                got, want = _ver_tuple(version), _ver_tuple(part[len(op):])
                ok = {">=": got >= want, "<=": got <= want, "==": got == want,
                      "!=": got != want, ">": got > want, "<": got < want}[op]
                if not ok:
                    return False
                break
    return True


def check_deps(requirements):
    """返回 [(名称, 是否通过, 说明), ...]。"""
    results = []
    ok = sys.version_info >= PY_MIN
    results.append((f"Python >= {'.'.join(map(str, PY_MIN))}", ok,
                    "本机 " + sys.version.split()[0]))

    import importlib.metadata as md
    import importlib.util
    for name, spec in requirements:
        try:
            found = importlib.util.find_spec(name.replace("-", "_")) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            results.append((name, False, f"未安装（需要 {spec or '任意版本'}）"))
            continue
        try:
            ver = md.version(name)
        except md.PackageNotFoundError:
            results.append((name, True, "已安装（版本未知）"))
            continue
        good = _satisfies(ver, spec) if spec else True
        results.append((name, good, f"已安装 {ver}" + (f"，要求 {spec}" if spec else "")))
    return results


def print_deps(results) -> bool:
    print("【依赖自检】")
    for name, ok, msg in results:
        print(f"  [{'√' if ok else '×'}] {name:<22} {msg}")
    allok = all(r[1] for r in results)
    print("  → " + ("环境就绪" if allok else "环境不满足运行要求"))
    return allok


# ---- 收集与打包 -------------------------------------------------------------

def collect(include_tools=True):
    """列出要打进包的绝对路径（已应用排除规则）。"""
    dirs = list(TOP_DIRS) if include_tools else [d for d in TOP_DIRS if d != "tools"]

    files = []
    for name in TOP_FILES:
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            files.append(p)
    for rel in DOCS_FILES:                     # docs/ 只挑必需的那几份
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            files.append(p)
    for d in dirs:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(EXCLUDE_SUFFIX) or EXCLUDE_RE.search(fn):
                    continue
                files.append(os.path.join(dirpath, fn))
    return sorted(set(files))


def build_zip(files, out_path, root_name):
    """写 zip。包内统一以 root_name/ 为顶层目录，路径分隔符用 `/`。"""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc = root_name + "/" + os.path.relpath(p, ROOT).replace(os.sep, "/")
            z.write(p, arc)
    return out_path


# ---- 打包后自检 -------------------------------------------------------------

SMOKE = """\
import sys
from engine.loader import Config, DataSet
from engine.core import run
from engine.conditions import evaluate
from engine.services import default as default_services
data = DataSet('.', preset='plot')
cfg = Config('.')
traj = run(cfg, data, max_frames=128, rules=evaluate, runtime=default_services())
print('SMOKE_OK', len(cfg.loci), traj.verdict)
"""

# 依赖 docs/ 的那几个单测：文档没打进包，这几条必红 —— 拿它们当「docs 齐不齐」的探针。
DOCTESTS = """\
import sys, unittest
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for pat in ('test_actors_spec.py', 'test_lexicon_table.py'):
    suite.addTests(loader.discover('tests', pattern=pat))
res = unittest.TextTestRunner(verbosity=0).run(suite)
print('DOCTESTS_%s %d' % ('OK' if res.wasSuccessful() else 'FAIL', res.testsRun))
sys.exit(0 if res.wasSuccessful() else 1)
"""


def _run_in(base, filename, source, tag, timeout=300):
    """把一段脚本落到解压目录里跑一次，返回 (是否通过, 说明)。"""
    path = os.path.join(base, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)
    try:
        proc = subprocess.run([sys.executable, os.path.abspath(path)],
                              cwd=base, capture_output=True, text=True,
                              timeout=timeout)
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except Exception as exc:  # 超时 / 启动失败
        rc, out, err = 1, "", str(exc)
    finally:
        os.remove(path)
    if rc != 0 or tag not in out:
        return False, (err.strip() or out.strip() or "无输出")
    return True, out.strip().splitlines()[-1]


def verify_zip(zip_path, root_name):
    """解压到临时目录，用独立解释器校验：文件齐、能导入、能装载、能跑一小段、docs 齐。"""
    print("【打包后自检】")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad is not None:
                print(f"  [×] zip 损坏于 {bad}")
                return False
            names = set(z.namelist())
            z.extractall(tmp)
        base = os.path.join(tmp, root_name)

        # 关键文件清单：engine/config/presets 是运行必需，docs/ 那几份是【自检与文档链接必需】。
        need = ["run.py", "README.md", "requirements.txt",
                "engine/loader.py", "config/params.json",
                "presets/_default/genesis.json",
                "docs/外部变量.json", "docs/术语对照表.md",
                "docs/使用教程.md", "docs/外部变量.md"]
        missing = [n for n in need if f"{root_name}/{n}" not in names]
        if missing:
            print("  [×] 缺关键文件：" + "、".join(missing))
            return False
        print(f"  [√] zip 完整，含 {len(names)} 个条目（顶层 {root_name}/），"
              f"docs/ 该带的都带了")

        ok, info = _run_in(base, "__smoke__.py", SMOKE, "SMOKE_OK")
        if not ok:
            print("  [×] 解压后无法运行：")
            print("      " + info)
            return False
        print("  [√] 解压后导入 engine、装载 config/presets 并跑通 128 帧")

        # tools/ 没进包时那两个探针单测也跑不了（它们要 import tools/ 下的生成器），跳过。
        if f"{root_name}/tools/lexicon_table.py" in names:
            ok, info = _run_in(base, "__doctests__.py", DOCTESTS, "DOCTESTS_OK")
            if not ok:
                print("  [×] 依赖 docs/ 的单测未通过：")
                print("      " + info)
                return False
            print("  [√] 依赖 docs/ 的单测通过（考据表与术语表都跟得上）")
    return True


# ---- 入口 -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="把项目打包成可直接分发的 zip")
    ap.add_argument("-o", "--output", default=None, help="输出 zip 路径")
    ap.add_argument("--check-only", action="store_true", help="只做依赖自检，不打包")
    ap.add_argument("--dry-run", action="store_true", help="只列出会被打包的文件")
    ap.add_argument("--exclude-tools", action="store_true", help="不打包 tools/")
    ap.add_argument("--no-check", action="store_true", help="跳过依赖自检")
    ap.add_argument("--no-verify", action="store_true", help="跳过打包后自检")
    args = ap.parse_args()

    requirements = parse_requirements(os.path.join(ROOT, "requirements.txt"))

    deps_ok = True
    if not args.no_check:
        deps_ok = print_deps(check_deps(requirements))
        print()
    if args.check_only:
        return 0 if deps_ok else 1

    files = collect(not args.exclude_tools)
    root_name = os.path.basename(ROOT.rstrip("\\/")) or "Amphoreus"

    if args.dry_run:
        print(f"【打包清单】顶层 {root_name}/ —— 共 {len(files)} 个文件")
        for p in files:
            print("  " + os.path.relpath(p, ROOT).replace(os.sep, "/"))
        return 0

    out_path = args.output or os.path.join(
        ROOT, "dist", f"{root_name}-{datetime.date.today():%Y%m%d}.zip")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    build_zip(files, out_path, root_name)

    size = os.path.getsize(out_path)
    print(f"【已打包】{out_path}")
    print(f"  顶层目录 {root_name}/ · {len(files)} 个文件 · {_human(size)}")
    print()

    if not args.no_verify:
        ok = verify_zip(out_path, root_name)
        print()
        if not ok:
            print("打包后自检未通过 —— 请检查上面的报告。")
            return 1

    if not deps_ok:
        print("注意：本机依赖不满足要求，包虽生成但需在目标机器上补装依赖。")
        return 1
    print("完成：把该 zip 发给别人，解压后按 README.md 安装依赖即可运行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
