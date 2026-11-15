# -*- coding: utf-8 -*-
"""把结果导出成单文件 HTML 可视化报告（双击即开，无需 Python / 服务器）。

产物：reports/系统可视化报告.html
  * 所有图片以 base64 内嵌，文件可单独发送；
  * 主题簇表格可点表头排序；
  * 每个簇可展开看簇内记录，并带原文链接；
  * 打印友好（Ctrl+P 可直接出 PDF）。

用法：python scripts/make_html_report.py
"""
from __future__ import annotations

import base64
import csv
import html
import io
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402

OUT = ROOT / "reports" / "系统可视化报告.html"


def load_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with io.open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def img_b64(p: Path) -> str:
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def esc(x) -> str:
    return html.escape(str(x or ""))


CSS = """
:root{--bg:#f7f8fa;--card:#fff;--ink:#1f2328;--muted:#656d76;--line:#e5e7eb;
--blue:#2563eb;--green:#16a34a;--orange:#ea580c;--red:#dc2626}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1160px;margin:0 auto;padding:28px 20px 80px}
header{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;
padding:34px 28px;border-radius:14px;margin-bottom:22px}
header h1{margin:0 0 6px;font-size:26px;letter-spacing:.5px}
header .sub{opacity:.88;font-size:13.5px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:20px}
.kpi{background:rgba(255,255,255,.14);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:26px;line-height:1.2}
.kpi span{font-size:12.5px;opacity:.85}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:20px 22px;margin-bottom:18px}
h2{font-size:18px;margin:0 0 14px;padding-left:10px;border-left:4px solid var(--blue)}
h3{font-size:15px;margin:18px 0 8px;color:var(--muted);font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f1f3f6;font-weight:600;position:sticky;top:0;cursor:pointer;user-select:none}
th:hover{background:#e6e9ee}
tr:hover td{background:#fafbfc}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600}
.b1{background:#dcfce7;color:#166534}.b2{background:#dbeafe;color:#1e40af}
.b3{background:#fef3c7;color:#92400e}.b4{background:#f3f4f6;color:#4b5563}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:14px}
.fig{border:1px solid var(--line);border-radius:10px;padding:10px;background:#fff}
.fig img{width:100%;display:block;border-radius:6px}
.fig p{margin:8px 2px 0;font-size:12.5px;color:var(--muted)}
details{border:1px solid var(--line);border-radius:10px;margin:10px 0;overflow:hidden}
summary{padding:12px 14px;cursor:pointer;background:#fafbfc;font-weight:600;font-size:14px}
summary:hover{background:#f1f3f6}
details .inner{padding:4px 14px 14px}
.note{font-size:12.5px;color:var(--muted);margin-top:10px}
.tag{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;color:var(--blue)}
footer{text-align:center;color:var(--muted);font-size:12.5px;padding:24px 0}
@media print{body{background:#fff}section{break-inside:avoid;border:none;padding:0 0 12px}
header{background:#1e3a8a !important;-webkit-print-color-adjust:exact}
details{break-inside:avoid}details[open] summary{background:#fff}}
"""

JS = """
document.querySelectorAll('table.sortable').forEach(function(t){
  t.querySelectorAll('th').forEach(function(th,i){
    th.addEventListener('click',function(){
      var rows=Array.from(t.tBodies[0].rows);
      var asc=th.dataset.asc!=='1'; th.dataset.asc=asc?'1':'0';
      rows.sort(function(a,b){
        var x=a.cells[i].innerText.trim(), y=b.cells[i].innerText.trim();
        var nx=parseFloat(x), ny=parseFloat(y);
        var v=(!isNaN(nx)&&!isNaN(ny))?(nx-ny):x.localeCompare(y,'zh');
        return asc?v:-v;
      });
      rows.forEach(function(r){t.tBodies[0].appendChild(r)});
    });
  });
});
"""


