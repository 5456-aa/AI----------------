# -*- coding: utf-8 -*-
"""翻译层：把英文（或其他语言）记录译成中文，让 GitHub / Kaggle 等来源可用。

设计（论文第 2 章要写清楚）：
1. **触发条件**：中文占比 < `translate.trigger_ratio` 才翻译，中文记录零成本。
2. **可溯源**：译文进 `clean_text`，原文完整保留在 `orig_title` / `orig_content` / `source_lang`，
   原始 URL 不动 —— 评委可逐条回原文核对。
3. **可复现**：所有翻译调用走 LLM 缓存（key 含模型名），重复跑不花第二次钱。
4. **降级**：没有 API key 时**不丢弃**记录，原样保留并标记 `translated=False`，
   配合 `clean.min_chinese_ratio = 0` 让英文记录也能进结果表（论文需说明）。
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from io_utils import get_logger
from llm.client import LLMClient, LLMUnavailable

RE_CJK = re.compile(r"[\u4e00-\u9fa5]")
RE_LATIN = re.compile(r"[A-Za-z]")

TRANSLATE_SYSTEM = """你是专业的技术文档翻译。把用户给的英文内容翻译成简体中文，要求：
1. 保留专业术语的准确性（如 RAG、embedding、ticket 等可保留英文或给出通行译名）；
2. 不要总结、不要增删信息、不要加解释；
3. 保持原文的语气（吐槽、求助、陈述都要如实保留）；
4. 只输出 JSON。"""

TRANSLATE_USER = """把下面这条来自「{source}」的记录翻译成简体中文。

标题：{title}
正文：{content}

只输出 JSON：
{{"title_zh": "中文标题", "content_zh": "中文正文", "lang": "原文语言代码，如 en"}}"""


def chinese_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(RE_CJK.findall(text)) / len(text)


def needs_translation(title: str, content: str, cfg: Dict[str, Any]) -> bool:
    """判断是否真的要翻译。

    只按中文占比判断会误伤中文标题，例如「精选项目 2026-11-02」中文占比只有 0.23，
    但它本来就是中文。所以再加两个条件：
      1. 必须有足够的英文字母（>= 20 个），否则无所谓翻译；
      2. 英文字母占比要够高（>= latin_min），才认定是外文内容。
    """
    tcfg = cfg.get("translate", {})
    if not tcfg.get("enabled", False):
        return False
    text = f"{title or ''}\n{content or ''}"
    if len(text.strip()) < 10:
        return False

    letters = len(RE_LATIN.findall(text))
    if letters < int(tcfg.get("min_latin_letters", 20)):
        return False
    latin_ratio = letters / max(len(text), 1)
    if latin_ratio < float(tcfg.get("latin_min", 0.25)):
        return False
    return chinese_ratio(text) < float(tcfg.get("trigger_ratio", 0.30))


def translate_one(rec: Dict[str, Any], client: LLMClient,
                  cfg: Dict[str, Any]) -> Dict[str, Any]:
    """返回补充了翻译字段的新记录（原始字段一律保留）。"""
    out = dict(rec)
    title = rec.get("title") or ""
    content = rec.get("content") or ""

    if not needs_translation(title, content, cfg):
        out.setdefault("source_lang", "zh")
        out.setdefault("translated", False)
        return out

    out["orig_title"] = title
    out["orig_content"] = content
    out["translated"] = False
    out["source_lang"] = "und"

    if not client.enabled:
        # 没有 LLM：保留原文，标记未翻译（配合放宽的中文占比阈值）
        return out

    try:
        data = client.chat_json(
            TRANSLATE_USER.format(source=rec.get("source", ""),
                                  title=title[:500], content=content[:3000]),
            system=TRANSLATE_SYSTEM)
    except LLMUnavailable:
        return out

    zh_title = str(data.get("title_zh") or "").strip()
    zh_content = str(data.get("content_zh") or "").strip()
    if zh_title or zh_content:
        out["title"] = zh_title or title
        out["content"] = zh_content or content
        out["translated"] = True
        out["source_lang"] = str(data.get("lang") or "en")
    return out


def run(cfg: Dict[str, Any], records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    log = get_logger(cfg, "translate")
    tcfg = cfg.get("translate", {})
    if not tcfg.get("enabled", False):
        return records

    client = LLMClient(cfg)
    candidates = [r for r in records if needs_translation(
        r.get("title") or "", r.get("content") or "", cfg)]
    log.info("需翻译 %d / %d 条（触发阈值 中文占比 < %.2f），LLM=%s",
             len(candidates), len(records), tcfg.get("trigger_ratio", 0.3),
             "可用" if client.enabled else "不可用（保留原文）")

    if not candidates:
        return records

    translated: Dict[str, Dict[str, Any]] = {}
    workers = max(1, int(tcfg.get("concurrency", 4))) if client.enabled else 1

    if workers == 1:
        for rec in candidates:
            translated[rec.get("record_id", "")] = translate_one(rec, client, cfg)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(translate_one, rec, client, cfg): rec
                       for rec in candidates}
            for fut in as_completed(futures):
                rec = futures[fut]
                try:
                    translated[rec.get("record_id", "")] = fut.result()
                except Exception as exc:
                    log.warning("翻译失败 %s：%s", rec.get("record_id"), exc)
                    translated[rec.get("record_id", "")] = rec

    n_ok = sum(1 for r in translated.values() if r.get("translated"))
    log.info("翻译完成 %d 条，未译（无 LLM 或失败）%d 条", n_ok, len(candidates) - n_ok)

    return [translated.get(r.get("record_id", ""), r) for r in records]
