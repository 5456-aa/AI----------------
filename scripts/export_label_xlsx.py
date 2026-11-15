# -*- coding: utf-8 -*-
"""把标注集导出成 Excel（带下拉框、冻结表头、进度统计）。

用法：python scripts/export_label_xlsx.py
产出：data/label/人工标注表.xlsx

设计要点：
  * label 列做成下拉框（1 / 0），避免手打错；
  * 表头冻结 + 筛选，正文自动换行；
  * 单独一页写判定标准，不用来回翻文档；
  * 顶部一页「进度」用公式统计已标/未标，随时看还剩多少。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import csv

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

CSV_PATH = ROOT / "data" / "label" / "label_set.csv"
OUT_PATH = ROOT / "data" / "label" / "人工标注表.xlsx"

HEADERS = ["序号", "记录编号", "来源", "标题", "正文", "发布时间",
           "模型判断", "模型置信度", "label", "备注"]
WIDTHS = [6, 12, 14, 32, 70, 20, 10, 11, 8, 18]
WRAP_COLS = {4, 5}          # 标题、正文自动换行

HDR_FILL = PatternFill("solid", fgColor="1F4E79")
HDR_FONT = Font(color="FFFFFF", bold=True, size=11)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
LABEL_FILL = PatternFill("solid", fgColor="FFF2CC")   # 需要填写的那列标浅黄

RULES = [
    ("判定标准（四条同时满足才算「机会」）", ""),
    ("1. 有真实需求", "具体的人在表达具体困难/求助/期望："
                 "「有没有工具…」「求推荐」「怎么才能…」「太麻烦了」「希望有个…」。"
                 "纯陈述事实、转述观点不算。"),
    ("2. AI 是核心", "这个问题必须依赖 AI 能力（语义理解、生成、识别、预测、多模态）才能解决；"
                  "普通信息化、外包、加人力就能解决的，不算。"),
    ("3. 技术可落地", "现有技术即可实现，不需要自研基础模型、不需要海量标注数据、不需要专用硬件。"),
    ("4. 排除情形", "纯资讯报道、广告营销、教程科普、招聘、政策公告、无诉求的情绪吐槽 —— 一律标 0。"),
    ("", ""),
    ("怎么填", "只在 label 列填 1（是机会）或 0（非机会）。有疑问写进备注列。"),
    ("填完怎么办", "保存这个 xlsx，运行："
                "python scripts/tune_threshold.py --tune data/label/人工标注表.xlsx"),
    ("注意", "这是人工判断，不要用 AI 预标后直接提交——那属于伪造研究过程。"),
]


def main() -> int:
    if not CSV_PATH.exists():
        print(f"找不到 {CSV_PATH}，先运行 python scripts/make_label_set.py --n 120")
        return 1

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    wb = Workbook()

    # ---------------- 说明页 ----------------
    ws0 = wb.active
    ws0.title = "填写说明"
    ws0.column_dimensions["A"].width = 22
    ws0.column_dimensions["B"].width = 95
    ws0["A1"] = "人工标注说明"
    ws0["A1"].font = Font(size=16, bold=True, color="1F4E79")
    ws0.merge_cells("A1:B1")

    for i, (k, v) in enumerate(RULES, start=3):
        ws0.cell(row=i, column=1, value=k).font = Font(bold=True)
        c = ws0.cell(row=i, column=2, value=v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws0.row_dimensions[i].height = 32 if len(v) > 40 else 18

    # ---------------- 标注表 ----------------
    ws = wb.create_sheet("标注表")
    for col, (h, w) in enumerate(zip(HEADERS, WIDTHS), start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{len(rows) + 1}"

    for r, row in enumerate(rows, start=2):
        for col, key in enumerate(HEADERS, start=1):
            val = row.get(key, "")
            if key in ("序号",):
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    pass
            cell = ws.cell(row=r, column=col, value=val)
            cell.border = BORDER
            cell.alignment = Alignment(
                wrap_text=col in WRAP_COLS,
                vertical="top",
                horizontal="center" if col in (1, 7, 8, 9) else "left")
            if col == 9:
                cell.fill = LABEL_FILL
        ws.row_dimensions[r].height = 58

    # label 列下拉框（1/0）
    dv = DataValidation(type="list", formula1='"1,0"', allow_blank=True,
                        showDropDown=False, error="只能填 1（是机会）或 0（非机会）",
                        errorTitle="取值不对", prompt="1=是机会，0=非机会",
                        promptTitle="请选择")
    ws.add_data_validation(dv)
    dv.add(f"I2:I{len(rows) + 1}")

    # ---------------- 进度页 ----------------
    ws2 = wb.create_sheet("进度")
    last = len(rows) + 1
    ws2["A1"] = "标注进度"
    ws2["A1"].font = Font(size=14, bold=True, color="1F4E79")
    stats = [
        ("总条数", f"=COUNTA(标注表!B2:B{last})"),
        ("已标注", f'=COUNTIFS(标注表!I2:I{last},"1")+COUNTIFS(标注表!I2:I{last},"0")'),
        ("其中 机会(1)", f'=COUNTIFS(标注表!I2:I{last},"1")'),
        ("其中 非机会(0)", f'=COUNTIFS(标注表!I2:I{last},"0")'),
        ("还剩", f'=B2-B3'),
        ("完成度", f'=IF(B2=0,0,B3/B2)'),
    ]
    for i, (k, formula) in enumerate(stats, start=2):
        ws2.cell(row=i, column=1, value=k).font = Font(bold=True)
        c = ws2.cell(row=i, column=2, value=formula)
        if k == "完成度":
            c.number_format = "0.0%"
    ws2.column_dimensions["A"].width = 16
    ws2.column_dimensions["B"].width = 12
    ws2["A9"] = "提示：填完保存后，运行"
    ws2["A10"] = "python scripts/tune_threshold.py --tune data/label/人工标注表.xlsx"
    ws2["A10"].font = Font(name="Consolas", size=10, color="C00000")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_PATH)

    print(f"已生成：{OUT_PATH}")
    print(f"  共 {len(rows)} 条；label 列是下拉框，只填 1 或 0")
    print(f"  另含「填写说明」「进度」两个工作表")
    return 0


if __name__ == "__main__":
    sys.exit(main())
