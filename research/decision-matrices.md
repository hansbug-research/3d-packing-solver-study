# 算法与前端决策矩阵

算法矩阵符号：✅ 原生能力且对应专项已通过；❌ 没有该能力；⚠️ 需要自建模型/adapter/扩展点，或本次存在已复现缺陷。矩阵按问题特性写，不把样例偶然满足某条约束当作能力证明。

## 算法/库矩阵

| 库/算法 | 正交旋转 | 24 面语义 | 逐件姿态子集 | 连续任意角 | 多箱装完 | 异构成本/库存 | 总重量 | 叠层/层高 | 最大上方重量 | 一般支撑/稳定 | 重心/轴荷 | 卸货/障碍 | 可证明界 | Python 融合 | 解证书 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PackingSolver 官方 `box` | ✅ 6 排列 | ❌ | ✅ 6 姿态白名单 | ❌ | ✅ | ⚠️ #536：官方版异构成本 comparator 崩溃 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ solver bound | ⚠️ C++ CLI 子进程 | ✅ CSV/JSON |
| PackingSolver 官方 `boxstacks` | ✅ | ❌ | ✅ 6 姿态白名单 | ❌ | ✅ | ⚠️ #536 | ✅ | ✅ nesting/堆数 | ✅ | ⚠️ 同底面 stack，不是一般接触载荷流 | ⚠️ 有接口，#537/#539 | ✅ increasing X/Y | ✅ solver bound | ⚠️ C++ CLI 子进程 | ✅ CSV/JSON |
| HansBug fork `box@d953148b` | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ 成本方向与 copies 回归通过 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ solver bound | ⚠️ 固定源码编译/CLI | ✅ CSV/JSON |
| HansBug fork `boxstacks@d953148b` | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ nesting/堆数 | ✅ | ⚠️ stack 模型边界 | ✅ 正常/边界/不可行专项通过 | ✅ increasing X | ✅ solver bound | ⚠️ 固定源码编译/CLI | ✅ CSV/JSON |
| OR-Tools CP-SAT 9.15 | ⚠️ 自建离散姿态 | ⚠️ 自建 face ID | ⚠️ 自建 | ❌ | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建线性化 | ⚠️ 自建 | ⚠️ 自建 | ✅ 7 个 exact-small 场景闭合 | ✅ Python wheel/native 核心 | ⚠️ 自行导出 |
| SCIP/PySCIPOpt 6.2.1 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 可建非线性模型，代价高 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ MIP/CIP/载荷流自建 | ⚠️ 自建 | ⚠️ 自建 | ✅ 7 个 exact-small 场景闭合 | ✅ Python binding/C++ 核心 | ⚠️ 自行导出 |
| Gurobi 13.0.3 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 非凸模型 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ✅ 7 个 strengthened 场景闭合 | ✅ `gurobipy`/商业许可 | ⚠️ 自行导出 |
| CPLEX 22.1.2 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 另需 CP Optimizer/模型 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ 自建 | ✅ 7 个 strengthened 场景闭合 | ✅ `cplex`/DOcplex/商业许可 | ⚠️ 自行导出 |
| `py3dbp` 1.1.2 pivot greedy | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ 无成本目标 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ 原生 Python | ⚠️ adapter 导出坐标 |
| Jerry `75764a` pivot/fix-point | ✅ | ❌ | ⚠️ `updown` 只有两档 | ❌ | ✅ | ❌ | ✅ | ⚠️ `level`/支撑启发式 | ⚠️ `loadbear` 只排序 | ⚠️ 四角/面积近似 | ❌ | ❌ | ❌ | ✅ 原生 Python fork | ⚠️ 4 条证书重叠 |
| Skjolber Plain/LAFF | ✅ | ❌ | ⚠️ 3D/2D rotate | ❌ | ✅ | ❌ | ✅ | ⚠️ controls 扩展点 | ❌ | ⚠️ 自定义 controls | ❌ | ✅ obstacles | ⚠️ brute force 仅小规模 | ⚠️ Java 常驻 sidecar | ⚠️ adapter 导出 placement |
| Go `bp3d@0ba3dcd` pivot greedy | ✅ | ❌ | ❌ | ❌ | ✅ 原生多箱 | ❌ | ⚠️ 字段存在但未执行硬检查 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ Go sidecar/C ABI 自建 | ⚠️ adapter 导出坐标 |
| Rust `u-nesting` ExtremePoint | ✅ | ❌ | ✅ `Fixed/Any` | ❌ | ⚠️ 上游单 boundary，adapter 重复调用 | ❌ | ✅ 单 boundary | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ PyO3/C ABI 自建 | ⚠️ adapter 导出；44/44 合法 |
| Rust `u-nesting` Layer/GA/BRKGA/SA | ⚠️ 接口有旋转，但专项出现越界 | ❌ | ⚠️ | ❌ | ⚠️ adapter | ❌ | ✅ 单 boundary | ⚠️ Layer decoder | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ PyO3/C ABI 自建 | ⚠️ 5 次重复均有无效证书 |

