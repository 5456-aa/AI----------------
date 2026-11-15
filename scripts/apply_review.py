# -*- coding: utf-8 -*-
"""合并复核结果 → 更新标注集 → 重新标定阈值。

流程：
  1. 读 data/label/复核表.xlsx 的「复核(填1/0)」列；
  2. 把有值的条目覆盖写回 label_set.csv 与 人工标注表.xlsx；
  3. 重新跑 tune_threshold，输出 P-R 曲线与最优 τ。

用法：python scripts/apply_review.py
      python scripts/apply_review.py --no-tune   # 只合并，不标定
"""
from __future__ import annotations

import argparse
import csv
import io
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook  # noqa: E402

LABEL_DIR = ROOT / "data" / "label"
REVIEW = LABEL_DIR / "复核表.xlsx"
CSV_PATH = LABEL_DIR / "label_set.csv"
XLSX_PATH = LABEL_DIR / "人工标注表.xlsx"


def read_review() -> dict[str, int]:
    if not REVIEW.exists():
        raise SystemExit(f"找不到 {REVIEW.name}，先生成复核表")
    wb = load_workbook(REVIEW, data_only=True)
    ws = wb["复核表"] if "复核表" in wb.sheetnames else wb.active
    header = [str(c.value or "").strip() for c in ws[1]]
    try:
        i_id = header.index("记录编号")
        i_new = header.index("复核(填1/0)")
    except ValueError:
        raise SystemExit("复核表缺少「记录编号」或「复核(填1/0)」列")

    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        rid = "" if row[i_id] is None else str(row[i_id]).strip()
        val = "" if row[i_new] is None else str(row[i_new]).strip()
        if rid and val in ("0", "1", "0.0", "1.0"):
            out[rid] = int(float(val))
    return out


def backup() -> None:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for p in (CSV_PATH, XLSX_PATH):
        if p.exists():
            shutil.copy(p, p.with_name(f"{p.stem}.bak_{stamp}{p.suffix}"))


def apply_to_csv(changes: dict[str, int]) -> tuple[int, int]:
    rows = list(csv.DictReader(io.open(CSV_PATH, encoding="utf-8-sig")))
    changed = 0
    for r in rows:
        new = changes.get(r["记录编号"])
        if new is None:
            continue
        if r["label"].strip() != str(new):
            r["label"] = str(new)
            changed += 1
    with io.open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return changed, len(rows)


def apply_to_xlsx(changes: dict[str, int]) -> int:
    if not XLSX_PATH.exists():
        return 0
    wb = load_workbook(XLSX_PATH)
    ws = wb["标注表"] if "标注表" in wb.sheetnames else wb.active
    header = [str(c.value or "").strip() for c in ws[1]]
    i_id, i_lab = header.index("记录编号"), header.index("label")
    n = 0
    for row in ws.iter_rows(min_row=2):
        rid = "" if row[i_id].value is None else str(row[i_id].value).strip()
        if rid in changes:
            row[i_lab].value = changes[rid]
            n += 1
    wb.save(XLSX_PATH)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tune", action="store_true")
    args = ap.parse_args(argv)

    changes = read_review()
    if not changes:
        print("复核表里还没填任何值（「复核(填1/0)」列是空的）。")
        print("填完保存后再运行本脚本。")
        return 1

    backup()
    n_csv, total = apply_to_csv(changes)
    n_xlsx = apply_to_xlsx(changes)
    print(f"复核条目 {len(changes)} 条；CSV 实际改动 {n_csv} 条（共 {total} 条），"
          f"Excel 更新 {n_xlsx} 行。")

    # 复核后统计
    rows = list(csv.DictReader(io.open(CSV_PATH, encoding="utf-8-sig")))
    lab = [r for r in rows if r["label"].strip() in ("0", "1")]
    pos = sum(1 for r in lab if r["label"] == "1")
    print(f"复核后：已标 {len(lab)}/120，机会 {pos}，非机会 {len(lab) - pos}"
          f"（机会率 {pos / max(len(lab), 1) * 100:.0f}%）")

    if args.no_tune:
        return 0

    print("\n" + "=" * 58)
    print("重新标定阈值 …")
    print("=" * 58)
    from scripts.tune_threshold import tune  # noqa: E402
    tune(XLSX_PATH if XLSX_PATH.exists() else CSV_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
