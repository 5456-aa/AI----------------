# -*- coding: utf-8 -*-
"""一键生成论文用的全部图（figs/*.png）。

用法：python scripts/make_figures.py
前提：先跑过 python run_all.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200


def _save(fig, name: str, out_dir: Path) -> None:
    fig.tight_layout()
    path = out_dir / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"图 -> {path}")


def fig_funnel(cfg, out_dir):
    rows = read_jsonl(Path(cfg["paths"]["clean"]) / "dedup_funnel.jsonl")
    if not rows:
        print("跳过漏斗图：没有 dedup_funnel.jsonl")
        return
    f = rows[0]
    labels = ["原始采集", "L1 URL去重", "L2 SimHash", "L3 语义去重"]
    values = [f["raw"], f["after_L1_url"], f["after_L2_simhash"], f["after_L3_semantic"]]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    bars = ax.barh(labels[::-1], values[::-1], color="#4C78A8")
    for b, v in zip(bars, values[::-1]):
        ax.text(b.get_width() + max(values) * 0.01, b.get_y() + b.get_height() / 2,
                str(v), va="center", fontsize=10)
    ax.set_xlabel("记录数")
    ax.set_title("清洗与去重漏斗")
    _save(fig, "fig_clean_funnel.png", out_dir)


def fig_sources(cfg, out_dir):
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    if not judged:
        print("跳过来源图：没有 judged.jsonl")
        return
    df = pd.DataFrame(judged)
    counts = df["source"].value_counts()
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    ax.barh(counts.index[::-1], counts.values[::-1], color="#59A14F")
    ax.set_xlabel("记录数")
    ax.set_title("各来源记录分布")
    _save(fig, "fig_source_dist.png", out_dir)

    # 各来源机会率
    rate = df.groupby("source")["is_opportunity"].mean().sort_values()
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.barh(rate.index, rate.values * 100, color="#F28E2B")
    ax.set_xlabel("机会率 (%)")
    ax.set_title("各来源机会率对比")
    _save(fig, "fig_source_opp_rate.png", out_dir)


def fig_cluster_sweep(cfg, out_dir):
    rows = read_jsonl(Path(cfg["paths"]["clean"]) / "cluster_metrics.jsonl")
    if not rows or not rows[0].get("k_sweep"):
        print("跳过 k 扫描图")
        return
    sweep = pd.DataFrame(rows[0]["k_sweep"])
    fig, ax1 = plt.subplots(figsize=(5.6, 3.6))
    ax1.plot(sweep["k"], sweep["silhouette"], marker="o", color="#4C78A8", label="轮廓系数")
    sel = sweep[sweep.get("selected", False) == True]  # noqa: E712
    if not sel.empty:
        ax1.scatter(sel["k"], sel["silhouette"], s=90, color="crimson", zorder=5,
                    label="选中 k")
    ax1.set_xlabel("簇数 k")
    ax1.set_ylabel("Silhouette")
    ax1.set_title("聚类 k 选择（轮廓系数）")
    ax1.grid(alpha=0.3)
    ax1.legend()
    _save(fig, "fig_cluster_k_sweep.png", out_dir)


def fig_ranking(cfg, out_dir):
    clusters = read_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl")
    if not clusters:
        print("跳过排名图")
        return
    df = pd.DataFrame(clusters).sort_values("priority")
    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    ax.barh(df["topic_name"][::-1], df["value_score"][::-1], color="#B07AA1")
    for i, (v, p) in enumerate(zip(df["value_score"][::-1], df["priority"][::-1])):
        ax.text(v + 0.8, i, f"{v:.1f}（P{p}）", va="center", fontsize=8)
    ax.set_xlabel("簇机会价值分")
    ax.set_title("主题簇价值分与优先级")
    ax.set_xlim(0, max(df["value_score"]) * 1.25)
    _save(fig, "fig_value_ranking.png", out_dir)


def fig_dims(cfg, out_dir):
    clusters = read_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl")
    if not clusters or "dim_scores" not in clusters[0]:
        print("跳过雷达图")
        return
    dims = list(clusters[0]["dim_scores"].keys())
    top = sorted(clusters, key=lambda c: c["priority"])[:5]

    angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(4.8, 4.4), subplot_kw=dict(polar=True))
    for c in top:
        vals = [c["dim_scores"][d] for d in dims]
        vals += vals[:1]
        ax.plot(angles, vals, lw=1.4, label=f"{c['cluster_id']} {c['topic_name']}")
        ax.fill(angles, vals, alpha=0.08)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dims, fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_title("Top-5 主题簇维度得分", pad=14)
    ax.legend(fontsize=7, loc="lower right", bbox_to_anchor=(1.15, -0.1))
    _save(fig, "fig_dim_radar.png", out_dir)


def fig_score_matrix(cfg, out_dir):
    detail = read_jsonl(Path(cfg["paths"]["clean"]) / "score_detail.jsonl")
    if not detail or not detail[0].get("dim_matrix"):
        print("跳过得分矩阵")
        return
    M = np.array(detail[0]["dim_matrix"])
    clusters = read_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl")
    try:
        from pipeline.score import raw_dimensions
        dims = raw_dimensions(clusters)[1]
    except Exception:
        dims = [f"dim{i}" for i in range(M.shape[1])]

    fig, ax = plt.subplots(figsize=(4.6, 0.42 * M.shape[0] + 1.6))
    im = ax.imshow(M, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(dims)))
    ax.set_xticklabels(dims, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(M.shape[0]))
    ax.set_yticklabels([c["cluster_id"] for c in sorted(clusters, key=lambda x: x["priority"])],
                       fontsize=8)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.0f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("主题簇维度得分矩阵（0~100）")
    _save(fig, "fig_score_matrix.png", out_dir)


def main(argv=None) -> None:
    import argparse

    from io_utils import TRACKS

    ap = argparse.ArgumentParser(description="生成论文图")
    ap.add_argument("--track", default="all", help="赛道名或 all")
    args = ap.parse_args(argv)

    cfg = load_config(track=args.track)
    out_dir = Path(cfg["base_paths"]["figs"]) / args.track
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"-> {out_dir}")
    for fn in (fig_funnel, fig_sources, fig_cluster_sweep,
               fig_ranking, fig_dims, fig_score_matrix):
        try:
            fn(cfg, out_dir)
        except Exception as exc:
            print(f"[{fn.__name__}] 失败：{exc}")


if __name__ == "__main__":
    main()
