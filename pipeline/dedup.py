# -*- coding: utf-8 -*-
"""任务一（后段）：三层去重。

L1 URL 精确去重 -> L2 SimHash 近似去重 -> L3 TF-IDF 余弦语义去重。
每层剔除数量都要写进论文的漏斗图。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple

import jieba

from io_utils import get_logger, safe_div, write_jsonl

RE_TOKEN = re.compile(r"[\u4e00-\u9fa5]|[A-Za-z]+|\d+")
STOP = set("的 了 是 我 你 他 这 那 就 也 都 和 与 在 有 个 不 人 上 中 下 很 会 "
           "吗 呢 吧 啊 呀 什么 怎么 可以 一个 我们 你们 他们".split())


def tokenize(text: str) -> List[str]:
    """中文用 jieba，英文/数字用正则，去掉停用词与单字噪声。"""
    toks = [t for t in jieba.lcut(text) if t.strip()]
    out = []
    for t in toks:
        if t in STOP:
            continue
        if len(t) == 1 and not RE_TOKEN.fullmatch(t):
            continue
        out.append(t.lower())
    return out


# ---------------------------------------------------------------------------
# SimHash（64 位）
# ---------------------------------------------------------------------------
def simhash(tokens: List[str], bits: int = 64) -> int:
    if not tokens:
        return 0
    weights = [0] * bits
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(bits):
            weights[i] += 1 if (h >> i) & 1 else -1
    value = 0
    for i in range(bits):
        if weights[i] > 0:
            value |= 1 << i
    return value


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ---------------------------------------------------------------------------
# 选优：同一组重复里保留“更有价值”的那条
# ---------------------------------------------------------------------------
def _heat_total(rec: Dict[str, Any]) -> float:
    heat = rec.get("heat") or {}
    return float(sum(v for v in heat.values() if isinstance(v, (int, float))))


def _keep_key(rec: Dict[str, Any]) -> Tuple:
    # 发布时间更早（原始出处）优先，其次热度更高、正文更长
    ts = rec.get("published_at") or "9999"
    return (ts if ts != "未知" else "9999", -_heat_total(rec), -len(rec.get("clean_text", "")))


def run(cfg: Dict[str, Any], records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    log = get_logger(cfg, "dedup")
    dcfg = cfg["clean"]["dedup"]
    n0 = len(records)

    # ---- L1：URL 精确 ----
    by_url: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        url = (rec.get("url") or "").strip().rstrip("/")
        by_url.setdefault(url or f"__nourl_{rec['record_id']}", []).append(rec)
    l1 = [sorted(group, key=_keep_key)[0] for group in by_url.values()]
    l1_dropped = n0 - len(l1)
    log.info("L1 URL 去重：%d -> %d（剔除 %d）", n0, len(l1), l1_dropped)

    # ---- L2：SimHash ----
    hashed = []
    for rec in l1:
        toks = tokenize(rec.get("clean_text", ""))
        hashed.append((simhash(toks), rec))

    kept_l2: List[Dict[str, Any]] = []
    kept_hash: List[int] = []
    for h, rec in hashed:
        dup = False
        for kh in kept_hash:
            if hamming(h, kh) <= dcfg.get("simhash_hamming", 3):
                dup = True
                break
        if not dup:
            kept_l2.append(rec)
            kept_hash.append(h)
    l2_dropped = len(l1) - len(kept_l2)
    log.info("L2 SimHash 去重：%d -> %d（剔除 %d）", len(l1), len(kept_l2), l2_dropped)

    # ---- L3：TF-IDF 余弦 ----
    l3 = kept_l2
    l3_dropped = 0
    if len(kept_l2) > 1:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np

        corpus = [r["clean_text"] for r in kept_l2]
        vec = TfidfVectorizer(tokenizer=tokenize, token_pattern=None,
                              max_features=20000, sublinear_tf=True)
        X = vec.fit_transform(corpus)
        sim = (X @ X.T).toarray()
        np.fill_diagonal(sim, 0.0)
        thr = dcfg.get("tfidf_cosine", 0.95)

        drop = set()
        for i in range(len(corpus)):
            if i in drop:
                continue
            for j in range(i + 1, len(corpus)):
                if j in drop:
                    continue
                if sim[i, j] >= thr:
                    # 保留 _keep_key 更优的一条
                    loser = j if _keep_key(kept_l2[i]) <= _keep_key(kept_l2[j]) else i
                    drop.add(loser)
                    if loser == i:
                        break
        l3 = [r for i, r in enumerate(kept_l2) if i not in drop]
        l3_dropped = len(kept_l2) - len(l3)
        log.info("L3 语义去重：%d -> %d（剔除 %d，阈值 %.2f）",
                 len(kept_l2), len(l3), l3_dropped, thr)

    funnel = {
        "raw": n0,
        "after_L1_url": len(l1),
        "after_L2_simhash": len(kept_l2),
        "after_L3_semantic": len(l3),
        "dropped_L1": l1_dropped,
        "dropped_L2": l2_dropped,
        "dropped_L3": l3_dropped,
        "dedup_rate": round(safe_div(n0 - len(l3), n0), 4),
    }
    write_jsonl(f"{cfg['paths']['clean']}/dedup_funnel.jsonl", [funnel])
    write_jsonl(f"{cfg['paths']['clean']}/records.jsonl", l3)

    # 按来源的去重审计（报告用）
    def _counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in rows:
            out[r.get("source", "未知")] = out.get(r.get("source", "未知"), 0) + 1
        return out

    c0, c1, c2, c3 = _counts(records), _counts(l1), _counts(kept_l2), _counts(l3)
    audit = [{
        "source": src,
        "before": c0.get(src, 0),
        "after_L1": c1.get(src, 0),
        "after_L2": c2.get(src, 0),
        "after_L3": c3.get(src, 0),
        "dropped": c0.get(src, 0) - c3.get(src, 0),
    } for src in sorted(c0, key=lambda s: -c0[s])]
    write_jsonl(f"{cfg['paths']['clean']}/audit_dedup.jsonl", audit)

    log.info("去重完成：%d 条保留（总去重率 %.1f%%）", len(l3), funnel["dedup_rate"] * 100)
    return l3
