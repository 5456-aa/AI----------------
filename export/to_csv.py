# -*- coding: utf-8 -*-
"""导出四个结果 CSV（UTF-8 with BOM，表头逐字对齐模板）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from io_utils import get_logger, write_csv_bom
from pipeline.clean import redact_secrets
from schema import RESULT1_COLS, RESULT2_COLS, RESULT3_COLS, RESULT4_COLS


def export_result1(cfg: Dict[str, Any], records: List[Dict[str, Any]]) -> Path:
    rows = [{
        "采集批次号": r.get("batch", ""),
        "记录编号": r.get("record_id", ""),
        "来源网站名称": r.get("source", ""),
        "来源链接": r.get("url", ""),
        "内容": r.get("clean_text", ""),
        "发布时间": r.get("published_at", "未知"),
        "热度指标（如浏览数、点赞数、讨论数等）": r.get("heat_str", "无"),
    } for r in records]
    for row in rows:
        for k, v in row.items():
            if isinstance(v, str):
                row[k] = redact_secrets(v)
    path = Path(cfg["paths"]["out"]) / "result1.csv"
    n = write_csv_bom(path, RESULT1_COLS, rows)
    get_logger(cfg, "export").info("result1.csv：%d 行", n)
    return path


def export_result2(cfg: Dict[str, Any], records: List[Dict[str, Any]]) -> Path:
    rows = [{
        "采集批次号": r.get("batch", ""),
        "记录编号": r.get("record_id", ""),
        "是否构成机会": int(r.get("is_opportunity", 0)),
        "机会置信度": f"{float(r.get('confidence', 0)):.4f}",
        "功能类别": r.get("func_category", "") if r.get("is_opportunity") == 1 else "",
        "所属行业": r.get("industry", "") if r.get("is_opportunity") == 1 else "",
    } for r in records]
    path = Path(cfg["paths"]["out"]) / "result2.csv"
    n = write_csv_bom(path, RESULT2_COLS, rows)
    get_logger(cfg, "export").info("result2.csv：%d 行（机会 %d 条）",
                                   n, sum(r["是否构成机会"] for r in rows))
    return path


def export_result3(cfg: Dict[str, Any], clusters: List[Dict[str, Any]],
                   batch: str) -> Path:
    rows = [{
        "采集批次号": batch,
        "主题簇编号": c["cluster_id"],
        "主题簇名称": c["topic_name"],
        "功能类别": c["func_category"],
        "所属行业": c["industry"],
        "簇内机会记录数": c["n_records"],
        "来源覆盖": "、".join(c["sources"]),
        "簇内机会记录": ";".join(c["record_ids"]),
    } for c in clusters]
    path = Path(cfg["paths"]["out"]) / "result3.csv"
    n = write_csv_bom(path, RESULT3_COLS, rows)
    get_logger(cfg, "export").info("result3.csv：%d 个主题簇", n)
    return path


def export_result4(cfg: Dict[str, Any], clusters: List[Dict[str, Any]],
                   batch: str) -> Path:
    rows = [{
        "采集批次号": batch,
        "主题簇编号": c["cluster_id"],
        "主题簇名称": c["topic_name"],
        "功能类别": c["func_category"],
        "所属行业": c["industry"],
        "机会价值分": f"{float(c['value_score']):.1f}",
        "优先级": int(c["priority"]),
    } for c in sorted(clusters, key=lambda x: x["priority"])]
    path = Path(cfg["paths"]["out"]) / "result4.csv"
    n = write_csv_bom(path, RESULT4_COLS, rows)
    get_logger(cfg, "export").info("result4.csv：%d 行", n)
    return path
