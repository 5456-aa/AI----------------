# -*- coding: utf-8 -*-
"""标注集重映射：把旧批次的标注按（来源+标题）迁到当前批次的新记录编号上。

背景：采集脚本每次运行会重新分配记录编号，导致「同一编号指向不同记录」。
本脚本按内容（来源 + 标题，必要时用正文前 40 字）重新对齐，并输出可审计的映射报告。

用法：python scripts/remap_labels.py
产出：data/label/label_set_mapped.csv、reports/标注重映射报告.md
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config  # noqa: E402

SRC = ROOT / "data" / "label" / "label_set.csv"
OUT_CSV = ROOT / "data" / "label" / "label_set_mapped.csv"
OUT_MD = ROOT / "reports" / "标注重映射报告.md"


def key2(source: str, title: str, text: str) -> tuple[str, str]:
    t = (title or "").strip()
    return (source or "", t if t else (text or "")[:40].strip())


def main() -> int:
    cfg = load_config(track="all")
    judged = [json.loads(l) for l in
              io.open(Path(cfg["paths"]["clean"]) / "judged.jsonl", encoding="utf-8")]

    by_key: dict[tuple, dict] = {}
    for r in judged:
        by_key.setdefault(key2(r.get("source"), r.get("title"), r.get("clean_text")), r)

    rows = list(csv.DictReader(io.open(SRC, encoding="utf-8-sig")))
    mapped, lost, mismatch = [], [], 0

    for r in rows:
        k = key2(r["来源"], r["标题"], r["正文"])
        j = by_key.get(k)
        if not j:
            lost.append(r)
            continue
        new_id = j["record_id"]
        if new_id != r["记录编号"]:
            mismatch += 1
        mapped.append({**r, "记录编号": new_id, "原记录编号": r["记录编号"],
                       "模型置信度_新": f"{float(j.get('confidence', 0)):.4f}"})

    with io.open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(mapped[0].keys()))
        w.writeheader()
        w.writerows(mapped)

    n_lab = sum(1 for x in mapped if x["label"].strip() in ("0", "1"))
    L = ["# 标注集重映射报告", "",
         f"- 原标注：{len(rows)} 条",
         f"- 成功对齐到当前批次：**{len(mapped)}** 条（其中编号发生变化的 {mismatch} 条）",
         f"- 无法对齐（当前批次中找不到同来源同标题）：**{len(lost)}** 条",
         f"- 可直接用于阈值标定的有效标注：**{n_lab}** 条", "",
         "## 为什么要重映射", "",
         "采集脚本每次运行会重新分配记录编号（DS00001…），因此重新采集后"
         "「同一编号指向不同记录」。论文中的阈值标定、混淆矩阵、消融对比都必须"
         "在当前批次的编号上重新计算，否则结果不可复核。", "",
         "## 处理方式", "",
         "按 **来源 + 标题**（标题为空时用正文前 40 字）在 `judged.jsonl` 中匹配，"
         "命中则迁移到新的记录编号，未命中则丢弃并在此列出。", ""]
    if lost:
        L += ["### 无法对齐的条目", "", "| 原编号 | 来源 | 标题 |", "|---|---|---|"]
        for r in lost[:40]:
            L.append(f"| {r['记录编号']} | {r['来源']} | {r['标题'][:40]} |")
        if len(lost) > 40:
            L.append(f"| … | 共 {len(lost)} 条 | |")
        L.append("")
    L += ["## 影响", "",
          f"- 阈值标定与消融实验改为在 **{n_lab}** 条有效标注上重算；",
          "- 三人盲标（κ）不受影响：标注人都看同一批文本，编号一致；",
          "- 论文中需说明「重新采集后按内容对齐标注」，避免前后批次混用。"]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"原 {len(rows)} 条 → 对齐 {len(mapped)} 条（编号变化 {mismatch}），丢失 {len(lost)} 条")
    print(f"有效标注 {n_lab} 条")
    print(f"报告 -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
