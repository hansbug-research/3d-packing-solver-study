# Campaign 结果说明

本目录保存 2026-08-31 全量、跨语言和专项实验的机器结果。汇总入口是 [`aggregate.json`](aggregate.json)，生成脚本是 [`../../benchmarks/campaign/analyze_campaign.py`](../../benchmarks/campaign/analyze_campaign.py)。聚合文件中的 `source_sha256` 绑定所有被消费的 JSON/JSONL，正文数字由 `scripts/verify.py` 再做断言。

符号：✅ 已运行，适用记录全部通过独立校验；⚠️ 已运行但只覆盖部分实例、依赖 adapter，或发现非法证书/known bug；❌ 该问题语义不受支持，因此没有运行完整 benchmark。`❌` 不等于算法速度慢，也不等于安装失败。

## 每类 benchmark 测什么

| Benchmark | 输入与规模 | 主目标/指标 | 能测试 | 不能测试 | 结果入口 |
|---|---|---|---|---|---|
| THPACK1-7 / BR 全集 | 700 个单容器实例 | 最大 packed volume、容器利用率、solver-reported bound gap | 单箱 3D knapsack、允许竖直方向、anytime 质量、1 s/10 s 预算响应 | 最少箱数、箱价、承压、轴荷、卸货 | `packingsolver-thpack*.jsonl` |
| THPACK8 / LN 全集 | 15 个单容器实例 | 最大 packed volume、容器利用率 | 另一分布的单箱 knapsack、预算响应 | 同上 | `packingsolver-thpack*.jsonl` |
| THPACK9 / IMM 全集 | 47 条源记录，其中 44 条合法 | 装完全部物品后最少箱数；合法率；相对体积下界差距 | 多箱完整性、正交几何、跨实现 solution quality | published optimum、异构成本、业务力学 | `packingsolver-thpack*.jsonl`、`skjolber-thpack9.json`、`crosslang_*_thpack9/results.json` |
| Python THPACK campaign | 762 个源实例 × 2 库 × 2 种排序，共 3,048 条计划状态；实际执行 280 条 | 合法率、完整率、箱数/利用率、排序敏感性 | `py3dbp`/Jerry 在可表达方向语义上的行为、输入顺序影响、certificate 重叠 | 两库不能表达的逐件姿态语义；成本/轴荷等业务约束 | `python_thpack/summary.json` |
| 跨语言 7 场景 | 网格、需旋转、禁旋、重量、两种异构箱行序、THPACK9-1 | 预期行为是否满足，certificate 是否合法 | 官方/fork bug 区分、姿态白名单、重量、成本方向、adapter 边界 | 大规模性能与统计稳定性 | `crosslang_*/results.json` |
| Exact-small canonical | 7 个手工真值场景 | `OPTIMAL/INFEASIBLE`、objective、bound、gap、certificate | 网格、溢出拆箱、需旋转、禁旋、重量拆箱、两种异构成本方向 | 大规模 3D 性能；求解器没有提供现成 3D 模型 | `exact-{backend}.json`，固定为 strengthened formulation |
| Exact formulation sensitivity | 3 种 formulation × 4 个 backend × 7 场景 | 状态、时间、错误和证书 | 模型加强对证明速度、许可证约束数的影响 | 通用 solver 性能排名；三种 formulation 不是完全单因素实验 | `exact-{legacy,reduced,strengthened}-{backend}.json` |
| PackingSolver `boxstacks` 专项 | 9 个构造场景 | 每条预期行为和独立重算 | 异构成本、最大上方重量、最大堆数、nesting、正常/边界/不可行轴荷、无卸货约束、IncreasingX | 一般部分支撑、动态稳定、完整装入路径 | `packingsolver-boxstacks.json` |
| PackingSolver 策略专项 | BR/LN/IMM 代表实例，6 种策略 | certificate 合法性和策略行为 | auto、tree search、maximal spaces、sequential single knapsack、value correction、column generation | 全实例策略质量排名 | `packingsolver-strategies.json` |
| Rust 五策略与重复 | 5 个统一场景；THPACK9-1 每策略重复 5 次 | certificate 合法性、重复稳定性、参数是否生效 | ExtremePoint、Layer、GA、BRKGA、SA 的 decoder 行为；seed/time limit 接线 | 不能把无效布局报告的 15-16 箱计入质量 | `crosslang_rust_unesting_strategies/results.json`、`crosslang_rust_unesting_strategy_repeats/results.json` |
| 工业数据集审计 | Alonso 2019 的 111 个实例、Alonso 2020 的 107 个实例、BAYTP 文件集 | 字段/行数/需求恒等式/快照完整性 | 数据是否自包含、现有 adapter 是否能保真表达 | 没有求解完整 Alonso/BAYTP；不产生算法得分 | `industrial-dataset-audit.json` |

