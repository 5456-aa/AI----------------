# -*- coding: utf-8 -*-
"""采集入口（按赛道）。

    python run_collect.py --track ecommerce --source V2EX --keyword programmer
    python run_collect.py --track education --source GitHub --limit 60
    python run_collect.py --track all --max-keywords 3     # 两个赛道都采

产物：data/raw/<track>/<source>.jsonl（原始响应快照另存在 data/raw/<track>/<source>/）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from collectors.base import stable_record_id
from collectors.registry import ENABLED_SOURCES, REGISTRY, SOURCE_NOTES
from io_utils import (TRACKS, ensure_dirs, get_logger, load_config,
                      make_batch_id, write_jsonl)


def collect_one(cfg, log) -> int:
    track = cfg["track"]
    tcfg = cfg.get("_track_cfg") or {}
    sources = tcfg.get("sources") or ENABLED_SOURCES
    keywords = cfg["collect"].get("keywords") or [cfg["project"]["demand_direction"]]
    prefix = cfg["project"].get("record_prefix", "S")
    batch = cfg.get("_batch") or make_batch_id(cfg)
    limit = cfg["collect"].get("max_per_source", 120)

    taken_ids: set[str] = set()
    total = 0          # 赛道内累计条数（仅用于日志）
    for name in sources:
        cls = REGISTRY.get(name)
        if cls is None:
            log.warning("未登记的来源，跳过：%s（说明：%s）", name, SOURCE_NOTES.get(name, ""))
            continue
        log.info("[%s] 采集中：%s（%s）", track, name, SOURCE_NOTES.get(name, ""))
        try:
            collector = cls(cfg, batch=batch)
            records, seen = [], 0
            for kw in keywords:
                got = collector.search(kw, limit=max(1, limit // max(len(keywords), 1)))
                records.extend(got)
                seen += len(got)
                if seen >= limit:
                    break
        except Exception as exc:
            log.error("[%s] 采集失败 %s：%s", track, name, exc)
            continue

        # 记录编号：由内容哈希生成，**同一内容每次重采都是同一个编号**。
        # 这样标注集、阈值标定在重新采集后依然有效（此前用自增序号导致编号错位）。
        # 先按内容去重：同一来源+链接+标题可能被多个检索词命中，
        # 若不去重，重复项会靠哈希碰撞的线性探测拿编号，顺序一变就互换。
        seen_keys: set[tuple] = set()
        uniq = []
        for r in records:
            k = ((r.source or "").strip(), (r.url or "").strip(), (r.title or "").strip())
            if k in seen_keys:
                continue
            seen_keys.add(k)
            uniq.append(r)
        if len(uniq) != len(records):
            log.info("[%s] %s 内容去重：%d -> %d 条", track, name, len(records), len(uniq))
        records = uniq

        # 再按内容排序，保证分配顺序固定
        records.sort(key=lambda r: ((r.source or ""), (r.url or ""), (r.title or "")))
        for rec in records:
            rec.record_id = stable_record_id(prefix, rec.source, rec.url, rec.title, taken_ids)
            taken_ids.add(rec.record_id)
            rec.batch = batch
            rec.extra = dict(rec.extra or {}, track=track)

        path = Path(cfg["paths"]["raw"]) / f"{name.replace(' ', '_')}.jsonl"
        write_jsonl(path, [r.to_dict() for r in records])
        log.info("[%s] %s：%d 条 -> %s", track, name, len(records), path)

    log.info("[%s] 本批次共 %d 条，批次号 %s", track, total, batch)
    return total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="多源采集（按赛道）")
    ap.add_argument("--track", default="ecommerce",
                    help="赛道名或 all（可用 scripts/new_batch.py 新建）")
    ap.add_argument("--source", default=None, help=f"只采某个源：{ENABLED_SOURCES}")
    ap.add_argument("--keyword", default=None, help="覆盖检索词（只采这一个词）")
    ap.add_argument("--max-keywords", type=int, default=None, help="每个源最多用几个检索词")
    ap.add_argument("--limit", type=int, default=None, help="每个源条数上限")
    ap.add_argument("--batch", default=None, help="采集批次号")
    args = ap.parse_args(argv)

    tracks = list(TRACKS) if args.track == "all" else [args.track]
    grand = 0
    for i, track in enumerate(tracks, 1):
        cfg = load_config(track=track)
        ensure_dirs(cfg)
        log = get_logger(cfg, "collect")

        if args.source:
            cfg["_track_cfg"] = dict(cfg.get("_track_cfg") or {}, sources=[args.source])
        if args.keyword:
            cfg["collect"]["keywords"] = [args.keyword]
        if args.max_keywords:
            kws = cfg["collect"].get("keywords") or []
            cfg["collect"]["keywords"] = kws[:args.max_keywords]
        if args.limit:
            cfg["collect"]["max_per_source"] = args.limit

        batch = args.batch or make_batch_id(cfg, seq=i)
        cfg["_batch"] = batch
        grand += collect_one(cfg, log)
    print(f"合计采集 {grand} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
