# -*- coding: utf-8 -*-
"""采集适配器注册表 + 两个参考实现（GitHub Issues / V2EX）。

当前状态：**骨架待用**。按赛题节奏，第 1 天再逐个启用。
每个适配器都用官方公开 API，不解析反爬页面，合规成本最低。

新增一个源的做法：
  1. 在下面写一个 BaseCollector 子类，实现 search()；
  2. 在 REGISTRY 里登记，并把 enabled 设为 True；
  3. 跑 `python run_collect.py --source <名称>`，检查 data/raw/<名称>/ 下的快照。
"""
from __future__ import annotations

from typing import Any, Dict, List, Type

from collectors.base import BaseCollector, Record
from collectors.live import (BilibiliCollector, CNBlogsCollector, CSDNCollector,
                              InfoQCollector, ITHomeCollector, JuejinCollector,
                              OSChinaCollector, QbitaiCollector, RSSCollector,
                              SegmentFaultCollector, ShaoshupaiCollector,
                              StackOverflowCollector)

# 每个来源的"该采什么"一句话说明 —— 论文的数据来源表直接用它
SOURCE_NOTES: Dict[str, str] = {
    "GitHub": "Issues 搜索，天然是「有人在描述具体问题」，机会密度最高",
    "V2EX": "节点话题与回复，真实从业者吐槽与求助",
    "Stack Overflow": "技术问题，偏开发侧需求",
    "少数派": "效率工具评测与求助，偏 C 端需求",
    "掘金": "开发者实践文章，偏 B 端工具需求",
    "机器之心": "AI 资讯，多数不能构成机会（用于验证「排除情形」规则）",
    "36氪": "商业资讯，用于补充商业信号",
    "Product Hunt": "新产品发布，用于识别已有竞品",
    "Kaggle": "数据集与竞赛，用于识别数据侧需求",
    "哔哩哔哩": "视频标题与评论，反爬较重，低频使用",
}


class GitHubCollector(BaseCollector):
    """GitHub Issues 搜索：官方 REST API。

    未认证调用限速 10 次/分钟，超出返回 403。这里做两件事：
      1. 两次请求之间至少间隔 `github_interval` 秒（默认 6.5s，即 ~9 次/分钟）；
      2. 撞上限流就按 X-RateLimit-Reset 睡到重置再重试一次，不丢数据。
    论文「采集纪律」一节可写：遵守平台限速，不做并发压测。
    """

    source_name = "GitHub"
    home_url = "https://github.com"

    def _pace(self) -> None:
        import time as _t
        gap = float(self.cfg["collect"].get("github_interval", 6.5))
        last = getattr(self, "_last_gh", 0.0)
        wait = gap - (_t.time() - last)
        if wait > 0:
            _t.sleep(wait)
        self._last_gh = _t.time()

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        import time as _t

        out: List[Record] = []
        per_page = min(limit, 50)
        since = self.cfg["collect"].get("since", "2024-01-01")
        url = ("https://api.github.com/search/issues"
               f"?q={keyword} is:issue created:>{since}&sort=created&order=desc"
               f"&per_page={per_page}")

        resp = None
        for attempt in range(2):
            self._pace()
            try:
                resp = self.get(url, headers={"Accept": "application/vnd.github+json"})
                break
            except Exception as exc:
                msg = str(exc)
                if "403" not in msg or attempt == 1:
                    raise
                # 睡到配额重置（最多 90 秒，避免卡死）
                reset = 0
                try:
                    reset = int(getattr(exc, "response", None).headers.get("X-RateLimit-Reset", 0))
                except Exception:
                    reset = 0
                wait = min(max(reset - int(_t.time()) + 2, 20), 90)
                print(f"[GitHub] 触发限流，等待 {wait}s 后重试…")
                _t.sleep(wait)

        for item in resp.json().get("items", [])[:limit]:
            out.append(Record(
                source=self.source_name,
                url=item.get("html_url", ""),
                title=item.get("title", ""),
                content=item.get("body") or "",
                published_at=item.get("created_at", ""),
                heat={"评论": item.get("comments", 0)},
                source_category="开源项目与产品社区",
                batch=self.batch,
                collected_at=item.get("created_at", ""),
                extra={"labels": [l["name"] for l in item.get("labels", [])]},
            ))
        return out


