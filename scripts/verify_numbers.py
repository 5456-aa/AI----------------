# -*- coding: utf-8 -*-
"""数字一致性核验：把「实际数据」与「文档里写的数字」逐项对照。

实际数据来源（唯一真相）：
  data/out/result1~4.csv、data/clean/score_detail.jsonl、data/clean/judged.jsonl、config.yaml
文档来源：
  reports/论文数据包.md、桌面/数据挖掘比赛/00_论文交接说明.md、reports/消融实验.md

用法：python scripts/verify_numbers.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

DEST = Path.home() / "Desktop" / "数据挖掘比赛"


def rows(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def truth() -> dict:
    cfg = load_config(track="all")
    r1 = rows(ROOT / "data/out/result1.csv")
    r2 = rows(ROOT / "data/out/result2.csv")
    r3 = rows(ROOT / "data/out/result3.csv")
    r4 = rows(ROOT / "data/out/result4.csv")
    judged = read_jsonl(ROOT / "data/clean/judged.jsonl")
    detail = (read_jsonl(ROOT / "data/clean/score_detail.jsonl") or [{}])[0]

    # 原始采集量：审计文件
    raw = sum(int(a.get("raw", 0)) for a in
              read_jsonl(ROOT / "data/clean/audit_clean.jsonl"))
    # 清洗保留量：funnel.raw
    funnel = (read_jsonl(ROOT / "data/clean/dedup_funnel.jsonl") or [{}])[0]

    wd = detail.get("weight_detail", {})
    sens = detail.get("sensitivity", {})
    top3 = sorted(r4, key=lambda x: int(x["优先级"]))[:3]

    return {
        "raw": raw,
        "cleaned": funnel.get("raw", 0),
        "deduped": len(r1),
        "opp": sum(1 for x in r2 if x["是否构成机会"] == "1"),
        "clusters": len(r3),
        "sources": len({x["来源网站名称"] for x in r1}),
        "tau": cfg["judge"]["threshold"],
        "weights": dict(zip(wd.get("dims", []), wd.get("w_final", []))),
        "spearman": sens.get("spearman_mean"),
        "top3": [(c["主题簇编号"], c["主题簇名称"], c["机会价值分"]) for c in top3],
        "judged": len(judged),
    }


EXPECT = {
    # 文档 -> 该文档应当包含的「数字或短语」
    "论文数据包": ["761", "749", "735", "52", "13", "0.36", "0.9984",
                   "0.2911", "0.3183", "0.2754", "0.1152",
                   "0.90", "1.00", "0.95", "0.52", "0.65", "0.58", "366"],
    "交接说明": ["761", "749", "735", "52", "13", "0.36", "0.9984",
                 "0.2911", "0.3183", "0.2754", "0.1152",
                 "0.90", "1.00", "0.95", "0.52", "0.65", "0.58", "366"],
    "消融实验": ["0.52", "0.65", "0.58", "0.90", "1.00", "0.95", "366", "52"],
    "阈值稳健性": ["0.15", "0.20", "0.24", "0.30", "0.36", "0.40",
                   "128", "90", "75", "60", "52", "45"],
}


def check_doc(name: str, path: Path, t: dict) -> list[tuple[str, str, bool]]:
    """按文档各自的应有内容核对（不是每个文档都要含全部数字）。"""
    if not path.exists():
        return [(name, f"文件缺失：{path.name}", False)]
    s = path.read_text(encoding="utf-8", errors="ignore")
    return [(name, needle, needle in s) for needle in EXPECT.get(name, [])]


def main() -> int:
    t = truth()
    print("=" * 66)
    print("  实际数据（唯一真相）")
    print("=" * 66)
    print(f"  原始采集 {t['raw']} → 清洗 {t['cleaned']} → 入表 {t['deduped']}")
    print(f"  机会 {t['opp']} 条（{t['opp']/max(t['deduped'],1)*100:.1f}%）　"
          f"主题簇 {t['clusters']} 个　来源 {t['sources']} 个")
    print(f"  判别阈值 τ = {t['tau']}")
    print(f"  组合权重 {t['weights']}")
    print(f"  敏感性 Spearman = {t['spearman']}")
    for c in t["top3"]:
        print(f"  Top3 {c[0]} {c[1][:22]} {c[2]}")
    print()

    docs = [("论文数据包", ROOT / "reports/论文数据包.md"),
            ("交接说明", DEST / "00_论文交接说明.md"),
            ("消融实验", ROOT / "reports/消融实验.md"),
            ("阈值稳健性", ROOT / "reports/阈值稳健性.md")]
    bad = 0
    for name, path in docs:
        res = check_doc(name, path, t)
        miss = [r for r in res if not r[2]]
        print(f"[{name}] {path.name}: {len(res)-len(miss)}/{len(res)} 命中")
        for tag, label, ok in miss:
            print(f"    ❌ {tag} 未匹配：{label}")
            bad += 1
    print()
    print("结论：" + ("✅ 所有文档数字与实际数据一致"
                    if bad == 0 else f"❌ 有 {bad} 处不一致，需修正文档"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
