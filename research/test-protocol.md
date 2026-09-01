# 全库综合 Benchmark 与技术选型测试协议

> 协议版本：`benchmark-protocol/3`；冻结日期：2026-08-31。本文定义后续“全部问题族 × 全部候选库”的实验边界、状态、证据、排行和发布门禁。已有 campaign 是基线证据，不自动视为已满足本协议的新增覆盖。

## 1. 目的与完成条件

本轮测试的目的不是选出一个脱离问题语义的总冠军，而是回答四个可执行的选型问题：每个候选是否能保真表达目标问题；在相同输入、预算和独立验证下能否给出合法解；合法解的质量、证明能力和资源代价如何；缺失能力应由库扩展、外层组合还是独立求解器承担。

协议完成需要同时满足以下条件：

1. 本文登记的每个 benchmark 套件都有固定来源或版本化生成器、canonical 输入、输入哈希和语义说明；
2. 每个候选库在每个套件都有机器可读状态，不能用空白代替不支持、未适配、失败或超时；
3. 所有进入质量统计的 placement 都通过与求解器实现隔离的 validator；
4. 原生能力、adapter 能力、问题投影和自建精确模型分别排行；
5. 原始输出、聚合结果、正文数字、图表和结论可由固定命令重算并通过 `scripts/verify.py`；
6. `report.md` 按问题族给出能力、质量、性能、稳定性和工程采用结论，未完成套件必须保留为明确缺口。

本文不把几何可行性外推为材料强度、动态稳定、系固、危险品或法规批准。没有校准数据和责任主体时，这些状态只能是 `UNKNOWN`、`NOT_APPLICABLE` 或 `NOT_SUPPORTED`。

## 2. 候选范围与比较轨道

候选清单以运行 manifest 为准，最低覆盖以下实现：

| 组 | 候选 | 主要算法或角色 |
|---|---|---|
| PS | PackingSolver fork、官方 rolling；`box` 与 `boxstacks` | tree search、maximal spaces、sequential knapsack/value correction、column generation、stack construction |
| PY | `py3dbp` 1.1.2、Jerry `75764a...` | pivot greedy、fix-point/level/support 近似 |
| SK | Skjolber Plain、LAFF、FastBruteForce 小规模轨 | extreme points、层构造、枚举 |
| GO | `gedex/bp3d@0ba3dcd...` | pivot greedy |
| RS | `u-nesting@8cde85b...` ExtremePoint、Layer、GA、BRKGA、SA | extreme point、layer decoder、元启发式 |
| EX | CP-SAT、SCIP、Gurobi、CPLEX | 统一生成的离散 CP/MIP 模型、证明和下界 |

同一个库经外层分箱、二分容器长度、成本分配或 pattern master 获得的能力，必须以 `adapter_name + library` 作为独立实现记录。不得把 `CP-SAT allocator + py3dbp` 的成本能力写成 `py3dbp` 原生能力。

排行分为三条轨道：

| 轨道 | 允许实现 | 可比较内容 |
|---|---|---|
| `NATIVE` | 库原生目标和硬约束 | 合法率、质量、库内时间、资源 |
| `COMPOSED` | 固定、公开、同版本 adapter 或 master + placement engine | 端到端质量、wall、资源；实现名必须包含 adapter |
| `EXACT_MODEL` | 四个后端使用同一模型生成器 | objective、bound、gap、证明率、证明时间 |

## 3. 全库状态契约

“ALL libs”表示每个候选在每个 benchmark 上都必须产生一条计划记录，并不表示每个候选都能进入该问题的数值榜。输入、能力、运行终止、解证书和证明是五个正交维度，不能压成一个状态；例如 `run_status=TIME_LIMIT` 可以同时具有可进入固定预算质量榜的 `solution_status=VALID_COMPLETE`，但其 `proof_status` 仍可能只是 `FEASIBLE`。

| 维度 | 允许状态 |
|---|---|
| `input_status` | `VALID`、`SOURCE_INVALID`、`SOURCE_INCOMPLETE` |
| `capability_status` | `SUPPORTED_NATIVE`、`SUPPORTED_COMPOSED`、`PROJECTION_ONLY`、`NOT_SUPPORTED`、`ADAPTER_MISSING` |
| `run_status` | `COMPLETED`、`TIME_LIMIT`、`MEMORY_LIMIT`、`CANCELLED`、`ERROR`、`NOT_RUN` |
| `solution_status` | `VALID_COMPLETE`、`VALID_PARTIAL`、`INVALID_CERTIFICATE`、`CONSTRAINT_VIOLATION`、`NO_SOLUTION`、`NOT_APPLICABLE` |
| `proof_status` | `PROVEN_OPTIMAL`、`PROVEN_INFEASIBLE`、`INCUMBENT_WITH_BOUND`、`FEASIBLE`、`UNKNOWN`、`NOT_APPLICABLE` |

`VALID_COMPLETE` 表示必装件完整且全部适用 hard checks 通过；`VALID_PARTIAL` 只用于原问题允许未装件的 knapsack/open-demand 语义。二者可进入对应固定预算质量榜，无论求解是正常提前结束还是达到 time limit。`INVALID_CERTIFICATE` 和 `CONSTRAINT_VIOLATION` 永远不进入质量均值。

