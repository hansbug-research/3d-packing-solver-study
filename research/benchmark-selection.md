# Benchmark 选择与覆盖决策

本表回答两个问题：一个 benchmark 适合哪些实现/算法，以及跑完后究竟能支持什么结论。实现缩写如下：`PS-F` = PackingSolver fork `box`，`PS-U` = 官方 rolling `box`，`PS-S` = `boxstacks`，`PY` = py3dbp，`JE` = Jerry，`SK` = Skjolber Plain/LAFF/FastBruteForce，`GO` = gedex/bp3d，`RS` = u-nesting 各策略，`EX` = OR-Tools/SCIP/Gurobi/CPLEX exact model。`native` 表示库原生表达问题，`composed` 表示外层 adapter 或重复单箱调用，`projection` 表示删去原问题字段后的几何投影；三者不合并排名。

## 总决策

建议保留 B01-B32 全部套件。B01/B02/B04 是经典正交几何核心，B03 补 profit 目标，B08-B11 补异构成本、开放维度和固定异构装载，B12-B18 覆盖姿态、重量、支撑、车辆静力、障碍、卸货和相容性，B19-B23 覆盖工业组合、非规则几何和真实分布，B24-B29 覆盖可靠性与运维，B30-B32 覆盖货架、托盘和在线作业。删掉任一组都会留下明确的能力盲区。

同一套件中的“适用”不是“必须全部纳入同一排行榜”。例如 B03 的固定姿态与全旋转投影必须分开，B21 的完整路线-装载与只做几何装载必须分开，B14/B15 的 hard validator 失败不能用体积或箱数抵消。

## BR/LN 之外的补充讨论与新增数据集决策

BR/LN 是必要的单箱几何起点，但它们只回答“一个固定箱里最多装多少体积”。即使把 BR/LN 的实例数量扩大一个数量级，也仍然不会回答以下问题：是否必须装完全部需求、箱型价格如何选择、有限库存如何分配、堆叠和上压是否合规、车辆轴荷是否可行、货物能否按站点卸出、非规则物体是否可碰撞验证，以及到货顺序变化后的累计代价。因此本项目采用“问题族覆盖”而不是“单一大样本替代所有问题”的原则。

### 1.1 最小可接受覆盖集

下表是发布第一版选型结论前的硬覆盖门。每一行至少需要一个原问题语义保持不变的 benchmark；如果某个库无法表达该语义，仍需输出 `NOT_SUPPORTED` 或 `ADAPTER_MISSING`，不能用删字段后的漂亮数字填补空位。

| 主要应用/问题族 | 必须有的套件 | 参加方式 | 结果能够回答 | 缺失时最容易出现的误判 |
|---|---|---|---|---|
| 单箱正交装载与困难尺寸 | B01、B02、B07 | native/composed/projection 分轨 | 基础几何、旋转、排序和预算响应 | 把一个尺寸分布上的好成绩当成通用能力 |
| 价值/利润取舍 | B03、B06 | B03 保持 fixed-pose；B06 给 exact oracle | 是否优化业务价值，小规模能否闭合 bound | 体积高但价值低，或把 incumbent 误称最优 |
| 同型多箱和外部复核 | B04、B05 | 必须装完；B05 来源完整后才排名 | 箱数、完整性、分布迁移 | 只对 THPACK9 调参造成过拟合 |
| 异构车队、价格、库存、开放尺寸 | B08-B11 | cost/open 语义单独排行 | 总成本、箱型选择、有限 copies、开放长度 | 用最少箱数代替成本，或把封闭箱结果叫 strip |
| 姿态、重量、支撑和车辆静力 | B12-B15 | 先 hard conformance，再比较目标 | 姿态白名单、重量、承压、重心/轴荷是否执行 | 仅检查 AABB 就宣称可运输 |
| 入口、障碍、卸货和相容性 | B16-B18 | 保留门洞、站点、隔离字段 | 装入/取出、重搬、温区/危化隔离 | 终点几何可行但现场无法装卸或不合规 |
| 工业组合、路线、非规则和真实分布 | B19-B23、B30-B32 | `FULL` 与 projection 严格分轨 | 端到端工业可行率和分布迁移 | 删除业务字段后仍称“工业能力” |
| 工程可靠性与托管 | B24-B29 | 所有部署候选都测 | 单位/顺序/seed/规模/取消/崩溃行为 | 平均质量好看但无法安全集成 |