class V2EXCollector(BaseCollector):
    """V2EX 公开 API：/api/topics/show.json 按节点拉取。"""

    source_name = "V2EX"
    home_url = "https://www.v2ex.com"

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        out: List[Record] = []
        node = keyword.strip() or "programmer"
        url = f"https://www.v2ex.com/api/topics/show.json?node_name={node}"
        resp = self.get(url)
        for item in resp.json()[:limit]:
            out.append(Record(
                source=self.source_name,
                url=item.get("url", ""),
                title=item.get("title", ""),
                content=item.get("content") or "",
                published_at=str(item.get("created", "")),
                heat={"回复": item.get("replies", 0)},
                source_category="问答与需求社区",
                batch=self.batch,
                collected_at="",
            ))
        return out


# 还没实现的源：保留占位，避免做到一半忘了结构
class TodoCollector(BaseCollector):
    source_name = "TODO"

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        raise NotImplementedError(
            f"「{self.source_name}」适配器还没写。参考 GitHubCollector 的实现，"
            "在 collectors/registry.py 里补一个子类并登记。")


REGISTRY: Dict[str, Type[BaseCollector]] = {
    # 实测可用（2026-11）——默认启用
    "GitHub": GitHubCollector,
    "掘金": JuejinCollector,
    "Stack Overflow": StackOverflowCollector,
    "少数派": ShaoshupaiCollector,
    "量子位": QbitaiCollector,          # 附件2
    "IT之家": ITHomeCollector,          # 附件2
    "InfoQ中国": InfoQCollector,        # 附件2
    "SegmentFault": SegmentFaultCollector,   # 清单外，V2EX 的问答类替代
    "博客园": CNBlogsCollector,         # 清单外，技术社区
    "开源中国": OSChinaCollector,       # 清单外，技术资讯
    "哔哩哔哩": BilibiliCollector,       # 附件2，视频社区（偏 C 端）
    "CSDN": CSDNCollector,              # 附件2，技术社区
    # 本机网络不可达 / 无 RSS：保留实现，默认不启用，用前先单独验证
    "V2EX": V2EXCollector,
}

# 当前默认启用的源（须与 config.yaml → tracks.*.sources 对应）
ENABLED_SOURCES: List[str] = [
    "GitHub", "掘金", "Stack Overflow", "少数派",
    "量子位", "IT之家", "InfoQ中国", "SegmentFault", "博客园",
    "哔哩哔哩",
]

# 已知不可用的源与原因（论文「数据来源」一节可直接引用，说明为什么没用）

# 已知不可用的源与原因 —— 结论来自 scripts/probe_sources.py 实测（2026-11-15）
# 报告见 reports/来源探测结果.md，论文「数据来源」一节可直接引用
SOURCE_STATUS: Dict[str, str] = {
    "V2EX": "不可达：DNS 正常但 80/443 全部连接超时（本机网络）",
    "36氪": "不可用：/feed 返回 SPA 页面，内部 API 返回 500",
    "机器之心": "不可用：/rss 返回 SPA 页面，/api/v4 返回 404",
    "CSDN": "合规禁止：so.csdn.net/robots.txt 为 Disallow: /，不采集",
    "Kaggle": "不可用：公开 API 需登录态，返回 SPA 页面",
    "天池": "不可用：接口返回 SPA 页面，无公开数据接口",
    "DataFountain": "不可用：接口返回空列表（需登录）",
    "数睿思": "不可用：门户为 SPA，无订阅入口",
    "阿里云开发者社区": "不可用：/rss 返回 404",
    "Papers with Code": "不可达：连接超时",
    "Semantic Scholar": "不可用：未认证请求被限流（429）",
    "Product Hunt": "不可用：GraphQL 需 OAuth 令牌",
    "哔哩哔哩": "已接入：公开搜索接口 + 匿名设备标识，低频、不取弹幕评论",
}

# 全部 20 个手册来源的实测结论：可采集 11 个（均已接入），其余 9 个不可用
PROBE_SUMMARY: Dict[str, int] = {"可采集": 11, "不可用": 9}
