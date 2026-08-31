# Benchmark 执行优先级与全库横评建议

本文回答“BR/LN 之外先补什么、为什么补、哪些库能参加、结果能证明什么，以及何时才可以称为 ALL libs 完整数据”。完整的问题定义和逐套件适用性见 [benchmark-selection.md](./benchmark-selection.md)；本文增加执行顺序、比较边界和范围外风险。

## 1. 结论

建议保留 B01-B32，不把所有套件压成一个总分。它们分成四个需要分别回答的问题：

| 层级 | 套件 | 必须回答的问题 | 是否进入数值质量排行 |
|---|---|---|---|
| P0 公共核心 | B01-B07 | 在公开正交实例上，谁能给出合法解、解质量怎样、何时需要 exact oracle | 是，按 volume knapsack、profit knapsack、identical-bin packing、exact proof 分开 |
| P0 目标/约束合规 | B08-B18 | 成本、异构箱、开放维度和硬约束是否被真正表达与执行 | 只有相同语义的实现进入；硬约束先按合规率筛选 |
| P1 工业问题 | B19-B23、B30-B32 | 真实车辆/托盘/路线/货架/在线流程能否端到端保真 | 是，但只在 `FULL` 轨；投影结果单独展示 |
| P0 工程可靠性 | B24-B29 | 输入重排、单位、seed、规模、取消和崩溃是否可控 | 作为 reliability/scalability 排行，不与解质量合并 |

“ALL libs”应理解为每个库在每个套件都有一条状态记录，而不是强行让不支持该问题的库产出一个数字。`NOT_SUPPORTED`、`ADAPTER_MISSING`、`PROJECTION_ONLY` 和运行失败都要进入分母；只有输入、语义、预算和 validator 相同的有效证书才能进入数值榜。

### 1.1 覆盖审计：为什么 BR/LN 之外不能只再加一个 benchmark

BR/LN 只回答“单个固定容器里，几何启发式能塞进多少体积”。它们没有覆盖“必须装完后的箱数”“价值选择”“箱型价格”“开放尺寸”“运输约束”“仓储顺序”或“在线重排”。因此不能用一个更大的单箱数据集替代下面的正交问题族：

| 应用/问题族 | 必选套件 | 主要验收问题 | 如果缺失会留下的误判 |
|---|---|---|---|
| 单箱正交装载、分布外困难尺寸 | B01、B02、B07 | 可行率、packed volume、预算响应、困难桶鲁棒性 | 把某一套尺寸分布上的好成绩当成通用几何能力 |
| 价值/利润装载 | B03、B06 | 是否优先保留高价值件；小规模 objective/bound 是否闭合 | 只按体积装得满，却错过业务价值；启发式被误称为最优 |
| 同型多箱、外部分布复核 | B04、B05 | 必须完整装完时的箱数、完整率和跨分布质量 | 只在 THPACK9 上调参过拟合，无法判断多箱泛化 |
| 异构箱型、成本、库存和开放维度 | B08、B09、B10、B11 | 成本方向、有限 copies、箱型分配、最小开放长度/高度 | 把“箱数少”误当“成本低”，或把封闭箱结果冒充 strip/open-dimension 能力 |
| 姿态、重量、支撑与静力安全 | B12、B13、B14、B15 | 姿态白名单、总重、支撑/上压、重心/轴荷硬约束 | 仅检查 AABB 就宣称可运输，漏掉最危险的硬约束 |
| 入口、障碍、多站卸货和业务隔离 | B16、B17、B18 | 门洞/keepout、无遮挡和重搬、温区/危化相容性 | 终点几何可行但无法装入、卸货或合规隔离 |
| 工业车辆/托盘/路线/非规则件/真实订单 | B19、B20、B21、B22、B23 | FULL 语义的需求完成、路线时间窗、非规则碰撞和分布迁移 | 删除业务字段后得到漂亮数字，却无法支持真实作业 |
| 仓储货架、mixed-SKU 托盘、在线到货 | B30、B31、B32 | bay/shelf 顺序、层型/承压、到货序列和重排代价 | 用离线自由装箱结果替代仓储和实时作业决策 |
| 工程可靠性与部署 | B24–B29 | 表示不变性、数值、重复性、规模、取消/崩溃恢复 | 质量均值好看，但换顺序、换单位或超时后不可托管 |

