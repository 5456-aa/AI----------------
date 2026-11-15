# -*- coding: utf-8 -*-
"""三个真正可用的采集适配器（2026-11 实测）：

  * JuejinCollector      掘金搜索 API（中文，可按关键词检索）—— 主力中文源
  * StackOverflowCollector  Stack Exchange 官方 API（英文，需求描述密度高）
  * RSSCollector         通用 RSS（少数派等），按关键词过滤

V2EX / 36氪 / 机器之心 在本机网络下不可用（超时或无 RSS），
保留在 registry 里但默认不启用；启用前先跑 `python run_collect.py --source <名>` 验证。
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from collectors.base import BaseCollector, Record

CST = timezone(__import__("datetime").timedelta(hours=8))
RE_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return html.unescape(RE_TAG.sub(" ", text or "")).strip()


# ---------------------------------------------------------------------------
# 掘金
# ---------------------------------------------------------------------------
class JuejinCollector(BaseCollector):
    """掘金站内搜索（公开接口，POST）。返回文章标题+摘要+互动数。"""

    source_name = "掘金"
    home_url = "https://juejin.cn"
    API = "https://api.juejin.cn/search_api/v1/search"

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        out: List[Record] = []
        body = {"key_word": keyword, "id_type": 0, "cursor": "0",
                "limit": min(limit, 20), "search_type": 0, "sort_type": 0}
        resp = self.post(self.API, body,
                         headers={"Content-Type": "application/json",
                                  "Origin": "https://juejin.cn",
                                  "Referer": "https://juejin.cn/"})
        data = resp.json().get("data") or []

        for item in data:
            model = item.get("result_model") or {}
            info = model.get("article_info") or {}
            aid = info.get("article_id") or model.get("article_id")
            if not aid:
                continue
            ctime = info.get("ctime")
            ts = ""
            if ctime:
                try:
                    ts = datetime.fromtimestamp(float(ctime), CST).isoformat()
                except (TypeError, ValueError):
                    ts = ""
            out.append(Record(
                source=self.source_name,
                url=f"https://juejin.cn/post/{aid}",
                title=(info.get("title") or "").strip(),
                content=_strip_html(info.get("brief_content") or ""),
                published_at=ts,
                heat={"浏览": int(info.get("view_count") or 0),
                      "点赞": int(info.get("digg_count") or 0),
                      "评论": int(info.get("comment_count") or 0)},
                source_category="技术内容与教程社区",
                batch=self.batch,
                collected_at=datetime.now(CST).isoformat(timespec="seconds"),
                extra={"keyword": keyword, "tags": model.get("tags") or []},
            ))
        return out[:limit]


# ---------------------------------------------------------------------------
# Stack Overflow
# ---------------------------------------------------------------------------
class StackOverflowCollector(BaseCollector):
    """Stack Exchange 官方 API /2.3/search/advanced（含 body）。"""

    source_name = "Stack Overflow"
    home_url = "https://stackoverflow.com"
    API = "https://api.stackexchange.com/2.3/search/advanced"

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        out: List[Record] = []
        since = self.cfg["collect"].get("since", "2024-01-01")
        try:
            fromdate = int(datetime.strptime(since, "%Y-%m-%d").timestamp())
        except ValueError:
            fromdate = 1704067200
        params = {
            "order": "desc", "sort": "votes", "q": keyword,
            "site": "stackoverflow", "pagesize": min(limit, 30),
            "filter": "withbody", "fromdate": fromdate,
        }
        resp = self.get(self.API, params=params)
        for item in resp.json().get("items", [])[:limit]:
            out.append(Record(
                source=self.source_name,
                url=item.get("link", ""),
                title=_strip_html(item.get("title", "")),
                content=_strip_html(item.get("body", ""))[:4000],
                published_at=datetime.fromtimestamp(
                    int(item.get("creation_date", 0)), CST).isoformat(),
                heat={"投票": int(item.get("score", 0)),
                      "回答": int(item.get("answer_count", 0))},
                source_category="问答与需求社区",
                batch=self.batch,
                collected_at=datetime.now(CST).isoformat(timespec="seconds"),
                extra={"keyword": keyword, "tags": item.get("tags") or []},
            ))
        return out


# ---------------------------------------------------------------------------
# 通用 RSS
# ---------------------------------------------------------------------------
class RSSCollector(BaseCollector):
    """通用 RSS 采集：按关键词切词命中过滤（RSS 没有检索能力）。"""

    source_name = "RSS"
    home_url = ""
    feed_url = ""
    category = ""

    def __init__(self, cfg: Dict[str, Any], batch: str = ""):
        super().__init__(cfg, batch)
        meta = (cfg.get("collect", {}).get("rss") or {}).get(self.source_name, {})
        self.feed_url = meta.get("feed", self.feed_url)
        self.category = meta.get("category", self.category)
        self.min_hits = int(meta.get("min_token_hits", 1))
        self._entries_cache: Dict[str, list] = {}

    @staticmethod
    def _tokens(keyword: str) -> List[str]:
        parts = re.split(r"[\s,，、/]+", keyword)
        return [p for p in parts if len(p) >= 2]

    def _hit(self, text: str, keyword: str) -> int:
        low = text.lower()
        toks = self._tokens(keyword)
        if not toks:            # 关键词只有一个短词时直接包含判断
            return 1 if keyword.lower() in low else 0
        return sum(1 for t in toks if t.lower() in low)

    def _entries(self):
        """同一次采集里只拉一次 feed（SegmentFault 这类慢站尤其重要）。"""
        if "items" in self._entries_cache:
            return self._entries_cache["items"]
        entries = []
        for attempt in range(2):
            try:
                resp = self.get(self.feed_url)
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.content)
                ns = {"a": "http://www.w3.org/2005/Atom"}
                is_atom = root.tag.endswith("feed")
                entries = list(root.findall("a:entry", ns) if is_atom
                               else root.iter("item"))
                break
            except Exception:
                if attempt == 1:
                    raise
        self._entries_cache = {"items": entries, "atom": root.tag.endswith("feed")}
        return entries

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        out: List[Record] = []
        if not self.feed_url:
            raise RuntimeError(f"{self.source_name} 未配置 RSS 地址")
        resp = None
        entries = self._entries()
        ns = {"a": "http://www.w3.org/2005/Atom"}
        is_atom = self._entries_cache.get("atom", False)

        for item in entries:
            title = (item.findtext("a:title", default="", namespaces=ns) if is_atom
                     else item.findtext("title") or "").strip()
            if is_atom:
                desc = _strip_html(item.findtext("a:summary", default="", namespaces=ns)
                                   or item.findtext("a:content", default="", namespaces=ns) or "")
                link_el = item.find("a:link", ns)
                link = (link_el.get("href") if link_el is not None else "") or ""
                published = (item.findtext("a:published", default="", namespaces=ns)
                             or item.findtext("a:updated", default="", namespaces=ns) or "")
            else:
                desc = _strip_html(item.findtext("description") or "")
                link = (item.findtext("link") or "").strip()
                published = (item.findtext("pubDate") or "").strip()

            if self._hit(f"{title} {desc}", keyword) < self.min_hits:
                continue
            out.append(Record(
                source=self.source_name,
                url=link,
                title=title,
                content=desc,
                published_at=published,
                heat={},
                source_category=self.category,
                batch=self.batch,
                collected_at=datetime.now(CST).isoformat(timespec="seconds"),
                extra={"keyword": keyword},
            ))
        return out[:limit]


class ShaoshupaiCollector(RSSCollector):
    source_name = "少数派"
    home_url = "https://sspai.com"
    feed_url = "https://sspai.com/feed"
    category = "技术内容与教程社区"


class QbitaiCollector(RSSCollector):
    """量子位（附件2 源，AI 垂直资讯）。"""
    source_name = "量子位"
    home_url = "https://www.qbitai.com"
    feed_url = "https://www.qbitai.com/feed"
    category = "科技与AI垂直资讯"


class ITHomeCollector(RSSCollector):
    """IT之家（附件2 源，科技资讯，量大）。"""
    source_name = "IT之家"
    home_url = "https://www.ithome.com"
    feed_url = "https://www.ithome.com/rss/"
    category = "科技与AI垂直资讯"


class InfoQCollector(RSSCollector):
    """InfoQ 中国（附件2 源，技术内容）。"""
    source_name = "InfoQ中国"
    home_url = "https://www.infoq.cn"
    feed_url = "https://www.infoq.cn/feed"
    category = "技术内容与教程社区"


class SegmentFaultCollector(RSSCollector):
    """SegmentFault（问答社区，V2EX 的替代源；Atom 格式）。"""
    source_name = "SegmentFault"
    home_url = "https://segmentfault.com"
    feed_url = "https://segmentfault.com/feeds"
    category = "问答与需求社区"


class CNBlogsCollector(RSSCollector):
    """博客园（技术社区，Atom 格式）。"""
    source_name = "博客园"
    home_url = "https://www.cnblogs.com"
    feed_url = "https://www.cnblogs.com/rss"
    category = "技术内容与教程社区"


class OSChinaCollector(RSSCollector):
    """开源中国（技术资讯，清单外补充源）。"""
    source_name = "开源中国"
    home_url = "https://www.oschina.net"
    feed_url = "https://www.oschina.net/news/rss"
    category = "技术内容与教程社区"


# ---------------------------------------------------------------------------
# 哔哩哔哩（视频与内容社区）—— 附件2 源，信号偏 C 端
# ---------------------------------------------------------------------------
class BilibiliCollector(BaseCollector):
    """B 站公开搜索接口：取视频标题 + 简介 + 播放/评论数。

    合规：只调用公开搜索接口，不登录、不取弹幕与评论正文，
    请求间隔由基类统一控制（默认 1.2s），低频使用。
    """

    source_name = "哔哩哔哩"
    home_url = "https://www.bilibili.com"
    API = "https://api.bilibili.com/x/web-interface/search/type"
    HEADERS = {
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    }

    def _ensure_visitor(self) -> None:
        """取一个匿名设备标识（buvid3）。没有它搜索接口会返回 412 风控。"""
        if getattr(self, "_visitor_ready", False):
            return
        try:
            r = self.session.get("https://api.bilibili.com/x/frontend/finger/spi",
                                 headers=self.HEADERS, timeout=10)
            b3 = (r.json().get("data") or {}).get("b_3")
            if b3:
                self.session.cookies.set("buvid3", b3, domain=".bilibili.com")
        except Exception:
            pass
        self._visitor_ready = True

    def _search_page(self, keyword: str, page: int):
        """带 412 重试：风控触发时重新取一次匿名标识再试。"""
        import time as _t

        self._ensure_visitor()
        for attempt in range(2):
            resp = self.get(self.API, params={
                "search_type": "video", "keyword": keyword, "page": page,
            }, headers=self.HEADERS)
            if resp.status_code == 412 and attempt == 0:
                self._visitor_ready = False
                _t.sleep(2)
                self._ensure_visitor()
                continue
            return resp
        return resp

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        out: List[Record] = []
        for page in (1, 2):
            if len(out) >= limit:
                break
            resp = self._search_page(keyword, page)
            data = (resp.json() or {}).get("data") or {}
            items = data.get("result") or []
            if not items:
                break
            for it in items:
                bvid = it.get("bvid") or ""
                if not bvid:
                    continue
                title = _strip_html(it.get("title") or "").replace("<em class=\"keyword\">", "")
                out.append(Record(
                    source=self.source_name,
                    url=f"https://www.bilibili.com/video/{bvid}",
                    title=title,
                    content=_strip_html(it.get("description") or ""),
                    published_at=datetime.fromtimestamp(
                        int(it.get("pubdate") or 0), CST).isoformat(),
                    heat={"播放": int(it.get("play") or 0),
                          "评论": int(it.get("video_review") or 0),
                          "收藏": int(it.get("favorites") or 0)},
                    source_category="视频与内容社区",
                    batch=self.batch,
                    collected_at=datetime.now(CST).isoformat(timespec="seconds"),
                    extra={"keyword": keyword, "tag": it.get("tag")},
                ))
        return out[:limit]


# ---------------------------------------------------------------------------
# CSDN（技术内容与教程社区）—— 附件2 源，站内搜索接口
# ---------------------------------------------------------------------------
class CSDNCollector(BaseCollector):
    """CSDN 站内搜索接口（公开）。取文章标题、摘要、浏览量。"""

    source_name = "CSDN"
    home_url = "https://www.csdn.net"
    API = "https://so.csdn.net/api/v3/search"

    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        out: List[Record] = []
        resp = self.get(self.API, params={"q": keyword, "t": "blog", "p": 1},
                        headers={"Referer": "https://so.csdn.net/"})
        data = resp.json() or {}
        items = data.get("result_vos") or data.get("data") or []
        if not isinstance(items, list):
            return out
        for it in items[:limit]:
            title = _strip_html(it.get("title") or "").replace("<em>", "").replace("</em>", "")
            url = it.get("url") or it.get("article_url") or ""
            out.append(Record(
                source=self.source_name,
                url=url,
                title=title,
                content=_strip_html(it.get("body") or it.get("description") or ""),
                published_at=str(it.get("create_time") or ""),
                heat={"浏览": int(it.get("view") or 0), "点赞": int(it.get("digg") or 0)},
                source_category="技术内容与教程社区",
                batch=self.batch,
                collected_at=datetime.now(CST).isoformat(timespec="seconds"),
                extra={"keyword": keyword},
            ))
        return out
