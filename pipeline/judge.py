# -*- coding: utf-8 -*-
"""任务二：机会判别 + 功能类别 / 行业双标签。

判别 = 规则特征（可解释、离线可用）+ LLM 结构化打分（覆盖语义）+ sigmoid 校准。
任何一步 LLM 不可用都会自动降级到规则，保证全链路始终能跑通（论文里作为 baseline）。
"""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from io_utils import get_logger, write_jsonl
from llm import prompts
from llm.client import LLMClient, LLMUnavailable
from schema import FUNC_CATEGORIES, INDUSTRIES

# ---------------------------------------------------------------------------
# 规则特征词表（论文附录可贴全表；命中率可作为可解释性证据）
# ---------------------------------------------------------------------------
NEED_PATTERNS = [
    r"有没有(什么|啥)?(工具|软件|方法|办法|插件|服务)",
    r"求(推荐|个|一个|教|助)",
    r"怎么(才能|样|办|做)",
    r"能不能(做|实现|自动)",
    r"如何(解决|实现|自动)",
    r"太(麻烦|费时|浪费时间|低效)",
    r"希望(有|能)",
    r"有没有人(知道|做过|遇到)",
    r"求助|请教|求指点",
    r"每天(都)?要(花|处理)",
    r"手动(处理|整理|填|录)",
    # 英文来源（GitHub / Kaggle / Stack Overflow）的需求句式
    r"\b(looking for|need|want|would (love|like)|hope(ful)? for)\b",
    r"\b(is there (a|an|any)|any(one)? (know|using)|does any(one)?)\b",
    r"\bhow (can|do|should) (i|we)\b",
    r"\b(spend|wasting) (hours|days|too much)\b",
    r"\b(manually|by hand|copy-paste)\b",
]

AI_CORE_PATTERNS = [
    r"(AI|人工智能|大模型|LLM|GPT|智能体|Agent|机器学习|深度学习)",
    r"(自动)?(识别|理解|生成|总结|摘要|翻译|问答|对话|推荐|预测|分类|提取)",
    r"(语音|图像|视频|文本)(识别|理解|生成|处理)",
    r"知识库|知识图谱|RAG|检索增强",
    r"多模态|OCR|NLP|CV",
    # 英文
    r"\b(summariz|translat|classif|predict|detect|extract|generat)(e|es|ed|ing|ion)?\b",
    r"\b(embedding|fine-?tun(e|ing)|inference|retrieval|knowledge base)\b",
]

INFEASIBLE_PATTERNS = [
    r"训练(一个)?(大)?模型",
    r"(十万|百万|千万|海量)(条)?(标注|样本|数据)",
    r"(自建|搭建)(算力|集群|GPU)",
    r"(专用|定制)硬件",
    r"从零(开始)?(研发|训练)",
    # 英文
    r"\b(train(ing)? (a |our own )?(large )?model|from scratch)\b",
    r"\b(millions? of (labeled|annotated) (samples|data))\b",
]

EXCLUDE_PATTERNS: Dict[str, List[str]] = {
    "recruit": [r"招聘", r"岗位职责", r"薪资", r"简历投递", r"急招",
                r"\b(we are hiring|job description|salary|resume|apply now)\b"],
    "ad": [r"限时优惠", r"折扣", r"免费试用.*天", r"扫码", r"加盟", r"代理",
           r"\b(discount|promo code|sign up (for )?free|limited time offer)\b"],
    "tutorial": [r"教程", r"手把手", r"入门(指南|教程)", r"一文(读懂|讲清)", r"详解",
                 r"\b(tutorial|step[- ]by[- ]step|a (complete|practical) guide)\b"],
    "news": [r"据悉", r"记者", r"发布会", r"融资", r"本轮", r"宣布", r"财报",
             r"\b(reportedly|announc|raises? \$|series [a-c] round|press release)\b"],
    "policy": [r"通知", r"征求意见", r"管理办法", r"政策解读", r"公告",
               r"\b(policy|regulation|compliance deadline)\b"],
    "chitchat": [r"哈哈", r"笑死", r"无语", r"吐槽一下",
                 r"\b(lol|funny|rant)\b"],
}

