# -*- coding: utf-8 -*-
"""角色与权限：赛题要求「明确用户角色及各角色的操作权限与数据可见范围」。

三种角色（由低到高）：

| 角色 | 能做什么 | 数据可见范围 |
|---|---|---|
| 访客 viewer | 浏览已有批次结果、看图表与问答 | 聚合结果与主题簇；不显示原始链接与标注数据 |
| 分析师 analyst | viewer + 发起新需求（触发采集）、导出策划案 | 全部结果 + 原始记录链接 |
| 管理员 admin | analyst + 模型设置/密钥、标注工具、结果自检 | 全部 + 密钥配置与标注集 |

实现方式：
  * 本机默认为 admin（自己的电脑当然自己说了算）
  * 设置环境变量 `PUBLIC_DEMO=1` 时强制降为 viewer，且不可切换
  * `ROLE=analyst` 可显式指定（用于给队友开一个"只能采集、不能改配置"的入口）
"""
from __future__ import annotations

import os

import streamlit as st

ROLES: dict[str, dict] = {
    "viewer": {
        "label": "访客（只读）",
        "desc": "浏览已有批次的结果、图表与问答，不能发起采集或修改配置",
        "perm": {"view", "export"},
        "see_raw_links": False,
        "see_labels": False,
        "see_settings": False,
    },
    "analyst": {
        "label": "分析师（可采集）",
        "desc": "可发起新需求触发采集、查看全部批次与原始记录链接，不能修改模型配置",
        "perm": {"view", "collect", "export", "view_all", "raw_links"},
        "see_raw_links": True,
        "see_labels": False,
        "see_settings": False,
    },
    "admin": {
        "label": "管理员（完全权限）",
        "desc": "含模型设置与密钥、标注工具、数据自检与导出",
        "perm": {"view", "collect", "export", "view_all", "raw_links",
                 "configure", "label", "audit"},
        "see_raw_links": True,
        "see_labels": True,
        "see_settings": True,
    },
}


def is_public_demo() -> bool:
    return bool(os.environ.get("PUBLIC_DEMO"))


def default_role() -> str:
    if is_public_demo():
        return "viewer"
    return os.environ.get("ROLE", "admin")


def current_role() -> str:
    """当前角色：公网模式固定 viewer；本机可在侧栏切换。"""
    if is_public_demo():
        return "viewer"
    role = st.session_state.get("role") or default_role()
    return role if role in ROLES else "admin"


def can(perm: str) -> bool:
    return perm in ROLES[current_role()]["perm"]


def sees(field: str) -> bool:
    """field: see_raw_links / see_labels / see_settings"""
    return bool(ROLES[current_role()].get(field))


def role_badge() -> None:
    role = current_role()
    r = ROLES[role]
    icon = {"viewer": "👁", "analyst": "🛠", "admin": "🔑"}[role]
    st.caption(f"{icon} 当前角色：**{r['label']}**")
    if is_public_demo():
        st.caption("公网演示模式：权限已锁定为只读")


def role_selector() -> None:
    """侧栏角色切换（公网模式下不显示）。"""
    if is_public_demo():
        role_badge()
        return
    names = list(ROLES)
    cur = current_role()
    idx = names.index(cur) if cur in names else len(names) - 1
    st.session_state["role"] = st.radio(
        "角色", names, index=idx,
        format_func=lambda n: ROLES[n]["label"])
    st.caption(ROLES[current_role()]["desc"])


def panel() -> None:
    """「角色与权限」说明面板（论文/答辩可直接截图）。"""
    st.markdown("""
| 角色 | 发起需求 | 查看批次 | 原始链接 | 导出策划案 | 模型设置 | 标注数据 |
|---|---|---|---|---|---|---|
| 访客 viewer | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| 分析师 analyst | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| 管理员 admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
""")
    st.caption("公网部署时强制为访客只读；本机默认管理员。")