`NOT_SUPPORTED`、`SUPPORTED_COMPOSED` 和 `PROJECTION_ONLY` 由 adapter capability check 产生，不得由人工删除失败记录来实现。`ADAPTER_MISSING` 表示从库能力看存在可行接法但本仓库尚未完成，它与明确不支持必须分开。最终汇总同时报告 planned、executed、valid、invalid、unsupported、adapter-missing、timeout、memory-limit 和 error 分母，并按 `termination_reason`、`error_kind`、`unsupported_reason` 保存简要原因。

## 4. Benchmark 目录与问题覆盖

B01-B11 是公共质量、目标函数和精确真值主线；B12-B18 是约束 conformance suite；B19-B23 与 B30-B32 是工业综合、边界和应用分布；B24-B29 是可靠性与托管测试。后三类不因统一编号而自动成为可比较的学术质量数据集。每个候选在每个套件必须有机器状态，但只有保留相同问题语义、输入交集和预算的记录才能进入数值排行。

### 4.1 公共几何与基础优化

| ID | 套件 | 原问题与主指标 | 适用实现 | 该结果主要说明什么 |
|---|---|---|---|---|
| B01 | ESICUP THPACK1-7 / BR | 单箱 3D knapsack；最大 packed volume；逐件允许竖直方向 | PS 原生；PY 仅语义可表达子集；SK/RS 需 adapter；GO 仅全旋转子集；EX 自建小规模 | 单箱选子集、姿态限制、anytime 质量 |
| B02 | ESICUP THPACK8 / LN | 另一分布的单箱 3D knapsack；最大 packed volume | PS 原生；Jerry 可表达 `(0,0,1)`；其余按 capability gate；EX 小规模 | 分布迁移、直立约束、初解速度 |
| B03 | Egeblad-Pisinger 3D-KP | 单箱最大总 `PROFIT`；20/40/60 件、5 类形状、clustered/random 和 50%/90% 容量档 | PS knapsack；RS `Fixed`、可禁旋的 SK 配置和 EX；PY/GO 只能进入全旋转投影；非原生 profit 候选使用公开排序 adapter | 是否选择高价值而非只追求体积；profit 与体积目标分离 |
| B04 | ESICUP THPACK9 / IMM | 同型无限箱；完整装载；最少箱数 | PS、PY、SK、GO、RS；EX 分层小规模 | 同构 3D-BPP 质量、完整性、顺序敏感性 |
| B05 | Martello-Pisinger-Vigo 3D-BPP | 经典同构 3D-BPP；按原始姿态规则；最少箱数和公开下界/已知结果 | PS、PY、SK、GO、RS；EX 适用规模 | 扩充 THPACK9 分布并提供更强的 known-result/gap 参照 |
| B06 | Exact-oracle generated | 6-30 件的正交 knapsack、BPP 和 feasibility 真值；最优或不可行证书 | 全部候选；EX 至少两后端闭合后发布真值 | 真正 objective gap、证明率、不可行识别、exact 适用阈值 |
| B07 | Davies-Bischoff extension | 900 个 BR0/BR8-15 单箱实例；按源语义恢复指标 | 与 B01 相同 | 扩大 SCLP 类型数和分布；若权重语义未从原始资料恢复，只能作为几何扩展 |

B05 在正式运行前必须完成官方实例、姿态规则、known optimum/best-known 和许可证审计；来源未冻结时使用 `input_status=SOURCE_INCOMPLETE`、`run_status=NOT_RUN` 和 `termination_reason=SOURCE_PENDING`，不得用自生成实例冒名替代。B03 本地固定 PackingSolver fork 已含 60 个转换实例；生成器区分 5 类形状、clustered/random 和 50%/90% 容量档，转换 CSV 没有旋转列，协议暂按固定方向解释。正式运行前仍需把原始文件、格式说明和引用纳入仓库级来源 manifest，并由论文/格式审计确认姿态规则。

### 4.2 异构容器、成本与开放维度

| ID | 套件 | 原问题与主指标 | 适用实现 | 该结果主要说明什么 |
|---|---|---|---|---|
| B08 | 3D multiple-bin-size/cost public | 多箱型、价格、可能的有限数量；最小总成本并报告箱数 | PS fork；EX；其他候选进入组合轨 | 价格与体积非单调时的箱型选择、下界和成本质量 |
| B09 | Variable-cost exact-truth | 2-5 箱型、非单调成本、有限 copies、箱型行反转；人工或 EX 证明真值 | PS fork/官方 bug 对照；EX；其余 `SUPPORTED_COMPOSED` 或 `ADAPTER_MISSING` | #536 类 comparator、库存、成本方向和输入顺序回归 |
| B10 | Fixed heterogeneous MCLP | 给定一组有限异构车辆/容器，要求完整装入或最大价值 | PS；SK/PY/GO/RS adapter；EX | 可行分配、有限供应、布局与分箱是否一致 |
| B11 | Open-X/Y/Z / 3D strip | 固定两个维度，最小使用长度或高度 | PS 原生；EX；其他候选用固定二分 wrapper 进入组合轨 | 车厢纵向压缩、货架/条带装载、open-dimension 原生能力 |

B08 优先采用 Alvarez-Valdes-Parreno-Tamarit 的 3D multiple-bin-size 数据和下界；若公开实例不可完整复现，B09 仍必须运行，但正文要把公共 benchmark 缺失和合成真值明确分开。

### 4.3 方向、运输和工业硬约束

