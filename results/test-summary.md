# 本地受控实测摘要

> 最后复跑：2026-08-31。平台为 Linux x86-64、Python 3.12.1、OpenJDK 21、Go 1.27.0、Rust 1.98.0。`VALID` 只表示对应输入语义和独立 validator 检查通过，不代表覆盖所有业务约束或已证明全局最优。

## 资源与证据

- PackingSolver 全集：每实例内部 1 s 或 10 s、1 GiB；10 s campaign 外层 4 个并行进程。CLI 没有暴露 engine thread limit，`OMP/OPENBLAS/MKL/NUMEXPR=1` 不能据此声称 C++ 内部严格单线程。
- Exact-small：20 s、单 worker/线程、seed 42；四个 backend 使用同一模型生成器和 validator。
- Java：`-Xmx512m -XX:ActiveProcessorCount=1`。Go/Rust 跨语言场景为每进程 20 s、2 GiB，Rust 另设 `RAYON_NUM_THREADS=1`。
- 原始 stdout/stderr、exitcode、resource log、certificate archive 和固定源码证据位于 [`../raw/experiments/campaign/`](../raw/experiments/campaign/)；统一汇总是 [`campaign/aggregate.json`](campaign/aggregate.json)，35 个消费源均记录 SHA-256。

不同实现的计时边界不同：有的包含 Python/JVM/进程启动，有的是已启动进程内库调用，PackingSolver 还有停止检查粒度。当前计时只能检查资源失控和数量级，不能作为跨语言速度排名。

## 实际运行总表

| 候选 | 实际运行范围 | 合法结果 | 主要发现 | 工程判断 |
|---|---|---:|---|---|
| PackingSolver fork `d953148b` | THPACK 759 个合法源 × 1 s/10 s；7 个跨语言场景；`boxstacks` 9 例；16 条策略记录 | 全集 1,518/1,518；跨语言 7/7；`boxstacks` 9/9；策略 15/16 | THPACK9 质量最好；10 s 显著改善 knapsack；column generation 在 THPACK9-47 返回 0/99 | 主正交候选，固定源码和 binary hash，保留 validator |
| PackingSolver 官方 rolling | 7 个跨语言场景 | 6 个成功 certificate 合法，1 个进程错误 | 小箱行先的异构成本触发 `Solution::operator<` #536 | 仅作官方行为对照，等待 PR 合并 |
| `py3dbp` 1.1.2 | 53 个语义可表达 THPACK 实例 × 2 排序；THPACK9 44 例 | 106/106；THPACK9 44/44 | 41/53 对质量随排序变化 | baseline/候选生成，不作业务真值 |
| Jerry `75764a` | 87 个语义可表达实例 × 2 排序；THPACK9 44 例 | 170/174；降序 THPACK9 43/44 | `fix_point` 吸附后不重检碰撞；`loadbear` 仅排序 | 不作承压或合法性真值 |
| Skjolber `c73d521...` Plain/LAFF | THPACK9 两算法 × 44；小型 LAFF/Plain/FastBruteForce | 88/88；小型 3/3 | Plain 在 27 例少用箱，17 例相同，LAFF 0 例胜 | Java 可用；有 obstacles/controls 真实收益时选装 |
| Go `bp3d@0ba3dcd` | THPACK9 44 例；7 个跨语言场景 | THPACK9 44/44；专项 5/7 | 禁旋无白名单；`MaxWeight` 未执行累计检查 | 不作核心，原因是语义缺口而非语言 |
| Rust ExtremePoint `8cde85b` | THPACK9 44 例；7 个跨语言场景；THPACK9-1 重复 5 次 | 44/44；7/7 行为符合能力声明；5/5 | 原生单 `Boundary3D`，多箱是 repeated-single-boundary adapter | 可保留为单箱布局基线/观察项 |
| Rust Layer/GA/BRKGA/SA | 4 策略 × 5 场景；THPACK9-1 每策略重复 5 次 | 主实验 14/20；逐策略 Layer 3/5、GA 3/5、BRKGA 4/5、SA 4/5；THPACK9-1 重复 0/20 | 共享 Layer decoder 越界；seed/time limit 接线不完整 | 当前排除；低箱数无效 |
| CP-SAT 9.15 | 7 场景 × 3 formulation | canonical strengthened 7/7 | BR/LN/IMM 不是其现成模型；需自建 3D | 默认 exact-small/成本主问题 |
| SCIP/PySCIPOpt 6.2.1 | 同上 | canonical 7/7 | reduced `overflow_9` 20 s 未证明 | 开放 MIP/CIP 对照与研究轨 |
| Gurobi 13.0.3 | 同上 | canonical 7/7 | 三种 formulation 均完成；小例不构成通用速度证据 | 有生产许可和真实收益时选装 |
| CPLEX 22.1.2.0 | 同上 | canonical 7/7 | legacy 超 promotional license 规模；reduced 20 s 未证明 | 客户已有 IBM 授权时适配 |

