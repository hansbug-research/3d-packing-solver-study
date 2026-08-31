# 跨平台三维装箱软件技术选型总报告

> 决策日期：2026-08-31。本文是技术架构与产品实施建议，不是车辆/集装箱/航空配载批准、结构计算、危险品合规证明或系固设计。详细证据分别见 [真实工况与元模型](research/domain-model.md)、[算法与论文/库实测](research/algorithms.md)、[逐特性算法/前端矩阵](research/decision-matrices.md)、[公共 benchmark 与指标](research/benchmarks.md)、[PackingSolver 上游核查](research/packingsolver-upstream.md)、[桌面与三维交互](research/frontend.md) 和 [本地测试摘要](results/test-summary.md)。

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
- Rust `u-nesting` 等新项目可观察，但不能因语言新而降低成熟度、约束覆盖和回归要求。

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
| PackingSolver C++ | 主正交启发式候选 | 工况覆盖最接近；必须 pin SHA、hash binary、子进程隔离，并关闭异构成本与轴荷边界回归 |
| OR-Tools CP-SAT | 默认成本/pattern master、exact-small | Apache-2.0、多平台 wheel、逻辑强；需自建 3D 模型且只接受整数 |
| SCIP/PySCIPOpt | 开放 MIP/CIP 研究轨 | 适合连续坐标、cuts、载荷流；不是现成装箱库 |
| Gurobi/CPLEX | 商业 exact 插件 | 真实企业规模基准有收益且生产/离线/分发许可已确认 |
| `py3dbp` | 基准和 smoke test | 很快但顺序敏感，无成本、姿态子集、支撑/承压/轴荷和 bound |
| Jerry 分支 | 仅参考可视化/支撑近似 | `loadbear` 实际只排序；本地反例未限制上压重量 |
| Skjolber Java | 强几何对照、可选 sidecar | LAFF 实测合格；只有障碍/controls/稳定 deadline 在真实基准显著胜出时才打包 JVM |
| Go `bp3d` | 不采用 | 维护旧且 `MaxWeight` 未进入放置可行性；拒绝原因不是 Go |
| Rust `u-nesting` | 观察项 | 2026 新项目、3D 仍是 axis-aligned，本机无 Cargo；未进入 shortlist、未实测 |

### 6.3 PackingSolver 的现实门禁

它是最接近工况的候选，但当前滚动版不能直接上线：

- `box` 和 `boxstacks` 的 `variable-sized-bin-packing` 都在 `Solution::operator<` 阶段异常退出；当前源码 switch 确无对应 case；
- 普通 `bin-packing` 随箱型输入顺序变化，不能替代价格目标；
- 一个刻意收紧的半挂轴荷合成边界例发生分配类异常且没有 certificate；这只证明该路径未通过，不代表全部正常轴荷参数失效；
- 官方滚动预编译资产覆盖 Linux x64、Windows x64、macOS x64；macOS arm64 等目标要自行从固定源码构建并在 CI 验证。

已向上游提交四个最小复现 issue（#536–#539）及对应 PR（#540–#543），但截至 2026-08-31 均为 open、尚未合并；在合并前仍需固定本地已回归的源码提交、在三平台自行构建，保留异构成本、箱序反转、正常/边界/不可行轴荷测试。修复前由 CP-SAT/SCIP 承担成本选择，轴荷一律由独立静力校核器硬门禁。

## 7. 本地实测结论

所有 Python/C++ 主测试均在外层 35 秒 timeout、4 GiB 虚拟内存和常见数值库单线程环境变量下复跑；PackingSolver 另有 10 秒/1 GiB 内部限制。详情和 JSON 路径见 [测试摘要](results/test-summary.md)。

| 候选 | 关键结果 | 判断 |
|---|---|---|
| PackingSolver | 网格、旋转子集、禁旋、总重量、`boxstacks` 上压通过；异构成本失败；轴荷边界例异常 | 有条件采用，不能盲信 README |
| PackingSolver 两文件最小 patch + HiGHS | 异构成本 `box`/`boxstacks` 均返回 0，选择 1 个成本 10 大箱，2/2 件并生成证书；公开 THPACK9-1 为 25 箱 | 仅本地验证，不是官方 release；已提交 issue [#536](https://github.com/fontanf/packingsolver/issues/536) / PR [#540](https://github.com/fontanf/packingsolver/pull/540)，open 未合并 |
| HansBug/packingsolver fork | `master` at `ac7b1384` integrates PR #540–#543 | 可在 pin 该 commit 后作为应急源码来源，仍不是官方 release |
| CP-SAT 9.15 | 9 个 `5^3` 物品装 `10^3` 箱：`OPTIMAL`，2 箱，bound 2，约 0.13 s solver | exact-small 模型语义与界通过 |
| PySCIPOpt 6.2.1 | 同例 `optimal`，目标/dual 都为 2，gap 0，约 0.06 s solver | 开放精确第二实现通过 |
| `py3dbp` 1.1.2 | 基础通过；异构箱小箱先为 2 箱，大箱先为 1 箱 | 顺序敏感，只作 baseline |
| Jerry | 脆弱件上方实际重量 20 仍被接受 | `loadbear` 不能当承压约束 |
| Skjolber `c73d521...` | 网格/旋转/upright/重量符合预期，100 件库内 21.275 ms，THPACK9-1 为 8.315 ms；当前 raw 冷 JVM 约 0.43 s/78,336 KiB | Java 可用但暂无独特到值得默认集成的能力 |
| Gurobi/CPLEX | 当前环境缺少 Python 包或运行时许可，复跑入口返回 `NOT_RUN`；两份历史 JSON 因模型字段与目标值矛盾，已标为 `INVALID_HISTORICAL_INCONSISTENT_FIXTURE` 并排除 | 没有可采信的本轮商业求解器数字；需在许可环境用固定 fixture 重跑 |

这些烟雾测试的功能覆盖比速度数字更重要。不同脚本的进程启动、案例数量和停止粒度不同，不能把微秒/毫秒列当跨语言性能榜。

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

若没有通过装入路径验证，动画必须叫 `layout animation`，不能叫 `executable loading sequence`。glTF/PNG 只是交流视图，权威结果始终是带 hash/schema 的 JSON 和验证报告。

### 8.4 Three.js 实现要点

后端保留整数坐标，渲染时映射到 Three.js 的 Y-up 坐标。相同几何/材质组使用 `InstancedMesh`；边线和标签只为选中/问题项创建；placement 数组和 scene 生命周期不放进 React 热路径。Node 数据层烟测在 256 MiB V8 heap 上限内创建 10,000 实例、计算 bounds、完成 instance picking 和 clipping plane 配置组合；本次归档运行约 23.211 ms、68,120 KiB RSS，且不含 GPU renderer。脚本、fixture 与原始输出见 [`smoke.mjs`](benchmarks/frontend-three-smoke/smoke.mjs)、[`smoke.stdout`](raw/experiments/frontend-three-smoke/smoke.stdout) 和 [`smoke.resources.txt`](raw/experiments/frontend-three-smoke/smoke.resources.txt)。正式决策门仍需三平台实际 Tauri WebView 的 1k/10k/50k FPS、显存、拾取和 GPU 恢复测试。

## 9. CLI、IPC 与插件契约

CLI 最少提供：

```bash
packctl project validate job.yaml --format json
packctl solve job.yaml --profile balanced --engine portfolio --time-limit 120s --threads 4 --seed 7 --out run-001
packctl verify run-001/solution.json --problem job.yaml --strict
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
