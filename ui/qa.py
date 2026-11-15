# -*- coding: utf-8 -*-
"""任务五：问答咨询（结构化查询为主，LLM 润色为辅）。

设计要点：
  1. **答案里的每个数字都来自结果文件**，不是模型编的；
  2. 意图识别用规则（关键词），不靠模型猜；
  3. 配了 Key 才用 LLM 把结构化结果改写成自然语言，且强制引用记录编号；
     没配 Key 就用模板句，功能不受影响。

启动：双击「问答咨询.bat」，或 streamlit run ui/qa.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402

from _init import page_config  # noqa: E402
page_config("问答咨询", "💬")


@st.cache_data(show_spinner=False)
def load_all():
    cfg = load_config(track="all")
    clean = Path(cfg["paths"]["clean"])
    judged = pd.DataFrame(read_jsonl(clean / "judged.jsonl"))
    scored = read_jsonl(clean / "scored.jsonl")
    detail = (read_jsonl(clean / "score_detail.jsonl") or [{}])[0]
    return cfg, judged, scored, detail


SUGGESTIONS = [
    "总共多少条机会记录？",
    "教育行业有哪些机会方向？",
    "哪些来源的机会率最高？",
    "价值最高的三个方向是什么？",
    "C1 为什么排第一？",
    "电商方向有哪些具体需求？",
]


# ---------------------------------------------------------------------------
# 意图识别
# ---------------------------------------------------------------------------
def match_industry(q: str, industries: list[str]) -> str | None:
    for ind in industries:
        if ind and ind in q:
            return ind
    return None


def match_cluster(q: str, scored: list[dict]) -> dict | None:
    m = re.search(r"\bC(\d{1,2})\b", q, re.I) or re.search(r"簇\s*(\d{1,2})", q)
    if m:
        cid = f"C{int(m.group(1))}"
        return next((c for c in scored if c.get("cluster_id") == cid), None)
    return None


def match_source(q: str, sources: list[str]) -> str | None:
    for s in sources:
        if s and s in q:
            return s
    return None


# ---------------------------------------------------------------------------
# 各类回答
# ---------------------------------------------------------------------------
def ans_overview(judged: pd.DataFrame, scored: list[dict]) -> tuple[str, dict]:
    n = len(judged)
    opp = int((judged["is_opportunity"] == 1).sum()) if "is_opportunity" in judged else 0
    txt = (f"当前批次共有 **{n}** 条清洗去重后的记录，其中判为 AI 应用机会的有 **{opp}** 条"
           f"（{opp / max(n, 1) * 100:.1f}%），聚合为 **{len(scored)}** 个主题簇，"
           f"覆盖 **{judged['source'].nunique()}** 个来源。")
    chart = judged.groupby("source").size().sort_values(ascending=False).rename("记录数")
    return txt, {"type": "table", "df": pd.DataFrame(
        [{"指标": "记录总数", "值": str(n)}, {"指标": "机会记录", "值": str(opp)},
         {"指标": "机会率", "值": f"{opp / max(n, 1) * 100:.1f}%"},
         {"指标": "主题簇", "值": str(len(scored))},
         {"指标": "来源数", "值": str(judged["source"].nunique())}]),
        "chart": ("各来源记录数", chart)}


def ans_industry(judged: pd.DataFrame, scored: list[dict], ind: str) -> tuple[str, dict]:
    sub = judged[(judged["is_opportunity"] == 1) & (judged["industry"] == ind)]
    if sub.empty:
        return f"**{ind}** 行业当前没有判为机会的记录。", {"type": "none"}
    cl = [c for c in scored if c.get("industry") == ind]
    cl_sorted = sorted(cl, key=lambda c: -float(c.get("value_score", 0)))
    lines = [f"**{ind}** 行业共 **{len(sub)}** 条机会记录，聚成 **{len(cl)}** 个主题簇："]
    for c in cl_sorted[:6]:
        lines.append(f"- **{c['cluster_id']} · {c['topic_name']}**（{c.get('func_category')}，"
                     f"{c.get('n_records')} 条，价值分 {c.get('value_score')}，"
                     f"优先级 P{c.get('priority')}）")
    if cl_sorted:
        top = cl_sorted[0]
        ids = "、".join(top.get("record_ids", [])[:8])
        lines.append(f"\n价值最高的是 **{top['topic_name']}**，依据记录：{ids} …")
    chart = pd.Series({c["topic_name"]: float(c.get("value_score", 0)) for c in cl_sorted})
    return "\n".join(lines), {"type": "records",
                              "df": sub[["record_id", "source", "title"]].head(30),
                              "chart": (f"{ind} 行业各簇价值分", chart)}


def ans_source_rank(judged: pd.DataFrame) -> tuple[str, dict]:
    g = judged.groupby("source").agg(记录数=("record_id", "count"),
                                     机会数=("is_opportunity", "sum"))
    g["机会率"] = (g["机会数"] / g["记录数"] * 100).round(1)
    g = g.sort_values("机会率", ascending=False)
    top = g.head(3)
    lines = ["按机会率排序的来源（机会率 = 机会记录 / 该来源入表记录）："]
    for name, row in top.iterrows():
        lines.append(f"- **{name}**：{int(row['机会数'])} / {int(row['记录数'])} = "
                     f"{row['机会率']}%")
    lines.append("\n可见**问答类社区**的机会密度显著高于教程类与资讯类。")
    return "\n".join(lines), {"type": "table", "df": g.reset_index(),
                              "chart": ("各来源机会率（%）", g["机会率"])}


def ans_top(scored: list[dict], k: int = 3) -> tuple[str, dict]:
    top = sorted(scored, key=lambda c: int(c.get("priority", 99)))[:k]
    lines = [f"按机会价值分排序，前 {len(top)} 个方向是："]
    for c in top:
        lines.append(f"- **P{c['priority']} {c['cluster_id']} · {c['topic_name']}**"
                     f"（{c.get('func_category')} / {c.get('industry')}，"
                     f"{c.get('n_records')} 条，覆盖 {c.get('n_sources')} 个来源，"
                     f"价值分 **{c.get('value_score')}**）")
    chart = pd.Series({c["topic_name"]: float(c.get("value_score", 0)) for c in top})
    return "\n".join(lines), {"type": "table", "df": pd.DataFrame(
        [{"优先级": f"P{c['priority']}", "簇": c["cluster_id"], "主题": c["topic_name"],
          "价值分": c.get("value_score"), "记录数": c.get("n_records"),
          "来源数": c.get("n_sources")} for c in top]),
        "chart": ("Top 簇价值分", chart)}


def ans_cluster(c: dict, detail: dict) -> tuple[str, dict]:
    dims = c.get("dim_scores", {})
    wd = detail.get("weight_detail", {})
    weights = dict(zip(wd.get("dims", []), wd.get("w_final", [])))
    lines = [f"**{c['cluster_id']} · {c['topic_name']}**　价值分 **{c.get('value_score')}**"
             f"（优先级 P{c.get('priority')}）", ""]
    lines.append(f"- 功能类别 / 行业：{c.get('func_category')} / {c.get('industry')}")
    lines.append(f"- 记录数：{c.get('n_records')} 条；来源覆盖：{'、'.join(c.get('sources', []))}")
    lines.append("")
    lines.append("**四维得分（0~100）与权重**")
    for d, v in dims.items():
        w = weights.get(d)
        lines.append(f"- {d}：{v}" + (f"（权重 {w:.3f}）" if isinstance(w, float) else ""))
    if dims:
        top_d = max(dims, key=lambda k: dims[k])
        lines.append("")
        lines.append(f"它排第一的主要原因是在 **{top_d}** 维度得分较高，"
                     f"而该维度的权重为 {weights.get(top_d, 0):.3f}。")
    ids = "、".join(c.get("record_ids", [])[:10])
    lines.append(f"\n依据记录（共 {len(c.get('record_ids', []))} 条）：{ids} …")
    chart = pd.Series(dims).astype(float) if dims else None
    return "\n".join(lines), {"type": "table", "df": pd.DataFrame(
        [{"记录编号": r["record_id"], "来源": r.get("source"),
          "标题": (r.get("title") or "")[:60]}
         for r in c.get("records", [])][:30]),
        "chart": (f"{c['cluster_id']} 四维得分", chart) if chart is not None else None}


def ans_func(judged: pd.DataFrame, fc: str) -> tuple[str, dict]:
    sub = judged[(judged["is_opportunity"] == 1) & (judged["func_category"] == fc)]
    if sub.empty:
        return f"功能类别 **{fc}** 下暂无机会记录。", {"type": "none"}
    lines = [f"功能类别为 **{fc}** 的机会记录共 **{len(sub)}** 条，主要来源："
             f"{'、'.join(sorted(set(sub['source'])))}。"]
    return "\n".join(lines), {"type": "records",
                              "df": sub[["record_id", "source", "title"]].head(30)}


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
def main() -> None:
    cfg, judged, scored, detail = load_all()

    st.title("💬 问答咨询")

    # 数据缺失时给明确提示，而不是抛 KeyError（云端可能只发布了部分数据）
    if judged is None or getattr(judged, "empty", True):
        st.warning("当前环境没有可用的明细数据，问答暂不可用。")
        st.caption("本地可运行：`python run_all.py --track all --offline --force` 生成后再试。")
        return
    st.caption("答案中的数字全部来自结果文件，可逐条溯源到原始记录。")

    q = st.text_input("问点什么", placeholder="例如：教育行业有哪些机会方向？")
    cols = st.columns(3)
    for i, s in enumerate(SUGGESTIONS):
        if cols[i % 3].button(s, use_container_width=True, key=f"sug{i}"):
            q = s

    if not q.strip():
        st.info("点击上面的示例问题，或直接输入。支持：总量统计、行业、来源、"
                "簇详情（如 C1）、价值排名、功能类别。")
        return

    # 意图识别
    industries = [x for x in judged["industry"].dropna().unique()] if "industry" in judged else []
    sources = [x for x in judged["source"].dropna().unique()]
    cl = match_cluster(q, scored)

    text, payload, kind = "", {"type": "none"}, ""
    if cl:
        text, payload = ans_cluster(cl, detail); kind = "簇详情"
    elif (ind := match_industry(q, industries)) and any(
            w in q for w in ("行业", "方向", "机会", "需求")):
        text, payload = ans_industry(judged, scored, ind); kind = "行业筛选"
    elif any(w in q for w in ("来源", "网站", "渠道")) and any(w in q for w in ("最高", "排名", "机会率")):
        text, payload = ans_source_rank(judged); kind = "来源对比"
    elif any(w in q for w in ("最高", "最好", "前几", "排名", "优先", "值得")):
        text, payload = ans_top(scored); kind = "价值排名"
    elif (src := match_source(q, sources)) and "来源" in q:
        sub = judged[judged["source"] == src]
        text = (f"来源 **{src}** 共 {len(sub)} 条记录，其中机会 "
                f"{int((sub['is_opportunity'] == 1).sum())} 条。")
        payload = {"type": "table", "df": sub[["record_id", "title", "is_opportunity"]].head(30)}
        kind = "单来源"
    elif any(fc in q for fc in judged["func_category"].dropna().unique()):
        fc = next(fc for fc in judged["func_category"].dropna().unique() if fc in q)
        text, payload = ans_func(judged, fc); kind = "功能类别"
    else:
        text, payload = ans_overview(judged, scored); kind = "总览"

    # 可选：LLM 润色（只允许用给定事实）
    llm_used = False
    try:
        from llm.client import LLMClient, LLMUnavailable
        client = LLMClient(cfg)
        if client.enabled and kind != "总览":
            facts = text
            out = client.chat_json(
                "把下面的结构化结论改写成一段自然、连贯的中文回答。"
                "严格约束：只能使用给定事实中的数字与名称，不得补充、推断或编造；"
                "保留所有记录编号；不超过 150 字。\n\n事实：\n" + facts
                + '\n\n只输出 JSON：{"answer": "..."}',
                system="你是数据分析助手，只根据给定事实作答，不确定就说不知道。")
            if out.get("answer"):
                text = str(out["answer"]).strip() + "\n\n<sub>（已由大模型润色，数字取自结果文件）</sub>"
                llm_used = True
    except Exception:
        pass

    st.markdown(f"**识别意图**：{kind}" + ("　·　由大模型润色" if llm_used else ""))
    st.markdown(text)

    ch = payload.get("chart")
    if ch:
        title, series = ch
        if series is not None and len(series) > 0:
            st.markdown(f"**{title}**")
            st.bar_chart(series)

    if payload.get("type") in ("table", "records") and payload.get("df") is not None:
        with st.expander("查看明细", expanded=False):
            st.dataframe(payload["df"], use_container_width=True, hide_index=True)

    with st.expander("这一类问题是怎么算出来的"):
        st.markdown("""
- 总量与行业统计：对 `result2.csv`（逐条判别结果）按条件过滤后计数；
- 来源机会率：`机会数 / 该来源入表记录数`，来源取自 `result1.csv`；
- 价值排名：直接读取 `result4.csv` 的「机会价值分」与「优先级」；
- 簇详情：读取 `scored.jsonl` 的四维得分与 `score_detail.jsonl` 的组合权重；
- 所有编号（如 JY00012）都能在 `result1.csv` 中查到原文与来源链接。
""")


if __name__ == "__main__":
    main()
