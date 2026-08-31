# 跨平台三维装箱软件技术选型总报告

> 决策日期：2026-08-31。本文是技术架构与产品实施建议，不是车辆/集装箱/航空配载批准、结构计算、危险品合规证明或系固设计。详细证据分别见 [真实工况与元模型](research/domain-model.md)、[算法与论文/库实测](research/algorithms.md)、[逐特性算法/前端矩阵](research/decision-matrices.md)、[公共 benchmark 与指标](research/benchmarks.md)、[benchmark 选择与覆盖决策](research/benchmark-selection.md)、[PackingSolver 上游核查](research/packingsolver-upstream.md)、[桌面与三维交互](research/frontend.md) 和 [本地测试摘要](results/test-summary.md)。

## 1. 最终结论

建议立项，但不要把它实现成“一个 Python `pack()` 函数加一个 3D 视图”。满足本需求的可交付产品应是：**一个版本化领域模型、多个求解引擎、一个不信任求解器的独立验证器，以及与 CLI 共用同一 application service 的桌面应用**。本轮已完成上游缺陷核查和 ESICUP 公共实例复跑；结果只能把候选排序到“有证据的 incumbent”，不能越过 validator 或把启发式称为全局最优。

首版推荐栈：

| 层 | 选择 | 决策 |
|---|---|---|
| 领域与编排 | Python 3.12、Pydantic v2 | Python 是统一后端和插件编排边界，算法实现语言不限 |
| CLI | Typer/Click，机器模式输出 JSON/NDJSON | 与 GUI 调同一 application service，不做第二套业务逻辑 |
| 本地数据 | SQLite + SQLAlchemy 2 + Alembic；运行结果为不可变 job bundle | SQLite 管目录/任务索引，JSON/CSV/日志/校验报告便于复现和迁移 |
| 默认成本主问题 | OR-Tools CP-SAT | 箱型价格、数量、分配、相容和 pattern 选择；小模型可返回可证明界 |
| 开放精确扩展 | PySCIPOpt/SCIP | 连续坐标 MIP、载荷流和高级研究；不是现成 3D packer |
| 正交启发式 | PackingSolver `box`/`boxstacks`，**有条件采用** | C++ CLI 子进程；必须 pin 源提交和 binary hash，并先关闭当前回归阻断项 |
| 商业精确插件 | Gurobi 优先；客户已有 IBM 体系时适配 CPLEX | 只在生产许可和真实基准收益成立时启用 |
| 独立几何/力学校核 | Python 接口，性能热点可用 C++/Rust binding | 所有引擎统一复算数量、几何、姿态、重量、支撑、重心/轴荷等 |
| 桌面壳 | Tauri 2 | Rust core 负责文件授权、更新、签名、worker 监管和窄 IPC |
| GUI | React + TypeScript + Vite | 适合虚拟化表格、复杂 inspector、方案比较和跨壳复用 |
| 3D | Three.js 直接 scene controller | `InstancedMesh`、拾取、剖切、正交视图和分步装载；不把实例逐个映射为 React 组件 |
| 桌面 IPC | 版本化 NDJSON/JSON-RPC 风格 stdio + Tauri Channel | 控制/进度走小消息，大 placement 数据写 job bundle 后分页读取 |
| 可选服务 | FastAPI | 只为外部系统集成显式启动；桌面默认不开 localhost 端口 |
| 打包 | Tauri 原生包 + PyInstaller `onedir` Python worker | 每个 OS/CPU 在原生 CI 构建；并行 PoC Nuitka `standalone` 后按成品数据选择 |

语言策略是按价值而不是标签选择：

- 纯 Python 当然优先，因为调试和发布最简单；
- C/C++/Rust 可通过官方 wheel、pybind11/PyO3/cffi 或受控 CLI 接入，完全属于主候选范围；
- native binding 仍运行在独立 Python worker 中，段错误不能拖垮 Tauri 主进程；
- Java 不作一票否决。实测 Skjolber LAFF 的基础几何和 100 件性能合格，但它未原生补齐本项目最难的承压、轴荷和价格目标，当前收益不足以抵消裁剪 JRE、第二进程协议、签名和三平台打包成本，因此只保留为选装 sidecar/强对照；
- Rust `u-nesting` 已完成构建、上游测试和跨语言实测。ExtremePoint 可保留为单容器布局基线；Layer、GA、BRKGA、SA 的共享 decoder 已复现越界，且 seed/time limit 接线不完整，当前不能进入生产 shortlist。

## 2. 产品边界

### 2.1 实际要解的不是一个问题

同一产品至少要显式区分：

1. 固定一个容器尽量多装的 3D knapsack；
2. 同型容器全部装完、最少箱数的 3D bin packing；
3. 多箱型、有价格和有限/无限供应的 variable-sized/heterogeneous BPP；
4. 已知车辆实例的多容器装载；
5. 带站点和倒货成本的多站装载，必要时与路径联合。

`problem_kind`、必装/可选需求和目标优先级必须进入 Schema，不能由输入中是否有 `price` 猜测。推荐词典序目标：硬约束违规为 0、必装漏装为 0、总成本最小，然后才是箱数、利用率、重心偏差、倒货和固定材料。

### 2.2 首版能承诺什么

首版承诺“可信的正交候选布局”：长方体、有限允许姿态、箱型价格/数量、重量、障碍/禁区、保守支撑/顶载、简单重心/轴荷、多站轴向近似，以及独立验证报告。

首版不承诺：

- 数百件任意约束实例的全局最优；
- 连续任意角装箱的通用全局最优；
- 仅凭最终坐标就证明货物可穿过门或叉车路径可执行；
- 用支持面积比例代替承压、动态稳定或系固证明；
- 用理论质量代替 VGM/称量，用软件方案代替危险品、航空 W&B 或现场签核。

结果状态应逐级升级：

```text
LAYOUT_ONLY
  -> GEOMETRY_VALIDATED
  -> PHYSICS_VALIDATED
  -> COMPLIANCE_VALIDATED
  -> EXECUTION_APPROVED
```

界面和报告只能显示已经有证据的级别。

## 3. 总体架构