关键 warning：

- ⚠️ PackingSolver 异构成本缺陷属于官方上游：文档、CLI 和枚举都声明该目标，官方源码的 `box::Solution::operator<` 与 `boxstacks::Solution::operator<` 漏分支。HansBug fork `d953148b...` 已合并 #540–#543 和追加回归，不能把 fork 通过写成官方 release 已修复。
- ⚠️ Jerry 的 `loadbear` 本地反例允许脆弱件上方实际重量 20；它改变排序优先级，不是硬承压约束。
- ⚠️ Go `bp3d` 的 `MaxWeight` 字段存在，但放置函数没有用它拒绝超重方案。
- ⚠️ OR-Tools/SCIP/Gurobi/CPLEX 是建模引擎，不是现成 3D packer；这些行的 ⚠️ 表示可以由自建模型表达，不能解读为官方提供 3D global constraint。它们保留的 ✅ 只表示求解器自身的 bound/optimality 或 Python 接口能力。
- ⚠️ Rust `u-nesting` 的 `Packer3D` 原生只接受一个 `Boundary3D`。THPACK9 的多箱结果来自本仓库 repeated-single-boundary adapter；ExtremePoint 44/44 合法。Layer decoder 关联的 BottomLeftFill、GA、BRKGA、SA 在 THPACK9-1 和旋转专项中产生越界 placement，5 次重复仍失败；主实验逐策略有效率为 Layer 3/5、GA 3/5、BRKGA 4/5、SA 4/5；无效的 15–16 箱不能进入排名。

## 技术栈与算法行为矩阵

