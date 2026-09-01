# B05 官方生成器派生轨

## 来源结论

论文原始的 Martello--Pisinger--Vigo 三维实例 archive 仍没有找到同时满足“实例内容、格式说明、姿态语义、来源身份和可复现许可”的公开归档，因此正式 `B05` 继续保持 `SOURCE_INCOMPLETE`，不能用下面的派生数据改写成原始 MPV 数据。

DIKU 官方页面提供了配套的 `3dbpp.c` exact solver、`test3dbpp.c` generator 和 `readme.3dbpp`：

- <https://di.ku.dk/~pisinger/new3dbpp/3dbpp.c>
- <https://di.ku.dk/~pisinger/new3dbpp/test3dbpp.c>
- <https://di.ku.dk/~pisinger/new3dbpp/readme.3dbpp>

官方 readme 明确问题是“固定方向长方体、同型三维箱、全部装入、最少箱数”，并声明代码仅可免费用于 research/academic purposes。三个文件的 SHA-256 和生成器包装器都由 [`generate_mpv_official.py`](../benchmarks/comprehensive/generate_mpv_official.py) 固定，审计结果见 [`b05-official-generator-audit.json`](../results/comprehensive/b05-official-generator-audit.json)。

## 已冻结的派生 corpus

| 参数 | 值 |
|---|---|
| 生成器类型 | `1, 6, 7, 8, 9`；type 1 是 Martello/Vigo 混合分布，6/7/8 是 Berkey/Wang 尺寸档，9 是三段 guillotine 构造 |
| 件数 | `n=30, 60, 90` |
| 箱尺寸 | `100 x 100 x 100` |
| replicate | 每个 type/件数 10 个；共 `150` 个实例 |
| seed | `seed = n + replicate`，与官方主程序每次测试的 `srand(v+n)`（`v=1..10`）一致 |
| 姿态 | `FIXED_XYZ`；生成器和官方 solver 不允许旋转 |
| canonical 文件 | [`benchmarks/data/public/mpv_official_generator_derived/`](../benchmarks/data/public/mpv_official_generator_derived/) |
| corpus SHA-256 | `2deb28215b99a3412f0b065e8d5888e21de604a57129ba53230a1883f4f08411` |

type 9 的每个实例物品总体积恰好是三个箱体积，因此它可用于检查“guillotine 结构的 3 箱真值/下界”；type 6--8 分别覆盖小尺寸、较宽尺寸和接近箱尺寸的困难组合。它们是论文生成器派生的可复现压力集，不是论文表格中某一批原始实例。

## 适用库和结果解释

| 实现轨道 | 适用方式 | 结果能说明什么 | 不能说明什么 |
|---|---|---|---|
| PackingSolver `box` fork/upstream | `NATIVE`，固定 XYZ，完整装载 | 同型多箱 fixed-pose 的箱数、完整率和预算响应 | fork 不是官方 release；solver 自报 bound 不自动是独立最优证明 |
| `boxstacks` | 仅在输入满足 stack master 语义时 `NATIVE` | 堆栈模型接口是否可运行 | 普通 MPV fixed-pose 输入不能强行解释为 stack 问题 |
| Skjolber Plain/LAFF/FastBruteForce | 需要 fixed-orientation/full adapter | 完整装载质量和超时/失败边界 | 默认 API 的全旋转或空结果不能当作 MPV 结论 |
| py3dbp、Jerry、Go bp3d、u-nesting | fixed-orientation adapter 通过独立 validator 后可比较；若放宽旋转必须单列 `PROJECTION_ONLY` | 几何启发式在该生成分布的箱数/可行率和规模响应 | all-rotation 投影不能升级为 MPV 原题能力；随机 decoder 的非法 certificate 必须排除 |
| CP-SAT/SCIP/Gurobi/CPLEX | 小规模 `EXACT_MODEL`；大规模只作 incumbent/bound | objective gap、下界、证明率和模型校准 | 受时间/许可证限制的 status-only 不是最优性证明 |
| 官方 `3dbpp.c` | 独立 C baseline；固定方向 | 论文算法在同一生成规则下的 lower/upper bound、求解时间 | 生成器输出没有官方 published optimum；超时结果只能叫 incumbent with bound |

派生轨道应在协议 v4 中单独命名，例如 `B05-MPV-OFFICIAL-GEN`，并为每个库保存输入 hash、姿态语义、时间预算、证书和 validator。它可以补足 B05 的可复现实验缺口，但不能提高当前 `B01--B32` 的完成率，也不能替代真正的 MPV archive。

## 全库派生轨执行结果

本轮共归档 4,050 条记录：官方 C 参考 150 条、PackingSolver fork/upstream `box` 600 条、u-nesting 五策略 1,500 条、Skjolber Plain/LAFF/FastBruteForce 900 条，以及 py3dbp/Jerry/Go 的 all-rotation projection 900 条。固定姿态轨只把通过独立 validator 且装完全部需求的 `VALID_COMPLETE` 记录纳入箱数统计；projection 轨单独标为 `GEOMETRY_PROJECTION`。

| 实现 | 轨道 | 1 s 合法完整 | 10 s 合法完整 | mean bins（合法完整） |
|---|---|---:|---:|---:|
| PackingSolver fork `box` | fixed native | 90/150 | 150/150 | 10.188889 -> 6.460000 |
| PackingSolver upstream `box` | fixed native | 89/150 | 150/150 | 10.202247 -> 6.460000 |
| Rust ExtremePoint / GA / BRKGA / SA / Layer | fixed composed | 各 150/150 | 各 150/150 | 7.013333 / 8.073333 / 8.326667 / 7.986667 / 8.786667 |
| Skjolber Plain / LAFF | fixed Java sidecar | 各 150/150 | 各 150/150 | 6.953333 / 8.320000 |
| Skjolber FastBruteForce | fixed Java sidecar | 60/150 | 60/150 | 1.000000（仅 type 6/7） |
| py3dbp / Jerry | all-rotation projection | 各 150/150 | 各 150/150 | 6.360000 |
| Go `bp3d` | all-rotation projection | 150/150 | 150/150 | 6.806667 |

逐实例记录、状态和分层统计见 [`B05-MPV-OFFICIAL-GEN-rankings.csv`](../results/comprehensive/rankings/B05-MPV-OFFICIAL-GEN-rankings.csv) 与 [`B05-MPV-OFFICIAL-GEN-rankings-by-type.csv`](../results/comprehensive/rankings/B05-MPV-OFFICIAL-GEN-rankings-by-type.csv)。这些结果不能与 B04/THPACK9 混合，也不能从 all-rotation projection 推断 fixed-pose 能力；FastBruteForce 的空证书是可行率/时间边界证据，不是几何 validator 失败被隐藏后的质量数字。