| ID | 套件 | 原问题与主指标 | 适用实现 | 该结果主要说明什么 |
|---|---|---|---|---|
| B12 | Pose/orientation gauntlet | 六尺寸排列、保持直立、禁倒置、逐件姿态子集、24 面语义和离散 OBB | 全部候选按 capability 运行；EX 建模参照 | “能够旋转”与“遵守具体面语义”的差异 |
| B13 | Payload/inventory gauntlet | 总重量、箱 payload、有限箱 copies、空箱/tare | PS、PY、SK、RS 部分；GO 缺陷对照；EX | 字段是否真正进入 hard check；重量和库存完整性 |
| B14 | Support/load-bearing gauntlet | 支撑面积、支撑凸包、最大上方重量、最大堆数、nesting、脆弱件 | PS `boxstacks`；Jerry/Skjolber 近似或 controls；EX；其余 capability 状态 | 区分排序启发式、几何稳定和硬承压模型 |
| B15 | CG/axle/floor-load gauntlet | 总重心、轴/轴组反力、逐站剩余载荷、地板点载/面载 | PS `boxstacks`；EX；其他候选 placement 只能送独立 post-validator | 几何可装方案是否具有车辆静力可行性 |
| B16 | Obstacles/door/keepout | 内部障碍、轮拱、禁区、门尺寸、直线抽取和装入路径反例；另设阶梯近似 ULD 与夹具包络子变体 | Skjolber obstacles/controls；EX；其他候选按能力状态 | 非完整长方体可用空间、近似 ULD 和基本可达性；不外推为连续机器人运动规划 |
| B17 | Multi-drop/unloading | 固定路线、Increasing-X/Y、无遮挡、允许倒货及倒货代价 | PS 部分；Skjolber controls；EX；其余通常 `NOT_SUPPORTED` | 是否能按站点执行、逐站状态和重搬成本 |
| B18 | Compatibility/segregation | 必须同箱/分箱、相容组、温区、危险品隔离、优先区域 | EX 与外层分组；其他候选按 capability | 业务规则不能由几何偶然满足来冒充支持 |

B12-B18 使用版本化 synthetic truth cases 补足公共数据缺字段的问题。每个 case 只改变一个主约束，并同时保留可行、边界和不可行反例；涉及材料、车辆或法规的数值仅作为算法测试参数，不得称为工程批准值。

### 4.4 工业综合、高级几何和真实分布

| ID | 套件 | 原问题与主指标 | 适用实现 | 该结果主要说明什么 |
|---|---|---|---|---|
| B19 | Alonso 2019 | 产品到层/托盘/车辆、交付日、重量和轴距；完整需求、车辆数和可行性 | PS `boxstacks` 投影；EX 完整模型候选；其他库仅几何投影 | 工业层级、车辆、轴荷和交付约束的综合覆盖 |
| B20 | Alonso 2020 | stock/case/rest pallet 和多日需求；需求完成与资源使用 | PS + master、EX；其余投影 | 大需求分解、托盘类别和日序联合优化 |
| B21 | ESICUP VRPTW-CLP | 46 个路由与装载实例；固定路线投影及完整组合问题分开 | PS/SK/EX 可做固定路线装载；其他候选几何投影 | 路由、时间窗、三维可装性和多站卸货的耦合 |
| B22 | ESICUP 3D irregular | mesh/voxel/polytope、连续或离散非正交姿态，以及非长方体容器边界 | 当前正交长方体库通常 `NOT_SUPPORTED`；未来 irregular engine | 明确任意角、多面体、voxel 与真实斜壁 ULD 的能力边界 |
| B23 | De-identified real orders | 按件数、类型数、箱型数、姿态受限率、重量密度、站点数分层 | 适用语义的全部实现 | 公共随机实例到真实订单的 distribution shift |

B19-B21 同时发布 `FULL_PROBLEM` 和 `GEOMETRY_PROJECTION`，两个结果表不得合并。删除层、托盘、轴荷、路线或日序字段后的成绩不属于原始工业 benchmark。B22 即使当前全部候选都是 `NOT_SUPPORTED` 也必须保留，因为这证明当前选型边界，而不是测试缺失。

### 4.5 仓储、托盘与在线作业

| ID | 套件 | 原问题与主指标 | 适用实现 | 该结果主要说明什么 |
|---|---|---|---|---|
| B30 | OR-Library BAYTP | 产品按给定 bay 顺序进入可选 shelf；考虑 shelf 厚度、位置和 top/left/inter/right gap；主指标为使用 bay/shelf 和完整装载 | EX 完整模型；PS/SK + shelf master；PY/JE/GO/RS 只能进入逐 shelf 几何投影 | 仓储货架不是自由 3D-BPP；检验 shelf 选择、bay 顺序、间隙和禁止越架 |
| B31 | Mixed-SKU pallet building | 由 BR 类型重复分层、Alonso 托盘字段和脱敏订单生成；固定托盘底面、最大高度、完整需求、全支撑/最小支撑、承压和层型；主指标为合法完整率、托盘数或使用高度 | PS `boxstacks`；EX 小规模；Jerry/Skjolber 近似或 controls；其余仅 `GEOMETRY_PROJECTION` | 高重复 SKU、层模式、支撑和承压联合后，普通箱体积排名是否仍成立 |
| B32 | Online/incremental 3D packing | 固定到货序列、有限 lookahead/buffer、不可移动或有预算重排；报告累计箱数/成本、每件决策延迟和 relocation | 当前离线候选均通过统一 rebuild/incremental adapter；EX 只到小规模窗口；无 adapter 时 `ADAPTER_MISSING` | 离线最优质量不能回答实时装箱；检验延迟、重排代价、顺序鲁棒性和离线损失 |

