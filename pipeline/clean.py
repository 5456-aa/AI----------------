# -*- coding: utf-8 -*-
"""任务一（中段）：文本清洗。

输入：data/raw/*.jsonl，每条记录形如
    {
      "source": "V2EX",              # 必须是附件2 的规范名
      "url": "https://...",
      "title": "...",
      "content": "...",
      "published_at": "2026-03-02T00:00:00+08:00",
      "heat": {"浏览": 2900, "点赞": 12},
      "collected_at": "...",
      "batch": "B20261107-01"
    }
输出：data/clean/records.jsonl，补充 clean_text / 清洗标记 / 是否丢弃。
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from io_utils import get_logger, read_jsonl, safe_div, write_jsonl
from pipeline import translate
from schema import SOURCE_NAMES

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------
RE_URL = re.compile(r"https?://\S+|www\.\S+")
RE_MENTION = re.compile(r"@[\w\-\u4e00-\u9fa5]{1,20}")
RE_TOPIC = re.compile(r"#([^#\n]{1,30})#")
RE_HTML_TAG = re.compile(r"<[^>]{1,200}>")
RE_SPACE = re.compile(r"[ \t\u3000]+")
RE_NEWLINES = re.compile(r"\n{3,}")
RE_REPEAT_PUNCT = re.compile(r"([!?！？。，,~～])\1{2,}")
RE_PHONE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
RE_EMAIL = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")
RE_IDCARD = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
RE_CJK = re.compile(r"[\u4e00-\u9fa5]")
RE_EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "]+"
)

# 繁简映射：完整方案建议用 opencc；这里用最小内置表兜底，避免额外依赖
_T2S = str.maketrans(
    "們個這說時會來後裡麼對開關點問題網頁記錄數據發現實際應該",
    "们个这说时会来后里么对开关点问题网页记录数据发现实际应该",
)


def html_to_text(raw: str) -> str:
    """HTML 实体还原 + 去标签。"""
    text = html.unescape(raw or "")
    text = RE_HTML_TAG.sub(" ", text)
    return text


def mask_pii(text: str) -> str:
    text = RE_PHONE.sub(lambda m: m.group(1)[:3] + "****" + m.group(1)[-4:], text)
    text = RE_EMAIL.sub("[邮箱]", text)
    text = RE_IDCARD.sub(lambda m: m.group(1)[:6] + "********" + m.group(1)[-4:], text)
    return text


_CJK_PUNCT = "，。！？：；、（）《》〈〉「」『』【】“”‘’…—～·"
_SPLIT_PUNCT = re.compile("([" + re.escape(_CJK_PUNCT) + "])")


def normalize(text: str) -> str:
    """NFKC 归一（全角数字/字母转半角），但**保留中文标点**。

    NFKC 会把「，。？！」也转成 ASCII，中文文本读起来会很怪，
    所以按标点切段，只对非标点部分做 NFKC。
    """
    parts = _SPLIT_PUNCT.split(text)
    out = []
    for i, part in enumerate(parts):
        out.append(part if i % 2 else unicodedata.normalize("NFKC", part))
    text = "".join(out)
    text = text.translate(_T2S)
    text = RE_SPACE.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text


def clean_text(raw: str, cfg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """返回 (清洗后文本, 统计标记)。"""
    c = cfg["clean"]
    stats: Dict[str, Any] = {}

    text = html_to_text(raw)
    stats["len_raw"] = len(text)

    if c.get("strip_urls", True):
        n_url = len(RE_URL.findall(text))
        text = RE_URL.sub(" ", text)
        stats["n_url"] = n_url
    if c.get("strip_mentions", True):
        text = RE_MENTION.sub(" ", text)
    text = RE_TOPIC.sub(r"\1", text)

    text = RE_EMOJI.sub(" ", text)
    if c.get("mask_pii", True):
        text = mask_pii(text)

    text = normalize(text)
    text = RE_REPEAT_PUNCT.sub(r"\1", text)
    text = RE_NEWLINES.sub("\n\n", text).strip()

    stats["len_clean"] = len(text)
    stats["chinese_ratio"] = round(safe_div(len(RE_CJK.findall(text)), max(len(text), 1)), 3)

    ad_hits = sum(1 for p in c.get("ad_patterns", []) if p in text)
    stats["ad_hits"] = ad_hits
    return text, stats


def is_valid(text: str, stats: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[bool, str]:
    c = cfg["clean"]
    if stats["len_clean"] < c.get("min_length", 15):
        return False, "too_short"
    if stats["chinese_ratio"] < c.get("min_chinese_ratio", 0.3):
        return False, "not_chinese"
    # 广告模板命中 2 条以上，视为营销内容
    if stats.get("ad_hits", 0) >= 2:
        return False, "ad_like"
    return True, ""


CST = timezone(timedelta(hours=8))   # 中文来源默认按北京时间解释


def normalize_time(value: str | None) -> str:
    """统一成 ISO8601（带时区）。无法解析时返回 '未知'，不编造时间。"""
    if not value:
        return "未知"
    txt = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                "%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(txt.replace("Z", "+0000") if fmt.endswith("%z") else txt, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CST)
            # 统一转成北京时间，避免同表里混着 +00:00 与 +08:00
            return dt.astimezone(CST).isoformat()
        except ValueError:
            continue
    # RSS/Atom 常见的 RFC822 格式，如 "Mon, 15 Nov 2026 10:00:00 +0800"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(txt)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CST)
            return dt.astimezone(CST).isoformat()
    except Exception:
        pass

    # 形如 1712345678 的时间戳
    if txt.isdigit() and len(txt) in (10, 13):
        ts = int(txt) / (1000 if len(txt) == 13 else 1)
        return datetime.fromtimestamp(ts, CST).astimezone(CST).isoformat()
    return "未知"


def heat_to_str(heat: Any) -> str:
    """热度指标统一成 '浏览:2900;点赞:12' 形式；无数据填 '无'（不要填 0）。"""
    if not heat:
        return "无"
    if isinstance(heat, dict):
        parts = [f"{k}:{int(v)}" for k, v in heat.items() if isinstance(v, (int, float))]
        return ";".join(parts) if parts else "无"
    if isinstance(heat, (int, float)):
        return f"热度:{int(heat)}"
    return str(heat)


def run(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    log = get_logger(cfg, "clean")
    raw_dir = cfg["paths"]["raw"]
    from pathlib import Path

    rows: List[Dict[str, Any]] = []
    files = sorted(Path(raw_dir).glob("*.jsonl"))
    if not files:
        log.warning("data/raw 下没有 *.jsonl，请先运行采集或放入原始数据")
    for f in files:
        rows.extend(read_jsonl(f))
    log.info("读入原始记录 %d 条，来自 %d 个文件", len(rows), len(files))

    # 翻译层：英文记录先译成中文，再做语言过滤（否则 GitHub/Kaggle 会被整源丢弃）
    rows = translate.run(cfg, rows)

    kept: List[Dict[str, Any]] = []
    drop_reason: Dict[str, int] = {}

    # 按来源的数据审计（对应评分标准第一条「数据预处理的完整性」）
    audit: Dict[str, Dict[str, Any]] = {}

    def _aud(src: str) -> Dict[str, Any]:
        return audit.setdefault(src or "未知", {
            "source": src or "未知", "raw": 0, "kept": 0, "dropped": 0,
            "drop_too_short": 0, "drop_not_chinese": 0, "drop_ad_like": 0,
            "missing_publish_time": 0, "missing_heat": 0, "missing_title": 0,
            "len_raw_sum": 0, "len_clean_sum": 0,
        })

    for rec in rows:
        source = rec.get("source", "")
        row_audit = _aud(source)
        row_audit["raw"] += 1
        if rec.get("translated"):
            row_audit["translated"] = row_audit.get("translated", 0) + 1
        if not str(rec.get("published_at") or "").strip():
            row_audit["missing_publish_time"] += 1
        if not rec.get("heat"):
            row_audit["missing_heat"] += 1
        if not str(rec.get("title") or "").strip():
            row_audit["missing_title"] += 1

        if source not in SOURCE_NAMES:
            # 不阻断，但必须留痕：来源名必须能在附件2 中找到
            log.warning("来源名不在附件2 清单内：%r（请改为规范名）", source)
        raw_body = (rec.get("title") or "") + "\n" + (rec.get("content") or "")
        text, stats = clean_text(raw_body, cfg)
        ok, reason = is_valid(text, stats, cfg)
        if not ok:
            drop_reason[reason] = drop_reason.get(reason, 0) + 1
            row_audit["dropped"] += 1
            row_audit[f"drop_{reason}"] = row_audit.get(f"drop_{reason}", 0) + 1
            continue

        row_audit["kept"] += 1
        row_audit["len_raw_sum"] += stats.get("len_raw", 0)
        row_audit["len_clean_sum"] += stats.get("len_clean", 0)

        kept.append({
            "batch": rec.get("batch", ""),
            "record_id": rec.get("record_id", ""),
            "source": source,
            "source_category": rec.get("source_category", ""),
            "url": rec.get("url", ""),
            "title": (rec.get("title") or "").strip(),
            "clean_text": text,
            "published_at": normalize_time(rec.get("published_at")),
            "heat": rec.get("heat") or {},
            "heat_str": heat_to_str(rec.get("heat")),
            "collected_at": rec.get("collected_at", ""),
            "clean_stats": stats,
            # 翻译溯源：原文与语言必须保留，评委可回原文核对
            "source_lang": rec.get("source_lang", "zh"),
            "translated": bool(rec.get("translated")),
            "orig_title": rec.get("orig_title", ""),
            "orig_content": rec.get("orig_content", ""),
        })

    out = f"{cfg['paths']['clean']}/records.jsonl"
    write_jsonl(out, kept)
    write_jsonl(f"{cfg['paths']['clean']}/audit_clean.jsonl",
                sorted(audit.values(), key=lambda x: -x["raw"]))
    log.info("清洗保留 %d 条，丢弃 %d 条，明细=%s -> %s",
             len(kept), len(rows) - len(kept), drop_reason, out)
    return kept
