# -*- coding: utf-8 -*-
"""数据审计报告：直接对应评分标准第一条「数据预处理的完整性」。

产出：
    reports/<track>/data_audit.md     每来源 采集/保留/剔除/缺失 明细 + 全局漏斗
    figs/<track>/fig_audit_sources.png  来源 × 阶段 堆叠柱
    figs/<track>/fig_audit_missing.png  字段缺失率

用法：python scripts/report_audit.py --track ecommerce|education|all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import (TRACKS, load_config, read_jsonl,  # noqa: E402
                      track_report_dir)
from schema import SOURCE_CATEGORY, source_meta  # noqa: E402


def _sum_by_source(rows: list) -> dict:
    """按来源累加（合并赛道时同一来源会出现多条）。"""
    acc: dict = {}
    for r in rows:
        src = r.get("source", "未知")
        cur = acc.setdefault(src, {"source": src})
        for k, v in r.items():
            if k == "source":
                continue
            if isinstance(v, (int, float)):
                cur[k] = cur.get(k, 0) + v
    return acc


def build(cfg) -> dict:
    clean_dir = Path(cfg["paths"]["clean"])
    audit_clean = _sum_by_source(read_jsonl(clean_dir / "audit_clean.jsonl"))
    audit_dedup = _sum_by_source(read_jsonl(clean_dir / "audit_dedup.jsonl"))
    funnel = (read_jsonl(clean_dir / "dedup_funnel.jsonl") or [{}])[0]
    judged = read_jsonl(clean_dir / "judged.jsonl")

    opp_by_src: dict[str, int] = {}
    for r in judged:
        if r.get("is_opportunity") == 1:
            src = r.get("source", "未知")
            opp_by_src[src] = opp_by_src.get(src, 0) + 1

    sources = sorted(audit_clean, key=lambda s: -audit_clean[s]["raw"])
    rows = []
    for src in sources:
        a, d = audit_clean[src], audit_dedup.get(src, {})
        n_clean = a["kept"]
        n_final = d.get("after_L3", n_clean)
        rows.append({
            "source": src,
            "raw": a["raw"],
            "kept_clean": n_clean,
            "dropped_clean": a["dropped"],
            "tooshort": a.get("drop_too_short", 0),
            "notcn": a.get("drop_not_chinese", 0),
            "ad": a.get("drop_ad_like", 0),
            "dedup_dropped": max(n_clean - n_final, 0),
            "final": n_final,
            "opp": opp_by_src.get(src, 0),
            "miss_time": a.get("missing_publish_time", 0),
            "miss_heat": a.get("missing_heat", 0),
            "miss_title": a.get("missing_title", 0),
            "translated": a.get("translated", 0),
        })
    return {"rows": rows, "funnel": funnel, "n_judged": len(judged),
            "n_opp": sum(opp_by_src.values())}


def render_md(cfg, data: dict) -> str:
    rows = data["rows"]
    tot = {k: sum(r[k] for r in rows) for k in
           ("raw", "kept_clean", "dropped_clean", "tooshort", "notcn", "ad",
            "dedup_dropped", "final", "opp", "miss_time", "miss_heat", "miss_title",
            "translated")}
    f = data["funnel"]

    L = [
        f"# 数据审计报告 · {cfg['track']}",
        "",
        f"需求方向：**{cfg['project'].get('demand_direction')}**　"
        f"来源数：**{len(rows)}**　最终记录：**{tot['final']}**　机会记录：**{tot['opp']}**",
        "",
        "## 一、全局处理漏斗",
        "",
        "| 阶段 | 记录数 | 本阶段剔除 | 本阶段剔除率 |",
        "|---|---|---|---|",
        f"| 原始采集 | {tot['raw']} | — | — |",
        f"| 清洗保留（进入去重） | {f.get('raw', 0)} | {tot['dropped_clean']} | "
        f"{_pct(tot['dropped_clean'], tot['raw'])} |",
        f"| L1 URL 精确去重 | {f.get('after_L1_url', 0)} | {f.get('dropped_L1', 0)} | "
        f"{_pct(f.get('dropped_L1', 0), f.get('raw', 0))} |",
        f"| L2 SimHash 近似去重 | {f.get('after_L2_simhash', 0)} | {f.get('dropped_L2', 0)} | "
        f"{_pct(f.get('dropped_L2', 0), max(f.get('after_L1_url', 1), 1))} |",
        f"| L3 语义去重（最终） | {f.get('after_L3_semantic', 0)} | {f.get('dropped_L3', 0)} | "
        f"{_pct(f.get('dropped_L3', 0), max(f.get('after_L2_simhash', 1), 1))} |",
        "",
        f"端到端保留率 **{_pct(tot['final'], tot['raw'])}**；"
        f"清洗阶段剔除 **{tot['dropped_clean']}** 条"
        f"（过短 {tot['tooshort']}、非中文 {tot['notcn']}、疑似广告 {tot['ad']}），"
        f"去重阶段剔除 **{f.get('dropped_L1', 0) + f.get('dropped_L2', 0) + f.get('dropped_L3', 0)}** 条。",
        "",
        "## 二、分来源明细",
        "",
        "| 来源 | 采集 | 清洗保留 | 过短 | 非中文 | 广告 | 去重剔除 | 最终 | 机会 | 缺时间 | 缺热度 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(
            f"| {r['source']} | {r['raw']} | {r['kept_clean']} | {r['tooshort']} | "
            f"{r['notcn']} | {r['ad']} | {r['dedup_dropped']} | {r['final']} | {r['opp']} | "
            f"{r['miss_time']} | {r['miss_heat']} |")
    L.append(
        f"| **合计** | {tot['raw']} | {tot['kept_clean']} | {tot['tooshort']} | {tot['notcn']} | "
        f"{tot['ad']} | {tot['dedup_dropped']} | {tot['final']} | {tot['opp']} | "
        f"{tot['miss_time']} | {tot['miss_heat']} |")

    L += [
        "",
        "## 三、字段完整性与来源结构（论文可直接引用）",
        "",
        f"- 发布时间缺失率：**{_pct(tot['miss_time'], tot['raw'])}**",
        f"- 热度指标缺失率：**{_pct(tot['miss_heat'], tot['raw'])}**（缺失记为「无」，不参与任务四热度维度，"
        f"按簇内均值处理）",
        f"- 标题缺失率：**{_pct(tot['miss_title'], tot['raw'])}**",
        f"- 机器翻译记录：**{tot.get('translated', 0)}** 条"
        f"（占最终记录 {_pct(tot.get('translated', 0), tot['final'])}，原文保留可逐条核对）",
        f"- 来源类别数：**{len({r['source'] for r in rows})}** 个站点，"
        f"最终记录平均每源 **{tot['final'] / max(len(rows), 1):.1f}** 条",
        f"- 机会转化率：**{_pct(tot['opp'], tot['final'])}**",
        "",
        "## 四、数据来源与合规说明",
        "",
        "| 来源 | 类别 | 官网 | 采集方式 | 合规依据 | 最终条数 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        meta = source_meta(r["source"])
        L.append(f"| {r['source']} | {SOURCE_CATEGORY.get(r['source'], '—')} | "
                 f"{meta['url']} | {meta['method']} | {meta['compliance']} | {r['final']} |")

    L += [
        "",
        "**采集纪律**（论文第 2 章「数据来源与合规」可直接引用本节）：",
        "",
        "1. 只访问公开可访问内容，不登录、不绕过验证码或反爬机制；",
        "2. 请求间隔 ≥ 1.2s，UA 明示用途与联系方式，遵守 robots.txt 与站点 ToS；",
        "3. 只保存正文与元数据，手机号/邮箱/身份证在本系统中正则脱敏；",
        "4. 每条记录保留 `来源链接` 与原始响应快照（`data/raw/<track>/`），实现逐条溯源；",
        "5. 英文记录经大模型翻译为中文，`orig_title` / `orig_content` 保留原文，",
        "   `source_lang` 标注语言，翻译过程可审计（LLM 调用全部落缓存）。",
        "",
        "> 说明：清洗阶段判定规则见 `config.yaml → clean`；去重阈值见 `clean.dedup`。"
        "所有剔除记录未进入结果文件，但原始快照保留在 `data/raw/<track>/` 可回溯。",
    ]
    return "\n".join(L)


def _pct(a, b) -> str:
    return f"{(a / b * 100) if b else 0:.1f}%"


def figures(cfg, data: dict, out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("（matplotlib 未安装，跳过图）")
        return

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 200

    rows = data["rows"]
    names = [r["source"] for r in rows]
    kept = np.array([r["final"] for r in rows])
    d_clean = np.array([r["dropped_clean"] for r in rows])
    d_dedup = np.array([r["dedup_dropped"] for r in rows])

    fig, ax = plt.subplots(figsize=(6.8, 0.45 * len(names) + 1.8))
    y = np.arange(len(names))[::-1]
    ax.barh(y, kept, color="#4C78A8", label="最终保留")
    ax.barh(y, d_clean, left=kept, color="#F28E2B", label="清洗剔除")
    ax.barh(y, d_dedup, left=kept + d_clean, color="#E15759", label="去重剔除")
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlabel("记录数")
    ax.set_title("分来源处理结果（原始 = 三段之和）")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "fig_audit_sources.png", bbox_inches="tight")
    plt.close(fig)

    miss = {
        "发布时间": sum(r["miss_time"] for r in rows),
        "热度指标": sum(r["miss_heat"] for r in rows),
        "标题": sum(r["miss_title"] for r in rows),
    }
    total = sum(r["raw"] for r in rows) or 1
    fig, ax = plt.subplots(figsize=(4.8, 2.8))
    vals = [v / total * 100 for v in miss.values()]
    bars = ax.bar(list(miss.keys()), vals, color="#59A14F")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.5, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_ylabel("缺失率 (%)")
    ax.set_title("字段缺失率（原始记录）")
    fig.tight_layout()
    fig.savefig(out_dir / "fig_audit_missing.png", bbox_inches="tight")
    plt.close(fig)
    print(f"图 -> {out_dir}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="all", help="赛道名或 all")
    args = ap.parse_args(argv)

    tracks = [args.track]   # all = 合并目录（提交用）；单赛道请显式指定
    for track in tracks:
        cfg = load_config(track=track)
        try:
            data = build(cfg)
        except FileNotFoundError as exc:
            print(f"[{track}] 缺少中间结果：{exc}")
            continue
        if not data["rows"]:
            print(f"[{track}] 没有审计数据，先跑 run_all.py --track {track}")
            continue

        rep_dir = track_report_dir(cfg, track)
        rep_dir.mkdir(parents=True, exist_ok=True)
        md = render_md(cfg, data)
        (rep_dir / "data_audit.md").write_text(md, encoding="utf-8")

        fig_dir = Path(cfg["base_paths"]["figs"]) / track
        figures(cfg, data, fig_dir)

        (rep_dir / "data_audit.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{track}] 审计报告 -> {rep_dir / 'data_audit.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
