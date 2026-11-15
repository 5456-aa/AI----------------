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

import re

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




def fig_time_trend(cfg) -> None:
    """发布时间月度分布（机会 vs 非机会，堆叠柱）。"""
    import collections
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    cnt = collections.defaultdict(lambda: [0, 0])
    for r in judged:
        d = str(r.get("published_at") or "")[:7]
        if len(d) != 7:
            continue
        cnt[d][1 if r.get("is_opportunity") == 1 else 0] += 1
    if not cnt:
        print("  跳过时间趋势：无发布时间")
        return
    months = sorted(cnt)[-15:]
    non_opp = [cnt[m][0] for m in months]
    opp = [cnt[m][1] for m in months]
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    ax.bar(months, non_opp, color="#cbd5e1", label="非机会")
    ax.bar(months, opp, bottom=non_opp, color="#2563eb", label="机会")
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("记录数")
    ax.set_title("按发布月份的内容分布（近 15 个月）")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    save(fig, "fig_time_trend.png")


def fig_source_category_heat(cfg) -> None:
    """来源 × 功能类别 热力图（仅机会记录）。"""
    import collections
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    pairs = collections.Counter()
    for r in judged:
        if r.get("is_opportunity") != 1:
            continue
        fc = (r.get("func_category") or "").strip()
        src = (r.get("source") or "").strip()
        if fc and src:
            pairs[(src, fc)] += 1
    if not pairs:
        print("  跳过热力图：无机会记录")
        return
    srcs = sorted({k[0] for k in pairs})
    cats = sorted({k[1] for k in pairs})
    M = np.zeros((len(srcs), len(cats)))
    for (s_, c_), v in pairs.items():
        M[srcs.index(s_), cats.index(c_)] = v
    fig, ax = plt.subplots(figsize=(8.2, max(2.6, 0.5 * len(srcs) + 1.2)))
    im = ax.imshow(M, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(len(srcs)))
    ax.set_yticklabels(srcs, fontsize=8)
    for i in range(len(srcs)):
        for j in range(len(cats)):
            if M[i, j] > 0:
                ax.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=8,
                        color="white" if M[i, j] > M.max() * 0.6 else "#1f2328")
    ax.set_title("机会记录的来源 × 功能类别分布")
    fig.colorbar(im, ax=ax, shrink=0.8, label="机会数")
    save(fig, "fig_source_category_heat.png")


def fig_confidence_hist(cfg) -> None:
    """机会置信度分布 + 阈值线。"""
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    conf = [float(r.get("confidence", 0)) for r in judged]
    if not conf:
        return
    tau = float(cfg["judge"]["threshold"])
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.hist(conf, bins=40, color="#94a3b8", edgecolor="white")
    ax.axvline(tau, color="#e15759", ls="--", lw=1.6, label=f"阈值 τ={tau}")
    ax.set_xlabel("机会置信度"); ax.set_ylabel("记录数")
    ax.set_title("置信度分布与判别阈值")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.25)
    save(fig, "fig_confidence_hist.png")




STOP = set("""的 了 和 是 在 我 有 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好
自己 这 那 我们 他们 可以 这个 那个 因为 所以 但是 如果 就是 什么 怎么 如何 为什么
以及 通过 进行 需要 问题 使用 目前 现在 已经 还是 或者 而且 并且 这样 那样 时候
ai 人工智能 大模型 模型 技术 系统 平台 工具 功能 方法 方案 需求 数据 应用 场景""".split())


def fig_word_freq(cfg) -> None:
    """机会记录的关键词 Top-20（TF-IDF 抽取，替代词云）。"""
    import jieba.analyse

    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    texts = [r.get("clean_text", "") for r in judged if r.get("is_opportunity") == 1]
    if not texts:
        print("  跳过词频：无机会记录")
        return

    import collections
    bag = collections.Counter()
    for t in texts:
        # TF-IDF 抽取：自带 IDF，天然压掉高频虚词
        for w, weight in jieba.analyse.extract_tags(t, topK=15, withWeight=True):
            bag[w] += weight
    # 过滤：纯英文虚词、符号、单字
    bad = {"the", "and", "for", "with", "this", "that", "you", "are", "not",
           "can", "use", "using", "from", "have", "will", "would", "there",
           "they", "your", "our", "its", "was", "but", "all", "any"}
    items = [(w, v) for w, v in bag.items()
             if w.lower() not in bad and len(w) >= 2
             and re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9+#.\-]{2,}", w or "")
             and not re.fullmatch(r"[0-9.#\-]+", w)]
    items.sort(key=lambda x: -x[1])
    top = items[:20]
    if not top:
        return
    words = [w for w, _ in top][::-1]
    vals = [round(v, 1) for _, v in top][::-1]
    fig, ax = plt.subplots(figsize=(6.8, 5.2))
    bars = ax.barh(words, vals, color="#2563eb", alpha=0.9)
    for b, v in zip(bars, vals):
        ax.text(v + max(vals) * 0.01, b.get_y() + b.get_height() / 2, f"{v}",
                va="center", fontsize=8, color="#334155")
    ax.set_xlabel("TF-IDF 累计权重（机会记录内）")
    ax.set_title("机会记录的关键词 Top-20（TF-IDF 抽取）")
    ax.grid(axis="x", alpha=0.25)
    save(fig, "fig_word_freq.png")


