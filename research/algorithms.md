# 三维装箱算法、论文与成熟求解器调研

> 调研与复核日期：2026-08-31。本文只讨论算法和可执行求解器能力；真实工况、法规与完整数据模型见 [domain-model.md](./domain-model.md)。版本、维护状态和实测均是该日期的快照，不代表未来版本继续保持相同行为。

## 1. 结论先行

不存在一个成熟的开源组件（无论 Python、C/C++、Rust、Java），能同时原生解决以下全部需求：异构有限箱型按价格选择、三维坐标、物品逐件允许姿态、不耐压、一般接触面支撑、稳定性、重心/轴荷、多站点装卸顺序和连续任意角，并且还能在业务规模上证明全局最优。后端要求 Python 不等于算法必须纯 Python：成熟 native solver 可通过 wheel/binding、稳定 C ABI 或受控子进程接入。可落地方案必须是多引擎、同一数据模型、同一独立验证器，而不是把所有能力归给一个 `pack()` 函数。

推荐路线如下：

1. **默认正交启发式引擎候选：PackingSolver 的 `box` / `boxstacks` CLI，固定到经回归测试的提交 SHA。** 它是候选库中工况覆盖最接近需求的：6 种轴向尺寸旋转子集、重量、最大上压重量、最大堆叠数、堆栈密度、中/后轴轴荷及二维卸货方向约束，支持 Linux、Windows、macOS 预编译程序。最坏时间仍是指数级，日常运行是 anytime tree search、序贯价值修正、列生成等组合，不应把任意有解输出称为最优。当前滚动版本的异构成本路径和一个窄轴荷合成路径均实测失败，因此它是有条件采用项，不是可直接上线的全部工况内核。
2. **精确/可证明轨：OR-Tools CP-SAT 或 PySCIPOpt/SCIP。** 两者都不是现成 3D 装箱器，需要建立坐标、姿态和六向分离模型。CP-SAT 部署简单、整数逻辑强；SCIP 支持 MIP、约束整数规划和非线性扩展，许可证也已开放。小中规模可返回 incumbent、bound、gap；只有 `OPTIMAL` / `optimal` 或 gap 在约定容差内才可标“已证明最优”。
3. **商业加速插件：Gurobi 优先，CPLEX 作为企业已有授权时的适配项。** 它们适合直接 MIP、解池、warm start、回调和大规模并行，但不自带 3D 几何模型，且桌面软件分发、离线许可、容器/云许可必须单独解决。商业求解器不能消除模型本身的 `O(n^2 B)` 两两分离规模。
4. **异构箱型 + 价格当前不能直接依赖 PackingSolver。** 2026-08-31 下载的官方 `latest` 构建在 `box` 与 `boxstacks` 的 `variable-sized-bin-packing` 上均以 `Solution::operator<` 不支持该目标而退出；普通 `bin-packing` 又受输入箱序影响，不能替代按成本自由选箱。首版应由 CP-SAT/SCIP 做箱型分配与成本主问题，再调用 PackingSolver 生成/改善单箱装载方案；若只枚举有限候选 pattern，这是可解释的 matheuristic，不是完整 branch-and-price，不能宣称全局最优。
5. **`py3dbp`、Go `bp3d` 和 Jerry 的 Python 分支只适合基线、教学或候选生成，不可作为业务真值。** `py3dbp` 无每件姿态限制、无成本目标、无稳定/承压/轴荷/顺序和最优性界；Go `bp3d` 的 `MaxWeight` 字段未进入 `PutItem` 可行性检查；Jerry 分支的 `loadbear` 实际是排序优先级而非最大上压重量，本地反例把 20 重量放在所谓脆弱件上方仍判可行。
6. **任意角是另一类连续非凸问题。** 正交主线保留 `ORTHOGONAL_SET`；工程上确有斜放需求时先用少量人工批准的 `DISCRETE_POSES`，每个姿态转成固定 OBB 后搜索，再用成熟碰撞库和独立力学校核复验。连续欧拉角/四元数优化放在专家插件，不能把 AABB 包围盒或 2D irregular packing 当成 3D 任意角支持。

## 2. 问题定义必须先分开

“装箱”至少包含以下不同优化问题。算法、目标与最优性声明都依赖所选问题，不能互换：

| 业务问题 | 标准名称 | 典型目标 | 关键区别 |
|---|---|---|---|
| 一个固定容器尽量多装 | 3D knapsack / Single Container Loading Problem (SCLP) | 最大价值、优先级或装载体积 | 允许有未装件 |
| 无限同型容器全部装完 | 3D Bin Packing Problem (3D-BPP) | 最少容器数 | 同型箱、必须全装 |
| 多箱型有价格与数量限制 | Variable-Sized / Heterogeneous 3D-BPP | 最小总价格 | 箱型选择是决策变量 |
| 已给定若干具体车辆 | Multiple Container Loading Problem (MCLP) | 可行性、均衡、少重搬 | 容器实例固定且可异构 |
| 固定底面、最小高度 | 3D strip packing / open dimension | 最小使用高度或长度 | 常见于托盘/货架 |
| 多站点车辆与装载联合 | VRP with 3D loading constraints | 路线成本 + 车辆数 + 重搬 | 路线与装载相互耦合 |

Wäscher、Haußner、Schumann 的 typology 用“输入物品同质性、容器维度、选择/分配/放置目标”统一分类；Bortfeldt 与 Wäscher 的 CLP 综述进一步区分方向、堆码、稳定、载荷分布、分组、隔离和多站点等真实约束。产品 API 应显式保存 `problem_kind` 和分层目标，不能由是否传了 `price` 猜测语义。

建议采用词典序而非任意加权和：

1. 硬约束违反为 0；
2. 必装件漏装为 0；
3. 最小总箱体成本；
4. 再最小容器数、未利用体积、重心偏差、重搬次数和固定材料需求。

若业务允许漏装，则必须给出每件价值或漏装惩罚并改成 knapsack/soft-demand 语义；不能让启发式悄悄丢件。

## 3. 方向不是一个布尔值

长方体三条边在载具 `x/y/z` 轴上的排列只有 6 种，因此多数库把“rotation”定义为 6 个尺寸排列。但具有 `top/front/door/label` 等面语义的刚体有 24 个保持手性的正交姿态。同一个尺寸排列仍可能有 4 种面朝向；立方体的尺寸更完全不随姿态变化。

因此：

- PackingSolver、`py3dbp` 和 `bp3d` 的 6 种 rotation 足以表达“哪条尺寸竖直”，不足以完整表达“哪个具体面朝上且标签朝门”；
- `can_rotate=false` 过于粗糙，至少要保存允许姿态集合；
- 产品内部应使用 24 姿态的面语义 ID，再映射到求解器可见的 6 个尺寸排列；映射丢失的面向约束由求解模型附加变量或后验验证器处理；
- “不得倒置但可水平转 90 度”通常是 4 个 upright 姿态中的子集，不是单纯禁止旋转；
- 任意角姿态用固定旋转矩阵/四元数保存，禁止只保存经过旋转后的 AABB 尺寸，因为那会丢失真实占用形状。

## 4. 理论难度与“最优”的含义

### 4.1 复杂度下限

一维 bin packing 已是 NP-hard；三维正交问题包含一维问题作为特例。由 3-Partition 可得到强 NP-hard 的常见装箱变体，因此不存在已知的通用多项式时间精确算法。允许有限姿态、异构箱型、支撑关系和装卸顺序只会扩大离散搜索空间；连续任意角再引入非凸实变量和碰撞约束。

对实际算法应使用以下复杂度描述，而不是给一个误导性的单一大 O：