这张表是覆盖门，不是总分权重：每一行至少要有一个真实 benchmark；其中 B14/B15/B17/B18 的 hard 失败不能被其他行的利用率或箱数抵消。B22 的 `NOT_SUPPORTED` 也应作为能力边界发布，不能把非规则件包成 AABB 后算作已覆盖。

### 1.2 先跑什么：推荐的“完整一波”边界

建议把“凑齐一波后跑 ALL libs”定义成一个可审计的 Wave 1，而不是把尚未冻结的数据源混进数字榜：

| 波次 | 套件 | 参加者 | 进入数值榜的条件 | 当前状态/动作 |
|---|---|---|---|---|
| Wave 1A 公共几何 | B01–B07 | 每个库都生成 `NATIVE`、`COMPOSED`、`PROJECTION_ONLY` 或 `NOT_SUPPORTED` 状态；可表达者全跑 | 输入 hash、姿态语义、预算和 validator 完全相同；B03 固定姿态与全旋转分榜 | B07 已有大规模 projection；补 Skjolber adapter 和 exact 小子集，随后全库复跑 |
| Wave 1B 真值校准 | B06、B09 | CP-SAT/SCIP/Gurobi/CPLEX；启发式只作 incumbent 对照 | primal/dual bound 闭合才显示 `PROVEN_OPTIMAL` | B06 有局部记录；先完成统一 B09 exact truth |
| Wave 2 目标与硬约束 | B08–B18 | 能保真表达者原生/组合运行，其余登记状态 | hard violation=0 且必装件完整后，才比较成本/箱数 | B08/B10/B11 先冻结来源；B12–B18 逐库补 conformance adapter |
| Wave 3 工业专项 | B19–B23、B30–B32 | 只对有 FULL adapter 的库做 full；其他做明确 projection/status | full 轨保留车辆、站点、日期、货架或 online 语义 | 当前多为 `ADAPTER_MISSING`/`SOURCE_PENDING`，不得用几何投影填数 |
| Wave 4 可靠性 | B24–B29 | 全部实际部署候选及其 worker/sidecar | 原始 artifact、取消和恢复状态完整；随机算法至少 5 seed | 在 Wave 1–3 代表实例上重复，形成 release gate |

所以“ALL libs”应当有两个同时成立的条件：一是每个库对每个 benchmark 都有可追溯状态行；二是每个可比轨道都完成同一输入和 validator 的实例级运行。仅有第一条只能叫 capability census，只有第二条才可以发布该轨道的质量/性能排行。

## 2. 建议的运行波次

### Wave 0：来源和语义门禁

先冻结 B05、B08、B10、B11、B23、B30 的原始文件、许可证、姿态规则、输入 hash 和 canonical 转换。B31/B32 固定生成器版本、父实例 hash、seed 和参数。来源不完整时保持 `SOURCE_INCOMPLETE/SOURCE_PENDING`，不能用自生成数据冒充公开 benchmark。

### Wave 1：公共质量主线，全库优先

先运行 B01-B07。每个实现至少固定两个时间预算（建议 1 s、10 s；exact 另设 20/60 s），并统一报告：

- `solution_status`、合法率和完整率；
- 主目标（体积、profit、箱数）及中位数/p95；
- `time_to_first_feasible`、wall/solver time、峰值 RSS；
- 有 published optimum/bound 时才报告 gap，否则只报告 incumbent 和体积下界诊断；
- 固定姿态、全旋转投影、composed adapter、exact model 分轨。

