# -*- coding: utf-8 -*-
"""补充论文配图：把还停留在表格里的分析全部画成图。

生成：
  fig_ablation.png        消融对比（规则 vs 规则+LLM）
  fig_confusion.png       最优阈值下的混淆矩阵
  fig_source_status.png   手册 20 个来源的可用性
  fig_batch_compare.png   四个需求方向的批次对比
  fig_weight_compare.png  熵权 / AHP / 组合权重对比
  fig_cluster_sizes.png   各主题簇的记录数与价值分

用法：python scripts/make_more_figures.py
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200

OUT = ROOT / "figs" / "all"
BLUE, ORANGE, GREEN, RED, GREY = "#4C78A8", "#F28E2B", "#59A14F", "#E15759", "#9E9E9E"


def eval_labels() -> dict[str, int]:
    """优先用重映射后的标注（编号与当前批次一致），否则退回标注表。"""
    mapped = ROOT / "data" / "label" / "label_set_mapped.csv"
    if mapped.exists():
        out = {}
        for r in rows(mapped):
            lab = (r.get("label") or "").strip()
            rid = (r.get("记录编号") or "").strip()
            if rid and lab in ("0", "1"):
                out[rid] = int(lab)
        if out:
            return out
    try:
        from scripts.tune_threshold import _read_labels
        return _read_labels(ROOT / "data" / "label" / "人工标注表.xlsx")
    except Exception:
        return {}


def rows(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with io.open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)
    print(f"  图 -> {name}")


# ---------------------------------------------------------------------------
def fig_ablation(cfg) -> None:
    """规则单用 vs 规则+大模型：与 scripts/ablation.py 完全同一口径。"""
    from pipeline.judge import combine, rule_features

    tau = float(cfg["judge"]["threshold"])
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    labels = eval_labels()
    if not judged or len(labels) < 20:
        print("  跳过消融图：数据或标注不足")
        return

    rule_conf, llm_conf = {}, {}
    for r in judged:
        feats = rule_features(r.get("clean_text", ""))
        rule_conf[r["record_id"]] = combine(feats, feats.get("exclude", "none"), cfg)
        llm_conf[r["record_id"]] = float(r.get("confidence", 0))

    ids = [i for i in labels if i in llm_conf]
    if len(ids) < 20:
        print("  跳过消融图：可对齐标注不足")
        return

    def prf(pred):
        y = [labels[i] for i in ids]
        tp = sum(1 for p, t in zip(pred, y) if p == 1 and t == 1)
        fp = sum(1 for p, t in zip(pred, y) if p == 1 and t == 0)
        fn = sum(1 for p, t in zip(pred, y) if p == 0 and t == 1)
        P = tp / (tp + fp) if tp + fp else 0
        R = tp / (tp + fn) if tp + fn else 0
        return P, R, (2 * P * R / (P + R) if P + R else 0)

    rule_prf = prf([1 if rule_conf[i] >= tau else 0 for i in ids])
    llm_prf = prf([1 if llm_conf[i] >= tau else 0 for i in ids])

    methods = ["仅规则特征", f"规则+大模型（τ={tau}）"]
    data = [rule_prf, llm_prf]
    P = [d[0] for d in data]; R = [d[1] for d in data]; F = [d[2] for d in data]
    x = np.arange(len(methods)); w = 0.26
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for i, (vals, lab, c) in enumerate([(P, "Precision", BLUE), (R, "Recall", ORANGE),
                                       (F, "F1", GREEN)]):
        bars = ax.bar(x + (i - 1) * w, vals, w, label=lab, color=c)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}",
                    ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(methods)
    ax.set_ylim(0, 1.12); ax.set_ylabel("指标值")
    ax.set_title(f"消融对比（{len(ids)} 条可对齐标注，τ={tau}）")
    ax.legend(fontsize=8, ncol=3)
    ax.grid(axis="y", alpha=0.3)
    save(fig, "fig_ablation.png")
    print(f"    规则 P/R/F1 = {rule_prf[0]:.2f}/{rule_prf[1]:.2f}/{rule_prf[2]:.2f}；"
          f"本文 = {llm_prf[0]:.2f}/{llm_prf[1]:.2f}/{llm_prf[2]:.2f}")


def fig_confusion(cfg) -> None:
    labels = eval_labels()
    if len(labels) < 20:
        print("  跳过混淆矩阵：有效标注不足")
        return
    judged = {r["record_id"]: float(r.get("confidence", 0))
              for r in read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")}
    ids = [i for i in labels if i in judged]
    if len(ids) < 20:
        return
    tau = float(cfg["judge"]["threshold"])
    tp = fp = fn = tn = 0
    for i in ids:
        pred = 1 if judged[i] >= tau else 0
        if pred == 1 and labels[i] == 1: tp += 1
        elif pred == 1 and labels[i] == 0: fp += 1
        elif pred == 0 and labels[i] == 1: fn += 1
        else: tn += 1
    M = np.array([[tn, fp], [fn, tp]])
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    im = ax.imshow(M, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, M[i, j], ha="center", va="center", fontsize=16,
                    color="white" if M[i, j] > M.max() * 0.6 else "#1f2328")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["预测=非机会", "预测=机会"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["实际=非机会", "实际=机会"])
    ax.set_title(f"混淆矩阵（τ={tau}，标注 {len(ids)} 条）")
    fig.colorbar(im, ax=ax, shrink=0.8)
    save(fig, "fig_confusion.png")


def fig_source_status(cfg) -> None:
    from collectors.registry import SOURCE_STATUS
    from schema import SOURCE_NAMES

    ok = [n for n in SOURCE_NAMES
          if n not in SOURCE_STATUS or "已接入" in SOURCE_STATUS.get(n, "")]
    bad = {k: v for k, v in SOURCE_STATUS.items() if "已接入" not in v}

    def bucket(reason: str) -> str:
        if "合规禁止" in reason: return "合规禁止"
        if "SPA" in reason: return "SPA 无接口"
        if "登录" in reason: return "需登录"
        if "限流" in reason: return "限流"
        if "404" in reason or "空列表" in reason: return "接口异常"
        if "超时" in reason or "不可达" in reason: return "网络不可达"
        return "其他"

    from collections import Counter
    c = Counter(bucket(v) for v in bad.values())
    labels = ["可采集"] + list(c.keys())
    vals = [len(ok)] + list(c.values())
    colors = [GREEN] + [RED if l == "合规禁止" else GREY for l in c.keys()]

    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bars = ax.barh(labels[::-1], vals[::-1], color=colors[::-1])
    for b, v in zip(bars, vals[::-1]):
        ax.text(v + 0.15, b.get_y() + b.get_height() / 2, str(v), va="center", fontsize=9)
    ax.set_xlabel("来源数量")
    ax.set_title(f"手册 {len(SOURCE_NAMES)} 个来源的可用性实测")
    ax.grid(axis="x", alpha=0.3)
    save(fig, "fig_source_status.png")


def fig_batch_compare(cfg) -> None:
    tracks = [("ecommerce", "电商客服"), ("education", "教育学习"),
              ("track-5383", "医疗问诊"), ("track-6717", "法律合同")]
    names, recs, opps = [], [], []
    for slug, label in tracks:
        p = ROOT / "data" / "out" / slug / "result2.csv"
        if not p.exists():
            continue
        r = rows(p)
        names.append(label)
        recs.append(len(r))
        opps.append(sum(1 for x in r if x["是否构成机会"] == "1"))
    if not names:
        print("  跳过批次对比：无数据")
        return
    x = np.arange(len(names)); w = 0.36
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    b1 = ax.bar(x - w / 2, recs, w, label="入表记录", color=BLUE)
    b2 = ax.bar(x + w / 2, opps, w, label="机会记录", color=ORANGE)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 6,
                    f"{int(b.get_height())}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel("记录数")
    ax.set_title("多批次验证：四个需求方向各自独立")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    save(fig, "fig_batch_compare.png")


def fig_weight_compare(cfg) -> None:
    detail = read_jsonl(Path(cfg["paths"]["clean"]) / "score_detail.jsonl")
    if not detail:
        print("  跳过权重图")
        return
    wd = detail[0].get("weight_detail", {})
    dims = wd.get("dims", [])
    if not dims:
        return
    x = np.arange(len(dims)); w = 0.26
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for i, (key, lab, c) in enumerate([("w_entropy", "熵权（客观）", BLUE),
                                       ("w_ahp", "AHP（主观）", ORANGE),
                                       ("w_final", "组合权重", GREEN)]):
        vals = wd.get(key, [])
        bars = ax.bar(x + (i - 1) * w, vals, w, label=lab, color=c)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.006, f"{v:.3f}",
                    ha="center", fontsize=7, rotation=90)
    ax.set_xticks(x); ax.set_xticklabels(dims)
    ax.set_ylabel("权重")
    ax.set_title("熵权法与 AHP 的组合赋权")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    save(fig, "fig_weight_compare.png")


def fig_cluster_sizes(cfg) -> None:
    r3 = rows(ROOT / "data/out/result3.csv")
    r4 = rows(ROOT / "data/out/result4.csv")
    if not r3 or not r4:
        print("  跳过簇规模图")
        return
    m = {r["主题簇编号"]: r for r in r3}
    data = []
    for r in sorted(r4, key=lambda x: int(x["优先级"])):
        cid = r["主题簇编号"]
        data.append((cid, r["主题簇名称"], int(m.get(cid, {}).get("簇内机会记录数", 0)),
                     float(r["机会价值分"])))
    labels = [f"{d[0]}" for d in data]
    sizes = [d[2] for d in data]
    scores = [d[3] for d in data]

    fig, ax1 = plt.subplots(figsize=(7.0, 3.8))
    bars = ax1.bar(labels, sizes, color=BLUE, alpha=0.85, label="记录数")
    ax1.set_ylabel("簇内机会记录数", color=BLUE)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_xlabel("主题簇（按优先级排序）")
    for b, v in zip(bars, sizes):
        ax1.text(b.get_x() + b.get_width() / 2, v + 0.4, str(v), ha="center", fontsize=8)

    ax2 = ax1.twinx()
    ax2.plot(labels, scores, color=ORANGE, marker="o", lw=1.8, label="价值分")
    ax2.set_ylabel("机会价值分", color=ORANGE)
    ax2.tick_params(axis="y", labelcolor=ORANGE)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")
    ax1.set_title("主题簇规模与价值分")
    ax1.grid(axis="y", alpha=0.25)
    save(fig, "fig_cluster_sizes.png")


def main() -> int:
    cfg = load_config(track="all")
    print("生成补充配图：")
    for fn in (fig_ablation, fig_confusion, fig_source_status,
               fig_batch_compare, fig_weight_compare, fig_cluster_sizes):
        try:
            fn(cfg)
        except Exception as exc:
            print(f"  [{fn.__name__}] 失败：{exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
