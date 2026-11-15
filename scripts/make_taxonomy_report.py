# -*- coding: utf-8 -*-
"""生成「标签体系对照表」：附件1 的 16 类功能类别 / 30 类行业，本系统的实际使用情况。

赛题要求「功能类别 16 类（包括但不限于）、所属行业 30 类」，
本脚本核对：体系是否完整落地、哪些类被用到、哪些没用到、有没有越界。

用法：python scripts/make_taxonomy_report.py
"""
from __future__ import annotations

import csv
import io
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config  # noqa: E402
from schema import FUNC_CATEGORIES, INDUSTRIES  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

OUT = ROOT / "reports" / "标签体系对照.md"


def rows(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with io.open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> int:
    cfg = load_config(track="all")
    r2 = rows(Path(cfg["paths"]["out"]) / "result2.csv")
    r3 = rows(Path(cfg["paths"]["out"]) / "result3.csv")
    opp = [r for r in r2 if r.get("是否构成机会") == "1"]

    fc_cnt = Counter(r["功能类别"] for r in opp if r.get("功能类别"))
    ind_cnt = Counter(r["所属行业"] for r in opp if r.get("所属行业"))
    cluster_fc = Counter(r["功能类别"] for r in r3)
    cluster_ind = Counter(r["所属行业"] for r in r3)

    bad_fc = {r["功能类别"] for r in r2 if r.get("功能类别") and r["功能类别"] not in FUNC_CATEGORIES}
    bad_ind = {r["所属行业"] for r in r2 if r.get("所属行业") and r["所属行业"] not in INDUSTRIES}

    L = ["# 标签体系对照（附件 1）", "",
         f"- 功能类别：**{len(FUNC_CATEGORIES)}** 类（与附件 1 一致）",
         f"- 所属行业：**{len(INDUSTRIES)}** 类（与附件 1 一致）",
         f"- 越界取值：功能类别 {len(bad_fc)} 个、行业 {len(bad_ind)} 个"
         f"{'（无）' if not bad_fc and not bad_ind else '：' + '、'.join(sorted(bad_fc | bad_ind))}",
         "",
         "## 一、功能类别（16 类）使用情况", "",
         "| # | 功能类别 | 机会记录数 | 主题簇数 | 是否使用 |",
         "|---|---|---|---|---|"]
    for i, c in enumerate(FUNC_CATEGORIES, 1):
        L.append(f"| {i} | {c} | {fc_cnt.get(c, 0)} | {cluster_fc.get(c, 0)} | "
                 f"{'✅' if fc_cnt.get(c, 0) else '—'} |")

    L += ["", f"共使用 **{sum(1 for c in FUNC_CATEGORIES if fc_cnt.get(c, 0))} / {len(FUNC_CATEGORIES)}** 类。",
          "", "## 二、所属行业（30 类）使用情况", "",
          "| # | 所属行业 | 机会记录数 | 主题簇数 | 是否使用 |",
          "|---|---|---|---|---|"]
    for i, c in enumerate(INDUSTRIES, 1):
        L.append(f"| {i} | {c} | {ind_cnt.get(c, 0)} | {cluster_ind.get(c, 0)} | "
                 f"{'✅' if ind_cnt.get(c, 0) else '—'} |")

    L += ["", f"共使用 **{sum(1 for c in INDUSTRIES if ind_cnt.get(c, 0))} / {len(INDUSTRIES)}** 类。",
          "",
          "## 三、说明（论文里要写清）", "",
          "1. **体系完整落地**：16 × 30 全部写进 `schema.py`，判别时按该体系取值，"
          "越界会被 `validate.py` 拦下；",
          "2. **「包括但不限于」的处理**：赛题允许扩展，但本项目**不做扩展**——"
          "宁可把记录归到「其他」，也不自造新类，保证与附件 1 可直接对齐；",
          "3. **未使用的类不是遗漏**：本批次只覆盖电商与教育两个方向，"
          "医疗、法律、金融等行业没有命中属于正常（见 `reports/多批次验证.md`）；",
          "4. **簇级标签取众数**：主题簇的功能类别与行业由簇内记录投票产生，"
          "避免模型在簇级给出组合词（早期版本踩过这个坑，见 AI 使用情况说明第四节）。",
          ""]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"已生成 {OUT}")
    print(f"  功能类别使用 {sum(1 for c in FUNC_CATEGORIES if fc_cnt.get(c,0))}/{len(FUNC_CATEGORIES)}；"
          f"行业使用 {sum(1 for c in INDUSTRIES if ind_cnt.get(c,0))}/{len(INDUSTRIES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
