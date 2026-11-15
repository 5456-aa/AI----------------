# -*- coding: utf-8 -*-
"""生成人工标注集（用于标定判别阈值 τ）。

抽样策略（论文里要写）：
  * 正例层：大模型判为机会的，全部纳入（通常 30~40 条）；
  * 边界层：置信度在 τ 附近 ±0.15 的，全部纳入（最难判、信息量最大）；
  * 随机层：其余随机抽，补足到目标条数。
分层抽样能保证标注集既有区分度、又覆盖真实分布。

用法：python scripts/make_label_set.py --n 120
产出：data/label/label_set.csv（含 label 空列，交给人工填）
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120, help="目标条数")
    ap.add_argument("--track", default="all")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    cfg = load_config(track=args.track)
    rows = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    if not rows:
        raise SystemExit("没有 judged.jsonl，先跑 run_all.py")

    tau = float(cfg["judge"]["threshold"])
    random.seed(args.seed)

    pos = [r for r in rows if r.get("is_opportunity") == 1]
    border = [r for r in rows if r.get("is_opportunity") != 1
              and abs(float(r.get("confidence", 0)) - tau) <= 0.15]
    rest = [r for r in rows if r not in pos and r not in border]

    picked = list(pos) + list(border)
    need = max(args.n - len(picked), 0)
    if need and rest:
        picked += random.sample(rest, min(need, len(rest)))

    random.shuffle(picked)

    out_dir = ROOT / "data" / "label"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "label_set.csv"

    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "记录编号", "来源", "标题", "正文", "发布时间",
                    "模型判断", "模型置信度", "label", "备注"])
        for i, r in enumerate(picked, 1):
            w.writerow([
                i, r.get("record_id", ""), r.get("source", ""),
                r.get("title", ""), r.get("clean_text", "")[:600],
                r.get("published_at", ""),
                "1" if r.get("is_opportunity") == 1 else "0",
                f"{float(r.get('confidence', 0)):.3f}", "", "",
            ])

    print(f"标注集：{out_csv}")
    print(f"  总数 {len(picked)} 条（正例层 {len(pos)} + 边界层 {len(border)} + 随机层 "
          f"{len(picked) - len(pos) - len(border)}）")
    print(f"  模型当前判为机会 {len(pos)} 条，τ = {tau}")
    print("\n下一步（二选一）：")
    print("  A. 双击「标注工具.bat」，点按钮标 —— 推荐，会自动存盘")
    print("  B. 用 Excel 打开上面 CSV，在 label 列填 1/0")
    print("  标完后运行：python scripts/tune_threshold.py --tune data/label/label_set.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