def main() -> int:
    cfg = load_config(track="all")
    clean = Path(cfg["paths"]["clean"])
    out = Path(cfg["paths"]["out"])
    fig_dir = ROOT / "figs" / "all"

    r1, r2 = load_csv(out / "result1.csv"), load_csv(out / "result2.csv")
    r3, r4 = load_csv(out / "result3.csv"), load_csv(out / "result4.csv")
    judged = read_jsonl(clean / "judged.jsonl")
    metrics = read_jsonl(clean / "cluster_metrics.jsonl")
    detail = (read_jsonl(clean / "score_detail.jsonl") or [{}])[0]

    n_all = len(r2)
    n_opp = sum(1 for r in r2 if r.get("是否构成机会") == "1")
    batch = r4[0]["采集批次号"] if r4 else "—"

    # 来源统计
    src: dict[str, dict] = {}
    for r in judged:
        s = r.get("source", "未知")
        d = src.setdefault(s, {"n": 0, "opp": 0})
        d["n"] += 1
        d["opp"] += 1 if r.get("is_opportunity") == 1 else 0

    # 簇 -> 记录
    by_cluster: dict[str, list] = {}
    for r in judged:
        if r.get("is_opportunity") == 1:
            by_cluster.setdefault(r.get("cluster_id", ""), []).append(r)
    # judged 里没有 cluster_id，用 result3 的编号列表反查
    rid2cluster = {}
    for row in r3:
        for rid in (row["簇内机会记录"] or "").split(";"):
            if rid.strip():
                rid2cluster[rid.strip()] = row["主题簇编号"]
    rec_by_id = {r.get("record_id"): r for r in judged}
    cl_records: dict[str, list] = {}
    for rid, cid in rid2cluster.items():
        if rid in rec_by_id:
            cl_records.setdefault(cid, []).append(rec_by_id[rid])

    P = []
    A = P.append
    A("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>")
    A("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    A("<title>AI 应用场景机会评估 · 可视化报告</title>")
    A(f"<style>{CSS}</style></head><body><div class='wrap'>")

    A("<header><h1>AI 应用场景的智能挖掘与机会评估系统</h1>")
    A(f"<div class='sub'>采集批次 {esc(batch)}　·　生成于 {datetime.now():%Y-%m-%d %H:%M}"
      f"　·　双赛道：电商客服与运营 + 教育学习与教学管理</div>")
    A("<div class='kpis'>")
    for label, val in [("入表记录", n_all), ("机会记录", n_opp),
                       ("机会率", f"{n_opp / max(n_all,1)*100:.1f}%"),
                       ("主题簇", len(r4)), ("来源数", len(src))]:
        A(f"<div class='kpi'><b>{val}</b><span>{label}</span></div>")
    A("</div></header>")

    # ---- 数据来源 ----
    A("<section><h2>一、数据来源与机会密度</h2>")
    A("<table class='sortable'><thead><tr><th>来源</th><th class='num'>记录数</th>"
      "<th class='num'>机会数</th><th class='num'>机会率</th></tr></thead><tbody>")
    for s, d in sorted(src.items(), key=lambda kv: -kv[1]["n"]):
        rate = d["opp"] / max(d["n"], 1) * 100
        cls = "b1" if rate > 20 else ("b2" if rate > 5 else "b4")
        A(f"<tr><td>{esc(s)}</td><td class='num'>{d['n']}</td>"
          f"<td class='num'>{d['opp']}</td>"
          f"<td class='num'><span class='badge {cls}'>{rate:.1f}%</span></td></tr>")
    A("</tbody></table>")
    A("<p class='note'>机会几乎全部来自开发者社区与问答社区，资讯类来源机会率接近 0，"
      "印证赛题「排除纯资讯」规则的有效性。</p></section>")

    # ---- 主题簇 ----
    A("<section><h2>二、主题簇排名（按机会价值分）</h2>")
    A("<table class='sortable'><thead><tr><th>优先级</th><th>编号</th><th>主题簇名称</th>"
      "<th>功能类别</th><th>所属行业</th><th class='num'>记录数</th>"
      "<th class='num'>来源数</th><th class='num'>价值分</th></tr></thead><tbody>")
    r3map = {x["主题簇编号"]: x for x in r3}
    for r in sorted(r4, key=lambda x: int(x["优先级"])):
        cid = r["主题簇编号"]
        row3 = r3map.get(cid, {})
        A(f"<tr><td class='num'>P{esc(r['优先级'])}</td><td>{esc(cid)}</td>"
          f"<td>{esc(r['主题簇名称'])}</td><td>{esc(r['功能类别'])}</td>"
          f"<td>{esc(r['所属行业'])}</td>"
          f"<td class='num'>{esc(row3.get('簇内机会记录数',''))}</td>"
          f"<td class='num'>{len((row3.get('来源覆盖') or '').split('、'))}</td>"
          f"<td class='num'><b>{esc(r['机会价值分'])}</b></td></tr>")
    A("</tbody></table>")
    A("<p class='note'>点击表头可排序。价值分 = 多源指向度、记录规模、互动热度、需求强度"
      "四维加权（熵权+AHP）。</p></section>")

    # ---- 簇内记录 ----
    A("<section><h2>三、簇内记录（可溯源到原文）</h2>")
    for r in sorted(r4, key=lambda x: int(x["优先级"])):
        cid = r["主题簇编号"]
        recs = cl_records.get(cid, [])
        A(f"<details><summary>{esc(cid)} · {esc(r['主题簇名称'])}"
          f"（{len(recs)} 条 · {esc(r3map.get(cid,{}).get('来源覆盖',''))}）</summary>")
        A("<div class='inner'><table><thead><tr><th>记录编号</th><th>来源</th>"
          "<th>标题</th><th class='num'>置信度</th></tr></thead><tbody>")
        for rec in recs[:60]:
            url = rec.get("url", "")
            title = esc(rec.get("title") or rec.get("clean_text", "")[:50])
            link = f"<a href='{esc(url)}' target='_blank' rel='noopener'>{title}</a>" if url else title
            A(f"<tr><td class='tag'>{esc(rec.get('record_id'))}</td>"
              f"<td>{esc(rec.get('source'))}</td><td>{link}</td>"
              f"<td class='num'>{float(rec.get('confidence',0)):.3f}</td></tr>")
        A("</tbody></table></div></details>")
    A("</section>")

    # ---- 图表 ----
    figs = [
        ("fig_clean_funnel.png", "清洗与去重漏斗"),
        ("fig_source_dist.png", "各来源记录分布"),
        ("fig_source_opp_rate.png", "各来源机会率对比"),
        ("fig_cluster_k_sweep.png", "聚类 k 选择（轮廓系数）"),
        ("fig_value_ranking.png", "主题簇价值分与优先级"),
        ("fig_dim_radar.png", "Top-5 主题簇维度得分"),
        ("fig_score_matrix.png", "主题簇维度得分矩阵"),
        ("fig_audit_sources.png", "分来源处理结果"),
    ]
    A("<section><h2>四、图表</h2><div class='figs'>")
    for name, desc in figs:
        b64 = img_b64(fig_dir / name)
        if b64:
            A(f"<div class='fig'><img src='{b64}' alt='{esc(desc)}'>"
              f"<p>{esc(desc)}</p></div>")
    A("</div><p class='note'>P-R 曲线见 <span class='tag'>figs/pr_curve.png</span>"
      "（由阈值标定脚本生成）。</p></section>")

    # ---- 方法参数 ----
    wd = detail.get("weight_detail", {})
    sens = detail.get("sensitivity", {})
    A("<section><h2>五、方法与参数</h2>")
    A("<table><tbody>")
    rows = [
        ("判别阈值 τ", cfg["judge"]["threshold"]),
        ("规则权重", f"has_need {cfg['judge']['weights']['has_need']} / "
                    f"ai_core {cfg['judge']['weights']['ai_core']} / "
                    f"feasible {cfg['judge']['weights']['feasible']}"),
        ("聚类方法", f"{cfg['cluster']['method']}（简约原则 k_tolerance="
                    f"{cfg['cluster'].get('k_tolerance')}）"),
        ("赋权方法", f"{wd.get('method','entropy+ahp')}，α={wd.get('alpha','—')}"),
        ("敏感性", f"权重 ±{sens.get('perturb_pct',0.1)*100:.0f}% 扰动 "
                  f"{sens.get('trials','—')} 次，Spearman 均值 "
                  f"{sens.get('spearman_mean','—')}"),
    ]
    if metrics:
        rows.append(("聚类指标", "；".join(
            f"{m.get('track')}：{m.get('n_clusters')} 簇，轮廓系数 {m.get('silhouette')}"
            for m in metrics)))
    for k, v in rows:
        A(f"<tr><td style='width:130px;color:#656d76'>{esc(k)}</td><td>{esc(v)}</td></tr>")
    A("</tbody></table></section>")

    A(f"<footer>本报告由 scripts/make_html_report.py 自动生成 · {datetime.now():%Y-%m-%d %H:%M}"
      " · 数据可逐条溯源至原始链接</footer>")
    A(f"<script>{JS}</script>")
    A("</div></body></html>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(P), encoding="utf-8")
    print(f"已生成：{OUT}")
    print(f"  大小 {OUT.stat().st_size / 1024:.0f} KB（图片全部内嵌，可单独发送）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
