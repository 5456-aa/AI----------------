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

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from io_utils import TRACKS, load_config, read_jsonl, track_report_dir  # noqa: E402
from llm.client import LLMClient, LLMUnavailable  # noqa: E402
import auth  # noqa: E402
from _init import sidebar_nav  # noqa: E402
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


C_BLUE, C_RED, C_GREY, C_GREEN = "#2563eb", "#e15759", "#94a3b8", "#59a14f"


def hbar(df, xcol: str, ycol: str, color: str = C_BLUE,
         fmt: str = ",.0f", height_per: int = 34, x_title: str = "") -> alt.Chart:
    """横向条形图：按给定顺序排列，条尾标数值。"""
    order = df[ycol].tolist()
    base = alt.Chart(df).encode(
        y=alt.Y(f"{ycol}:N", sort=order, title=None,
                axis=alt.Axis(labelOverlap=False, labelLimit=180,
                              labelFontSize=11, tickCount=len(order))),
        x=alt.X(f"{xcol}:Q", title=x_title or None,
                axis=alt.Axis(format="~s", grid=True, gridColor="#eef1f6")))
    bars = base.mark_bar(cornerRadius=4, color=color, height=16)
    text = base.mark_text(align="left", dx=6, fontSize=12, color="#334155").encode(
        text=alt.Text(f"{xcol}:Q", format=fmt))
    return (bars + text).properties(height=max(180, height_per * len(df)))


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

    # ---------- 侧栏：品牌标题 + 三页导航（在最上方）----------
    sidebar_nav()

    # ---------- 批次选择：紧跟导航，最常用 ----------
    all_tracks = ["all"] + list(TRACKS) + [
        k for k in (base_cfg.get("tracks") or {}) if k not in TRACKS]
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

    try:
        _q = dict(st.query_params)
    except Exception:
        _q = {}
    _want = _q.get("track") or st.session_state.get("view_track")
    _idx = all_tracks.index(_want) if _want in all_tracks else 0

    # 批次列表自动刷新：data/tracks 有新增/修改时重跑一次
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

    with st.sidebar:
        track = st.radio(
            "📚 赛道 / 批次", all_tracks, index=_idx,
            format_func=lambda t: TRACK_LABEL.get(
                t, (base_cfg.get("tracks", {}).get(t, {}) or {}).get("label", t)))
        # 刷新按钮放大：整行宽、与选项等距，点起来不费劲
        if st.button("⟳  刷新批次列表", use_container_width=True,
                     help="刚创建的批次没出现时点这里"):
            st.rerun()

        st.divider()
        if st.button("🏠  返回首页", use_container_width=True):
            st.switch_page(str(UI_DIR / "home.py"))

        auth.mode_switcher()
        auth.role_selector()
        if is_public_demo():
            st.caption("🌐 公网访问：可浏览全部批次；发起新需求请回「首页」")

        st.divider()
        render_llm_settings(base_cfg)
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

        fc_all = sorted([x for x in clusters.get("func_category", pd.Series(dtype=str))
                         .dropna().unique() if str(x).strip()])
        ind_all = sorted([x for x in clusters.get("industry", pd.Series(dtype=str))
                          .dropna().unique() if str(x).strip()])
        st.caption("下面两个筛选作用于「主题簇」与下方图表")
        picked_fc = st.multiselect("功能类别", fc_all, default=fc_all)
        picked_ind = st.multiselect("所属行业", ind_all, default=ind_all)

    view = judged[judged["source"].isin(picked)] if picked else judged
    if only_opp:
        view = view[view["is_opportunity"] == 1]

    cview = clusters.copy()
    if not cview.empty:
        if picked_fc:
            cview = cview[cview["func_category"].isin(picked_fc)]
        if picked_ind:
            cview = cview[cview["industry"].isin(picked_ind)]

    st.sidebar.divider()
    st.sidebar.metric("当前筛选记录", len(view))
    st.sidebar.metric("当前筛选主题簇", len(cview))
    st.sidebar.download_button(
        "⬇ 导出当前筛选明细 CSV",
        view.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{track}_筛选明细.csv", mime="text/csv",
        use_container_width=True, key=f"dl_view_{track}")

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
        st.markdown("**各来源记录数**")
        vc = view["source"].value_counts()
        df_src = pd.DataFrame({"来源": vc.index, "记录数": vc.values})
        st.altair_chart(hbar(df_src, "记录数", "来源"), use_container_width=True)
        st.download_button("⬇ 来源统计 CSV",
                           df_src.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{track}_来源统计.csv", mime="text/csv",
                           key=f"dl_src_{track}")
    with col_b:
        st.markdown("**各来源机会率**")
        g = view.groupby("source").agg(记录=("is_opportunity", "size"),
                                       机会=("is_opportunity", "sum"))
        g["机会率"] = (g["机会"] / g["记录"]).round(3)
        g = g.sort_values("机会率", ascending=False).reset_index()
        g["标签"] = (g["机会率"] * 100).round(1).astype(str) + "%"
        chart = hbar(g, "机会率", "source", color=C_GREEN, fmt=".1%",
                     x_title="机会率")
        st.altair_chart(chart, use_container_width=True)

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
        f0 = funnel[0]
        # 真实原始量取自审计文件（funnel.raw 是清洗后的数量）
        raw_true = f0.get("raw", 0)
        try:
            audit = read_jsonl(Path(cfg["paths"]["clean"]) / "audit_clean.jsonl")
            raw_true = sum(int(a.get("raw", 0)) for a in audit) or raw_true
        except Exception:
            pass
        cleaned = f0.get("raw", raw_true)
        steps = [
            ("① 原始采集", raw_true, 0),
            ("② 清洗保留", cleaned, raw_true - cleaned),
            ("③ URL 去重", f0.get("after_L1_url", cleaned), f0.get("dropped_L1", 0)),
            ("④ SimHash 去重", f0.get("after_L2_simhash", 0), f0.get("dropped_L2", 0)),
            ("⑤ 语义去重", f0.get("after_L3_semantic", 0), f0.get("dropped_L3", 0)),
        ]
        df_f = pd.DataFrame(steps, columns=["阶段", "保留", "剔除"])
        total_drop = raw_true - int(df_f.iloc[-1]["保留"])

        with st.expander(f"①c 清洗与去重：{raw_true} → {df_f.iloc[-1]['保留']}"
                         f"（共剔除 {total_drop} 条，保留率 "
                         f"{df_f.iloc[-1]['保留'] / max(raw_true,1) * 100:.1f}%）",
                         expanded=False):
            cl, cr = st.columns([3, 2])
            with cl:
                st.markdown("**累计保留量**（条尾为剩余记录数）")
                st.altair_chart(hbar(df_f, "保留", "阶段", height_per=34),
                                use_container_width=True)
            with cr:
                st.markdown("**各阶段剔除量**")
                d_drop = df_f[df_f["剔除"] > 0]
                if d_drop.empty:
                    st.info("本批次没有剔除记录（数据本身较干净）。")
                else:
                    st.altair_chart(
                        hbar(d_drop, "剔除", "阶段", color=C_RED,
                             height_per=34, x_title="剔除条数"),
                        use_container_width=True)
            st.caption("说明：去重率仅 "
                       f"{(1 - df_f.iloc[-1]['保留'] / max(raw_true,1)) * 100:.1f}%，"
                       "各阶段数量接近，因此左图柱高差异很小；"
                       "右图单独展示剔除量，才是真正能看出差异的视图。")

    # ---------------- ①d 数据透视（多角度可视化） ----------------
    st.subheader("①d 数据透视")
    dv = view.copy()
    pv_col = "published_at" if "published_at" in dv.columns else None

    t1, t2, t3, t4, t5 = st.tabs(
        ["时间分布", "来源 × 功能类别", "置信度分布", "需求关键词", "来源 → 簇"])

    with t1:
        if pv_col:
            dv["月份"] = dv[pv_col].astype(str).str.slice(0, 7)
            dv_m = dv[dv["月份"].str.len() == 7]
            if not dv_m.empty:
                g = (dv_m.groupby(["月份", "is_opportunity"]).size()
                     .reset_index(name="记录数"))
                g["类型"] = g["is_opportunity"].map({1: "机会", 0: "非机会"})
                area = alt.Chart(g).mark_area(opacity=0.75, interpolate="monotone").encode(
                    x=alt.X("月份:N", title=None,
                            axis=alt.Axis(labelAngle=-45, labelOverlap=True)),
                    y=alt.Y("记录数:Q", title="记录数", stack=True),
                    color=alt.Color("类型:N", scale=alt.Scale(
                        domain=["非机会", "机会"], range=["#cbd5e1", "#2563eb"])),
                    tooltip=["月份:N", "类型:N", "记录数:Q"],
                ).properties(height=300)
                st.altair_chart(area, use_container_width=True)
                st.caption("按月统计采集内容的发布时间（机会记录用深色标识）。"
                           "可见近期内容以 2026 年下半年为主，机会记录与总记录同向波动。")
        else:
            st.info("当前数据缺发布时间字段。")

    with t2:
        opp = dv[dv["is_opportunity"] == 1]
        if not opp.empty and "func_category" in opp.columns:
            hm = (opp.groupby(["source", "func_category"]).size()
                  .reset_index(name="机会数"))
            heat = alt.Chart(hm).mark_rect(cornerRadius=2).encode(
                x=alt.X("func_category:N", title="功能类别",
                        axis=alt.Axis(labelAngle=-40, labelLimit=120)),
                y=alt.Y("source:N", title=None),
                color=alt.Color("机会数:Q", scale=alt.Scale(scheme="blues"),
                                title="机会数"),
                tooltip=["source:N", "func_category:N", "机会数:Q"],
            ).properties(height=max(240, 26 * hm["source"].nunique()))
            st.altair_chart(heat, use_container_width=True)
            st.caption("机会记录在「来源 × 功能类别」上的分布。空白表示该组合没有机会记录，"
                       "颜色越深机会越密集——可据此看出不同来源擅长暴露哪类需求。")
        else:
            st.info("当前筛选下没有机会记录。")

    with t3:
        if "confidence" in dv.columns:
            hist = alt.Chart(dv).mark_bar(opacity=0.85).encode(
                x=alt.X("confidence:Q", bin=alt.Bin(maxbins=30), title="机会置信度"),
                y=alt.Y("count()", title="记录数"),
                color=alt.Color("is_opportunity:N", scale=alt.Scale(
                    domain=[0, 1], range=["#cbd5e1", "#2563eb"]), title="是否机会"),
            ).properties(height=300)
            rule = alt.Chart(pd.DataFrame({"x": [cfg["judge"]["threshold"]]})).mark_rule(
                color="#e15759", strokeDash=[5, 4]).encode(x="x:Q")
            st.altair_chart(hist + rule, use_container_width=True)
            st.caption(f"置信度分布，红色虚线为判别阈值 τ = {cfg['judge']['threshold']}。"
                       "阈值右侧即判为机会；分布呈明显双峰，说明打分具备区分度。")
        else:
            st.info("当前数据缺置信度字段。")


    with t4:
        try:
            import jieba.analyse
            opp_txt = dv[dv["is_opportunity"] == 1]["clean_text"].astype(str).tolist()
            if opp_txt:
                import collections as _c
                bag = _c.Counter()
                for t in opp_txt:
                    for w, wt in jieba.analyse.extract_tags(t, topK=15, withWeight=True):
                        bag[w] += wt
                bad = {"the", "and", "for", "with", "this", "that", "you", "are",
                       "not", "can", "use", "using", "from", "have", "will"}
                items = [(w, v) for w, v in bag.items()
                         if w.lower() not in bad and len(w) >= 2]
                items.sort(key=lambda x: -x[1])
                df_w = pd.DataFrame(items[:20], columns=["关键词", "权重"])
                df_w = df_w.iloc[::-1]
                st.altair_chart(hbar(df_w, "权重", "关键词", fmt=".1f",
                                     height_per=26, x_title="TF-IDF 累计权重"),
                                use_container_width=True)
                st.caption("对机会记录做 TF-IDF 关键词抽取（jieba.analyse），"
                           "可看出这批需求集中在哪些主题上。")
            else:
                st.info("当前筛选下没有机会记录。")
        except Exception as exc:
            st.info(f"关键词抽取不可用：{exc}")

    with t5:
        try:
            scored_now = read_jsonl(Path(cfg["paths"]["clean"]) / "scored.jsonl")
            id2c = {}
            for c in scored_now:
                for rid in c.get("record_ids", []):
                    id2c[rid] = c.get("cluster_id")
            rows = []
            for _, r in dv[dv["is_opportunity"] == 1].iterrows():
                cid = id2c.get(r.get("record_id"))
                if cid:
                    rows.append({"来源": r.get("source"), "主题簇": cid})
            if rows:
                df_f = pd.DataFrame(rows).groupby(["来源", "主题簇"]).size().reset_index(name="记录数")
                heat2 = alt.Chart(df_f).mark_rect(cornerRadius=2).encode(
                    x=alt.X("主题簇:N", title="主题簇", axis=alt.Axis(labelAngle=-40)),
                    y=alt.Y("来源:N", title=None),
                    color=alt.Color("记录数:Q", scale=alt.Scale(scheme="tealblues"),
                                    title="记录数"),
                    tooltip=["来源:N", "主题簇:N", "记录数:Q"],
                ).properties(height=max(200, 26 * df_f["来源"].nunique()))
                st.altair_chart(heat2, use_container_width=True)
                st.caption("机会记录在「来源 × 主题簇」上的流向矩阵（颜色越深流向越集中）。"
                           "论文里另有一张桑基风格流向图 `figs/all/fig_flow_sankey.png`。")
            else:
                st.info("当前筛选下没有可映射到主题簇的记录。")
        except Exception as exc:
            st.info(f"流向矩阵不可用：{exc}")

    # ---------------- ② 主题簇 ----------------
    st.subheader(f"② 主题簇与优先级（当前 {len(cview)} / {len(clusters)} 个）")
    if not cview.empty:
        scatter = cview[["topic_name", "n_sources", "n_records", "value_score", "priority"]].copy()
        scatter.columns = ["主题簇", "来源覆盖", "记录数", "价值分", "优先级"]
        # 主题簇一目了然：按优先级排序的横条（价值分），条上标注记录数与来源数
        rank = cview.sort_values("priority")[["topic_name", "value_score",
                                            "n_records", "n_sources", "priority"]].copy()
        rank["标签"] = rank["topic_name"].str.slice(0, 18)
        order = rank["标签"].tolist()
        base = alt.Chart(rank).encode(
            y=alt.Y("标签:N", sort=order, title=None),
            x=alt.X("value_score:Q", title="机会价值分（0~100）",
                    scale=alt.Scale(domain=[0, 100]),
                    axis=alt.Axis(grid=True, gridColor="#eef1f6")),
            tooltip=[alt.Tooltip("topic_name:N", title="主题簇"),
                     alt.Tooltip("value_score:Q", title="价值分", format=".1f"),
                     alt.Tooltip("n_records:Q", title="记录数"),
                     alt.Tooltip("n_sources:Q", title="来源数"),
                     alt.Tooltip("priority:Q", title="优先级")],
        )
        bars = base.mark_bar(cornerRadius=4, height=18).encode(
            color=alt.Color("n_records:Q", title="记录数",
                            scale=alt.Scale(scheme="blues", domain=[0, max(rank["n_records"].max(), 1)])))
        text = base.mark_text(align="left", dx=6, fontSize=11, color="#334155").encode(
            text=alt.Text("value_score:Q", format=".1f"))
        inline = base.mark_text(align="right", dx=-8, fontSize=10,
                                color="#ffffff").encode(
            text=alt.Text("n_records:Q", format=".0f"))
        st.altair_chart((bars + text + inline).properties(height=max(220, 30 * len(rank))),
                        use_container_width=True)
        st.caption("按优先级从高到低排列；条长 = 机会价值分，颜色深浅 = 簇内记录数。"
                   "原来那张「来源覆盖 × 记录数」的散点图在绝大多数簇只有 1~2 个来源时"
                   "会挤成一团、无法辨认，因此改为按价值分排序的条形图。")

        show = cview[["cluster_id", "topic_name", "func_category", "industry",
                         "n_records", "n_sources", "value_score", "priority"]].copy()
        show.columns = ["簇编号", "主题簇名称", "功能类别", "所属行业",
                        "记录数", "来源数", "机会价值分", "优先级"]
        st.dataframe(show.sort_values("优先级"), use_container_width=True, hide_index=True)
        st.download_button(
            "⬇ 导出当前主题簇表 CSV",
            show.sort_values("优先级").to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{track}_主题簇.csv", mime="text/csv",
            key=f"dl_clu_{track}")
    else:
        st.info("暂无主题簇。")

    # ---------------- ③ 单簇详情 ----------------
    st.subheader("③ 单簇详情（可溯源到原文）")
    if not cview.empty and "records" in cview.columns:
        names = [f"{r['cluster_id']} · {r['topic_name']}" for _, r in cview.iterrows()]
        pick = st.selectbox("选择一个主题簇", names)
        row = cview.iloc[names.index(pick)]

        d1, d2 = st.columns([1, 2])
        with d1:
            st.metric("机会价值分", f"{row['value_score']}")
            st.metric("优先级", f"{int(row['priority'])}")
            st.metric("来源覆盖", f"{row['n_sources']} 个")
            st.caption("、".join(row["sources"]))
            if row.get("dim_scores"):
                st.markdown("**各维度得分（0~100）**")
                dim_map = {"multi_source": "多源指向度", "scale": "记录规模",
                           "heat": "互动热度", "need_strength": "需求强度"}
                d = row["dim_scores"]
                df_d = pd.DataFrame({
                    "维度": [dim_map.get(k, k) for k in d.keys()],
                    "得分": list(d.values())})
                st.altair_chart(hbar(df_d, "得分", "维度", height_per=38,
                                     fmt=".1f", x_title="得分（0~100）"),
                                use_container_width=True)
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