# 关键词 -> 功能类别（规则兜底 / LLM 不可用时的分类器）
FUNC_KEYWORDS: Dict[str, List[str]] = {
    "图像识别": ["图像", "图片", "照片", "ocr", "截图", "识图", "人脸"],
    "语义分析": ["语义", "情感", "舆情", "意图", "文本分析", "关键词"],
    "语音处理": ["语音", "录音", "转写", "会议纪要", "字幕", "asr", "tts"],
    "文本生成": ["写作", "文案", "生成", "润色", "改写", "摘要"],
    "对话问答": ["客服", "问答", "对话", "机器人", "咨询", "答疑"],
    "推荐系统": ["推荐", "个性化", "千人千面", "猜你喜欢"],
    "知识检索": ["知识库", "检索", "搜索", "文档", "rag", "查资料"],
    "数据挖掘": ["数据", "报表", "统计", "分析", "指标", "埋点"],
    "多模态融合": ["多模态", "图文", "音视频"],
    "智能体编排": ["智能体", "agent", "工作流", "编排", "自动化流程"],
    "自动化流程": ["自动化", "批量", "脚本", "rpa", "流程"],
    "预测分析": ["预测", "预警", "趋势", "风控", "估计"],
    "审核审查": ["审核", "风控", "合规", "质检", "过滤", "违规"],
    "搜索匹配": ["搜索", "匹配", "召回", "比对"],
    "翻译转写": ["翻译", "转写", "多语言", "本地化"],
    "视频理解": ["视频", "剪辑", "拆条", "镜头", "直播"],
}

INDUSTRY_KEYWORDS: Dict[str, List[str]] = {
    "金融": ["金融", "银行", "证券", "基金", "理财", "信贷"],
    "教育": ["教育", "学生", "老师", "课程", "学习", "考试", "培训"],
    "医疗": ["医疗", "医院", "医生", "问诊", "病历", "健康"],
    "法律": ["法律", "律师", "合同", "诉讼", "法条"],
    "电商": ["电商", "店铺", "淘宝", "天猫", "京东", "订单", "卖家", "客服"],
    "零售": ["零售", "门店", "超市", "便利店", "库存"],
    "房地产": ["房产", "楼盘", "中介", "租房", "物业"],
    "制造": ["制造", "工厂", "产线", "质检", "设备", "工艺"],
    "物流": ["物流", "快递", "仓储", "配送", "运输"],
    "游戏": ["游戏", "玩家", "副本", "策划", "美术"],
    "餐饮": ["餐饮", "餐厅", "外卖", "菜单", "门店"],
    "农业": ["农业", "种植", "养殖", "农技", "作物"],
    "政务": ["政务", "政府", "审批", "办事", "街道", "社区"],
    "汽车": ["汽车", "车辆", "车企", "驾驶", "4S"],
    "家居": ["家居", "家具", "装修", "软装"],
    "交通": ["交通", "出行", "地铁", "公交", "路况"],
    "能源": ["能源", "电力", "光伏", "电网", "油气"],
    "通信": ["通信", "运营商", "基站", "流量", "5G"],
    "娱乐": ["娱乐", "综艺", "明星", "粉丝", "内容平台"],
    "体育": ["体育", "赛事", "球队", "健身", "训练"],
    "旅游": ["旅游", "景区", "酒店", "行程", "攻略"],
    "保险": ["保险", "理赔", "保单", "险种"],
    "建筑": ["建筑", "施工", "工地", "图纸", "工程"],
    "环保": ["环保", "排放", "污染", "监测", "碳"],
    "科研": ["科研", "论文", "实验", "课题", "文献"],
    "人力资源": ["人力", "HR", "招聘", "绩效", "考勤", "员工"],
    "媒体出版": ["媒体", "编辑", "新闻", "出版", "稿件"],
    "营销广告": ["营销", "广告", "投放", "转化", "私域", "内容种草"],
    "外贸": ["外贸", "跨境", "进出口", "海关", "询盘"],
}


def _match_ratio(patterns: List[str], text: str) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.I))


def rule_features(text: str) -> Dict[str, Any]:
    """把赛题的 4 条规则翻译成 3 个连续分 + 1 个排除类别。"""
    n_need = _match_ratio(NEED_PATTERNS, text)
    n_ai = _match_ratio(AI_CORE_PATTERNS, text)
    n_bad = _match_ratio(INFEASIBLE_PATTERNS, text)

    # 需求信号：命中 1 条 = 0.55，之后每条 +0.15，封顶 0.95
    has_need = min(0.95, 0.55 + 0.15 * (n_need - 1)) if n_need else 0.20
    # AI 核心：未提 AI 相关词则给低分（但允许 LLM 事后纠正）
    ai_core = min(0.95, 0.50 + 0.15 * (n_ai - 1)) if n_ai else 0.25
    # 可落地：命中不可行信号就往下压
    feasible = max(0.10, 0.85 - 0.25 * n_bad)

    exclude, exclude_hits = "none", 0
    for label, pats in EXCLUDE_PATTERNS.items():
        hits = _match_ratio(pats, text)
        if hits > exclude_hits:
            exclude, exclude_hits = label, hits

    return {"has_need": round(has_need, 3), "ai_core": round(ai_core, 3),
            "feasible": round(feasible, 3), "exclude": exclude,
            "rule_hits": {"need": n_need, "ai": n_ai, "infeasible": n_bad,
                          "exclude": exclude_hits}}