BR/LN 与 IMM 的目标不同，不能把它们混成一列“平均箱数”。THPACK 的经典几何数据也没有价格、最大上压、重心/轴荷或多站卸货字段，因此需要构造专项补齐；构造专项又不能代替 759 个公开实例的分布质量测试。

## 库与 benchmark 的实际运行范围

| 库/算法 | BR/LN 全集 | THPACK9 44 例 | 7 个跨语言场景 | Exact-small 7 例 | `boxstacks` 9 例 | 策略/重复实验 | 工业完整问题 |
|---|---:|---:|---:|---:|---:|---:|---:|
| PackingSolver fork `d953148b` | ✅ 715/715，1 s 与 10 s | ✅ 44/44 | ✅ 7/7 | ❌ 不是该模型后端 | ✅ 9/9 | ⚠️ column generation 在 THPACK9-47 给出 0/99 件 | ❌ Alonso/BAYTP adapter 未实现 |
| PackingSolver 官方 rolling | ⚠️ 未跑全量，只作固定反例 | ⚠️ THPACK9-1 有效 | ⚠️ 6/7；小箱行先触发 #536 | ❌ | ❌ | ❌ | ❌ |
| `py3dbp` 1.1.2 | ⚠️ 53 个语义可表达实例 × 2 排序，106/106 有效 | ✅ 44/44（降序） | ⚠️ 旧受控专项已跑；无成本/姿态子集 | ❌ | ❌ | ⚠️ 41/53 个实例随顺序改变质量 | ❌ |
| Jerry `75764a` | ⚠️ 87 个语义可表达实例 × 2 排序，170/174 有效 | ⚠️ 降序 43/44，1 条重叠 | ⚠️ `loadbear` 反例失败 | ❌ | ❌ | ⚠️ 66/87 质量变化，4/87 有效性变化 | ❌ |
| Skjolber Plain/LAFF | ❌ 未实现 BR/LN adapter | ✅ 两算法各 44/44 | ⚠️ 小型 3 算法与既有约束 smoke 已跑 | ❌ | ❌ | ✅ Plain 在 27 例优于 LAFF，17 例相同 | ❌ |
| Go `bp3d@0ba3dcd` | ❌ 方向语义不支持 | ✅ 44/44 | ⚠️ 5/7 certificate 合法；禁旋和重量失败 | ❌ | ❌ | ❌ | ❌ |
| Rust ExtremePoint `8cde85b` | ❌ 未实现 BR/LN adapter | ⚠️ 44/44 有效，但多箱来自重复单 boundary adapter | ✅ 7/7 行为符合能力声明 | ❌ | ❌ | ✅ THPACK9-1 重复 5/5 有效 | ❌ |
| Rust Layer/GA/BRKGA/SA | ❌ | ❌ THPACK9-1 certificate 越界 | ⚠️ 14/20 场景有效；Layer 3/5、GA 3/5、BRKGA 4/5、SA 4/5 | ❌ | ❌ | ❌ 每种策略 THPACK9-1 重复 5/5 非法 | ❌ |
| OR-Tools CP-SAT 9.15 | ❌ 非现成 3D 库 | ❌ 未解 44 例 | ❌ | ✅ strengthened 7/7 | ❌ | ⚠️ legacy/reduced/strengthened 均跑 | ❌ |
| SCIP/PySCIPOpt 6.2.1 | ❌ | ❌ | ❌ | ✅ strengthened 7/7 | ❌ | ⚠️ reduced `overflow_9` 20 s 未证明 | ❌ |
| Gurobi 13.0.3 | ❌ | ❌ | ❌ | ✅ strengthened 7/7 | ❌ | ✅ 三种 formulation 均跑 | ❌ |
| CPLEX 22.1.2.0 | ❌ | ❌ | ❌ | ✅ strengthened 7/7 | ❌ | ⚠️ legacy 受 promotional license 1,000 约束上限阻断；reduced 20 s 未证明 | ❌ |

