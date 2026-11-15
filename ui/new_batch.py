# -*- coding: utf-8 -*-
"""发起新需求（新批次）—— 网页入口。

对应赛题：「用户可多次发起需求，发起一次需求则触发一次采集，即为一个批次，
各批次分析相互独立」。填写方向 → 后台采集 → 自动跑完整链路 → 出四个 CSV。

启动：双击「发起新需求.bat」，或 streamlit run ui/new_batch.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config  # noqa: E402
from collectors.registry import ENABLED_SOURCES, SOURCE_STATUS  # noqa: E402

st.set_page_config(page_title="发起新需求", page_icon="🚀", layout="centered")


def main() -> None:
    cfg = load_config(track="all")
    known = [k for k in (cfg.get("tracks") or {})]

    st.title("🚀 发起新需求")
    st.caption("一次需求 = 一个批次；各批次结果相互独立，互不影响已有的电商/教育批次。")

    c1, c2 = st.columns([2, 3])
    with c1:
        direction = st.text_input("需求方向（必填）", placeholder="例：医疗在线问诊")
    with c2:
        keywords_raw = st.text_input(
            "检索词（可选，逗号分隔）",
            placeholder="在线问诊, 病历结构化, 分诊（留空则按方向自动扩展）")

    c3, c4 = st.columns(2)
    with c3:
        sources = st.multiselect(
            "采集来源", ENABLED_SOURCES,
            default=["GitHub", "掘金", "Stack Overflow", "博客园"])
    with c4:
        limit = st.slider("每源最多采集条数", 20, 200, 100, step=20)

    with st.expander("哪些源不可用？（论文「数据来源」要写）"):
        for name, why in SOURCE_STATUS.items():
            st.caption(f"- **{name}**：{why}")

    st.divider()
    go = st.button("开始采集与分析", type="primary", use_container_width=True,
                   disabled=not direction.strip())

    if not go:
        if known:
            st.info(f"已有批次：{'、'.join(known)}")
        return

    cmd = [sys.executable, str(ROOT / "scripts" / "new_batch.py"),
           "--direction", direction.strip(), "--limit", str(limit)]
    if keywords_raw.strip():
        cmd += ["--keywords", keywords_raw.strip()]
    if sources:
        cmd += ["--sources", ",".join(sources)]

    st.markdown("**运行日志**（采集较慢，请勿关闭页面）")
    log_box = st.empty()
    lines: list[str] = []

    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
    for line in proc.stdout:            # type: ignore[union-attr]
        lines.append(line.rstrip())
        if len(lines) > 400:
            lines = lines[-400:]
        log_box.code("\n".join(lines[-40:]), language="text")
    proc.wait()

    if proc.returncode == 0:
        st.success("完成！")
        slug = None
        for ln in lines:
            if "赛道标识：" in ln:
                slug = ln.split("：", 1)[1].strip()
        if slug:
            out = Path(load_config(track=slug)["paths"]["out"])
            rows = sorted(out.glob("*.csv"))
            st.markdown(f"**本批次结果目录**：`{out}`")
            for f in rows:
                st.caption(f"- {f.name}（{sum(1 for _ in f.open(encoding='utf-8-sig')) - 1} 行）")
            st.info("去主界面「启动界面.bat」，左侧赛道选择里就能看到这个新批次。")
    else:
        st.error(f"失败（退出码 {proc.returncode}），把上面的日志发给我。")


if __name__ == "__main__":
    main()
