# -*- coding: utf-8 -*-
"""在线标注（多人版）：每人选自己的名字，各存各的文件，互不覆盖。

启动：双击「在线标注.bat」，或 streamlit run ui/label_multi.py
队友在同一局域网打开 http://<你的IP>:8504 即可。

数据：
  题目 —— data/label/iaa_items.json + label_set.csv（同一批 40 条，所有人一致）
  作答 —— data/label/by_person/<姓名>.csv（按人名分目录，安全并发）
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LABEL_DIR = ROOT / "data" / "label"
ITEMS_PATH = LABEL_DIR / "iaa_items.json"
BASE_CSV = LABEL_DIR / "label_set.csv"
PEOPLE_DIR = LABEL_DIR / "by_person"

st.set_page_config(page_title="在线标注", page_icon="🏷️", layout="centered")


def load_items() -> list[dict]:
    import json
    if not ITEMS_PATH.exists():
        return []
    ids = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    base = {}
    if BASE_CSV.exists():
        with open(BASE_CSV, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                base[r["记录编号"]] = r
    return [base[i] for i in ids if i in base]


def person_file(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in "-_")
    return PEOPLE_DIR / f"{safe or 'anonymous'}.csv"


def load_answers(name: str) -> dict[str, str]:
    p = person_file(name)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        return {r["记录编号"]: r["label"] for r in csv.DictReader(f)
                if (r.get("label") or "").strip() in ("0", "1")}


def save_answer(name: str, rid: str, label: str, all_items: list[dict]) -> None:
    """只重写这个人的文件，别人不受影响。"""
    answers = load_answers(name)
    answers[rid] = label
    PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    p = person_file(name)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["记录编号", "来源", "标题", "label", "时间"])
        for it in all_items:
            i = it["记录编号"]
            if i in answers:
                w.writerow([i, it["来源"], it["标题"], answers[i],
                            datetime.now().strftime("%Y-%m-%d %H:%M")])


def main() -> None:
    items = load_items()
    if not items:
        st.error("没有标注题目。先运行：`python scripts/make_iaa_sample.py --who B`")
        return

    st.title("🏷️ 在线标注")
    st.caption(f"共 {len(items)} 条，判断每条是否构成「AI 应用机会」。约 15 分钟。")

    # 用表单 + 按钮：手机上不用按回车，点一下按钮就行
    if "who" not in st.session_state:
        st.session_state.who = ""

    if not st.session_state.who:
        with st.form("who_form"):
            typed = st.text_input("你的名字（用于分开保存，填拼音或姓名都行）",
                                  placeholder="例如：zhangsan")
            if st.form_submit_button("开始标注", type="primary",
                                     use_container_width=True):
                if typed.strip():
                    st.session_state.who = typed.strip()
                    st.rerun()
                else:
                    st.warning("名字不能为空")
        with st.expander("判定标准（点开看）"):
            st.markdown(STANDARD)
        return

    name = st.session_state.who
    c_who, c_switch = st.columns([3, 1])
    c_who.caption(f"当前标注人：**{name}**")
    if c_switch.button("换人", use_container_width=True):
        st.session_state.who = ""
        st.rerun()

    answers = load_answers(name.strip())
    done = len(answers)
    st.progress(done / len(items), text=f"{name}：已标 {done} / {len(items)} 条")

    idx = next((i for i, it in enumerate(items) if it["记录编号"] not in answers), None)
    if idx is None:
        pos = sum(1 for v in answers.values() if v == "1")
        st.success(f"{name} 全部标完：{len(items)} 条（机会 {pos} / 非机会 {len(items) - pos}）")
        st.info("告诉队长已完成即可，他会统一计算一致性。")
        return

    it = items[idx]
    st.caption(f"第 {idx + 1} / {len(items)} 条　·　来源 {it['来源']}")
    st.subheader(it["标题"] or "（无标题）")
    st.write(it["正文"][:900])

    with st.expander("判定标准（不确定时展开）"):
        st.markdown(STANDARD)

    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("✅ 是机会 (1)", type="primary", use_container_width=True):
        save_answer(name.strip(), it["记录编号"], "1", items)
        st.rerun()
    if c2.button("❌ 非机会 (0)", use_container_width=True):
        save_answer(name.strip(), it["记录编号"], "0", items)
        st.rerun()
    if c3.button("↩ 撤销上一条", use_container_width=True):
        prev = [i for i, x in enumerate(items) if x["记录编号"] in answers and i < idx]
        if prev:
            rid = items[prev[-1]]["记录编号"]
            answers.pop(rid, None)
            p = person_file(name.strip())
            PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["记录编号", "来源", "标题", "label", "时间"])
                for x in items:
                    if x["记录编号"] in answers:
                        w.writerow([x["记录编号"], x["来源"], x["标题"],
                                    answers[x["记录编号"]],
                                    datetime.now().strftime("%Y-%m-%d %H:%M")])
            st.rerun()

    st.caption("每次点击立即保存到 `data/label/by_person/<你的名字>.csv`，关掉页面不丢进度。")


STANDARD = """
**四条同时满足才算「机会」**

1. **有真实需求**：具体的人在表达具体困难/求助/期望（"有没有工具…""求推荐""怎么才能…"）。
   纯陈述事实、转述观点不算。
2. **AI 是核心**：必须靠语义理解、生成、识别、预测才能解决；普通信息化/加人力能做的，不算。
3. **可落地**：现有技术能做，不需要自研基础模型、海量标注、专用硬件。
4. **排除**：纯资讯、广告、教程、招聘、政策公告、无诉求吐槽 → 一律 0。

**一句话**：作者在"分享/说明/记录" → 0；用户在"抱怨/求助/想要" → 1。
"""


if __name__ == "__main__":
    main()
