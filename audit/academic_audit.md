# 学术调研审计

审计日期：2026-08-31。审计范围为 `research/algorithms.md`、`research/domain-model.md` 和 `research/benchmarks.md` 中的论文 DOI、数据集语义、复杂度和能力断言。外部元数据通过 Crossref API 核对；数据集语义以 ESICUP `3d_rectangular/thpack/README.txt` 的本地快照为准。

## Findings

### 🔴 高（已修复）：THPACK1–7 的 Bischoff–Ratcliff DOI 错误

- 文件位置：`research/benchmarks.md:7`。
- 审计时当前值为 `10.1016/0305-0548(94)00066-3`；Crossref 对该 DOI 返回 Resource not found。当前正文已改为正确 DOI。
- 证据：ESICUP THPACK README 将来源列为 E.E. Bischoff and M.S.W. Ratcliff, “Issues in the development of approaches to container loading”, *Omega* 23(4), 377–390 (1995)；该论文的 Crossref 记录和 Springer 论文参考元数据给出 DOI `10.1016/0305-0483(95)00015-G`。
- 修复：替换为 <https://doi.org/10.1016/0305-0483(95)00015-G>，并保留访问日期/来源快照映射。该错误影响 THPACK1–7 的主要来源可审计性；正文已完成替换。

### 🟡 中（已修复）：THPACK 旋转标记的中文表述不精确

- 文件位置：`research/benchmarks.md:7`。
- 审计时当前值为“轴向尺寸旋转（每轴标记）”；当前正文已改为按竖直方向允许标记的描述。
- 证据：ESICUP README 说明每个尺寸后面的 0/1 表示“该尺寸是否允许作为竖直方向”（placement in the vertical orientation），并非三个空间轴各自独立开关。
- 修复建议：改为“每个尺寸作为竖直方向的允许标记；其余两边的水平互换遵循实例定义”，并保留指向原始 README 的引用。

### 🟢 低（已修复）：LAFF 性能句应限定为实验观察

- 文件位置：`research/algorithms.md:66`。
- 审计时当前值为“LAFF 等通常毫秒级”；当前正文已限定为本仓库 100 件 smoke test 的 12 ms 观察值。
- 证据：本仓库 100 件 smoke test 的 Skjolber LAFF 库内耗时约 12 ms；该数字不能证明所有硬件、规模和参数下的普遍性能。
- 修复建议：改成“在本仓库 100 件 smoke test 中库内约 12 ms；实际耗时随实例、JVM 和 deadline 变化”，或添加官方 benchmark 引用。

### 🟡 中（已修复）：CPLEX Python 包与 CP Optimizer 产品接口混写

- 文件位置：`research/algorithms.md:150`。
- 审计时表格把 `IBM CPLEX / cplex` 的类型和能力同时写成“商业 LP/MIP/CP Optimizer”与“CP Optimizer、Python、多平台”；当前正文已明确区分 IBM 产品族与 `cplex` 包。
- 证据：`cplex` PyPI 包是 CPLEX 数学规划 Python API；CP Optimizer 的 Python 建模接口通常是 `docplex.cp`，并依赖单独的 CP Optimizer 引擎/许可。它们属于 IBM 产品生态，但不是同一个 Python 模块。
- 修复建议：拆成 CPLEX MIP（`cplex`）与 CP Optimizer（`docplex.cp`）两项，或明确该行是 IBM 产品族而非单一可安装包；当前表格已采用后一种写法，避免高估 Python 后端的直接集成能力。

### 🟡 中（已修复）：Alonso 数据集来源未固定 commit

- 文件位置：`sources/manifest.csv` 的 S04、S05。
- 审计时当前值为 URL 和 `commit_or_version` 使用 ESICUP `main`，而 S01–S03 已固定到 commit `154a8f006a8e72f65d734f2d1e36777f678f31f8`；当前 manifest 已完成固定。
- 证据：该固定快照中同时存在 `3d_rectangular/alonso_2019/readme.txt` 与 `alonso_2020/readme.txt`。
- 修复建议：将 S04、S05 URL 和版本一并固定到 `154a8f006a8e72f65d734f2d1e36777f678f31f8`，避免上游 `main` 变动后来源语义无法重现；当前 manifest 已采用该修复。

### 🟡 中（已修复）：法规和标准引用未完整登记到来源 manifest

