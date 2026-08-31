# 公共数据集、Benchmark 与度量

## 数据集核查结果

| 数据集 | 公开来源/论文 | 原始问题与可比指标 | 能否覆盖本项目约束 |
|---|---|---|---|
| **ESICUP THPACK1–7 (BR)** | [ESICUP 3d_rectangular/thpack](https://github.com/ESICUP/datasets/tree/main/3d_rectangular/thpack)，Bischoff & Ratcliff 1995，DOI [10.1016/0305-0483(95)00015-G](https://doi.org/10.1016/0305-0483(95)00015-G) | 单容器装载，最大体积利用率；报告 packed volume、利用率、运行时间 | 每个尺寸作为竖直方向的允许标记，其余两边水平互换按实例语义；没有价格、承压、轴荷 |
| **ESICUP THPACK8 (LN)** | [ESICUP THPACK README](https://github.com/ESICUP/datasets/blob/154a8f006a8e72f65d734f2d1e36777f678f31f8/3d_rectangular/thpack/README.txt)，H.T. Loh & A.Y. Nee (1992), *A packing algorithm for hexahedral boxes*, Proc. Industrial Automation 92 Conf., Singapore, pp.115–126 | 单容器最大体积利用率 | 同上；无业务力学 |
| **ESICUP THPACK9 (IMM)** | Ivancic, Mathur & Mohanty 1989，后被 Bischoff 使用；[OR-Library 恢复说明](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/thpackinfo.html) | 多容器装完，最少箱数；报告 bins、完整性、时间 | 6 姿态/几何和多箱目标；没有箱价、承压、站点 |
| **ESICUP BAYTP** | Hoare & Beasley 2001，DOI [10.1057/palgrave.jors.2601130](https://doi.org/10.1057/palgrave.jors.2601130) | 货架/层序列，不能越过 shelf；报告 bays/shelves 和装载量 | 有序货架/障碍语义；不是一般自由 3D BPP |
| **ESICUP Alonso 2019** | Alonso et al. 2019，DOI [10.1016/j.cie.2018.11.012](https://doi.org/10.1016/j.cie.2018.11.012) | 多容器、托盘/层、交付日和实际车辆约束；报告车辆数、需求完成、轴荷等 | 最接近业务：交付日、层/托盘、重量、轴距离；格式复杂，需专门 adapter |
| **ESICUP Alonso 2020** | Alonso, Alvarez-Valdes & Parreño 2020，DOI [10.1007/s10288-018-0397-z](https://doi.org/10.1007/s10288-018-0397-z) | GRASP 多容器装载；库存托盘/案例托盘/剩余货物和日序 | 堆叠、分组、站点/日序；仍没有通用任意角和完整力学 |
| **PackingSolver 自带 `data/box`/`boxstacks`** | 上游仓库 `data/box/{bischoff1995,ivancic1989,loh1992,tests}`、`data/boxstacks` | 与其 CLI 直接兼容，适合回归与证书校验 | 旋转、箱重、同底面 stack、上压、轴荷/卸货专项；不是跨库标准 |

数据集语义必须保持原样：THPACK1–8 是单箱 knapsack（可漏装以最大体积），THPACK9 是多箱 BPP（必须装完以最少箱）；把前者当“最少箱”或把启发式漏件当“高利用率”会产生错误排名。ESICUP 总 README 明确要求每个数据集带来源、论文/DOI、格式说明，并接受通过 issue/PR 修订格式问题。

本次已下载 ESICUP shallow snapshot，并转换 `THPACK9 instance 1`：容器 `10x6x16`，20 件 `2x6x8` 和 50 件 `8x4x10`，总 70 件。统一输入见 [`benchmarks/data/public/thpack9_instance1.json`](../benchmarks/data/public/thpack9_instance1.json)；PackingSolver CSV adapter 见同目录两个 CSV。

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
- 每个结果带库版本/提交、输入 SHA-256、seed、参数、状态、bound、证书路径和独立 validator 结果。
- 启发式至少运行多个 item/bin 排序和 seed；精确模型小规模同时跑 CP-SAT 与 SCIP，检查上下界闭合。
- 统一 validator 检查箱边界、AABB/OBB 碰撞、姿态白名单、件数、总重；承压/支撑/轴荷用单独校验器，缺数据不默认通过。

## 本次公共实例实测

`THPACK9 instance 1` 是几何/最少箱对照，不包含价格和力学字段；所有库均使用同一箱尺寸、70 件和 80 个候选箱，输出通过独立 AABB validator：

| 实现 | 完整件数 | 箱数 | 成本（单位箱价） | wall/库内时间 | 几何 |
|---|---:|---:|---:|---:|---|
| PackingSolver patched `box` | 70/70 | 25 | 25 | 约 1 s / 输出 JSON | ✅ |
| Skjolber LAFF | 70/70 | 28 | 28 | 8.315 ms 库内（当前 raw 快照） | ✅ |
| `py3dbp` 1.1.2 | 70/70 | 50 | 50 | 约 16 ms | ✅ |
| Jerry fork | 70/70 | 50 | 50 | 约 24 ms | ✅ |

这不是已知最优表：THPACK9 文件没有给该实例的 optimum，体积下界为 `ceil(17920 / 960) = 19`，所以只能报告 25/28/50 的 incumbent，不把 25 叫最优。PackingSolver certificate 的 `COPIES` 是按相同布局聚合的箱实例，validator 已按物理 copy 展开后再检查；直接把聚合行重复到同一 bin 会错误地产生重叠。

CP-SAT/SCIP 的 9 立方体 exact-small smoke test 已分别闭合到 2 箱；它验证建模/界和资源协议，不代表 70 件 THPACK9 的全局最优。对大公共实例，正确做法是报告 time-limit/incumbent/bound，而不是强行延长到不可控。

## 约束合规套件（不能用经典数据集替代）

另建版本化 synthetic suite，每个 case 只改变一个约束并保留人工可算真值：旋转白名单、禁止倒置、有限箱 copies、总重、最大上压、部分支撑、重心/地板点载荷、半挂轴荷、门洞、障碍物、多站 LIFO、危险品隔离和离散 OBB 姿态。结果必须逐项 `PASS/FAIL/NOT_APPLICABLE` 并显示反例证书。经典 THPACK/Alonso 只用于算法质量和业务格式覆盖，不能证明材料强度、摩擦、加速度或法规合规。
