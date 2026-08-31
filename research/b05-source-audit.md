# B05 MPV 3D-BPP 来源审计

## 结论

Martello、Pisinger 与 Vigo 的论文 *The Three-Dimensional Bin Packing Problem*（Operations Research 48(2), 2000, DOI [10.1287/opre.48.2.256.12386](https://doi.org/10.1287/opre.48.2.256.12386)）确认了 B05 的问题定义：正交长方体物品、同型三维箱、全部装入、最少箱数；论文报告了最多 90 件的计算实验，并给出了 continuous lower bound 的理论性质。

论文引用和可执行输入不是同一件事。本审计固定检查了 PackingSolver fork `d953148b8f710c06fa6c410949b7272f9e36327b`、ESICUP 数据快照 `154a8f006a8e72f65d734f2d1e36777f678f31f8` 及本地目录：PackingSolver 的 `data/rectangle/martello1998` 是二维 `.2bp` 数据；其 `data/box` 和 `data/box_raw` 没有对应的三维 `martello1998` 目录；ESICUP 的固定三维快照也没有 MPV 命名的三维实例文件。因此目前没有同时具备实例内容、格式/姿态说明、来源身份和可复现许可的 MPV 三维输入归档。

机器可读证据见 [`results/comprehensive/b05-source-audit.json`](../results/comprehensive/b05-source-audit.json)，复现脚本见 [`benchmarks/comprehensive/audit_b05_source.py`](../benchmarks/comprehensive/audit_b05_source.py)。

## 协议决策

| 字段 | 固定值 | 原因 |
|---|---|---|
| `input_status` | `SOURCE_INCOMPLETE` | 只有论文和模型描述，没有可执行的公开三维实例归档 |
| `run_status` | `NOT_RUN` | 不能在输入身份未冻结时运行 |
| `termination_reason` | `SOURCE_PENDING` | 等待可核验实例、格式、姿态规则和许可 |
| 排行 | 禁止 | 没有共同输入，不能计算箱数或 gap |

以下替代均被禁止：把二维 `martello1998` 目录当成三维数据；把 THPACK9、BR/LN 或自行生成的实例改名为 MPV；用论文中的表格数字反推实例并宣称可复现。未来找到公开文件后，必须先新增文件哈希、姿态语义、许可证和独立 parser，再将 B05 状态从 `SOURCE_INCOMPLETE` 改为 `VALID`。

## 独立补充轨

这不意味着多箱能力不测。THPACK9（B04）继续作为公开同型多箱基线；小规模 exact-oracle（B06）用于真值校准。若要增加独立的现代公开数据，应以新的明确名称和独立审计加入，例如 Q4RealBPP（Mendeley Data DOI [10.17632/y258s6d939.2](https://doi.org/10.17632/y258s6d939.2)，12 个带重量/相容/相对位置/重心限制的合成实例）或 3DBPPsi（Science Data Bank DOI [10.57760/sciencedb.42066](https://doi.org/10.57760/sciencedb.42066)，异构车辆与可堆叠物品）。它们不是 MPV，应分别记录问题族和约束语义，不能覆盖 B05 的名称。