## 主要结果和算法行为

- PackingSolver 1 s 到 10 s：BR 的平均利用率从 `0.7216` 升到 `0.9624`，700 对中 673 对改善；LN 从 `0.5072` 升到 `0.7115`，15 对中 7 对改善。BR/LN 的 1 s 空解分别为 166/5 个，10 s 均为 0。IMM 的 44 对箱数全部相同，但 solver-reported bound 闭合从 23 增到 25。说明额外预算主要改善 knapsack incumbent，不保证每个问题族都少用箱。
- THPACK9 44 例按有效 certificate 的平均箱数：PackingSolver 1 s/10 s `15.48`，Skjolber Plain `17.80`，Rust ExtremePoint adapter `18.41`，`py3dbp` 降序 `18.43`，Go `bp3d` `19.93`，Skjolber LAFF `20.84`。Jerry 降序均值 `18.72`，但有 1 条重叠，只能作为带 warning 的结果。
- `py3dbp` 的 53 对可比实例中 41 对受排序影响；Jerry 的 87 对中 66 对质量改变、4 对连 certificate 有效性也改变。对这类 pivot greedy，物品排序是算法参数，不是无关的输入细节。
- Skjolber Plain 在 27/44 例比 LAFF 少用箱，17 例相同，LAFF 没有赢。本组数据不支持“层算法一定更好”；LAFF 更快或更适合规则层状货物的假设仍需同进程、同预算 benchmark 验证。
- Rust Layer、GA、BRKGA、SA 共用 `layer_place_items` decoder。换层后只检查 Z，没有重新检查新姿态的 X/Y 边界；低箱数输出全部无效。GA/BRKGA/SA 的 `seed` 未接入实际随机源，多数策略也未读取 `time_limit_ms`。
- Exact-small 的 strengthened formulation 在四个 backend 上都通过 7 个场景。legacy CPLEX 因 1,489 条约束超过 promotional license，SCIP/CPLEX reduced 在 `overflow_9` 上 20 s 未证明，而 strengthened 版本很快闭合。这首先是 formulation 效应，不是通用的求解器速度排名。

## 状态词

`VALID`/`FEASIBLE` 表示 certificate 已通过本轮独立检查，不表示全局最优。PackingSolver 的 `SOLVER_REPORTED_BOUND_CLOSED` 只记录求解器报告的 primal/bound 闭合；本仓库没有独立证明该 bound，因此不升级成无条件 `PROVEN_OPTIMAL`。`INVALID` 表示进程可能正常退出，但坐标、姿态、件数、重量或目标复算失败。`NOT_SUPPORTED` 表示数据语义不能保真映射，不能删除字段后冒充完整 benchmark。

微秒/毫秒计时来自不同语言、JVM/进程启动方式和停止粒度，不能作跨语言性能排名。可比较的质量数字必须先满足同一输入语义、完整装载和独立 certificate 校验。
