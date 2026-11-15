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
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402
from collectors.registry import ENABLED_SOURCES, SOURCE_STATUS  # noqa: E402
from io_utils import load_config  # noqa: E402

st.set_page_config(page_title="AI 机会评估系统", page_icon="🎯", layout="wide")

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


def stream(cmd: list[str], bar, status, log_box) -> tuple[int, list[str]]:
    """只显示阶段与进度；原始日志收进折叠区（不刷屏）。"""
    lines: list[str] = []
    done: set[str] = set()
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
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

    top = top_clusters(slug)
    if top:
        st.markdown('<div class="card-title">🏆 价值最高的方向</div>',
                    unsafe_allow_html=True)
        for r in top:
            st.markdown(
                f"**P{r['优先级']}　{r['主题簇名称']}**　"
                f"<span style='color:#64748b'>{r['功能类别']} / {r['所属行业']}</span>　"
                f"价值分 **{r['机会价值分']}**", unsafe_allow_html=True)

    if os.environ.get("PUBLIC_DEMO"):
        st.caption("🔒 公网演示模式：分析看板与问答需单独的公网地址（见运行窗口输出），"
                   "本页已展示该批次的核心结论。")
        return

    a, b = st.columns(2)
    a.link_button("📊 打开分析看板", f"{DASHBOARD}/?track={slug}",
                  use_container_width=True)
    b.link_button("💬 就这批结果提问", QA, use_container_width=True)
    st.caption("看板会自动切到该批次；若打不开，先双击对应的 .bat 启动服务。")


# ---------------------------------------------------------------------------
def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
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
        with st.popover("哪些源不可用？"):
            for name, why in SOURCE_STATUS.items():
                st.caption(f"- **{name}**：{why}")

    allow_collect = auth.can("collect")
    if not allow_collect:
        st.caption("🔒 当前角色为只读：可浏览已有批次结果；发起新需求需"
                   "「需求发起者」或「系统管理员」权限。")

    go = allow_collect and st.button("开始采集与分析", type="primary",
                                     disabled=not direction.strip(),
                                     use_container_width=True)

    if go:
        batch = next_batch_no()
        st.info(f"批次 **{batch}**　·　方向「{direction.strip()}」　·　"
                f"{len(sources) or 4} 个来源 × 每源 {limit} 条")
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

        code, lines = stream(cmd, bar, status, log)
        if code != 0:
            st.error("运行失败，日志见上")
            return
        slug = next((ln.split("slug=")[-1].strip() for ln in lines if "slug=" in ln), None)
        if not slug:
            slug = list(all_tracks())[-1]
        st.success("完成，结果如下")
        result_block(slug, direction.strip())

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
        auth.panel()
        st.caption("实现：`ui/auth.py`；公网部署时强制为决策者只读，不可切换。")
    with t2:
        try:
            cost = (ROOT / "reports" / "成本与资源.md").read_text(encoding="utf-8")
            head = [ln for ln in cost.splitlines() if ln.startswith("- ")][:6]
            st.markdown("\n".join(head) if head else "详见 reports/成本与资源.md")
        except Exception:
            st.caption("详见 reports/成本与资源.md")
        st.caption("成本控制：全量缓存复用、离线模式零费用复现、判别合并为一次调用。")
    with t3:
        st.markdown("""
| 方式 | 成本 | 适用 |
|---|---|---|
| 本机双击 bat | 0 | 开发与答辩演示 |
| 局域网 `http://本机IP:8500` | 0 | 队内多人查看 |
| Cloudflare 临时隧道 | 0 | 评委临时查看 |
| Streamlit Cloud | 0 | 长期只读展示 |

运行环境：Python 3.10+｜内存 400~600 MB｜磁盘约 200 MB。
""")

    st.caption(f"其它入口：分析看板 {DASHBOARD}　·　问答咨询 {QA}　·　"
               f"在线标注 http://localhost:8504")


if __name__ == "__main__":
    main()
