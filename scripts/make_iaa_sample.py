# -*- coding: utf-8 -*-
"""导出「双人盲标」样本：给第二个人标注，用于计算 Cohen's κ。

从已标注的 120 条里抽 40 条，**不显示第一个人的标签**（盲标），
第二人独立标注后运行 scripts/iaa.py 计算一致性与 κ。

用法：python scripts/make_iaa_sample.py --n 40
产出：data/label/双标样本_B.xlsx
"""
from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

SRC = ROOT / "data" / "label" / "label_set.csv"
OUT = ROOT / "data" / "label" / "双标样本_B.xlsx"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--who", default="B", help="标注人代号，如 B / C")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    out_path = Path(args.out) if args.out else (ROOT / "data" / "label" / f"双标样本_{args.who}.xlsx")
    rows = [r for r in csv.DictReader(io.open(SRC, encoding="utf-8-sig"))
            if r["label"].strip() in ("0", "1")]
    if len(rows) < args.n:
        raise SystemExit(f"已标注只有 {len(rows)} 条，不够抽 {args.n} 条")

    random.seed(args.seed)
    pos = [r for r in rows if r["label"] == "1"]
    neg = [r for r in rows if r["label"] == "0"]
    half = args.n // 2
    picked = random.sample(pos, min(half, len(pos))) + \
        random.sample(neg, min(args.n - min(half, len(pos)), len(neg)))
    random.shuffle(picked)

    wb = Workbook()
    ws0 = wb.active
    ws0.title = "说明"
    ws0.column_dimensions["A"].width = 100
    ws0["A1"] = "双人盲标说明"
    ws0["A1"].font = Font(size=15, bold=True, color="1F4E79")
    for i, t in enumerate([
        "1. 这 40 条是从已标注的 120 条里随机抽的，用于检验两个人的判断是否一致。",
        "2. 本表不显示第一个人的标签——请独立判断，不要问、不要对照。",
        "3. 只填「label」列：1 = 构成 AI 应用机会，0 = 不构成。",
        "4. 判定标准与第一轮相同（见下），拿不准就按最接近的一条判，不要空着。",
        "",
        "四条标准（同时满足才算机会）：",
        "  ① 有真实需求：具体的人在表达具体困难/求助/期望，纯陈述事实不算；",
        "  ② AI 是核心：必须靠语义理解/生成/识别/预测才能解决；",
        "  ③ 可落地：不需要自研基础模型、海量标注、专用硬件；",
        "  ④ 排除：纯资讯、广告、教程、招聘、政策公告、无诉求吐槽 → 一律 0。",
        "",
        "填完保存，运行：python scripts/iaa.py",
    ], start=3):
        ws0.cell(row=i, column=1, value=t).alignment = Alignment(wrap_text=True)

    ws = wb.create_sheet("标注")
    hdr = ["序号", "记录编号", "来源", "标题", "正文", "label", "备注"]
    widths = [6, 12, 14, 34, 72, 8, 16]
    for i, (h, w) in enumerate(zip(hdr, widths), 1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(color="FFFFFF", bold=True)
        c.fill = PatternFill("solid", fgColor="1F4E79")
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"

    for n, r in enumerate(picked, 1):
        ws.cell(row=n + 1, column=1, value=n)
        ws.cell(row=n + 1, column=2, value=r["记录编号"])
        ws.cell(row=n + 1, column=3, value=r["来源"])
        ws.cell(row=n + 1, column=4, value=r["标题"])
        c = ws.cell(row=n + 1, column=5, value=r["正文"][:600])
        c.alignment = Alignment(wrap_text=True, vertical="top")
        lab = ws.cell(row=n + 1, column=6, value=None)
        lab.fill = PatternFill("solid", fgColor="FFF2CC")
        ws.row_dimensions[n + 1].height = 58

    dv = DataValidation(type="list", formula1='"1,0"', allow_blank=True, showDropDown=False)
    ws.add_data_validation(dv)
    dv.add(f"F2:F{len(picked) + 1}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)

    # 给在线标注工具用的样本清单（同一批 40 条，seed 固定所以可复现）
    import json
    items_path = ROOT / "data" / "label" / "iaa_items.json"
    items_path.write_text(json.dumps(
        [r["记录编号"] for r in picked], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成盲标样本：{out_path}（标注人 {args.who}）")
    print(f"  {len(picked)} 条（机会 {sum(1 for r in picked if r['label']=='1')} / "
          f"非机会 {sum(1 for r in picked if r['label']=='0')}），未显示第一人的标签")
    print("  给第二个人标完后，运行：python scripts/iaa.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