B30 的 ESICUP 快照只含 README 与两个 bay 文件，但 OR-Library 的 `products.txt`、`shelves.txt`、`baytp1.txt` 和 `baytp2.txt` 已于 2026-08-31 重新取回并记录内容 SHA-256，因此输入来源为 `VALID`；当前缺口是完整模型/adapter，不再是源文件缺失。B31 是版本化工业 conformance/performance suite，不冒充公开学术数据集；每个生成实例必须保存父分布、seed 和约束参数。B32 的 arrival trace 从公共实例和 B23 订单确定性派生，离线重算必须单独记录 `OFFLINE_REBUILD`，不能写成库原生 online 能力。

### 4.6 可靠性、扩展性和故障行为

| ID | 套件 | 变换或规模 | 适用实现 | 该结果主要说明什么 |
|---|---|---|---|---|
| B24 | Metamorphic | 物品置换、ID 重命名、类型 copies 展开/聚合、X/Y/Z 置换、镜像 | 全部 | 输入表示不应改变的目标或合法性是否变化 |
| B25 | Cost/bin-order metamorphic | 箱型行反转、等比例价格缩放、添加 dominated 箱型 | PS、EX、组合轨 | comparator、成本方向和 dominance 预处理错误 |
| B26 | Unit/numeric | mm/cm/m 等比例整数化、接触边界、极大/极小整数、近容差 | 全部 | 溢出、舍入、浮点碰撞和单位错误 |
| B27 | Seed/order repeatability | 确定性库重复 5 次；随机库至少 5 个 seed；原始/升序/降序/固定随机顺序 | 全部 | seed 是否生效、顺序敏感性、best/median/p95 方差 |
| B28 | Scalability | 20/50/100/200/500/1000 件，类型重复率和箱型数分层 | 全部；EX 到预算允许的桶 | time-to-first、最终质量、wall、CPU、RSS、超时率 |
| B29 | Fault/cancellation | timeout、取消、OOM、非法输出、子进程崩溃和恢复 | 全部 adapter/worker | 后端能否安全托管 native/JVM/Python 库 |

## 5. 数据冻结与问题投影

每个数据集必须登记来源 URL、访问日期、commit/version、原始文件哈希、许可证/引用要求和转换器版本。canonical 输入使用稳定实例 ID、整数单位、显式 objective、允许姿态、箱型成本与 copies；转换结果必须能回指原始行。

BAYTP 四个源文件必须逐文件校验已登记 SHA-256，不能只校验目录或 README。B31/B32 的生成器版本、seed、父实例 hash 和生成参数视同外部数据来源，缺少任一项时使用 `SOURCE_INCOMPLETE`。真实订单只能使用获准的脱敏快照；没有可发布数据时必须保留 B23 计划状态，不得用随机实例替代后沿用 `REAL_ORDER` 名称。

允许的问题投影必须具有新 ID 和明确的 `projection_of`：例如 `Alonso2019/GEOMETRY_PROJECTION`、`THPACK/RELAXED_ALL_ROTATIONS`。以下行为禁止：删除不受支持字段后沿用原 benchmark 名称；把 knapsack 当完整装箱；把最少箱数替代最小成本；把体积下界写成已证明 optimum；把 adapter 能力记到原库名下。

## 6. 统一运行矩阵

每条计划记录至少由以下维度唯一确定：

```text
benchmark_id / problem_variant / instance_id / implementation_id /
algorithm / adapter / budget / item_order / bin_order / seed / repetition
```

启发式公共质量集默认运行 `1 s` 和 `10 s` 两档内部预算；代表规模另加 `60 s` 档。没有内部 time limit 的库由外层强杀，并记录无法保证完整输出。exact-oracle 默认 `20 s`，分层扩展可用 `60 s/300 s`，但不同预算不混为一列。

确定性实现至少运行原始、体积降序、体积升序和一个固定哈希顺序；profit 套件增加 profit、profit/volume 降序。随机实现至少 5 个 seed，并验证 seed 确实改变或固定随机源。策略共享 decoder 时仍分别记录算法名，但共同缺陷必须在结论中关联说明。B32 另记录 arrival sequence、buffer/lookahead、每次可移动件数、每件决策 deadline、rebuild 次数和 relocation 次数；允许重排与不可重排结果不得合并。

## 7. 资源与计时边界

运行环境记录 OS、CPU 型号、核心数、内存、Python/JDK/Go/Rust 版本、库 commit、编译器、build flags、binary SHA-256 和许可证类型。默认设置：

