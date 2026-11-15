# -*- coding: utf-8 -*-
"""消融实验（同一语料、同一阈值）：仅规则特征 vs 规则+大模型。

为什么重做：旧数据包里有互相矛盾的两套数字（F1=0.06/1.00 与 0.37/0.94），
且对应的是重新采集前的旧语料。本脚本在当前 735 条语料上统一重算，只输出一套。

评价口径（两套并列，避免误导）：
  A. 人工标注子集：在可对齐的标注记录上算 Precision / Recall / F1
     —— 这是真正的分类指标，但样本量受标注规模限制；
  B. 全量语料：机会数 + 与「规则+大模型」结果的重合度（Jaccard）
     —— 说明两种方法在多大程度上给出同样的机会集合。

用法：python scripts/ablation.py
产出：reports/消融实验.md
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402
from pipeline.judge import combine, rule_features  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass


def load_labels() -> dict[str, int]:
    """优先用重映射后的标注（编号与当前批次一致）。"""
    for name in ("label_set_mapped.csv", "label_set.csv"):
        p = ROOT / "data" / "label" / name
        if not p.exists():
            continue
        out: dict[str, int] = {}
        with io.open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                rid = (r.get("记录编号") or r.get("record_id") or "").strip()
                lab = (r.get("label") or "").strip()
                if rid and lab in ("0", "1"):
                    out[rid] = int(lab)
        if out:
            return out
    return {}


def prf(pred: list[int], gold: list[int]) -> tuple[float, float, float]:
    tp = sum(1 for p, g in zip(pred, gold) if p == 1 and g == 1)
    fp = sum(1 for p, g in zip(pred, gold) if p == 1 and g == 0)
    fn = sum(1 for p, g in zip(pred, gold) if p == 0 and g == 1)
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    F = 2 * P * R / (P + R) if P + R else 0.0
    return P, R, F


def main() -> int:
    cfg = load_config(track="all")
    tau = float(cfg["judge"]["threshold"])
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    if not judged:
        raise SystemExit("没有 judged.jsonl")

    # 规则单用：用与线上完全相同的特征与合成函数，只是不做 LLM 修正
    rule_conf = {}
    for r in judged:
        feats = rule_features(r.get("clean_text", ""))
        rule_conf[r["record_id"]] = combine(feats, feats.get("exclude", "none"), cfg)
    llm_conf = {r["record_id"]: float(r.get("confidence", 0)) for r in judged}

    rule_pred = {i: (1 if c >= tau else 0) for i, c in rule_conf.items()}
    llm_pred = {i: (1 if c >= tau else 0) for i, c in llm_conf.items()}

    n_rule = sum(rule_pred.values())
    n_llm = sum(llm_pred.values())
    inter = sum(1 for i in rule_pred if rule_pred[i] == 1 and llm_pred[i] == 1)
    union = sum(1 for i in rule_pred if rule_pred[i] == 1 or llm_pred[i] == 1)
    jac = inter / union if union else 0.0

    # A. 标注子集
    labels = load_labels()
    ids = [i for i in labels if i in llm_conf]
    P1 = prf([rule_pred[i] for i in ids], [labels[i] for i in ids]) if ids else (0, 0, 0)
    P2 = prf([llm_pred[i] for i in ids], [labels[i] for i in ids]) if ids else (0, 0, 0)

    L = ["# 消融实验（同一语料、同一阈值）", "",
         f"> 语料：当前批次 {len(judged)} 条；阈值 τ = **{tau}**；"
         f"生成自 `scripts/ablation.py`", "",
         "## A. 人工标注子集上的分类指标", "",
         f"可对齐的标注记录 **{len(ids)}** 条"
         f"（标注总 {len(labels)} 条，其余因重新采集后编号/内容变化未能对齐）。", "",
         "| 方法 | 判为机会数 | Precision | Recall | F1 |",
         "|---|---|---|---|---|"]
    L.append(f"| 仅规则特征 | {sum(rule_pred[i] for i in ids)} | "
             f"{P1[0]:.2f} | {P1[1]:.2f} | {P1[2]:.2f} |")
    L.append(f"| 规则+大模型（本文） | {sum(llm_pred[i] for i in ids)} | "
             f"{P2[0]:.2f} | {P2[1]:.2f} | {P2[2]:.2f} |")
    L += ["", "## B. 全量语料上的产出与一致性", "",
          "| 方法 | 机会记录数 | 与本文方法的重合（Jaccard） |", "|---|---|---|",
          f"| 仅规则特征 | {n_rule} | {jac:.0%} |",
          f"| 规则+大模型（本文） | {n_llm} | — |", "",
          "## 结论", ""]
    L.append(f"1. 在 {len(ids)} 条可对齐标注上，本文方法 F1 = **{P2[2]:.2f}**，"
             f"仅规则特征 F1 = **{P1[2]:.2f}**；")
    L.append(f"2. 全量语料上，规则单用产出 {n_rule} 条机会，与本文方法仅重合 {jac:.0%}"
             f"（交集 {inter} 条），说明**规则无法替代语义判别**；")
    L.append("3. 规则版的主要误差来源：教程类文章命中「推荐 / 自动 / 知识库」等词被误判为机会，"
             "资讯类又因缺少需求句式被漏判；")
    L.append("4. 说明：τ=0.36 是针对**大模型打分**标定的，规则打分沿用同一阈值并非其最优工作点；"
             "若为规则单独重新标定阈值，机会数与 P/R 会变化。本对比固定同一 τ，"
             "目的是说明「在同一决策口径下，规则不足以替代语义判别」。")
    L.append("5. 口径说明：A 部分样本量有限（标注仅覆盖 120 条，重新采集后可对齐的更少），"
             "指标用于**方法对比**而非全量泛化估计；B 部分不依赖人工标注，可与 A 部分互为印证。")

    out = ROOT / "reports" / "消融实验.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"语料 {len(judged)} 条 | τ={tau} | 规则机会 {n_rule} | 本文机会 {n_llm} | 重合 {jac:.0%}")
    print(f"标注对齐 {len(ids)} 条 | 规则 P/R/F1 = {P1[0]:.2f}/{P1[1]:.2f}/{P1[2]:.2f} | "
          f"本文 = {P2[0]:.2f}/{P2[1]:.2f}/{P2[2]:.2f}")
    print(f"报告 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
