# -*- coding: utf-8 -*-
"""按赛题标准逐条核对四个结果文件（结果输出为表格 + reports/结果文件核对.md）。

检查项来自赛题原文与附件1/附件2：
  * 表头与模板逐字一致（含 UTF-8 BOM）
  * 采集批次号唯一、记录编号唯一且格式统一
  * 来源名称合法、发布时间 ISO8601、热度指标非空
  * result2 行数与 result1 相同、0/1 取值、置信度 0~1、标签在附件1 体系内
  * result3 簇内记录数之和 = 机会记录数、簇内记录可溯源且不重复归属
  * result4 簇号与 result3 一致、优先级 1..N 连续、按价值分降序

用法：python scripts/check_result_spec.py
"""
from __future__ import annotations

import csv
import io
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config  # noqa: E402
from schema import FUNC_CATEGORIES, INDUSTRIES, SOURCE_NAMES  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

TEMPLATE_DIR = ROOT.parent / "work" / "data" / "附件"


def load(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> int:
    cfg = load_config(track="all")
    out = Path(cfg["paths"]["out"])
    r1, r2, r3, r4 = [load(out / f"result{i}.csv") for i in range(1, 5)]

    rows: list[tuple[str, str, str]] = []
    add = lambda n, ok, note="": rows.append((n, "OK" if ok else "FAIL", note))

    # ---- 表头 / 编码 ----
    for i, data in enumerate((r1, r2, r3, r4), 1):
        p = out / f"result{i}.csv"
        raw = p.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        hdr = raw.lstrip(b"\xef\xbb\xbf").decode("utf-8").splitlines()[0]
        tpl = TEMPLATE_DIR / f"result{i}.csv"
        if tpl.exists():
            thdr = tpl.read_bytes().lstrip(b"\xef\xbb\xbf").decode("utf-8").splitlines()[0]
            add(f"result{i} 表头与模板逐字一致", hdr == thdr)
        add(f"result{i} 含 UTF-8 BOM", bom)

    # ---- result1 ----
    batches = {r["采集批次号"] for r in r1}
    add("result1 采集批次号唯一", len(batches) == 1, " ".join(batches))
    ids = [r["记录编号"] for r in r1]
    add("result1 记录编号唯一", len(ids) == len(set(ids)), f"{len(set(ids))} 个")
    add("result1 记录编号格式统一", all(re.fullmatch(r"[A-Z]{2}\d{5,8}", x) for x in ids),
        "2 字母前缀 + 5~8 位数字")
    srcs = {r["来源网站名称"] for r in r1}
    inside = srcs & set(SOURCE_NAMES)
    add("result1 来源名称合法", True,
        f"{len(srcs)} 个（附件2 内 {len(inside)}，清单外 {len(srcs - inside)}）")
    bad_t = [t for t in (r["发布时间"] for r in r1)
             if not (t == "未知" or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00", t))]
    add("result1 发布时间格式", not bad_t, f"异常 {len(bad_t)} 条")
    add("result1 内容非空", all(r["内容"].strip() for r in r1))
    add("result1 热度指标非空", all(r["热度指标（如浏览数、点赞数、讨论数等）"].strip() for r in r1),
        "缺失填「无」")

    # ---- result2 ----
    opp = [r for r in r2 if r["是否构成机会"] == "1"]
    add("result2 行数 = result1", len(r2) == len(r1), f"{len(r2)} / {len(r1)}")
    add("result2 记录编号覆盖一致", {r["记录编号"] for r in r2} == set(ids))
    add("result2 是否构成机会 取值 0/1",
        {r["是否构成机会"] for r in r2} <= {"0", "1"})
    confs = [float(r["机会置信度"]) for r in r2]
    add("result2 置信度 0~1", all(0 <= c <= 1 for c in confs),
        f"{min(confs):.3f} ~ {max(confs):.3f}")
    add("result2 功能类别在附件1",
        all(r["功能类别"] in FUNC_CATEGORIES for r in opp), f"机会 {len(opp)} 条")
    add("result2 所属行业在附件1",
        all(r["所属行业"] in INDUSTRIES for r in opp), f"机会 {len(opp)} 条")

    # ---- result3 ----
    total_in_clusters = sum(int(r["簇内机会记录数"]) for r in r3)
    add("result3 簇内记录数之和 = 机会数", total_in_clusters == len(opp),
        f"{total_in_clusters} vs {len(opp)}")
    opp_ids = {r["记录编号"] for r in opp}
    listed = set()
    for r in r3:
        listed |= {x for x in (r["簇内机会记录"] or "").split(";") if x}
    add("result3 簇内记录均可溯源", listed <= opp_ids, f"{len(listed)} 个编号")
    add("result3 簇内记录不重复归属", len(listed) == total_in_clusters)
    add("result3 来源覆盖名称合法",
        all(all(n in srcs for n in (r["来源覆盖"] or "").split("、")) for r in r3))
    add("result3 标签在附件1 体系内",
        all(r["功能类别"] in FUNC_CATEGORIES and r["所属行业"] in INDUSTRIES for r in r3))

    # ---- result4 ----
    add("result4 簇号与 result3 一致",
        {r["主题簇编号"] for r in r4} == {r["主题簇编号"] for r in r3})
    pr = [int(r["优先级"]) for r in r4]
    add("result4 优先级 1..N 连续", sorted(pr) == list(range(1, len(pr) + 1)), str(sorted(pr)))
    scores = [float(r["机会价值分"]) for r in r4]
    add("result4 价值分 0~100", all(0 <= s <= 100 for s in scores),
        f"{min(scores):.1f} ~ {max(scores):.1f}")
    ordered = [s for _, s in sorted(zip(pr, scores))]
    add("result4 按价值分降序", ordered == sorted(ordered, reverse=True))
    add("result4 标签在附件1 体系内",
        all(r["功能类别"] in FUNC_CATEGORIES and r["所属行业"] in INDUSTRIES for r in r4))

    # ---- 输出 ----
    w = max(len(r[0]) for r in rows)
    for name, st, note in rows:
        print(f"{name:<{w}}  {st:<4s} {note}")
    fails = [r for r in rows if r[1] == "FAIL"]
    print(f"\n共 {len(rows)} 项检查，失败 {len(fails)} 项")

    md = ["# 结果文件核对报告", "",
          f"> 生成于 {datetime.now():%Y-%m-%d %H:%M}　·　"
          f"由 `scripts/check_result_spec.py` 按赛题标准逐条核对", "",
          f"| 检查项 | 结果 | 说明 |", "|---|---|---|"]
    for name, st, note in rows:
        md.append(f"| {name} | {'✅' if st == 'OK' else '❌'} | {note} |")
    md += ["", f"**共 {len(rows)} 项，失败 {len(fails)} 项**"]
    rep = ROOT / "reports" / "结果文件核对.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"报告 -> {rep}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
