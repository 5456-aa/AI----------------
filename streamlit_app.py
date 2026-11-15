# -*- coding: utf-8 -*-
"""Streamlit Community Cloud 默认入口。

本项目的界面在 ui/ 下，且 ui/*.py 之间用「同目录模块」方式互相引用
（例如 `import auth`、`from _init import page_config`）。
本地运行时 `streamlit run ui/home.py` 会把 ui/ 加入 sys.path，云端跑本文件时不会，
所以这里显式把 ui/ 也加进去，两种入口行为一致。

用法：
  * Main file path 留默认            → 走这个文件
  * Main file path 填 ui/home.py     → 直接跑首页
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"

# 顺序很重要：ui/ 放最前，保证 `import auth` / `from _init import ...` 能解析
for p in (str(ROOT), str(UI)):
    if p not in sys.path:
        sys.path.insert(0, p)

runpy.run_path(str(UI / "home.py"), run_name="__main__")
