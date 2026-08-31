# Benchmark 选择与覆盖决策

本表回答两个问题：一个 benchmark 适合哪些实现/算法，以及跑完后究竟能支持什么结论。实现缩写如下：`PS-F` = PackingSolver fork `box`，`PS-U` = 官方 rolling `box`，`PS-S` = `boxstacks`，`PY` = py3dbp，`JE` = Jerry，`SK` = Skjolber Plain/LAFF/FastBruteForce，`GO` = gedex/bp3d，`RS` = u-nesting 各策略，`EX` = OR-Tools/SCIP/Gurobi/CPLEX exact model。`native` 表示库原生表达问题，`composed` 表示外层 adapter 或重复单箱调用，`projection` 表示删去原问题字段后的几何投影；三者不合并排名。

## 总决策

建议保留 B01-B32 全部套件。B01/B02/B04 是经典正交几何核心，B03 补 profit 目标，B08-B11 补异构成本、开放维度和固定异构装载，B12-B18 覆盖姿态、重量、支撑、车辆静力、障碍、卸货和相容性，B19-B23 覆盖工业组合、非规则几何和真实分布，B24-B29 覆盖可靠性与运维，B30-B32 覆盖货架、托盘和在线作业。删掉任一组都会留下明确的能力盲区。

同一套件中的“适用”不是“必须全部纳入同一排行榜”。例如 B03 的固定姿态与全旋转投影必须分开，B21 的完整路线-装载与只做几何装载必须分开，B14/B15 的 hard validator 失败不能用体积或箱数抵消。

## 逐套件选择表

| ID | 问题/数据形态 | 适用实现与轨道 | 首要输出 | 结果主要说明什么 | 不能外推/缺口 |
|---|---|---|---|---|---|
| B01 | ESICUP THPACK1-7 / BR，单箱最大体积 | PS-F/PS-U、PY、JE、SK、GO、RS；EX 仅小子集 | 合法率、packed volume、利用率、顺序差异 | 基础正交 knapsack 的可装性、旋转和排序敏感性 | 不含多箱成本、支撑、路线和 profit |
| B02 | ESICUP THPACK8 / LN，单箱最大体积 | 同 B01；保留各库姿态语义 | 合法率、packed volume、空解率 | 对另一分布和较难尺寸组合的泛化 | 仍不是完整多箱 BPP |
| B03 | Egeblad-Pisinger 3D-KP，20/40/60 件、profit、固定 XYZ | PS-F/PS-U native；PY/JE/GO `RELAXED_ALL_ROTATIONS` projection；RS fixed composed；EX fixed 20 件 | packed profit/total profit、合法率、bound/proof、时间 | 是否真正优化价值而非仅体积；姿态放宽带来的收益；小规模可证明性 | 上游 57 行参照表无效，禁止算 reference gap；projection 不代表原题 |
| B04 | ESICUP THPACK9 / IMM，同型多箱装完最少箱 | PS-F/PS-U、PY、JE、SK、GO、RS；EX 小规模 | 完整合法率、箱数、共同 44 例配对胜负 | 多箱分配和规模化几何质量 | 无价格、轴荷、卸货和证明最优值 |
| B05 | Martello-Pisinger-Vigo 3D-BPP 公共集 | 数据完整后 PS/SK/PY/GO/RS；EX 小规模 | 箱数、best-known/lower-bound gap | 经典多箱分布外部复核 | 当前来源不完整，未补齐前不得排名 |
| B06 | 版本化 exact-oracle 生成实例 | EX 四后端；启发式仅作 incumbent 对照 | objective、bound、proof rate、time-to-proof | 模型和 validator 是否正确、规模阈值在哪里 | 合成真值不是工业分布；不用于跨库总分 |
| B07 | Davies-Bischoff BR0/BR8-15，单箱/困难尺寸 | PS、PY、JE、SK、GO、RS；EX 小子集 | packed volume、合法率、困难桶分层 | BR 外的公开质量与困难实例鲁棒性 | 当前 Python/Go/Rust 为 `GEOMETRY_PROJECTION`；Jerry `fix_point=True` overlap 与 `False` control 分榜，Skjolber/EX 仍需 adapter |
| B08 | 多箱型、价格、有限 copies 的公开成本集 | PS-F/PS-U（当前 #536 轨需单独记录）；EX；其他库 projection | total cost、箱型用量、bound | 成本目标是否被真正优化、箱型 dominance 是否正确 | PS issue #536 未修复前不能把异常当质量结果；普通 BPP 箱数不等价成本 |
| B09 | 版本化 variable-cost exact truth | EX native；PS/PY/JE/SK/GO/RS 只作 conformance/projection | exact cost、hard compliance、proof | 成本、库存和分配模型的真值回归 | 小规模逻辑测试，不代表大规模速度 |
| B10 | 固定异构箱型 MCLP，必须完整装载 | PS/EX native；SK/PY/JE/GO/RS 需 master + placement projection | complete feasible rate、未装需求、成本 | 异构容量、库存、完整性联合能力 | 数据源未齐前保持 SOURCE_INCOMPLETE |
| B11 | Open-X/Y/Z / 3D strip，开放一个或多个维度 | PS rectangle/1D、EX；其他库需固定二分 adapter | used length/height、合法率 | 开放维度目标和截面利用率 | 不能用封闭箱数成绩代替开放维度 |
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

## 结果阅读规则

每个套件至少发布 `capability_status`、`solution_status`、`proof_status`、主 objective、wall/CPU/RSS 和 artifact hash。质量排序先按 hard feasibility/完整性，再按主 objective；`INVALID_CERTIFICATE` 永远不能因为箱数少或 profit 高而进入排名。跨库只有在输入 hash、问题 variant、姿态语义、预算和验证器相同时才做配对比较。

B03 的具体执行契约是一个可复用例子：原题 `FIXED_XYZ`，放宽轨 `RELAXED_ALL_ROTATIONS`，exact 只跑 20 件层；参照表因 48/57 行低于单件 profit 下界而整体禁用。该边界应复制到 B08/B19/B21 等所有存在字段删减或公共 best-known 不可靠的套件。