- 文件位置：`research/domain-model.md:669-697` 与 `sources/manifest.csv`。
- 审计时正文列出了 R3–R23 的法规、标准和工程指南 URL，但 manifest 主要登记论文、数据集和软件，未逐项登记这些引用的访问日期/版本；当前 manifest 已补齐对应条目。
- 影响：文档中的链接可供人工访问，但现有 verifier 无法对全部规范引用执行机器化的版本追踪；标准全文通常受许可限制，不能简单复制进仓库。
- 修复建议：至少为 R3–R23 增加 manifest 行，记录 `type`、URL、访问日期、法规/标准 revision 和“未做本地快照/受许可限制”说明；当前 manifest 已完成登记，并保留未快照状态。

### 🟢 低（已修复）：R6 的补充 CTU Code 通告需单独登记

- 文件位置：`research/domain-model.md:680` 与 `sources/manifest.csv`。
- 审计时 R6 同时引用 MSC.1/Circ.1497 和 MSC.1/Circ.1498；manifest 当时只登记 1497。当前 manifest 已新增 1498 条目 S54。
- 修复建议：新增一个 manifest 条目或在 S36 中明确列出两个 URL，避免来源清单遗漏补充材料；当前已采用新增 S54 条目的方式。

### 🟡 中（已修复）：算法论文表仍有 DOI 未进入来源 manifest

- 文件位置：`research/algorithms.md:463-525` 与 `sources/manifest.csv`。
- 审计时正文论文 DOI 均已逐项核验，但 manifest 只登记其中的代表性条目；当前 manifest 已新增 S55–S75，覆盖 Paquay、Fanslau、Pisinger（2002/2005）、TS2PACK、Zhao、Correia、Alvarez-Valdes、Nascimento、PackageCargo、Ramos、Pollaris、Junqueira multi-drop、Bonet、Egeblad、Lamas、Cano 等条目。
- 影响：人工点击正文 DOI 可以复核题名，但来源清单无法作为完整的机器化引用索引；这不影响 DOI 本身的解析正确性。
- 修复建议：发布前补齐对应 `paper` 行（DOI、访问日期、用途），或在 manifest 文档中明确声明其为代表性来源子集，并保留正文 DOI 作为完整引用入口；当前已采用补齐对应 `paper` 行的方式。

### 🟢 低（已修复）：Alonso 2020 出版年份存在 online/issue 差异

- 文件位置：`sources/manifest.csv` 的 S56。
- 证据：Crossref/Springer 元数据给出 online 2019；Springer 卷 18(1) 页面标注 article publication year 2020，ESICUP 数据集目录也将该条目命名为 `alonso_2020` 并按 2020 引用。
- 修复：S56 版本字段记录为 `2020 (online 2019)`，正文使用数据集目录的 2020 标识，避免把两个出版日期误当矛盾。

## 已核对且未发现错误的项目

- `research/algorithms.md` 论文表（Martello–Pisinger–Vigo、Fekete–Schepers–van der Veen、Nascimento 等、Paquay 等、Crainic 等、Fanslau–Bortfeldt、Pisinger、TS2PACK、Zhao 等、异构箱型、支撑/承压、轴荷、多站和连续旋转条目）的 DOI、题名和作者与 Crossref 记录一致。
- `research/domain-model.md` 的 R1、R2、R16 及 ASTM D642 DOI 均可解析，法规/标准 URL 可访问；正文明确指出法规版本、许可和工程签核边界，没有把几何可行性写成法规或强度证明。
- ESICUP README 明确：THPACK1–7 和 THPACK8 是单容器最大体积利用率问题；THPACK9 是装完全部货物并最小化容器数的多容器问题。`research/benchmarks.md:15`、`:32-34`、`:72-79` 保持了这一区分，并正确声明 instance 1 没有 published known optimum。
- Alonso 2019（DOI `10.1016/j.cie.2018.11.012`）摘要明确包含轴荷、重心、动态稳定和交付日期；Alonso 2020（DOI `10.1007/s10288-018-0397-z`）题名和摘要元数据支持 GRASP 与 practical constraints 的描述。
- 复杂度段落关于 3D 正交 BPP 强 NP-hard、Martello continuous lower-bound asymptotic ratio 1/8、pairwise 分离约束和启发式无最优保证的表述与相应论文/模型性质一致；这些是理论/模型边界，不是实验性能承诺。

## 复核命令与时间

```text
curl https://api.crossref.org/works/<doi>
curl https://api.semanticscholar.org/graph/v1/paper/DOI:<doi>?fields=title,abstract,year
sed -n '1,120p' .cache/esicup-datasets/3d_rectangular/thpack/README.txt
```

本文件记录的是审计发现；正文修复应在变更日志或提交说明中引用本文件。法规、标准和商业软件许可仍需按实际运输方式、司法辖区、版本和采购条款重新确认。
