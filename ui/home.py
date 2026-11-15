# -*- coding: utf-8 -*-
"""系统首页：需求驱动入口（8500）。

设计：第一屏只做一件事——让用户说清要挖什么方向。
其余参数收进「高级设置」，默认值已经能跑。

联动：跑完可一键跳转分析看板（8501）与问答（8505），并带上批次参数。
"""
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
_UI_DIR = Path(__file__).resolve().parent      # 页面跳转用绝对路径
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402
from collectors.registry import ENABLED_SOURCES, SOURCE_STATUS  # noqa: E402
from io_utils import load_config  # noqa: E402

from _init import page_config, sidebar_nav; page_config("AI 机会评估系统", "🎯")

TRACKS_DIR = ROOT / "data" / "tracks"
OUT_DIR = ROOT / "data" / "out"
DASHBOARD = "http://localhost:8501"
QA = "http://localhost:8505"

CSS = """
<style>
.block-container{padding-top:1.2rem;padding-bottom:2rem;max-width:1180px}
h1,h2,h3,h4{letter-spacing:.2px}
section[data-testid="stSidebar"]{background:#fafbff;border-right:1px solid #eef1f6;
  min-width:270px;max-width:270px}

.hero{
  background:linear-gradient(120deg,#1e3a8a 0%,#2563eb 55%,#3b82f6 100%);
  border-radius:18px;padding:30px 34px;color:#fff;margin-bottom:20px;
  box-shadow:0 10px 30px rgba(37,99,235,.22);position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;right:-60px;top:-60px;width:240px;height:240px;
  background:radial-gradient(circle,rgba(255,255,255,.18),transparent 70%);border-radius:50%}
.hero h1{margin:0 0 6px;font-size:30px;font-weight:800;color:#fff}
.hero p{margin:0;opacity:.9;font-size:14.5px}
.pills{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
.pill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.28);
  border-radius:999px;padding:7px 15px;font-size:13px}
.pill b{font-size:16px;font-weight:800}

.card-title{font-size:16px;font-weight:700;color:#0f172a;margin:6px 0 10px}

div[data-testid="stButton"]>button{
  border-radius:12px;border:1px solid #e2e8f0;background:#fff;
  padding:.55rem .6rem;font-size:13.5px;transition:all .15s ease;text-align:left}
div[data-testid="stButton"]>button:hover{
  border-color:#2563eb;color:#1d4ed8;transform:translateY(-1px);
  box-shadow:0 6px 16px rgba(37,99,235,.12)}
div[data-testid="stButton"]>button[kind="primary"]{
  background:linear-gradient(120deg,#2563eb,#3b82f6);border:none;color:#fff;
  font-weight:600;box-shadow:0 6px 18px rgba(37,99,235,.25)}

div[data-testid="stTextInput"] input{
  border-radius:12px;border:1.5px solid #e2e8f0;padding:.7rem .9rem;font-size:15px}
div[data-testid="stTextInput"] input:focus{
  border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}

div[data-testid="stMetric"]{background:#fff;border:1px solid #eef1f6;border-radius:14px;
  padding:14px 16px;box-shadow:0 2px 10px rgba(15,23,42,.04)}
div[data-testid="stMetricValue"]{font-size:24px;font-weight:800;color:#1e3a8a}

div[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;border:1px solid #eef1f6}
hr{margin:1.6rem 0;border-color:#eef1f6}
.section{margin:28px 0 8px;font-size:17px;font-weight:800;color:#0f172a;
  display:flex;align-items:center;gap:10px}
.section em{font-style:normal;background:linear-gradient(120deg,#2563eb,#3b82f6);
  color:#fff;width:26px;height:26px;border-radius:8px;display:inline-flex;
  align-items:center;justify-content:center;font-size:14px}
.side-title{font-size:13px;font-weight:800;color:#1e3a8a;letter-spacing:.5px;
  margin:4px 0 8px}
/* 侧栏里的表格不换行，避免中文竖排 */
section[data-testid="stSidebar"] table th,
section[data-testid="stSidebar"] table td{white-space:nowrap}
/* 侧栏 radio 更紧凑 */
section[data-testid="stSidebar"] div[role="radiogroup"] label{
  padding:6px 8px;border-radius:8px;margin-bottom:2px}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover{background:#eef2ff}
@media (max-width:900px){.hero{padding:22px}.hero h1{font-size:23px}}
</style>
"""