def fig_flow_sankey(cfg) -> None:
    """来源 → 主题簇 流向图（桑基风格，用贝塞尔带绘制）。"""
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch
    import collections

    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    scored = read_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl")
    id2clu = {}
    for c in scored:
        for rid in c.get("record_ids", []):
            id2clu[rid] = (c.get("cluster_id"), c.get("topic_name"))
    flows = collections.Counter()
    for r in judged:
        if r.get("is_opportunity") != 1:
            continue
        c = id2clu.get(r.get("record_id"))
        if not c:
            continue
        flows[(r.get("source", ""), c[0])] += 1
    if not flows:
        print("  跳过流向图：无可用映射")
        return

    srcs = sorted({k[0] for k in flows})
    clus = sorted({k[1] for k in flows}, key=lambda x: int(str(x).lstrip("C") or 0))
    name_map = {c.get("cluster_id"): c.get("topic_name") for c in scored
                if c.get("cluster_id") in clus}

    src_tot = {s_: sum(v for (a, _), v in flows.items() if a == s_) for s_ in srcs}
    clu_tot = {c_: sum(v for (_, b), v in flows.items() if b == c_) for c_ in clus}
    total = sum(src_tot.values())

    fig, ax = plt.subplots(figsize=(9.2, max(4.2, 0.42 * max(len(srcs), len(clus)) + 1.5)))
    ax.set_xlim(0, 10); ax.set_ylim(0, total * 1.06); ax.axis("off")

    def layout(nodes, sizes):
        gap = total * 0.035
        span = total - gap * (len(nodes) - 1)
        y, pos = total, {}
        for n in nodes:
            h = sizes[n] / total * span
            pos[n] = (y - h, h)
            y -= h + gap
        return pos

    lpos, rpos = layout(srcs, src_tot), layout(clus, clu_tot)
    lcur = {k: v[0] + v[1] for k, v in lpos.items()}
    rcur = {k: v[0] + v[1] for k, v in rpos.items()}
    palette = ["#2563eb", "#59a14f", "#f28e2b", "#e15759", "#7c3aed",
               "#0ea5e9", "#94a3b8", "#db2777"]

    for i, s_ in enumerate(srcs):
        for c_ in clus:
            v = flows.get((s_, c_), 0)
            if not v:
                continue
            h = v / total * (total - total * 0.035 * (len(srcs) - 1))
            y0a, y0b = lcur[s_] - h, lcur[s_]
            h2 = v / total * (total - total * 0.035 * (len(clus) - 1))
            y1a, y1b = rcur[c_] - h2, rcur[c_]
            lcur[s_] -= h
            rcur[c_] -= h2
            # 上边：左 -> 右 的贝塞尔；下边：右 -> 左 返回，形成带状闭合
            x0, x1, xm = 1.15, 8.85, (1.15 + 8.85) / 2
            verts = [(x0, y0b), (xm, y0b), (xm, y1b), (x1, y1b),
                     (x1, y1a), (xm, y1a), (xm, y0a), (x0, y0a), (x0, y0b)]
            codes = [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
                     MPath.LINETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
                     MPath.CLOSEPOLY]
            ax.add_patch(PathPatch(MPath(verts, codes),
                                   facecolor=palette[i % len(palette)],
                                   alpha=0.35, edgecolor="none"))

    for s_ in srcs:
        y, h = lpos[s_]
        ax.add_patch(plt.Rectangle((0.7, y), 0.45, h, color="#334155"))
        ax.text(0.6, y + h / 2, f"{s_} ({src_tot[s_]})", ha="right", va="center", fontsize=9)
    for c_ in clus:
        y, h = rpos[c_]
        ax.add_patch(plt.Rectangle((8.85, y), 0.45, h, color="#2563eb"))
        label = f"{c_} {str(name_map.get(c_, ''))[:10]} ({clu_tot[c_]})"
        ax.text(9.4, y + h / 2, label, ha="left", va="center", fontsize=8)
    ax.set_title("机会记录从来源到主题簇的流向（带宽 = 记录数）", fontsize=11)
    save(fig, "fig_flow_sankey.png")


def main() -> int:
    cfg = load_config(track="all")
    print("生成补充配图：")
    for fn in (fig_ablation, fig_confusion, fig_source_status,
               fig_batch_compare, fig_weight_compare, fig_cluster_sizes,
               fig_time_trend, fig_source_category_heat, fig_confidence_hist,
               fig_word_freq, fig_flow_sankey):
        try:
            fn(cfg)
        except Exception as exc:
            print(f"  [{fn.__name__}] 失败：{exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
