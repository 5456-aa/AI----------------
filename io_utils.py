# -*- coding: utf-8 -*-
"""通用 IO：配置、JSONL、带 BOM 的 CSV、批次号、日志。"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml

ROOT = Path(__file__).resolve().parent

# Windows 控制台默认 GBK，中文/符号会抛 UnicodeEncodeError，这里强制 UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 配置（支持多赛道 / multi-track）
# ---------------------------------------------------------------------------
TRACKS = ("ecommerce", "education")

# 这些目录按赛道分开；cache 共用，避免同一 prompt 在两个赛道重复调 LLM
TRACK_SCOPED = ("raw", "clean", "out")


def seed_everything(seed: int = 42) -> None:
    """固定所有随机源，保证同一份输入跑出同一份结果。"""
    import os
    import random
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass


def load_config(path: str | os.PathLike | None = None,
                track: str | None = None) -> Dict[str, Any]:
    """读取配置。track 非空时，raw/clean/out 自动切到该赛道子目录。

    track=None 或 "all" 表示「合并赛道」：直接读写数据根目录下的出口，
    供最终提交使用。

    顺序：config.yaml → 再由本机 .env 里的 LLM_* 覆盖模型设置
    （这样换服务商/换 key 只动 .env，不动主配置，也不影响别人）。
    """
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    base: Dict[str, str] = {}
    for key, value in list(cfg.get("paths", {}).items()):
        p = Path(value)
        base[key] = str(p if p.is_absolute() else ROOT / p)

    cfg["base_paths"] = dict(base)
    cfg["paths"] = dict(base)
    cfg["_root"] = str(ROOT)
    cfg["track"] = track or "all"

    # 动态赛道：data/tracks/<slug>.json 里运行时新增的需求方向（用户发起）
    _load_dynamic_tracks(cfg)

    # 本机 .env 里的模型设置优先于 config.yaml —— 换服务商不用改主配置，
    # 也让"每个使用者填自己的 key"成为默认行为。
    _apply_local_llm_overrides(cfg)

    if track and track not in ("all",):
        for key in TRACK_SCOPED:
            cfg["paths"][key] = str(Path(base[key]) / track)
        cfg["_track_cfg"] = cfg.get("tracks", {}).get(track, {})
        # 赛道自己的需求方向 / 关键词 / 记录编号前缀
        proj = cfg.setdefault("project", {})
        tcfg = cfg["_track_cfg"] or {}
        if tcfg.get("demand_direction"):
            proj["demand_direction"] = tcfg["demand_direction"]
        if tcfg.get("keywords"):
            cfg["collect"]["keywords"] = tcfg["keywords"]
        if tcfg.get("record_prefix"):
            proj["record_prefix"] = tcfg["record_prefix"]
    else:
        m = cfg.get("merged") or {}
        if m.get("demand_direction"):
            cfg.setdefault("project", {})["demand_direction"] = m["demand_direction"]

    return cfg


def track_cfg(cfg: Dict[str, Any], track: str) -> Dict[str, Any]:
    """从一个基准配置派生出某赛道的配置（不重新读 yaml）。"""
    import copy

    out = copy.deepcopy(cfg)
    for key in TRACK_SCOPED:
        out["paths"][key] = str(Path(cfg["base_paths"][key]) / track)
    out["track"] = track
    tcfg = (cfg.get("tracks") or {}).get(track, {})
    out["_track_cfg"] = tcfg
    proj = out.setdefault("project", {})
    if tcfg.get("demand_direction"):
        proj["demand_direction"] = tcfg["demand_direction"]
    if tcfg.get("keywords"):
        out["collect"]["keywords"] = tcfg["keywords"]
    if tcfg.get("record_prefix"):
        proj["record_prefix"] = tcfg["record_prefix"]
    return out


def track_report_dir(cfg: Dict[str, Any], track: str | None = None) -> Path:
    """策划案/图表按赛道分目录，避免两边互相覆盖。"""
    base = Path(cfg["base_paths"]["reports"])
    return base / track if track and track != "all" else base


def ensure_dirs(cfg: Dict[str, Any]) -> None:
    for key in ("raw", "clean", "cache", "out", "logs", "figs", "reports"):
        Path(cfg["paths"][key]).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
def get_logger(cfg: Dict[str, Any], name: str = "pipeline") -> logging.Logger:
    track = cfg.get("track", "all")
    full = f"{track}.{name}"
    logger = logging.getLogger(full)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    log_file = Path(cfg["paths"]["logs"]) / f"{name}_{track}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


# ---------------------------------------------------------------------------
# JSONL
# ---------------------------------------------------------------------------
def read_jsonl(path: str | os.PathLike, strict: bool = False) -> List[Dict[str, Any]]:
    """读 JSONL。默认容错：跳过被截断/损坏的行，避免一行坏数据毁掉整条流水线。"""
    p = Path(path)
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    bad = 0
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
                if strict:
                    raise
    if bad:
        print(f"[警告] {p.name} 有 {bad} 行无法解析，已跳过")
    return rows


def write_jsonl(path: str | os.PathLike, rows: Iterable[Dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def append_jsonl(path: str | os.PathLike, row: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CSV：模板是 UTF-8 with BOM，保持 BOM，否则 Excel 打开乱码
# ---------------------------------------------------------------------------
def write_csv_bom(path: str | os.PathLike, columns: Sequence[str],
                  rows: Iterable[Dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns),
                                extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})
            n += 1
    return n


def read_csv_dicts(path: str | os.PathLike) -> List[Dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 其他小工具
# ---------------------------------------------------------------------------
def make_batch_id(cfg: Dict[str, Any], seq: int = 1,
                  when: datetime | None = None) -> str:
    """采集批次号：B + 日期 + 当日批次序号，如 B20261107-01。"""
    when = when or datetime.now()
    prefix = cfg.get("project", {}).get("batch_prefix", "B")
    return f"{prefix}{when:%Y%m%d}-{seq:02d}"


def short_hash(text: str, n: int = 8) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:n]


# ---------------------------------------------------------------------------
# 密钥读取：环境变量优先，其次项目根目录的 .env 文件
# ---------------------------------------------------------------------------
def load_dotenv(path: str | os.PathLike | None = None) -> Dict[str, str]:
    """极简 .env 解析（不引第三方库）。支持 KEY=VALUE、# 注释、引号。"""
    p = Path(path) if path else ROOT / ".env"
    out: Dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        out[k.strip()] = v
    return out


