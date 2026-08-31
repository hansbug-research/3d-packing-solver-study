# 算法与前端决策矩阵

符号：✅ 原生或已实测支持；❌ 没有该能力；⚠️ 只能通过自建模型/扩展点实现，或本次发现已知限制。矩阵按“问题特性”写，不把某个样例偶然装成功当作能力证明。

## 算法/库矩阵

| 库/算法 | 6 轴向旋转 | 24 面语义姿态 | 直立/姿态子集 | 连续任意角 | 多箱装完 | 异构箱成本 | 有限 copies | 箱总重量 | 叠层/层高 | 最大堆叠数 | 最大上方重量 | 部分支撑/稳定 | 重心/轴荷 | 多站卸货 | 障碍物 | 最优性界 | Python 接入 | C/C++ 原生 | 结果证书 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PackingSolver `box` | ✅ | ❌ | ⚠️ 6 排列，不保留面语义 | ❌ | ✅ | ⚠️ 当前 master `operator<` 崩溃，修复后可用 | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ primal/dual，但常为 anytime | ⚠️ CLI/子进程 | ✅ C++ | ✅ CSV/JSON |
| PackingSolver `boxstacks` | ✅ | ❌ | ⚠️ | ❌ | ✅ | ⚠️ 同一已复现缺陷 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ stack 几何，不是一般接触面载荷流 | ✅ 半挂中/后轴 | ✅ increasing X/Y | ❌ | ✅ 有 bound/gap | ⚠️ CLI/子进程 | ✅ C++ | ✅ CSV/JSON |
| OR-Tools CP-SAT | ⚠️ 需自建姿态变量 | ⚠️ 需自建 face ID | ✅ 可精确列举 | ❌ | ✅ 自建模型 | ✅ 自建主问题 | ✅ | ✅ | ⚠️ 自建支撑/层约束 | ⚠️ | ⚠️ | ⚠️ 自建线性化 | ⚠️ 自建 | ⚠️ 自建 | ⚠️ `NoOverlap2D` 不能直接替代 3D | ✅ 小规模可证明 | ✅ wheel | ✅ native 核心 | ❌ 需自行导出 |
| SCIP + PySCIPOpt | ⚠️ 需自建 | ⚠️ 需自建 | ✅ | ❌ | ✅ 自建 | ✅ | ✅ | ✅ | ⚠️ 自建 | ⚠️ | ⚠️ | ⚠️ 可做 MIP/CIP/载荷流 | ⚠️ | ⚠️ | ⚠️ 自建碰撞 | ✅ branch-and-bound | ✅ wheel | ✅ C++ | ❌ 需自行导出 |
| Gurobi / `gurobipy` | ⚠️ 需自建 | ⚠️ 需自建 | ✅ | ⚠️ 非凸连续模型代价高 | ✅ | ✅ | ✅ | ✅ | ⚠️ 自建 | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ 完成搜索可证明 | ✅ wheel/商业许可 | ✅ C++ | ❌ 需自行导出 |
| IBM CPLEX / CP Optimizer | ⚠️ 需自建 | ⚠️ 需自建 | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ⚠️ 自建 | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ 完成搜索可证明 | ✅ wheel/商业许可 | ✅ C++ | ❌ 需自行导出 |
| `py3dbp` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ 无 bound | ✅ 原生 Python | ❌ | ❌ |
| Jerry `3D-bin-packing` | ✅ | ❌ | ✅ `updown` 布尔 | ❌ | ✅ | ❌ | ✅ | ✅ | ⚠️ 支撑面积启发式 | ❌ | ⚠️ `loadbear` 只是排序，见 warning | ⚠️ 四角/面积近似 | ❌ | ❌ | ❌ | ❌ | ✅ Python fork | ❌ | ❌ 绘图/坐标可导出 |
| Skjolber LAFF (Java) | ✅ | ❌ | ⚠️ 3D/2D rotate | ❌ | ✅ | ❌ | ✅ | ✅ | ⚠️ controls 扩展点 | ⚠️ | ❌ | ⚠️ 自定义 controls | ❌ | ❌ | ✅ obstacles | ⚠️ brute force 仅小规模 | ⚠️ JVM sidecar | ✅ Java | ❌ |
| Go `bp3d` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ⚠️ `MaxWeight` 未进入 `PutItem` 检查 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ Go sidecar | ✅ Go | ❌ |

关键 warning：

- ⚠️ PackingSolver 异构成本不是“不会优化”，而是当前 `box::Solution::operator<` 与 `boxstacks::Solution::operator<` 漏分支；最小 patch 和复现见 [packingsolver-upstream.md](packingsolver-upstream.md)。
- ⚠️ Jerry 的 `loadbear` 本地反例允许脆弱件上方实际重量 20；它改变排序优先级，不是硬承压约束。
- ⚠️ Go `bp3d` 的 `MaxWeight` 字段存在，但放置函数没有用它拒绝超重方案。
- ⚠️ OR-Tools/SCIP/Gurobi/CPLEX 是建模引擎，不是现成 3D packer；矩阵中的 ✅ 指“可以可靠承载自建模型”，不表示官方提供 3D global constraint。

