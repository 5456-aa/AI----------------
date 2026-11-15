# -*- coding: utf-8 -*-
"""把已有数据里的记录编号迁移成「内容哈希」编号，并做幂等性验证。

背景：早期采集按自增序号编号，重采一次编号就全变，标注集失效。
本脚本一次性把 `data/raw/<track>/*.jsonl` 里的 record_id 换成
`stable_record_id(source, url, title)` 的结果。**脚本可重复执行，结果不变**。

用法：
  python scripts/fix_record_ids.py            # 迁移
  python scripts/fix_record_ids.py --check    # 只检查是否会变（不动文件）
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.base import stable_record_id  # noqa: E402
from io_utils import load_config, read_jsonl, write_jsonl  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告会变多少条，不写文件")
    args = ap.parse_args(argv)

    cfg = load_config(track="all")
    raw_root = Path(cfg["base_paths"]["raw"])
    tracks = sorted([d.name for d in raw_root.iterdir() if d.is_dir()]) if raw_root.exists() else []

    total = changed = 0
    for track in tracks:
        tcfg = load_config(track=track)
        prefix = tcfg["project"].get("record_prefix", "S")
        d = raw_root / track
        files = sorted(d.glob("*.jsonl"))
        if not files:
            continue

        taken: set[str] = set()
        per_track = 0
        per_changed = 0
        for f in files:
            recs = read_jsonl(f)
            recs.sort(key=lambda r: ((r.get("source") or ""), (r.get("url") or ""),
                                     (r.get("title") or "")))
            # 同一内容只保留一条，避免重复项靠碰撞探测拿编号（会导致编号漂移）
            uniq, seen = [], set()
            for r in recs:
                k = ((r.get("source") or "").strip(), (r.get("url") or "").strip(),
                     (r.get("title") or "").strip())
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(r)
            if len(uniq) != len(recs):
                print(f"    {f.name}: 内容去重 {len(recs)} -> {len(uniq)}")
            recs = uniq
            for r in recs:
                new = stable_record_id(prefix, r.get("source", ""), r.get("url", ""),
                                       r.get("title", ""), taken)
                taken.add(new)
                per_track += 1
                if r.get("record_id") != new:
                    per_changed += 1
                    r["record_id"] = new
            if not args.check:
                write_jsonl(f, recs)
        total += per_track
        changed += per_changed
        print(f"  {track:12s} 前缀 {prefix}  {per_track:4d} 条，编号变化 {per_changed:4d}")

    print(f"\n合计 {total} 条，编号将变化 {changed} 条"
          + ("（--check 模式，未写文件）" if args.check else "（已写回）"))
    if not args.check:
        print("\n下一步：")
        print("  python run_all.py --track all --batch B20261113-01 --force")
        print("  python scripts/remap_labels.py        # 按内容对齐标注集")
        print("  python scripts/tune_threshold.py --tune data/label/label_set_mapped.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
