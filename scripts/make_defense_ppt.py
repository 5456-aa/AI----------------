# -*- coding: utf-8 -*-
"""生成答辩 PPT（16:9，15 页），每页带讲稿备注。

用法：python scripts/make_defense_ppt.py
产出：reports/答辩PPT.pptx
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from io_utils import load_config, read_jsonl  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402

OUT = ROOT / "reports" / "答辩PPT.pptx"
FIG = ROOT / "figs" / "all"
SHOT = ROOT / "figs" / "screens"

NAVY = RGBColor(0x1E, 0x3A, 0x8A)
BLUE = RGBColor(0x25, 0x63, 0xEB)
INK = RGBColor(0x11, 0x18, 0x27)
GREY = RGBColor(0x6B, 0x72, 0x80)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def rows(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with io.open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def add_slide(prs, title: str, bullets: list[str] | None = None,
              img: Path | None = None, note: str = "",
              img_width: float = 6.4, img_left: float = 6.2, img_top: float = 1.7):
    s = prs.slides.add_slide(prs.slide_layouts[6])      # 空白版式
    bar = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = BLUE; bar.line.fill.background()

    tb = s.shapes.add_textbox(Inches(0.55), Inches(0.45), Inches(12.2), Inches(0.8))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; r = p.add_run(); r.text = title
    r.font.size = Pt(30); r.font.bold = True; r.font.color.rgb = NAVY
    r.font.name = "微软雅黑"

    if bullets:
        body = s.shapes.add_textbox(Inches(0.7), Inches(1.55),
                                    Inches(img_left - 0.5 if img else 12.0), Inches(5.2))
        bf = body.text_frame; bf.word_wrap = True
        for i, b in enumerate(bullets):
            para = bf.paragraphs[0] if i == 0 else bf.add_paragraph()
            para.space_after = Pt(10)
            run = para.add_run(); run.text = b
            run.font.size = Pt(17); run.font.color.rgb = INK
            run.font.name = "微软雅黑"

    if img and img.exists():
        s.shapes.add_picture(str(img), Inches(img_left), Inches(img_top),
                             width=Inches(img_width))

    if note:
        s.notes_slide.notes_text_frame.text = note
    return s


def cover(prs, title: str, sub: str, meta: str):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
    bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()

    tb = s.shapes.add_textbox(Inches(0.9), Inches(2.1), Inches(11.6), Inches(1.4))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; r = p.add_run(); r.text = title
    r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = WHITE
    r.font.name = "微软雅黑"

    tb2 = s.shapes.add_textbox(Inches(0.95), Inches(3.5), Inches(11.4), Inches(0.8))
    tf2 = tb2.text_frame; tf2.word_wrap = True
    r2 = tf2.paragraphs[0].add_run(); r2.text = sub
    r2.font.size = Pt(19); r2.font.color.rgb = RGBColor(0xBF, 0xD2, 0xFE)
    r2.font.name = "微软雅黑"

    tb3 = s.shapes.add_textbox(Inches(0.95), Inches(5.4), Inches(11.4), Inches(1.0))
    r3 = tb3.text_frame.paragraphs[0].add_run(); r3.text = meta
    r3.font.size = Pt(14); r3.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)
    r3.font.name = "微软雅黑"

    s.notes_slide.notes_text_frame.text = (
        "开场：我们用 15 分钟讲清楚三件事——为什么做、怎么做的、做出来什么效果。"
        "全程不念 PPT，数字都在屏幕上。")
    return s


def main() -> int:
    cfg = load_config(track="all")
    judged = read_jsonl(Path(cfg["paths"]["clean"]) / "judged.jsonl")
    detail = (read_jsonl(Path(cfg["paths"]["clean"]) / "score_detail.jsonl") or [{}])[0]
    r1 = rows(ROOT / "data/out/result1.csv")
    r2 = rows(ROOT / "data/out/result2.csv")
    r3 = rows(ROOT / "data/out/result3.csv")
    r4 = rows(ROOT / "data/out/result4.csv")
    n_all, n_opp = len(r2), sum(1 for r in r2 if r["是否构成机会"] == "1")
    src_n = len({r["来源网站名称"] for r in r1})
    sens = detail.get("sensitivity", {})

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    cover(prs, "AI 应用场景的智能挖掘与机会评估系统",
          "从多源零散信号，到可量化的决策结论",
          f"采集批次 B20261113-01　·　{src_n} 个来源　·　{n_all} 条入表　·　{n_opp} 条机会")

    add_slide(prs, "一、我们要解决的问题",
              ["企业想知道「AI 能做什么、怎么用 AI 解决实际问题」",
               "但信号散落在 GitHub、问答社区、视频、技术博客…… 零散、量大、噪声高",
               "赛题要求：把零散信号 → 结构化、可量化的决策结论",
               "难点不在模型，在「来源选择 + 判别口径 + 可溯源」"],
              note="这一页只讲三句话：信号散、判断难、要可量化。不要展开技术细节。")

    add_slide(prs, "二、技术路线：五步端到端",
              ["① 多源采集 → 原始快照（可回原文）",
               "② 清洗 + 三层去重 → 917 条收敛到 735 条",
               "③ 机会判别 → 四规则 + 大模型协同，阈值由 P-R 标定",
               "④ 主题聚类 → 分赛道聚类 + 稳定性检验",
               "⑤ 价值评估 → 熵权+AHP 组合赋权 + 敏感性分析",
               "⑥ 决策产出 → 立项策划案 + 仪表盘 + 问答"],
              note="强调每一步都落盘、都能回放，这是后面溯源演示的基础。")

    add_slide(prs, "三、任务一：11 个来源，全部实测",
              [f"可采集 {src_n} 个：GitHub、掘金、SegmentFault、哔哩哔哩、Stack Overflow…",
               "手册 20 个来源逐个探测：8 个可用 + 3 个清单外补充",
               "弃用有据：V2EX 网络不可达、36氪/机器之心 是 SPA",
               "CSDN 的 robots.txt 为 Disallow: / → 主动放弃",
               "哔哩哔哩需先取匿名设备标识 buvid3，否则 412"],
              img=FIG / "fig_source_status.png", img_width=5.6, img_left=7.2,
              note="这是最能体现「认真做过」的一页：20 个源全试过，不能用的都有原因。")

    add_slide(prs, "四、任务一：清洗与三层去重",
              ["L1 URL 精确去重：剔除 163 条（跨检索词重复）",
               "L2 SimHash（汉明距离 ≤3）：剔除 6 条",
               "L3 TF-IDF 余弦 ≥0.95：本批 0 条（转载少）",
               "清洗规则链 9 条：HTML、脱敏、全半角、繁简、广告模板…",
               "结果：917 条 → 735 条，去重率 19.8%"],
              img=FIG / "fig_clean_funnel.png", img_width=5.4, img_left=7.4,
              note="去重不是越多越好，要说明每层剔除的是什么形态的重复。")

    add_slide(prs, "五、任务二：把四条规则变成可计算的分数",
              ["① 真实需求：需求句式正则 + 语义打分",
               "② AI 为核心：能力词表 + 语义打分",
               "③ 可落地：排除「自研模型/海量标注/专用硬件」",
               "④ 排除情形：资讯、广告、教程、招聘、政策、吐槽",
               "conf = σ(slope·Σwᵢsᵢ + bias) × 排除惩罚"],
              note="公式要讲清楚：加权和再过一个 sigmoid，slope/bias 是为了把分数拉开。")

    prs_slide = add_slide(prs, "六、任务二：阈值不是拍脑袋，是标定出来的",
                          [f"人工标注 120 条（分层抽样：正例 + 边界 + 随机）",
                           f"扫描 τ ∈ [0.10, 0.90]，取 F1 最大点",
                           f"最优 τ = {cfg['judge']['threshold']}，P=0.90 / R=1.00 / F1=0.95",
                           "分层抽样下指标偏乐观——用于选阈值，不代表全量泛化"],
                          img=ROOT / "figs" / "pr_curve.png", img_width=5.6, img_left=7.2,
                          note="主动说明局限：这是分层样本，不是全量估计。评委反而会认可。")

    add_slide(prs, "七、任务二：消融实验——为什么必须上语义判别",
              ["仅规则特征：P=0.44，R=0.18，F1=0.26",
               "规则+大模型：P=0.90，R=1.00，F1=0.95",
               "规则版召回只有 0.18——五分之四的真实需求被漏掉",
               "原因：教程文章命中了「推荐/自动/知识库」等词"],
              img=FIG / "fig_ablation.png", img_width=6.0, img_left=6.8,
              note="这是全文最有说服力的一张图：不是「我们用了大模型」，而是「不用会漏多少」。")

    add_slide(prs, "八、任务三：聚类与稳定性",
              [f"分赛道聚类：电商与教育语义差异大，混聚会被稀释",
               "层次聚类 + k 扫描，三条约束防退化：",
               "　· max_cluster_share 防巨簇　· k_tolerance 简约原则　· 小簇合并",
               f"电商 ARI 0.768 / 教育 0.745（Bootstrap 10 次）",
               f"最终 {len(r3)} 个主题簇，每簇可溯源到记录编号"],
              img=FIG / "fig_cluster_k_sweep.png", img_width=5.6, img_left=7.2,
              note="ARI 是关键：说明换 80% 样本，簇结构还能对上七成以上。")

    add_slide(prs, "九、任务四：四维评分 + 组合赋权",
              ["多源指向度、记录规模、互动热度、需求强度",
               "熵权法（客观）+ AHP（主观）组合，α=0.5",
               f"敏感性：权重 ±10% 扰动 100 次，Spearman {sens.get('spearman_mean','—')}",
               "输出：11 个簇的价值分与优先级"],
              img=FIG / "fig_weight_compare.png", img_width=5.8, img_left=7.0,
              note="权重不是拍脑袋，是两种方法组合；敏感性分析证明排序稳定。")

    add_slide(prs, "十、任务五：决策产出与系统",
              ["立项策划案：目标功能/技术路线/实施周期/子任务/依据来源/价值评分",
               "技术路线逐条引用记录编号（如 JY00007），可回溯",
               "仪表盘 + 单文件 HTML 报告 + 问答咨询",
               "三级降级：有 Key 用 API，无 Key 用缓存，都没有退回规则"],
              img=SHOT / "03_簇内记录可溯源.png", img_width=6.2, img_left=6.6,
              note="强调可溯源：点开每条记录能回到原文链接，这是赛题硬要求。")

    add_slide(prs, "十一、多批次：一次需求 = 一个批次",
              ["电商 351 条 / 教育 384 条 / 医疗 73 条 / 法律 76 条",
               "各批次独立：采集、去重、聚类、评分互不影响",
               "提交版取电商+教育合并批次，其余用于验证可扩展性",
               "发现：来源覆盖不足时，方向越垂直，机会越少"],
              img=FIG / "fig_batch_compare.png", img_width=6.0, img_left=6.8,
              note="主动讲局限：医疗法律信号少，是来源问题不是系统问题。")

    add_slide(prs, "十二、核心结论：选源比调模型更重要",
              ["机会密度由来源形态决定，不由需求方向决定：",
               "　问答社区 47.8% ＞ GitHub 11.5% ＞ 视频 2.5% ＞ 教程 2.5% ＞ 资讯 0%",
               "同为技术社区，问答形态天然产生需求，教程形态天然不产生",
               "所以：多源探测 + 合规判断，比模型调参更能提升产出"],
              img=FIG / "fig_source_opp_rate.png", img_width=5.6, img_left=7.2,
              note="这是全篇的「一句话结论」，答辩时务必让评委记住这一页。")

    add_slide(prs, "十三、局限与改进",
              ["标注集 120 条偏小，重新采集后 62 条可对齐，κ 正在补",
               "TF-IDF 向量在小样本上会低估簇数，建议换 BGE 句向量",
               "医疗/法律方向来源覆盖不足（2~3 个源）",
               "单一时间窗口采集，未做趋势对比"],
              note="主动讲局限，比被问出来好。每一条都给出改进方向。")

    add_slide(prs, "十四、总结",
              [f"{n_all} 条入表，{n_opp} 条机会，{len(r3)} 个主题簇",
               "五步端到端，每步可溯源、可复现",
               "判别阈值数据驱动，消融实验证明必要性",
               "交付：四份结果文件 + 源码 + 11 张截图 + AI 使用说明"],
              note="收尾一句话：我们交付的不只是结果，是一套能重跑、能追溯的系统。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"已生成：{OUT}（{len(prs.slides.__iter__.__self__._sldIdLst)} 页）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
