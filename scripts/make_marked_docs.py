# -*- coding: utf-8 -*-
"""生成「待核对 / 待改写」标红版 Word，供队员直接改。

红字 = 必须由你们亲自处理（核对页码、用自己的话重写），不是可以直接用的成品。

用法：python scripts/make_marked_docs.py
产出：docs/论文引用核对与改写清单.docx
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

RED = RGBColor(0xC0, 0x00, 0x00)
GREY = RGBColor(0x60, 0x60, 0x60)

# ---------------------------------------------------------------------------
# 1. 文献核对清单：(序号, 文献简称, 红字待核对字段, 核对建议)
# ---------------------------------------------------------------------------
REFS = [
    ("[1]", "Charikar. Similarity estimation techniques… STOC 2002",
     "页码 380-388", "ACM DL 查 STOC 2002 proceedings 页码"),
    ("[2]", "Broder. On the resemblance and containment… 1997",
     "页码 21-29", "IEEE Xplore 查 Compression and Complexity of Sequences 1997"),
    ("[4]", "Reimers & Gurevych. Sentence-BERT. EMNLP 2019",
     "页码 3982-3992", "ACL Anthology 查 EMNLP-IJCNLP 2019"),
    ("[5]", "Xiao et al. C-Pack (BGE). SIGIR 2024",
     "页码 641-649", "ACM DL 查 SIGIR 2024；若查不到页码改用 arXiv:2309.07597"),
    ("[6]", "Campello et al. HDBSCAN. PAKDD 2013",
     "LNCS 7819 与页码 160-172", "Springer Link 查 PAKDD 2013 Part I"),
    ("[7]", "Rousseeuw. Silhouettes. 1987",
     "卷 20 页码 53-65", "ScienceDirect 查 J. Comput. Appl. Math."),
    ("[8]", "Davies & Bouldin. 1979",
     "卷期 PAMI-1(2) 页码 224-227", "IEEE Xplore 查 TPAMI 1979"),
    ("[9]", "Caliński & Harabasz. 1974",
     "卷 3(1) 页码 1-27", "Taylor & Francis 查 Communications in Statistics"),
    ("[12]", "郭显光. 熵值法及其在综合评价中的应用. 财贸研究 1994",
     "整条都要核（这条把握最低，可能卷期有误）",
     "知网检索「熵值法 综合评价」，若查不到就换成能查到的熵值法论文"),
    ("[13]", "Manning et al. Introduction to IR. CUP 2008",
     "出版年/版次", "出版社官网核对"),
    ("[14]", "Cohen. A coefficient of agreement. 1960",
     "卷 20(1) 页码 37-46", "SAGE 查 Educational and Psychological Measurement"),
    ("[15]", "Brown et al. Language models are few-shot learners. NeurIPS 2020",
     "页码 1877-1901", "NeurIPS proceedings 官网核对"),
    ("[16]", "Wei et al. Chain-of-thought. NeurIPS 2022",
     "页码 24824-24837", "NeurIPS proceedings 官网核对"),
    ("[17]", "Lewis et al. RAG. NeurIPS 2020",
     "页码 9459-9474", "NeurIPS proceedings 官网核对"),
    ("[18]", "DeepSeek-AI. DeepSeek-V3 technical report",
     "arXiv 编号 2412.19437", "arXiv 核对编号与年份"),
    ("[19]", "Pedregosa et al. Scikit-learn. JMLR 2011",
     "卷 12 页码 2825-2830", "JMLR 官网核对"),
    ("[21]-[24]", "竞赛章程 / 省厅通知 / 赛题 / 附件",
     "访问日期（引用格式要求 [EB/OL] 需注明引用日期）",
     "按 GB/T 7714 补「(2026-11-11)[2026-11-20]. 网址」"),
]

# ---------------------------------------------------------------------------
# 2. 必须用自己话重写的段落
# ---------------------------------------------------------------------------
REWRITE = [
    ("合规声明（data_sources.md 第五节）",
     "本文数据均来自公开可访问内容。采集严格遵守以下纪律：（1）不登录、不绕过验证码或反爬机制……",
     "这段是我按赛题要求拟的模板。必须按你们真实做法改写：实际用了哪些源、间隔多少秒、"
     "有没有做脱敏、快照存在哪。写你们真做过的事，不要照抄。"),
    ("多语言处理说明（data_sources.md 第四节）",
     "针对英文来源，本文采用大模型翻译后再参与建模，以避免语言过滤导致来源多样性下降……",
     "改写要点：① 说明触发条件（中文占比阈值）；② 说明原文如何保留；"
     "③ 如实写「翻译会不会引入偏差」，不要只说好处。"),
    ("方法描述（论文第 3~6 章所有方法段）",
     "如「本文采用 SimHash 进行近似去重，汉明距离阈值取 3……」",
     "方法原理必须用自己的话重述，禁止整段翻译或复制参考文献原文。"
     "查重 >30% 取消资格，>50% 按学术不端处理。"),
    ("结果分析（论文各实验小节）",
     "如「如表 5 所示，轮廓系数为 0.13，说明聚类效果良好」",
     "必须结合你们的真实数字解释「为什么是这个结果」，包括效果不好的地方。"
     "评委评析里专门提到：误差要如实报告，藏起来反而扣分。"),
    ("AI 使用报告（单独提交）",
     "工具名称与版本、使用目的、交互记录、采纳与人工修改",
     "必须逐项写实：用了哪个模型、哪几处用了、哪些结论是你们自己下的。"
     "赛题要求「明确标注工具名称与版本、使用目的」，隐瞒属违规。"),
]

# ---------------------------------------------------------------------------
# 3. 红线
# ---------------------------------------------------------------------------
REDLINES = [
    "论文、代码注释、截图、终端路径中不得出现队号、学校、学院、姓名、指导教师——否则作品无效。",
    "知网/万方查重：重复率 >30% 取消参赛资格，>50% 按学术不端处理。",
    "不得用 AI 直接生成完整论文并作为原创提交；不得伪造数据与研究过程。",
    "四份 CSV 的表头必须与模板逐字一致（含全角括号），编码 UTF-8 with BOM。",
    "论文正文不超过 30 页（含图表，不含附录）。",
    "提交截止 2026-11-20 18:00，逾期不予受理。",
]


def _red(doc: Document, text: str, size: float = 10.5, bold: bool = False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.color.rgb = RED
    r.font.size = Pt(size)
    r.bold = bold
    return p


def build() -> Path:
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(10.5)

    h = doc.add_heading("论文引用核对与改写清单（红字部分必须由队员处理）", level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER

    _red(doc, "说明：本文件中所有红色文字都是「必须你们亲自处理」的内容——"
              "需要上知网/ACM/NeurIPS 核对的页码，以及必须用自己话重写的段落。"
              "黑色文字是可直接使用的框架。", size=10.5, bold=True)

    # ---- 一 ----
    doc.add_heading("一、参考文献核对表（红字=必须核对，核对不通过就替换）", level=1)
    doc.add_paragraph("核对标准：作者、题名、出处、年份、卷(期)、页码六项齐全，"
                      "格式遵守 GB/T 7714—2015。查不到的条目直接换一篇能查到的。")

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, t in enumerate(["序号", "文献", "需核对的字段", "核对方式"]):
        hdr[i].text = ""
        r = hdr[i].paragraphs[0].add_run(t)
        r.bold = True

    for num, ref, fields, how in REFS:
        cells = table.add_row().cells
        cells[0].text = num
        cells[1].text = ref
        cells[2].text = ""
        rr = cells[2].paragraphs[0].add_run(fields)
        rr.font.color.rgb = RED
        cells[3].text = how

    doc.add_paragraph("")
    _red(doc, "特别提示：[12] 郭显光那篇把握最低，请优先核对；若知网查不到，"
              "建议换成你们能检索到的熵值法论文（如《统计与决策》上的综述），序号不变。")

    # ---- 二 ----
    doc.add_heading("二、必须用自己话重写的段落", level=1)
    doc.add_paragraph("下表列出的是我拟的「素材稿」，只能当骨架。"
                      "红色部分 = 必须重写或必须写实的地方。")

    for i, (title, original, advice) in enumerate(REWRITE, 1):
        p = doc.add_paragraph()
        r = p.add_run(f"{i}. {title}")
        r.bold = True

        q = doc.add_paragraph()
        q.paragraph_format.left_indent = Pt(18)
        rq = q.add_run("现状（素材稿）：" + original[:80] + "……")
        rq.font.color.rgb = GREY
        rq.italic = True

        a = doc.add_paragraph()
        a.paragraph_format.left_indent = Pt(18)
        ra = a.add_run("【必须处理】" + advice)
        ra.font.color.rgb = RED

    # ---- 三 ----
    doc.add_heading("三、红线清单（任一违反即出局）", level=1)
    for line in REDLINES:
        p = doc.add_paragraph(style="List Bullet")
        r = p.add_run(line)
        r.font.color.rgb = RED

    # ---- 四 ----
    doc.add_heading("四、可直接使用的部分（黑色，不用改）", level=1)
    for t in [
        "数据来源表（reports/data_audit.md 第四节）——条数由脚本真实统计，可直接进论文表 2-1。",
        "分来源处理明细（同文件第二节）——采集/保留/剔除/缺失，是「数据预处理完整性」的证据。",
        "检索式表（docs/data_sources.md 第三节）——与 config.yaml 一致，改配置要同步改表。",
        "四份 CSV 的表头与字段定义（schema.py）——与模板逐字一致，不要改。",
    ]:
        doc.add_paragraph(t, style="List Bullet")

    out = ROOT / "docs" / "论文引用核对与改写清单.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


if __name__ == "__main__":
    path = build()
    print(f"生成 -> {path}")
