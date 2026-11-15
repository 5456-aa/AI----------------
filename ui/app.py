# -*- coding: utf-8 -*-
"""任务五：交互式仪表盘（Streamlit，双赛道）。

启动：
    streamlit run ui/app.py
前提：先跑过 `python run_all.py --track all`（或单赛道）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import TRACKS, load_config, read_jsonl, track_report_dir  # noqa: E402
from llm.client import LLMClient, LLMUnavailable  # noqa: E402
import auth  # noqa: E402
import llm_settings  # noqa: E402

from _init import page_config  # noqa: E402
page_config("分析看板", "📊")

TRACK_LABEL = {
    "all": "两赛道合并（提交版）",
    "ecommerce": "电商客服与运营",
    "education": "教育学习与教学管理",
}


def is_public_demo() -> bool:
    """公网演示模式：隐藏一切会改写本机配置的入口。"""
    import os
    return bool(os.environ.get("PUBLIC_DEMO"))


def render_llm_settings(cfg) -> None:
    """模型设置面板：每个使用者填自己的服务商与 key，只写到本机 .env。"""
    if not auth.sees("see_settings"):
        st.sidebar.caption("🔒 当前角色无配置权限：模型设置已隐藏")
        return
    st.sidebar.subheader("⚙ 模型设置")
    stt = llm_settings.status(cfg)

    if stt["enabled"]:
        st.sidebar.success(f"已连接：{stt['label']}\n\n`{stt['model']}`")
    else:
        st.sidebar.warning("未配置 Key —— 当前以**纯规则模式**运行")

    with st.sidebar.expander("填写我自己的 Key", expanded=not stt["enabled"]):
        keys = list(llm_settings.PROVIDERS)
        labels = {k: v["label"] for k, v in llm_settings.PROVIDERS.items()}
        cur = stt["provider"] if stt["provider"] in keys else "deepseek"

        provider = st.selectbox(
            "服务商", keys, index=keys.index(cur),
            format_func=lambda k: labels[k], key="llm_provider")

        preset = llm_settings.PROVIDERS[provider]
        base_url = st.text_input("接口地址 base_url",
                                 value=stt["base_url"] or preset["base_url"],
                                 key=f"llm_base_{provider}")
        model = st.text_input("模型名 model",
                              value=stt["model"] or preset["model"],
                              key=f"llm_model_{provider}")
        api_key = st.text_input("API Key（只存本机）", value="", type="password",
                                placeholder="sk-...", key=f"llm_key_{provider}")

        st.caption(f"当前 key：`{stt['key_masked']}`（来源：{stt['key_source']}）")
        if preset.get("signup"):
            st.caption(f"没有 key？[去 {preset['label']} 申请]({preset['signup']})")

        c1, c2 = st.columns(2)
        if c1.button("保存并测试", use_container_width=True, key="llm_save"):
            if not api_key.strip():
                st.error("请先填写 Key")
            else:
                p = llm_settings.save_settings(provider, base_url.strip(),
                                               model.strip(), api_key.strip())
                st.caption(f"已写入 {p.name}")
                try:
                    test_cfg = load_config(track="all")
                    client = LLMClient(test_cfg)
                    out = client.chat_json('只输出 JSON：{"ok": true}',
                                           system="连通性测试，只回 JSON。")
                    if out:
                        st.success("测试通过，已切换到大模型模式")
                        st.rerun()
                    else:
                        st.warning("接口能通，但返回不是 JSON —— 可能该模型不支持 json 模式")
                except LLMUnavailable as exc:
                    st.error(f"测试失败：{exc}")
        if c2.button("清除本机 Key", use_container_width=True, key="llm_clear"):
            llm_settings.save_settings("", "", "", "")
            st.info("已清除。当前回到纯规则模式。")
            st.rerun()

        st.caption("说明：Key 只写进本机 `.env`，不进代码、不进仓库、不进提交包。"
                   "换人使用时，对方填自己的即可。")


@st.cache_data(show_spinner=False)
def load_data(root: str, track: str):
    cfg = load_config(track=track)
    clean = Path(cfg["paths"]["clean"])
    judged = pd.DataFrame(read_jsonl(clean / "judged.jsonl"))
    clusters = pd.DataFrame(read_jsonl(clean / "scored.jsonl"))
    metrics = read_jsonl(clean / "cluster_metrics.jsonl")
    detail = read_jsonl(clean / "score_detail.jsonl")
    funnel = read_jsonl(clean / "dedup_funnel.jsonl")
    return cfg, judged, clusters, metrics, detail, funnel


def main() -> None:
    base_cfg = load_config(track="all")
    with st.sidebar:
        st.title("🎯 机会评估系统")
        st.caption("AI 应用场景的智能挖掘与机会评估")
        if is_public_demo():
            st.caption("🌐 公网访问：可浏览全部批次；发起新需求请回「首页」")
        if st.button("← 返回首页", use_container_width=True):
            # 必须用绝对路径：云端主入口在仓库根目录，
            # 相对路径 "home.py" 会以主入口目录为基准解析，导致找不到页面
            st.switch_page(str(Path(__file__).resolve().parent / "home.py"))
        auth.mode_switcher()
        auth.role_selector()
        st.divider()
        render_llm_settings(base_cfg)
        st.divider()
        all_tracks = ["all"] + list(TRACKS) + [
            k for k in (base_cfg.get("tracks") or {})
            if k not in TRACKS]
        # 首页「发起新需求」创建的批次（data/tracks/*.json）也要能在这里选到
        _tdir = ROOT / "data" / "tracks"
        if _tdir.exists():
            for _f in sorted(_tdir.glob("*.json")):
                try:
                    _t = json.loads(_f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                _slug = _t.get("slug") or _f.stem
                if _slug not in all_tracks:
                    all_tracks.append(_slug)
                    TRACK_LABEL.setdefault(
                        _slug, _t.get("label") or _t.get("demand_direction") or _slug)
        _q = {}
        try:
            _q = dict(st.query_params)
        except Exception:
            _q = {}
        _want = _q.get("track") or st.session_state.get("view_track")
        _idx = all_tracks.index(_want) if _want in all_tracks else 0
        # 批次列表自动刷新：data/tracks 有新增/修改时，自动重跑一次
        try:
            _sig = "|".join(f"{p.name}:{int(p.stat().st_mtime)}"
                            for p in sorted((ROOT / "data" / "tracks").glob("*.json")))
            _prev = st.session_state.get("_track_sig")
            if _prev is not None and _prev != _sig:
                st.session_state["_track_sig"] = _sig
                st.rerun()
            st.session_state["_track_sig"] = _sig
        except Exception:
            pass

        _c1, _c2 = st.columns([3, 1])
        if _c2.button("⟳", help="刷新批次列表（刚创建的批次没出现时点这里）",
                      use_container_width=True):
            st.rerun()
        with _c1:
            track = st.radio(
                "赛道 / 批次", all_tracks, index=_idx,
            format_func=lambda t: TRACK_LABEL.get(
                t, (base_cfg.get("tracks", {}).get(t, {}) or {}).get("label", t)))
        st.divider()

    cfg, judged, clusters, metrics, detail, funnel = load_data(str(ROOT), track)

    if judged.empty and track != "all":
        # 这批数据可能只在本地跑过、没随仓库发布（如云端演示只带了部分批次）
        st.warning(f"批次「{TRACK_LABEL.get(track, track)}」在当前环境没有明细数据，"
                   f"已自动切换到「两赛道合并（提交版）」。")
        track = "all"
        cfg, judged, clusters, metrics, detail, funnel = load_data(str(ROOT), track)

    if judged.empty:
        st.error("当前环境没有任何可用的结果数据。"
                 "本地可运行：`python run_all.py --track all --offline --force`")
        return

    with st.sidebar:
        sources = sorted(judged["source"].dropna().unique().tolist())
        picked = st.multiselect("来源筛选", sources, default=sources)
        only_opp = st.checkbox("只看机会记录", value=False)

    view = judged[judged["source"].isin(picked)] if picked else judged
    if only_opp:
        view = view[view["is_opportunity"] == 1]
    st.sidebar.divider()
    st.sidebar.metric("当前筛选记录", len(view))

    # ---------------- ① 总览 ----------------
    st.subheader("① 数据总览")
    c1, c2, c3, c4, c5 = st.columns(5)
    n_all = len(judged)
    n_opp = int((judged["is_opportunity"] == 1).sum())
    c1.metric("清洗后记录", f"{n_all}")
    c2.metric("机会记录", f"{n_opp}")
    c3.metric("机会率", f"{n_opp / max(n_all, 1) * 100:.1f}%")
    c4.metric("主题簇", f"{len(clusters)}")
    c5.metric("来源数", f"{judged['source'].nunique()}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**来源分布**")
        st.bar_chart(view["source"].value_counts())
    with col_b:
        st.markdown("**机会率（按来源）**")
        rate = view.groupby("source")["is_opportunity"].mean().sort_values(ascending=False)
        st.bar_chart(rate)

    if funnel:
        f = funnel[0]
        st.caption(f"处理漏斗：去重前 {f.get('raw', 0)} → 去重后 {f.get('after_L3_semantic', 0)}"
                   f"（去重率 {f.get('dedup_rate', 0) * 100:.1f}%）")

    # ---------------- ①b 结果文件下载 ----------------
    with st.expander("⬇ 下载本批次结果文件（result1~4.csv）"):
        out_dir = Path(cfg["paths"]["out"])
        cols = st.columns(4)
        for i, name in enumerate(["result1.csv", "result2.csv",
                                  "result3.csv", "result4.csv"]):
            f = out_dir / name
            if f.exists():
                cols[i].download_button(
                    name, f.read_bytes(), file_name=f"{track}_{name}",
                    mime="text/csv", use_container_width=True,
                    key=f"dl_{track}_{name}")

    # ---------------- ①c 清洗与去重漏斗 ----------------
    if funnel:
        with st.expander("①c 清洗与去重漏斗（任务一过程）", expanded=False):
            f0 = funnel[0]
            st.markdown(
                f"原始采集 **{f0.get('raw',0)}** → 清洗保留 **{f0.get('after_clean', f0.get('raw',0))}** → "
                f"L1 URL 去重 **{f0.get('after_L1_url',0)}** → "
                f"L2 SimHash **{f0.get('after_L2_simhash',0)}** → "
                f"L3 语义 **{f0.get('after_L3_semantic',0)}**")
            st.bar_chart(pd.Series({
                "原始采集": f0.get("raw", 0),
                "清洗保留": f0.get("after_clean", f0.get("raw", 0)),
                "L1 后": f0.get("after_L1_url", 0),
                "L2 后": f0.get("after_L2_simhash", 0),
                "L3 后": f0.get("after_L3_semantic", 0),
            }, name="记录数"))

    # ---------------- ② 主题簇 ----------------
    st.subheader("② 主题簇与优先级")
    if not clusters.empty:
        scatter = clusters[["topic_name", "n_sources", "n_records", "value_score", "priority"]].copy()
        scatter.columns = ["主题簇", "来源覆盖", "记录数", "价值分", "优先级"]
        st.markdown("**气泡图：来源覆盖 × 记录数（点大小 = 价值分）**")
        st.scatter_chart(scatter, x="来源覆盖", y="记录数", size="价值分", color="优先级")

        show = clusters[["cluster_id", "topic_name", "func_category", "industry",
                         "n_records", "n_sources", "value_score", "priority"]].copy()
        show.columns = ["簇编号", "主题簇名称", "功能类别", "所属行业",
                        "记录数", "来源数", "机会价值分", "优先级"]
        st.dataframe(show.sort_values("优先级"), use_container_width=True, hide_index=True)
    else:
        st.info("暂无主题簇。")

    # ---------------- ③ 单簇详情 ----------------
    st.subheader("③ 单簇详情（可溯源到原文）")
    if not clusters.empty and "records" in clusters.columns:
        names = [f"{r['cluster_id']} · {r['topic_name']}" for _, r in clusters.iterrows()]
        pick = st.selectbox("选择一个主题簇", names)
        row = clusters.iloc[names.index(pick)]

        d1, d2 = st.columns([1, 2])
        with d1:
            st.metric("机会价值分", f"{row['value_score']}")
            st.metric("优先级", f"{int(row['priority'])}")
            st.metric("来源覆盖", f"{row['n_sources']} 个")
            st.caption("、".join(row["sources"]))
            if row.get("dim_scores"):
                st.markdown("**各维度得分**")
                st.bar_chart(pd.Series(row["dim_scores"]).rename("得分"))
        with d2:
            recs = pd.DataFrame(row["records"])
            keep = [c for c in ["record_id", "source", "title", "heat_str", "url"] if c in recs.columns]
            st.dataframe(recs[keep], use_container_width=True, hide_index=True)
            for _, r in recs.head(5).iterrows():
                st.markdown(f"- [{r.get('title') or r['record_id']}]({r.get('url', '')})")

    # ---------------- ④ 立项策划案 ----------------
    st.subheader("④ 立项策划案")
    rep_dir = track_report_dir(cfg, track)
    reports = sorted(rep_dir.glob("proposal_*.md")) if rep_dir.exists() else []
    if reports:
        pick = st.selectbox("选择策划案", [p.name for p in reports])
        _f = rep_dir / pick
        st.download_button("⬇ 下载策划案（Markdown）", _f.read_bytes(),
                           file_name=pick, mime="text/markdown",
                           key=f"dl_prop_{track}_{pick}")
        _docx = _f.with_suffix(".docx")
        if _docx.exists():
            st.download_button("⬇ 下载策划案（Word）", _docx.read_bytes(),
                               file_name=_docx.name,
                               mime="application/vnd.openxmlformats-officedocument"
                                    ".wordprocessingml.document",
                               key=f"dl_docx_{track}_{pick}")
        st.divider()
        st.markdown(_f.read_text(encoding="utf-8"))
    else:
        st.info("还没有策划案。运行 `python run_all.py --track all` 生成。")

    # ---------------- ⑤ 方法与参数 ----------------
    with st.expander("⑤ 方法与参数（论文引用这里）"):
        st.markdown(f"""
- **需求方向**：{cfg['project'].get('demand_direction')}
- **判别阈值 τ**：{cfg['judge']['threshold']}（标定脚本 `scripts/tune_threshold.py`）
- **聚类方法**：{cfg['cluster'].get('method')}，merge_sim={cfg['cluster'].get('merge_sim')}，
  简约容差={cfg['cluster'].get('k_tolerance')}
- **权重法**：{cfg['score'].get('weight_method')}，α={cfg['score'].get('alpha')}
""")
        if metrics:
            m = metrics[0]
            st.markdown("**聚类评估**")
            st.json({k: v for k, v in m.items() if k != "k_sweep"})
            if m.get("k_sweep"):
                st.markdown("**k 扫描（论文作图用）**")
                st.dataframe(pd.DataFrame(m["k_sweep"]), use_container_width=True, hide_index=True)
        if detail:
            st.markdown("**权重与敏感性**")
            st.json({"weights": detail[0].get("weight_detail", {}),
                     "sensitivity": detail[0].get("sensitivity", {})})

    audit_md = rep_dir / "data_audit.md"
    if audit_md.exists():
        with st.expander("⑥ 数据审计（对应评分标准第一条）"):
            st.markdown(audit_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
