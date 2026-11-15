# -*- coding: utf-8 -*-
"""角色与权限：对齐赛题「明确用户角色（如需求发起者、决策者等）及各角色的操作权限与数据可见范围」。

三种角色：

| 角色 | 对应赛题 | 能做什么 | 数据可见范围 |
|---|---|---|---|
| 决策者 decider | 决策者 | 查看批次结论、主题簇排序、导出策划案 | 聚合结果与策划案；不含原始链接与标注集 |
| 需求发起者 requester | 需求发起者 | 发起需求触发采集、查看全部批次、打开原始链接、导出策划案 | 结果 + 原始链接；不含标注集与密钥 |
| 系统管理员 admin | （运维角色） | 上述全部 + 模型设置与密钥、标注工具、结果自检 | 全部 |

实现：
  * 本机默认「系统管理员」（自己的电脑自己说了算）
  * `PUBLIC_DEMO=1` 时强制为「决策者」只读，不可切换
  * `ROLE=requester|decider|admin` 可显式指定（如给队友开"只能采集、不能改配置"的入口）
"""
from __future__ import annotations

import os

import streamlit as st

ROLES: dict[str, dict] = {
    "decider": {
        "label": "决策者（只读）",
        "role_name": "决策者",
        "desc": "查看各批次结论、主题簇排序与立项策划案；不能发起采集，看不到原始链接",
        "perm": {"view", "export"},
        "see_raw_links": False,
        "see_labels": False,
        "see_settings": False,
    },
    "requester": {
        "label": "需求发起者（可采集）",
        "role_name": "需求发起者",
        "desc": "发起新需求触发采集，查看全部批次与原始记录链接；不能修改模型配置",
        "perm": {"view", "collect", "export", "view_all", "raw_links"},
        "see_raw_links": True,
        "see_labels": False,
        "see_settings": False,
    },
    "admin": {
        "label": "系统管理员（完全权限）",
        "role_name": "系统管理员",
        "desc": "含模型设置与密钥、标注工具、结果自检与数据导出",
        "perm": {"view", "collect", "export", "view_all", "raw_links",
                 "configure", "label", "audit"},
        "see_raw_links": True,
        "see_labels": True,
        "see_settings": True,
    },
}

# 兼容旧名称（早期版本用过 viewer / analyst）
_ALIAS = {"viewer": "decider", "analyst": "requester"}


LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def request_host() -> str:
    """取本次请求的 Host（去掉端口）。取不到时视为本机。"""
    try:
        h = (st.context.headers.get("Host") or "").strip().lower()
    except Exception:
        return "localhost"
    return h.split(":")[0] if h else "localhost"


def is_public_request() -> bool:
    """公网隧道（如 *.trycloudflare.com）来的请求 → 只读。

    本机（localhost / 127.0.0.1 / 局域网 IP）视为可信，可用管理模式。
    """
    if os.environ.get("PUBLIC_DEMO"):
        return True
    host = request_host()
    if host in LOCAL_HOSTS:
        return False
    # 局域网私网地址也允许（10.x / 192.168.x / 172.16~31.x）
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        if a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31):
            return False
    return True


def is_public_demo() -> bool:
    """兼容旧接口：等价于「当前请求只读」。"""
    return is_public_request()


def default_role() -> str:
    role = os.environ.get("ROLE", "admin")
    role = _ALIAS.get(role, role)
    if is_public_request():
        return "decider"
    return role


def current_role() -> str:
    """当前角色：公网固定「决策者」；本机可用管理开关或侧栏切换。"""
    if is_public_request():
        return "decider"
    if "role" not in st.session_state:
        st.session_state["role"] = default_role()
    role = st.session_state["role"]
    return role if role in ROLES else "admin"


def mode_switcher() -> None:
    """本机专用：管理模式开关（公网访客看不到）。"""
    if is_public_request():
        return
    managing = current_role() == "admin"
    new = st.toggle("🔓 管理模式（仅本机可见）", value=managing,
                    help="关闭后与公网访客一致：只能浏览，不能采集或改配置")
    want = "admin" if new else "decider"
    if want != current_role():
        st.session_state["role"] = want
        st.rerun()


def can(perm: str) -> bool:
    return perm in ROLES[current_role()]["perm"]


def sees(field: str) -> bool:
    """field: see_raw_links / see_labels / see_settings"""
    return bool(ROLES[current_role()].get(field))


def role_badge() -> None:
    role = current_role()
    r = ROLES[role]
    icon = {"decider": "👁", "requester": "🛠", "admin": "🔑"}[role]
    st.caption(f"{icon} 当前角色：**{r['label']}**")
    if is_public_demo():
        st.caption("公网演示模式：权限已锁定为决策者（只读）")


def role_selector() -> None:
    """侧栏角色切换（公网模式下不显示）。"""
    if is_public_demo():
        role_badge()
        return
    names = list(ROLES)
    cur = current_role()
    idx = names.index(cur) if cur in names else len(names) - 1
    st.session_state["role"] = st.radio(
        "角色", names, index=idx, label_visibility="collapsed",
        format_func=lambda n: ROLES[n]["role_name"])
    st.caption(ROLES[current_role()]["desc"])


PERM_LABELS = [
    ("collect", "发起需求"),
    ("view_all", "查看批次"),
    ("raw_links", "原始链接"),
    ("export", "导出策划案"),
    ("configure", "模型设置"),
    ("label", "标注数据"),
]


def panel_compact() -> None:
    """侧栏：当前角色的权限用彩色小胶囊表示，窄栏也不会挤成竖排。"""
    role = current_role()
    perm = ROLES[role]["perm"]
    chips = []
    for key, label in PERM_LABELS:
        ok = key in perm
        bg, fg, mark = (("#ecfdf5", "#047857", "✓") if ok
                        else ("#fef2f2", "#b91c1c", "✕"))
        chips.append(
            f"<span style='display:inline-block;background:{bg};color:{fg};"
            f"border-radius:999px;padding:3px 10px;font-size:11.5px;"
            f"margin:0 6px 6px 0'>{mark} {label}</span>")
    st.markdown("".join(chips), unsafe_allow_html=True)
    if ROLES[role]["see_raw_links"]:
        st.caption("可见原始记录链接")
    else:
        st.caption("仅见聚合结论与策划案")


def panel() -> None:
    """「角色与权限」说明面板（论文/答辩可直接截图）。"""
    st.markdown("""
| 角色 | 发起需求 | 查看批次 | 原始链接 | 导出策划案 | 模型设置 | 标注数据 |
|---|---|---|---|---|---|---|
| 决策者 | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| 需求发起者 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| 系统管理员 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
""")
    st.caption("数据可见范围：决策者只看聚合结论与策划案；原始记录链接仅需求发起者与管理员；"
               "标注集与密钥仅管理员。公网部署时强制为决策者只读。")
