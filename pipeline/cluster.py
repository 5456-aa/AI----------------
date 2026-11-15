# -*- coding: utf-8 -*-
"""任务三：主题聚类 + 主题名提炼 + 热点统计 + 结果溯源。

只对 is_opportunity == 1 的记录聚类。
默认用 TF-IDF + SVD 生成向量（离线可跑，无需下载模型）；
若装了 sentence-transformers 且改了 config，则用 BGE 句向量（效果更好，论文里做对比）。
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Tuple

import numpy as np

from io_utils import get_logger, safe_div, write_jsonl
from llm import prompts
from llm.client import LLMClient, LLMUnavailable
from pipeline.dedup import tokenize


# ---------------------------------------------------------------------------
# 向量化
# ---------------------------------------------------------------------------
def build_vectors(texts: List[str], cfg: Dict[str, Any]) -> np.ndarray:
    backend = cfg["cluster"].get("embedding", "tfidf_svd")

    if backend == "sentence_transformers":
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(cfg["cluster"]["st_model"])
            vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return np.asarray(vecs)
        except Exception as exc:  # 没装/没网就退回离线方案
            print(f"[cluster] sentence_transformers 不可用（{exc}），回退 tfidf_svd")

    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    vec = TfidfVectorizer(tokenizer=tokenize, token_pattern=None,
                          max_features=30000, sublinear_tf=True, min_df=1)
    X = vec.fit_transform(texts)
    dims = min(cfg["cluster"].get("svd_dims", 100), max(2, X.shape[1] - 1), X.shape[0] - 1)
    X = TruncatedSVD(n_components=max(2, dims), random_state=42).fit_transform(X)
    return normalize(X)


# ---------------------------------------------------------------------------
# 聚类
# ---------------------------------------------------------------------------
def cluster_vectors(X: np.ndarray, cfg: Dict[str, Any]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """返回 (簇标签, k 扫描表)。k 扫描表直接进论文的「聚类评估」小节。"""
    from sklearn.cluster import AgglomerativeClustering, KMeans
    from sklearn.metrics import silhouette_score

    ccfg = cfg["cluster"]
    method = ccfg.get("method", "auto")
    n = X.shape[0]
    sweep: List[Dict[str, Any]] = []

    if method == "distance":       # 按余弦距离阈值切树，簇数不预设
        labels = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=ccfg.get("distance_threshold", 0.62),
            metric="cosine", linkage="average").fit_predict(X)
        return labels, sweep

    lo, hi = ccfg.get("k_range", [2, 12])
    hi = int(min(hi, n - 1, max(2, int(n * 0.8))))
    if hi < lo:
        return np.zeros(n, dtype=int), sweep

    max_share = float(ccfg.get("max_cluster_share", 0.70))
    candidates = []
    for k in range(int(lo), hi + 1):
        if method == "kmeans":
            labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X)
        else:  # auto / agglomerative：平均连接 + 余弦距离
            labels = AgglomerativeClustering(
                n_clusters=k, metric="cosine", linkage="average").fit_predict(X)
        if len(set(labels.tolist())) < 2:
            continue
        s = float(silhouette_score(X, labels, metric="cosine"))
        share = float(np.bincount(labels).max() / n)
        sweep.append({"k": k, "silhouette": round(s, 4),
                      "max_share": round(share, 3), "sizes": np.bincount(labels).tolist()})
        candidates.append((k, s, share, labels))

    if not candidates:
        return np.zeros(n, dtype=int), sweep

    # 约束一：单一簇占比不得超过 max_share，否则会出现「一个巨簇 + 一堆单点」的退化解
    balanced = [c for c in candidates if c[2] <= max_share]
    pool = balanced or candidates

    # 约束二（简约原则）：在轮廓系数与最优值差距 <= tol 的解里取最小的 k，
    # 避免把一个完整方向切成一堆单点簇。
    tol = float(ccfg.get("k_tolerance", 0.01))
    best_s = max(c[1] for c in pool)
    near = [c for c in pool if c[1] >= best_s - tol]
    best_k = min(c[0] for c in near)
    best_labels = next(c[3] for c in near if c[0] == best_k)
    for row in sweep:
        row["selected"] = (row["k"] == best_k)
    return best_labels, sweep


def merge_small(labels: np.ndarray, X: np.ndarray, min_size: int,
                merge_sim: float = 0.45, force: bool = False) -> np.ndarray:
    """把过小的簇（含单点）并入质心最近的簇。

    两条保护规则（论文里要写）：
      1. 只有与目标簇质心相似度 >= merge_sim 才合并，否则保留为独立方向，
         避免把语义上并不相近的单条记录硬塞进某个簇；
      2. 不允许把整批合并成 1 个簇 —— 那样聚类就没有意义了。
    """
    labels = labels.copy()
    seen_shapes = set()

    while True:
        clusters = Counter(labels.tolist())
        small = [c for c, n in clusters.items() if n < min_size]
        big = [c for c, n in clusters.items() if n >= min_size]
        if not small or not big or len(clusters) <= 1:
            break
        shape = (len(small), len(big), len(clusters))
        if shape in seen_shapes:      # 防死循环
            break
        seen_shapes.add(shape)

        centroids = {c: X[labels == c].mean(axis=0) for c in big}
        changed = False
        for c in small:
            for i in np.where(labels == c)[0]:
                best_c, best_sim = None, -1.0
                for bc, vec in centroids.items():
                    sim = float(np.dot(X[i], vec) / (np.linalg.norm(vec) + 1e-9))
                    if sim > best_sim:
                        best_c, best_sim = bc, sim
                if best_c is not None and (force or best_sim >= merge_sim):
                    if len(set(labels.tolist())) <= 2:
                        continue      # 保住至少 2 个簇
                    labels[i] = best_c
                    changed = True
        if not changed:
            break
    return labels


def stability(X: np.ndarray, labels: np.ndarray, cfg: Dict[str, Any],
              trials: int = 10, ratio: float = 0.8,
              seed: int = 42) -> Dict[str, float]:
    """聚类稳健性：Bootstrap 抽样重聚类，与全量标签算 ARI。

    赛题要求「自行设计聚类效果的评估方案」——内部指标（轮廓系数）衡量簇的紧致度，
    ARI 衡量的则是「换个样本，簇还长这样吗」，两者互补。
    """
    from sklearn.metrics import adjusted_rand_score
    from sklearn.model_selection import train_test_split

    n = len(labels)
    if n < 8 or len(set(labels.tolist())) < 2:
        return {"ari_mean": 0.0, "ari_min": 0.0, "trials": 0}

    rng = np.random.default_rng(seed)
    aris = []
    for _ in range(trials):
        idx = rng.choice(n, size=max(6, int(n * ratio)), replace=False)
        sub = X[idx]
        try:
            sub_labels, _ = cluster_vectors(sub, cfg)
            sub_labels = merge_small(sub_labels, sub,
                                     cfg["cluster"].get("min_cluster_size", 2),
                                     float(cfg["cluster"].get("merge_sim", 0.35)),
                                     force=bool(cfg["cluster"].get("force_merge_singletons", True)))
        except Exception:
            continue
        if len(set(sub_labels.tolist())) < 2:
            continue
        aris.append(adjusted_rand_score(labels[idx], sub_labels))

    if not aris:
        return {"ari_mean": 0.0, "ari_min": 0.0, "trials": 0}
    return {"ari_mean": round(float(np.mean(aris)), 3),
            "ari_min": round(float(np.min(aris)), 3),
            "ari_std": round(float(np.std(aris)), 3),
            "trials": len(aris)}


def evaluate(X: np.ndarray, labels: np.ndarray) -> Dict[str, float]:
    from sklearn.metrics import (calinski_harabasz_score, davies_bouldin_score,
                                 silhouette_score)
    uniq = set(labels.tolist())
    if len(uniq) < 2:
        return {"n_clusters": len(uniq), "silhouette": 0.0,
                "davies_bouldin": 0.0, "calinski_harabasz": 0.0,
                "intra_sim": 0.0, "inter_sim": 0.0}

    intra, inter = [], []
    sim = X @ X.T
    lab = np.asarray(labels)
    for i in range(len(lab)):
        for j in range(i + 1, len(lab)):
            (intra if lab[i] == lab[j] else inter).append(float(sim[i, j]))

    return {
        "n_clusters": len(uniq),
        "silhouette": round(float(silhouette_score(X, labels, metric="cosine")), 4),
        "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 4),
        "calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 2),
        "intra_sim": round(float(np.mean(intra)) if intra else 0.0, 4),
        "inter_sim": round(float(np.mean(inter)) if inter else 0.0, 4),
    }


# ---------------------------------------------------------------------------
# 主题名
# ---------------------------------------------------------------------------
def fallback_topic_name(titles: List[str], max_chars: int = 20,
                        func: str = "", industry: str = "") -> str:
    """无 LLM 时：簇内高频中文词拼一个名字；拼不出来就用「行业+功能类别」。"""
    import re
    words: Counter = Counter()
    for t in titles:
        for tok in tokenize(t):
            if re.fullmatch(r"[\u4e00-\u9fa5]{2,6}", tok):
                words[tok] += 1
    top = [w for w, _ in words.most_common(4)]
    if top:
        return "".join(top[:3])[:max_chars]
    # 兜底：用标签拼一个语义明确的名字，避免出现「零散机会方向」这种无信息量的簇名
    if industry and func:
        return f"{industry}·{func}"[:max_chars]
    return (func or industry or "待命名方向")[:max_chars]


def topic_name(recs: List[Dict[str, Any]], client: LLMClient,
               cfg: Dict[str, Any]) -> Tuple[str, str, str]:
    """返回 (主题名, 功能类别, 所属行业)。

    标签一律取**簇内记录的众数**，不让大模型自由发挥——附件1 要求单选
    （16 个功能类别 / 30 个行业），模型很容易返回「对话问答与知识检索」这种
    组合词，直接判不合规。大模型只负责起名。
    """
    titles = [r.get("title") or r.get("clean_text", "")[:30] for r in recs]
    max_chars = cfg["cluster"].get("topic_name_max_chars", 20)
    func = _mode(recs, "func_category")
    ind = _mode(recs, "industry")

    if client.enabled:
        try:
            data = client.chat_json(
                prompts.topic_name_prompt(titles, max_chars),
                system=prompts.TOPIC_NAME_SYSTEM)
            name = str(data.get("topic_name", "")).strip()
            name = re.sub(r"[「」“”\"']", "", name).strip("：: ，,。.")
            if name and len(name) >= 3:
                return name[:max_chars], func, ind
        except LLMUnavailable:
            pass

    return (fallback_topic_name(titles, max_chars, func, ind), func, ind)


def _mode(recs: List[Dict[str, Any]], key: str) -> str:
    values = [r.get(key) for r in recs if r.get(key)]
    return Counter(values).most_common(1)[0][0] if values else "其他"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(cfg: Dict[str, Any], records: List[Dict[str, Any]]) -> Dict[str, Any]:
    log = get_logger(cfg, "cluster")
    opps = [r for r in records if r.get("is_opportunity") == 1]
    log.info("机会记录 %d 条 / 全部 %d 条", len(opps), len(records))

    if len(opps) < 2:
        log.error("机会记录不足 2 条，无法聚类。请先补数据或下调阈值 τ。")
        write_jsonl(f"{cfg['paths']['clean']}/clusters.jsonl", [])
        return {"clusters": [], "metrics": {}, "records": opps}

    texts = [r.get("clean_text", "") for r in opps]
    X = build_vectors(texts, cfg)
    labels, sweep = cluster_vectors(X, cfg)
    labels = merge_small(labels, X, cfg["cluster"].get("min_cluster_size", 2),
                         float(cfg["cluster"].get("merge_sim", 0.35)),
                         force=bool(cfg["cluster"].get("force_merge_singletons", True)))
    metrics = evaluate(X, labels)
    metrics["k_sweep"] = sweep
    metrics.update(stability(X, labels, cfg,
                             trials=int(cfg["cluster"].get("stability_trials", 10))))
    log.info("聚类完成：%d 个簇，silhouette=%.4f，DB=%.4f",
             metrics["n_clusters"], metrics["silhouette"], metrics["davies_bouldin"])

    client = LLMClient(cfg)
    clusters: List[Dict[str, Any]] = []
    for cid in sorted(set(labels.tolist())):
        idx = [i for i, lab in enumerate(labels) if lab == cid]
        recs = [opps[i] for i in idx]
        name, func, ind = topic_name(recs, client, cfg)
        sources = sorted({r.get("source", "") for r in recs})
        clusters.append({
            "cluster_id": "",                     # 稍后按价值分排序后重编号
            "topic_name": name,
            "func_category": func,
            "industry": ind,
            "records": recs,
            "n_records": len(recs),
            "sources": sources,
            "n_sources": len(sources),
            "n_categories": len({r.get("source_category", "") for r in recs}),
            "mean_conf": round(float(np.mean([r.get("confidence", 0) for r in recs])), 4),
            "record_ids": [r["record_id"] for r in recs],
        })

    # 排序稳定化：先按记录数降序，再按来源数降序，最后按主题名（保证可复现）
    clusters.sort(key=lambda c: (-c["n_records"], -c["n_sources"], c["topic_name"]))
    for i, c in enumerate(clusters, 1):
        c["cluster_id"] = f"C{i}"

    total = sum(c["n_records"] for c in clusters)
    log.info("簇内记录合计 %d（应等于机会记录数 %d）", total, len(opps))
    assert total == len(opps), "簇内记录数之和与机会记录数不一致！"

    for c in clusters:
        write_row = {k: v for k, v in c.items() if k != "records"}
        write_row["titles"] = [r.get("title", "") for r in c["records"]][:10]
        write_row["_"] = write_row.pop("titles")
    write_jsonl(f"{cfg['paths']['clean']}/clusters.jsonl", clusters)
    write_jsonl(f"{cfg['paths']['clean']}/cluster_metrics.jsonl", [metrics])
    return {"clusters": clusters, "metrics": metrics, "records": opps}