| 库/算法 | 核心技术栈 | 算法族 | 随机性/主要决策偏好 | Python 后端接入 | 本轮观察到的行为 |
|---|---|---|---|---|---|
| PackingSolver `box`/`boxstacks` | C++14、CMake、Boost/HiGHS 可选 | tree search、maximal spaces、sequential knapsack/value correction、column generation；`boxstacks` 先构造 stack | 多策略 portfolio；按 guide、bound 和停止预算改进 incumbent | 首版 subprocess + CSV/JSON；后续可做窄 C ABI/pybind11 | THPACK9 质量最好；10 s 主要改善 BR/LN knapsack；column generation 在 THPACK9-47 返回空解 |
| OR-Tools CP-SAT | C++ native core + Python wheel | SAT/CP/整数 branch-and-bound | 固定模型可设 seed/worker；强依赖整数化、对称消除和 formulation | 官方 Python wheel | strengthened 7/7；适合 exact-small 和成本主问题，不是现成 3D decoder |
| SCIP/PySCIPOpt | SCIP C/C++ core + PySCIPOpt binding | MIP/CIP/MINLP branch-and-cut | 分支、cuts、primal heuristics；模型松紧显著影响证明 | 官方 PySCIPOpt | strengthened 7/7；reduced `overflow_9` 20 s 未证明 |
| Gurobi | native commercial Optimizer + `gurobipy` | MIP/QCP/全局非线性 | 并行 MIP、cuts、heuristics、warm start | 官方 Python package + license | strengthened 7/7；本小例不能外推为通用速度优势 |
| CPLEX | native commercial CPLEX + `cplex`/DOcplex | LP/MIP branch-and-cut；CP Optimizer 是独立引擎 | formulation 和许可证限制同时影响结果 | 官方 Python package + license | strengthened 7/7；legacy 1,489 constraints 超 promotional limit |
| `py3dbp` | 纯 Python | pivot greedy | 体积排序和首个可行 pivot/rotation；输入顺序强影响结果 | 直接 import | 53 对中 41 对质量改变；降序 THPACK9 均值 18.43 箱 |
| Jerry fork | Python、NumPy/Matplotlib | `py3dbp` pivot + fix-point/level/support 近似 | fix-point 吸附、level/loadbear 排序；不是硬承压 | 直接 import | 87 对中 66 对质量改变；fix-point 吸附后不重检碰撞导致 4 条非法 |
| Skjolber Plain | Java 21/Maven | extreme-point/plain placement | 逐步选择可行 placement，较少强制层结构 | 常驻 JVM sidecar | THPACK9 均值 17.80；27 例优于 LAFF、17 例相同 |
| Skjolber LAFF | Java 21/Maven | Largest Area Fit First 层构造 | 偏好大底面积和规则层，速度/可解释性优先 | 常驻 JVM sidecar | THPACK9 均值 20.84；本数据分布未体现质量优势 |
| Go `bp3d` | Go module | pivot greedy | 按体积排序箱/件，首个可行旋转和 pivot | sidecar、RPC 或自建 C ABI | THPACK9 44/44 有效；禁旋、累计重量语义失败 |
| Rust ExtremePoint | Rust 1.98、Cargo；仓库含 PyO3/C FFI/WASM | extreme point first-fit | 体积降序，EP 按 z/y/x，首个可行姿态提交 | 可复用现有 PyO3，但源码依赖需固定四仓布局 | 单 boundary 原生；adapter THPACK9 44/44 有效，均值 18.41 |
| Rust Layer/GA/BRKGA/SA | Rust 1.98、`u-metaheur` | layer decoder + permutation/orientation metaheuristics | GA/BRKGA/SA 搜索顺序/姿态，但共用 Layer decoder | 同上 | decoder 越界；seed 未接线，多数策略 time limit 未生效 |

## Benchmark 运行状态矩阵

符号：✅ 适用记录全部合法；⚠️ 已运行但只覆盖部分语义、使用 adapter 或出现失败；❌ 没有保真实现该 benchmark。分母和失败原因见 [`results/campaign/README.md`](../results/campaign/README.md)。

| 库/算法 | BR/LN 715 例 | THPACK9 44 例 | 旋转/禁旋/重量/成本专项 | Exact-small 7 例 | 堆叠/轴荷/卸货 9 例 | 重复/顺序敏感性 | Alonso/BAYTP 完整问题 |
|---|---:|---:|---:|---:|---:|---:|---:|
| PackingSolver fork | ✅ 1 s/10 s | ✅ | ✅ | ❌ | ✅ | ⚠️ 策略专项有 1 条无效 | ❌ |
| PackingSolver 官方 | ❌ | ⚠️ 仅 THPACK9-1 | ⚠️ 异构成本 #536 | ❌ | ❌ | ❌ | ❌ |
| `py3dbp` | ⚠️ 53 例 × 2 顺序 | ✅ | ⚠️ 无逐件姿态/成本 | ❌ | ❌ | ⚠️ 41/53 质量变化 | ❌ |
| Jerry | ⚠️ 87 例 × 2 顺序，4 条非法 | ⚠️ 43/44 | ⚠️ `loadbear` 非硬约束 | ❌ | ❌ | ⚠️ 66/87 质量变化 | ❌ |
| Skjolber Plain/LAFF | ❌ | ✅ 两算法 | ⚠️ 既有小型 smoke | ❌ | ❌ | ✅ 同实例配对 | ❌ |
| Go `bp3d` | ❌ | ✅ | ⚠️ 禁旋/重量失败 | ❌ | ❌ | ❌ | ❌ |
| Rust ExtremePoint | ❌ | ⚠️ 44/44，adapter 多箱 | ✅ 能力声明内 7/7 | ❌ | ❌ | ✅ 5/5 有效 | ❌ |
| Rust Layer/GA/BRKGA/SA | ❌ | ❌ | ⚠️ 14/20 场景有效（Layer 3/5、GA 3/5、BRKGA 4/5、SA 4/5） | ❌ | ❌ | ❌ 每策略 5/5 非法 | ❌ |
| CP-SAT/SCIP/Gurobi/CPLEX | ❌ | ❌ | ❌ | ✅ strengthened 各 7/7 | ❌ | ⚠️ formulation sensitivity | ❌ |

