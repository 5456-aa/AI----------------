# -*- coding: utf-8 -*-
"""页面初始化小工具：让页面既能被 main.py 统一调度，也能单独运行。

st.set_page_config 一次运行只能调用一次。多页应用里由入口统一设置，
页面脚本再调用会抛异常——这里包一层 try/except，两种运行方式都兼容。
"""
from __future__ import annotations

import streamlit as st


def page_config(title: str, icon: str = "🎯", layout: str = "wide") -> None:
    try:
        st.set_page_config(page_title=title, page_icon=icon, layout=layout)
    except Exception:
        # 已由入口设置过，忽略即可
        pass