- **直接坐标 MIP/CP-SAT**：`n` 件、`B` 个候选箱、每件 `K` 个姿态，分配/姿态变量约 `O(n B K)`；每对同箱物品至少有 6 个相对位置分支，变量/约束约 `O(n^2 B)`；支撑关系通常再增加 `O(n^2 B)`。branch-and-bound/CP 搜索最坏指数级。
- **空间索引/网格 MIP**：变量随离散坐标格点数增长，属于伪多项式；毫米级大车厢通常不可直接建满网格。
- **排列 + 姿态穷举**：最坏约 `n! * product_i(|R_i|)`，即使剪掉相同件和对称姿态也只适合很小 `n`。
- **极点/最大空余空间启发式**：每次放置检查候选点/空间和既有物品，朴素实现常见 `O(n^2)` 到 `O(n^3)`，维护 maximal spaces 的数量本身可能组合爆炸；但在正常实例上通常很快，没有近似比或最优保证。
- **层/墙/块启发式**：排序一般 `O(n log n)`，构造阶段依候选块而变；本仓库 100 件 smoke test 的 LAFF 库内耗时为 12 ms，但这不是一般性能保证；层结构可能排除更好的非层状方案。
- **GA/SA/VNS/Tabu/GRASP**：复杂度约为“迭代数 × decoder 成本”；能改进排序和选择，但最终可行性与质量仍取决于 decoder，不提供全局最优证明。
- **列生成/branch-and-price**：LP 主问题变量按可行单箱 pattern 指数多，通过定价逐步生成；只有把分支与定价完整结合并收敛才是精确 branch-and-price。有限 pattern 池 + 整数主问题只是 matheuristic。

### 4.2 四种必须分开的结果状态

| 状态 | 产品可显示的说法 | 证据 |
|---|---|---|
| `FEASIBLE` | 找到并通过独立验证的可行方案 | 完整性、几何和所有硬约束复算通过 |
| `INCUMBENT_WITH_BOUND` | 当前最好方案，最优性差距为 `gap` | primal/dual bound 同时存在 |
| `PROVEN_OPTIMAL` | 在模型与数值容差内已证明最优 | 求解器 optimal 状态或上下界闭合 |
| `UNKNOWN/TIME_LIMIT` | 未在时限内证明，可能有当前可行解 | 超时状态；不得把 incumbent 改名为最优 |

MIP 的“证明”是在给定模型、浮点容差和求解器实现内成立，不等于真实世界的力学/法规证明。CP-SAT 只接受整数系数，尺寸和质量必须选择单位并安全缩放；不应把任意小数乘一个巨大常数，以免整数溢出和性能恶化。

## 5. 算法家族与适用边界

### 5.1 精确枚举、branch-and-bound 与 CP/MIP

Martello、Pisinger、Vigo 的经典精确 3D-BPP 工作使用下界、装箱可行性检查和 branch-and-bound；Fekete、Schepers 的 conservative scales / dual feasible functions 为多维正交装箱提供有效下界和精确框架。它们的价值主要是：

- 小实例可证明最优；
- 强下界可量化启发式质量；
- 对不可能装下的组合给出可核验不可行证据。

局限是几何可行性子问题和两两关系迅速爆炸。直接坐标 MIP 的典型变量如下：

```text
y_b              是否使用候选箱 b
a_i_b            物品 i 是否分配到箱 b
r_i_k            物品 i 是否采用允许姿态 k
x_i, y_i, z_i    左下后角坐标
d_i_j_b_q        同箱 i,j 在 q in {left,right,front,back,below,above} 的分离分支
```

边界、唯一分配、姿态唯一和重量是线性约束。两物体不相交用六向析取和 big-M / indicator constraints 表达。选择紧的每轴 M、消除对称箱、同型物品排序和体积/重量下界非常重要。连续坐标 MIP 可以保留非整数位置；CP-SAT 则需整数格点。

一般承压与稳定性会加入 `support_i_j`、接触范围、支撑面积和载荷流变量。接触面积本身包含 `min/max` 与乘积，常需离散化或分段线性化；模型规模和数值风险远高于单纯不重叠。不要因为 MIP 语法能写出来就假定求解可扩展到数百件。

### 5.2 构造启发式：层、块、极点和 maximal spaces

成熟 3D 实现主要依赖这类方法：

- **层/墙构造（LAFF、wall building）**：先选大底面积物品形成层高，再填层内剩余空间；快、可解释、适合规则箱，但会错过跨层组合。
- **Extreme Point (EP)**：每次放置后从几何边界生成新候选点，对每个物品/姿态/点打分；对异质货物灵活，容易加入靠墙、重心、优先级等打分。
- **Empty/Maximal Spaces (EMS/MS)**：维护未被占用、且不包含于其他空空间的长方体，放置后切分/修剪；装载率通常优于简单 pivot，但空间数可能增长且去重复杂。
- **Block/stack generation**：先将相容箱组成规则 block 或同底面 stack，再把 block 当大件装；能天然表达堆码规则，但 block 候选数可能指数增长。
- **Tree/beam search with decoder**：节点是部分装载，guide/score 决定保留哪些分支；beam 有界后是启发式，只有不丢分支且完整搜索才能证明最优。

Crainic、Perboli、Tadei 的 extreme-point 工作、Bischoff/Ratcliff 工业 CLP 基准，以及后续 GRASP/VNS/树搜索构成了当前开源启发式的主要思想来源。启发式应至少多起点运行：不同物品排序、箱型排序、姿态顺序和 guide；输出前统一用独立验证器淘汰非法方案。

### 5.3 Pattern、列生成与分层求解

对“多箱型 + 成本”最自然的主问题是 set covering / set partitioning：每个 pattern `p` 表示一个具体箱型中的一组可行放置，整数变量 `lambda_p` 表示使用次数，目标 `min sum(cost_p * lambda_p)`，覆盖每种物品需求。优点是箱价、有限供应和物品数量在主问题中很清楚；难点是可行 pattern 数指数多，定价子问题本身是 3D knapsack。

工程上可以分三档：

1. 由 PackingSolver 对每种箱型、多个随机/guide/价值权重生成候选 pattern，再用 CP-SAT/SCIP 求整数主问题：实用 matheuristic；
2. 用 LP 对偶价格迭代调用 3D knapsack 定价，直到没有负 reduced-cost 列，再整数化：列生成下界 + 启发式整数解；
3. 在分支节点继续正确定价：完整 branch-and-price，才有全局最优保证。

首版建议实现第 1 档，并明确报告 pattern 数、生成预算和“未证明最优”。第 2/3 档应优先复用 PackingSolver 已有的 sequential value correction / column generation 思想或商业求解器回调框架，而不是仓促自写通用 branch-and-price。

### 5.4 学习与元启发式的正确位置

GA、PSO、RL 和神经网络适合产生物品顺序、箱型优先级、候选姿态或 placement score，不适合作为硬约束的最终裁判。生产使用必须满足：

- decoder 始终生成几何可行解，或输出后由验证器拒绝；
- 训练分布、随机种子和基准集版本可追踪；
- 与简单 EP/EMS/LAFF、PackingSolver 及 exact-small 基线比较；
- 不以平均体积利用率掩盖漏件、方向、承压或轴荷违规。

在当前项目中没有必要把 ML 作为第一阶段依赖。

## 6. 成熟库与求解器对比

### 6.1 总表

