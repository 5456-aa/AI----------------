# -*- coding: utf-8 -*-
"""交付前自检：四个 CSV 的表头、编码、交叉一致性。

用法：python validate.py
退出码 0 = 全部通过；1 = 有阻断性问题（必须修）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from io_utils import load_config, read_csv_dicts
from schema import (ALL_RESULT_COLS, FUNC_CATEGORIES, INDUSTRIES, SOURCE_NAMES)

ERRORS: list[str] = []
WARNS: list[str] = []


def err(msg: str) -> None:
    ERRORS.append(msg)


def warn(msg: str) -> None:
    WARNS.append(msg)


def check_bom_and_header(path: Path, key: str) -> list[dict]:
    if not path.exists():
        err(f"{path.name} 不存在")
        return []
    raw = path.read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        err(f"{path.name} 缺少 UTF-8 BOM（Excel 打开会乱码，模板是带 BOM 的）")

    header = raw.decode("utf-8-sig").splitlines()[0]
    got = [c.strip() for c in header.split(",")]
    want = ALL_RESULT_COLS[key]
    if got != want:
        err(f"{path.name} 表头不一致\n    期望: {want}\n    实际: {got}")
    return read_csv_dicts(path)


def main(argv=None) -> int:
    import argparse
    from io_utils import TRACKS

    ap = argparse.ArgumentParser(description="交付前自检")
    ap.add_argument("--track", default="all", help="赛道名或 all")
    args = ap.parse_args(argv)

    cfg = load_config(track=args.track)
    out = Path(cfg["paths"]["out"])
    print(f"校验目录：{out}（赛道：{args.track}）")

    r1 = check_bom_and_header(out / "result1.csv", "result1")
    r2 = check_bom_and_header(out / "result2.csv", "result2")
    r3 = check_bom_and_header(out / "result3.csv", "result3")
    r4 = check_bom_and_header(out / "result4.csv", "result4")

    # ---- 行数 ----
    if r1 and r1[0].get("采集批次号", "").startswith("DEMO"):
        warn("result1 的批次号以 DEMO 开头 —— 这是演示数据，提交前务必换成真实采集批次！")

    if len(r2) != len(r1):
        err(f"result2 行数({len(r2)}) != result1 行数({len(r1)})：每条清洗记录都要有判别结果")

    # ---- 主键一致性 ----
    ids1 = {r["记录编号"] for r in r1}
    ids2 = {r["记录编号"] for r in r2}
    if ids1 and ids2 and ids1 != ids2:
        err(f"result1 与 result2 的记录编号集合不一致（差异 {len(ids1 ^ ids2)} 个）")

    # ---- 记录编号唯一性（跨来源撞号会导致合并后出现 DS00004-00 这类补丁编号）----
    dup_ids = [k for k, v in __import__("collections").Counter(
        r["记录编号"] for r in r1).items() if v > 1]
    if dup_ids:
        err(f"result1 存在重复记录编号 {len(dup_ids)} 个（示例：{dup_ids[:3]}），"
            f"通常是采集时为每个来源重置了计数器")
    if any("-" in r["记录编号"] for r in r1):
        warn("存在形如 DS00004-00 的补丁编号 —— 说明采集阶段记录编号撞号了，建议重新采集")

    # ---- 标签合法性 ----
    for r in r2:
        if r.get("是否构成机会") not in ("0", "1"):
            err(f"result2 记录 {r.get('记录编号')} 的“是否构成机会”不是 0/1：{r.get('是否构成机会')!r}")
            break
    for r in r2:
        if r.get("是否构成机会") == "1":
            if r.get("功能类别") not in FUNC_CATEGORIES:
                err(f"result2 记录 {r.get('记录编号')} 功能类别不在附件1：{r.get('功能类别')!r}")
                break
            if r.get("所属行业") not in INDUSTRIES:
                err(f"result2 记录 {r.get('记录编号')} 所属行业不在附件1：{r.get('所属行业')!r}")
                break
    try:
        for r in r2:
            v = float(r.get("机会置信度") or "nan")
            if not (0.0 <= v <= 1.0):
                err(f"result2 记录 {r.get('记录编号')} 置信度越界：{v}")
                break
    except ValueError:
        err("result2 存在无法解析为数字的“机会置信度”")

    # ---- 来源名称 ----
    for r in r1:
        if r.get("来源网站名称") not in SOURCE_NAMES:
            warn(f"来源名称不在附件2 规范清单：{r.get('来源网站名称')!r}"
                 f"（记录 {r.get('记录编号')}）")
            break

    # ---- 任务三一致性（最关键的一条）----
    n_opp = sum(1 for r in r2 if r.get("是否构成机会") == "1")
    total_in_clusters = 0
    cluster_ids = set()
    for r in r3:
        cluster_ids.add(r.get("主题簇编号", ""))
        try:
            total_in_clusters += int(r.get("簇内机会记录数") or 0)
        except ValueError:
            err(f"result3 簇内机会记录数不是整数：{r.get('簇内机会记录数')!r}")
        n_listed = len([x for x in (r.get("簇内机会记录") or "").split(";") if x.strip()])
        if n_listed and n_listed != int(r.get("簇内机会记录数") or -1):
            err(f"result3 {r.get('主题簇编号')}：列出的记录编号数({n_listed}) "
                f"与“簇内机会记录数”({r.get('簇内机会记录数')})不一致")
        if int(r.get("簇内机会记录数") or 0) < 2:
            warn(f"result3 {r.get('主题簇编号')} 只有 1 条记录 —— 单条不构成“主题簇”，"
                 f"建议合并或说明处理方式")
    if n_opp and total_in_clusters != n_opp:
        err(f"result3 簇内机会记录数之和({total_in_clusters}) != result2 机会记录数({n_opp})")

    # ---- 任务四一致性 ----
    r4_ids = {r.get("主题簇编号", "") for r in r4}
    if cluster_ids and r4_ids != cluster_ids:
        err(f"result3 与 result4 的主题簇编号集合不一致：{sorted(cluster_ids ^ r4_ids)}")
    priorities = [r.get("优先级") for r in r4]
    if priorities and sorted(int(p) for p in priorities) != list(range(1, len(priorities) + 1)):
        err(f"result4 优先级应为 1..N 连续整数，实际：{priorities}")
    scores = [float(r.get("机会价值分") or 0) for r in r4]
    if scores:
        sorted_by_score = [s for _, s in sorted(zip(priorities, scores), key=lambda x: int(x[0]))]
        if sorted_by_score != sorted(sorted_by_score, reverse=True):
            err("result4 未按机会价值分降序排列（优先级 1 应为最高分）")

    # ---- 任务三/四 的标签必须也在附件1 体系内 ----
    for name, rows in (("result3", r3), ("result4", r4)):
        for r in rows:
            if r.get("功能类别") not in FUNC_CATEGORIES:
                err(f"{name} {r.get('主题簇编号')} 功能类别不在附件1：{r.get('功能类别')!r}")
                break
            if r.get("所属行业") not in INDUSTRIES:
                err(f"{name} {r.get('主题簇编号')} 所属行业不在附件1：{r.get('所属行业')!r}")
                break

    # ---- 标注集漂移检测（重新采集后编号可能对不上）----
    try:
        import csv as _csv
        lab_path = Path("data/label/label_set_mapped.csv")
        if lab_path.exists():
            with open(lab_path, encoding="utf-8-sig", newline="") as f:
                labs = [r for r in _csv.DictReader(f)
                        if (r.get("label") or "").strip() in ("0", "1")]
            cur = {r["记录编号"] for r in r2}
            hit = sum(1 for r in labs
                      if (r.get("记录编号") or "").strip() in cur)
            ratio = hit / max(len(labs), 1)
            if ratio < 0.8:
                err(f"标注集漂移：仅 {hit}/{len(labs)}（{ratio:.0%}）标注能找到对应记录，"
                    f"先运行 python scripts/remap_labels.py")
            else:
                warn(f"标注集对齐率 {hit}/{len(labs)}（{ratio:.0%}）")
    except Exception as exc:
        warn(f"标注漂移检测未执行：{exc}")

    # ---- 密钥泄漏 ----
    try:
        import security
        leaks = security.scan()
        if leaks:
            security.trip(leaks, "validate.py 交付自检")
            for f in leaks[:5]:
                err(f"密钥泄漏：{f.format()}")
            err(f"共 {len(leaks)} 处疑似密钥，已触发熔断（标记文件 .leak_alert）")
        if not Path(".gitignore").exists() or ".env" not in Path(".gitignore").read_text(
                encoding="utf-8", errors="ignore"):
            err(".gitignore 未排除 .env —— 打包/提交时会把密钥带上")
    except Exception as exc:
        warn(f"密钥自检未执行：{exc}")

    # ---- 输出 ----
    print("=" * 68)
    print(f"result1 {len(r1):>4} 行 | result2 {len(r2):>4} 行（机会 {n_opp}）"
          f" | result3 {len(r3):>3} 簇 | result4 {len(r4):>3} 簇")
    print("=" * 68)
    for w in WARNS:
        print(f"[警告] {w}")
    for e in ERRORS:
        print(f"[错误] {e}")
    print("-" * 68)
    if ERRORS:
        print(f"❌ 未通过：{len(ERRORS)} 个错误，{len(WARNS)} 个警告")
        return 1
    print(f"✅ 全部通过（{len(WARNS)} 个警告）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
