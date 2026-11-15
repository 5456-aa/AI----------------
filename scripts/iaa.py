# -*- coding: utf-8 -*-
"""计算双人标注一致性：观察一致率 + Cohen's κ。

输入：
  A = data/label/人工标注表.xlsx（第一个人）
  B = data/label/双标样本_B.xlsx（第二个人，盲标）
输出：
  reports/iaa.json  +  reports/标注一致性报告.md

κ 判读（Landis & Koch 1977）：
  <0 差；0~0.2 轻微；0.2~0.4 一般；0.4~0.6 中等；0.6~0.8 较强；0.8~1.0 很强
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

from openpyxl import load_workbook  # noqa: E402

A_PATH = ROOT / "data" / "label" / "人工标注表.xlsx"
LABEL_DIR = ROOT / "data" / "label"
OUT_JSON = ROOT / "reports" / "iaa.json"
OUT_MD = ROOT / "reports" / "标注一致性报告.md"


def read_labels(path: Path, sheet_hint: str) -> dict[str, int]:
    wb = load_workbook(path, data_only=True)
    ws = wb[sheet_hint] if sheet_hint in wb.sheetnames else wb.active
    hdr = [str(c.value or "").strip() for c in ws[1]]
    i_id = hdr.index("记录编号")
    i_lab = hdr.index("label")
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        rid = "" if row[i_id] is None else str(row[i_id]).strip()
        lab = "" if row[i_lab] is None else str(row[i_lab]).strip()
        if rid and lab in ("0", "1", "0.0", "1.0"):
            out[rid] = int(float(lab))
    return out


def kappa_level(k: float) -> str:
    if k == k and k >= 0.8:
        return "很强（almost perfect）"
    if k >= 0.6:
        return "较强（substantial）"
    if k >= 0.4:
        return "中等（moderate）"
    if k >= 0.2:
        return "一般（fair）"
    return "较弱（slight/poor）"


def main(people_dir: Path | None = None, tag: str = "") -> int:
    pdir = people_dir or (LABEL_DIR / "by_person")
    out_json = ROOT / "reports" / (f"iaa{tag}.json" if tag else "iaa.json")
    out_md = ROOT / "reports" / (f"标注一致性报告{tag}.md" if tag else "标注一致性报告.md")
    if not A_PATH.exists():
        raise SystemExit(f"找不到 {A_PATH.name}")
    if not people_dir and not list(LABEL_DIR.glob("双标样本_*.xlsx")):
        raise SystemExit("还没有双标样本，先运行：python scripts/make_iaa_sample.py --who B")

    # 第二轮（指定 --dir）时，所有人都在同一个目录里，不再单读 A 的 Excel
    a = read_labels(A_PATH, "标注表") if not people_dir else {}

    # 标注人来源有两类，合并读取：
    #   1) 在线的 data/label/by_person/<姓名>.csv（优先，按人名分目录）
    #   2) 离线的 双标样本_B.xlsx / C.xlsx
    others = {}
    for f in sorted(pdir.glob("*.csv")) if pdir.exists() else []:
        with io.open(f, encoding="utf-8-sig", newline="") as fh:
            lab = {r["记录编号"]: int(r["label"]) for r in csv.DictReader(fh)
                   if (r.get("label") or "").strip() in ("0", "1")}
        if lab:
            others[f.stem] = lab
    for f in sorted(LABEL_DIR.glob("双标样本_*.xlsx")):
        who = f.stem.split("_")[-1]
        if who in others:
            continue
        lab = read_labels(f, "标注")
        if lab:
            others[who] = lab
    people = ({**({"A": a} if a else {}), **others})
    if not people:
        raise SystemExit("没有找到任何标注结果，先运行 python scripts/make_iaa_sample.py --who B")

    # 以所有标注人都标了的记录为准
    common = set(next(iter(people.values())))
    for lab in others.values():
        common &= set(lab)
    ids = sorted(common)
    if not ids:
        raise SystemExit("没有共同记录编号，检查样本是否同一批")
    n = len(ids)

    def pair_kappa(x: dict, y: dict) -> dict:
        both1 = sum(1 for i in ids if x[i] == 1 and y[i] == 1)
        both0 = sum(1 for i in ids if x[i] == 0 and y[i] == 0)
        x1y0 = sum(1 for i in ids if x[i] == 1 and y[i] == 0)
        x0y1 = sum(1 for i in ids if x[i] == 0 and y[i] == 1)
        po = (both1 + both0) / n
        px = (both1 + x1y0) / n
        py = (both1 + x0y1) / n
        pe = px * py + (1 - px) * (1 - py)
        k = (po - pe) / (1 - pe) if pe < 1 else 1.0
        return dict(p_o=po, p_e=pe, kappa=k, both1=both1, both0=both0,
                    x1y0=x1y0, x0y1=x0y1)

    # 两两一致性
    names = sorted(people)
    pairs = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pairs[f"{names[i]}-{names[j]}"] = pair_kappa(people[names[i]], people[names[j]])

    # 多数投票（平票时以 A 为准）
    agree_all = 0
    for rid in ids:
        votes = [people[p][rid] for p in names]
        if len(set(votes)) == 1:
            agree_all += 1

    kappa = pairs[f"{names[0]}-{names[1]}"]["kappa"]
    level = kappa_level(kappa)
    data = {"n": n, "kappa": round(kappa, 4), "level": level,
            "p_o": round(pairs[f"{names[0]}-{names[1]}"]["p_o"], 4),
            "pairs": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                          for kk, vv in v.items()} for k, v in pairs.items()},
            "unanimous": agree_all, "unanimous_rate": round(agree_all / n, 4)}

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# 标注一致性报告", "",
         f"- 标注人数：**{len(names)}**（{'、'.join(names)}）",
         f"- 重叠样本：**{n}** 条",
         f"- 三人完全一致：{agree_all} / {n}（{agree_all / n:.1%}）", "",
         "## 两两一致性", "",
         "| 对比 | 观察一致率 | κ | 判读 |", "|---|---|---|---|"]
    for kk, v in pairs.items():
        L.append(f"| {kk} | {v['p_o']:.1%} | **{v['kappa']:.3f}** | {kappa_level(v['kappa'])} |")
    L += ["", "## 列联表（A 与第一位标注人）", ""]
    p0 = pairs[f"{names[0]}-{names[1]}"]
    L += ["| | 对方判 0 | 对方判 1 |", "|---|---|---|",
          f"| **A 判 0** | {p0['both0']} | {p0['x0y1']} |",
          f"| **A 判 1** | {p0['x1y0']} | {p0['both1']} |", "",
          "## 判读", ""]
    if kappa >= 0.6:
        L.append("κ ≥ 0.6，属于较强一致，**标注集可作为模型评测基准**。")
    elif kappa >= 0.4:
        L.append("κ 在 0.4~0.6，属中等一致。建议对分歧条目复盘一次，统一口径后再报告。")
    else:
        L.append("κ < 0.4，一致性偏弱。**需要重新统一判定口径**（尤其「AI 是否为核心」这条），"
                 "否则标注集不宜作为评测基准。")
    L += ["", "> 备注：κ 只反映标注人是否按同一套标准判断，不代表标准本身对不对——"
              "标准以赛题四条规则为准。分歧条目建议复盘一次，形成统一口径说明写进论文。"]
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"重叠 {n} 条 | 标注人 {'、'.join(names)} | 三人全一致 {agree_all}/{n}")
    for kk, v in pairs.items():
        print(f"  {kk}: 一致率 {v['p_o']:.1%}  κ = {v['kappa']:.3f}（{kappa_level(v['kappa'])}）")
    print(f"  列联表 {names[0]}-{names[1]}: 都判1 {p0['both1']} / 都判0 {p0['both0']} / "
          f"{names[0]}1{names[1]}0 {p0['x1y0']} / {names[0]}0{names[1]}1 {p0['x0y1']}")
    print(f"报告 -> {out_md}")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None, help="标注目录，如 data/label/by_person_round2")
    ap.add_argument("--tag", default="", help="报告后缀，如 _round2")
    args = ap.parse_args()
    d = None
    if args.dir:
        d = Path(args.dir) if Path(args.dir).is_absolute() else ROOT / args.dir
    sys.exit(main(d, args.tag))