TEMPLATES: list[tuple[str, str, str]] = [
    ("🛒", "电商客服与售后", "退货, 售后, 客服, 退款, 评价"),
    ("🎓", "教育学习与作业批改", "作业批改, 答疑, 错题, 备课"),
    ("🏥", "医疗在线问诊", "在线问诊, 病历, 分诊, 复诊"),
    ("⚖️", "法律合同审查", "合同审查, 法条检索, 合规, 风险条款"),
    ("🧑‍💼", "招聘简历筛选", "简历筛选, 面试, 人才匹配"),
    ("🛡️", "内容审核与风控", "审核, 违规, 风控, 垃圾内容"),
    ("📊", "数据分析与报表", "报表, 取数, 指标, 数据清洗"),
    ("🎧", "客服质检", "质检, 通话记录, 服务评价"),
    ("💻", "代码开发辅助", "代码生成, 调试, 单测, 代码review"),
    ("✍️", "营销文案生成", "文案, 投放, 素材, 标题"),
]


# ---------------------------------------------------------------------------
def public_urls() -> dict[str, str]:
    """隧道启动时写入的公网地址（公网访客点「看板」要用它，不能给 localhost）。"""
    p = ROOT / "data" / "runtime" / "public_urls.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def all_tracks() -> dict[str, str]:
    cfg = load_config(track="all")
    m: dict[str, str] = {}
    for slug, t in (cfg.get("tracks") or {}).items():
        if slug == "all":
            continue
        m[slug] = t.get("label") or t.get("demand_direction") or slug
    if TRACKS_DIR.exists():
        for f in sorted(TRACKS_DIR.glob("*.json")):
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            slug = t.get("slug") or f.stem
            m.setdefault(slug, t.get("label") or t.get("demand_direction") or slug)
    return m


