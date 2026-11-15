# -*- coding: utf-8 -*-
"""页面初始化与统一侧栏：让页面既能被 main.py 调度，也能单独运行。"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

_UI = Path(__file__).resolve().parent


def page_config(title: str, icon: str = "🎯", layout: str = "wide") -> None:
    """st.set_page_config 一次运行只能调用一次，多页时由入口统一设置。"""
    try:
        st.set_page_config(page_title=title, page_icon=icon, layout=layout)
    except Exception:
        pass


def sidebar_nav() -> None:
    """侧栏顶部：系统名 + 三个页面链接。

    用 position="hidden" 隐藏 Streamlit 默认导航，由这里自己画，
    这样品牌名可以出现在导航之上，顺序完全可控。
    """
    with st.sidebar:
        st.markdown(
            "<div style='font-size:22px;font-weight:700;line-height:1.3;"
            "margin:4px 0 2px'>🎯 机会评估系统</div>"
            "<div style='color:#64748b;font-size:12.5px;margin-bottom:10px'>"
            "AI 应用场景的智能挖掘与机会评估</div>",
            unsafe_allow_html=True)
        def _link(fname: str, label: str, icon: str) -> None:
            """注册过页面时画导航链接；单独运行某页时静默跳过（避免报错）。"""
            try:
                st.page_link(str(_UI / fname), label=label, icon=icon)
            except Exception:
                pass

        _link("home.py", "首页", "🏠")
        _link("app.py", "分析看板", "📊")
        _link("qa.py", "问答咨询", "💬")
        st.divider()