- Python/C++/Go/Rust 外层进程 4 GiB 地址空间；具体 benchmark 可收紧但必须登记；
- `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`NUMEXPR_NUM_THREADS=1`；
- Java `-Xmx512m -XX:ActiveProcessorCount=1`；
- Rust 设置 `RAYON_NUM_THREADS=1`；无法限制的内部线程明确标为 `THREAD_LIMIT_UNVERIFIED`；
- 同时记录 library/solver elapsed、端到端 wall、CPU user/system、peak RSS、退出码、stdout、stderr 和取消延迟。

跨语言 wall 只有在相同进程生命周期、预热、输入解析和输出序列化边界下才进入速度榜。否则只能作部署数量级参考；Java 同 JVM 内算法、同一 Python worker 内两库、同一 exact 模型的四后端可分别形成受限性能榜。

## 8. 独立验证

validator 不读取求解器内部“feasible”布尔值作为真值。所有 placement 至少检查：

1. item instance identity、copies、必装完整性和重复；
2. container identity、箱型库存、边界和目标复算；
3. 允许姿态、AABB 碰撞；离散斜角使用 OBB/SAT 或可信碰撞库；
4. 总重量、tare/gross/payload；
5. 适用时的支撑并集、重心投影、载荷流、最大上方重量、堆数和 nesting；
6. 适用时的总重心、轴/轴组反力、地板载荷和每个卸货状态；
7. 障碍、keepout、门洞、站点遮挡、相容和隔离规则；
8. objective、bound、gap 和状态的一致性。

对 `INVALID_CERTIFICATE` 保留原始 certificate 和首个失败证据；不得修正坐标后将其升级为库的有效结果。validator 与 adapter 各自有版本/hash，回归必须同时覆盖已发现的 PackingSolver comparator、Jerry fix-point、Go MaxWeight 和 Rust Layer decoder 反例。

## 9. 指标与统计

| 问题族 | 首要质量指标 | 次要指标 |
|---|---|---|
| 单箱 volume knapsack | packed volume / container volume | packed count、空解率、bound/gap |
| profit 3D-KP | packed profit；相对 optimum/best-known gap | volume、profit density、漏装明细 |
| 同构 3D-BPP | bins used；相对 proven/best-known/合法下界 gap | 利用率、完整率 |
| 异构成本 | total cost | 箱型用量、bins、库存 margin、bound |
| fixed MCLP | 完整可行率或 packed value | 容器均衡、未装需求 |
| open dimension | used length/height | 截面利用率、gap |
| shelf/bay | 完整可行率；使用 bay/shelf | 空位、间隙 margin、顺序违规 |
| pallet building | 合法完整率；pallets 或 used height | 层数、支撑/承压 margin、层型重复率 |
| online/incremental | 累计 bins/cost；deadline 命中率 | 每件 p50/p95/p99 延迟、relocation、相对离线损失 |
| 支撑/运输 | hard violation rate 必须为 0 | 最小支撑/承压/轴荷/CG margin、重搬量 |
| exact | proof rate、objective、bound、gap | time-to-first、time-to-proof、节点/冲突 |
| reliability | metamorphic invariance、重复合法率 | seed/order best/median/p95 |
| performance | 在固定质量门下的 wall/CPU/RSS | timeout、OOM、取消延迟 |

每个表报告样本数、有效分母、mean、median、p95、min/max；配对实例优先报告 win/tie/loss 和差值分布。随机算法报告每实例多 seed 的 best/median/p95，再做跨实例聚合，不能把所有 seed 当独立实例扩大样本量。

## 10. 排名规则

1. `solution_status=VALID_COMPLETE` 或问题允许的 `VALID_PARTIAL` 是进入质量榜的前置条件；非法低箱数永远排除；
2. 先按 hard feasibility/完整性分层，再按该问题首要 objective 排名，再报告时间和资源；
3. 不同输入子集不得直接比较平均数；同时发布 all-common intersection 和 per-library supported coverage；
4. `NATIVE`、`COMPOSED`、`EXACT_MODEL` 分榜；工业 `FULL_PROBLEM` 与 `GEOMETRY_PROJECTION` 分榜；
5. 没有 published optimum 或独立合法 bound 时只写 feasible incumbent，不写“最优”或“最优差距”；
6. 不生成跨问题族单一加权总分。最终选型由能力门禁和各问题族排名共同决定。

质量榜排序键必须在聚合脚本中版本化。例如最少箱问题使用 `(invalid_rate, incomplete_rate, mean_bins, median_bins)`；成本问题使用 `(invalid_rate, incomplete_rate, mean_cost, median_cost)`。性能榜必须先声明最大允许质量损失，避免用空解或低质量解换取速度第一。

## 11. 运行阶段与退出门

| 阶段 | 内容 | 退出条件 |
|---|---|---|
| P0 协议冻结 | 本文、来源、状态、schema、validator 和运行 manifest | Markdown/链接/来源检查通过，人工 review 无 blocking finding |
| P1 公共核心 | B01-B07；全部基础 packer，EX 分层 | all-libs 状态矩阵完整；共同实例质量榜可重算 |
| P2 成本与硬约束 | B08-B18 | 原生/组合分榜；所有 hard case 有独立反例验证 |
| P3 工业与高级边界 | B19-B23、B30-B32 | full/projection 分开；BAYTP/托盘/在线结果分榜；不支持项完整记录；真实数据缺口明确 |
| P4 可靠性与回归 | B24-B29；重跑各波次代表实例 | metamorphic、numeric、repeatability、scalability、fault/cancellation 均有结果；失败可重现 |
| P5 结论冻结 | 更新 aggregate、结果 README、图、`report.md` 和决策矩阵 | `analyze/plot/verify/pytest` 全过；需求逐项审计完成 |

## 12. 结果目录和必交付物

每个 suite 使用以下结构，原始结果不可由报告脚本覆盖：

```text
raw/experiments/comprehensive/<benchmark>/<implementation>/<run-id>/
  input.json
  effective-config.json
  stdout.log
  stderr.log
  resources.json
  solution.json
  validation.json
