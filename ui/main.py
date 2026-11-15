# -*- coding: utf-8 -*-
"""系统入口：单应用多页（Streamlit Navigation）。

一个进程、一个端口、一个公网地址，页面之间用侧栏切换——
不再需要 8500/8501/8505 三个端口。

启动：双击「启动系统.bat」，或
  streamlit run ui/main.py --server.port 8500
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="AI 应用场景机会评估系统", page_icon="🎯", layout="wide")

pages = [
    st.Page("home.py", title="首页", icon="🏠", default=True),
    st.Page("app.py", title="分析看板", icon="📊"),
    st.Page("qa.py", title="问答咨询", icon="💬"),
]

st.navigation(pages).run()