B03 已证明姿态语义必须单独分轨；B04 的 THPACK9 不能代表所有多箱分布，因此 B05 是必要的外部复核，B06 是必要的真值校准，B07 用于 BR/LN 之外的困难单箱分布。B07 的 projection 轨目前已覆盖八个 Python/Go/Rust 实现（900 例、两排序、1/10 s），但 Skjolber 与 exact 仍须保持 `ADAPTER_MISSING`，不能用 projection 数字替代它们。Jerry 的 `fix_point=True` overlap 与 `fix_point=False` control 必须分开排行：前者的非法 certificate 永远不能因体积较高进入质量榜。Wave 1 完成后，才能回答“基础 3D 装箱质量”而不是“某一个 benchmark 的质量”。

### Wave 2：成本、异构和硬约束

运行 B08-B18，先做 capability/conformance，再做质量。推荐顺序：B09（小规模 exact truth） -> B08/B10/B11（公开或固定异构输入） -> B12-B18（逐约束 gauntlet）。

这波的门禁是词典序：硬约束违反率必须为 0，必装件必须完整，之后才比较成本/箱数/利用率。一个库即使箱数很好，只要重量、支撑、轴荷或卸货硬校验失败，也不能被标为生产可用。

### Wave 3：工业端到端和应用专项

运行 B19-B23、B30-B32。每个套件至少输出两个轨道：

- `FULL`：保留原始车辆、托盘、站点、交付日、货架或在线语义；
- `PROJECTION`：明确列出删除了哪些字段，只用于几何算法诊断。

只有 `FULL` 轨可以回答工业采用问题。B22 的 `NOT_SUPPORTED` 本身是结果，不能通过给非规则物体套 AABB 把正交库升级为 irregular 支持。B32 的离线重建必须和原生 incremental 解分开。

### Wave 4：可靠性和部署边界

运行 B24-B29，并重复 Wave 1-3 中的代表性实例。每个随机算法至少 5 个 seed；每个确定性库至少测输入顺序、ID、单位和进程取消。性能报告同时保留库内时间和端到端 wall time，Java sidecar、Python binding 和 CLI 不混用一个时间榜。

## 3. 每个 benchmark 的选择逻辑

下面的“适用库”指可以在原问题语义下进入相应轨道的候选；不适用的库仍然必须产生 `NOT_SUPPORTED` 或 `PROJECTION_ONLY` 状态。

