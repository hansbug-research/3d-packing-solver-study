# 公共数据集、Benchmark 与度量

## 数据集核查结果

| 数据集 | 公开来源/论文 | 原始问题与可比指标 | 能否覆盖本项目约束 |
|---|---|---|---|
| **ESICUP THPACK1–7 (BR)** | [ESICUP 3d_rectangular/thpack](https://github.com/ESICUP/datasets/tree/154a8f006a8e72f65d734f2d1e36777f678f31f8/3d_rectangular/thpack)，Bischoff & Ratcliff 1995，DOI [10.1016/0305-0483(95)00015-G](https://doi.org/10.1016/0305-0483(95)00015-G) | 单容器装载，最大体积利用率；报告 packed volume、利用率、运行时间 | 每个尺寸作为竖直方向的允许标记，其余两边水平互换按实例语义；没有价格、承压、轴荷 |
| **ESICUP THPACK8 (LN)** | [ESICUP THPACK README](https://github.com/ESICUP/datasets/blob/154a8f006a8e72f65d734f2d1e36777f678f31f8/3d_rectangular/thpack/README.txt)，H.T. Loh & A.Y. Nee (1992), *A packing algorithm for hexahedral boxes*, Proc. Industrial Automation 92 Conf., Singapore, pp.115–126 | 单容器最大体积利用率 | 同上；无业务力学 |
| **ESICUP THPACK9 (IMM)** | Ivancic, Mathur & Mohanty 1989，后被 Bischoff 使用；[OR-Library 恢复说明](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/thpackinfo.html) | 多容器装完，最少箱数；报告 bins、完整性、时间 | 6 姿态/几何和多箱目标；没有箱价、承压、站点 |
| **ESICUP BAYTP** | Hoare & Beasley 2001，DOI [10.1057/palgrave.jors.2601130](https://doi.org/10.1057/palgrave.jors.2601130) | 货架/层序列，不能越过 shelf；报告 bays/shelves 和装载量 | 有序货架/障碍语义；不是一般自由 3D BPP |
| **ESICUP Alonso 2019** | Alonso et al. 2019，DOI [10.1016/j.cie.2018.11.012](https://doi.org/10.1016/j.cie.2018.11.012) | 多容器、托盘/层、交付日和实际车辆约束；报告车辆数、需求完成、轴荷等 | 最接近业务：交付日、层/托盘、重量、轴距离；格式复杂，需专门 adapter |
| **ESICUP Alonso 2020** | Alonso, Alvarez-Valdes & Parreño 2020，DOI [10.1007/s10288-018-0397-z](https://doi.org/10.1007/s10288-018-0397-z) | GRASP 多容器装载；库存托盘/案例托盘/剩余货物和日序 | 堆叠、分组、站点/日序；仍没有通用任意角和完整力学 |
| **PackingSolver 自带 `data/box`/`boxstacks`** | 上游仓库 `data/box/{bischoff1995,ivancic1989,loh1992,tests}`、`data/boxstacks` | 与其 CLI 直接兼容，适合回归与证书校验 | 旋转、箱重、同底面 stack、上压、轴荷/卸货专项；不是跨库标准 |
| **Q4RealBPP** | Mendeley Data DOI [10.17632/y258s6d939.2](https://doi.org/10.17632/y258s6d939.2)，版本 2；GPLv3 | 12 个现实导向实例；输入 quantity 合计 578 件，包含尺寸、重量、箱数/重量上限、相对位置、不相容/亲和与重心字段 | 适合现实约束 conformance 和小规模端到端回归；不能替代 MPV，也不能作为唯一吞吐集；官方 `Description.txt` 对 `3dBPP_5`、`3dBPP_6`、`3dBPP_10` 的件数与输入 quantity 不一致，canonical 以输入文件为准 |
| **3DBPPsi** | Science Data Bank DOI [10.57760/sciencedb.42066](https://doi.org/10.57760/sciencedb.42066)，V1；CC BY 4.0 | 20 个 CSV（A–J 的 items/vehicles）；异构车队、价格、payload、stacked-weight、density、nesting height、stackability class、forced orientation；item 行数 50–8,402 | 适合异构车队、stackable 约束和大规模 scalability；公开元数据未给统一 optimum，先报合法 incumbent/下界；不能替代同型多箱、门洞路径或路线时间窗 |

数据集语义必须保持原样：THPACK1–8 是单箱 knapsack（可漏装以最大体积），THPACK9 是多箱 BPP（必须装完以最少箱）；把前者当“最少箱”或把启发式漏件当“高利用率”会产生错误排名。ESICUP 总 README 明确要求每个数据集带来源、论文/DOI、格式说明，并接受通过 issue/PR 修订格式问题。

本次已下载 ESICUP shallow snapshot，并转换 `THPACK9 instance 1`：容器 `10x6x16`，20 件 `2x6x8` 和 50 件 `8x4x10`，总 70 件。统一输入见 [`benchmarks/data/public/thpack9_instance1.json`](../benchmarks/data/public/thpack9_instance1.json)；PackingSolver CSV adapter 见同目录两个 CSV。

Q4RealBPP 和 3DBPPsi 的源文件没有复制进仓库：本仓库只提交来源文件 ID、下载 URL、SHA-256 和结构审计结果，避免在未完成许可证审计前把 GPL 数据打包进发布物。审计脚本与结果分别见 [`benchmarks/comprehensive/audit_b33_source.py`](../benchmarks/comprehensive/audit_b33_source.py)、[`results/comprehensive/b33-source-audit.json`](../results/comprehensive/b33-source-audit.json)、[`benchmarks/comprehensive/audit_b34_source.py`](../benchmarks/comprehensive/audit_b34_source.py) 和 [`results/comprehensive/b34-source-audit.json`](../results/comprehensive/b34-source-audit.json)。两者当前仍是 `SOURCE_INCOMPLETE / NOT_RUN`，待 canonical converter、独立 hard validator 和 exact-small 校准后再进入下一版 ALL-libs 计划。

## 常用指标定义

### 质量与完整性

```text
bins_used             使用的物理箱实例数
total_cost            Σ(bin_type_cost × copies)，异构箱首要目标
packed_items          实际放置件数（按 item_instance 计，不按 item_type 行数）
completeness          packed_items / required_items；硬需求必须等于 1
volume_utilization    Σ packed item volume / Σ used bin volume
weight_utilization    Σ packed weight / Σ used bin capacity
```

单箱 THPACK 用 `volume_utilization`/packed volume；THPACK9 用 `bins_used`，体积利用率只作次级诊断。异构箱报告 `total_cost`，不能用箱数替代价格。若允许漏装，必须为每件给 profit/penalty，并同时报告 profit 和漏装列表。

### 最优性、性能与可靠性

| 指标 | 记录方式 | 适用边界 |
|---|---|---|
| `best_known_gap` | `(incumbent - best_known)/best_known`（最小化；若只有 bound 则标 bound gap） | 只有 known optimum/合法下界才可叫 gap；启发式不能伪造 dual bound |
| `proof_status` | `PROVEN_OPTIMAL`、`INCUMBENT_WITH_BOUND`、`FEASIBLE`、`TIME_LIMIT`、`UNKNOWN` | 绑定模型、容差和 solver 版本 |
| `time_to_first_feasible` | 首个通过独立 validator 的方案时间 | 对 anytime 引擎比只报最终时间更有用 |
| `wall_time` / `solver_time` | 外层进程/库内部分别计时 | wall 含启动和 IPC；必须同时记录 |
| `peak_rss` | `/usr/bin/time -v` 或平台等价值 | 内存控制和部署估算 |
| `seed_variance` | 至少 5 个 seed 的 best/median/p95 | 随机启发式；固定 seed 不能代表稳定性 |
| `invalid_geometry_rate` | 越界、重叠、非法姿态、漏件计数 | 任何非零都是硬失败，不得被利用率掩盖 |
| `constraint_violation` | 重量、承压、支撑、重心、轴荷、站点遮挡逐项计数/幅度 | 没有数据的约束标 `not_applicable`，不能填 0 |

仅在 `status=OPTIMAL` 或 primal/dual bound 在约定容差内闭合时显示“已证明最优”。CP-SAT 需要整数化单位并记录 scale；SCIP/Gurobi/CPLEX 的证明也只对给定离散模型成立，不等于真实车辆法规证明。

## 受控实验协议

- Python/C++ 外层 35 s、虚拟内存 4 GiB，`OMP/OPENBLAS/MKL/NUMEXPR=1`；PackingSolver 子任务 10 s、1 GiB。
- Java 使用 `-Xmx512m -XX:ActiveProcessorCount=1`；记录 JVM 启动/JIT 影响，不能宣称严格单线程。
- 正式实验协议要求每个新结果带库版本/提交、输入 SHA-256、seed、参数、状态、bound、证书路径和独立 validator 结果。本轮归档中，公共 THPACK9 JSON 已记录 source hash、版本/commit、参数和 validator；其他 smoke JSON 的 stdout/stderr、退出码、资源和输入由 `raw/experiments/` 与 `raw/provenance.json` 绑定，未生成证书的库明确记录为空，不能把协议要求倒写成已有字段。
- 启发式至少运行多个 item/bin 排序和 seed；精确模型小规模同时跑 CP-SAT 与 SCIP，检查上下界闭合。
- 统一 validator 检查箱边界、AABB/OBB 碰撞、姿态白名单、件数、总重；承压/支撑/轴荷用单独校验器，缺数据不默认通过。

## 本次公共 benchmark 实测

### THPACK 全集

PackingSolver fork `d953148b...` 实际处理 762 条记录。THPACK9 18、19、20 的源行 malformed，作为 `MALFORMED_SOURCE_EXCLUDED` 保留；其余 759 个源在 1 s 和 10 s 两档均得到合法 certificate。validator 独立核对输入/证书 item identity、copies、允许 rotation 对应尺寸、箱尺寸、边界、重叠、完整性、packed volume 和箱数。

| 问题族 | 合法源 | 主指标 | 1 s | 10 s | 预算响应 |
|---|---:|---|---:|---:|---|
| THPACK1-7 / BR | 700 | 单箱 volume utilization | mean `0.7216`，166 个空解 | mean `0.9624`，0 个空解 | 673 改善、27 相同 |
| THPACK8 / LN | 15 | 单箱 volume utilization | mean `0.5072`，5 个空解 | mean `0.7115`，0 个空解 | 7 改善、8 相同 |
| THPACK9 / IMM | 44 | bins used | mean/median `15.48/11.5` | mean/median `15.48/11.5` | 44 个箱数相同；reported bound closed 从 23 到 25 |

1 秒 BR/LN 原汇总曾因空解的“已使用箱体积”为 0 而把 `volume_utilization` 记为 null，均值跳过这些记录。离线重验改用输入容器总体积作分母，空解明确为 `0.0`；表中是修正后的结果。PackingSolver 的 bound 没有由本仓库独立证明，因此状态写 `SOLVER_REPORTED_BOUND_CLOSED`，不直接写 `PROVEN_OPTIMAL`。

### THPACK9 44 个合法实例的跨实现质量

每行只统计完整且通过 certificate 检查的记录：

| 实现 | 有效/总数 | mean bins | median | p95 | 说明 |
|---|---:|---:|---:|---:|---|
| PackingSolver 1 s | 44/44 | 15.48 | 11.5 | 50.1 | 10 s 箱数完全相同 |
| Skjolber Plain | 44/44 | 17.80 | 14 | 53.5 | 27 例优于 LAFF，17 例相同 |
| Rust ExtremePoint adapter | 44/44 | 18.41 | 14 | 51.7 | repeated-single-boundary，不是原生多箱 |
| `py3dbp` 降序 | 44/44 | 18.43 | 14 | 51.7 | pivot greedy，顺序敏感 |
| Jerry 降序 | 43/44 | 18.72 | 14 | 51.8 | 1 个重叠 certificate 被排除 |
| Go `bp3d` | 44/44 | 19.93 | 16 | 54.25 | 原生多箱；另有禁旋/重量缺口 |
| Skjolber LAFF | 44/44 | 20.84 | 17 | 60.1 | 层构造在此分布未赢 Plain |

THPACK9 没有 published optimum。`ceil(total item volume / bin volume)` 只是体积下界；相对它的差值不是已证明 optimality gap。

### THPACK9 instance 1 诊断例

instance 1 的箱为 `10x6x16`，物品是 20 件 `2x6x8` 和 50 件 `8x4x10`，总 70 件。体积下界 `ceil(17920 / 960) = 19`。它适合手工核对 adapter 和 certificate，但不能代替 44 例分布：

| 实现 | 完整件数 | 箱数 | certificate |
|---|---:|---:|---|
| PackingSolver fork | 70/70 | 25 | ✅ |
| Skjolber LAFF | 70/70 | 28 | ✅ |
| `py3dbp` / Jerry | 70/70 | 50 | ✅ |
| Go `bp3d` | 70/70 | 50 | ✅ |
| Rust ExtremePoint adapter | 70/70 | 50 | ✅ |
| Rust Layer/GA/BRKGA/SA | 报告 70/70 | 15-16 | ❌ 越界，全部作废 |

PackingSolver certificate 的 `COPIES` 是按相同布局聚合的箱实例，validator 先展开物理 copy 再检查。把聚合行直接重复到同一 bin 会产生错误的重叠报告。

### 顺序与 formulation sensitivity

Python campaign 共计划 3,048 条状态记录；因逐件姿态语义不匹配，实际只有 280 条可运行，276 条合法。`py3dbp` 的 53 对可比实例中 41 对质量随升/降序改变；Jerry 的 87 对中 66 对质量改变、4 对 certificate 有效性改变。

Exact-small 用 7 个手工真值场景测试网格、溢出拆箱、需旋转、禁旋、重量拆箱和两种异构成本方向。CP-SAT 9.15、SCIP/PySCIPOpt 6.2.1、Gurobi 13.0.3、CPLEX 22.1.2.0 的 canonical strengthened formulation 均为 7/7。legacy/reduced/strengthened 用来测模型强度：CPLEX legacy 的 1,489 条约束超过 promotional license，SCIP/CPLEX reduced 的 `overflow_9` 在 20 s 内未证明，而 strengthened 四家均闭合。它不是跨求解器通用速度榜。

### 工业数据集只审计、未降格求解

Alonso 2019/2020 已解析并核对字段、行数和需求恒等式，但现有 adapter 不能保真表达完整车辆、托盘、层、交付日和实际约束，状态为 `NOT_SUPPORTED / NOT_RUN`。ESICUP BAYTP 快照缺公共 `products`/`shelves`，状态为 `ESICUP_SNAPSHOT_INCOMPLETE / NOT_RUN`。本轮没有删除字段后用普通 3D BPP 冒充完整工业 benchmark。

所有 benchmark 的目的、结果路径和库覆盖矩阵见 [`../results/campaign/README.md`](../results/campaign/README.md)。

## 约束合规套件（不能用经典数据集替代）

另建版本化 synthetic suite，每个 case 只改变一个约束并保留人工可算真值：旋转白名单、禁止倒置、有限箱 copies、总重、最大上压、部分支撑、重心/地板点载荷、半挂轴荷、门洞、障碍物、多站 LIFO、危险品隔离和离散 OBB 姿态。结果必须逐项 `PASS/FAIL/NOT_APPLICABLE` 并显示反例证书。经典 THPACK/Alonso 只用于算法质量和业务格式覆盖，不能证明材料强度、摩擦、加速度或法规合规。
