# -*- coding: utf-8 -*-
"""系统首页：需求驱动入口（8500）。

设计原则：**第一屏只做一件事——让用户说清要挖什么方向**。
其余参数收进「高级设置」，默认值已经能跑。

联动：
  * 跑完可一键跳转分析看板（8501）与问答咨询（8505），并自动带上批次参数
  * 历史批次可直接回看，支持跳到看板
"""
from __future__ import annotations

import csv
import io
import json
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

# 需求模板：方向 → 默认检索词（点一下即填，也可自己改）
TEMPLATES: list[tuple[str, str]] = [
    ("电商客服与售后", "退货, 售后, 客服, 退款, 评价"),
    ("教育学习与作业批改", "作业批改, 答疑, 错题, 备课"),
    ("医疗在线问诊", "在线问诊, 病历, 分诊, 复诊"),
    ("法律合同审查", "合同审查, 法条检索, 合规, 风险条款"),
    ("招聘简历筛选", "简历筛选, 面试, 人才匹配"),
    ("内容审核与风控", "审核, 违规, 风控, 垃圾内容"),
    ("数据分析与报表", "报表, 取数, 指标, 数据清洗"),
    ("客服质检", "质检, 通话记录, 服务评价"),
    ("代码开发辅助", "代码生成, 调试, 单测, 代码review"),
    ("营销文案生成", "文案, 投放, 素材, 标题"),
]


# ---------------------------------------------------------------------------
def all_tracks() -> dict[str, str]:
    """slug -> 显示名。内置赛道 + data/tracks 下自建的。"""
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


def stream(cmd: list[str], box) -> tuple[int, list[str]]:
    lines: list[str] = []
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
    for line in proc.stdout:            # type: ignore[union-attr]
        lines.append(line.rstrip())
        if len(lines) > 600:
            lines = lines[-600:]
        box.code("\n".join(lines[-22:]), language="text")
    proc.wait()
    return proc.returncode, lines


def top_clusters(slug: str, k: int = 3) -> list[dict]:
    p = OUT_DIR / slug / "result4.csv"
    if not p.exists():
        return []
    with io.open(p, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: int(r["优先级"]))
    return rows[:k]


def result_block(slug: str, label: str) -> None:
    s = batch_stats(slug)
    c1, c2, c3 = st.columns(3)
    c1.metric("入表记录", s["n"])
    c2.metric("机会记录", s["opp"], f"{s['opp']/max(s['n'],1)*100:.1f}%")
    c3.metric("主题簇", s["clusters"])

    top = top_clusters(slug)
    if top:
        st.markdown("**价值最高的方向**")
        for r in top:
            st.markdown(f"- **P{r['优先级']}　{r['主题簇名称']}**　"
                        f"{r['功能类别']} / {r['所属行业']}　"
                        f"价值分 **{r['机会价值分']}**")

    import os
    if os.environ.get("PUBLIC_DEMO"):
        # 公网演示：localhost 链接对访客无效，改为提示
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
    tracks = all_tracks()

    st.title("🎯 AI 应用场景机会评估")
    st.caption("说清要挖什么方向 → 自动采集、判别、聚类、评分，给出可落地的方向排序")

    with st.sidebar:
        st.subheader("🎫 角色与权限")
        auth.role_selector()
        with st.expander("各角色能做什么"):
            auth.panel()

    # ---------- 第一步：需求输入 ----------
    st.markdown("#### 1　你要挖掘哪个方向？")
    cols = st.columns(5)
    for i, (name, kw) in enumerate(TEMPLATES):
        if cols[i % 5].button(name, key=f"tpl{i}", use_container_width=True):
            st.session_state["direction"] = name
            st.session_state["keywords"] = kw

    direction = st.text_input(
        "需求方向", key="direction",
        placeholder="直接输入，或点上面的模板",
        label_visibility="collapsed")

    with st.expander("高级设置（不改也能跑）"):
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
        st.caption("🔒 当前角色为只读：可浏览已有批次结果；发起新需求需分析师或管理员权限。")
    go = allow_collect and st.button("开始采集与分析", type="primary",
                                     disabled=not direction.strip(),
                                     use_container_width=True)

    if go:
        batch = next_batch_no()
        st.info(f"批次 **{batch}**　·　方向「{direction.strip()}」　·　"
                f"{len(sources) or 4} 个来源 × 每源 {limit} 条")
        log = st.empty()
        cmd = [sys.executable, str(ROOT / "scripts" / "new_batch.py"),
               "--direction", direction.strip(), "--limit", str(limit)]
        if keywords.strip():
            cmd += ["--keywords", keywords.strip()]
        if sources:
            cmd += ["--sources", ",".join(sources)]
        if offline:
            cmd += ["--offline"]

        code, lines = stream(cmd, log)
        if code != 0:
            st.error("运行失败，日志见上")
            return
        slug = next((ln.split("slug=")[-1].strip() for ln in lines if "slug=" in ln), None)
        if not slug:
            slug = list(all_tracks())[-1]
        st.success("完成，结果如下")
        result_block(slug, direction.strip())

    # ---------- 第二步：历史批次 ----------
    st.divider()
    st.markdown("#### 2　已有批次")
    total_opp = sum(batch_stats(s)["opp"] for s in tracks)
    st.caption(f"共 {len(tracks)} 个批次，累计识别 {total_opp} 条机会。"
               f"每次发起需求都会新增一个批次，各批次互不影响。")

    rows = [{"批次": slug, "方向": label,
             **{k: v for k, v in batch_stats(slug).items()
                if k in ("n", "opp", "clusters")}}
            for slug, label in tracks.items()]
    st.dataframe(
        [{"批次": r["批次"], "方向": r["方向"], "记录": r["n"],
          "机会": r["opp"], "主题簇": r["clusters"]} for r in rows],
        use_container_width=True, hide_index=True)

    pick = st.selectbox("查看某个批次", list(tracks), index=0,
                        format_func=lambda s: f"{tracks[s]}（{s}）")
    if pick:
        result_block(pick, tracks[pick])

    # ---------- 第三步：系统说明 ----------
    st.divider()
    st.markdown("#### 3　系统说明")
    t1, t2, t3 = st.tabs(["角色与权限", "成本与资源", "部署与运行"])

    with t1:
        auth.panel()
        st.caption("实现：`ui/auth.py`；公网部署时强制为访客只读，不可切换。")

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