| ID | 为什么必须选 | 适用库/算法轨道 | 主要说明 | 不应外推 |
|---|---|---|---|---|
| B01 BR | 公开单箱体积基线 | PackingSolver native；py3dbp/Jerry/Go projection；Skjolber/Rust/EX 适配后 | 基础可行性、旋转、排序和 anytime 质量 | 不说明多箱、成本或稳定性 |
| B02 LN | 与 BR 不同的尺寸分布和直立语义 | 同 B01，保留原姿态规则 | 分布迁移、初解和空解率 | 仍不是 3D-BPP |
| B03 Profit-KP | 把体积目标和价值目标分开 | PackingSolver native；Rust 固定姿态 composed；其他多为全旋转 projection；EX 小规模 | 是否真正优化 profit；小规模 exact 校准 | 无效 best-known 表不能算 gap；姿态轨不可混排 |
| B04 IMM/THPACK9 | 基础同型多箱装完 | 全库几何实现；Rust 为 composed | 箱数和完整性 | 不含成本、路线或力学 |
| B05 MPV 3D-BPP | 防止只对 THPACK9 过拟合 | 同 B04；EX 小规模 | 外部分布的箱数质量和 known-result gap | 来源未冻结前不能排名 |
| B06 Exact oracle | 给启发式一个可信真值 | CP-SAT/SCIP/Gurobi/CPLEX；启发式作 incumbent | objective gap、下界、证明率和不可行识别 | 合成小实例不代表生产分布 |
| B07 BR0/BR8-15 | 扩大公开单箱困难桶 | 同 B01 | 困难尺寸的鲁棒性 | 不能推出任意角或业务约束能力 |
| B08 Multiple-bin-size/cost | 测真正的箱型选择和价格目标 | PackingSolver cost 轨、EX；其他 composed/projection | 总成本、箱型 dominance、库存影响 | 箱数最少不等于成本最低 |
| B09 Variable-cost exact | 回归 comparator、价格方向和 copies 逻辑 | EX native；PackingSolver 对照 | 成本真值和 bug 定位 | 规模小，不能作吞吐榜 |
| B10 Fixed heterogeneous MCLP | 测给定异构车辆/箱的完整分配 | PackingSolver/EX native；其他 master + placement | 完整率、未装件、箱型分配 | 删除异构字段后不是 MCLP |
| B11 Open dimension/strip | 测最小长度/高度而非封闭箱数 | PackingSolver open-dimension、EX；其他 wrapper | 使用长度、截面利用率、开放维度目标 | 封闭箱成绩不能替代 |
| B12 Pose gauntlet | 区分 6 尺寸排列和面语义姿态 | PS/Skjolber/Rust/EX；Python/Go projection | 姿态白名单遵守率 | 不证明连续任意角 |
| B13 Payload/inventory | 检查重量、tare、copies 是否是硬约束 | PS/EX；其余 validator/conformance | 超重率、漏件率 | 存字段不等于执行约束 |
| B14 Support/load-bearing | 检查接触、支撑面积、上压和堆数 | boxstacks/EX；部分 controls；其余 projection | 违反率和余量 | 排序或接触面积近似不是力学证明 |
| B15 CG/axle/floor | 检查车辆静力和地板载荷 | boxstacks/EX；其余 post-validator | 轴荷、重心、地板点载荷余量 | 不是法规认证计算 |
| B16 Obstacles/door/keepout | 检查终点可行空间和入口限制 | controls/EX；其他 projection | keepout、门洞和反例 | AABB 终点不等于连续路径可达 |
| B17 Multi-drop/unloading | 检查交付顺序和重搬 | controls/EX；几何库 projection | 遮挡、重搬、顺序违约 | 离线最优不等于在线装卸可执行 |
| B18 Compatibility | 检查温区、危化和隔离组 | EX/group master；其他有字段才可 | 分组与隔离合规 | 几何分离不能冒充业务合规 |
| B19 Alonso 2019 | 工业多容器、托盘、车辆和交付日 | full 仅 PS-S/EX；其余 projection | 需求完成、车辆数、轴荷/成本 | projection 不能叫 full |
| B20 Alonso 2020 | 多周期需求与托盘类型 | full PS/EX；其余 projection | 日序、库存、托盘联合能力 | 不是单日 BPP |
| B21 VRPTW-CLP | 路线/时间窗/装载耦合 | full PS-S/Skjolber/EX；其余 fixed-route projection | 路由和装载同时可行率 | 只跑几何不代表解决 VRPTW-CLP |
| B22 3D irregular | 覆盖 mesh/voxel/polytope 和斜边界 | irregular 专用引擎；正交库记 NOT_SUPPORTED | 非规则几何支持边界 | OBB/AABB 不能替代 mesh 碰撞 |
| B23 Real orders | 测公开分布到真实订单的迁移 | 有语义 adapter 的库，full/projection 分开 | 分层质量、延迟、完整率 | 没有获准脱敏数据就不运行 |
| B24 Metamorphic | 检查表示变化不应改变结果语义 | 全库 + exact oracle | 置换、ID、轴置换、镜像一致性 | 随机算法要固定 seed 和容差 |
| B25 Cost/bin-order metamorphic | 检查成本方向、dominance 和顺序 bug | cost-capable PS/EX；其余 adapter | 预期不变/预期变化是否正确 | 最优解变化不一定是失败 |
| B26 Numeric/unit | 暴露单位、舍入、边界和溢出问题 | 全库 validator/EX | 数值一致性、越界率 | 不替代物理公差校准 |
| B27 Repeatability | 衡量 seed、顺序敏感性和方差 | 全库；随机算法 >=5 seed | median/p95、方差、合法率 | seed 不是额外独立样本 |
| B28 Scalability | 找质量-延迟-内存拐点 | 全库；EX 到预算上限 | time-quality curve、RSS、timeout | 不同进程边界需分组 |
| B29 Fault/cancellation | 判断能否安全托管到 Python/Tauri | 全部 worker/sidecar/CLI | 取消延迟、恢复率、artifact 完整性 | 不评价布局质量 |
| B30 BAYTP | 覆盖货架/bay 顺序和间隙 | shelf master/EX；其他 projection | bay/shelf 数和顺序违约 | 不是自由 3D-BPP |
| B31 Mixed-SKU pallet | 覆盖高重复 SKU、层型和托盘 | boxstacks/EX；controls；其他 projection | 托盘数、高度、支撑/承压 | synthetic truth 不冒充公开集 |
| B32 Online/incremental | 覆盖到货序列、lookahead 和重排 | 有 incremental adapter 的库；EX 小窗口 | 累计成本、deadline、offline loss | 离线 rebuild 不能叫原生 online |

