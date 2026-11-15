# 参考文献（GB/T 7714—2015 格式）

> 🔴 **本文件里凡是标了「待核对」的字体，都必须你们上知网/ACM/NeurIPS 逐条核实后再进论文。**
> 可直接打印的标红版（真·红字）见 [`论文引用核对与改写清单.docx`](./论文引用核对与改写清单.docx)。
>
> 用法：论文正文按 `[1]`、`[2]` 顺序上标引用，文末按引用顺序列出。
> ⚠️ **提交前必做**：到知网/Google Scholar 逐条核对卷、期、页码（尤其是会议论文的页码）。
> ⚠️ **不要**整段复制这些文献的摘要或方法描述——赛后会查重，>30% 直接取消资格。

---

## 待核对字段一览（🔴 红字，逐条落实）

| 序号 | 必须核对的字段 | 去哪核 |
|---|---|---|
| [1] | 页码 380-388 | ACM DL（STOC 2002） |
| [2] | 页码 21-29 | IEEE Xplore（Sequences 1997） |
| [4] | 页码 3982-3992 | ACL Anthology（EMNLP-IJCNLP 2019） |
| [5] | 页码 641-649 | ACM DL（SIGIR 2024）；查不到就改引 arXiv:2309.07597 |
| [6] | LNCS 7819、页码 160-172 | Springer Link（PAKDD 2013） |
| [7] | 卷 20、页码 53-65 | ScienceDirect |
| [8] | PAMI-1(2)、页码 224-227 | IEEE Xplore |
| [9] | 卷 3(1)、页码 1-27 | Taylor & Francis |
| **[12]** | **整条（把握最低，优先核）** | 知网「熵值法 综合评价」；查不到就换一篇 |
| [14] | 卷 20(1)、页码 37-46 | SAGE |
| [15] | 页码 1877-1901 | NeurIPS 2020 proceedings |
| [16] | 页码 24824-24837 | NeurIPS 2022 proceedings |
| [17] | 页码 9459-9474 | NeurIPS 2020 proceedings |
| [18] | arXiv 编号 2412.19437 | arXiv |
| [19] | 卷 12、页码 2825-2830 | JMLR |
| [21]-[24] | 补「引用日期」`(2026-11-11)[2026-11-20]. 网址` | 按 GB/T 7714-2015 |

## 一、数据清洗与相似度（对应第 3 章）

[1] Charikar M S. Similarity estimation techniques from rounding algorithms[C]//Proceedings of the 34th Annual ACM Symposium on Theory of Computing. Montreal: ACM, 2002: 380-388.

[2] Broder A Z. On the resemblance and containment of documents[C]//Proceedings of the Compression and Complexity of Sequences. Salerno: IEEE, 1997: 21-29.

[3] 全国信息与文献标准化技术委员会. GB/T 7714—2015 信息与文献 参考文献著录规则[S]. 北京: 中国标准出版社, 2015.

## 二、文本表示与聚类（对应第 4、5 章）

[4] Reimers N, Gurevych I. Sentence-BERT: Sentence embeddings using Siamese BERT-networks[C]//Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing. Hong Kong: ACL, 2019: 3982-3992.

[5] Xiao S, Liu Z, Zhang P, et al. C-Pack: Packed resources for general Chinese embeddings[C]//Proceedings of the 47th International ACM SIGIR Conference. Washington DC: ACM, 2024: 641-649.

[6] Campello R J G B, Moulavi D, Sander J. Density-based clustering based on hierarchical density estimates[C]//Advances in Knowledge Discovery and Data Mining (PAKDD 2013), LNCS 7819. Berlin: Springer, 2013: 160-172.

[7] Rousseeuw P J. Silhouettes: a graphical aid to the interpretation and validation of cluster analysis[J]. Journal of Computational and Applied Mathematics, 1987, 20: 53-65.

[8] Davies D L, Bouldin D W. A cluster separation measure[J]. IEEE Transactions on Pattern Analysis and Machine Intelligence, 1979, PAMI-1(2): 224-227.