## 工程定位矩阵

| 组件 | 算法角色 | 许可证/集成 | 本地证据 | 采用结论 |
|---|---|---|---|---|
| PackingSolver fork | tree search、maximal spaces、sequential single knapsack、value correction、column generation | MIT，C++ CLI；固定 SHA + 子进程 | THPACK 759 个合法源证书通过；`boxstacks` 9/9；column generation 在 THPACK9-47 返回空证书 | **主正交启发式候选，保留策略/版本回归** |
| PackingSolver 官方 rolling | 同上 | MIT，C++ CLI | 几何场景通过；异构成本为 confirmed known bug，轴荷另有 #537/#539 | 不直接上线，等待上游合并或固定 fork |
| CP-SAT | 成本主问题、exact-small | Apache-2.0，Python wheel | strengthened 7/7；`overflow_9` 为 2 箱且 bound=2 | **默认精确小规模/箱型分配** |
| SCIP | 开放 MIP/CIP 精确轨 | SCIP Apache-2.0，PySCIPOpt MIT | strengthened 7/7；reduced `overflow_9` 20 秒未证明 | **研究扩展与独立对照** |
| Gurobi/CPLEX | 商业 MIP 插件 | Python binding + native runtime/商业许可 | strengthened 各 7/7；CPLEX legacy 受 promotional license 规模限制 | 真实企业规模与许可收益成立时选装 |
| Skjolber Plain/LAFF | greedy/level packing；小规模 FastBruteForce | Apache-2.0，Java sidecar | THPACK9 44/44 均合法；Plain 均值 17.80 箱，LAFF 20.84 箱 | 有独特 obstacles/controls 需求再引入 |
| `py3dbp` | pivot greedy | MIT，原生 Python | THPACK9 44/44 合法；降序均值 18.43 箱，41/53 个可比实例受顺序影响 | baseline/候选生成 |
| Jerry | pivot + fix-point/支撑近似 | MIT，Python fork | 280 条语义可表达任务中 4 条重叠；`fix_point=False` 对照合法；`loadbear` 不是硬约束 | 不作业务真值 |
| Go `bp3d` | pivot greedy | MIT，Go | THPACK9 44/44 合法；禁旋和重量专项失败 | 不作核心，拒绝原因是约束语义而非语言 |
| Rust `u-nesting` | ExtremePoint、Layer、GA、BRKGA、SA | Rust；PyO3/C ABI 尚需自建 | ExtremePoint adapter THPACK9 44/44 合法；其余四类的 Layer decoder 产生越界证书 | 观察项；只保留 ExtremePoint 合法基线 |

## 前端/交互技术矩阵

前端矩阵的 ✅ 表示官方支持且工程路径明确，⚠️ 表示仍需本项目的 packaged/GPU PoC，❌ 表示当前路线不满足要求。它不沿用算法矩阵中“专项已通过”的定义。