def rule_classify(text: str) -> Tuple[str, str]:
    """关键词投票兜底分类（LLM 不可用时）。"""
    low = text.lower()

    def best(mapping: Dict[str, List[str]], default: str) -> str:
        scores = {k: sum(low.count(w) for w in ws) for k, ws in mapping.items()}
        top = max(scores.values()) if scores else 0
        if top <= 0:
            return default
        return max(scores, key=scores.get)

    return best(FUNC_KEYWORDS, "语义分析"), best(INDUSTRY_KEYWORDS, "其他")


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def combine(scores: Dict[str, float], exclude: str, cfg: Dict[str, Any]) -> float:
    """conf = sigmoid(slope * 加权和 + bias) * 排除惩罚。

    slope/bias 是校准参数：用于把「加权和 ~0.38-0.92」拉伸到有判别力的区间，
    使 conf=0.5 大致落在加权和 0.55 处。标定方法见 scripts/tune_threshold.py。
    """
    w = cfg["judge"]["weights"]
    s = (w["has_need"] * scores["has_need"]
         + w["ai_core"] * scores["ai_core"]
         + w["feasible"] * scores["feasible"])
    z = cfg["judge"].get("slope", 3.5) * s + cfg["judge"].get("bias", -1.925)
    conf = sigmoid(z)
    if exclude and exclude != "none":
        conf *= 0.35          # 排除类不直接归零：保留可复核的中间值
    return round(conf, 4)


def _judge_one(rec: Dict[str, Any], client: LLMClient,
               cfg: Dict[str, Any]) -> Dict[str, Any]:
    text = rec.get("clean_text", "")
    feats = rule_features(text)
    scored_by = "rule"
    out = dict(feats)

    if client.enabled:
        try:
            data = client.chat_json(prompts.judge_prompt(rec),
                                    system=prompts.JUDGE_SYSTEM)
            if data:
                out = {
                    "has_need": float(data.get("has_need", feats["has_need"])),
                    "ai_core": float(data.get("ai_core", feats["ai_core"])),
                    "feasible": float(data.get("feasible", feats["feasible"])),
                    "exclude": str(data.get("exclude", feats["exclude"])) or "none",
                    "reason": str(data.get("reason", ""))[:120],
                    "func_category": data.get("func_category"),
                    "industry": data.get("industry"),
                    "rule_hits": feats["rule_hits"],
                }
                scored_by = "llm"
        except LLMUnavailable:
            pass

    conf = combine(out, out.get("exclude", "none"), cfg)
    label = 1 if conf >= cfg["judge"]["threshold"] else 0

    func = out.get("func_category")
    ind = out.get("industry")
    if func not in FUNC_CATEGORIES or ind not in INDUSTRIES:
        f2, i2 = rule_classify(text)
        func = func if func in FUNC_CATEGORIES else f2
        ind = ind if ind in INDUSTRIES else i2

    rec2 = dict(rec)
    rec2.update({
        "has_need": round(out["has_need"], 3),
        "ai_core": round(out["ai_core"], 3),
        "feasible": round(out["feasible"], 3),
        "exclude": out.get("exclude", "none"),
        "reason": out.get("reason", ""),
        "confidence": conf,
        "is_opportunity": label,
        "func_category": func,
        "industry": ind,
        "scored_by": scored_by,
    })
    return rec2


def run(cfg: Dict[str, Any], records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    log = get_logger(cfg, "judge")
    client = LLMClient(cfg)
    log.info("LLM 状态：enabled=%s model=%s cache=%d 条",
             client.enabled, cfg["llm"].get("model"), client.cache_size())

    results: List[Dict[str, Any]] = []
    workers = max(1, int(cfg["judge"].get("llm_concurrency", 4))) if client.enabled else 1

    if workers == 1:
        for rec in records:
            results.append(_judge_one(rec, client, cfg))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_judge_one, rec, client, cfg): rec for rec in records}
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as exc:  # 单条失败不影响整批
                    log.warning("判别失败 %s：%s", futures[fut].get("record_id"), exc)

    order = {r["record_id"]: i for i, r in enumerate(records)}
    results.sort(key=lambda r: order.get(r["record_id"], 1 << 30))

    n_pos = sum(r["is_opportunity"] for r in results)
    log.info("判别完成：%d 条，机会 %d 条（%.1f%%），阈值 τ=%.2f",
             len(results), n_pos, 100 * n_pos / max(len(results), 1),
             cfg["judge"]["threshold"])

    write_jsonl(f"{cfg['paths']['clean']}/judged.jsonl", results)
    return results
