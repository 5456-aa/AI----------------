# -*- coding: utf-8 -*-
"""系统入口：单应用多页（Streamlit Navigation）。

侧栏导航由 ui/_init.py 的 sidebar_nav() 统一绘制，
这样「机会评估系统」标题可以出现在导航之上。页面之间用 st.switch_page 跳转。
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
UI = Path(__file__).resolve().parent
for p in (str(ROOT), str(UI)):
    if p not in sys.path:
        sys.path.insert(0, p)

st.set_page_config(page_title="AI 应用场景机会评估系统", page_icon="🎯",
                   layout="wide", initial_sidebar_state="expanded")

pages = [
    st.Page(str(UI / "home.py"), title="首页", icon="🏠", default=True),
    st.Page(str(UI / "app.py"), title="分析看板", icon="📊"),
    st.Page(str(UI / "qa.py"), title="问答咨询", icon="💬"),
]

# hidden：不用默认导航，改由 sidebar_nav() 绘制，位置更自由
st.navigation(pages, position="hidden").run()
