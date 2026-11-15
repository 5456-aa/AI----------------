# -*- coding: utf-8 -*-
"""在人工标注集上标定判别阈值 τ，并输出 P-R 曲线与混淆矩阵。

流程：
  1. 导出待标注清单：  python scripts/tune_threshold.py --export labels.csv
  2. 人工在 labels.csv 里填 label 列（1=机会，0=非机会），至少 150 条
  3. 标定：            python scripts/tune_threshold.py --tune labels.csv
产物：
  reports/threshold_report.md   阈值扫描表 + 最优 τ + 混淆矩阵
  figs/pr_curve.png             P-R 曲线（直接进论文）
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402


def export_labels(path: Path) -> None:
    rows = read_jsonl(ROOT / "data/clean/judged.jsonl")
    if not rows:
        raise SystemExit("先运行 python run_all.py --stage judge")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["record_id", "source", "title", "text", "confidence", "label"])
        for r in rows:
            w.writerow([r["record_id"], r["source"], r.get("title", ""),
                        r.get("clean_text", "")[:200], r.get("confidence", ""), ""])
    print(f"导出 {len(rows)} 条待标注 -> {path}")
    print("请在 label 列填 1（构成机会）或 0（不构成），然后运行 --tune")


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def _read_labels(path: Path) -> dict:
    """支持 CSV 与 Excel（人工标注表.xlsx）两种来源。"""
    labels = {}

    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
        ws = wb["标注表"] if "标注表" in wb.sheetnames else wb.active
        header = [str(c.value or "").strip() for c in ws[1]]
        try:
            i_id = header.index("记录编号")
            i_lab = header.index("label")
        except ValueError:
            raise SystemExit("Excel 缺少「记录编号」或「label」列，请用导出的模板填写")
        for row in ws.iter_rows(min_row=2, values_only=True):
            # 注意：0 是 falsy，不能用 `or ""`，否则 0 会被当成空值丢掉
            raw_id = row[i_id] if i_id < len(row) else None
            raw_lab = row[i_lab] if i_lab < len(row) else None
            rid = "" if raw_id is None else str(raw_id).strip()
            lab = "" if raw_lab is None else str(raw_lab).strip()
            if rid and lab in ("0", "1", "0.0", "1.0"):
                labels[rid] = int(float(lab))
        return labels

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            # 兼容两种列名：新标注表用「记录编号」，内部 CSV 用 record_id
            rid = (row.get("record_id") or row.get("记录编号") or "").strip()
            lab = (row.get("label") or "").strip()
            if rid and lab in ("0", "1"):
                labels[rid] = int(lab)
    return labels


def tune(path: Path) -> None:
    cfg = load_config()
    labels = _read_labels(path)
    if len(labels) < 30:
        raise SystemExit(f"有效标注只有 {len(labels)} 条，至少 30 条才能标定（建议 150+）")

    judged = {r["record_id"]: r for r in read_jsonl(ROOT / "data/clean/judged.jsonl")}
    ids = [i for i in labels if i in judged]
    y = np.array([labels[i] for i in ids])
    conf = np.array([float(judged[i]["confidence"]) for i in ids])

    rows = []
    best = (-1.0, 0.5, 0.0, 0.0, 0.0)
    for tau in np.arange(0.10, 0.91, 0.01):
        pred = (conf >= tau).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        p, r, f1 = prf(tp, fp, fn)
        rows.append((round(float(tau), 2), round(p, 4), round(r, 4), round(f1, 4)))
        if f1 > best[0]:
            best = (f1, float(tau), p, r, f1)

    best_f1, best_tau, bp, br, bf1 = best
    report = ROOT / "reports" / "threshold_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 判别阈值标定报告", "",
        f"- 标注样本：{len(labels)} 条（正例 {int(y.sum())}，负例 {int((1 - y).sum())}）",
        f"- **最优阈值 τ = {best_tau:.2f}**（F1 最大）",
        f"- Precision = {bp:.4f}，Recall = {br:.4f}，F1 = {bf1:.4f}", "",
        "## 阈值扫描", "", "| τ | Precision | Recall | F1 |", "|---|---|---|---|",
    ]
    for tau, p, r, f1 in rows[::5]:
        mark = " ⭐" if abs(tau - best_tau) < 1e-9 else ""
        lines.append(f"| {tau:.2f}{mark} | {p:.4f} | {r:.4f} | {f1:.4f} |")

    # 最优阈值下的混淆矩阵
    pred = (conf >= best_tau).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    lines += ["", "## 混淆矩阵（τ 取最优）", "",
              "| | 预测=机会 | 预测=非机会 |", "|---|---|---|",
              f"| 实际=机会 | TP={tp} | FN={fn} |",
              f"| 实际=非机会 | FP={fp} | TN={tn} |",
              "", f"**下一步：把 config.yaml 里 `judge.threshold` 改成 {best_tau:.2f}，"
                  f"然后重跑 `python run_all.py`。**"]
    report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:8]))
    print(f"\n报告 -> {report}")

    # 画 P-R 曲线（matplotlib 可选）
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(5.2, 4.2))
        ax.plot([r[2] for r in rows], [r[1] for r in rows], lw=2)
        ax.scatter([br], [bp], color="crimson", zorder=5,
                   label=f"τ={best_tau:.2f}, F1={bf1:.3f}")
        ax.set_xlabel("Recall 召回率")
        ax.set_ylabel("Precision 精确率")
        ax.set_title("机会判别 P-R 曲线")
        ax.grid(alpha=0.3)
        ax.legend()
        out = ROOT / "figs" / "pr_curve.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(out, dpi=200)
        print(f"图 -> {out}")
    except Exception as exc:
        print(f"（跳过绘图：{exc}）")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default=None, help="导出待标注 CSV 的路径")
    ap.add_argument("--tune", default=None, help="已标注 CSV 的路径")
    args = ap.parse_args(argv)
    if args.export:
        export_labels(Path(args.export))
    elif args.tune:
        tune(Path(args.tune))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
