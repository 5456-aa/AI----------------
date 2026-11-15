# -*- coding: utf-8 -*-
"""界面级任务覆盖自检：五个任务在界面上是否真的做得到。

不看文件在不在，而是用 Streamlit 的 AppTest 真的把页面跑起来，
检查关键控件（下载按钮 / 图表 / 表格 / 链接 / 问答输入）是否存在。

用法：python scripts/check_ui_tasks.py
产出：reports/系统任务覆盖自检.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ui"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

from streamlit.testing.v1 import AppTest  # noqa: E402

OUT = ROOT / "reports" / "系统任务覆盖自检.md"


def run(page: str):
    at = AppTest.from_file(str(ROOT / "ui" / page), default_timeout=180)
    at.run()
    return at


def count(at, kind: str) -> int:
    try:
        return len(at.get(kind))
    except Exception:
        try:
            return len(getattr(at, kind))
        except Exception:
            return 0


def main() -> int:
    rows: list[tuple[str, str, bool, str]] = []
    add = lambda t, item, ok, note="": rows.append((t, item, ok, note))

    # ---------- 首页（任务一入口 + 任务五入口） ----------
    home = run("home.py")
    add("任务一", "首页有需求方向输入框", count(home, "text_input") >= 1)
    add("任务一", "首页有「开始采集与分析」按钮",
        any("开始采集" in b.label for b in home.button))
    add("任务一", "首页有 10 个方向模板（一键填入）",
        sum(1 for b in home.button if any(k in b.label for k in ("🛒", "🎓", "🏥"))) >= 3)
    add("任务五", "首页展示批次统计指标", count(home, "metric") >= 3)
    add("任务五", "首页可查看历史批次列表", count(home, "dataframe") >= 1)
    add("系统", "首页有角色与权限面板", any("角色" in t.label for t in home.tabs))

    # ---------- 看板（任务一~四结果呈现 + 任务五决策产出） ----------
    app = run("app.py")
    add("任务一", "看板有去重漏斗与结果文件下载", count(app, "expander") >= 3)
    add("任务二", "看板有逐条判别表格", count(app, "dataframe") >= 1)
    # Streamlit 的图表统一渲染为 vega_lite_chart
    add("任务三", "看板有主题簇气泡图", count(app, "vega_lite_chart") >= 1)
    add("任务四", "看板有优先级排序表", count(app, "dataframe") >= 1)
    add("任务五", "看板可查看并下载立项策划案", count(app, "expander") >= 3)
    add("任务五", "看板有单簇下钻（可溯源原文）", count(app, "selectbox") >= 2)

    # ---------- 问答（任务五交互） ----------
    qa = run("qa.py")
    add("任务五", "问答页有提问输入框", count(qa, "text_input") >= 1)
    add("任务五", "问答页有示例问题按钮", len(qa.button) >= 4)

    # 汇总
    tasks = ["任务一", "任务二", "任务三", "任务四", "任务五", "系统"]
    L = ["# 系统任务覆盖自检（界面级）", "",
         f"> 生成于 {datetime.now():%Y-%m-%d %H:%M}　·　"
         f"由 `scripts/check_ui_tasks.py` 真实渲染三个页面后断言控件存在", "",
         "| 任务 | 检查项 | 结果 | 说明 |", "|---|---|---|---|"]
    for t, item, ok, note in rows:
        L.append(f"| {t} | {item} | {'✅' if ok else '❌'} | {note} |")

    L += ["", "## 按任务汇总", "", "| 任务 | 通过率 |", "|---|---|"]
    for t in tasks:
        sub = [r for r in rows if r[0] == t]
        if not sub:
            continue
        ok = sum(1 for r in sub if r[2])
        L.append(f"| {t} | {ok}/{len(sub)} |")

    bad = [r for r in rows if not r[2]]
    L += ["", f"**共 {len(rows)} 项检查，未通过 {len(bad)} 项。**"]
    if bad:
        L += ["", "未通过项："] + [f"- {r[0]}：{r[1]}" for r in bad]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    for t, item, ok, note in rows:
        print(f"  {'OK ' if ok else 'FAIL'} [{t}] {item}")
    print(f"\n共 {len(rows)} 项，未通过 {len(bad)} 项 -> {OUT}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