## 工程定位矩阵

| 组件 | 算法角色 | 许可证/集成 | 本地证据 | 采用结论 |
|---|---|---|---|---|
| PackingSolver | 正交单箱启发式、tree/maximal spaces、SVC/列生成 | MIT，C++ CLI；固定 SHA + 子进程 | 基础/重量/叠层通过；公开 THPACK9-1 为 25 箱；成本路径原版失败、patch 版通过 | **主启发式候选，但必须回归门禁** |
| CP-SAT | 成本主问题、exact-small | Apache-2.0，Python wheel | 9 立方体 2 箱，`OPTIMAL` 且 bound=2 | **默认精确小规模/箱型分配** |
| SCIP | 开放 MIP/CIP 精确轨 | SCIP Apache-2.0，PySCIPOpt MIT | 同例 `optimal`、dual=2、gap=0 | **研究扩展与独立对照** |
| Skjolber | LAFF 几何强启发式 | Apache-2.0，Java sidecar | 基准 70 件 28 箱，几何通过；库内约 5 ms | 有独特障碍/controls 需求再引入 |
| `py3dbp` | pivot greedy 基线 | MIT，原生 Python | THPACK9-1 70 件 50 箱，几何通过 | 只作 baseline |
| Jerry | 支撑/绘图参考实现 | MIT，Python fork | THPACK9-1 70 件 50 箱；承压反例失败 | 不作真值 |
| Go `bp3d` | 老 pivot greedy | MIT，Go | 代码审计发现重量字段不生效 | 拒绝作为核心 |

## 前端/交互技术矩阵

| 方案 | Win/macOS/Linux | 直接管理 Python worker | 原生 3D/拾取 | 大规模 instancing | 离线发布 | 安装体积/复杂度 | 许可证 | 适合本项目 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Tauri 2 + React/TypeScript + Three.js** | ✅ | ✅ 子进程/sidecar | ✅ WebGL/WebGPU、raycast | ✅ `InstancedMesh` | ✅ | ✅ 小于 Electron，需签名/sidecar | MIT/Apache 生态 | **首选桌面壳** |
| PySide6 + Qt Quick 3D | ✅ | ✅ 同进程/worker | ✅ Qt scene graph | ⚠️ 需自建批量策略 | ✅ | ⚠️ Qt 部署较重 | LGPL/商业双许可 | Python-only 团队、原生控件优先 |
| Electron + React + Three.js | ✅ | ✅ sidecar | ✅ | ✅ | ✅ | ❌ Chromium 体积大、内存高 | MIT | 需要成熟 Web 调试生态时选 |
| Flutter desktop + `flutter_3d_controller`/原生插件 | ✅ | ⚠️ 进程/插件桥 | ⚠️ 3D 生态不如 Three.js | ⚠️ | ✅ | ⚠️ 插件与平台差异 | BSD/MIT | 不作为首版默认 |
| Flet | ✅ | ✅ Python | ❌ 不适合复杂 3D 拾取 | ❌ | ✅ | ✅ | MIT | 仅内部表单/原型 |

前端首选的交互信息架构：左侧实例/约束/求解器配置，中间可旋转、框选、剖切、爆炸视图的 3D 场景，右侧当前方案的箱数/成本/装载率/违规列表/证书状态；底部显示求解进度、time-to-first-feasible、bound 和 gap。所有物品、箱、姿态和违规都用稳定 ID，点击表格行与 3D 高亮双向联动。

## 建议的数据与可视化格式

| 数据 | 推荐格式 | 用途与注意点 |
|---|---|---|
| 规范输入/结果 | 版本化 JSON（`schema_version`、`problem_kind`、`items`、`bins`、`poses`、`constraints`） | 保留 24 姿态面语义、重量、承压、站点；不能只传旋转后 AABB |
| 求解证书 | CSV 或 JSONL placement certificate | 每件 `item_instance_id`、`bin_instance_id`、`x/y/z`、尺寸、`pose_id`、solver SHA；独立 validator 逐行复算 |
| 3D 场景 | glTF 2.0/GLB + `extras` 稳定 ID | Three.js 加载和离线缓存；网格仅表达形状，约束/指标仍在 JSON |
| 实验结果 | Parquet/Arrow + JSON manifest | 记录实例、seed、版本、资源、status、bound、gap、RSS；便于 pandas/前端筛选 |
| 实时进度 | 版本化 JSON 事件（stdio/HTTP/WebSocket/Tauri Channel） | `started`、`incumbent`、`bound`、`warning`、`finished`；前端可恢复和取消 |

3D 展示必须可见地表达“不可行原因”：碰撞红色、越界橙色、超重/承压紫红色、重心/轴荷用箭头和轴线，卸货站点用时间滑块；不要只给一个体积利用率百分比。任意角对象用 OBB/SAT 校验后的姿态矩阵渲染，不能把 AABB 当作真实碰撞结果。