| 组件 | 类型/算法 | 许可证 | 维护快照 | 最优性 | 原生相关能力 | 关键缺口 | 建议 |
|---|---|---|---|---|---|---|---|
| [fontanf/packingsolver](https://github.com/fontanf/packingsolver) | C++，tree/beam search、maximal spaces、SVC、列生成、下界 | MIT | 2026-08-29 仍有提交；`latest` 是随 master 重建的滚动二进制，稳定 tag `v1.1.0` 停在 2023 | 有 primal/dual/gap，部分实例可证明；一般是 anytime 近似 | 6 旋转子集、重量；`boxstacks` 有同底面堆栈、上压、层数、密度、半挂轴荷、2D 卸货方向 | 当前 variable-sized cost 路径崩溃；窄轴荷合成例触发异常；无通用部分支撑/载荷传播、3D 任意角、官方 Python API | **主启发式候选，必须 pin SHA + subprocess 适配 + 回归门禁** |
| [Google OR-Tools](https://github.com/google/or-tools) CP-SAT | SAT + CP + integer optimization | Apache-2.0 | v9.15，2026-01；持续维护 | 完整搜索可证明，超时给 best bound | 强布尔/整数逻辑、indicator、调度 interval，Python/多平台 | 官方 bin-packing 示例是 1D；只有 `NoOverlap2D`，没有 3D global constraint；只接受整数 | **精确小规模/成本主问题首选** |
| [SCIP](https://github.com/scipopt/scip) + [PySCIPOpt](https://github.com/scipopt/PySCIPOpt) | MIP/CIP/MINLP 框架 | SCIP Apache-2.0；PySCIPOpt MIT | SCIP 10.0.3 (2026-07)，PySCIPOpt 6.2.1 (2026-05) | branch-and-bound 完成可证明；有 primal/dual/gap | 线性/指示/逻辑/非线性约束、插件/回调、Python | 不自带 3D 几何；直接 pairwise 模型仍会爆炸 | **开放许可证精确轨与研究扩展首选** |
| [Gurobi](https://www.gurobi.com/product) / `gurobipy` | 商业 MIP/QCP/全局非线性 | Proprietary | 13.0.3 wheel，持续维护 | 完成可证明；MIP gap/解池；非凸函数用 spatial B&B | 高性能 MIP、indicator、回调、warm start，多平台 | 需付费生产许可；无 3D 模型；任意角碰撞仍很难 | **预算允许时的商业加速插件** |
| [IBM CPLEX](https://www.ibm.com/products/ilog-cplex-optimization-studio) / `cplex` | 商业 LP/MIP；CP Optimizer 为同一产品族的独立引擎 | Proprietary | PyPI `cplex` 22.2.0.1；引擎报告 22.2.0.0 | MIP 完成可证明，返回 best bound/gap | CPLEX MIP 的 indicator、回调、Python、多平台；CP Optimizer 应使用 `docplex.cp` 与对应引擎 | 许可和分发门槛；无 3D 模型；非凸连续几何不宜直接承担 | **客户已有 IBM 授权时适配** |
| [enzoruiz/3dbinpacking](https://github.com/enzoruiz/3dbinpacking) / `py3dbp` | Python pivot greedy，源自 Go `bp3d` / Dube 模拟报告 | MIT | PyPI 1.1.2 发布于 2020；仓库最后实际 commit 2023-04 | 无界、无证明，顺序敏感 | 6 轴向尺寸旋转、箱总重量、多箱分配、坐标输出 | 无姿态子集、成本、支撑、承压、轴荷、顺序；API 很小 | **只作 smoke baseline，不作核心** |
| [gedex/bp3d](https://github.com/gedex/bp3d) | Go pivot greedy | MIT | 最后实际 commit 2017-02 | 无 | 6 旋转、坐标，多箱 | `MaxWeight` 仅存字段，`PutItem` 未校验；老旧，Go/Python 集成多余 | **拒绝作为核心** |
| [jerry800416/3D-bin-packing](https://github.com/jerry800416/3D-bin-packing) | `py3dbp` 分支，增加落地/支撑启发式和绘图 | MIT | 最后实际 commit 2023-06 | README 明示 example3 “algorithm does not optimize” | up/down 布尔、支撑比例启发式、四象限重量统计、输出顺序 | `loadbear` 只是排序值，不强制上压；稳定规则是面积/四角近似；有 README 自报 binding crash | **可参考 UI/校验思路，不作为求解真值** |
| [skjolber/3d-bin-container-packing](https://github.com/skjolber/3d-bin-container-packing) | Java LAFF、plain、brute force、controls | Apache-2.0 | 2026-08-26 有提交；README 为 4.2.x | brute force 小件数可穷举；LAFF/plain 近似 | 障碍物、重量、箱数量、deadline、自定义 manifest/point/placement controls、Three.js 调试可视化 | Java 运行时；高级稳定/结构能力只是 control 扩展点，README 明示不一定已实现；连续角无 | **强备选/对照，不优先引入 JVM** |

维护状态按“最后实际 commit / 官方 release”判断，不用 GitHub 页面访问时间或星标替代。滚动 `latest` 不是稳定版本号，生产构建必须记录二进制 SHA-256 与源提交。

#### 6.1.1 语言与集成形态

| 组件类别 | Python 后端集成方式 | 跨平台/打包判断 | 选择原则 |
|---|---|---|---|
| PackingSolver C++ | 首版用独立 CLI + CSV/JSON；稳定后可补窄 C ABI/pybind11 binding | 官方已有 Linux x64、Windows x64、macOS x64 滚动二进制；仍需自行补 arm64/签名/固定版本 | 子进程隔离崩溃、内存和取消最稳；不要直接暴露庞大 C++ API |
| OR-Tools / PySCIPOpt | 官方 Python wheels，native 核心在 wheel 内 | 主流 Linux/Windows/macOS 易部署；应在目标 Python/CPU 矩阵实测 | 默认 exact-small/主问题最省集成成本 |
| Gurobi / CPLEX | 官方 Python wheels + 外部/嵌入许可证 | 技术打包成熟，真正风险是客户生产许可、离线激活和并发条款 | 只有性能/客户授权收益覆盖许可成本时启用 |
| Rust solver（未来候选） | 优先 PyO3 + maturin wheel，或稳定 C ABI | Rust 本身不是优势；仍需 manylinux、Windows、macOS/arm64 构建与异常边界 | 只按算法成熟度选，不为语言重写已有求解器 |
| Skjolber Java | JVM 子进程/本地 sidecar + JSON/Protobuf IPC；不建议嵌入 Python 进程 | 可用 `jlink/jpackage` 随桌面应用带裁剪 JRE；增加安装体积、冷启动、签名和进程管理 | 不因 Java 排除；只有 obstacles/controls/LAFF 的独特价值显著时引入 |
| Go `bp3d` | 可编译 shared library 或 sidecar，但跨 FFI 对象/错误管理需额外协议 | 技术可行，算法与维护状态不足以支付集成成本 | 拒绝原因是能力和维护，不是 Go |

所有 native/JVM 引擎都必须在进程或 FFI 边界做输入 schema 校验、版本握手、超时/取消、内存限制、stderr 捕获和 crash recovery。桌面应用默认优先子进程：某个求解器崩溃不能带走 GUI/Python 服务；待 ABI 稳定且 profiling 证明 IPC 是瓶颈后再考虑进程内 binding。

### 6.2 PackingSolver：最接近工况，但不能盲信 README

官方 README 对 `box` 声明的目标包括 knapsack、bin packing、open X/Y/Z、variable-sized bin packing；可选 6 种旋转并限制箱总重量。`boxstacks` 进一步声明：

- 相同放置宽/长且 `stackability_id` 相同的物品才可在同一 stack；
- nesting height、最大 stack 件数；
- 每件 `maximum_weight_above`；
- 箱总重量、最大 stack density；
- 半挂车中轴/后轴最大重量；
- 仅沿水平/垂直、递增 x/y 的卸货约束。

源代码核验显示 `check_stack()` 会累计 stack 自下而上的剩余可承受重量，并真实拒绝超限，不只是排序；轴荷由货物重量一阶矩、牵引车/挂车空重、牵引座与轴距用静力平衡计算，并可对配送 group 前缀逐组检查。这是本次候选中少见的真实工况实现。

边界也必须写清：

- `boxstacks` 不是任意支撑图。上下件必须具有相同 x/y 尺寸与相同 stackability id；跨两件桥接、部分支撑、多接触件载荷分摊、局部压强均不在该模型中。
- 卸货约束是二维单调可达近似，不是带门洞、叉车转弯和扫掠体的完整运动规划。
- 半挂轴荷只覆盖其内建两反力模型（middle/rear），左右轮载、多轴组制造商载荷曲线、最小转向轴荷等需要外部模型。
- `box`/`boxstacks` 的 rotation 只有 6 个尺寸映射，不完整表达 24 个面朝向。
- 官方没有稳定 Python binding；推荐以受限子进程调用 CLI，输入/输出用版本化 CSV/JSON，并设置 wall timeout、`--time-limit`、`--memory-limit`，进程退出后再独立校验 certificate。

算法上，当前源包含 tree search、maximal-spaces tree search、dual feasible functions、sequential single knapsack、sequential value correction、column generation 与 dichotomic search。最坏复杂度仍指数级。其输出可给 primal bound、dual bound、gap；只有 bound 闭合才可标证明。固定 beam/queue 或时限下得到的是近似解。

本次还发现一个会改变架构的当前版本缺陷：官方 2026-08-29 `latest` master build 对 `variable-sized-bin-packing` 先生成候选方案后，在 `box::Solution::operator<` 比较时抛出“不支持 VariableSizedBinPacking”；`boxstacks` 内部调用 `box` 子问题同样失败。源文件对应 switch 确实没有该 case。采用它之前必须：

1. 向上游提交最小复现并等待正式修复；
2. pin 到已通过所有目标回归的 commit，而不是 `latest`；
3. 在 CI 中保留异构成本、有限 copies、箱型顺序反转测试；
4. 在修复前由 CP-SAT/SCIP 承担成本主问题。

轴荷也需要独立发布门禁。一个单件 `2 x 2 x 2`、车厢长 100 的合成用例把半挂后轴/中轴上限收紧到必须避开极端纵向位置，当前 `latest` 的 `boxstacks` 在 5 ms 内抛出 `std::bad_array_new_length`，没有 certificate。这个窄例不能证明所有轴荷输入都失败，且静力公式与最终 solution feasibility check 在源码中确实存在；它证明的是**当前 solver 搜索路径尚不能被视为已通过轴荷验收**。上线前必须最小化复现、报上游、加入正常/边界/不可行三类轴荷案例，并由独立静力计算器逐站复算。

### 6.3 OR-Tools CP-SAT：逻辑强，但不是 3D 库

官方 [bin packing 教程](https://developers.google.com/optimization/pack/bin_packing) 是按重量容量的一维 MIP 分配，并不生成三维坐标。CP-SAT Python API 有一维 `NoOverlap` 与轴对齐二维 `NoOverlap2D`；源码说明后者约束平面矩形，没有 `NoOverlap3D`。三维必须手工为每对同箱物品建立 6 个方向析取，或者采用离散空间/层分解。

适用点：

- 箱型数量与价格、分组/隔离、姿态枚举、装卸先后、软约束和词典序目标；
- 小规模直接坐标模型，返回 `OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN` 和 best objective bound；
- pattern master、容器分配与启发式后处理；
- Python wheel 覆盖主流桌面平台，Apache-2.0 适合分发。

限制：所有约束必须整数化；两两析取随 `n^2 B` 增长；通用接触面积与连续角不适合。建议先做体积、单件可装、重量和相容性预筛选，再分 cluster/箱型求解；只给 exact-small 配置承诺证明。

### 6.4 SCIP/PySCIPOpt：开放的 MIP/CIP 扩展轨

SCIP 10.0.3 本体是 Apache-2.0，PySCIPOpt 6.2.1 是 MIT。官方接口支持变量/线性与非线性表达式、branching、separator、primal heuristic、lazy constraint/constraint handler 等扩展。它比 OR-Tools 更适合：

- 连续坐标 + binary separation 的 MIP；
- 紧 big-M、LP relaxation、cut 和 lazy collision constraints 的实验；
- axle moment、固定总质量下的重心区间、载荷流 LP；
- 将定价/branch-and-price 做成长期研究模块。

它同样不含现成 3D packing constraint。PySCIPOpt wheel 的可用性不能代替模型性能基准；一般非凸 MINLP 即使能表达也可能很慢，连续 OBB 碰撞仍不宜进入首版。

### 6.5 Gurobi 与 CPLEX：性能/生态换许可证

两者的 MIP 状态、best bound、relative gap、indicator constraints、warm start 和解池都适合企业求解。Gurobi 13 的官方 nonlinear 文档描述 spatial branch-and-bound 与 outer approximation，可对其支持的非凸表达式做全局搜索；这仍不意味着任意角 OBB packing 会具有可接受规模。CPLEX 在企业已有 IBM Optimization Studio/CP Optimizer 时具有集成价值，但新项目不应同时绑定两套商业 API。

许可证事实：Gurobi 与 CPLEX Python 包均是 proprietary。免费 academic / community 或 restricted license 不能用于生产桌面分发；离线客户、CI、开发人员、云并发与 SaaS 是否允许均需采购条款确认。推荐定义内部 `ExactSolverAdapter`，开源默认 SCIP/CP-SAT，商业实现按部署授权启用。

### 6.6 `py3dbp` / `bp3d` 的真实算法边界

`py3dbp` 将物品按体积排序；对已放物品的 x/y/z 正方向面生成 pivot，尝试 6 个尺寸排列，做 AABB 相交与箱总重量检查。没有全局回溯、没有 bound，也不优化箱价。粗略朴素上界是每件遍历 `O(n)` pivots、每次与 `O(n)` 已放件相交，整批可到 `O(B n^3)`；实际很小且极快，但对输入/箱型顺序敏感。

源码还存在需要注意的控制流：`put_item()` 在找到第一个边界内姿态后，不论后续因碰撞成功与否都会 return，因此并不总会在同一 pivot 穷尽余下旋转。它不能作为“6 姿态均已尝试”的证据。

Go `bp3d` 是其来源之一。当前 `Bin.PutItem` 检查边界和相交，但未把 `GetTotalWeight + item.Weight <= MaxWeight` 放入可行性；`MaxWeight` 只是字段。README 的“based on Dube paper”也不能替代代码审计。

### 6.7 Jerry 分支与 skjolber Java 库

Jerry 分支增加 `fix_point`、`check_stable`、`support_surface_ratio`、`updown`、四象限重量比例和放置顺序输出，适合研究简单重力落地与可视化。其 README 对 `loadbear` 的描述是“高值优先排序”，代码/实测均未把它当最大上压阈值；稳定规则主要检查支持面积比及底面四角是否有支撑，不能替代重心投影落在支撑多边形、载荷传播和动态稳定。

Skjolber Java 项目相对成熟且仍维护：LAFF/plain 追求可预测时间，brute-force 文档明确只建议约 6 件以内并要求 deadline；支持障碍物、箱数量和扩展 controls。它是优秀对照与 Java 生态备选，但 placement controls 中“可考虑 stability/structural integrity”是扩展接口，不等于项目已内建这些规则。Java 不是排除理由；如果障碍物、manifest/point/placement controls 或其稳定 deadline 行为成为明确优势，可用裁剪 JRE + sidecar 接入。当前它在承压、轴荷、成本最优上没有超过 PackingSolver + CP-SAT/SCIP 组合，暂不值得为相近几何启发式增加第二个常驻运行时。

## 7. 真实约束如何进入算法

### 7.1 姿态、边界与不相交

正交模式先过滤每件允许姿态 `R_i`。放置尺寸由姿态选择变量线性组合；每件必须在箱边界内。对同箱 `i,j`，至少一个成立：

```text
x_i + dx_i <= x_j  or  x_j + dx_j <= x_i
y_i + dy_i <= y_j  or  y_j + dy_j <= y_i
z_i + dz_i <= z_j  or  z_j + dz_j <= z_i
```

MIP 用 indicator 或 6 个 binary + tight M；CP-SAT 用 `OnlyEnforceIf`。相同物品和同型空箱需加对称破除，否则搜索会重复大量等价解。

### 7.2 支撑、稳定与承压

至少分四级实现并在结果中声明等级：

1. **L0 floor/stack-only**：物品在地面或完整同底面 stack 上；PackingSolver `boxstacks` 属于此类但有真实上压累计。
2. **L1 minimum support ratio**：底面与下层顶面接触并集占比不低于阈值，且重心投影在有效支撑并集/凸包内。
3. **L2 support graph + load flow**：建立直接支撑有向无环图；上层重力通过接触边分配，用 LP 检查每件/每接触区压缩力与压强。不能把整件上层重量重复计给所有支撑者。
4. **L3 dynamics/restraint**：加入运输加速度、摩擦、倾覆边、挡块/绑带/气袋和锚点能力，通常是独立工程校核而非核心 packing decoder。

Junqueira 等包含稳定/承压的 MIP 文献说明这些约束可以离散建模，但规模和假设非常敏感。首版建议：默认 PackingSolver `boxstacks` 的保守同底面模型；需要一般支撑时由独立 verifier 做 L1/L2，失败则向求解器添加 no-good/cut 或重新生成候选，而非信任启发式分数。

### 7.3 重心、地板载荷和轴荷

若一个箱内装载总质量固定，则货物重心约束可改写为线性一阶矩界：

```text
Gx_min * sum(m_i) <= sum(m_i * (x_i + cg_local_x_i)) <= Gx_max * sum(m_i)
```

箱内选件使分母也变化时，直接比值是分式；可以仍用交叉相乘（总质量为正且质量常数）、按候选箱 assignment 分开，或对载荷区间做保守线性约束。轴反力在简单两支点/半挂模型中也是重量一阶矩的线性函数；复杂多轴、左右轮和制造商载荷曲线应用分段线性包络或独立校核。

PackingSolver `boxstacks` 的半挂模型可直接利用，但必须校准其轴距/空重/牵引座参数，并补充左右偏载与实际车辆规则。普通 `box`、`py3dbp` 的箱总重量并不代表重心/轴荷支持。

### 7.4 多站点与装卸顺序

由后门沿 x 轴装卸时，保守规则可要求早卸 group 不被晚卸 group 在门方向阻挡；PackingSolver 的 increasing x/y unloading 是类似二维近似。完整可执行性还包含：

- 货物通过门洞；
- 搬运设备和货物 sweep volume 无碰撞；
- 上方/前方遮挡、允许临时重搬；
- 多扇门和每站可用门；
- 装货顺序是卸货顺序的可执行逆序。

建议先提供 `STRICT_LIFO_AXIS`、`NO_REHANDLE_APPROX`、`POSTCHECK_PATH` 三档。运动路径用独立几何/规划模块验证，不要把 x 单调约束描述成完整 forklift path planning。

### 7.5 空隙与固定

“空白体积大于阈值就需要固定”不是可靠物理规则。算法可以输出空余空间分解、每件六面间隙、靠墙/靠块关系和连通空腔；固定模块再依据运输加速度、摩擦、可滑移距离和可用材料生成挡块/气袋/绑带候选。固定材料要作为有尺寸/重量/成本的对象回灌，并重新校验边界、重量、轴荷和压强。

## 8. 任意角装箱：单独技术路线

### 8.1 为什么正交算法不能小改得到任意角

给定 OBB 中心 `c`、半边长 `h` 与旋转矩阵 `R`，边界约束、OBB-OBB 不相交和接触面都会依赖角度。两个 OBB 的 Separating Axis Theorem 最多检查 15 个候选轴（两盒各 3 个面法向及 9 个叉积轴）；“至少存在一个分离轴”又是非凸析取。角度连续时，旋转矩阵含 sin/cos 或四元数单位范数，支撑接触和重心投影也随角度变化。

所以：

- PackingSolver `irregular` 的连续 rotation 是 **二维多边形** nesting，不能用于三维箱体；
- 把旋转后 OBB 换成 AABB 会过度保守，有时又因错误接触假设产生不稳定方案；
- Gurobi/SCIP 能表达部分非凸函数，不代表数百件 OBB packing 可实用求解；
- Bullet/物理仿真得到“若干步没有倒”不是全局优化或安全证明。

### 8.2 可落地三档

| 模式 | 求解表示 | 适用 | 保证/边界 |
|---|---|---|---|
| `ORTHOGONAL_SET` | 24 面语义姿态映射到有限轴向尺寸 | 默认物流箱、托盘、车辆 | 最成熟；可用 PackingSolver/CP/MIP |
| `DISCRETE_POSES` | 工程师批准的若干固定旋转矩阵；预计算 OBB | 长件斜靠、门洞特殊通过 | 对列出的姿态搜索，不代表连续角全局最优 |
| `CONTINUOUS_ENVELOPE` | 四元数/角区间 + 非凸碰撞优化 | 少量高价值特殊件、专家模式 | 高成本；必须二次碰撞/稳定/路径验证 |

离散姿态模式可复用成熟 [FCL](https://github.com/flexible-collision-library/fcl) 做 OBB/凸体碰撞检测，或用 [trimesh](https://github.com/mikedh/trimesh) 管理网格与变换；它们是几何内核，不是 packing optimizer。搜索仍建议限定为很少物品、很少候选姿态，以 PackingSolver 的正交方案为初始解，再在局部空区做 pose neighborhood search。任何斜放结果应输出碰撞余量、接触面、重心投影、最大倾角和固定要求，并强制人工签核。

## 9. 本地受控实测

### 9.1 仓库内可复现基准

可复现实测脚本与机器可读结果位于：

- `benchmarks/run_controlled.sh`
- `benchmarks/benchmark_packingsolver.py`
- `benchmarks/benchmark_py3dbp.py`
- `benchmarks/benchmark_jerry.py`
- `benchmarks/benchmark_ortools.py`
- `results/*.json` 与 `results/raw/*.resources.txt`

Skjolber 的 Java/Maven 用例另位于 `benchmarks/java-skjolber/`，结果为 `results/skjolber.json`。

共同限制：单线程环境变量、虚拟内存上限 4 GiB、外层 35 s timeout；PackingSolver 另设 10 s solver time 与 1024 MiB memory。所有坐标由独立 AABB/重量验证器复算。结果快照：

| 组件/案例 | 结果 | wall / max RSS（整个脚本） | 结论 |
|---|---|---|---|
| PackingSolver 8 个 `5^3` 立方体装 `10^3` | 1 箱、8 件、独立校验通过 | 5.06 s / 15,168 KiB（全 8 案例） | 基础正交输出可靠 |
| PackingSolver 方向允许 | 必须旋转后装入，1 件通过 | 同上 | 6 旋转子集有效 |
| PackingSolver 方向禁止 | 0 件，正确不装 | 同上 | 约束有效；“必须全装”需业务层检查 |
| PackingSolver 箱总重量 | 3 个重 6 的物品分 3 箱（每箱上限 10） | 同上 | 重量约束有效 |
| PackingSolver `boxstacks` 上压 | 脆弱件置顶，累计上压无违规 | 同上 | 内建 stack 上压真实生效 |
| PackingSolver 异构成本 | `box`、`boxstacks` 均 return code 1，无 certificate | 约 1.00 s / case | 当前滚动版本阻断项 |
| PackingSolver 半挂窄轴荷合成例 | return code 1，`std::bad_array_new_length`，无 certificate | 0.0046 s / case | 只说明该边界搜索路径未通过；不得泛化为全部轴荷配置 |
| `py3dbp` 基础/旋转/重量 | 均几何校验通过 | 0.03 s / 13,696 KiB | 可作极轻 baseline |
| `py3dbp` 异构箱顺序 | 小箱先用 2 箱；大箱先用 1 箱 | 同上 | 明显顺序敏感，不按成本优化 |
| Jerry 分支反例 | `fragile` 上方实际重量 20，仍判可行 | 1.13 s / 70,688 KiB | `loadbear` 不是硬承压约束 |
| OR-Tools 9 个 `5^3` 立方体 | `OPTIMAL`，2 箱，best bound 2 | 0.40 s / 101,072 KiB | 小规模 pairwise CP-SAT 能证明 |
| PySCIPOpt/SCIP 同一 9 立方体例 | `optimal`，2 箱，dual 2，gap 0；9 件独立校验通过 | 0.14 s / 60,760 KiB；solver 0.055 s | 开源 exact-small 第二实现通过 |
| Skjolber LAFF | 网格、3D 旋转、upright 禁止、重量均符合预期；100 异质件装入 1 箱 | 缓存依赖后冷 JVM 0.24 s / 76,088 KiB；100 件库内 12 ms | 活跃 Java 启发式可作强对照；未测试承压/轴荷/成本最优 |

PackingSolver 的 8 案例脚本时长包含多个 CLI 各自约 1 s 的 solver time；Skjolber 同时报告冷 JVM 与库内 duration。它们都不应与单个 Python case 的微秒数直接作性能排名。

### 9.2 本次补充的求解器烟雾测试

同一最小成本实例：两件 `10 x 10 x 10`；候选为两个 `10 x 10 x 10` 小箱（单价 5）和一个 `20 x 10 x 10` 大箱（单价 8）。手工建立固定姿态、分配与六向分离模型，限制单线程/2 s：

| 求解器 | 安装版本 | 状态 | 目标 / bound / gap | wall / max RSS |
|---|---|---|---|---|
| OR-Tools CP-SAT | 9.15.6755 | `OPTIMAL` | 8 / 8 / 0 | 0.34 s / 95,268 KiB |
| PySCIPOpt + SCIP | 6.2.1 + 10.0 | `optimal` | 8 / 8 / 0 | 0.13 s / 46,160 KiB |
| Gurobi | 13.0.3 restricted non-production license | status 2 (`OPTIMAL`) | 8 / 8 / 0 | 0.03 s / 24,508 KiB |
| CPLEX | wheel 22.2.0.1；引擎 22.2.0.0 | `integer optimal solution` | 8 / 8 / 0 | 0.04 s / 27,580 KiB |

这些数字只证明历史运行中的官方 wheel 在 x86-64 Linux 环境可安装、模型语义正确、能返回界；实例太小，**不能**据此排名真实性能。原始结构化记录在 `raw/experiments/commercial/`，复跑入口为 `benchmarks/benchmark_gurobi.py` 和 `benchmarks/benchmark_cplex.py`；当前发布环境没有这些包或运行时许可，脚本会明确返回 `NOT_RUN`。Gurobi 测试明确输出 restricted、non-production license；CPLEX wheel 的 community/许可条件同样不能外推到生产。

另一个 PackingSolver 对照把同一 `bin-packing` 输入箱型顺序反转：小箱在前得到 2 箱且报告 gap 0；大箱在前得到 1 箱且 gap 0。这两个“证明”针对的是它按给定 bin 序列定义的普通目标，进一步证明不能用该目标代替 variable-sized cost selection。

## 10. 推荐求解架构

### 10.1 引擎分层

```text
ProblemSpec
   |
   +-- precheck / dominance / clustering
   |
   +-- CostAllocator (CP-SAT default; SCIP/Gurobi/CPLEX optional)
   |      |
   |      +-- candidate bin counts / pattern master
   |
   +-- OrthogonalPlacementEngine
   |      +-- PackingSolver box
   |      +-- PackingSolver boxstacks
   |      +-- ExactSmall CP-SAT/SCIP direct model
   |
   +-- DiscretePoseExpert (later; OBB collision checker)
   |
   +-- IndependentValidator
          +-- completeness / bounds / collision / orientation
          +-- support / load flow / COG / axle / unloading
          +-- fixation and operator-signoff requirements
```

`CostAllocator` 与 placement 不是一次性串行：主问题提出箱型/物品 cluster，放置器若证实不可行就返回 conflict/no-good；放置器生成的新 pattern 回到主问题，迭代到预算结束。保存每轮的候选、不可行原因、incumbent、bound 与随机种子，GUI 才能解释“为何多用一辆车”。

### 10.2 首版算法组合

1. 预处理删除单件绝不可能装入的箱型-姿态，计算体积/重量/单维下界、箱型 dominance 和相容组。
2. CP-SAT 先解数量/价格/重量/相容性的松弛主问题，得到低成本箱型组合和可报告下界。
3. 对每个候选箱调用 PackingSolver：一般正交用 `box`；启用保守堆栈、上压或半挂轴荷时用 `boxstacks`。
4. 多个排序/guide/随机种子产生候选 pattern；CP-SAT/SCIP 在 pattern 池上重选最小成本组合。
5. 独立 validator 逐件复算，任何硬约束失败则拒绝并加入 no-good；不允许仅作 warning 后交付。
6. 小于配置阈值（例如 10--30 件，实际阈值由基准决定）时并行启动单 worker exact-small；若证明完成则升级状态，否则保留 incumbent/gap。
7. 所有解输出 `solver_id/version/commit/hash`、输入 hash、time/memory、seed、状态、primal/dual/gap、约束覆盖清单和未在 solver 内表达但已 postcheck 的规则。

### 10.3 不建议的方案

- 不直接 fork `py3dbp` 持续堆功能；它的 decoder 和数据结构太薄，最终会变成自行重写求解器。
- 不把 Jerry 的 `loadbear`、四象限 `gravity` 或 support ratio 标成工程承压/轴荷证明。
- 不在 GUI 线程内运行任何求解器；CLI 进程必须可取消、超时后可强杀并保留最后完整 certificate。
- 不同时在首版维护 OR-Tools、SCIP、Gurobi、CPLEX 四套完整直接 3D 模型；先定义中立模型测试，默认 CP-SAT，SCIP 做高级研究轨，商业适配按客户需求。
- 不承诺连续任意角全局最优；先收集真实案例，确认正交/离散姿态确实不足再投资。

## 11. 算法验收与基准建议

### 11.1 数据集

至少保留三层：

- **经典几何基准**：Martello/Pisinger/Vigo、Bischoff/Ratcliff（BR）等公开实例，用于与论文装载率/箱数比较；
- **构造真值实例**：整齐网格、必须旋转、禁止翻转、成本 dominance、有限 copies、重量、同底面上压、部分支撑反例；
- **脱敏真实订单**：按弱/强异质、件数、姿态受限比例、重量/体积密度、站点数和箱型数分层。

经典 BR 实例主要测几何，不含本产品全部工况；不能用 BR 装载率证明承压或轴荷正确。

### 11.2 指标

- 硬约束合法率必须 100%；
- 必装完整率、总成本、箱数、体积/重量利用率；
- 对 exact-small：objective、best bound、gap、证明率、节点/冲突数；
- 对启发式：固定 wall time 下 best/median/p95、不同 seed 方差、相对已知最优/下界 gap；
- 支撑面积最小余量、承压最小余量、重心/轴荷余量、重搬次数；
- wall、CPU、peak RSS、取消延迟和无有效解超时比例。

每次算法/依赖升级都要跑：箱型顺序反转、单位缩放、相同物品置换、坐标平移/镜像、价格等比例缩放等 metamorphic tests。求解器输出与独立 validator 必须版本隔离，避免同一 bug 同时存在于生成和校验代码。

## 12. 官方与源码证据索引

### 12.1 软件

1. PackingSolver repository、功能与命令示例：<https://github.com/fontanf/packingsolver>；滚动 release：<https://github.com/fontanf/packingsolver/releases/tag/latest>；MIT：<https://github.com/fontanf/packingsolver/blob/master/LICENSE>。
2. PackingSolver `boxstacks` 数据结构（stackability、maximum weight above、truck data）：<https://github.com/fontanf/packingsolver/blob/master/include/packingsolver/boxstacks/instance.hpp>；承压与轴荷校验：<https://github.com/fontanf/packingsolver/blob/master/src/boxstacks/solution.cpp>；半挂静力公式：<https://github.com/fontanf/packingsolver/blob/master/include/packingsolver/algorithms/truck.hpp>。
3. PackingSolver 当前 variable-sized 缺失 switch 的源码：<https://github.com/fontanf/packingsolver/blob/master/src/box/solution.cpp>。
4. OR-Tools repository/license：<https://github.com/google/or-tools>；CP-SAT 整数与状态说明：<https://developers.google.com/optimization/cp/cp_solver>；官方一维 bin-packing 示例：<https://developers.google.com/optimization/pack/bin_packing>；Python `NoOverlap2D` 源码：<https://github.com/google/or-tools/blob/stable/ortools/sat/python/cp_model.py>。
5. SCIP 10：<https://github.com/scipopt/scip>；PySCIPOpt：<https://github.com/scipopt/PySCIPOpt> 与 <https://pyscipopt.readthedocs.io/en/latest/>。
6. Gurobi product/API：<https://www.gurobi.com/product>；nonlinear / spatial branch-and-bound：<https://docs.gurobi.com/projects/optimizer/en/current/features/nonlinear.html>；13.0 release notes：<https://docs.gurobi.com/projects/optimizer/en/current/reference/releasenotes.html>；academic license 不是生产许可：<https://support.gurobi.com/hc/en-us/articles/360040541251-How-do-I-obtain-a-free-academic-license>。
7. IBM CPLEX Optimization Studio：<https://www.ibm.com/products/ilog-cplex-optimization-studio>；定价与 academic initiative：<https://www.ibm.com/products/ilog-cplex-optimization-studio/pricing>；Python package：<https://pypi.org/project/cplex/>。
8. `py3dbp`：<https://github.com/enzoruiz/3dbinpacking> 与 <https://pypi.org/project/py3dbp/>；Go `bp3d`：<https://github.com/gedex/bp3d>；Jerry 分支：<https://github.com/jerry800416/3D-bin-packing>；Skjolber Java：<https://github.com/skjolber/3d-bin-container-packing>。

### 12.2 论文

论文按原始出版页/DOI 列出；每篇的算法性质与本项目意义见下一节补充表。

#### 12.2.1 分类、精确法与正交启发式

| 论文 | 原始贡献 | 算法性质与本项目边界 |
|---|---|---|
| Wäscher, Haußner, Schumann (2007), *An improved typology of cutting and packing problems* ([DOI](https://doi.org/10.1016/j.ejor.2005.12.047)) | 按物品/容器维度、同质性、选择与分配目标整理 cutting & packing 分类。 | 定义 `problem_kind` 的主要依据；是分类论文，不提供求解算法。 |
| Martello, Pisinger, Vigo (2000), *The Three-Dimensional Bin Packing Problem* ([DOI](https://doi.org/10.1287/opre.48.2.256.12386)，[机构摘要](https://cris.unibo.it/handle/11585/915180)) | 相同 3D 箱最少箱数；下界、单箱精确填充、外层 branch-and-bound，并嵌入近似算法；原摘要报告最多 90 件的试验。 | 精确搜索闭合才证明最优，最坏指数。论文给出的 continuous lower bound asymptotic worst-case ratio `1/8` 是**下界质量性质**，不是“所得方案最多差 1/8”。不覆盖真实工况约束。 |
| Fekete, Schepers, van der Veen (2007), *An Exact Algorithm for Higher-Dimensional Orthogonal Packing* ([DOI](https://doi.org/10.1287/opre.1060.0369)，[作者 PDF](https://arxiv.org/pdf/cs/0604045)) | 用每个轴的 interval graph 组成 `packing class`；结合 conservative scales，下界与两层树搜索判定 orthogonal packing。 | 固定方向的精确 oracle；OPP 强 NP-hard、树最坏指数。不直接处理六向姿态选择、承压或斜角。 |
| Nascimento, Queiroz, Junqueira (2021), *Practical constraints in the container loading problem: Comprehensive formulations and exact algorithm* ([DOI](https://doi.org/10.1016/j.cor.2020.105186)) | 迭代 ILP/CP，并基于平面装箱松弛；统一建模 complete shipment、冲突、优先、重量、稳定、承压、多站、平衡、人工装载、分组、分隔、多姿态等 12 类约束。摘要报告约 10 item types/110 件，全部测试中超过 70% 得到最优。 | 最接近多约束的精确研究入口；仍是 single-container，最坏指数。110 件多含 type 聚合，不能理解为任意 110 个独特物品的普遍性能。 |
| Paquay, Schyns, Limbourg (2014), *A mixed integer programming formulation for the three-dimensional bin packing problem deriving from an air cargo application* ([DOI](https://doi.org/10.1111/itor.12111)) | 多箱尺寸、稳定、脆弱、重量分布、箱体旋转，并处理航空截角平行六面体容器的 MILP。 | 小实例验证的精确模型；证明了约束可统一表达，不证明模型能扩展到大订单。 |
| Crainic, Perboli, Tadei (2008), *Extreme Point-Based Heuristics for Three-Dimensional Bin Packing* ([DOI](https://doi.org/10.1287/ijoc.1070.0250)) | 系统定义 3D extreme points，构造与具体目标相对解耦的 placement 候选，并讨论附加约束。 | 构造启发式，无最优/近似比；适合作为生产候选点与 anytime 初解。 |
| Fanslau, Bortfeldt (2010), *A Tree Search Algorithm for Solving the Container Loading Problem* ([DOI](https://doi.org/10.1287/ijoc.1090.0338)) | 广义 block building、partition-controlled tree search；区分 full-support / no-support，可考虑 guillotine cut。 | 有限宽树搜索是启发式，未截断搜索最坏指数；full support 只是几何规则，不等于承压合格。 |
| Pisinger (2002), *Heuristics for the container loading problem* ([DOI](https://doi.org/10.1016/S0377-2217(02)00132-7)) | 经典 wall-building/层块单箱启发式和 benchmark 比较。 | 成熟、可复现基线；无最优证明，也不是现代工况统一模型。 |
| Crainic, Perboli, Tadei (2009), *TS2PACK: A two-level tabu search for the three-dimensional bin packing problem* ([DOI](https://doi.org/10.1016/j.ejor.2007.06.063)) | 外层改进分箱，内层改进箱内可行性/布局的两层 tabu search。 | 元启发式；无全局证明，但支持本报告“分配 + 放置”分层设计。 |
| Zhao, Bennell, Bektaş, Dowsland (2014), *A comparative review of 3D container loading algorithms* ([DOI](https://doi.org/10.1111/itor.12094)) | 对 3D CLP 算法设计和 benchmark 作系统比较。 | 用于选择基准与理解历史算法；综述排名不能代替本项目约束下的本地实测。 |

#### 12.2.2 异构尺寸、价格和有限库存

| 论文 | 原始贡献 | 可迁移结论与边界 |
|---|---|---|
| Crainic, Perboli, Rei, Tadei (2011), *Efficient lower bounds and heuristics for the variable cost and size bin packing problem* ([DOI](https://doi.org/10.1016/j.cor.2011.01.001)，[作者稿](https://iris.polito.it/bitstream/11583/2374786/2/2374786.pdf)) | 异构容量、固定选择成本、有限可用箱；knapsack/column-generation 下界与 BFD 类启发式；特别说明成本未必与容积成比例，试验达 1000 items。 | 这是**一维容量** VCSBPP。可迁移成本/库存语义、主问题和下界，绝不能把千件实验当三维布局性能。 |
| Pisinger, Sigurd (2005), *The two-dimensional bin packing problem with variable bin sizes and costs* ([DOI](https://doi.org/10.1016/j.disopt.2005.01.002)) | 2D 变尺寸/成本，Dantzig-Wolfe、下界和 branch-and-price。 | 精确框架可迁移；3D pricing 子问题明显更难。 |
| Correia, Gouveia, Saldanha-da-Gama (2008), *Solving the variable size bin packing problem with discretized formulations* ([DOI](https://doi.org/10.1016/j.cor.2006.10.014)) | variable-size BPP 的离散整数模型及加强。 | 主要是一维容量，不是三维布局算法。 |
| Alvarez-Valdes, Parreño, Tamarit (2015), *Lower bounds for three-dimensional multiple-bin-size bin packing problems* ([DOI](https://doi.org/10.1007/s00291-013-0347-2)) | 三维 multiple-bin-size BPP 下界。 | 可用于报告 gap 和剪枝；下界论文不等于完整工况求解器。 |

这组论文共同支持 set-partitioning / pattern master：pattern `p` 带箱型 `t(p)`、成本 `c_t` 和每类物品数量 `a_ip`；选择整数 `lambda_p` 满足需求、箱型库存并最小化成本。无限数量必须在数据中显式表达为 unbounded，而不是无依据的大数。

#### 12.2.3 支撑、静态稳定与承压

| 论文 | 原始贡献 | 边界 |
|---|---|---|
| Junqueira, Morabito, Yamashita (2012), *Three-dimensional container loading models with cargo stability and load bearing constraints* ([DOI](https://doi.org/10.1016/j.cor.2010.07.017)) | 在 3D CLP 数学模型中显式加入 stability 与 load-bearing，是后续综合模型基础。 | MIP 搜索闭合才证明；载荷传播是模型假设，不等于有限元、包装试验或认证。 |
| Christensen, Rousøe (2009), *Container loading with multi-drop constraints* ([DOI](https://doi.org/10.1111/j.1475-3995.2009.00714.x)) | 建材配送 hard multi-drop；无需移动其他箱即可取货，同时检查 load bearing 和下方支撑；dynamic-width tree search。 | 实用启发式，无全局保证；显示卸货顺序与支撑/承压必须联合处理。 |
| Martínez-Franco, Céspedes-Sabogal, Álvarez-Martínez (2020), *PackageCargo: A decision support tool ... with stability* ([DOI](https://doi.org/10.1016/j.softx.2020.100601)) | 数学稳定指标，并用 Unity/PhysX 做仿真验证的开源决策支持工具。 | Metaheuristic + 近似物理仿真；仿真不能替代强度试验和工程签核。 |
| Bortfeldt, Wäscher (2013), *Constraints in container loading - A state-of-the-art review* ([DOI](https://doi.org/10.1016/j.ejor.2012.12.006)) | 权威分类方向、稳定、承压、重量分布、分组、装卸等实际约束。 | 是需求字典和文献入口，不提供统一算法保证。 |

两个反例应进入单元测试：底面 70% 被支撑仍可能全部位于重心一侧；重心投影在支撑凸包内仍可能只通过一个很小接触角传力而压坏下件。因此 support area、重心 margin、接触载荷和剩余承压裕量要分别报告。

#### 12.2.4 重量分布、轴荷与多站状态

| 论文 | 原始贡献 | 算法性质与边界 |
|---|---|---|
| Davies, Bischoff (1999), *Weight distribution considerations in container loading* ([DOI](https://doi.org/10.1016/S0377-2217(98)00139-8)) | 经典 container-loading 重量空间分布研究。 | 说明体积利用率以外必须优化/约束载荷分布；不自动覆盖具体车型轴系。 |
| Ramos, Silva, Oliveira (2018), *A new load balance methodology for container loading problem in road transportation* ([DOI](https://doi.org/10.1016/j.ejor.2017.10.050)) | 面向道路运输提出装载平衡方法。 | 平衡指标不等同于每轴法定限制，仍需车辆静力模型。 |
| Krebs, Ehmke (2021), *Axle Weights in combined Vehicle Routing and Container Loading Problems* ([开放论文/DOI](https://doi.org/10.1016/j.ejtl.2021.100043)) | 从静力学推导有/无挂车及不同轴配置公式；嵌入 2L/3L-CVRP；外层 ALNS，内层 Deepest-Bottom-Left-Fill，并强调每次放置后检查轴荷。 | 混合启发式，无全局保证；轴荷可行性应是硬校验。 |
| Pollaris (2017), *Loading constraints in vehicle routing problems: a focus on axle weight limits* ([DOI](https://doi.org/10.1007/s10288-017-0352-4)) | 聚焦轴荷的车辆路径/装载约束研究。 | 支持“路由与装载不能完全割裂”的架构判断。 |

对多站任务，出发状态合格不代表每次卸货后的剩余载荷仍合格；每站都要重新计算总重心、轴/轴组反力、左右轮差、地板载荷和剩余堆叠稳定。

#### 12.2.5 多站卸货与可达性

| 论文 | 原始贡献 | 算法性质与边界 |
|---|---|---|
| Ceschia, Schaerf (2013), *Local search for a multi-drop multi-container loading problem* ([DOI](https://doi.org/10.1007/s10732-011-9162-6)) | 多站、多容器局部搜索。 | 元启发式，无全局证明。 |
| Junqueira 等, *MIP-based approaches for the container loading problem with multi-drop constraints* ([DOI](https://doi.org/10.1007/s10479-011-0942-z)) | 用 MIP 表达 multi-drop 约束。 | 小实例可精确，最坏指数。 |
| Bonet Filella, Trivella, Corman (2023), *Modeling soft unloading constraints in the multi-drop container loading problem* ([DOI](https://doi.org/10.1016/j.ejor.2022.10.033)) | 允许倒箱并按被移动体积、重量和移动类型计罚；小实例 MILP，大实例随机 EP + destroy/reconstruct。 | 小实例闭合可证明；大实例启发式。比把所有遮挡直接判死更贴合实际业务。 |

正交“无遮挡”常用保守规则是：若两件在门截面投影相交，晚卸件不能挡在早卸件与门之间。它只证明直线抽取近似，不证明叉车能接近、货能过门或能在门外转向。

#### 12.2.6 连续旋转与三维 irregular packing

| 论文 | 原始贡献 | 算法性质与边界 |
|---|---|---|
| Egeblad, Nielsen, Brazil (2009), *Translational packing of arbitrary polytopes* ([DOI](https://doi.org/10.1016/j.comgeo.2008.06.003)) | 任意多面体的几何与平移装箱。 | 标题即限定 translational，姿态固定；不是连续旋转证据。局部搜索无全局保证。 |
| Romanova, Bennell, Stoyan, Pankratov (2018), *Packing of concave polyhedra with continuous rotations using nonlinear optimisation* ([DOI](https://doi.org/10.1016/j.ejor.2018.01.025)，[作者稿入口](https://eprints.soton.ac.uk/418130/)) | 凹多面体、连续旋转与非线性优化。 | 连续非凸 NLP/多启动通常只有局部结果；碰撞模型和数值容差远难于正交问题。 |
| Lamas-Fernandez, Martinez-Sykora, Bennell (2023), *Voxel-Based Solution Approaches to the Three-Dimensional Irregular Packing Problem* ([DOI](https://doi.org/10.1287/opre.2022.2260)，[作者稿入口](https://eprints.soton.ac.uk/454733/)) | voxel 几何、数学模型、局部邻域和 metaheuristic，用于 3D irregular objects。 | 分辨率带来内存/速度/几何误差权衡；体素可行不等于连续公差下可行，无全局保证。 |
| Romanova 等 (2020), *Packing Oblique 3D Objects* ([DOI](https://doi.org/10.3390/math8071130)) | oblique 3D objects 的数学建模与优化，开放获取。 | 适合作为实验 NLP 路线，不是大规模物流统一精确解。 |
| Cano, Torra (2009), *Container Loading for Nonorthogonal Objects with Stability and Load Bearing Strength Compliance* ([DOI](https://doi.org/10.1109/LINDI.2009.5258764)) | 多面体表示正交/非正交物品，考虑三维旋转权限、承压和最小稳定度的构造状态。 | 启发式，无全局证明；“稳定度”仍是简化模型指标。 |

给定姿态的 OBB 碰撞检测、连续姿态搜索和可执行装入路径是三个不同问题。以上文献支持把连续角放到独立实验 capability，而不是给正交库增加一个 `allow_tilt=true` 就对外声称支持。

## 13. 公共实例复核补充

ESICUP THPACK9 instance 1 已按同一物品清单复跑：PackingSolver 修复版 25 箱，Skjolber
LAFF 28 箱，py3dbp/Jerry 各 50 箱，均 70/70 件且 validator 通过。数据文件没有
known optimum；体积下界 19，所以这些都是 feasible incumbent。异构成本的原始
PackingSolver 失败及两文件最小修复见 [packingsolver-upstream.md](packingsolver-upstream.md)。

矩阵化的逐特性 ✅/❌/⚠️ 结论（含前端选型与导出格式）集中在
[decision-matrices.md](decision-matrices.md)，避免将“建模引擎可表达”误写成“库原生实现”。
