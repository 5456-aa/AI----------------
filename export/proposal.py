# -*- coding: utf-8 -*-
"""任务五：立项策划案导出（Markdown + Word）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from llm import prompts
from llm.client import LLMClient, LLMUnavailable
from io_utils import get_logger


def build_proposal(cluster: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """优先用 LLM 生成正文，失败则用模板兜底（保证总能交出一份文档）。"""
    client = LLMClient(cfg)
    evidence = "\n".join(
        f"- [{r.get('source')}] {r.get('title') or r.get('clean_text', '')[:40]}（{r.get('record_id')}）"
        for r in cluster["records"][:8]
    )

    if client.enabled:
        try:
            data = client.chat_json(prompts.PROPOSAL_USER.format(
                topic_name=cluster["topic_name"],
                func_category=cluster["func_category"],
                industry=cluster["industry"],
                score=cluster["value_score"],
                rank=cluster["priority"],
                n=cluster["n_records"],
                sources="、".join(cluster["sources"]),
                evidence=evidence,
            ))
            if data.get("goal"):
                data.setdefault("subtasks", [])
                data.setdefault("risks", [])
                data.setdefault("kpis", [])
                data.setdefault("duration_weeks", 12)
                return data
        except LLMUnavailable:
            pass

    return {
        "goal": f"面向「{cluster['industry']}」场景，建设以{cluster['func_category']}为核心的"
                f"「{cluster['topic_name']}」能力，解决簇内 {cluster['n_records']} 条真实需求所指向的问题。",
        "tech_route": "1) 复用通用大模型 API 承担理解与生成；\n"
                      "2) 领域知识库 + 检索增强（RAG）保证答案可溯源；\n"
                      "3) 规则/小模型做前置过滤与成本控制；\n"
                      "4) 人工复核闭环持续补充 badcase。",
        "duration_weeks": 12,
        "subtasks": [
            {"name": "需求验证与访谈", "weeks": 2, "owner_role": "产品"},
            {"name": "数据与知识库建设", "weeks": 3, "owner_role": "数据工程"},
            {"name": "原型与模型接入", "weeks": 4, "owner_role": "算法/后端"},
            {"name": "小范围灰度与评估", "weeks": 2, "owner_role": "产品/测试"},
            {"name": "上线与运营迭代", "weeks": 1, "owner_role": "运营"},
        ],
        "risks": ["数据来源合规风险", "大模型输出幻觉", "冷启动阶段标注不足"],
        "kpis": ["任务完成率", "人工介入率", "单次调用成本"],
    }


def render_markdown(cluster: Dict[str, Any], proposal: Dict[str, Any],
                    cfg: Dict[str, Any]) -> str:
    dims = cluster.get("dim_scores", {})
    lines = [
        f"# 立项策划案：{cluster['topic_name']}",
        "",
        f"- **功能类别**：{cluster['func_category']}",
        f"- **所属行业**：{cluster['industry']}",
        f"- **簇机会价值分**：{cluster['value_score']}（全簇排名第 {cluster['priority']}）",
        f"- **机会记录数**：{cluster['n_records']} 条，覆盖 {cluster['n_sources']} 个来源",
        f"- **来源覆盖**：{'、'.join(cluster['sources'])}",
        "",
        "## 一、目标用户与核心痛点",
        f"**目标用户**：{cluster['industry']}领域的一线从业者与业务负责人"
        f"（对应功能类别「{cluster['func_category']}」）。",
        "",
        f"**核心痛点**：本簇 {cluster['n_records']} 条机会记录来自 "
        f"{cluster['n_sources']} 个来源（{'、'.join(cluster['sources'])}），"
        f"多条独立记录共同指向同一类问题，说明痛点真实且具有普遍性。"
        f"典型诉求见下方「依据来源」。",
        "",
        "## 二、目标功能",
        proposal.get("goal", ""),
        "",
        "## 三、技术路线",
        proposal.get("tech_route", ""),
        "",
        f"## 四、实施周期",
        f"共 {proposal.get('duration_weeks', 12)} 周。",
        "",
        "## 五、子任务分解",
        "",
        "| 子任务 | 周期（周） | 负责角色 |",
        "|---|---|---|",
    ]
    for st in proposal.get("subtasks", []):
        lines.append(f"| {st.get('name', '')} | {st.get('weeks', '')} | {st.get('owner_role', '')} |")

    lines += ["", "## 六、价值评分依据", "", "| 维度 | 得分（0~100） |", "|---|---|"]
    for k, v in dims.items():
        lines.append(f"| {k} | {v} |")

    lines += ["", "## 七、依据来源（可溯源）", ""]
    for r in cluster["records"]:
        lines.append(f"- `{r['record_id']}` [{r.get('source')}] "
                     f"{r.get('title') or r.get('clean_text', '')[:50]} —— {r.get('url', '')}")

    if proposal.get("risks"):
        lines += ["", "## 七、风险与对策", ""]
        lines += [f"- {x}" for x in proposal["risks"]]
    if proposal.get("kpis"):
        lines += ["", "## 八、衡量指标", ""]
        lines += [f"- {x}" for x in proposal["kpis"]]
    return "\n".join(lines)


def export_docx(md_text: str, path: Path, title: str) -> bool:
    """可选：装了 python-docx 就顺手导出 Word。"""
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError:
        return False

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(10.5)

    for line in md_text.splitlines():
        s = line.rstrip()
        if not s:
            doc.add_paragraph("")
        elif s.startswith("# "):
            doc.add_heading(s[2:], level=0)
        elif s.startswith("## "):
            doc.add_heading(s[3:], level=1)
        elif s.startswith("| "):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set("".join(cells)) <= set("- "):
                continue
            doc.add_paragraph(" | ".join(cells))
        elif s.startswith("- "):
            doc.add_paragraph(s[2:], style="List Bullet")
        else:
            doc.add_paragraph(s)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return True


def run(cfg: Dict[str, Any], scored: List[Dict[str, Any]], top_k: int = 3,
        out_dir: Path | None = None) -> List[Path]:
    log = get_logger(cfg, "proposal")
    out_dir = Path(out_dir) if out_dir else Path(cfg["paths"]["reports"])
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: List[Path] = []
    for cluster in sorted(scored, key=lambda c: c["priority"])[:top_k]:
        proposal = build_proposal(cluster, cfg)
        md = render_markdown(cluster, proposal, cfg)
        md_path = out_dir / f"proposal_{cluster['cluster_id']}.md"
        md_path.write_text(md, encoding="utf-8")
        paths.append(md_path)

        docx_path = out_dir / f"proposal_{cluster['cluster_id']}.docx"
        if export_docx(md, docx_path, cluster["topic_name"]):
            paths.append(docx_path)
        log.info("策划案：%s", md_path.name)
    return paths