def get_secret(name: str, dotenv_path: str | os.PathLike | None = None):
    """返回 (值, 来源)。来源 ∈ {"env", "dotenv", ""}。"""
    val = os.environ.get(name, "")
    if val:
        return val, "env"
    val = load_dotenv(dotenv_path).get(name, "")
    if val:
        return val, "dotenv"
    return "", ""


def _load_dynamic_tracks(cfg: Dict[str, Any]) -> None:
    """把 data/tracks/*.json 合并进 cfg["tracks"]，支持用户随时新增需求方向。"""
    import json

    d = ROOT / "data" / "tracks"
    if not d.exists():
        return
    tracks = cfg.setdefault("tracks", {})
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = data.get("slug") or f.stem
        tracks.setdefault(slug, {})
        tracks[slug].update({k: v for k, v in data.items() if k != "slug"})


def create_track(direction: str, keywords: List[str], sources: List[str],
                 slug: str | None = None) -> Dict[str, Any]:
    """新建一个需求方向（一个批次），写入 data/tracks/<slug>.json。"""
    import hashlib
    import json
    import re

    if not slug:
        import hashlib
        ascii_part = re.sub(r"[^a-z0-9]+", "-", direction.lower()).strip("-")
        digest = hashlib.sha1(direction.encode("utf-8")).hexdigest()[:4]
        slug = (ascii_part or "track") + "-" + str(int(digest, 16) % 10000)

    payload = {
        "slug": slug,
        "label": direction,
        "demand_direction": direction,
        "record_prefix": "T" + hashlib.sha1(slug.encode("utf-8")).hexdigest()[:3].upper(),
        "keywords": keywords or [direction],
        "sources": sources or ["GitHub", "掘金", "Stack Overflow", "博客园"],
    }
    d = ROOT / "data" / "tracks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _apply_local_llm_overrides(cfg: Dict[str, Any]) -> None:
    """把 .env 里的 LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL / LLM_API_KEY 盖到配置上。"""
    d = load_dotenv(ROOT / ".env")
    if not d:
        return
    llm = cfg.setdefault("llm", {})
    if d.get("LLM_BASE_URL"):
        llm["base_url"] = d["LLM_BASE_URL"].strip()
    if d.get("LLM_MODEL"):
        llm["model"] = d["LLM_MODEL"].strip()
    if d.get("LLM_PROVIDER"):
        llm["provider"] = d["LLM_PROVIDER"].strip()
    # 统一用 LLM_API_KEY 作为入口；具体服务商的变量名由 LLMClient 再兜底
    if d.get("LLM_API_KEY"):
        llm["api_key_env"] = "LLM_API_KEY"


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def to_jsonable(obj: Any) -> Any:
    """numpy / Path 等类型转成可 json 序列化的形式。"""
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return str(obj)
