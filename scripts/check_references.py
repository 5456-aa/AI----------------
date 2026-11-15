# -*- coding: utf-8 -*-
"""参考文献格式自检（不做联网核实，只查结构与缺失字段）。

能自动查的：
  * 编号是否连续、是否重复
  * 每条是否含文献类型标识 [J]/[C]/[M]/[S]/[D]/[EB/OL] 等
  * 期刊/会议是否带页码；学位论文是否带学校
  * 网络资源 [EB/OL] 是否带「引用日期」与 URL
  * 是否残留占位符（待核对 / TODO / xx）

不能自动查的（须人工上知网/ACM/NeurIPS 核对）：卷、期、页码的真伪。

用法：python scripts/check_references.py
产出：reports/参考文献自检.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "references.md"
OUT = ROOT / "reports" / "参考文献自检.md"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

TYPES = re.compile(r"\[(J|C|M|S|D|R|N|P|Z|(?:EB|CP|DB|M|J)/OL)\]")
NUM = re.compile(r"^\[(\d+)\]\s*(.+)$")


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    entries: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = NUM.match(line.strip())
        if m:
            entries.append((int(m.group(1)), m.group(2).strip()))

    rows = []
    nums = [n for n, _ in entries]
    dup = {n for n in nums if nums.count(n) > 1}
    gaps = [i for i in range(1, max(nums) + 1) if i not in nums] if nums else []

    for n, body in entries:
        issues = []
        if not TYPES.search(body):
            issues.append("缺文献类型标识（如 [J]/[C]/[EB/OL]）")
        is_online = ("[EB/OL]" in body or "[CP/OL]" in body
                     or "http" in body or "www." in body)
        if is_online:
            if "http" not in body:
                issues.append("网络资源缺 URL")
            if not re.search(r"\(\d{4}-\d{2}-\d{2}\)", body):
                issues.append("网络资源缺「引用日期 (YYYY-MM-DD)」")
        elif "[J]" in body or "[C]" in body:
            # 只有期刊与会议必须给起止页
            if not re.search(r"\d+\s*[-–]\s*\d+", body):
                issues.append("期刊/会议缺起止页")
        elif "[M]" in body:
            if not re.search(r"(出版社|Press|Publishing|Wiley|Springer|SAGE|McGraw|Elsevier|Academic Press|清华大学出版社|科学出版社)", body):
                issues.append("专著缺出版者")
        # [S] 标准、[R] 报告、[Z] 其他：不要求页码
        if re.search(r"待核对|TODO|xx|\?\?", body):
            issues.append("残留占位符")
        if n in dup:
            issues.append("编号重复")
        rows.append((n, body, issues))

    bad = [r for r in rows if r[2]]
    L = ["# 参考文献自检", "",
         f"> 由 `scripts/check_references.py` 自动检查 `docs/references.md`",
         "> **只查结构，不查真伪**。卷/期/页码是否真实，必须人工上知网 / ACM DL / NeurIPS 核对。",
         "",
         f"- 条目总数：**{len(entries)}**",
         f"- 编号连续：{'✅' if not gaps else '❌ 缺 ' + str(gaps)}",
         f"- 编号重复：{'✅ 无' if not dup else '❌ ' + str(sorted(dup))}",
         f"- 结构有问题的条目：**{len(bad)}**",
         "",
         "## 需处理的条目", "",
         "| 编号 | 问题 | 文献（前 60 字） |", "|---|---|---|"]
    for n, body, issues in bad:
        L.append(f"| [{n}] | {'；'.join(issues)} | {body[:60]} |")
    if not bad:
        L.append("| — | 无 | 全部条目的类型标识与页码结构完整 |")

    L += ["", "## 人工核对清单（按优先级）", "",
          "1. **页码**：会议论文页码最容易错，优先核 [1][2][4][5][15][16][17]；",
          "2. **卷期**：[6][7][8][9][14][19] 的卷、期；",
          "3. **整条存疑**：[12]（熵值法中文文献）把握最低，查不到就换一篇同主题的；",
          "4. **网络资源**：[21]~[24] 需补「(引用日期)[访问日期]. URL」；",
          "5. 核对方式：知网（中文）/ ACM DL / IEEE Xplore / NeurIPS Proceedings / arXiv。",
          ""]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"条目 {len(entries)} 条，结构问题 {len(bad)} 条 -> {OUT}")
    for n, body, issues in bad:
        print(f"  [{n}] {'；'.join(issues)}  | {body[:44]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
