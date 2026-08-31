# 三维装箱求解器、约束模型与可视化技术选型

> 基准日 **2026-08-31** ｜ 能力矩阵实现 **11 个**（含 Rust `u-nesting` 未测试观察项）｜ 公共 THPACK9 对照 **4 个实现** ｜ 受控测试 **9 项机器断言全部通过** ｜ 统一公共实例 **70 件物品** ｜ 上游缺陷复现与 patch 验证 **2 条路径**

三维装箱软件面对的不是一个 `pack()` 函数，而是一组不同的优化问题：固定容器的 3D knapsack、同型容器的 3D bin packing、多箱型有成本与库存限制的 variable-sized BPP、带堆叠/承压/轴荷/多站卸货的运输装载，以及连续姿态的非正交装箱。本仓库把这些问题形式化，核对论文和官方文档，审计开源实现，接入 ESICUP 公共 benchmark，并用独立 validator 检查布局、数量、重量和证书。

**完整报告：[`report.md`](report.md)**

![ESICUP THPACK9 instance 1 箱数对照，虚线为体积下界 19](figures/fig01_thpack9_bins.png)

---

## 主要结论

| # | 结论 | 证据 |
|---|---|---|
| 1 | **推荐分层架构：CP-SAT/SCIP 负责成本与 exact-small，PackingSolver 负责正交布局，所有结果经过独立 validator。** | [`report.md`](report.md)、[`research/decision-matrices.md`](research/decision-matrices.md) |
| 2 | **PackingSolver 原版异构成本路径是上游缺陷，不是调用错误。** `box` 与 `boxstacks` 漏掉 `VariableSizedBinPacking` 的方案比较分支；本地最小 patch 两条路径均通过；issue [#536](https://github.com/fontanf/packingsolver/issues/536) 与 PR [#540](https://github.com/fontanf/packingsolver/pull/540) 仍在 open。 | [`research/packingsolver-upstream.md`](research/packingsolver-upstream.md) |
| 3 | **公共 THPACK9 instance 1：PackingSolver patch 25 箱、Skjolber 28 箱、py3dbp/Jerry 各 50 箱，均装下 70/70 件。** 数据文件没有 known optimum，因此只能报告 incumbent。 | [`research/benchmarks.md`](research/benchmarks.md)、`results/public/` |
| 4 | **py3dbp、Jerry 和 Go bp3d 不能承担业务真值。** py3dbp 顺序敏感，Jerry 的 `loadbear` 只是排序，Go bp3d 的 `MaxWeight` 没进入放置检查。 | [`research/algorithms.md`](research/algorithms.md)、代码审计和反例 |
| 5 | **桌面首选 Tauri 2 + React/TypeScript + Three.js + Python worker。** 大 placement 数据写入 job bundle，进度走版本化事件，3D 场景与表格按稳定 ID 联动。 | [`research/frontend.md`](research/frontend.md)、[`research/decision-matrices.md`](research/decision-matrices.md) |

## 已知限制与修正

本轮将四个可复现的 PackingSolver 问题提交为 [#536](https://github.com/fontanf/packingsolver/issues/536)、[#537](https://github.com/fontanf/packingsolver/issues/537)、[#538](https://github.com/fontanf/packingsolver/issues/538)、[#539](https://github.com/fontanf/packingsolver/issues/539)，对应修复 PR 为 [#540](https://github.com/fontanf/packingsolver/pull/540)、[#541](https://github.com/fontanf/packingsolver/pull/541)、[#542](https://github.com/fontanf/packingsolver/pull/542)、[#543](https://github.com/fontanf/packingsolver/pull/543)。截至 2026-08-31 均未合并，patch 二进制不能当作官方 release。用户维护的公开 fork [`HansBug/packingsolver@ac7b1384`](https://github.com/HansBug/packingsolver/tree/ac7b1384151bd33f56aec47d5c180dd4c5652266) 已整合四个修复，着急使用时可 pin 该 commit；学术 DOI、THPACK 语义、LAFF 性能措辞、CPLEX 接口归属和来源 commit 的修正记录在 [`audit/academic_audit.md`](audit/academic_audit.md)，实验边界和未测试项见 [`results/test-summary.md`](results/test-summary.md)。

## 目录

```text
report.md                         总报告：问题、模型、算法、benchmark、前端与路线
research/                         学术综述、能力矩阵、公共数据集、上游审计
benchmarks/                       受控脚本、统一数据转换器、独立 validator
results/                          机器可读结果与测试摘要
raw/                              原始结果快照（由 scripts/collect_raw.py 生成）
derived/                          统计表和 manifest 派生文件
figures/                          由 scripts/plot.py 生成的图
sources/                          URL、DOI、官方文档和关键逐字引文登记
audit/                            复现审计、学术审计、自审迭代日志
scripts/                          分析、绘图、manifest、verify、Markdown 门禁和全量复现入口
LICENSE / DATA-LICENSE.md         代码许可和外部数据许可边界
CITATION.cff                      GitHub “Cite this repository” 信息
references.bib                    主要论文与数据集的 BibTeX 条目
REVIEW.md / CLAUDE.md              发布门禁和写作/实验工作约定
```

审计入口：[`sources/manifest.csv`](sources/manifest.csv)（来源、版本、快照哈希）、[`sources/quotes.md`](sources/quotes.md)（关键逐字引文）、[`audit/claims.csv`](audit/claims.csv)（断言证据映射）、[`audit/reproducibility_audit.md`](audit/reproducibility_audit.md) 和 [`audit/academic_audit.md`](audit/academic_audit.md)。

## 复现

项目要求 Python 3.12。干净环境可按下面的步骤建立虚拟环境并安装测试依赖；仓库自带的 `raw/`、`derived/` 和 `figures/` 已足够执行离线校验，不需要下载求解器。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
```

离线重算和机器检查：

```bash
.venv/bin/python scripts/analyze.py
.venv/bin/python scripts/plot.py
.venv/bin/python scripts/verify.py
.venv/bin/python -m pytest -q
```

需要运行 Python/Jerry/公共数据转换时，先执行 `bash scripts/fetch_dependencies.sh` 固定外部 source checkout，再运行下方命令。PackingSolver 的预编译二进制和 Skjolber 的 Maven/JDK 环境不随脚本下载，需按 `research/test-protocol.md` 的版本与 SHA-256 自行准备；无网络或缺少 native/JVM 工具链时，仍可只做上述离线校验。

候选库受控 smoke test：

```bash
bash benchmarks/run_controlled.sh
bash benchmarks/run_java_controlled.sh
.venv/bin/python benchmarks/convert_thpack9.py
.venv/bin/python benchmarks/benchmark_public_thpack9.py
```

公共数据转换依赖 `.cache/esicup-datasets` 的 shallow checkout；没有该目录时脚本会明确报出缺少来源，不会静默生成替代实例。PackingSolver 的原始滚动二进制、修复版源码副本和 SHA-256 只作为审计实验输入，不伪装成官方 release。

## 可审计性

正式实验协议要求每个新结果记录输入实例、库版本/提交、参数、seed、时间/内存/线程限制、stdout/stderr、退出码、证书路径和 validator 结果；本轮公共 THPACK9 JSON 已记录版本/commit、参数、来源 hash 和 validator，其他 smoke 结果的原始日志、退出码、资源和输入由 `raw/experiments/` 与 `raw/provenance.json` 绑定，未生成证书的路径明确保留为空。`raw/` 是发布用的 canonical 原始目录，其中 `raw/experiments/` 完整镜像工作目录的原始日志；`derived/` 由脚本重新生成，`sources/manifest.csv` 登记 URL、访问日期、快照路径和哈希，`audit/` 记录被推翻的结论、未测试项和子代理 review。`verify.py` 只证明登记的断言，不替代人工逐条引用审阅。

## 边界

公开几何 benchmark 不能证明材料强度、动态稳定、摩擦、系固、危险品或车辆法规合规；没有真实字段的约束报告为 `NOT_APPLICABLE` 或 `UNKNOWN`。x86-64 实测不能外推到 aarch64、loongarch64 或其他平台。Gurobi/CPLEX 本轮没有可采信的实测数字：当前环境缺包/许可，历史 fixture 因内部矛盾被排除。Go/Rust 候选本轮因本机没有对应 toolchain，仅保留源码审计，不冒充运行结果。

## 许可

原创代码和报告按 Apache-2.0 发布。ESICUP 和各第三方库、论文、数据集按其原始许可与引用要求使用，边界见 [`DATA-LICENSE.md`](DATA-LICENSE.md)。