```text
React/TypeScript UI + Three.js
          |
          | narrow commands / typed progress channel
          v
Tauri Rust core
  file scopes | process limits | updates | crash recovery
          |
          | packing-worker/1 over stdio
          v
Python application service
  Catalog / Job / Rules / SolverRun / Solution
          |
          +-- Precheck + normalization
          +-- CostAllocator: CP-SAT (SCIP/Gurobi/CPLEX optional)
          +-- Placement adapters
          |     +-- PackingSolver CLI
          |     +-- exact-small CP-SAT/SCIP
          |     +-- optional native binding / Java sidecar
          +-- IndependentValidator
          +-- SQLite index + immutable run bundle

CLI (packctl) --------------------^  same application service
Optional FastAPI -----------------^  separate deployment mode
```

关键隔离边界：

- WebView 不获得通用 shell 和文件系统权限；只调用 Rust 暴露的业务命令；
- Python stdout 只承载协议，stderr 承载结构化日志；
- 每个求解任务有独立目录、输入 hash、有效配置、seed、引擎版本/binary hash 和资源预算；
- native/JVM 引擎在 Python worker 内或其子进程运行，均不进入 UI 进程；
- 完整结果先写临时文件，完成校验后原子改名；崩溃时只保留明确标为候选的完整 artifact；
- 大型 placement 列表按容器/页读取，不以 5-10 Hz 进度流重复发送。

建议目标仓库边界：

```text
packages/
  packing-core/       Python 模型、application service、validator、adapters
  packing-cli/        packctl
  packing-worker/     stdio protocol、job lifecycle、resource limits
  packing-api/        可选 FastAPI transport
apps/
  desktop-ui/         React/TypeScript/Three.js
  desktop-shell/      Tauri Rust core
schemas/
  problem.schema.json
  solution.schema.json
  validation.schema.json
  worker-protocol.schema.json
```

## 4. 数据元模型

采用五个聚合边界，避免无限膨胀的 `Box` 类：

```text
Catalog
  CargoType / CarrierType / AuxiliaryType / PoseCatalog
        |
PackingJob -- Route / DemandLine / RegulatoryProfile / ObjectiveProfile
        |
NormalizedProblemSpec ---- SolverRun
        |                       |
PackingSolution ---------- ValidationReport
        |
ExecutionPlan / OperatorSignoff
```

### 4.1 必须进入模型的字段族

| 对象 | 关键字段 |
|---|---|
| `CargoType` | 名义/上下界尺寸与质量、局部坐标、重心偏移、允许姿态、六面间隙、承压/支撑、摩擦、站点、环境与合规数据及来源 |
| `CarrierType` | 舱室、真实可用内尺寸、门、障碍/禁区、价格、有限/无限数量、payload/gross/tare、地板/墙载、重心包络、轴荷模型、锚点和温区 |
| `PackingJob` | 明确的问题类型、有限需求数量、路线、规则包、目标顺序、资源预算和 unknown policy |
| `Placement` | 稳定实例 ID、容器/舱室、坐标、完整 pose、支撑边、装卸序列和辅助材料 |
| `ValidationReport` | 每条规则的 `PASS/FAIL/UNKNOWN/NOT_APPLICABLE`、actual、limit、margin、证据和 validator 版本 |

JSON Schema 使用 Draft 2020-12、`additionalProperties:false` 和显式 `schema_version`。外部值带单位，进入求解前归一为有界整数 tick；金额使用十进制定点数。承载器 `max_count:null` 可表示无业务上限，但一次任务的货物数量必须有限，JSON 中禁止 `Infinity/NaN`。

### 4.2 姿态不能只存六种尺寸排列

正交长方体只有 6 种边长排列，但有 24 个保持手性的面语义姿态。立方体尺寸不变，也仍可能违反“具体 top 面向上、label 朝门”。内部 `PoseCatalog` 保存完整局部面到世界轴映射，再投影到库支持的 6 个 rotation；求解器无法表达的面语义必须附加建模或 post-hard 验证。

姿态分三档：

| 模式 | 用法 | 发布建议 |
|---|---|---|
| `ORTHOGONAL_SET` | 24 个面语义姿态的允许子集 | 首版默认，成熟主路径 |
| `DISCRETE_POSES` | 工程师批准的固定旋转矩阵/OBB，例如 15°、30° | 第二阶段专家功能，离散搜索 + OBB/SAT + 支撑复验 |
| `CONTINUOUS_ENVELOPE` | 连续角区间/四元数的非凸优化 | 少量高价值特殊件；独立实验引擎与人工签核 |

## 5. 约束与验证策略

每条规则有两个正交维度：业务严重度 `HARD/SOFT/INFO`，执行阶段 `PRECHECK/IN_SOLVER/POSTCHECK/OPERATOR_SIGNOFF`。`POSTCHECK HARD` 失败仍必须淘汰方案，不能降级成黄色提示。

| 约束域 | 首版求解 | 独立验证/后续增强 |
|---|---|---|
| 数量、箱型供应、价格 | CP-SAT 主问题 | 重算实例完整性、成本和库存 |
| 边界、碰撞、间隙、姿态 | PackingSolver/CP-SAT/SCIP | AABB；斜角用 OBB/SAT；完整面语义复核 |
| 总质量 | 引擎内约束 | 含托盘/衬垫后的总质量重算 |
| 支撑、承压 | 首版用保守 stack/支撑比例 | 支撑图、重心投影、接触并集与载荷流 LP；动态稳定另算 |
| 重心、轴荷、地板载荷 | 线性一阶矩/简化车辆模型 | 每个卸货状态重新计算；复杂车型使用制造商曲线 |
| 多站卸货 | 轴向 LIFO/无遮挡近似 | 门洞、扫掠路径、搬运设备与有界倒货 |
| 空隙和固定 | 输出空腔/六面间隙/潜在滑移 | 辅材选择、摩擦、加速度、锚点和系固工程签核 |
| 危险品/温区 | 版本化规则生成分组/隔离 | 专域规则包 hard gate，缺数据默认拒绝 |

安全域缺失值不等于无限制。默认策略：质量、承压、危化分类等 `REJECT`；组织批准的保守值才可 `CONSERVATIVE_DEFAULT`；只有偏好数据可 `ALLOW_WITH_WARNING`。

## 6. 算法方案

