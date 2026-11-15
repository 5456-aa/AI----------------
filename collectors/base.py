# -*- coding: utf-8 -*-
"""采集适配器基类：统一的礼貌访问、重试、原始快照落盘。

设计约束（写进论文的合规章节）：
  * 只访问公开页面 / 官方 API，不登录、不绕验证码；
  * 请求间隔 >= config.collect.request_interval_sec；
  * 遵守 robots.txt（respect_robots=true 时）；
  * 原始响应原样落盘到 data/raw/<source>/<ts>.json，保证可复现与可追溯。
"""
from __future__ import annotations

import json
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from io_utils import load_config


def stable_record_id(prefix: str, source: str, url: str, title: str,
                     taken: set[str] | None = None) -> str:
    """由内容生成稳定的记录编号（前缀 + 7 位数字）。

    为什么不用自增序号：采集脚本每次重跑都会重新编号，导致「同一编号指向不同记录」，
    标注集、阈值标定随之失效。改为「来源 + 链接 + 标题」的哈希，同一内容永远同一编号。

    taken 用于解决哈希碰撞：撞了就线性探测下一个数。
    """
    import hashlib

    taken = taken if taken is not None else set()
    basis = f"{(source or '').strip()}|{(url or '').strip()}|{(title or '').strip()}"
    # 7 位数字：空间 1000 万。原先 5 位（10 万）在千条量级下会碰撞，
    # 碰撞后靠线性探测分配，探测顺序随采集顺序变化 → 编号漂移。
    h = int(hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12], 16)
    n = h % 10000000
    for _ in range(10000000):
        rid = f"{prefix}{n:07d}"
        if rid not in taken:
            return rid
        n = (n + 1) % 10000000
    raise RuntimeError("记录编号空间已满")


@dataclass
class Record:
    """一条采集记录 —— 字段与 result1.csv 对齐。"""
    source: str                     # 附件2 规范名
    url: str
    title: str
    content: str
    published_at: str               # 原始值，清洗阶段再归一为 ISO8601
    heat: Dict[str, float] = field(default_factory=dict)
    source_category: str = ""
    record_id: str = ""
    batch: str = ""
    collected_at: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseCollector:
    source_name: str = ""           # 子类必须写成附件2 的规范名
    home_url: str = ""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, batch: str = ""):
        self.cfg = cfg or load_config()
        self.batch = batch
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.cfg["collect"]["user_agent"],
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self._last_request = 0.0
        self._robots: Optional[robotparser.RobotFileParser] = None
        self.raw_dir = Path(self.cfg["paths"]["raw"]) / (self.source_name or "unknown")
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- 合规 ----------------
    def _check_robots(self, url: str) -> bool:
        if not self.cfg["collect"].get("respect_robots", True):
            return True
        if self._robots is None:
            parsed = urlparse(url)
            self._robots = robotparser.RobotFileParser()
            self._robots.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
            try:
                self._robots.read()
            except Exception:
                # robots.txt 不可读时按“允许”处理，但只访问公开页面
                return True
        # 简化：直接看是否 Disallow: /
        try:
            return self._robots.can_fetch(self.cfg["collect"]["user_agent"], url)
        except Exception:
            return True

    def _throttle(self) -> None:
        gap = float(self.cfg["collect"].get("request_interval_sec", 1.2))
        wait = gap - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()

    def get(self, url: str, **kwargs) -> requests.Response:
        if not self._check_robots(url):
            raise PermissionError(f"robots.txt 禁止访问：{url}")
        self._throttle()
        resp = self.session.get(url, timeout=self.cfg["collect"].get("timeout_sec", 15), **kwargs)
        resp.raise_for_status()
        self._snapshot(url, resp)
        return resp

    def post(self, url: str, json_body: dict, **kwargs) -> requests.Response:
        """POST 接口（如掘金搜索）。同样走 robots 检查、限流与快照。"""
        if not self._check_robots(url):
            raise PermissionError(f"robots.txt 禁止访问：{url}")
        self._throttle()
        resp = self.session.post(url, json=json_body,
                                 timeout=self.cfg["collect"].get("timeout_sec", 15), **kwargs)
        resp.raise_for_status()
        self._snapshot(url, resp)
        return resp

    def _snapshot(self, url: str, resp: requests.Response) -> None:
        """原始响应落盘：这是“可溯源”的物理证据，论文里可以截图。"""
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        digest = abs(hash(url)) % 100000
        path = self.raw_dir / f"{ts}_{digest}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "url": url,
                "status": resp.status_code,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "content_type": resp.headers.get("Content-Type", ""),
                "body": resp.text[:200000],
            }, f, ensure_ascii=False)

    # ---------------- 子类实现 ----------------
    def search(self, keyword: str, limit: int = 50) -> List[Record]:
        """按关键词检索并返回规范化记录。子类必须实现。"""
        raise NotImplementedError