## 4. 全库横评的输出格式

每一个 `suite × implementation × variant × budget` 至少产生一条 JSONL 记录，包含：

```text
input_status, capability_status, run_status, solution_status, proof_status
problem_kind, pose_semantics, track, library/version/commit, adapter_name
input_sha256, seed, budget, wall_time, solver_time, peak_rss
objective, completeness, hard_violation_count, validator_version, artifact_sha256
termination_reason, error_kind, unsupported_reason
```

排行只在同一问题族内生成。建议的榜单是：

1. volume knapsack：B01/B02/B07；
2. profit knapsack：B03；
3. identical-bin packing：B04/B05；
4. exact proof：B06/B09 及其他小规模 exact 子集；
5. variable-cost/open-dimension：B08-B11；
6. hard-constraint conformance：B12-B18；
7. industrial full：B19-B23/B30-B32；
8. reliability/scalability：B24-B29。

不生成“所有问题的总冠军”。原因是 B03 的 profit、B04 的箱数、B15 的轴荷合规和 B29 的取消恢复没有共同的可加单位；任意加权都会掩盖硬失败。

## 5. 当前范围外但应登记的扩展

B01-B32 已覆盖当前 3D 正交装载产品的主要应用场景。若产品范围扩大，以下不是简单加几个样例就能解决的独立问题，应另立 benchmark 和模型：

| 扩展 | 何时必须加入 | 当前处理 |
|---|---|---|
| 尺寸/重量不确定性与鲁棒装载 | 测量误差、包装变形或供应波动导致 nominal 解不可靠时 | 新增 robust/stochastic suite；不能用 B26 单位测试替代 |
| 多目标 Pareto（成本、碳排、装卸、服务水平） | 产品需要让业务选择 Pareto 方案时 | 在 B08/B19/B23 上增加目标向量和 Pareto 指标；不合成一个分数 |
| 软包装、可压缩或液体晃动 | 物品不是刚性长方体时 | 需要材料/物理模型；B14 不能直接代表 |
| 机器人连续运动与系固 | 需要验证装入轨迹、门洞穿越或运输加速度时 | 新增 motion/securement 专项；B16 只测静态和反例 |
| 2D cutting/nesting | 业务包含板材切割、排样而非箱体装载时 | 单独引入 2D 数据集；不能把 B22 的 3D irregular 结果外推 |

这些扩展要么在产品需求确认后加入，要么在报告中明确列为 out-of-scope；不能以“库支持 3D box”代替它们。

## 6. 推荐的停止条件

一次完整的 ALL-libs campaign 至少满足：Wave 0 来源冻结；B01-B07 每个候选有状态且每个可比较轨道有合法证书；B08-B18 完成 capability/conformance；B19-B23、B30-B32 对缺适配器的库明确记录；B24-B29 完成代表性重复和故障测试；所有结果经过独立 validator、hash 和 `scripts/verify.py`。

在此之前，报告只能说“已完成的子集结果”和“覆盖计划”，不能说“全部 benchmark 已跑完”。