## Benchmark 分工

| Benchmark | 主要测量 | 本轮结论 |
|---|---|---|
| THPACK1-7 / BR，700 例 | 单箱最大 packed volume | PackingSolver 1 s mean utilization `0.7216`，10 s `0.9624`；673/700 改善 |
| THPACK8 / LN，15 例 | 单箱最大 packed volume | `0.5072` 到 `0.7115`；7/15 改善 |
| THPACK9 / IMM，44 个合法例 | 完整装载后的最少箱数 | PackingSolver 1 s/10 s 箱数 44/44 相同；跨实现质量见下表 |
| Python 顺序 campaign | pivot greedy 对输入顺序的敏感性 | `py3dbp` 41/53 质量变化；Jerry 66/87 质量变化、4/87 有效性变化 |
| Exact-small | 旋转、禁旋、重量、成本方向、bound | strengthened 四后端均 7/7；formulation 强弱影响证明和许可证规模 |
| `boxstacks` 专项 | 上压、堆数、nesting、轴荷、卸货 | 9/9；正常轴荷独立重算通过 |
| 工业数据审计 | Alonso/BAYTP 数据完整性和语义映射 | Alonso 完整问题 `NOT_SUPPORTED / NOT_RUN`；BAYTP `ESICUP_SNAPSHOT_INCOMPLETE / NOT_RUN` |

THPACK 不带价格、最大上压、重心/轴荷或卸货字段，不能用 THPACK 箱数证明这些能力。构造专项能验证具体约束实现，却不能代替公开数据分布上的算法质量。

## THPACK9 44 例质量

只统计完整且 certificate 有效的记录：

| 实现 | 有效/总数 | mean bins | median | p95 |
|---|---:|---:|---:|---:|
| PackingSolver 1 s | 44/44 | 15.48 | 11.5 | 50.1 |
| PackingSolver 10 s | 44/44 | 15.48 | 11.5 | 50.1 |
| Skjolber Plain | 44/44 | 17.80 | 14 | 53.5 |
| Rust ExtremePoint adapter | 44/44 | 18.41 | 14 | 51.7 |
| `py3dbp` 降序 | 44/44 | 18.43 | 14 | 51.7 |
| Jerry 降序 | 43/44 | 18.72 | 14 | 51.8 |
| Go `bp3d` | 44/44 | 19.93 | 16 | 54.25 |
| Skjolber LAFF | 44/44 | 20.84 | 17 | 60.1 |

THPACK9 没有 published optimum。表中的箱数是 feasible incumbent；`relative_gap_to_volume_lower_bound` 只是相对体积下界的诊断，不是合法的最优性 gap。

## 已复现缺陷与边界

- PackingSolver 官方 #536：文档、CLI 和 objective enum 都声明异构成本能力，调用方式正确；`box`/`boxstacks` 的两个 `Solution::operator<` 漏分支。#536-#539 与 PR #540-#543 仍 open，fork 通过不能写成官方已修复。
- Jerry：`fix_point=True` 修改 placement 坐标后没有重新运行碰撞检查，产生 4 条重叠 certificate；`fix_point=False` 对照均合法。
- Go `bp3d`：没有逐件姿态白名单；`MaxWeight` 是公开字段，但 `PutItem` 不检查累计重量。
- Rust `u-nesting`：Layer 换层并重置 X/Y 后只检查 Z；GA/BRKGA/SA 共用该 decoder。`Config.seed=42` 没传到随机 runner，多数策略不读取 `time_limit_ms`。
- Exact-small：canonical 文件 `exact-{backend}.json` 固定代表 strengthened formulation。legacy/reduced/strengthened 是模型敏感性实验，不是单因素后端性能对照。
- PackingSolver 的 `SOLVER_REPORTED_BOUND_CLOSED` 没有独立证明 bound 有效，只能视为求解器自报闭合。

逐项文件和状态含义见 [`campaign/README.md`](campaign/README.md)，算法/库 × 特性矩阵见 [`../research/decision-matrices.md`](../research/decision-matrices.md)。
