# -*- coding: utf-8 -*-
"""发起一个新需求（新批次）：创建赛道 → 采集 → 清洗判别聚类评分 → 导出。

赛题要求「用户可多次发起需求，发起一次需求则触发一次采集，即为一个批次，
各批次分析相互独立」。本脚本就是那个入口。

用法：
    python scripts/new_batch.py --direction "医疗问诊" 
    python scripts/new_batch.py --direction "法律合同审查" --keywords "合同,审查,条款" --limit 80
    python scripts/new_batch.py --direction "医疗问诊" --collect-only
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import create_track, load_config, make_batch_id  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass


def slugify(direction: str) -> str:
    """赛道标识必须稳定：用 sha1 而不是内置 hash()（后者受 PYTHONHASHSEED 影响）。"""
    import hashlib
    base = re.sub(r"[^a-z0-9]+", "-", direction.lower()).strip("-")
    digest = hashlib.sha1(direction.encode("utf-8")).hexdigest()[:4]
    return (base or "track") + "-" + str(int(digest, 16) % 10000)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="发起新需求（新批次）")
    ap.add_argument("--direction", required=True, help="需求方向，如「医疗问诊」")
    ap.add_argument("--keywords", default="", help="检索词，逗号分隔；不给则由方向自动扩展")
    ap.add_argument("--sources", default="", help="来源，逗号分隔；默认 GitHub/掘金/Stack Overflow/博客园")
    ap.add_argument("--limit", type=int, default=100, help="每源条数上限")
    ap.add_argument("--collect-only", action="store_true", help="只采集，不跑分析")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--offline", action="store_true",
                    help="只用缓存、不调用 API（界面首页默认开启，保证可复现）")
    args = ap.parse_args(argv)

    direction = args.direction.strip()
    keywords = [k.strip() for k in re.split(r"[,，、]", args.keywords) if k.strip()]
    sources = [s.strip() for s in re.split(r"[,，、]", args.sources) if s.strip()]

    # 关键词自动扩展：方向本身 + 常见需求句式组合
    if not keywords:
        keywords = [
            direction,
            f"{direction} 有没有 工具",
            f"{direction} 自动化",
            f"{direction} 效率 痛点",
        ]

    slug = args.slug or slugify(direction)
    payload = create_track(direction, keywords, sources, slug)

    print("=" * 62)
    print(f"slug={slug}")          # 供界面解析
    print(f"新建需求方向：{direction}")
    print(f"  赛道标识：{slug}")
    print(f"  记录编号前缀：{payload['record_prefix']}")
    print(f"  检索词（{len(keywords)} 个）：")
    for k in keywords:
        print(f"    - {k}")
    print(f"  来源：{'、'.join(payload['sources'])}")
    print("=" * 62)

    py = sys.executable
    batch = make_batch_id(load_config(track="all"))

    print(f"\n[1/2] 采集中（批次 {batch}）…")
    rc = subprocess.run([py, str(ROOT / "run_collect.py"), "--track", slug,
                         "--limit", str(args.limit), "--batch", batch]).returncode
    if rc != 0:
        print("采集失败，终止。")
        return rc

    if args.collect_only:
        print("\n只采集，不分析。稍后可运行：")
        print(f"  python run_all.py --track {slug} --batch {batch}")
        return 0

    print(f"\n[2/2] 分析中（清洗 → 去重 → 判别 → 聚类 → 评分 → 导出）…")
    run_cmd = [py, str(ROOT / "run_all.py"), "--track", slug, "--batch", batch,
               "--force"]
    if args.offline:
        run_cmd.append("--offline")
    rc = subprocess.run(run_cmd).returncode
    if rc != 0:
        print("分析失败。")
        return rc

    cfg = load_config(track=slug)
    out = Path(cfg["paths"]["out"])
    print("\n" + "=" * 62)
    print(f"完成。本批次结果目录：{out}")
    for f in sorted(out.glob("*.csv")):
        print(f"  {f.name}")
    print("\n查看可视化：")
    print(f"  streamlit run ui/app.py     # 左侧赛道选「{direction}」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