### 6.1 为什么需要分层

三维正交装箱强 NP-hard。直接坐标 CP/MIP 对 `n` 件、`B` 个候选箱通常需要约 `O(n^2 B)` 的物品对六向分离关系；branch-and-bound 最坏指数。极点、最大空余空间、层/块和 beam search 在正常实例上很快，但没有通用最优保证。连续任意角又增加非凸旋转与 OBB 碰撞，不是正交算法加一个布尔开关。

因此首版采用“成本分配 + 单箱放置 + pattern 回流 + 独立验证”的 matheuristic：

1. 预检单件可装性、体积/重量下界、箱型 dominance、相容组和允许姿态；
2. CP-SAT 解箱型数量、价格、重量和相容性的松弛主问题，给出候选组合与下界；
3. 对候选 cluster 调 PackingSolver `box`，只有启用保守同底面堆栈/上压时才调 `boxstacks`；
4. 用多种排序、guide 和 seed 产生单箱 patterns；
5. CP-SAT/SCIP 在 pattern 池上重选最小成本组合；放置失败返回 no-good/conflict；
6. 独立 validator 拒绝所有硬约束失败方案；
7. 小规模任务同时跑 exact-small 直接模型。只有上下界闭合才升级为 `PROVEN_OPTIMAL`，否则显示 incumbent、合法 bound/gap 或“无可证明界”。

有限 pattern 池不是完整 branch-and-price，不得标为全局最优。首版 exact-small 件数阈值只能通过真实基准确定，10-30 件可作为起始实验范围，不是 SLA。

### 6.2 库的最终定位

| 引擎 | 定位 | 采用条件/拒绝原因 |
|---|---|---|
| PackingSolver C++ fork `d953148b` | 主正交启发式候选 | 工况覆盖最接近；759 个合法 THPACK 源和 `boxstacks` 9 项专项通过。必须 pin SHA、hash binary、子进程隔离，保留策略与上游回归 |
| PackingSolver 官方 rolling | 上游行为对照 | 异构成本 #536 等四个 issue/PR 尚未合并，不能把 fork 通过写成官方已修复 |
| OR-Tools CP-SAT | 默认成本/pattern master、exact-small | Apache-2.0、多平台 wheel、逻辑强；需自建 3D 模型且只接受整数 |
| SCIP/PySCIPOpt | 开放 MIP/CIP 研究轨 | 适合连续坐标、cuts、载荷流；不是现成装箱库 |
| Gurobi/CPLEX | 商业 exact 插件 | 真实企业规模基准有收益且生产/离线/分发许可已确认 |
| `py3dbp` | 基准和候选生成 | THPACK9 44/44 合法，但 53 对中 41 对受排序影响；无成本、姿态子集、支撑/承压/轴荷和 bound |
| Jerry 分支 | 仅参考可视化/支撑近似 | 174 个执行结果有 4 个重叠；`loadbear` 实际只排序，不能当承压约束 |
| Skjolber Java Plain/LAFF | 强几何对照、可选 sidecar | 两算法 THPACK9 各 44/44 合法；Plain 本轮质量优于 LAFF。只有 obstacles/controls 带来真实收益时才打包 JVM |
| Go `bp3d` | 不采用 | THPACK9 44/44 合法，但禁旋和累计重量专项失败；拒绝原因是约束语义，不是 Go |
| Rust `u-nesting` ExtremePoint | 观察项/单箱基线 | THPACK9 adapter 44/44 合法；上游原生只接受一个 `Boundary3D`，Python/PyO3 构建还需固定多仓依赖 |
| Rust Layer/GA/BRKGA/SA | 不采用 | 共用 Layer decoder，旋转专项和 THPACK9-1 产生越界 placement；无效低箱数不得排名 |

### 6.3 PackingSolver 的现实门禁

它是最接近工况的候选，但当前滚动版不能直接上线：

- `box` 和 `boxstacks` 的 `variable-sized-bin-packing` 都在 `Solution::operator<` 阶段异常退出；当前源码 switch 确无对应 case；
- 普通 `bin-packing` 随箱型输入顺序变化，不能替代价格目标；
- 一个刻意收紧的半挂轴荷合成边界例发生分配类异常且没有 certificate；这只证明该路径未通过，不代表全部正常轴荷参数失效；
- 官方滚动预编译资产覆盖 Linux x64、Windows x64、macOS x64；macOS arm64 等目标要自行从固定源码构建并在 CI 验证。

已向上游提交四个最小复现 issue（#536–#539）及对应 PR（#540–#543），但截至 2026-08-31 均为 open、尚未合并；在合并前仍需固定本地已回归的源码提交、在三平台自行构建，保留异构成本、箱序反转、正常/边界/不可行轴荷测试。修复前由 CP-SAT/SCIP 承担成本选择，轴荷一律由独立静力校核器硬门禁。

