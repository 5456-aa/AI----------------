# -*- coding: utf-8 -*-
"""提示词集中管理。改 prompt 会改变判别结果 —— 一定要同步更新论文与缓存版本。"""
from __future__ import annotations

from typing import Any, Dict, List

from schema import FUNC_CATEGORIES, INDUSTRIES

PROMPT_VERSION = "v1.3-20261106"

JUDGE_SYSTEM = """你是产业分析师，专门从真实的用户发言中判断"是否存在可以被 AI 技术解决的商业机会"。
你的判断必须克制：宁可漏判，也不要把资讯、广告、教程、招聘当成需求。
只输出 JSON，不要任何解释性文字。"""

JUDGE_USER = """请判断下面这条来自「{source}」的记录，是否构成一个"AI 应用机会"。

判定标准（四条，缺一不可）：
1. has_need（有真实需求）：记录里出现了具体的人在表达具体的问题、痛点、求助或期望，
   例如"有没有工具能…""求推荐…""怎么才能…""太麻烦了""希望有个…"。纯陈述事实不算。
2. ai_core（AI 是核心）：这个问题必须依赖 AI 能力（语义理解、生成、识别、预测、多模态）
   才能解决；如果只是普通信息化/外包/人力就能解决，应判低分。
3. feasible（技术可落地）：当前技术即可实现，不需要自研基础模型、不需要海量标注数据、
   不需要专用硬件。
4. exclude（排除情形）：如果记录属于以下任一类别，exclude 设为该类别，否则设为 "none"：
   news（纯资讯报道）、ad（广告营销）、tutorial（教程科普）、recruit（招聘）、
   policy（政策公告）、chitchat（纯情绪无诉求）、other。

待判定记录：
标题：{title}
正文：{content}

只输出如下 JSON：
{{"has_need": 0.0, "ai_core": 0.0, "feasible": 0.0,
  "exclude": "none",
  "func_category": "{func0}",
  "industry": "{ind0}",
  "reason": "不超过40字的中文理由"}}
其中 has_need/ai_core/feasible 取值 0 到 1；func_category 只能从 {func_list} 中选一个；
industry 只能从 {ind_list} 中选一个。"""

CLASSIFY_USER = """把下面这条记录归到一个"功能类别"和一个"所属行业"。

功能类别候选：{func_list}
所属行业候选：{ind_list}

标题：{title}
正文：{content}

只输出 JSON：{{"func_category": "…", "industry": "…", "confidence": 0.0}}"""

TOPIC_NAME_SYSTEM = """你擅长把一个话题簇概括成一个精准的中文短语。只输出 JSON。"""

TOPIC_NAME_USER = """下面是一组被聚为同一主题的记录，请概括它们共同指向的"AI 应用机会方向"。

要求：
1. 一句话，不超过 {max_chars} 个汉字；
2. 必须包含"场景 + AI 能力"两层信息，例如"电商智能客服与知识库问答"；
3. 不要出现"其他""综合""相关""等"这类空泛词；
4. 不要写成句子，不要标点结尾。

簇内记录标题：
{titles}

只输出 JSON：{{"topic_name": "…"}}
（不要输出功能类别和行业，这两个字段由系统按簇内记录众数自动填充）"""

PROPOSAL_USER = """请为下面这个"AI 应用机会方向"写一份立项策划案，中文，结构化输出 JSON。

方向：{topic_name}
功能类别：{func_category}
所属行业：{industry}
机会价值分：{score}（满分 100，全簇排名第 {rank}）
依据记录（共 {n} 条，来自 {sources}）：
{evidence}

输出 JSON，字段如下：
{{"goal": "目标功能，2-3 句",
  "tech_route": "技术路线，分点",
  "duration_weeks": 12,
  "subtasks": [{{"name": "子任务名", "weeks": 2, "owner_role": "角色"}}],
  "risks": ["风险1", "风险2"],
  "kpis": ["指标1", "指标2"]}}"""


def _fmt_list(items: List[str], limit: int = 40) -> str:
    return "、".join(items[:limit])


def judge_prompt(rec: Dict[str, Any]) -> str:
    return JUDGE_USER.format(
        source=rec.get("source", ""),
        title=rec.get("title", ""),
        content=rec.get("clean_text", "")[:1500],
        func0=FUNC_CATEGORIES[0],
        ind0=INDUSTRIES[0],
        func_list=_fmt_list(FUNC_CATEGORIES),
        ind_list=_fmt_list(INDUSTRIES),
    )


def classify_prompt(rec: Dict[str, Any]) -> str:
    return CLASSIFY_USER.format(
        func_list=_fmt_list(FUNC_CATEGORIES),
        ind_list=_fmt_list(INDUSTRIES),
        title=rec.get("title", ""),
        content=rec.get("clean_text", "")[:1200],
    )


def topic_name_prompt(titles: List[str], max_chars: int = 20) -> str:
    return TOPIC_NAME_USER.format(
        max_chars=max_chars,
        titles="\n".join(f"- {t}" for t in titles[:20]),
    )
