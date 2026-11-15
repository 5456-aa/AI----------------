# -*- coding: utf-8 -*-
"""任务四：簇机会价值分与优先级。

维度（全部归一化到 0~100）：
  ① multi_source    多源指向度 = 簇内来源种类数
  ② scale           记录规模   = 簇内机会记录数
  ③ heat            互动热度   = 簇内热度分位均值（补充维度）
  ④ need_strength   需求强度   = 簇内机会置信度均值（补充维度）

权重：熵权法（客观） + AHP（主观）组合；并做 ±10% 扰动敏感性分析。
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Dict, List, Tuple

import numpy as np

from io_utils import get_logger, write_jsonl


# ---------------------------------------------------------------------------
# 维度计算
# ---------------------------------------------------------------------------
def _heat_score(rec: Dict[str, Any]) -> float:
    heat = rec.get("heat") or {}
    return float(sum(v for v in heat.values() if isinstance(v, (int, float))))


def raw_dimensions(clusters: List[Dict[str, Any]]) -> Tuple[np.ndarray, List[str]]:
    dims = ["multi_source", "scale", "heat", "need_strength"]
    rows = []
    for c in clusters:
        heats = [_heat_score(r) for r in c["records"]]
        rows.append([
            float(c["n_sources"]),
            float(c["n_records"]),
            float(np.mean(heats)) if heats else 0.0,
            float(c.get("mean_conf", 0.0)),
        ])
    return np.asarray(rows, dtype=float), dims


def normalize(M: np.ndarray, method: str = "minmax") -> np.ndarray:
    """minmax / log_minmax：映射到 0~100。全列相同则统一给 50 分（无区分度）。"""
    out = np.zeros_like(M, dtype=float)
    for j in range(M.shape[1]):
        col = M[:, j].astype(float)
        if method == "log_minmax":
            col = np.log1p(np.clip(col, 0, None))
        lo, hi = float(col.min()), float(col.max())
        if math.isclose(hi, lo):
            out[:, j] = 50.0
        else:
            out[:, j] = 100.0 * (col - lo) / (hi - lo)
    return out


# ---------------------------------------------------------------------------
# 权重
# ---------------------------------------------------------------------------
def entropy_weight(S: np.ndarray) -> np.ndarray:
    """熵权法。输入应为 0~100 的归一化矩阵。"""
    n, m = S.shape
    P = (S + 1e-9) / (S + 1e-9).sum(axis=0, keepdims=True)
    E = -(P * np.log(P)).sum(axis=0) / math.log(max(n, 2))
    d = 1.0 - E
    if d.sum() <= 0:
        return np.full(m, 1.0 / m)
    return d / d.sum()


def ahp_weight(weights: Dict[str, float], dims: List[str]) -> np.ndarray:
    w = np.array([float(weights.get(d, 1.0)) for d in dims], dtype=float)
    return w / w.sum()


def combine_weights(S: np.ndarray, cfg: Dict[str, Any],
                    dims: List[str]) -> Tuple[np.ndarray, Dict[str, Any]]:
    scfg = cfg["score"]
    w_e = entropy_weight(S)
    w_a = ahp_weight(scfg.get("ahp_weights", {}), dims)
    method = scfg.get("weight_method", "entropy+ahp")

    if method == "entropy":
        w, alpha = w_e, 1.0
    elif method == "ahp":
        w, alpha = w_a, 0.0
    else:
        alpha = float(scfg.get("alpha", 0.5))
        w = alpha * w_e + (1 - alpha) * w_a

    w = w / w.sum()
    detail = {
        "method": method,
        "alpha": alpha,
        "dims": dims,
        "w_entropy": [round(float(x), 4) for x in w_e],
        "w_ahp": [round(float(x), 4) for x in w_a],
        "w_final": [round(float(x), 4) for x in w],
        "entropy_E": [round(float(x), 4) for x in
                      (-(S + 1e-9) / (S + 1e-9).sum(axis=0, keepdims=True) *
                       np.log((S + 1e-9) / (S + 1e-9).sum(axis=0, keepdims=True))).sum(axis=0)
                      / math.log(max(S.shape[0], 2))],
    }
    return w, detail


# ---------------------------------------------------------------------------
# 敏感性分析
# ---------------------------------------------------------------------------
def _rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(-values)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(values) + 1)
    return ranks


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = _rank(a).astype(float), _rank(b).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / denom) if denom else 1.0


def sensitivity(S: np.ndarray, w: np.ndarray, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """权重 ±p 随机扰动 N 次，看排名稳定性（Spearman）与 Top-3 保持率。"""
    scfg = cfg["score"]
    p = float(scfg.get("sensitivity_perturb", 0.10))
    trials = int(scfg.get("sensitivity_trials", 100))
    rng = np.random.default_rng(42)

    base = S @ w
    base_top3 = set(np.argsort(-base)[:3].tolist())

    rhos, top3_keep = [], 0
    for _ in range(trials):
        factor = 1.0 + rng.uniform(-p, p, size=w.shape)
        wt = w * factor
        wt = wt / wt.sum()
        cur = S @ wt
        rhos.append(_spearman(base, cur))
        if set(np.argsort(-cur)[:3].tolist()) == base_top3:
            top3_keep += 1

    return {
        "perturb_pct": p,
        "trials": trials,
        "spearman_mean": round(float(np.mean(rhos)), 4),
        "spearman_min": round(float(np.min(rhos)), 4),
        "top3_stability": round(top3_keep / trials, 4),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(cfg: Dict[str, Any], clusters: List[Dict[str, Any]]) -> Dict[str, Any]:
    log = get_logger(cfg, "score")
    if not clusters:
        log.error("没有主题簇可评分")
        return {"clusters": [], "weight_detail": {}, "sensitivity": {}}

    M, dims = raw_dimensions(clusters)
    S = normalize(M, cfg["score"].get("normalize", "minmax"))
    w, detail = combine_weights(S, cfg, dims)
    log.info("权重（%s）：%s", detail["method"],
             {d: round(float(x), 3) for d, x in zip(dims, w)})

    final = S @ w
    order = sorted(range(len(clusters)),
                   key=lambda i: (-final[i], -clusters[i]["n_sources"],
                                  -clusters[i]["n_records"], clusters[i]["topic_name"]))

    scored: List[Dict[str, Any]] = []
    for rank, i in enumerate(order, 1):
        c = dict(clusters[i])
        c["dim_scores"] = {d: round(float(S[i, j]), 2) for j, d in enumerate(dims)}
        c["value_score"] = round(float(final[i]), 1)
        c["priority"] = rank
        c["cluster_id"] = f"C{rank}"        # 按价值分重编号，C1 = 最高优先级
        scored.append(c)

    sens = sensitivity(S, w, cfg)
    log.info("敏感性：Spearman 均值 %.3f，Top3 稳定率 %.0f%%",
             sens["spearman_mean"], sens["top3_stability"] * 100)

    write_jsonl(f"{cfg['paths']['clean']}/scored.jsonl", scored)
    write_jsonl(f"{cfg['paths']['clean']}/score_detail.jsonl",
                [{"weight_detail": detail, "sensitivity": sens,
                  "dim_matrix": S.round(2).tolist()}])
    return {"clusters": scored, "weight_detail": detail, "sensitivity": sens}