[9] Caliński T, Harabasz J. A dendrite method for cluster analysis[J]. Communications in Statistics, 1974, 3(1): 1-27.

## 三、综合评价与赋权（对应第 6 章）

[10] Shannon C E. A mathematical theory of communication[J]. Bell System Technical Journal, 1948, 27(3): 379-423.

[11] Saaty T L. The Analytic Hierarchy Process: Planning, Priority Setting, Resource Allocation[M]. New York: McGraw-Hill, 1980.

[12] 郭显光. 熵值法及其在综合评价中的应用[J]. 财贸研究, 1994(6): 56-60.

## 四、判别评价指标（对应第 4 章）

[13] Manning C D, Raghavan P, Schütze H. Introduction to Information Retrieval[M]. Cambridge: Cambridge University Press, 2008.

[14] Cohen J. A coefficient of agreement for nominal scales[J]. Educational and Psychological Measurement, 1960, 20(1): 37-46.

## 五、大模型与提示工程（对应第 4、7 章）

[15] Brown T B, Mann B, Ryder N, et al. Language models are few-shot learners[C]//Advances in Neural Information Processing Systems 33. 2020: 1877-1901.

[16] Wei J, Wang X, Schuurmans D, et al. Chain-of-thought prompting elicits reasoning in large language models[C]//Advances in Neural Information Processing Systems 35. 2022: 24824-24837.

[17] Lewis P, Perez E, Piktus A, et al. Retrieval-augmented generation for knowledge-intensive NLP tasks[C]//Advances in Neural Information Processing Systems 33. 2020: 9459-9474.

[18] DeepSeek-AI. DeepSeek-V3 technical report[R]. arXiv: 2412.19437, 2024.

## 六、工具与软件

[19] Pedregosa F, Varoquaux G, Gramfort A, et al. Scikit-learn: Machine learning in Python[J]. Journal of Machine Learning Research, 2011, 12: 2825-2830.

[20] Sun J. jieba: 中文分词组件[CP/OL]. (2020-01-01)[2026-11-20]. https://github.com/fxsjy/jieba.

## 七、竞赛文件与数据来源

[21] 泰迪杯数据挖掘挑战赛组织委员会. 泰迪杯数据挖掘挑战赛章程[EB/OL]. (2026-01-01)[2026-11-20]. https://www.tipdmcup.cn/sszx/2166.jhtml.

[22] 甘肃省教育厅. 关于公布 2026 年大学生学科专业竞赛项目的通知（甘教高函〔2026〕6 号）[Z]. 2026.

[23] 甘肃省第三届大学生数据挖掘挑战赛组委会. 本科组赛题：AI 应用场景的智能挖掘与机会评估系统[Z]. 2026.

[24] 甘肃省第三届大学生数据挖掘挑战赛组委会. 附件1 标签体系、附件2 数据来源清单[Z]. 2026.

---

## 附：正文引用位置对照表（照抄即可，省得漏引）

| 论文小节 | 该引哪几条 | 引用场景 |
|---|---|---|
| 2.1 数据来源 | [21][22][23][24] | 赛题与来源清单出处 |
| 3.2 去重 | [1][2] | SimHash / MinHash 原理 |
| 3.3 文本规范化 | [3] | 标准引用格式（如涉及） |
| 4.2 特征与判别 | [13][15][16] | P/R/F1、few-shot、结构化提示 |
| 4.4 阈值标定 | [13][14] | P-R 曲线、标注一致性 κ |
| 5.2 向量化 | [4][5] | SBERT / BGE 中文句向量 |
| 5.3 聚类 | [6][7][8][9] | HDBSCAN、轮廓系数、DB、CH |
| 6.2 权重 | [10][11][12] | 信息熵、AHP、熵值法中文出处 |
| 7.2 系统实现 | [19][20][18] | sklearn、jieba、所用大模型 |

> 说明：[12] 的卷期页码请在知网上核对；若格式要求更严格，可换成《统计与决策》等期刊上的熵值法综述。
