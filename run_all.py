# -*- coding: utf-8 -*-
"""一键流水线：清洗 -> 去重 -> 判别 -> 聚类 -> 评估 -> 导出 -> 策划案。

用法（双赛道）：
    python run_all.py --track ecommerce     # 只跑电商赛道 -> data/out/ecommerce/
    python run_all.py --track education     # 只跑教育赛道 -> data/out/education/
    python run_all.py --track all           # 两赛道合并 -> data/out/（最终提交用）

单赛道也支持分段重跑：
    python run_all.py --track education --stage judge
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import io_utils
import security
from export import proposal as proposal_mod, to_csv
from io_utils import (TRACKS, ensure_dirs, get_logger, load_config, read_jsonl,
                      seed_everything, track_cfg, write_jsonl)
from pipeline import clean, cluster as cluster_mod, dedup, judge, score

STAGES = ["clean", "dedup", "judge", "cluster", "score", "export", "proposal"]


def _load(cfg, filename: str, stage: str):
    rows = read_jsonl(Path(cfg["paths"]["clean"]) / filename)
    if not rows:
        raise SystemExit(f"找不到 {cfg['paths']['clean']}/{filename}，请先运行 --stage {stage}")
    return rows


def run_single(cfg, batch: str, stages, args) -> dict:
    """单赛道：在 data/*/<track>/ 下完整跑一遍。"""
    log = get_logger(cfg, "run_all")
    cfg["_batch"] = batch
    log.info("=" * 70)
    log.info("赛道 %s | 方向：%s | 批次 %s", cfg["track"],
             cfg["project"].get("demand_direction"), batch)

    for stage in stages:
        log.info("▶ %s", stage)
        if stage == "clean":
            clean.run(cfg)
        elif stage == "dedup":
            dedup.run(cfg, _load(cfg, "records.jsonl", "clean"))
        elif stage == "judge":
            judge.run(cfg, _load(cfg, "records.jsonl", "clean"))
        elif stage == "cluster":
            try:
                cluster_mod.run(cfg, _load(cfg, "judged.jsonl", "judge"))
            except SystemExit as exc:
                # 机会记录不足（新方向常见）：不终止整条流水线，继续导出空簇
                log.warning("聚类跳过：%s", exc)
                write_jsonl(Path(cfg["paths"]["clean"]) / "clusters.jsonl", [])
                write_jsonl(Path(cfg["paths"]["clean"]) / "cluster_metrics.jsonl", [])
        elif stage == "score":
            cluster_mod_rows = read_jsonl(Path(cfg["paths"]["clean"]) / "clusters.jsonl")
            try:
                score.run(cfg, cluster_mod_rows)
            except SystemExit as exc:
                log.warning("评分跳过：%s", exc)
                write_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl", [])
                write_jsonl(Path(cfg["paths"]["clean"]) / "score_detail.jsonl", [])
        elif stage == "export":
            rows = _load(cfg, "judged.jsonl", "judge")
            clusters = read_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl")
            if not clusters:
                log.warning("本批次未形成主题簇（机会记录不足），result3/result4 输出空表")
            to_csv.export_result1(cfg, rows)
            to_csv.export_result2(cfg, rows)
            to_csv.export_result3(cfg, clusters, batch)
            to_csv.export_result4(cfg, clusters, batch)
        elif stage == "proposal" and not args.no_proposal:
            clusters = read_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl")
            proposal_mod.run(cfg, clusters, top_k=args.top_k,
                             out_dir=io_utils.track_report_dir(cfg, cfg["track"]))
    return {}


def ensure_track_judged(base_cfg, track: str, args) -> list:
    """确保某赛道已有 judged.jsonl；没有就现场跑 clean→dedup→judge。"""
    cfg = track_cfg(base_cfg, track)
    ensure_dirs(cfg)
    log = get_logger(cfg, "run_all")
    judged_path = Path(cfg["paths"]["clean"]) / "judged.jsonl"

    if judged_path.exists() and not args.force:
        rows = read_jsonl(judged_path)
        log.info("[%s] 复用已有 judged.jsonl：%d 条", track, len(rows))
        return rows

    cfg["_batch"] = base_cfg.get("_batch", "")
    log.info("[%s] 没有现成判别结果，现场跑 clean→dedup→judge", track)
    clean.run(cfg)
    dedup.run(cfg, read_jsonl(Path(cfg["paths"]["clean"]) / "records.jsonl"))
    return judge.run(cfg, read_jsonl(Path(cfg["paths"]["clean"]) / "records.jsonl"))


def _merge_audits(base_cfg, log) -> None:
    """把各赛道的清洗/去重审计汇总到合并目录，供 report_audit.py 出总表。"""
    base_clean = Path(base_cfg["paths"]["clean"])
    funnels, aud_clean, aud_dedup = [], [], []

    for track in TRACKS:
        cfg = track_cfg(base_cfg, track)
        d = Path(cfg["paths"]["clean"])
        f = read_jsonl(d / "dedup_funnel.jsonl")
        if f:
            funnels.append(f[0])
        aud_clean.extend(read_jsonl(d / "audit_clean.jsonl"))
        aud_dedup.extend(read_jsonl(d / "audit_dedup.jsonl"))

    if funnels:
        keys = ["raw", "after_L1_url", "after_L2_simhash", "after_L3_semantic",
                "dropped_L1", "dropped_L2", "dropped_L3"]
        agg = {k: sum(f.get(k, 0) for f in funnels) for k in keys}
        agg["dedup_rate"] = round(
            (agg["raw"] - agg["after_L3_semantic"]) / agg["raw"], 4) if agg["raw"] else 0.0
        write_jsonl(base_clean / "dedup_funnel.jsonl", [agg])

    if aud_clean:
        write_jsonl(base_clean / "audit_clean.jsonl", aud_clean)
    if aud_dedup:
        write_jsonl(base_clean / "audit_dedup.jsonl", aud_dedup)
    log.info("审计数据已汇总：%d 个来源", len(aud_clean))


def run_merged(base_cfg, batch: str, args) -> dict:
    """两赛道合并：各自清洗判别后拼成一个批次，再统一聚类/评分/导出。"""
    log = get_logger(base_cfg, "run_all")
    base_cfg["_batch"] = batch
    log.info("=" * 70)
    log.info("合并模式：%s | 批次 %s", " + ".join(TRACKS), batch)

    merged = []
    for track in TRACKS:
        rows = ensure_track_judged(base_cfg, track, args)
        for r in rows:
            r["batch"] = batch          # 提交时同一批次号
            r["track"] = track
        merged.extend(rows)
        log.info("  合并入 %s：%d 条", track, len(rows))

    if not merged:
        raise SystemExit("两个赛道都没有数据。请先运行 run_collect.py 或 scripts/make_demo.py")

    # 记录编号去重保护：万一两赛道前缀撞了，这里补后缀
    seen, fixed = set(), 0
    for r in merged:
        rid = r.get("record_id", "")
        if rid in seen:
            r["record_id"] = f"{rid}-{fixed:02d}"
            fixed += 1
        seen.add(r["record_id"])
    log.info("合并后共 %d 条（补编号 %d 个）", len(merged), fixed)

    write_jsonl(Path(base_cfg["paths"]["clean"]) / "judged.jsonl", merged)
    _merge_audits(base_cfg, log)

    # 分赛道聚类：两个需求方向语义差异大，混在一起会把簇稀释成「电商 / 教育」两个大块。
    # 合并后的簇再统一评分与排序（价值分基于计数类指标，跨赛道可比）。
    log.info("▶ cluster（分赛道各自聚类，再合并）")
    all_clusters, metrics_rows = [], []
    for track in TRACKS:
        tcfg = track_cfg(base_cfg, track)
        rows = [r for r in merged if r.get("track") == track]
        if len([r for r in rows if r.get("is_opportunity") == 1]) < 2:
            log.warning("[%s] 机会记录不足 2 条，跳过聚类", track)
            continue
        res = cluster_mod.run(tcfg, rows)
        for c in res["clusters"]:
            c["track"] = track
            all_clusters.append(c)
        if res.get("metrics"):
            metrics_rows.append(dict(res["metrics"], track=track))
        log.info("  %s：%d 个簇", track, len(res["clusters"]))

    for i, c in enumerate(all_clusters, 1):
        c["cluster_id"] = f"C{i}"
    write_jsonl(Path(base_cfg["paths"]["clean"]) / "clusters.jsonl", all_clusters)
    write_jsonl(Path(base_cfg["paths"]["clean"]) / "cluster_metrics.jsonl", metrics_rows)

    log.info("▶ score")
    score.run(base_cfg, all_clusters)

    log.info("▶ export")
    clusters = read_jsonl(Path(base_cfg["paths"]["clean"]) / "scored.jsonl")
    to_csv.export_result1(base_cfg, merged)
    to_csv.export_result2(base_cfg, merged)
    to_csv.export_result3(base_cfg, clusters, batch)
    to_csv.export_result4(base_cfg, clusters, batch)

    if not args.no_proposal:
        clusters = read_jsonl(Path(base_cfg["paths"]["clean"]) / "scored.jsonl")
        proposal_mod.run(base_cfg, clusters, top_k=args.top_k,
                         out_dir=io_utils.track_report_dir(base_cfg, "all"))
    return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AI 应用场景机会评估系统 - 全流程（双赛道）")
    ap.add_argument("--track", default="all", help="赛道名或 all（可用 scripts/new_batch.py 新建）")
    ap.add_argument("--stage", default="all", choices=["all"] + STAGES)
    ap.add_argument("--batch", default=None)
    ap.add_argument("--force", action="store_true", help="合并模式下强制重跑各赛道的清洗判别")
    ap.add_argument("--no-proposal", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="只用缓存、不调用 API（复现提交结果时用）")
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args(argv)
    seed_everything()
    if args.offline:
        import os
        os.environ["LLM_OFFLINE"] = "1"

    # 熔断自检：发现明文密钥就立刻停下（只扫项目目录，不碰 DSH 凭据）
    security.assert_clean("run_all 全流程")

    t0 = time.time()
    base_cfg = load_config(track="all")
    ensure_dirs(base_cfg)
    batch = args.batch or io_utils.make_batch_id(base_cfg)

    if args.track == "all":
        run_merged(base_cfg, batch, args)
    else:
        cfg = load_config(track=args.track)
        ensure_dirs(cfg)
        stages = STAGES if args.stage == "all" else [args.stage]
        run_single(cfg, batch, stages, args)

    get_logger(base_cfg, "run_all").info("完成，用时 %.1fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