results/comprehensive/
  run-manifest.jsonl
  aggregate.json
  coverage.csv
  rankings/<problem-family>.csv
  README.md
```

`run-manifest.jsonl` 每条记录保存输入和工具哈希、执行命令、环境、状态和 artifact 相对路径。聚合文件登记所有消费源 SHA-256；`scripts/verify.py` 对 headline 数字、全库覆盖、无效证书排除、来源哈希和正文数字建立断言。

最终 `report.md` 至少增加以下独立结果表：单箱 knapsack、profit 3D-KP、同构多箱、异构成本/库存、open dimension、shelf/bay、托盘构建、online/incremental、exact 证明、硬约束合规、工业 full/projection、可靠性/扩展性。每个表都要回答“能否做、做得是否合法、质量如何、资源如何、工程上是否采用”。

## 13. 当前基线与明确缺口

现有证据已经覆盖 PackingSolver THPACK 759 个合法源两档预算、THPACK9 44 例主要 packer 横评、四个 exact backend 的 7 个 strengthened 场景、PackingSolver `boxstacks` 9 项、Rust 策略和工业数据字段审计。它们作为协议 v2 的回归基线保留；协议 v3 不倒写这些历史结果。

当前尚未完成并因此不能宣称全库综合选型已经冻结的项目包括：B05、B08、B10 的来源/统一 adapter 和全量运行；B11 的 SK/EX adapter 及大规模独立公开分布；PY/SK 对 B12-B18 的统一状态；Alonso/VRPTW-CLP 的 full/projection 求解；B22 的明确能力边界执行记录；B23 的脱敏真实订单；B30 的完整 shelf adapter；B31 的生成器和联合约束 FULL 运行；B32 的原生 incremental/FULL adapter。B24-B29 reliability-v3 已完成一轮 19 个实现的代表性跨库运行，但仍需在 B05/B23 等非对称真实分布上复跑，才能作为最终稳定性结论。B11 已对 PY/JE/GO/RS 增加可复现的外层搜索 projection，但不得把该轨写成原生 open-dimension 能力；B32 已对 PY/JE/GO/RS 完成固定 arrival trace 的组合 policy 校准，全部记录为 `COMPOSED/GEOMETRY_PROJECTION`，不能解释为库原生 online API。B03 已完成来源审计、PackingSolver 官方/fork、Python/Go/Rust adapter 和 exact 20 件子集，但其 projection 与 fixed 轨必须继续分开解释。后续提交必须逐项关闭这些缺口，不能用已有 THPACK9 或 B03 排名替代。

## 14. 研究问题到实验设计的映射

协议不是“把所有库运行一次”的 smoke test，而是为选型决策提供可反驳证据。每个问题至少要由一个公开或版本化数据源、一个反例/边界套件和一个资源/可靠性套件共同覆盖：

| 研究问题 | 主要套件 | 必须得到的证据 | 选型决策 |
|---|---|---|---|
| Q1：库能否保真表达问题？ | B01-B05、B08-B23、B30-B32 | capability 状态、原生字段映射、projection 删除字段清单 | 选择原生库、组合架构或 exact/master 后端 |
| Q2：输出是否确实可行？ | 全部有 placement 的套件；B12-B18 反例 | 独立 validator、首个失败原因、hard violation 和完整性 | 非法证书直接淘汰，不用 objective 抵消 |
| Q3：合法解质量和证明能力如何？ | B01-B11、B19-B23、B30-B32 | objective、best-known/合法 bound、proof rate、配对差异 | 按问题族选择质量/证明最优的实现 |
| Q4：质量代价和部署风险是什么？ | B24-B29 + 全部代表规模重复 | wall/CPU/RSS、p95 延迟、seed/order 方差、取消恢复 | 决定 Python binding、native worker、Java sidecar 或 exact 服务边界 |
| Q5：结果是否可复现和可审计？ | 全部 suite | source/input/adapter/validator/binary hash、原始 stdout/stderr、重算命令 | 只有证据链闭合的结果可进入最终报告 |

每个 benchmark 的设计都要至少包含一类“正常”、一类“边界”和一类“应失败”实例；公开数据缺乏应失败样例时，用独立 synthetic conformance case 补足，但必须改用新的 `problem_variant`，不能修改公开实例后继续沿用原始名称。

## 15. Canonical 输入与证书契约

所有 adapter 的输入先转换为版本化 canonical model，再调用库。转换器不能隐式删除字段；不能表达的字段必须在 capability 阶段显式产生 `PROJECTION_ONLY` 或 `NOT_SUPPORTED`。canonical model 的最小逻辑结构如下，实际 JSON 可以按 suite 扩展，但不得改变这些语义：

```json
{
  "schema_version": 1,
  "benchmark_id": "Bxx",
  "problem_variant": "FIXED_XYZ",
  "instance_id": "stable-id",
  "units": {"length": "source-unit", "mass": "source-mass"},
  "containers": [{"type_id": "bin-1", "size": [X, Y, Z], "copies": 1, "cost": 1}],
  "items": [{"type_id": "sku-1", "instance_ids": ["i-1"], "size": [x, y, z], "copies": 1}],
  "pose_semantics": {"allowed_orientations": [[x, y, z]]},
  "constraints": {},
  "objective": {"kind": "packed_volume", "direction": "max"},
  "provenance": {"source_ref": "...", "source_commit": "...", "source_sha256": "..."}
}
```

长度和质量在 canonical 文件中使用可精确回转的整数或显式 decimal 字符串；转换器必须保留 `source_scale`，不能通过 binary float 截断。每个 placement 至少包含 `instance_id`、`type_id`、`container_id`、`origin`、`size_after_pose` 和 `pose_id`。解中未出现的 item 只有在该 suite 允许 partial 的情况下才能省略，且必须写出 `unpacked_items`；完整装载 suite 的漏件一律是 `INVALID_CERTIFICATE` 或 `CONSTRAINT_VIOLATION`。

`run-record.schema.json` 是执行记录的机器契约，不是 solver 输出格式。solver 的原始 JSON/CSV 必须作为 artifact 保留，validator 从该 artifact 或 canonical placement 转换结果重新计算 objective 和所有 hard checks。`solver_says_feasible`、reported objective 或 reported bound 只能作为诊断字段，不能覆盖 validator 结论。

## 16. 一条 run 的生命周期和不可跳过的步骤

每个 `benchmark × implementation × variant × budget × order × seed × repetition` 按下面顺序执行；任何步骤失败都要留下记录，不能删除该 cell：

1. **Freeze**：读取来源 manifest，检查 source commit、license、输入文件 hash 和 canonical converter hash；非 `VALID` 输入不得启动 solver。
2. **Capability gate**：根据实现 catalog 和 adapter 的字段映射确定 `SUPPORTED_NATIVE`、`SUPPORTED_COMPOSED`、`PROJECTION_ONLY`、`NOT_SUPPORTED` 或 `ADAPTER_MISSING`；记录被删除/近似的字段。
3. **Prepare**：生成只读 canonical input、effective config 和环境快照；固定工作目录，禁止 runner 修改原始 source。
4. **Execute**：以受控子进程或同等隔离边界运行；捕获开始/结束时间、退出码、signal、stdout、stderr、CPU、RSS 和取消延迟。
5. **Capture**：保存原始 solution、solver log、资源文件和命令行；即使超时或崩溃也保留部分输出。
6. **Validate**：用独立 validator 检查 identity/copies、尺寸/姿态、边界、碰撞、库存、重量、支撑、运输和业务约束；先保存错误列表，再决定 solution status。
7. **Recompute**：从 validated placement 重新计算 objective、bound 可比性、完整率、利用率、箱数、成本和 margin；不信任 solver 汇总数字。
8. **Aggregate**：只让同一输入交集、variant、track、budget 和 validator version 的记录进入排行；写入 source hashes 和聚合版本。
9. **Review**：运行 `analyze.py --check`、`scripts/verify.py`、测试和 Markdown/link 检查；正文数字必须来自 generated artifact，而不是手工复制。

`TIME_LIMIT`、`MEMORY_LIMIT` 和 `CANCELLED` 是运行结局，不自动等于无解；若部分证书通过 validator，可以是 `VALID_COMPLETE` 或 `VALID_PARTIAL` 并进入相应 anytime 榜。反之，正常退出但证书非法必须是 `INVALID_CERTIFICATE`，不能因为 `run_status=COMPLETED` 而升级。

## 17. 资源、随机性和计时控制

每个 runner 在 `effective-config.json` 中写出实际生效值；命令行默认值不能替代记录。固定配置为：单 worker/单 solver thread；Python/C++/Go/Rust 进程默认 4 GiB 地址空间；Java sidecar `-Xmx512m -XX:ActiveProcessorCount=1`；Rust `RAYON_NUM_THREADS=1`；BLAS/OpenMP 线程变量全部设为 1。无法证明线程限制时写 `THREAD_LIMIT_UNVERIFIED`，该结果只能进受限资源榜。

启发式的公共预算是 1 s、10 s；代表规模可增加 60 s，但三档不得混为一列。exact 默认 20 s，扩展 60/300 s 只作为单独预算。外层 timeout 必须留出捕获/清理时间，并区分 solver time、process wall、CPU user/system 和 post-validation time。跨语言 speed ranking 只在相同预热、进程生命周期、输入解析、输出序列化和隔离边界下成立。

确定性实现至少运行 `ORIGINAL`、`ASCENDING`、`DESCENDING`、`HASHED_FIXED` 四种输入顺序；profit 套件另运行 `PROFIT_DESCENDING` 和 `PROFIT_VOLUME_DESCENDING`。随机实现至少使用五个固定 seed，且 runner 要在日志中证明 seed 被传入有效随机源；seed 未接线的实现不能把重复结果伪装成独立实验。B32 额外固定 arrival trace、lookahead、buffer、deadline、rebuild 和 relocation budget。

## 18. Validator 的固定判定顺序与数值规则

validator 采用 fail-closed 规则，检查顺序固定为：

1. JSON/schema、有限数、唯一 run/instance/container ID；
2. copies、必装需求、未知/重复 item 和箱型库存；
3. pose whitelist、尺寸重排和正交边界；
4. 同箱 AABB 分离；斜角/网格使用 OBB/SAT 或经过独立测试的碰撞引擎；
5. 总重、tare、payload、箱型成本和 objective 重算；
6. 适用时支撑并集、重心投影、载荷流、上方重量、堆数、nesting；
7. 适用时轴/轴组反力、地板载荷、门洞、障碍、keepout、卸货可达性和相容/隔离；
8. 对照 solver bound、proof status、termination reason 和 certificate metadata 的一致性。

canonical 整数坐标采用精确整数比较；格式转换产生的浮点仅允许 `1e-7` canonical unit 的解析容差。边界接触（例如 `x + dx == X`）是合法的，只有存在严格正体积重叠才判 collision；负零、NaN、Infinity、负尺寸和无法解析的 decimal 一律失败。所有 tolerance、碰撞算法和 validator commit/hash 写入 run record 或其 artifact metadata。

硬约束存在一条错误也不得进入 quality mean。对 `INVALID_CERTIFICATE` 保存首个失败规则、完整错误列表、原始输出 hash 和 validator version；禁止在报告阶段“修坐标后重算”并把修正版归给原库。若需要诊断修复，必须另起 `REPAIRED_DIAGNOSTIC` variant 且不进入原问题排行。

## 19. 统计、配对和不确定性报告

百分位使用 nearest-rank，先在每个实例内聚合 seed，再跨实例聚合；不得把 seed 当独立实例。均值必须同时给出有效分母和 invalid/incomplete 分母。没有 published optimum 或独立合法 bound 时报告 incumbent、下界和 solver-reported bound 分开，不写 gap-to-optimum。

同一问题族的跨库比较使用 all-common intersection，并同时输出每库 supported coverage。主指标相等时报告 median/p95、资源和 win/tie/loss；不使用任意 epsilon 把微小差异强行分成胜负。版本比较（例如 fork/upstream）单独输出 pairwise 表，不把 patched upstream 写成官方发行版。

硬约束套件采用词典序：先最大化合法完整率（理想值 100%），再最小化 violation count，之后才比较成本/箱数/利用率。可靠性套件报告 invariance/pass rate、重复方差、p50/p95/p99 延迟和恢复率，不与几何质量分数相加。

## 20. 失败分类、问题升级和结论用语

失败按责任边界分类，便于决定是修 adapter、向上游提 issue/PR 还是换技术栈：

| 类别 | 典型证据 | 报告用语 | 后续动作 |
|---|---|---|---|
| `SOURCE_INVALID/INCOMPLETE` | 文件缺失、引用或 hash 不一致 | “数据源未就绪，未排名” | 补来源或锁定版本 |
| `NOT_SUPPORTED` | 库模型不能表达关键字段 | “明确不支持” | 评估换库/自建模型 |
| `ADAPTER_MISSING` | 理论可组合但本仓库还没实现 | “尚未适配，不等于不支持” | 实现 adapter 后重跑 |
| `PROJECTION_ONLY` | 删除了成本、路线、姿态或力学字段 | “仅几何投影诊断” | 不得作为 full 结论 |
| `INVALID_CERTIFICATE` | 越界、重叠、漏件、非法姿态 | “库/adapter 输出非法” | 最小复现、回归和 issue/PR |
| `CONSTRAINT_VIOLATION` | 几何合法但重量、轴荷、支撑等失败 | “硬约束不合规” | 不能进入质量榜 |
| `ERROR/TIMEOUT/MEMORY` | 进程失败或资源耗尽 | “在该预算/环境失败” | 保留 artifact，测扩展和隔离 |

结论只使用可被证据支持的词：`在该 variant/预算上观察到`、`通过独立 validator`、`未发现`、`明确不支持`、`尚未适配`。禁止使用“保证最优”“工业可用”“法规合规”“支持任意角”等超出 benchmark 的表述；这些需要另行的物理、法规或现场验收证据。

## 21. Ready gate 与逐项审计

最终 ready 不是“测试命令返回 0”这一条，而是以下条件全部成立：

1. B01-B32 每个计划 cell 都有状态记录，且 `SOURCE_*`、`NOT_SUPPORTED`、`ADAPTER_MISSING`、`NOT_RUN` 的原因可追溯；
2. B01-B07 的公共质量轨、B08-B18 的能力/合规轨、B19-B23/B30-B32 的 full/projection 轨和 B24-B29 的可靠性轨均有对应排行或边界表；
3. 每个质量数字都有原始 artifact、输入/实现/validator hash 和可重算命令；
4. 所有非法证书和 hard violation 被排除并在报告中计数，不能隐藏在平均值之外；
5. `analyze.py --check`、`build_plan.py --check`、`scripts/verify.py`、`pytest`、Markdown/link 检查和 `git diff --check` 全部通过；
6. `report.md`、decision matrix、coverage CSV、rankings 和 self-review 的数字一致；
7. 仍未完成的来源、adapter、真实订单或工程验证明确列为 gap，不得以“未发现错误”替代证据。

本附录与 [`run-record.schema.json`](../benchmarks/comprehensive/run-record.schema.json)、[`suites.json`](../benchmarks/comprehensive/suites.json)、[`implementations.json`](../benchmarks/comprehensive/implementations.json) 和 [`results/comprehensive/README.md`](../results/comprehensive/README.md) 一起构成可执行协议；若代码与本文冲突，必须先更新协议版本和 self-review，再运行新实验。