这张表不是跨问题族加权评分表。B14/B15/B17/B18 的硬约束失败不能由 B01 的利用率或 B04 的箱数抵消；B22 的 `NOT_SUPPORTED` 也是重要能力边界。

### 1.2 Q4RealBPP 与 3DBPPsi：建议新增但不替代经典套件

在协议 v3 冻结后又发现两个可复现的公开数据源。它们应作为下一版协议的 B33/B34 候选，先完成许可证、文件哈希、canonical converter 和独立 validator，再进入 ALL-libs 运行。它们不应直接改名覆盖 B05，也不应在未完成 source audit 前混入当前 `32 x 19 = 608` 的完成率。

| 候选 | 数据与许可证 | 适用库/算法轨道 | 建议指标 | 结果主要说明 | 明确不能外推 | 当前决策 |
|---|---|---|---|---|---|---|
| **B33 Q4RealBPP**（Mendeley Data DOI [10.17632/y258s6d939.2](https://doi.org/10.17632/y258s6d939.2)，S125） | 12 个 real-world-oriented 实例，输入 quantity 合计 578 件（单实例 38–53 件）；尺寸、重量、最大箱数/重量、incompatibility、positive affinity、相对位置、中心位置等字段，并附 `Q4RealBPP-DataGen.py`；数据集标注 GPLv3 | PackingSolver/boxstacks 与 exact model 进入 `FULL`（能保留的约束逐项记录）；py3dbp、Jerry、Go、Rust、Skjolber 只有保留字段的 projection 或 post-validator；全部实现都必须有状态行 | 完整率、总成本/箱数、逐约束 `PASS/FAIL/UNKNOWN`、违规幅度、time-to-first-feasible；没有可靠 optimum 时不报 gap | 现实约束字段是否真正被执行，以及公共几何集到业务分布的迁移；适合 conformance 和小规模端到端回归 | 12 个实例太小，不能作为吞吐/泛化唯一依据；量子求解器导向的生成分布不能代表所有订单；GPLv3 需要审计衍生数据和再分发义务；`Description.txt` 对 `3dBPP_5`、`3dBPP_6`、`3dBPP_10` 的件数与输入 quantity 不一致；不能替代 MPV 的经典同型多箱 | **加入 B33 候选；先做许可证和语义审计，再跑 FULL/projection 双轨** |
| **B34 3DBPPsi**（Science Data Bank DOI [10.57760/sciencedb.42066](https://doi.org/10.57760/sciencedb.42066)，S126） | V1，20 个文件，CC BY 4.0；异构车队、车辆尺寸/价格/payload/stacked-weight/density、物品重量、nesting height、stackability class、forced orientation、最大 stackability；规模从小中型到数千件 | `boxstacks`/exact model 进入 `FULL`；PackingSolver `box`、Skjolber controls 等只有删去堆叠/成本字段后的 projection；py3dbp/Jerry/Go/Rust 作为几何对照；大实例优先测 scalability | 完整率、总运输成本、车辆组合、堆叠/密度/姿态硬合规、time-quality-RSS 曲线；小实例先由 exact oracle 校准 | 异构车队选择、stackable item 规则和大规模部署拐点；这是 B31/B19 的公开现实化补充 | 公开元数据没有给出统一 published optimum，先按合法 incumbent/下界报告；它不测门洞连续路径、路线时间窗或任意角；不能替代 B05 的同型多箱分布 | **加入 B34 候选；先实现 stack master 和 hard validator，再进入工业 Wave** |

两者的使用方式应明确分层：B33 主要是“现实约束是否被正确执行”的 conformance suite，B34 主要是“异构车队与堆叠在中大规模上是否可部署”的 industrial/performance suite。两者都不产生跨问题族总分；B33 的 GPLv3 数据也不能未经审计直接复制进一个闭源安装包，B34 的 CC BY 4.0 则至少要保留署名和许可证信息。

### 1.3 覆盖缺口与范围外项目

B01-B34 覆盖的是刚性长方体为主的正交装载产品。以下问题不是再加几条 BR/LN 样例就能覆盖，应该在产品范围确认后另立 suite：尺寸/重量不确定性的 robust/stochastic packing；成本、碳排、服务水平和装卸代价的 Pareto 多目标；软包装、可压缩物和液体晃动；机器人连续运动、系固和运输加速度；以及 2D cutting/nesting。当前应在报告中显式标记为 out-of-scope，不能用 B26、B16 或 B22 的结果替代。

## 逐套件选择表

| ID | 问题/数据形态 | 适用实现与轨道 | 首要输出 | 结果主要说明什么 | 不能外推/缺口 |
|---|---|---|---|---|---|
| B01 | ESICUP THPACK1-7 / BR，单箱最大体积 | PS-F/PS-U、PY、JE、SK、GO、RS；EX 仅小子集 | 合法率、packed volume、利用率、顺序差异 | 基础正交 knapsack 的可装性、旋转和排序敏感性 | 不含多箱成本、支撑、路线和 profit |
| B02 | ESICUP THPACK8 / LN，单箱最大体积 | 同 B01；保留各库姿态语义 | 合法率、packed volume、空解率 | 对另一分布和较难尺寸组合的泛化 | 仍不是完整多箱 BPP |
| B03 | Egeblad-Pisinger 3D-KP，20/40/60 件、profit、固定 XYZ | PS-F/PS-U native；PY/JE/GO `RELAXED_ALL_ROTATIONS` projection；RS fixed composed；EX fixed 20 件 | packed profit/total profit、合法率、bound/proof、时间 | 是否真正优化价值而非仅体积；姿态放宽带来的收益；小规模可证明性 | 上游 57 行参照表无效，禁止算 reference gap；projection 不代表原题 |
| B04 | ESICUP THPACK9 / IMM，同型多箱装完最少箱 | PS-F/PS-U、PY、JE、SK、GO、RS；EX 小规模 | 完整合法率、箱数、共同 44 例配对胜负 | 多箱分配和规模化几何质量 | 无价格、轴荷、卸货和证明最优值 |
| B05 | Martello-Pisinger-Vigo 3D-BPP 公共集 | 数据完整后 PS/SK/PY/GO/RS；EX 小规模 | 箱数、best-known/lower-bound gap | 经典多箱分布外部复核 | 当前来源不完整，未补齐前不得排名 |
| B06 | 版本化 exact-oracle 生成实例 | EX 四后端；启发式仅作 incumbent 对照 | objective、bound、proof rate、time-to-proof | 模型和 validator 是否正确、规模阈值在哪里 | 合成真值不是工业分布；不用于跨库总分 |
| B07 | Davies-Bischoff BR0/BR8-15，单箱/困难尺寸 | PS、PY、JE、SK、GO、RS；EX 小子集 | packed volume、合法率、困难桶分层 | BR 外的公开质量与困难实例鲁棒性 | 当前 Python/Go/Rust 为 `GEOMETRY_PROJECTION`；Jerry `fix_point=True` overlap 与 `False` control 分榜；CP-SAT 已对 4 个不超过 60 件的 source-rotation 实例做 exact calibration；Skjolber 原生 API 要求所有输入件装完，B07 单箱 optional-subset 轨返回空结果，保持 `ADAPTER_MISSING` |
| B08 | 多箱型、价格、有限 copies 的公开成本集 | PS-F/PS-U（当前 #536 轨需单独记录）；EX；其他库 projection | total cost、箱型用量、bound | 成本目标是否被真正优化、箱型 dominance 是否正确 | PS issue #536 未修复前不能把异常当质量结果；普通 BPP 箱数不等价成本 |
| B09 | 版本化 variable-cost exact truth | EX native；PS/PY/JE/SK/GO/RS 只作 conformance/projection | exact cost、hard compliance、proof | 成本、库存和分配模型的真值回归 | 小规模逻辑测试，不代表大规模速度 |
| B10 | 固定异构箱型 MCLP，必须完整装载 | PS/EX native；SK/PY/JE/GO/RS 需 master + placement projection | complete feasible rate、未装需求、成本 | 异构容量、库存、完整性联合能力 | 数据源未齐前保持 SOURCE_INCOMPLETE |
| B11 | Open-X/Y/Z / 3D strip，开放一个或多个维度 | PS rectangle/1D 原生；PY/JE/GO/RS 通过固定整数 X 外层搜索作 `PROJECTION_ONLY/COMPOSED`；SK/EX 暂 `ADAPTER_MISSING` | used length/height、合法率；外层搜索候选数和 wall time | 开放维度目标和截面利用率，以及组合 adapter 的代价 | 投影放宽姿态，不能称原生；不能用封闭箱数成绩代替开放维度 |
| B12 | 姿态 gauntlet：六排列、直立、固定面、离散 OBB | 全部先跑 capability/conformance；PS/SK/RS/EX 原生或 composed；PY/JE/GO 多为 projection | pose compliance、非法姿态率 | 区分“能旋转”与“遵守姿态子集” | 当前 AABB 轨不代表连续任意角 |
| B13 | payload/inventory：重量、tare、copies、空箱 | PS/EX；SK/RS 部分；PY/JE 可做外层 hard validator；GO 作为失败对照 | hard compliance、漏件/超重率 | 字段是否进入硬约束而非仅存储 | GO `MaxWeight` 字段不执行，不能因几何合法而升级 |
| B14 | 支撑、上压、堆数、nesting、脆弱件 | PS-S native；EX；JE/SK controls/近似；其他 validator/projection | hard violation rate、支撑/承压 margin | 几何接触、支撑图和载荷限制是否真实执行 | 面积比例或排序不是承压证明 |
| B15 | CG、轴/轴组反力、地板载荷 | PS-S/EX；其他库只能 placement + post-validator | hard violation rate、最大 margin | 车辆静力可行性和卸货后状态 | 简化轴模型不是车辆制造商批准计算 |
| B16 | 障碍、keepout、门洞、抽取路径 | PS/SK controls；EX；其他 projection | hard compliance、可达性反例 | 非完整可用空间和基本入口约束 | 终点 AABB 不能证明连续机器人路径 |
| B17 | 多站卸货、无遮挡/重搬和顺序 | PS 部分、SK controls、EX；其他通常 projection | hard compliance、relocation/rehandle | 装载序列是否服务于交付顺序 | 离线多箱结果不能回答在线决策 |
| B18 | compatibility/segregation，温区/危化/相容组 | EX/group master；PS/SK/其他只在字段可表达时 | hard compliance、分组正确率 | 业务隔离规则是否被明确建模 | 几何偶然分开不是合规证明；缺数据默认拒绝 |
| B19 | Alonso 2019，多容器、托盘、交付日、重量 | PS-S/EX full；其他仅 geometry projection | full feasible rate、需求完整率、成本 | 工业层级约束的综合覆盖 | 删除车辆/交付字段后的结果不能叫 full |
| B20 | Alonso 2020，多周期需求和 pallet 类型 | PS/EX full；其他 projection | demand completion、资源和日期违约 | 需求分解、日序和托盘类别联合能力 | 不是普通单日 BPP |
| B21 | ESICUP VRPTW-CLP，路线/时间窗/装载 | PS/SK/EX full；其他 fixed-route projection | full feasible rate、路由与装载违约 | 路线、时间窗、三维装载耦合 | 只跑装载不代表解决 VRPTW-CLP |
| B22 | ESICUP irregular，mesh/voxel/polytope/斜边界 | irregular 专用引擎；当前正交 PS/PY/JE/SK/GO/RS/EX 通常 NOT_SUPPORTED | capability coverage、OBB/SAT 合法率 | 明确任意角和非长方体能力边界 | NOT_SUPPORTED 是有效结论，不是缺少一次 smoke |
| B23 | 脱敏真实订单，按件数/密度/站点分层 | 所有语义适配的实现；full 与 projection 分开 | objective by stratum、完整率、延迟 | 公共随机集到真实分布的 distribution shift | 无可发布脱敏数据时不伪造 REAL_ORDER 结果 |
| B24 | metamorphic：置换、ID、copies、轴置换、镜像 | 全部；EX 作为 oracle | invariance rate、目标/合法性差异 | 表示变化是否错误改变解质量或合法性 | 对随机算法需固定 seed/统计容差 |
| B25 | 成本/箱序 metamorphic：反序、价格缩放、dominated bin | PS/EX、成本 adapter；其他可做 projection | invariance/expected-change rate | comparator、cost direction、dominance 预处理错误 | 不应把合理的最优解变化误判为不变性失败 |
| B26 | numeric：单位缩放、边界接触、极值整数/浮点 | 全部 validator/adapter；EX oracle | numeric consistency、越界/溢出率 | 单位、舍入、AABB 接触和整数溢出风险 | 不代替真实物理公差和测量不确定度 |
| B27 | seed/order repeatability，5 次重复、多 seed | 全部；随机 RS/EX 至少 5 seed | best/median/p95、方差、合法率 | seed 是否生效、顺序敏感性和稳定性 | 不能把 seed 当额外独立实例扩大样本量 |
| B28 | scalability，20/50/100/200/500/1000 件 | 全部；EX 到预算允许规模 | time-quality curve、RSS、timeout | 质量-延迟-内存拐点与部署上限 | 不同语言启动边界需分 timing group |
| B29 | fault/cancellation/OOM/非法输出/恢复 | 全部 worker、sidecar、CLI | recovery rate、取消延迟、残留 artifact | 是否适合被 Python/Tauri 安全托管 | 不评价布局质量；失败必须保留原始证据 |
| B30 | OR-Library BAYTP shelf/bay，间隙和 bay 顺序 | EX full；PS/SK + shelf master；其他 projection | bays/shelves、完整率、顺序违约 | 仓储货架选择而非自由 3D-BPP | 当前输入已恢复；完整 shelf adapter 仍需实现 |
| B31 | mixed-SKU pallet，层型、支撑、承压、托盘数 | PS-S/EX；JE/SK controls；其他 projection | legal complete rate、pallets/height | 高重复 SKU 与层/承压联合能力 | 版本化 synthetic truth，不冒充公开数据集 |
| B32 | online/incremental，到货序列、lookahead、重排 | 有 incremental adapter 的全部；EX 小窗口；无 adapter = ADAPTER_MISSING | cumulative cost、deadline、relocation、offline loss | 实时延迟和顺序鲁棒性，不只是离线最优 | 离线 rebuild 必须单独标记，不能声称库原生 online |

**B30/B31 校准边界。** `SHELF_SEQUENCE_CALIBRATION`、`FLAT_MIXED_CALIBRATION`、`STACKABLE_CALIBRATION` 和 `WEIGHT_INFEASIBLE_CALIBRATION` 是协议维护的 hand-checkable exact fixtures。它们用于校准独立 validator、投影 adapter 和小规模 exact truth，必须带 `metrics.calibration_only=true`、fixture hash 与 proof artifact。校准记录可以在对应工业结果表中单列展示，但不得冒充完整 BAYTP/订单 corpus 的质量排名，也不得提高 suite 的 source/corpus 完成率。

## 结果阅读规则

每个套件至少发布 `capability_status`、`solution_status`、`proof_status`、主 objective、wall/CPU/RSS 和 artifact hash。质量排序先按 hard feasibility/完整性，再按主 objective；`INVALID_CERTIFICATE` 永远不能因为箱数少或 profit 高而进入排名。跨库只有在输入 hash、问题 variant、姿态语义、预算和验证器相同时才做配对比较。

B03 的具体执行契约是一个可复用例子：原题 `FIXED_XYZ`，放宽轨 `RELAXED_ALL_ROTATIONS`，exact 只跑 20 件层；参照表因 48/57 行低于单件 profit 下界而整体禁用。该边界应复制到 B08/B19/B21 等所有存在字段删减或公共 best-known 不可靠的套件。
