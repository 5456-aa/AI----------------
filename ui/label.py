# -*- coding: utf-8 -*-
"""人工标注工具（Streamlit）：点一下存一次，CSV 与 Excel 双向同步。

启动：双击「标注工具.bat」，或 streamlit run ui/label.py
数据：data/label/label_set.csv  +  data/label/人工标注表.xlsx
存盘：每次点击立即写 CSV，并同步更新 Excel 的 label 列（Excel 被占用时自动跳过）
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CSV_PATH = ROOT / "data" / "label" / "label_set.csv"
XLSX_PATH = ROOT / "data" / "label" / "人工标注表.xlsx"
SHEET = "标注表"

st.set_page_config(page_title="机会标注工具", page_icon="🏷️", layout="centered")


# ---------------------------------------------------------------------------
# Excel 读写（容错：文件被 Excel 打开时只写 CSV）
# ---------------------------------------------------------------------------
def read_xlsx_labels() -> dict[str, str]:
    if not XLSX_PATH.exists():
        return {}
    try:
        from openpyxl import load_workbook
        wb = load_workbook(XLSX_PATH, data_only=True)
        ws = wb[SHEET] if SHEET in wb.sheetnames else wb.active
        header = [str(c.value or "").strip() for c in ws[1]]
        i_id, i_lab = header.index("记录编号"), header.index("label")
        out = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            rid = "" if row[i_id] is None else str(row[i_id]).strip()
            lab = "" if row[i_lab] is None else str(row[i_lab]).strip()
            if rid and lab in ("0", "1", "0.0", "1.0"):
                out[rid] = str(int(float(lab)))
        return out
    except Exception:
        return {}


def write_xlsx_labels(rows: list[dict]) -> str:
    """把 label 写回 Excel；返回状态说明。"""
    if not XLSX_PATH.exists():
        return "未找到 Excel，仅写 CSV"
    try:
        from openpyxl import load_workbook
        wb = load_workbook(XLSX_PATH)
        ws = wb[SHEET] if SHEET in wb.sheetnames else wb.active
        header = [str(c.value or "").strip() for c in ws[1]]
        i_id, i_lab = header.index("记录编号"), header.index("label")

        mapping = {r["记录编号"]: r["label"].strip() for r in rows}
        n = 0
        for row in ws.iter_rows(min_row=2):
            rid = "" if row[i_id].value is None else str(row[i_id].value).strip()
            if rid in mapping:
                val = mapping[rid]
                row[i_lab].value = int(val) if val in ("0", "1") else None
                n += 1
        wb.save(XLSX_PATH)
        return f"已同步 Excel（{n} 行）"
    except PermissionError:
        return "Excel 正被占用（请先关闭），本次只写了 CSV"
    except Exception as exc:
        return f"Excel 同步失败：{exc}（CSV 已保存）"


# ---------------------------------------------------------------------------
# CSV 读写
# ---------------------------------------------------------------------------
def load_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # Excel 里填的优先（方便有的人用 Excel 标，有的人用这个页面）
    xl = read_xlsx_labels()
    for r in rows:
        if xl.get(r["记录编号"]):
            r["label"] = xl[r["记录编号"]]
    return rows


def save_rows(rows: list[dict]) -> str:
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return write_xlsx_labels(rows)


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
def main() -> None:
    if "rows" not in st.session_state:
        st.session_state.rows = load_rows()
    rows = st.session_state.rows

    if not rows:
        st.error("没有标注集。先运行：`python scripts/make_label_set.py --n 120`")
        return

    flash = st.session_state.pop("flash", None)
    done = [r for r in rows if r["label"].strip() in ("0", "1")]
    pos = sum(1 for r in rows if r["label"].strip() == "1")

    st.title("🏷️ 机会标注工具")
    if flash:
        st.caption(f"💾 {flash}")
    st.progress(len(done) / len(rows), text=f"已标 {len(done)} / {len(rows)} 条"
                                           f"（机会 {pos}，非机会 {len(done) - pos}）")

    top = st.columns([1, 1, 2])
    if top[0].button("⟳ 从 Excel 重新载入", use_container_width=True):
        st.session_state.rows = load_rows()
        st.rerun()
    if top[1].button("💾 立即保存", use_container_width=True):
        st.session_state.flash = save_rows(rows)
        st.rerun()
    top[2].caption(f"每次点击自动保存 · 最近保存 {datetime.now():%H:%M:%S}")

    idx = next((i for i, r in enumerate(rows) if r["label"].strip() not in ("0", "1")), None)
    if idx is None:
        st.success(f"全部标完了！共 {len(rows)} 条（机会 {pos} / 非机会 {len(rows) - pos}）")
        st.info("下一步运行：`python scripts/tune_threshold.py --tune data/label/人工标注表.xlsx`")
        return

    r = rows[idx]
    st.caption(f"第 {idx + 1} / {len(rows)} 条　·　来源 {r['来源']}　·　"
               f"模型参考：{'机会' if r['模型判断'] == '1' else '非机会'}（{r['模型置信度']}）")

    st.subheader(r["标题"] or "（无标题）")
    st.write(r["正文"][:900])
    st.caption(f"发布时间 {r['发布时间']}　·　记录编号 {r['记录编号']}")

    with st.expander("判定标准（不确定时展开）"):
        st.markdown("""
**四条同时满足才是「机会」**
1. **有真实需求**：具体的人在求助/吐槽/期望，纯陈述事实不算
2. **AI 是核心**：必须靠语义理解/生成/识别/预测才能解决，普通信息化不算
3. **可落地**：现有技术能做，不需要自研模型/海量标注/专用硬件
4. **排除**：纯资讯、广告、教程、招聘、政策公告、无诉求吐槽 → 一律非机会
""")

    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("✅ 是机会 (1)", use_container_width=True, type="primary"):
        rows[idx]["label"] = "1"
        st.session_state.flash = save_rows(rows)
        st.rerun()
    if c2.button("❌ 非机会 (0)", use_container_width=True):
        rows[idx]["label"] = "0"
        st.session_state.flash = save_rows(rows)
        st.rerun()
    if c3.button("⏭ 跳过", use_container_width=True):
        rows[idx]["备注"] = "跳过"
        save_rows(rows)
        st.rerun()

    st.divider()
    b1, b2 = st.columns(2)
    if b1.button("↩ 撤销上一条"):
        prev = [i for i, x in enumerate(rows) if i < idx and x["label"].strip() in ("0", "1")]
        if prev:
            rows[prev[-1]]["label"] = ""
            save_rows(rows)
            st.rerun()
    if b2.button("🔄 重新载入"):
        st.session_state.rows = load_rows()
        st.rerun()

    st.caption("每次点击立即写入 CSV 并同步 Excel。Excel 正被打开时只写 CSV，"
               "关掉 Excel 后点「立即保存」即可补齐。")


if __name__ == "__main__":
    main()
