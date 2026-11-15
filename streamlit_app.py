# -*- coding: utf-8 -*-
"""Streamlit Community Cloud 默认入口。

界面的真正入口是 ui/main.py —— 它用 st.navigation 注册了三个页面
（首页 / 分析看板 / 问答咨询），页面之间可以用 st.switch_page 互相跳转。

若直接跑 ui/home.py，switch_page("app.py") 会报
StreamlitPageNotFoundError（页面未注册），所以这里必须走 main.py。

两种部署方式都成立：
  * Main file path 留默认            → 走这个文件 → ui/main.py
  * Main file path 填 ui/main.py     → 同样效果
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"

# ui/ 必须在 sys.path 里：ui/*.py 之间用同目录模块方式互相引用（import auth 等）
for p in (str(ROOT), str(UI)):
    if p not in sys.path:
        sys.path.insert(0, p)

runpy.run_path(str(UI / "main.py"), run_name="__main__")
