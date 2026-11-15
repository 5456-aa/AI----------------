# -*- coding: utf-8 -*-
"""Streamlit Community Cloud 默认入口。

Streamlit Cloud 默认查找仓库根目录的 streamlit_app.py，
而本项目的界面在 ui/ 下，这里做一个薄封装，两种入口都可用：
  * Main file path 留空/默认  → 走这个文件
  * Main file path 填 ui/home.py → 直接跑首页
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

runpy.run_path(str(ROOT / "ui" / "home.py"), run_name="__main__")