应急源码可固定到用户 fork [`HansBug/packingsolver@d953148b8f710c06fa6c410949b7272f9e36327b`](https://github.com/HansBug/packingsolver/tree/d953148b8f710c06fa6c410949b7272f9e36327b)。该 `master` 已整合 #540–#543 并追加 data-driven 回归；本轮全量 campaign 使用的 `box` binary SHA-256 为 `1a1a114938a9c2ebf12225751b8c88d69b9fc2b2a434f6ca2f51531d3cf26285`。它仍是 fork，不是官方 release。

## 7. 本地实测结论

只跑“最少箱数”无法回答本项目的算法能力。THPACK1–8 是单箱 knapsack，主指标是 packed volume；THPACK9 才是装完全部物品后最少箱数。即便箱数更少，只要存在漏件、越界、重叠、非法姿态或超重，certificate 就必须作废。价格、堆叠、轴荷和卸货又需要独立专项，因为 THPACK 没有这些字段。各 benchmark 的字段、主指标、不能外推的结论和逐库运行状态见 [`results/campaign/README.md`](results/campaign/README.md)。

### 7.1 PackingSolver 公开全集与时间预算

固定 fork 运行 762 条 THPACK 记录，其中 THPACK9 18–20 为 malformed source 并排除，留下 759 个合法源。1 秒和 10 秒结果都从原始 certificate archive 离线重验：逐件 ID/数量、允许 rotation 对应尺寸、箱尺寸、边界、AABB 重叠、packed volume、箱数和完整性全部重算。759/759 均为合法 certificate；solver-reported bound 只记录为 `SOLVER_REPORTED_BOUND_CLOSED`，不当作独立最优性证明。

| 问题族 | 目标 | 1 s | 10 s | 配对行为 |
|---|---|---:|---:|---|
| BR，700 例 | 单箱最大体积利用率 | mean `0.7216`；166 个 0-item incumbent | mean `0.9624`；0 个空解 | 673 改善、27 相同、0 变差 |
| LN，15 例 | 单箱最大体积利用率 | mean `0.5072`；5 个 0-item incumbent | mean `0.7115`；0 个空解 | 7 改善、8 相同、0 变差 |
| IMM，44 个合法例 | 多箱最少箱数 | mean/median `15.48/11.5`；23 个 reported bound closed | mean/median `15.48/11.5`；25 个 reported bound closed | 44 个箱数全部相同 |

10 秒预算显著改善 knapsack 初解，并消除 BR/LN 空解，但没有让 THPACK9 少用箱。不能由此写成“10 秒总是更优”或“1 秒已足够”：三个问题族的搜索行为不同。

### 7.1.1 B07 Davies-Bischoff 困难单箱分布

B07 补的是 BR/LN 之外的公开困难分布：固定容器 `587×233×220`，来源为 `BR0`、`BR8`–`BR15` 九个桶，每桶 100 个实例，共 900 例。输入 CSV 显式冻结六种轴向排列许可；本轮只运行 `box` 轨，fork 和 upstream patched 分开记录。upstream 使用了为复现已知 comparator 问题而保留的源码 patch，不能称为官方未修改 release；fork 输入和 binary 均绑定到 [`HansBug/packingsolver@d953148b`](https://github.com/HansBug/packingsolver/tree/d953148b8f710c06fa6c410949b7272f9e36327b)，campaign summary/manifest 绑定 source commit、binary hash，所有布局均经过独立 certificate validator。

四组全量运行都是 `900/900` 条记录、`900/900` 合法 partial certificate；B07 的目标是单箱 packed-volume，不要求装完全部件，因此 `VALID_PARTIAL` 是预期状态。整体结果如下，均值按 900 例计算：

| 实现/预算 | mean utilization | median | p95 | 预算配对（10 s 相对 1 s） |
|---|---:|---:|---:|---:|
| fork / 1 s | `0.100890` | `0` | `0.929065` | 820 改善 / 80 持平 / 0 变差 |
| fork / 10 s | `0.949427` | `0.953804` | `0.963448` | |
| upstream patched / 1 s | `0.100897` | `0` | `0.929065` | 819 改善 / 81 持平 / 0 变差 |
| upstream patched / 10 s | `0.949377` | `0.953739` | `0.963448` | |

10 s 下 upstream 相对 fork 的逐实例结果为 `13` 胜、`834` 平、`53` 负，平均差为 `-0.0000500`（upstream minus fork）；这不是严格支配关系。按困难桶的 10 s mean utilization，fork 为：`BR0 0.909800`、`BR8 0.959940`、`BR9 0.957578`、`BR10 0.956700`、`BR11 0.955095`、`BR12 0.954063`、`BR13 0.952356`、`BR14 0.950343`、`BR15 0.948967`；对应 upstream 为 `0.909831`、`0.960105`、`0.957582`、`0.956684`、`0.955037`、`0.953897`、`0.952087`、`0.950216`、`0.948952`。完整逐桶/逐预算配对表见 [`B07-version-pairwise.csv`](results/comprehensive/rankings/B07-version-pairwise.csv)，原始 JSONL 和 tarball 在 [`results/comprehensive/runs/`](results/comprehensive/runs/) 与 [`raw/experiments/comprehensive/B07/`](raw/experiments/comprehensive/B07/)。

B07 能回答“困难尺寸桶上的正交单箱 anytime 鲁棒性、预算响应和版本漂移”，不能回答多箱成本、库存、承压、轴荷、连续装入路径或卸货顺序。1 s 下 BR8–BR15 的大量 `0` 利用率是合法低预算 incumbent；只有独立 validator 报出的越界、重叠、漏件/身份或旋转白名单错误才算证书错误。B07 也不能替代 B05 的外部多箱分布、B08–B18 的目标/硬约束套件或 B19+ 的工业 full 轨。

### 7.1.2 BR/LN 之外的完整 benchmark 建议

建议保留 `B01–B32`，按问题族分别排行，绝不合成跨目标“总冠军”。选择理由、每个套件适用的库/算法轨道、主指标及不可外推边界详见 [benchmark 选择与覆盖决策](research/benchmark-selection.md)；执行顺序和 ALL-libs 记录规则详见 [benchmark 执行优先级与全库横评建议](research/benchmark-execution-plan.md)。核心取舍是：

| 问题族 | benchmark | 参加的库/算法 | 结果主要说明 |
|---|---|---|---|
| 单箱体积与困难分布 | B01 BR、B02 LN、B07 BR0/BR8–15 | PackingSolver 原生；Python/Go/Jerry、Rust/Skjolber 在语义一致时作 composed/projection；exact 只跑小子集 | 合法率、体积利用率、姿态/排序敏感性和 anytime 预算响应 |
| 价值目标 | B03 Profit-KP | PackingSolver 原生；固定姿态 Rust composed；其他库只能放宽旋转 projection；exact 20 件 | 是否真正优化 profit，而非只优化体积；小规模 objective gap/proof |
| 同型多箱 | B04 IMM、B05 MPV 3D-BPP | 全部几何库；exact 小规模；B05 来源冻结后才排名 | 装完完整性、箱数质量和分布迁移；THPACK9 单独结果不够 |
| 真值与成本 | B06 exact oracle、B08 多箱型成本、B09 variable-cost exact、B10 固定异构、B11 open dimension | CP-SAT/SCIP/Gurobi/CPLEX 原生；PackingSolver cost/open 轨；其余只能 projection | 成本方向、箱型/库存选择、开放维度目标和启发式距真值的差距 |
| 约束合规 | B12 姿态、B13 重量/库存、B14 支撑/承压、B15 重心/轴荷、B16 障碍/门洞、B17 卸货、B18 相容性 | 原生能表达者进入 FULL；其余只作 post-validator/projection，并保留 NOT_SUPPORTED | 硬约束是否真的执行；违反率先于箱数/体积进入门禁 |
| 工业 full | B19 Alonso 2019、B20 Alonso 2020、B21 VRPTW-CLP、B22 irregular、B23 脱敏真实订单、B30 BAYTP | 只有保留车辆/托盘/路线/货架/非规则字段的 adapter 才能进 FULL；其余明确 projection 或 NOT_SUPPORTED | 从公开正交数据到真实应用的分布迁移和端到端可行率；不能把删字段后的分数叫工业能力 |
| 可靠性与在线 | B24–B29 metamorphic、numeric、repeatability、scalability、fault/cancellation；B31 mixed-SKU pallet；B32 online/incremental | 所有库都需 capability/conformance；随机算法至少 5 seed；online 需原生增量 adapter | 表示/单位/顺序一致性、质量-延迟-RSS 拐点、取消恢复和在线重排代价 |

因此“ALL libs”不是让每个库都输出一个数字，而是让每个 `benchmark × implementation × variant × budget` 都有明确状态：`SUPPORTED_NATIVE`、`SUPPORTED_COMPOSED`、`PROJECTION_ONLY`、`NOT_SUPPORTED`、`ADAPTER_MISSING` 或运行失败。只有输入 hash、姿态语义、预算和 validator 完全一致且 certificate 合法的记录才进入对应问题族排行。

当前综合证据仍不是全套件完成：`13/32` benchmark 有记录、`91/608` cell 有证据，其中 `27` 个 cell 已执行 protocol-v3，合计 `6,947` 条记录（legacy `2,078`，protocol-v3 `4,869`）。B05 新增的 19 条记录是经来源审计生成的 `SOURCE_INCOMPLETE / NOT_RUN / SOURCE_PENDING` 状态记录，不是实际求解运行，也不计入 27 个 executed cells。本轮约束 gauntlet 覆盖四个 PackingSolver 版本变体和 30 条实例记录；它补充了硬约束行为证据，不能替代其他库的全量 adapter。B05 来源仍未冻结，B08、B10–B11 和 B19+ 尚未形成全库共同适配器，B24–B32 也只完成局部专项；在这些门禁完成前，报告只宣称“已完成子集结果 + 覆盖计划”，不宣称 ALL-libs 全量完成。

### 7.2 Protocol-v3 约束 gauntlet 实测

本轮新增 runner 对已冻结的异构成本、姿态、重量、堆叠、轴荷和卸货 fixture 进行了四条 PackingSolver 原生轨复测。每条记录都有 canonical 输入、源码/二进制 hash、配置、stdout/stderr、资源、CSV certificate 和独立 validator；总计 30 条 protocol-v3 记录，均为 10 s 预算。

| 问题族 | fork `box` | fork `boxstacks` | upstream patched `box` | upstream patched `boxstacks` | 结论 |
|---|---|---|---|---|---|
| B09 成本方向 | 2/2 `VALID_COMPLETE`，两种价格方向均 cost=10 | 2/2 `VALID_COMPLETE`，两种价格方向均 cost=10 | 2/2 `VALID_COMPLETE`，两种价格方向均 cost=10 | 2/2 `VALID_COMPLETE`，两种价格方向均 cost=10 | fork 与 patched upstream 的两个模型在小型回归上正确；不能外推到大规模全局最优 |
| B12 姿态 | 1 个合法姿态 + 1 个预期不可行，2/2 行为通过 | 不适用 | 1 个合法姿态 + 1 个预期不可行，2/2 行为通过 | 不适用 | 姿态白名单被独立 validator 复核；`rotation_forbidden` 不是失败，而是允许姿态全部放不进箱 |
| B13 重量/库存 | 1/1 `VALID_COMPLETE`，3 件分到 3 个箱 | 不适用 | 1/1 `VALID_COMPLETE` | 不适用 | 总重量和 copies 守恒有效进入 hard check |
| B14 堆叠/承压 | 不适用 | 3/3 `VALID_COMPLETE` | 不适用 | 3/3 `VALID_COMPLETE` | `boxstacks` 的最大上方重量、最大堆数和 nesting fixture 通过；仍不是通用支撑/材料力学模型 |
| B15 轴荷 | 不适用 | 正常例通过；2 个反例按预期不可行，3/3 行为通过 | 不适用 | 正常例通过；2 个反例触发进程错误 | fork 的轴荷路径可用于当前模型；upstream 的边界/不可行轴荷仍受已知 #537/#539 路径影响 |
| B17 卸货 | 不适用 | 2/2 `VALID_COMPLETE` | 不适用 | 2/2 `VALID_COMPLETE` | 无约束和 Increasing-X 顺序均通过；不等于完整路线/时间窗优化 |

`constraint-conformance.csv` 同时包含历史 baseline 和本轮 protocol-v3 记录；正式比较必须按 `record_origin`、轨道和实例交集拆开。upstream 轴荷错误保留为 `run_status=ERROR`，没有被写成 `PROVEN_INFEASIBLE`。完整 runner、fixture 说明和复现命令见 [`research/constraint-gauntlet.md`](research/constraint-gauntlet.md) 与 [`results/comprehensive/README.md`](results/comprehensive/README.md)。

### 7.3 THPACK9 44 例跨实现质量

下表只统计完整且通过独立 certificate 检查的结果。THPACK9 没有 published optimum；相对体积下界只用于诊断，不能替代合法 dual bound。

| 实现 | 有效 certificate | mean bins | median bins | 观察 |
|---|---:|---:|---:|---|
| PackingSolver fork，1 s/10 s | 44/44 | 15.48 | 11.5 | 本轮质量最好；两档箱数相同 |
| Skjolber Plain | 44/44 | 17.80 | 14 | 27 例优于 LAFF，17 例相同 |
| Rust ExtremePoint adapter | 44/44 | 18.41 | 14 | 原生单 boundary，外层重复调用形成多箱 |
| `py3dbp` 降序 | 44/44 | 18.43 | 14 | 与 Rust EP 很接近，但整体顺序敏感 |
| Jerry 降序 | 43/44 | 18.72 | 14 | 1 条重叠；均值只基于 43 条有效记录 |
| Go `bp3d` | 44/44 | 19.93 | 16 | 几何有效，但另有禁旋/重量语义缺陷 |
| Skjolber LAFF | 44/44 | 20.84 | 17 | 层结构在该分布未带来质量优势 |

跨语言微型计时没有统一 JVM/进程启动、停止粒度和计时边界，因此本报告不据此作性能排名。

### 7.4 顺序、策略与硬约束

- Python campaign 计划 3,048 条状态记录；语义可表达并实际执行 280 条，276 条合法。`py3dbp` 的 53 对可比实例中 41 对质量随升/降序改变。Jerry 的 87 对中 66 对质量改变、4 对有效性改变；4 条重叠来自 `fix_point=True` 吸附坐标后未重新检查碰撞，改为 `fix_point=False` 后对照合法。
- PackingSolver `boxstacks` 9/9 通过：异构成本、最大上方重量、最大堆数、nesting、正常/边界/不可行轴荷、无卸货约束和 IncreasingX。正常轴荷由独立公式重算为 middle `6315.789... <= 6400`、rear `3000 <= 9000`。
- PackingSolver 策略专项中 auto、tree search、maximal spaces、sequential single knapsack 和 sequential value correction 的已运行记录合法；column generation 在 THPACK9-47 返回 0/99 件，validator 判 `INVALID`。
- Rust ExtremePoint 在 THPACK9-1 重复 5/5 均为 50 箱且合法。Layer、GA、BRKGA、SA 每类重复 5 次均越界，报告的 15–16 箱全部作废；在 20 个主实验场景中逐策略只有 Layer 3/5、GA 3/5、BRKGA 4/5、SA 4/5 通过独立校验。源码显示换层后只检查 Z、未重检姿态后的 X/Y；GA/BRKGA/SA 共用该 decoder。请求的 seed 未接入随机 runner，多数策略也没有读取 `time_limit_ms`，适合分别向上游提交 issue 和小 PR。
- Go `bp3d` THPACK9 44/44 合法，但专项证明它没有逐件姿态白名单，`PutItem` 也不检查累计 `MaxWeight`。这类失败不会出现在纯几何 THPACK 排名中。

### 7.5 B03 profit 3D-KP 全库对照

B03 是 60 个 Egeblad-Pisinger 实例，覆盖 20/40/60 件、C/L/F/U/D 形状、clustered/random 和 50/90 容量档。来源审计发现上游 57 行参照表中 48 行低于单件最大 profit，且缺 3 行，因此整表标记 `INVALID_REFERENCE_TABLE`，没有使用 reference gap。所有结果都由同一独立 AABB/copies/姿态 validator 重验；完整 runner、原始 stdout/stderr、资源和二进制 hash 见 [`results/comprehensive/rankings/profit-knapsack.csv`](results/comprehensive/rankings/profit-knapsack.csv) 与 [`research/b03-source-audit.md`](research/b03-source-audit.md)。

下表是 60 例平均 `packed_profit / total_available_profit`；固定姿态和全旋转投影不混排，10 s 对没有内部 time-limit 的库只是重复运行边界，不应解读为额外搜索时间。

| 轨道/实现 | 预算 | 合法率 | mean profit fraction | mean solver time | 解释 |
|---|---:|---:|---:|---:|---|
| `FIXED_XYZ` Rust ExtremePoint | 1 s | 60/60 | 0.4614 | 0.00014 s | 固定姿态单箱 adapter 基线，速度快但不优化 profit |
| `FIXED_XYZ` PackingSolver official | 1 s | 60/60 | 0.4498 | 1.118 s | 原生 profit；官方 rolling 对照 |
| `FIXED_XYZ` PackingSolver fork | 1 s | 60/60 | 0.4442 | 1.146 s | fork 与官方差异不稳定，不能宣称普遍优于官方 |
| `FIXED_XYZ` Rust SA/GA/BRKGA | 1 s | 60/60 | 0.4078/0.4025/0.3906 | 0.0230/0.0585/0.0175 s | 共享 adapter 可出合法布局，但未接通有效 profit objective |
| `FIXED_XYZ` Rust Layer | 1 s | 60/60 | 0.3138 | 0.00004 s | 极快几何 baseline，质量明显较低 |
| `RELAXED_ALL_ROTATIONS` py3dbp | 1 s | 60/60 | 0.5047 | 0.0876 s | 放宽旋转且 best-of-ascending/descending；不能与 fixed 原题直接比较 |
| `RELAXED_ALL_ROTATIONS` Jerry | 1 s | 59/60 | 0.5006 | 0.5165 s | 1 例最终证书非法；另外 3 个候选布局失败被保留为可靠性证据 |
| `RELAXED_ALL_ROTATIONS` Go bp3d | 1 s | 60/60 | 0.4761 | 0.00038 s | 几何投影合法，但库不优化 profit |
| `FIXED_XYZ` PackingSolver fork | 10 s | 60/60 | 0.5217 | 9.252 s | 10 s 相比 1 s 提升约 17.4%（同一 fixed 轨） |
| `FIXED_XYZ` PackingSolver official | 10 s | 60/60 | 0.5214 | 9.236 s | 与 fork 几乎持平；两者均为合法 incumbent，不是 proof |

固定姿态 1 s 配对中 fork 相对官方为 6 胜/49 平/5 负，10 s 为 3 胜/56 平/1 负；10 s 总收益 fork 高 407,115，但不能据此把 fork 作为所有实例的严格支配版本。exact CP-SAT 只跑 20 件子集：20/20 合法、13/20 在 20 s 内证明最优，7/20 返回合法 incumbent 与上界；它用于校准小规模模型，不给 40/60 件实例制造伪造 optimum。

该实验支持的工程结论是：PackingSolver fork 仍是最接近 B03 原题语义的正交主候选，Python/Go/Jerry 只适合作为放宽旋转的候选生成器或对照；Rust ExtremePoint 是低延迟几何基线，不是 profit 优化器；Rust GA/BRKGA/SA/Layer 目前不能替代原生 profit 求解。完整的 32 套 benchmark 选择、每个套件适用库和结论边界见 [benchmark 选择与覆盖决策](research/benchmark-selection.md)；运行波次、ALL-libs 记录规则和范围外扩展见 [benchmark 执行优先级与全库横评建议](research/benchmark-execution-plan.md)。

### 7.6 精确后端与 formulation

OR-Tools CP-SAT 9.15、SCIP/PySCIPOpt 6.2.1、Gurobi 13.0.3 和 CPLEX 22.1.2.0 都运行了同一组 7 个手工真值场景：网格、9 件溢出拆箱、需旋转、禁旋、重量拆箱、两种异构成本方向。canonical strengthened formulation 四家均为 7/7，证书与目标复算通过。

legacy/reduced/strengthened 三种 formulation 用于模型敏感性，不是求解器速度榜。CPLEX legacy 的 1,489 条约束超过 promotional license 的 1,000 条上限；SCIP 和 CPLEX 的 reduced `overflow_9` 在 20 秒内未证明；strengthened 四后端都闭合。这里首先说明加强约束和对称处理的重要性，不能外推为某个 solver 在一般 3D 实例上固定更快。

### 7.7 工业数据集状态

Alonso 2019 的 111 个实例和 Alonso 2020 的 107 个实例已完成字段、行数、需求恒等式和语义审计，但现有库没有保真表达其完整车辆/托盘/交付约束，因此状态为 `NOT_SUPPORTED / NOT_RUN`。ESICUP 的 BAYTP 快照缺少公共 `products`/`shelves`；虽从 OR-Library 核对了对应文件与 SHA-256，仍标为 `ESICUP_SNAPSHOT_INCOMPLETE / NOT_RUN`。删除字段后运行普通 3D 箱数算法会改变问题，不能作为完整 benchmark 分数。

## 8. GUI 与三维产品原型

### 8.1 主工作流

```text
创建/导入任务
  -> 单位、引用、可装性和缺失数据预检
  -> 编辑货物/承载器/姿态/堆码/路线/目标
  -> 查看所选引擎 capability matrix
  -> 在资源预算内运行、取消或派生 run
  -> 比较合法候选与 Pareto 指标
  -> 3D、表格和 validator issue 联动复核
  -> 固化方案 revision、装载清单、报告与签核
```

打开应用直接进入工作区。左侧导航为项目、目录、规则、求解运行、方案、导入导出和设置；不做营销式首页。任务编辑器采用全宽虚拟表格 + 右侧当前行 inspector，支持 CSV/XLSX 映射、矩形粘贴、批量赋值、undo/redo、单位显示、错误定位和个体例外。

### 8.2 求解与方案比较

求解前列出每类 HARD 约束由哪个阶段“求解内保证/求解后硬校核/不支持”。没有可执行 hard gate 时禁止启动。运行页显示 phase、elapsed、CPU/RSS、当前最好成本/箱数/利用率、合法 bound/gap、候选时间线和 worker 状态；明确区分 timeout、用户取消、infeasible、OOM 和 crash。

多方案页允许 pin 2-4 个候选，对比成本、箱型用量、漏装、利用率、重心/轴荷余量、承压最小余量、倒货和固定需求。硬不可行方案不进入 Pareto front，也不生成含混的单一“综合分”。

### 8.3 三维检查器

3D 是全宽工作面，左侧容器/步骤树，右侧 selection/issue inspector，底部装载时间轴。首版必须有：

- orbit/pan/zoom、正交/透视与六向视图；
- 实例拾取、框选、搜索，按 SKU/站点/问题隐藏、ghost 或 isolate；
- X/Y/Z 剖切，精确输入剖切位置；
- 装载步骤逐件/逐批播放，issue 与实例双向定位；
- 选中件的 pose、坐标、质量、支撑、上方传递载荷、站点和数据来源；
- 碰撞、越界、方向、支撑、承压、重心/轴荷等分类高亮；
- 门、障碍、keepout、重心包络、轴/地板载 overlay；
- 顶/侧/端 2D 正投影、坐标、编号和装载顺序导出。

若没有通过装入路径验证，动画必须叫 `layout animation`，不能叫 `executable loading sequence`。glTF/PNG 只是交流视图；CSV/XLSX/JSONL placement 明细必须由 manifest 绑定完整 problem/solution hash、单位、预期件数和 validator/version。权威结果始终是带 hash/schema 的完整 ProblemSpec/Solution/ValidationReport JSON。

### 8.4 Three.js 实现要点

后端保留整数坐标，渲染时映射到 Three.js 的 Y-up 坐标。相同几何/材质组使用 `InstancedMesh`；边线和标签只为选中/问题项创建；placement 数组和 scene 生命周期不放进 React 热路径。Node 数据层烟测在 256 MiB V8 heap 上限内创建 10,000 实例、计算 bounds、完成 instance picking 和 clipping plane 配置组合；本次归档运行约 23.211 ms、68,120 KiB RSS，且不含 GPU renderer。脚本、fixture 与原始输出见 [`smoke.mjs`](benchmarks/frontend-three-smoke/smoke.mjs)、[`smoke.stdout`](raw/experiments/frontend-three-smoke/smoke.stdout) 和 [`smoke.resources.txt`](raw/experiments/frontend-three-smoke/smoke.resources.txt)。正式决策门仍需三平台实际 Tauri WebView 的 1k/10k/50k FPS、显存、拾取和 GPU 恢复测试。

## 9. CLI、IPC 与插件契约

CLI 最少提供：

YAML/CSV/XLSX 只作便捷导入。导入器拒绝歧义并完成单位、默认值和 ID 归一化，产出带 `schema_version` 的 canonical JSON；hash、求解和复现均绑定归一化后的 JSON。

```bash
packctl project import job.yaml --out job.json
packctl project validate job.json --format json
packctl solve job.json --profile balanced --engine portfolio --time-limit 120s --threads 4 --seed 7 --out run-001
packctl verify run-001/solution.json --problem job.json --strict
packctl inspect run-001 --solutions --format table
packctl export run-001/solution.json --format pdf --out load-plan.pdf
packctl engines list --capabilities
```

机器结果只写 stdout，日志写 stderr；长任务用 NDJSON 进度；稳定 exit code 区分输入无效、无可行解、超时/取消、引擎故障和验证失败。GUI 的“复制 CLI 命令”从 effective run spec 生成。

统一 `EngineAdapter` 接口：

```text
capabilities()
validate_support(problem)
solve(problem, limits, progress, cancel)
normalize(raw_solution)
```

每个 adapter 必须完成版本握手、能力声明、线程/内存/时间限制、取消、stderr 捕获、异常归一和 provenance。不得让项目文件或 UI 判断引擎实现语言。

Java sidecar 只有在统一真实基准上显著提高可行率、约束覆盖、成本/装载率或时限稳定性，且许可、固定 seed、资源限制、独立验证、jlink 体积和签名都通过时才进入可选安装包。UI 只看到 engine id/capability。

## 10. 跨平台发布

| 平台 | 首发目标 | 要点 |
|---|---|---|
| Windows | Windows 10/11 x64 | 原生 CI、NSIS/MSI、Authenticode、WebView2 离线策略、Windows Job Objects、GPU blacklist |
| macOS | arm64 首发，x64 单独产物 | `.app`/DMG、Developer ID、公证/staple、所有嵌套 Python/dylib/JVM 签名 |
| Linux | 明确支持的 LTS/Fedora x64 | 老 glibc 基线、AppImage + deb/rpm 取舍、WebKitGTK 4.1、Wayland/X11/Mesa/NVIDIA 实机矩阵 |

不要声称“一台 Linux 构建全部平台”。每个 release manifest 固化 shell、Python worker、native wheels、solver binary 和可选 JVM 的 SHA-256、SBOM、许可证/NOTICE。Linux 用 `setrlimit`/cgroup 能力、Windows 用 Job Objects、macOS 用可用的进程资源限制加内部 solver cap；所有平台都要验证强杀、子进程回收和 OOM 状态。

Tauri 的主要风险是 WebView 差异。先做 2-3 周 vertical slice；若只有目标 Linux WebKitGTK/GPU 长期不达标，切到 Electron 并复用同一 React/Three/Python 协议。若团队强 Python/Qt 且已解决 Qt Quick 3D 的 GPLv3/商业许可，再考虑 PySide6。不要长期维护三套 GUI。

## 11. 分阶段路线

### Phase 0：决策原型与基准门

- 冻结 Problem/Solution/Validation/Worker Schema v1；
- 完成 CLI、worker 协议、取消/强杀/崩溃恢复和 run bundle；
- Tauri vertical slice 覆盖 50k 编辑行、10k/50k 3D 实例和一个真实 native solver；
- Windows/macOS/Linux 各产一份可安装开发签名包；
- 建立经典几何、构造真值和脱敏订单三层 benchmark；
- 按 [`research/test-protocol.md`](research/test-protocol.md) 完成全部问题族 × 全部候选库的状态矩阵，并将原生、组合 adapter、精确模型和工业投影分榜；
- 跟踪已提交的 PackingSolver issue #536–#539 与 PR #540–#543；在合并前固定可回归源码提交。

退出条件：三平台 worker 故障不影响 UI；Schema 可由 Python/TS/Rust 一致解析；Tauri WebView 达到明确性能门；主候选升级不会绕过测试。

### Phase 1：可信正交 MVP

- 箱型价格与有限/无限供应、必装/可选需求；
- 24 面语义正交姿态，映射到有限 rotation；
- CP-SAT 成本主问题 + PackingSolver patterns + exact-small；
- 数量、几何、姿态、重量、保守支撑/顶载的独立 validator；
- GUI 任务编辑、运行、候选比较、3D 剖切/步骤/问题联动；
- JSON/CSV/XLSX/PDF 和可复现 job bundle。

退出条件：所有构造 hard-constraint 测试合法率 100%；异构成本与箱序 metamorphic tests 通过；超时/取消/崩溃不产生伪成功；每个结果有 input/solver/validator hash。

### Phase 2：运输作业

- 门洞/障碍和装入/卸出路径；
- 一般支撑图、载荷流、重心、复杂轴荷/地板载；
- 多站有界倒货、逐站剩余状态；
- 危险品/温区规则包接口；
- 空腔和固定需求、辅助物料回灌。

退出条件：每个运输状态都能重算安全余量；post-hard 失败不可批准；真实车辆/CTU 数据由责任方校准。

### Phase 3：专家能力

- 离散斜放 OBB；少量连续角实验插件；
- 动态滑移/倾覆、锚点和系固件选择；
- 冷链热工、航空 WBM/ULD 或外部专域系统接口；
- 真实基准证明价值后启用 Gurobi、Java 或其他 native engine 插件。

## 12. 主要风险与立即动作

| 风险 | 当前判断 | 动作 |
|---|---|---|
| 单一库覆盖幻觉 | 高 | capability matrix + 独立 validator；未建模不标“支持” |
| PackingSolver 当前回归 | 已复现 | 不用滚动 `latest` 上线；修复、pin、三平台回归 |
| 启发式被称为最优 | 高责任风险 | 只有合法 primal/dual bound 闭合才显示 `PROVEN_OPTIMAL` |
| 6 rotations 丢面语义 | 必然发生 | 24 pose catalog + solver mapping + post-hard 验证 |
| 支撑比例被误作力学 | 高 | 分开支持并集、重心、载荷流、压强和动态固定 |
| 连续斜角范围失控 | 高 | 默认正交，离散 pose 先行，连续角只给专家少量实例 |
| Java/native 崩溃或打包复杂 | 可控 | worker 故障域、选装引擎、统一协议、签名/资源门 |
| Tauri WebView 三平台差异 | 中高 | vertical slice 真机 GPU 矩阵；Electron 是明确后备 |
| 法规/设备数据过期 | 高 | authority/revision/effective date、签名规则包和现场签核 |
| 商业 solver 许可 | 高 | 插件化；未确认生产/离线/分发权就不进入默认包 |

立项后的第一批工程工作不应是继续写新的装箱启发式，而是固化 Schema、validator、benchmark 和 worker 故障边界；然后把通过实测的成熟引擎组合起来。这样后续替换 C++、Rust、Java 或商业求解器时，CLI、GUI、项目格式与安全结论都不需要推倒重来。
