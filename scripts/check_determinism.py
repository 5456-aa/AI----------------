# -*- coding: utf-8 -*-
"""复现性检查：连续跑两次全流程，逐文件比对 md5。

任何一处不一致都会列出来（含行级 diff 摘要），用来定位非确定性来源。

用法：
  python scripts/check_determinism.py            # 跑两次并比对
  python scripts/check_determinism.py --keep     # 保留两次的产物便于排查
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

FILES = ["result1.csv", "result2.csv", "result3.csv", "result4.csv"]


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()[:12] if p.exists() else "MISSING"


def run_once(offline: bool = False) -> None:
    cmd = [sys.executable, str(ROOT / "run_all.py"), "--track", "all",
           "--batch", "DETERMINISM", "--force", "--no-proposal"]
    if offline:
        cmd.append("--offline")
    subprocess.run(cmd,
                   cwd=str(ROOT), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")


def diff_summary(a: Path, b: Path, n: int = 3) -> str:
    if not a.exists() or not b.exists():
        return "（文件缺失）"
    la = a.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    lb = b.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if len(la) != len(lb):
        return f"行数不同：{len(la)} vs {len(lb)}"
    out = []
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            out.append(f"    第 {i+1} 行：\n      A: {x[:110]}\n      B: {y[:110]}")
            if len(out) >= n:
                break
    return "\n".join(out) or "（内容一致）"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--offline", action="store_true", help="强制离线（只用缓存）")
    args = ap.parse_args(argv)

    cfg = load_config(track="all")
    out = Path(cfg["paths"]["out"])
    snap = ROOT / "reports" / "_determinism"
    if snap.exists():
        shutil.rmtree(snap)

    print("[1/3] 第一次运行 …")
    run_once(args.offline)
    snap.mkdir(parents=True, exist_ok=True)
    first = {}
    for f in FILES:
        p = out / f
        first[f] = md5(p)
        if p.exists():
            shutil.copy(p, snap / f"run1_{f}")
        print(f"   {f:12s} md5 {first[f]}")

    print("[2/3] 第二次运行 …")
    run_once(args.offline)
    second = {}
    for f in FILES:
        p = out / f
        second[f] = md5(p)
        if p.exists():
            shutil.copy(p, snap / f"run2_{f}")
        print(f"   {f:12s} md5 {second[f]}")

    print("[3/3] 比对 …")
    bad = []
    for f in FILES:
        if first[f] != second[f]:
            bad.append(f)
            print(f"   ❌ {f} 不一致")
            print(diff_summary(snap / f"run1_{f}", snap / f"run2_{f}"))
        else:
            print(f"   ✅ {f} 完全一致")

    if not bad:
        print("\n结论：✅ 两次运行结果完全一致（在缓存命中前提下可复现）")
        if not args.keep:
            shutil.rmtree(snap)
        return 0

    print(f"\n结论：❌ {len(bad)} 个文件不一致，需排查非确定性来源")
    print("   已保留两次产物：" + str(snap))
    return 1


if __name__ == "__main__":
    sys.exit(main())