def batch_stats(slug: str) -> dict:
    rec = {"n": 0, "opp": 0, "clusters": 0}
    r2, r3 = OUT_DIR / slug / "result2.csv", OUT_DIR / slug / "result3.csv"
    if r2.exists():
        with io.open(r2, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        rec["n"] = len(rows)
        rec["opp"] = sum(1 for r in rows if r.get("是否构成机会") == "1")
    if r3.exists():
        with io.open(r3, encoding="utf-8-sig") as fh:
            rec["clusters"] = len(list(csv.DictReader(fh)))
    return rec


def next_batch_no() -> str:
    today = datetime.now().strftime("%Y%m%d")
    used = set()
    for p in OUT_DIR.glob("*/result1.csv"):
        try:
            with io.open(p, encoding="utf-8-sig") as fh:
                first = next(csv.DictReader(fh), None)
            b = (first or {}).get("采集批次号", "")
            if b.startswith(f"B{today}"):
                used.add(b)
        except Exception:
            continue
    n = 1
    while f"B{today}-{n:02d}" in used:
        n += 1
    return f"B{today}-{n:02d}"


STAGES = [
    ("采集", ("collect", "采集中", "条 ->")),
    ("清洗", ("clean", "清洗保留")),
    ("去重", ("dedup", "去重完成")),
    ("判别", ("judge", "判别完成")),
    ("聚类", ("cluster", "聚类完成")),
    ("评分", ("score", "权重")),
    ("导出", ("export", "result1.csv")),
]


def _stage_of(line: str) -> str | None:
    low = line.lower()
    for name, keys in STAGES:
        if any(k.lower() in low for k in keys):
            return name
    return None


def stream(cmd: list[str], bar, status, log_box,
           offline: bool = False) -> tuple[int, list[str]]:
    """只显示阶段与进度；原始日志收进折叠区（不刷屏）。"""
    lines: list[str] = []
    done: set[str] = set()
    env = dict(os.environ)
    if offline:
        env["LLM_OFFLINE"] = "1"      # 硬保证：不发起任何 API 调用
    else:
        v = st.session_state.get("visitor_llm") or {}
        if v.get("key"):
            import llm_settings as _ls
            pv = _ls.PROVIDERS.get(v["provider"], {})
            env[pv.get("env", "LLM_API_KEY")] = v["key"]
            env["LLM_BASE_URL"] = pv.get("base_url", "")
            env["LLM_MODEL"] = pv.get("model", "")
            env.pop("LLM_OFFLINE", None)
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
    for line in proc.stdout:            # type: ignore[union-attr]
        clean_line = line.rstrip()
        lines.append(clean_line)
        if len(lines) > 800:
            lines = lines[-800:]
        st_name = _stage_of(clean_line)
        if st_name and st_name not in done:
            done.add(st_name)
            pct = min(len(done) / len(STAGES), 0.99)
            bar.progress(pct, text=f"正在进行：{st_name}（{len(done)}/{len(STAGES)}）")
            status.caption(" → ".join(f"**{s}**" if s in done else s
                                      for s, _ in STAGES))
        log_box.code("\n".join(lines[-15:]), language="text")
    proc.wait()
    bar.progress(1.0, text="完成")
    return proc.returncode, lines


def top_clusters(slug: str, k: int = 3) -> list[dict]:
    p = OUT_DIR / slug / "result4.csv"
    if not p.exists():
        return []
    with io.open(p, encoding="utf-8-sig") as fh:
        rws = list(csv.DictReader(fh))
    rws.sort(key=lambda r: int(r["优先级"]))
    return rws[:k]


def result_block(slug: str, label: str) -> None:
    s = batch_stats(slug)
    c1, c2, c3 = st.columns(3)
    c1.metric("入表记录", s["n"])
    c2.metric("机会记录", s["opp"], f"{s['opp']/max(s['n'],1)*100:.1f}%")
    c3.metric("主题簇", s["clusters"])

    if s["opp"] == 0:
        st.warning("本批次未识别到机会记录（0 条）。常见原因：\n\n"
                   "- 方向太窄或太新，缓存里没有对应内容（离线模式会退回规则判别）\n"
                   "- 采集来源太少，建议在「高级设置」里多选几个来源\n"
                   "- 关键词太具体，可在高级设置里改写检索词\n\n"
                   "result1/result2 仍会正常产出，result3/result4 为空表。")

    top = top_clusters(slug)
    if top:
        st.markdown('<div class="card-title">🏆 价值最高的方向</div>',
                    unsafe_allow_html=True)
        for r in top:
            st.markdown(
                f"**P{r['优先级']}　{r['主题簇名称']}**　"
                f"<span style='color:#64748b'>{r['功能类别']} / {r['所属行业']}</span>　"
                f"价值分 **{r['机会价值分']}**", unsafe_allow_html=True)

    a, b = st.columns(2)
    if a.button("📊 打开分析看板", use_container_width=True, key=f"go_dash_{slug}"):
        st.session_state["view_track"] = slug
        st.switch_page(str(_UI_DIR / "app.py"))
    if b.button("💬 就这批结果提问", use_container_width=True, key=f"go_qa_{slug}"):
        st.switch_page(str(_UI_DIR / "qa.py"))
    st.caption("单应用多页：点按钮直接切换，不会跳出站点。")


# ---------------------------------------------------------------------------
def _watch_tracks() -> None:
    """批次目录有新增/修改时自动重跑一次，保证列表不过期。"""
    try:
        sig = "|".join(f"{p.name}:{int(p.stat().st_mtime)}"
                       for p in sorted((ROOT / "data" / "tracks").glob("*.json")))
        prev = st.session_state.get("_home_track_sig")
        if prev is not None and prev != sig:
            st.session_state["_home_track_sig"] = sig
            st.rerun()
        st.session_state["_home_track_sig"] = sig
    except Exception:
        pass


def main() -> None:
    sidebar_nav()

    st.markdown(CSS, unsafe_allow_html=True)
    _watch_tracks()
    tracks = all_tracks()
    total_opp = sum(batch_stats(s)["opp"] for s in tracks)
    total_src = len(ENABLED_SOURCES)

    st.markdown(f"""
<div class="hero">
  <h1>🎯 AI 应用场景机会评估</h1>
  <p>把散落在十余个渠道的零散讨论，变成可排序、可溯源、可落地的方向清单</p>
  <div class="pills">
    <div class="pill">批次 <b>{len(tracks)}</b></div>
    <div class="pill">累计机会 <b>{total_opp}</b></div>
    <div class="pill">接入来源 <b>{total_src}</b></div>
    <div class="pill">一次需求 = 一个批次</div>
  </div>
</div>
""", unsafe_allow_html=True)

    with st.sidebar:
        if (auth.can("collect") and not auth.sees("see_settings")
                and not auth.is_cloud_host()):
            with st.expander("🔑 用我自己的 API Key（可选）", expanded=False):
                import llm_settings as _ls
                _keys = list(_ls.PROVIDERS)
                _pk = st.selectbox(
                    "服务商", _keys, index=0,
                    format_func=lambda k: _ls.PROVIDERS[k]["label"])
                _vkey = st.text_input("Key", type="password",
                                      placeholder="sk-...")
                st.caption("仅用于本次会话，**不写入本机任何文件**；"
                           "不填则走离线缓存与规则。")
                if _vkey.strip():
                    st.session_state["visitor_llm"] = {
                        "provider": _pk, "key": _vkey.strip()}
                    st.success("已填入，将使用你自己的 Key 调用")
                elif st.session_state.get("visitor_llm"):
                    st.session_state.pop("visitor_llm", None)
        auth.mode_switcher()
        st.markdown('<div class="side-title">🎫 当前角色</div>', unsafe_allow_html=True)
        auth.role_selector()
        st.markdown("---")
        st.markdown('<div class="side-title">权限对照</div>', unsafe_allow_html=True)
        auth.panel_compact()

    # ---------- 第一步 ----------
    st.markdown('<div class="section"><em>1</em>　你要挖掘哪个方向？</div>',
                unsafe_allow_html=True)
    st.caption("点下面任意卡片自动填入，也可以自己输入")

    cols = st.columns(5)
    for i, (icon, name, kw) in enumerate(TEMPLATES):
        if cols[i % 5].button(f"{icon} {name}", key=f"tpl{i}",
                              use_container_width=True):
            st.session_state["direction"] = name
            st.session_state["keywords"] = kw

    direction = st.text_input(
        "需求方向", key="direction", placeholder="例如：医疗在线问诊",
        label_visibility="collapsed")

    with st.expander("⚙ 高级设置（不改也能跑）"):
        c1, c2 = st.columns(2)
        keywords = c1.text_input("检索词（逗号分隔，留空按方向自动扩展）", key="keywords")
        limit = c2.number_input("每源条数", 20, 200, 80, step=20)
        c3, c4 = st.columns([3, 1])
        sources = c3.multiselect("采集来源", ENABLED_SOURCES,
                                 default=["GitHub", "掘金", "SegmentFault", "博客园"])
        offline = c4.checkbox("离线模式", value=True,
                              help="只用缓存，不调 API；快且结果可复现")
        try:
            import llm_settings as _ls
            _st = _ls.status(load_config(track="all"))
            _env_key = bool(_st.get("enabled"))
        except Exception:
            _env_key = False
        _vis_key = bool((st.session_state.get("visitor_llm") or {}).get("key"))
        if _vis_key:
            st.caption("🔑 当前：**在线模式**（使用你自己填的 Key，仅本次会话）")
        elif _env_key and not auth.is_cloud_host():
            st.caption("🔑 当前：**在线模式**（使用本机 `.env` 中配置的 Key）")
        else:
            st.caption("💡 当前：**离线模式**（本地缓存 + 规则，**无需 Key**）；"
                       "想要更好的判别质量，可配置 Key 或在左侧填写")
        with st.popover("哪些源不可用？"):
            for name, why in SOURCE_STATUS.items():
                st.caption(f"- **{name}**：{why}")

    public_mode = auth.is_public_request()
    cloud_mode = auth.is_cloud_host()
    allow_collect = auth.can_collect()
    if cloud_mode:
        st.info("☁ 云端为**演示环境**：可发起采集，但强制使用**本地缓存与规则**"
                "（不调用任何外部 API，**无需填写 Key**）。"
                "注意云端容器是临时的，新采集的批次在实例重启后可能丢失；"
                "需要长期保存请在本机运行后 `git push`。", icon="☁")
    _has_key0 = bool((st.session_state.get("visitor_llm") or {}).get("key"))
    if public_mode and allow_collect and _has_key0:
        st.info("🔑 已使用**你自己的 API Key**：本次采集走在线模式，"
                "Key 仅存在本次会话，不写入本机文件、不进日志。", icon="✅")
    elif public_mode and allow_collect:
        st.info("🌐 公网模式：发起采集将使用**本地缓存与规则**（不调用任何外部 API，"
                "不消耗系统管理员的额度）。想用在线模式？在左侧填你自己的 Key。", icon="💡")
    elif not allow_collect:
        st.caption("🔒 当前角色无采集权限：可浏览已有批次结果。")

    _has_key = bool((st.session_state.get("visitor_llm") or {}).get("key"))
    if public_mode and _has_key:
        label = "开始采集与分析（用我的 Key）"
    elif public_mode:
        label = "开始采集与分析（离线）"
    else:
        label = "开始采集与分析"
    go = allow_collect and st.button(label, type="primary",
                                     use_container_width=True)
    if go and not direction.strip():
        st.warning("请先在上面输入需求方向，或点一个模板卡片（例如「医疗在线问诊」）。")
        go = False

    visitor = st.session_state.get("visitor_llm") or {}
    if go and not offline and not (visitor.get("key") or _env_key):
        st.warning("未检测到 API Key：本次将自动使用**离线模式**（缓存 + 规则）。"
                   "如需在线模式，请在左侧填写你自己的 Key，或在本机配置 .env。")
        offline = True
    if go and cloud_mode:
        offline = True           # 云端强制离线
    elif go and visitor.get("key"):
        offline = False          # 用访客自己的 Key，走在线模式
    if go:
        if public_mode and not visitor.get("key"):
            offline = True
            cap = 40
            try:
                import yaml as _y
                _cfg = _y.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
                cap = int((_cfg.get("ui") or {}).get("public_max_per_source", 40))
            except Exception:
                pass
            limit = min(int(limit), cap)

        lock = ROOT / "data" / "runtime" / "collecting.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        if lock.exists():
            age = time.time() - lock.stat().st_mtime
            if age < 900:
                st.warning(f"已有采集任务在运行（{int(age)} 秒前启动），请稍后再试。")
                return
            lock.unlink(missing_ok=True)
        lock.write_text(datetime.now().isoformat(), encoding="utf-8")

        batch = next_batch_no()
        st.info(f"批次 **{batch}**　·　方向「{direction.strip()}」　·　"
                f"{len(sources) or 4} 个来源 × 每源 {limit} 条"
                + ("　·　**离线模式**" if offline else ""))
        bar = st.progress(0.0, text="准备中…")
        status = st.empty()
        with st.expander("运行日志（调试用，可忽略）", expanded=False):
            log = st.empty()
        cmd = [sys.executable, str(ROOT / "scripts" / "new_batch.py"),
               "--direction", direction.strip(), "--limit", str(limit)]
        if keywords.strip():
            cmd += ["--keywords", keywords.strip()]
        if sources:
            cmd += ["--sources", ",".join(sources)]
        if offline:
            cmd += ["--offline"]

        # 持久化记录：谁在什么时候发起了什么方向（便于事后追溯）
        try:
            _log = ROOT / "logs" / "collect_requests.log"
            _log.parent.mkdir(parents=True, exist_ok=True)
            with _log.open("a", encoding="utf-8") as _f:
                _f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t"
                         f"{'public' if public_mode else 'local'}\t"
                         f"{'offline' if offline else 'online'}\t"
                         f"{direction.strip()}\t{direction and ''}\n")
        except Exception:
            pass

        try:
            code, lines = stream(cmd, bar, status, log, offline=offline)
        finally:
            lock.unlink(missing_ok=True)
        if code != 0:
            st.error("运行失败，日志见上")
            return
        slug = next((ln.split("slug=")[-1].strip() for ln in lines if "slug=" in ln), None)
        if not slug:
            slug = list(all_tracks())[-1]
        st.success("完成，结果如下")
        result_block(slug, direction.strip())
        if st.button("⟳ 刷新批次列表并定位到该批次", use_container_width=True):
            st.session_state["view_slug"] = slug
            st.session_state["view_track"] = slug
            st.rerun()

    # ---------- 第二步 ----------
    st.markdown('<div class="section"><em>2</em>　已有批次</div>',
                unsafe_allow_html=True)
    st.caption(f"共 {len(tracks)} 个批次，累计识别 {total_opp} 条机会。"
               f"每次发起需求都会新增一个批次，各批次互不影响。")

    rows = []
    for slug, label in tracks.items():
        s = batch_stats(slug)
        rows.append({"批次": slug, "方向": label, "记录": s["n"],
                     "机会": s["opp"], "主题簇": s["clusters"]})
    st.dataframe(rows, use_container_width=True, hide_index=True)

    pick = st.selectbox("查看某个批次", list(tracks), index=0,
                        format_func=lambda s: f"{tracks[s]}（{s}）")
    if pick:
        result_block(pick, tracks[pick])

    # ---------- 第三步 ----------
    st.markdown('<div class="section"><em>3</em>　系统说明</div>',
                unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["角色与权限", "成本与资源", "部署与运行"])

    with t1:
        st.dataframe(
            pd.DataFrame({
                "角色": ["决策者", "需求发起者", "系统管理员"],
                "发起需求": ["❌", "✅", "✅"],
                "查看批次": ["✅", "✅", "✅"],
                "原始链接": ["❌", "✅", "✅"],
                "导出策划案": ["✅", "✅", "✅"],
                "模型设置": ["❌", "❌", "✅"],
                "标注数据": ["❌", "❌", "✅"],
            }),
            use_container_width=True, hide_index=True, height=170)
        st.caption("数据可见范围：决策者只看聚合结论与策划案；原始记录链接仅需求发起者与管理员；"
                   "标注集与密钥仅系统管理员。公网 / 云端访问自动降为决策者。")

    with t2:
        try:
            cost = (ROOT / "reports" / "成本与资源.md").read_text(encoding="utf-8")
            bullets = [ln.strip()[2:].strip() for ln in cost.splitlines()
                       if ln.strip().startswith("- ")]
            keep = [b for b in bullets if b][:6]
            st.markdown("\n".join(f"- {b}" for b in keep) if keep
                        else "详见 reports/成本与资源.md")
        except Exception:
            st.info("详见 reports/成本与资源.md")
        st.caption("成本控制：全量缓存复用（重跑零成本）、离线模式（`--offline`）"
                   "不产生 API 费用、判别合并为一次调用。")

    with t3:
        st.dataframe(
            pd.DataFrame({
                "部署方式": ["本机运行（双击 bat）", "局域网共享",
                             "Cloudflare 临时隧道", "Streamlit Cloud"],
                "成本": ["0", "0", "0", "0"],
                "需要本机开机": ["是", "是", "是", "否"],
                "适用场景": ["开发与答辩演示", "队内多人查看",
                             "评委临时查看", "长期只读展示"],
            }),
            use_container_width=True, hide_index=True, height=190)
        st.caption("运行环境：Python 3.10+　·　内存 400~600 MB　·　磁盘约 200 MB")

    st.divider()
    st.caption("页面入口：首页 / 分析看板 / 问答咨询（左侧导航切换）"
               "　·　在线标注工具：本机 http://localhost:8504（不对外暴露）")



if __name__ == "__main__":
    main()