| 方案 | Win/macOS/Linux | 直接管理 Python worker | 3D/拾取路线 | 大规模 instancing | 离线发布 | 安装体积/复杂度 | 许可证 | 适合本项目 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Tauri 2 + React/TypeScript + Three.js** | ✅ | ✅ 子进程/sidecar | ⚠️ Three.js 数据层 smoke 通过；实际 WebView/GPU 待三平台验证 | ⚠️ `InstancedMesh` 10k 数据层通过，FPS/显存待测 | ✅ | ⚠️ 不内置浏览器，成品包体待测 | MIT/Apache 生态 | **首选桌面壳，先过 GPU 决策门** |
| PySide6 + Qt Quick 3D/Qt 3D/PyVista/QWebEngine | ✅ | ✅ `QProcess` worker | ⚠️ 四条路线能力与许可不同，均未做本项目 PoC | ⚠️ Qt Quick 3D 有 instancing；其他路线需分别验证 | ✅ | ⚠️ Qt/VTK/plugin 裁剪后实测 | PySide6 LGPLv3/GPLv3/Commercial；Qt Quick 3D GPLv3/Commercial；Qt 3D LGPLv3/GPLv2/Commercial | Python/Qt 团队的条件备选 |
| Electron + React + Three.js | ✅ | ✅ sidecar | ⚠️ Three.js 路线明确，packaged Chromium/GPU 未做本项目 PoC | ⚠️ API 支持，FPS/显存待测 | ✅ | ❌ Chromium 体积和常驻内存高 | MIT | Tauri 在客户 WebView/GPU 矩阵失败时后备 |
| Flutter desktop + `flutter_3d_controller`/原生插件 | ✅ | ⚠️ 进程/插件桥 | ⚠️ 3D 生态不如 Three.js；该插件元数据列 Android/iOS/Web/macOS，不覆盖 Win/Linux | ⚠️ | ✅ | ⚠️ 插件与平台差异 | BSD/MIT | 不作为首版默认 |
| Flet | ✅ | ✅ Python | ❌ 不适合复杂 3D 拾取 | ❌ | ✅ | ⚠️ Flutter+Python 成品包体待测 | Apache-2.0 | 仅内部表单/原型 |

前端首选的交互信息架构：左侧实例/约束/求解器配置，中间可旋转、框选、剖切、爆炸视图的 3D 场景，右侧当前方案的箱数/成本/装载率/违规列表/证书状态；底部显示求解进度、time-to-first-feasible、bound 和 gap。所有物品、箱、姿态和违规都用稳定 ID，点击表格行与 3D 高亮双向联动。

## 建议的数据与可视化格式

| 数据 | 推荐格式 | 用途与注意点 |
|---|---|---|
| 规范输入/结果 | 版本化 canonical JSON（完整 ProblemSpec/Solution/ValidationReport） | 带 `schema_version`、单位和 hash；YAML/CSV/XLSX 只作导入，消除歧义并归一化为 canonical JSON 后再求 hash |
| Placement 明细/流 | CSV 或 JSONL | 每件 `item_instance_id`、`bin_instance_id`、`x/y/z`、尺寸、`pose_id`；必须由 manifest 绑定 problem/solution hash、schema、单位、预期件数和 validator/version。它是原始/派生明细，不单独构成有效证书 |
| 3D 场景 | glTF 2.0/GLB + `extras` 稳定 ID | Three.js 加载和离线缓存；网格仅表达形状，约束/指标仍在 JSON |
| 实验分析/归档 | Parquet + JSON manifest | Parquet 保存实例、seed、版本、资源、status、bound、gap、RSS；manifest 保存 provenance、hash 和分区信息；不替代 canonical JSON |
| 条件式分页传输 | Arrow IPC | 仅在 profiling 证明 JSON placement page 是瓶颈后进入协议 v2，不作为首版用户导出或权威结果 |
| 实时进度 | 版本化 JSON 事件（stdio/HTTP/WebSocket/Tauri Channel） | `started`、`incumbent`、`bound`、`warning`、`finished`；前端可恢复和取消 |

3D 展示必须可见地表达“不可行原因”：碰撞红色、越界橙色、姿态黄色、超重/承压紫红色，重心/轴荷用箭头和轴线，卸货站点用时间滑块。同一实例的多项违规用 issue badge 列表、叠加 outline/hatch 和 inspector 表达，不能用单一填充色覆盖；碰撞显示 pair 与穿透面，支撑/承压显示 footprint 与 load path，物品显示 top/front 面标记或局部轴。任意角对象用 OBB/SAT 校验后的姿态矩阵渲染，不能把 AABB 当作真实碰撞结果。
