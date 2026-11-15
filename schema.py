# -*- coding: utf-8 -*-
"""四个结果文件的表头与字段约束（唯一真源 / single source of truth）。

改动此处之前先看 result1~4.csv 模板原文：表头必须逐字一致，包括全角括号。
"""
from typing import Dict, List

# 任务一：清洗去重后的全部记录
RESULT1_COLS: List[str] = [
    "采集批次号",
    "记录编号",
    "来源网站名称",
    "来源链接",
    "内容",
    "发布时间",
    "热度指标（如浏览数、点赞数、讨论数等）",
]

# 任务二：逐条机会判别 + 功能类别 / 所属行业
RESULT2_COLS: List[str] = [
    "采集批次号",
    "记录编号",
    "是否构成机会",
    "机会置信度",
    "功能类别",
    "所属行业",
]

# 任务三：主题簇与簇内溯源
RESULT3_COLS: List[str] = [
    "采集批次号",
    "主题簇编号",
    "主题簇名称",
    "功能类别",
    "所属行业",
    "簇内机会记录数",
    "来源覆盖",
    "簇内机会记录",
]

# 任务四：簇机会价值分与优先级
RESULT4_COLS: List[str] = [
    "采集批次号",
    "主题簇编号",
    "主题簇名称",
    "功能类别",
    "所属行业",
    "机会价值分",
    "优先级",
]

ALL_RESULT_COLS: Dict[str, List[str]] = {
    "result1": RESULT1_COLS,
    "result2": RESULT2_COLS,
    "result3": RESULT3_COLS,
    "result4": RESULT4_COLS,
}

# ---------------------------------------------------------------------------
# 附件1 标签体系（16 功能类别 / 30 行业）。允许“包括但不限于”，
# 但建议严格使用原表，便于与评审口径对齐。
# ---------------------------------------------------------------------------
FUNC_CATEGORIES: List[str] = [
    "图像识别", "语义分析", "语音处理", "文本生成", "对话问答", "推荐系统",
    "知识检索", "数据挖掘", "多模态融合", "智能体编排", "自动化流程", "预测分析",
    "审核审查", "搜索匹配", "翻译转写", "视频理解",
]

INDUSTRIES: List[str] = [
    "金融", "教育", "医疗", "法律", "电商", "零售", "房地产", "制造", "物流",
    "游戏", "餐饮", "农业", "政务", "汽车", "家居", "交通", "能源", "通信",
    "娱乐", "体育", "旅游", "保险", "建筑", "环保", "科研", "人力资源",
    "媒体出版", "营销广告", "外贸", "其他",
]

# 附件2 来源清单的规范名称（必须用这些名字，不要自造简称）
SOURCE_NAMES: List[str] = [
    "哔哩哔哩", "GitHub", "Product Hunt", "掘金", "InfoQ中国", "少数派", "CSDN",
    "机器之心", "量子位", "36氪", "IT之家", "V2EX", "Stack Overflow",
    "阿里云开发者社区", "Papers with Code", "Semantic Scholar", "Kaggle",
    "天池", "DataFountain", "数睿思",
]

SOURCE_CATEGORY: Dict[str, str] = {
    "哔哩哔哩": "视频与内容社区",
    "GitHub": "开源项目与产品社区",
    "Product Hunt": "开源项目与产品社区",
    "掘金": "技术内容与教程社区",
    "InfoQ中国": "技术内容与教程社区",
    "少数派": "技术内容与教程社区",
    "CSDN": "技术内容与教程社区",
    "机器之心": "科技与AI垂直资讯",
    "量子位": "科技与AI垂直资讯",
    "36氪": "科技与AI垂直资讯",
    "IT之家": "科技与AI垂直资讯",
    "V2EX": "问答与需求社区",
    "Stack Overflow": "问答与需求社区",
    "阿里云开发者社区": "问答与需求社区",
    "Papers with Code": "学术论文与预印本",
    "Semantic Scholar": "学术论文与预印本",
    "Kaggle": "竞赛与数据集平台",
    "天池": "竞赛与数据集平台",
    "DataFountain": "竞赛与数据集平台",
    "数睿思": "竞赛与数据集平台",
    # 清单外补充源（赛题允许自主选用其他公开渠道）
    "SegmentFault": "问答与需求社区",
    "博客园": "技术内容与教程社区",
    "开源中国": "技术内容与教程社区",
}

# 论文「数据来源」表要用：官网、采集方式、合规依据
SOURCE_META: Dict[str, Dict[str, str]] = {
    "GitHub": {"url": "https://github.com", "method": "官方 REST API（/search/issues）",
               "compliance": "公开 API；未认证限速 10 次/分钟，已按 1.2s 间隔节流"},
    "V2EX": {"url": "https://www.v2ex.com", "method": "官方公开 API（/api/topics/show.json）",
             "compliance": "公开只读 API，不登录"},
    "Stack Overflow": {"url": "https://stackoverflow.com", "method": "官方 API（/2.3/questions）",
                       "compliance": "公开 API，遵守配额限制"},
    "Kaggle": {"url": "https://www.kaggle.com", "method": "公开页（竞赛/数据集列表）",
               "compliance": "仅取公开元数据，不下载受限数据集"},
    "掘金": {"url": "https://juejin.cn", "method": "站内搜索页（低频）",
             "compliance": "遵守 robots.txt 与 ToS，1.2s 间隔，不绕验证码"},
    "少数派": {"url": "https://sspai.com", "method": "站点 RSS / 文章页",
               "compliance": "RSS 由站点公开提供"},
    "36氪": {"url": "https://36kr.com", "method": "站点 RSS / 资讯页",
             "compliance": "RSS 由站点公开提供"},
    "机器之心": {"url": "https://www.jiqizhixin.com", "method": "站点 RSS / 资讯页",
                 "compliance": "RSS 由站点公开提供"},
    "CSDN": {"url": "https://www.csdn.net", "method": "站内搜索页（低频）",
             "compliance": "遵守 robots.txt；反爬严格时降低频率或弃用"},
    "哔哩哔哩": {"url": "https://www.bilibili.com", "method": "公开搜索接口（低频）",
                 "compliance": "反爬较强，仅取公开元数据，低频访问"},
}


SOURCE_META.update({
    "SegmentFault": {"url": "https://segmentfault.com", "method": "Atom feed（问答流）",
                     "compliance": "feed 由站点公开提供"},
    "博客园": {"url": "https://www.cnblogs.com", "method": "Atom feed",
             "compliance": "feed 由站点公开提供"},
    "开源中国": {"url": "https://www.oschina.net", "method": "RSS（资讯）",
               "compliance": "RSS 由站点公开提供"},
})


def source_meta(name: str) -> Dict[str, str]:
    return SOURCE_META.get(
        name, {"url": "", "method": "公开页面", "compliance": "公开可访问内容"})
