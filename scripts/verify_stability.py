# -*- coding: utf-8 -*-
"""稳定性验证：证明「同一内容 → 同一记录编号」，重采不会让编号漂移。

做法：
  1. 记录当前 data/raw/<track> 的（来源+链接+标题 → 记录编号）映射；
  2. 重新采集一次到临时目录；
  3. 比对：同内容编号是否一致、有多少新增/消失；
  4. 恢复原数据（不改动工作区）。

用法：python scripts/verify_stability.py --track ecommerce --limit 60
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass


def key(r: dict) -> tuple:
    return ((r.get("source") or "").strip(),
            (r.get("url") or "").strip(),
            (r.get("title") or "").strip())


def mapping(files: list[Path]) -> dict[tuple, str]:
    out = {}
    for f in files:
        for r in read_jsonl(f):
            out[key(r)] = r.get("record_id", "")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="ecommerce")
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args(argv)

    cfg = load_config(track=args.track)
    raw_dir = Path(cfg["paths"]["raw"])
    before_dir = raw_dir.parent / f"_{args.track}_before"

    if before_dir.exists():
        shutil.rmtree(before_dir)
    shutil.copytree(raw_dir, before_dir)
    before = mapping(sorted(before_dir.glob("*.jsonl")))
    print(f"[1/4] 快照：{len(before)} 条（{args.track}）")

    print(f"[2/4] 重新采集（limit={args.limit}）…")
    subprocess.run([sys.executable, str(ROOT / "run_collect.py"),
                    "--track", args.track, "--limit", str(args.limit)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    after = mapping(sorted(raw_dir.glob("*.jsonl")))
    print(f"       采集到 {len(after)} 条")

    print("[3/4] 比对编号…")
    common = set(before) & set(after)
    same = sum(1 for k in common if before[k] == after[k])
    diff = [k for k in common if before[k] != after[k]]
    new = len(set(after) - set(before))
    gone = len(set(before) - set(after))

    print(f"       重叠内容 {len(common)} 条")
    print(f"       编号一致 {same} 条（{same / max(len(common),1) * 100:.1f}%）")
    print(f"       编号不一致 {len(diff)} 条")
    print(f"       新增 {new} 条 / 消失 {gone} 条（正常，渠道内容在变）")
    if diff[:3]:
        print("       不一致样例：")
        for k in diff[:3]:
            print(f"         {k[2][:40]}  {before[k]} -> {after[k]}")

    print("[4/4] 恢复原数据…")
    shutil.rmtree(raw_dir)
    shutil.copytree(before_dir, raw_dir)
    shutil.rmtree(before_dir)

    ok = len(diff) == 0 and len(common) > 0
    print("\n结论：" + ("✅ 通过 —— 同一内容编号稳定，重采不影响标注集"
                      if ok else "❌ 未通过 —— 存在编号漂移，需检查 stable_record_id"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
