# Go / Rust / C++ 3D packing 实测审计

核查日期：2026-08-31。本文只报告跨语言候选 campaign；所有结论均区分原生能力、adapter 能力和未支持能力。符号含义：✅ 原生支持且本轮通过；❌ 原生不支持或实测违反约束；⚠️ 有接口但有限制、仅 adapter 支持、存在 known bug，或本轮未覆盖到足以写成无条件支持。

## 结论先行

1. **当前综合能力最强的仍是 PackingSolver，但只能 pin 修复 fork，不能把官方 rolling binary 当成可直接上线版本。** 固定 fork `d953148b...` 的 7 个场景均通过独立 validator；官方 binary 在同一异构实例上仅因 bin CSV 行顺序不同，一次成功、一次在 `Solution::operator<` 退出。这与官方 issue #536 / PR #540 完全一致，证明调用方法没有错。
2. **`gedex/bp3d` 不可作为带业务约束的后端内核。** 它的几何基本场景能跑，THPACK9-1 也能装完，但没有姿态白名单，且 `MaxWeight` 字段完全未执行：禁旋物品被旋转装入，重量 18 被装进上限 10 的箱。相关重量 issue #1 从 2016 年保持 open，PR #4 从 2018 年保持 open。
3. **`iyulab/u-nesting` 只能把 ExtremePoint 暂列为有效单箱排布内核。** ExtremePoint 的几何、姿态和重量证书有效；Layer 存在换层后漏检宽/深边界的上游 bug，GA/BRKGA/SA 共用该 layer decoder，因而本轮 15/16 箱的 THPACK9-1 输出全部越界。它仍是单 `Boundary3D` 求解器，campaign 的多箱结果来自外层重复调用，不能冒充原生多箱算法。
4. **THPACK9-1 上，PackingSolver fixed 为 25 箱，Go 和 Rust ExtremePoint adapter 均为 50 箱。** 实例总物品体积为 17,920，单箱体积 960，纯体积下界为 19 箱；对应总体积利用率分别为 74.67% 和 37.33%。Layer/GA/BRKGA/SA 表面上的 15/16 箱都因越界而作废。该实例没有可据此声称的 published optimum，因此这里只写 feasible incumbent，不写最优。
5. **THPACK9 全部 44 个可解析实例上，Go 与 Rust ExtremePoint adapter 都得到 44/44 完整有效证书、invalid rate 0%。** Go 箱数 mean/median/p95 为 `19.93/16/55`，Rust 为 `18.41/14/52`；Rust 在 16 个实例少用箱、26 个相同、2 个多用箱。但这只比较两个具体贪心控制流，不把 Rust adapter 写成上游原生多箱支持。

## 技术栈与可复现性

| 候选 | 固定版本 | 技术栈 / Python 融入方式 | 构建与上游测试 | 可复现性结论 |
|---|---|---|---|---|
| PackingSolver official | rolling Linux x64 binary，SHA-256 `98925f...f166`；附近官方源码为 `367ebf...`，**不能断言二进制正由该 SHA 构建** | C++14 CLI/C++ library；无现成官方 Python binding，可用 subprocess、C API/pybind11 自行封装 | ⚠️ 预编译物，campaign 无法把 CTest 与二进制源码一一绑定 | ⚠️ 只适合作为官方行为对照，不满足严格源码可追溯上线要求 |
| PackingSolver fixed | HansBug fork `d953148b8f710c06fa6c410949b7272f9e36327b`；binary SHA-256 `1a1a...6285` | C++14，GCC 13.3.0，CMake 4.4.3；Python 接入同上 | ✅ 重新执行 build target；CTest 603 passed，1 disabled，0 failed，172.11 s，峰值 230,176 KiB | ✅ 源码/二进制对应；⚠️ fork patch 尚未被官方合并 |
| `gedex/bp3d` | `0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7`（2017-02-08） | 原生 Go；Python 后端需自建 c-shared、RPC 或 sidecar，无官方 Python 包 | ⚠️ Go 1.27.0 build 通过；上游 `go test` 失败，原因是等体积物品排序后的具体合法布局与写死快照不同 | ✅ 源码固定；⚠️ 项目陈旧、测试对现代 Go 排序行为脆弱 |
| `iyulab/u-nesting` | 主库 `8cde85b...170d`；另固定 `u-geometry e8d23e...`、`u-metaheur 717192...`、`u-numflow 652d40...` | Rust 1.98.0；官方仓库含 PyO3 `cdylib`、C FFI、WASM | ✅ `u-nesting-d3 --all-features`：103 unit passed；3 doc passed、2 ignored；adapter release build 通过 | ⚠️ 单仓 checkout 不能构建当前源码；三个仓库外 path dependency 必须按特定目录补齐，上游 CI clone 的是未固定 main |

工具链 bootstrap 下载校验：Go archive SHA-256 `675c26...0685`；`rustup-init` SHA-256 `4acc9a...6a10`。Rust adapter 提交了 `Cargo.lock`，并在临时四仓目录中使用 `--locked` 构建。

## 问题维度能力矩阵

| 算法 / 库 | 3D AABB | 6 轴向旋转 | 每件禁旋 / Upright | 箱总重量 | 同规格多箱 | 异构箱尺寸 | 箱成本目标 | 叠层 / 上压 / 稳定性 | 逐件坐标输出 | Python 后端集成 |
|---|---|---|---|---|---|---|---|---|---|---|
| PackingSolver official `box` | ✅ | ✅ 六姿态可逐项选择 | ✅ CSV 姿态列 | ✅ | ✅ 原生 | ⚠️ API/文档声称支持，但特定行序触发 #536 | ⚠️ `variable-sized-bin-packing` known bug | ⚠️ 需切换 `boxstacks`；该能力不属于本轮 `box` campaign | ✅ CSV certificate | ⚠️ C++/CLI，需自建 binding 或进程封装 |
| PackingSolver fixed `box` | ✅ | ✅ | ✅ | ✅ | ✅ 原生 | ✅ 两种行序均通过 | ✅ 两种行序均选成本 10 | ⚠️ `boxstacks` 是另一个模型，本表结果未冒充已验证 | ✅ CSV certificate | ⚠️ 同上，且当前是未合并 fork |
| `gedex/bp3d` pivot greedy | ✅ 基础例通过 | ✅ 总是遍历旋转 | ❌ 无姿态白名单 | ❌ `MaxWeight` 未参与 `PutItem` | ✅ 贪心逐箱 | ⚠️ 能接收不同箱，但按体积排序并贪心提交 | ❌ 无成本字段/目标 | ❌ | ✅ Go struct；需自行序列化 | ⚠️ 无 Python binding，封装工作小但业务风险高 |
| `u-nesting-d3` Layer | ❌ 必须旋转最小例与 THPACK9-1 出界 | ⚠️ 会枚举姿态，但换层后漏检 X/Y | ✅ `Any/Upright/Fixed`；禁旋拒装通过 | ✅ `max_mass` | ⚠️ 仅外层重复单 `Boundary3D` | ❌ | ❌ | ⚠️ 有 API，本轮未验证业务稳定性 | ⚠️ 有坐标，但实测可能非法 | ⚠️ PyO3 已存在；源码构建需四仓布局 |
| `u-nesting-d3` GA | ❌ THPACK9-1 证书出界 | ⚠️ permutation + orientation chromosome，共用非法 layer decoder | ✅ 禁旋拒装通过 | ✅ | ⚠️ 仅 adapter 多箱 | ❌ | ❌ | ⚠️ 同上 | ⚠️ 有坐标，但必须外部复验 | ⚠️ 同上 |
| `u-nesting-d3` BRKGA | ❌ THPACK9-1 证书出界 | ⚠️ random key + orientation，共用非法 layer decoder | ✅ 禁旋拒装通过 | ✅ | ⚠️ 仅 adapter 多箱 | ❌ | ❌ | ⚠️ 同上 | ⚠️ 有坐标，但必须外部复验 | ⚠️ 同上 |
| `u-nesting-d3` SA | ❌ THPACK9-1 证书出界 | ⚠️ 顺序/姿态邻域，共用非法 layer decoder | ✅ 禁旋拒装通过 | ✅ | ⚠️ 仅 adapter 多箱 | ❌ | ❌ | ⚠️ 同上 | ⚠️ 有坐标，但必须外部复验 | ⚠️ 同上 |
| `u-nesting-d3` ExtremePoint | ✅ 44/44 THPACK9 证书通过 | ✅ `Any`；按顺序取首个可行姿态 | ✅ `Any/Upright/Fixed` | ✅ `max_mass` | ⚠️ 原生只解一个 `Boundary3D`；campaign 重复调用 | ❌ 单次 API 只有一个 boundary | ❌ 无异构选箱成本目标 | ⚠️ 有 gravity/stability/stacking API 与测试，但本轮只验证总重量 | ✅ serde / FFI response；本轮输出规范 JSON | ⚠️ PyO3 binding 已存在；无 sdist，源码构建需四仓布局 |

补充限制：PackingSolver 的 `boxstacks` 文档列出最大上压、堆叠数量、密度、轴荷和卸货顺序；这些是另一个求解模型，不能从本轮 `box` 结果推导为已验证。`u-nesting` 文档也列出 mass/stacking/gravity/stability，但本轮没有用业务级稳定性 benchmark 验证，因此保持 ⚠️。

## 统一场景结果矩阵

每个成功输出都由 `crosslang_validate.py` 再验 item identity、重复 ID、姿态尺寸、固定姿态、边界、同箱重叠、完整性和箱总重量。异构场景还要求 1 个大箱、总成本 10。

| 库 / 版本 | 规则网格 8 件 | 必须旋转 | 禁旋 | 重量上限 | 异构：小箱行先 | 异构：大箱行先 | THPACK9-1 | 独立校验摘要 |
|---|---|---|---|---|---|---|---|---|
| PackingSolver official | ✅ 8/8，1 箱 | ✅ `ZXY` | ✅ 0/1，正确拒装 | ✅ 3/3，3 箱 | ⚠️ exit 1，`Solution::operator<` known bug | ✅ 2/2，1 大箱，成本 10 | ✅ 70/70，25 箱 | ⚠️ 6 个成功 certificate 均有效；另 1 个进程错误 |
| PackingSolver fixed | ✅ 8/8，1 箱 | ✅ `ZXY` | ✅ 0/1，正确拒装 | ✅ 3/3，3 箱 | ✅ 2/2，1 大箱，成本 10 | ✅ 2/2，1 大箱，成本 10 | ✅ 70/70，25 箱 | ✅ 7/7 场景符合预期 |
| `gedex/bp3d` | ✅ 8/8，1 箱 | ✅ 非 identity | ❌ 把 fixed 物品旋转后装入 | ❌ 18 重量进入上限 10 的同一箱 | ⚠️ 2/2，但小箱+大箱，成本 17 | ⚠️ 同样成本 17；输入顺序被体积排序抹平 | ⚠️ 70/70，50 箱 | ❌ validator 抓到姿态和重量违反；异构目标也未达到 |
| `u-nesting-d3` ExtremePoint | ✅ 8/8，1 boundary | ✅ `zxy` | ✅ 0/1，正确拒装 | ⚠️ 3/3、3 箱有效，但多箱来自 adapter | ❌ `NOT_SUPPORTED` | ❌ `NOT_SUPPORTED` | ⚠️ 70/70，50 箱；重复单箱 adapter | ✅ 所有已声明原生/adapter 行为与 certificate 一致；异构能力仍是 ❌ |

`expected_behavior_pass` 只表示结果与声明一致。例如 Rust 异构行以 `NOT_SUPPORTED`、零 placement 返回，因此 validator 不报伪 certificate；它不意味着 Rust 已支持异构成本优化。

## THPACK9-1 质量与资源

| 库 | 装入 | 箱数 | 相对体积下界 19 | 总体积利用率 | 求解/adapter 记录 | 进程峰值 RSS |
|---|---:|---:|---:|---:|---:|---:|
| PackingSolver official | 70/70 | 25 | +6 / +31.6% | 74.67% | 约 1.005 s | 15,348 KiB |
| PackingSolver fixed | 70/70 | 25 | +6 / +31.6% | 74.67% | 约 1.005 s | 15,488 KiB |
| `gedex/bp3d` | 70/70 | 50 | +31 / +163.2% | 37.33% | 库内 0.324 ms | 3,584 KiB |
| `u-nesting-d3` | 70/70 | 50 | +31 / +163.2% | 37.33% | adapter 内 0.893 ms | 3,072 KiB |

时间不能横向当性能排名：PackingSolver CLI 受约 1 秒停止检查粒度影响；Go/Rust 数字是已启动进程内的库调用，且 Rust 数字包含多次极快单箱调用但不含构建/启动。该表主要比较 solution quality 和数量级资源，不做微秒级优劣结论。

## `u-nesting` 五策略敏感性与稳定性

固定源码、Rust 1.98.0、release build、`RAYON_NUM_THREADS=1`、2 GiB 地址空间上限，每个单 boundary 请求 `time_limit_ms=1000`，每个进程另设 20 秒硬超时。所有 25 个主实验和 25 个重复实验均 exit 0；exit 0 只说明库返回 JSON，不代表 certificate 合法。

| 策略 | 技术路径 / 实际参数 | 规则网格 | 必须旋转 | 禁旋 | 重量 | THPACK9-1 单次 | 同参数 5 次 THPACK9-1 | 独立 validator 判定 |
|---|---|---|---|---|---|---|---|---|
| Layer / `bottomleftfill` | 确定性 layer/row；请求 1000 ms 确实在主循环检查 | ✅ 8/8，1 箱 | ❌ 放出 `3×4×2` 进入 `4×3×2` | ✅ 正确拒装 | ✅ 3 件分 3 箱，adapter | ❌ 报 16 箱但越界 | `16,16,16,16,16`；5/5 非法 | ❌ 换层后未重检 X/Y 边界 |
| GA | population 100，generation 500，crossover 0.85，mutation 0.05；layer decoder | ✅ | ❌ 本次随机路径返回越界姿态 | ✅ | ✅ adapter | ❌ 报 15 箱但越界 | `15,15,15,15,15`；5/5 非法 | ❌ 共用 `layer_place_items` 边界 bug |
| BRKGA | population 50，generation 100，elite 0.2，mutant 0.15，bias 0.7；layer decoder | ✅ | ⚠️ 本次最小例有效，但同一 decoder 可接受非法姿态 | ✅ | ✅ adapter | ❌ 报 15 箱但越界 | `15,15,15,16,15`；5/5 非法 | ❌ decoder bug；同 seed 请求仍波动 |
| SA | temperature 100→0.1，cooling 0.95，50 iter/temp，最多 10000 iter；layer decoder | ✅ | ⚠️ 本次最小例有效，但同一 decoder 可接受非法姿态 | ✅ | ✅ adapter | ❌ 报 15 箱但越界 | `15,15,16,15,15`；5/5 非法 | ❌ decoder bug；同 seed 请求仍波动 |
| ExtremePoint | 体积降序；orientation 0..n、EP 以 z/y/x 排序，首个可行即提交 | ✅ | ✅ | ✅ | ✅ adapter | ✅ 50 箱、70/70、无越界/重叠 | `50,50,50,50,50`；5/5 有效 | ✅ 本轮唯一可用于质量统计的 `u-nesting` 策略 |

参数接线另有独立问题。`Config.seed=42` 没有传入 GA/BRKGA/SA runner，它们调用系统随机源，因此 `seed_effective=false`；Layer/ExtremePoint 是确定性路径，seed 不适用。`Config.time_limit_ms` 只在 Layer 主循环读取，GA/BRKGA/SA/ExtremePoint 都未接线，因此这些策略真正统一的停止条件只有外部 20 秒 timeout。官方 3D 配置文档把 `time_limit_ms` 写成 “Maximum solving time”，配置源码也称 seed 用于可复现随机策略，与当前执行路径不一致。

Layer 的最小复现不是 adapter 误读姿态：输入物品原尺寸 `3×2×4`、箱 `4×3×2`、允许旋转，库返回 rotation index 1 和尺寸 `3×4×2`。`packer.rs` 与共享 `packing_utils::layer_place_items` 在 Y 超限后把位置重置到新层，随后只检查 Z 高度，未再次检查 `x+width` / `y+depth`，于是接受深度 4 进入深度 3 的箱。GA/BRKGA/SA 都通过该共享 decoder 计算 fitness 和最终坐标。

## THPACK9 全 44 个合法实例

ESICUP `thpack9.txt` 共 47 个实例；`THPACK9-018/019/020` 源数据行缺字段，按 parser 记录排除，未把 malformed 输入记成算法失败。其余 44 个实例为 70–180 件，vertical flags 均为 `(1,1,1)`，可由六轴向旋转精确表达。每实例使用 35 秒进程超时、2 GiB `RLIMIT_AS`、单线程环境；原始 input/stdout/stderr/exit code/resources 和逐件坐标均保存。

| 候选 | 多箱能力归属 | 执行 / 有效完整 | identity | 姿态 | 边界 | 同箱重叠 | 箱数 mean / median / p95 | min–max | 库内耗时 mean / p95 | RSS median / p95 | invalid rate |
|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|
| `gedex/bp3d` | ✅ 上游原生多个 `Bin` 对象 | 44 / 44 | ✅ 44/44 | ✅ 44/44 | ✅ 44/44 | ✅ 44/44 | 19.93 / 16 / 55 | 2–68 | 1.678 / 3.772 ms | 3712 / 4224 KiB | 0% |
| `u-nesting` ExtremePoint | ⚠️ `ADAPTER_MULTI_BIN`：重复调用单 `Boundary3D` | 44 / 44 | ✅ 44/44 | ✅ 44/44 | ✅ 44/44 | ✅ 44/44 | 18.41 / 14 / 52 | 2–55 | 1.249 / 2.374 ms | 2944 / 3072 KiB | 0% |

Rust adapter 合计 810 箱，Go 合计 877 箱；Rust 少用箱 16 例、相同 26 例、多用箱 2 例。这里不计算 “gap to optimum”：当前 campaign 没有为这些实例引入可信 BKS/optimum，箱数只是有效 incumbent。库内毫秒时间也不含进程启动和 JSON I/O，不应拿来与 C++ CLI 的 wall time 做微秒级排名。

逐实例表中“✅”同时表示 item identity、完整性、vertical orientation、边界和同箱 AABB overlap 全通过；差值为 `Go - Rust`，正数表示本轮 Rust adapter 少用箱。

| 实例 | 件数 | Go 箱数 | Go 五项校验 | Rust 箱数 | Rust 五项校验 / 能力归属 | 差值 |
|---|---:|---:|---|---:|---|---:|
| `THPACK9-001` | 70 | 50 | ✅ | 50 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-002` | 70 | 10 | ✅ | 10 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-003` | 180 | 24 | ✅ | 23 | ✅ `ADAPTER_MULTI_BIN` | +1 |
| `THPACK9-004` | 180 | 27 | ✅ | 30 | ✅ `ADAPTER_MULTI_BIN` | -3 |
| `THPACK9-005` | 180 | 65 | ✅ | 52 | ✅ `ADAPTER_MULTI_BIN` | +13 |
| `THPACK9-006` | 103 | 11 | ✅ | 10 | ✅ `ADAPTER_MULTI_BIN` | +1 |
| `THPACK9-007` | 103 | 16 | ✅ | 16 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-008` | 103 | 4 | ✅ | 4 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-009` | 110 | 25 | ✅ | 22 | ✅ `ADAPTER_MULTI_BIN` | +3 |
| `THPACK9-010` | 110 | 55 | ✅ | 55 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-011` | 110 | 25 | ✅ | 18 | ✅ `ADAPTER_MULTI_BIN` | +7 |
| `THPACK9-012` | 95 | 68 | ✅ | 55 | ✅ `ADAPTER_MULTI_BIN` | +13 |
| `THPACK9-013` | 95 | 40 | ✅ | 40 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-014` | 95 | 40 | ✅ | 40 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-015` | 95 | 15 | ✅ | 15 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-016` | 95 | 33 | ✅ | 33 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-017` | 95 | 10 | ✅ | 10 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-021` | 95 | 23 | ✅ | 23 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-022` | 95 | 11 | ✅ | 10 | ✅ `ADAPTER_MULTI_BIN` | +1 |
| `THPACK9-023` | 95 | 24 | ✅ | 26 | ✅ `ADAPTER_MULTI_BIN` | -2 |
| `THPACK9-024` | 72 | 7 | ✅ | 7 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-025` | 72 | 5 | ✅ | 5 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-026` | 72 | 4 | ✅ | 4 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-027` | 95 | 5 | ✅ | 5 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-028` | 95 | 12 | ✅ | 11 | ✅ `ADAPTER_MULTI_BIN` | +1 |
| `THPACK9-029` | 118 | 22 | ✅ | 21 | ✅ `ADAPTER_MULTI_BIN` | +1 |
| `THPACK9-030` | 118 | 25 | ✅ | 25 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-031` | 118 | 16 | ✅ | 14 | ✅ `ADAPTER_MULTI_BIN` | +2 |
| `THPACK9-032` | 90 | 5 | ✅ | 5 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-033` | 90 | 18 | ✅ | 5 | ✅ `ADAPTER_MULTI_BIN` | +13 |
| `THPACK9-034` | 90 | 20 | ✅ | 10 | ✅ `ADAPTER_MULTI_BIN` | +10 |
| `THPACK9-035` | 84 | 3 | ✅ | 3 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-036` | 84 | 16 | ✅ | 14 | ✅ `ADAPTER_MULTI_BIN` | +2 |
| `THPACK9-037` | 102 | 23 | ✅ | 23 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-038` | 102 | 45 | ✅ | 45 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-039` | 102 | 18 | ✅ | 18 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-040` | 85 | 12 | ✅ | 11 | ✅ `ADAPTER_MULTI_BIN` | +1 |
| `THPACK9-041` | 85 | 23 | ✅ | 21 | ✅ `ADAPTER_MULTI_BIN` | +2 |
| `THPACK9-042` | 90 | 5 | ✅ | 4 | ✅ `ADAPTER_MULTI_BIN` | +1 |
| `THPACK9-043` | 90 | 4 | ✅ | 4 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-044` | 90 | 4 | ✅ | 4 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-045` | 99 | 3 | ✅ | 3 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-046` | 99 | 2 | ✅ | 2 | ✅ `ADAPTER_MULTI_BIN` | +0 |
| `THPACK9-047` | 99 | 4 | ✅ | 4 | ✅ `ADAPTER_MULTI_BIN` | +0 |

## 为什么会得到这些结果

### PackingSolver

官方 README 的 `box` feature 明确列出 `Variable-sized bin packing`，CLI、目标枚举、bound、formatter 和 tree search 都认识该目标；因此原版异常不是参数误用。官方 `box::Solution::operator<` 和 `boxstacks::Solution::operator<` 唯独漏掉该 objective，两个可行方案需要比较时落入 default 并抛异常。

本轮新增的行序实验解释了“为什么有时看似能用”：大箱行先时预处理/控制流可落到单一有效 bin type，未触发 comparator；小箱行先时两个不同 bin type 留到方案池比较，立即报错。PR #540 在两个 comparator 中加入与 rectangle/onedimensional 相同的成本比较分支；固定 fork 两种行序都选择大箱、成本 10，说明修复方向和比较方向均正确。

### `gedex/bp3d`

它是简单的体积排序 + pivot greedy：箱按体积升序、物品按体积降序；已放物品的三个正方向面生成 pivot。四个直接后果与实验一致：

1. `PutItem` 无累计重量检查，`MaxWeight` 只是结构字段；所以 3 个重量 6 的物品进入同一上限 10 的箱。
2. `PutItem` 固定遍历 6 个旋转且没有 per-item whitelist；所以 fixed 场景仍旋转成功。
3. 异构场景先向小箱贪心提交第一件，第二件再升级到大箱；没有回溯把两件合并到大箱，也没有成本目标，最终成本 17。两份输入都先被体积排序，所以原始行序不产生区别。
4. pivot 使用 `GetWidth/GetHeight/GetDepth` 的原始尺寸而不是当前旋转后的尺寸；而且某个姿态边界可行但碰撞后，`PutItem` 会直接 return，不继续尝试后续姿态。这会漏掉更紧凑的候选布局。THPACK 中 50 个大件基本各占一箱，之后小件填缝，最终 50 箱。

上游 `go test` 的失败不是本轮 certificate 违反几何，而是测试把等体积物品的顺序和具体坐标整段写死；Go 1.27 得到另一组合法顺序。即使忽略该脆弱测试，重量和姿态两项仍是独立 validator 确认的功能性失败。

### `u-nesting-d3` Layer / GA / BRKGA / SA

Layer 主路径和 `packing_utils::layer_place_items` 有相同的状态转移缺口：当前行 X 放不下时推进 Y；Y 放不下时推进 Z 并把 X/Y 重置到 margin；之后只检查 `current_z + height`，没有再检查重置后的 `width/depth` 是否本身小于容器。这个错误不仅影响 Layer，还是 GA/BRKGA/SA 的共同 decoder，因此随机搜索是在优化一个会奖励非法越界布局的 fitness，不能靠增加 population、generation 或运行时间修复。

GA 从顶层 `Config` 读取 population/generation/crossover/mutation，但不读取 `Config.seed/time_limit_ms`；BRKGA 和 SA 甚至在 `packer.rs` 内重新构造硬编码参数，也没有接入顶层 seed/time limit。固定 `RAYON_NUM_THREADS=1` 后，同样请求 seed 42 的 BRKGA 与 SA 仍分别在 15/16 箱波动，和源码调用 `rand::rng()` 一致。这是上游参数接线问题，不是 campaign 把 seed 传错位置。

### `u-nesting-d3` ExtremePoint

本轮调用的是 `Strategy::ExtremePoint`；adapter 记录请求 seed 42 和每 boundary 1000 ms，但该策略是确定性的，seed 不适用，而且源码没有读取 `Config.time_limit_ms`，真正保护进程的是 campaign 外部 20/35 秒 timeout。其控制流先按体积降序，再对每件物品按 orientation index 从 0 开始，按 z/y/x 的 EP 优先队列选择第一个可放位置，并在首次成功后停止尝试其他旋转。官方算法指南写的是“evaluate all extreme points / select the point that minimizes wasted space”，与当前 first-fit 实现也不完全一致。

THPACK 大件的 identity `8x4x10` 能在空箱原点放下，因此算法不会先尝试可使两个大件更紧密组合的 `10x4x8`；adapter 又在单箱无法放更多大件后开启下一 boundary，形成 50 个“大件各一箱”，小件随后填入前几个箱的剩余空间。

这不是 certificate bug：所有 70 个 placement 均在边界内且无重叠。它是 first-fit 姿态顺序 + 单箱 API + 外层重复调用共同造成的质量结果。若继续评估该库，应把 `Layer/GA/BRKGA/SA/ExtremePoint` 全部跑同一 THPACK campaign，并把“选择姿态的评分”纳入调参，而不是只优化 seed。

## Issue、文档与是否应提 PR

| 项目 | 已有上游记录 | 本轮判断 | 建议动作 |
|---|---|---|---|
| PackingSolver 异构成本 | issue #536 open；PR #540 open，API 快照更新于 2026-08-31 | 已有最小复现、根因、patch 和测试；本轮又增加输入行序 A/B 证据 | 不重复开 issue；可把本轮 small-first/large-first 对照和 fixed 603-test 结果补充到现有 PR |
| `gedex/bp3d` 重量 | issue #1 open（2016）；PR #4 `Check weight` open（2018） | known missing enforcement，不是新发现 | 不重复开 issue；若必须采用，应维护 fork 并补累计重量、姿态白名单、旋转后 pivot 和回归 validator，但整体维护收益偏低 |
| `gedex/bp3d` 边界 | issue #6 `Objects locate outside bin` open | 本轮全部成功 certificate 未复现越界；源码的原始尺寸 pivot 值得单独最小化 | 先构造能稳定越界/漏装的最小例，再决定评论 #6 或新 issue；当前证据不足以声称复现 #6 |
| `u-nesting` 源码依赖 | issue #1 曾报告 fresh checkout path deps，因发布 registry crate 于 2026-05-05 关闭 | 当前 `0.9.0` 源码仍需仓库外三依赖；CI 每次 shallow clone 未固定 main，源码 checkout 可复现性问题仍存在 | 值得开一个聚焦当前 0.9 source build/CI pin 的新 issue；PR 可改用 registry deps，或将兄弟仓作为 submodule/git rev 并提交锁定说明 |
| `u-nesting` Layer 越界 | 官方 issue 列表只有 #1，未见同类报告；源码注释称 GA layer decoder 为 `collision-free` | 新的确定性最小复现；Layer 必须旋转场景出界，Layer/GA/BRKGA/SA 的 THPACK9-1 均被独立 validator 判非法 | **适合开新 issue + PR**：在 `packer.rs` 与 `packing_utils.rs` 换层后统一重检 X/Y/Z；增加 `3×2×4` into `4×3×2` 回归，并让现有 “respects bounds” 测试枚举会单轴超限的姿态 |
| `u-nesting` seed/time limit | 无现有 issue；官方 3D 文档称 `time_limit_ms` 为 maximum，`Config.seed` 注释称随机策略可复现 | GA/BRKGA/SA 不接 seed；除 Layer 外本轮五策略其余路径不接顶层 time limit；五次重复已观察到同 seed 结果波动 | **适合另开 issue/PR**：把 seed 映射到各 runner 的 seeded RNG，把 time limit 映射到 GA/BRKGA/SA config，并给 EP 增加 deadline/cancel check；分别写相同 seed 输出一致和极短 deadline 的测试 |

这里没有直接向外部仓库写评论或创建 issue/PR；raw 只保存了公开 API 证据。`u-nesting` 应拆成三个聚焦条目：source checkout 可复现性、layer bounds correctness、seed/deadline wiring；不要把它们混成一个难以审阅的大 issue，也不要把已解决的 crates.io 安装问题重复报告。边界 bug 的 PR 范围很小且已有最小回归，优先具备提交条件；参数接线涉及多个 runner，适合先 issue 确认 API 语义再拆 PR。

## 输出格式与前端展示

PackingSolver 原生输出是 certificate CSV：`TYPE, ID, COPIES, BIN, X, Y, Z, LX, LY, LZ, ROTATION`。其中 `COPIES` 是聚合 packing pattern，前端或 validator 必须展开成不同物理箱，不能把多份布局叠在同一 `BIN` 上。官方仓库自带 `scripts/visualize_box.py`。

`u-nesting` 的 serde/C FFI wire response 已包含 `geometry_id`、`bin_index`、`x/y/z`、orientation、利用率和未装件；Go `bp3d` 返回 Bin/Item struct，需要自行定义 JSON。本 campaign 统一成：

```text
bins[]:       id, size[3], max_weight, cost
items[]:      id, size[3], weight, orientation_requirement
placements[]: item_id, bin_id, position[3], size[3], rotation
unplaced[]:   item_id
```

前端最有信息量的交互不是只画一个静态箱体，而是：按物理箱分页/缩略图浏览；3D 中显示半透明边界和逐件 hover 元数据；按 item type/rotation/weight 着色；切换 validator overlay（越界红、重叠洋红、超重箱警告）；并排比较 `small-first`/`large-first` 和不同库的同一实例。指标栏至少显示装入件数、箱数、成本、利用率、未装件、约束错误和求解状态。Canonical JSON 应作为前后端契约，PackingSolver 的聚合 CSV 仅作为原始证据保留。

## 复现入口与证据位置

```bash
CROSSLANG_TOOLCHAIN_ROOT=/tmp/crosslang-toolchains \
  benchmarks/campaign/crosslang_go_bp3d/run.sh
CROSSLANG_TOOLCHAIN_ROOT=/tmp/crosslang-toolchains \
  benchmarks/campaign/crosslang_rust_unesting/run.sh
CROSSLANG_TOOLCHAIN_ROOT=/tmp/crosslang-toolchains \
  benchmarks/campaign/crosslang_rust_unesting/run_strategies.sh
CROSSLANG_TOOLCHAIN_ROOT=/tmp/crosslang-toolchains \
  benchmarks/campaign/crosslang_rust_unesting/run_strategy_repeats.sh
CROSSLANG_TOOLCHAIN_ROOT=/tmp/crosslang-toolchains \
  benchmarks/campaign/crosslang_run_thpack9.sh
benchmarks/campaign/crosslang_cpp_packingsolver/run.sh official
benchmarks/campaign/crosslang_cpp_packingsolver/run.sh fixed
python3 benchmarks/campaign/crosslang_validate.py
```

- 原始 stdout/stderr、exit code、resource、certificate、toolchain、源码与 binary hash：`raw/experiments/campaign/crosslang_*`
- 独立校验汇总：`results/campaign/crosslang_*/results.json`
- GitHub API 证据与 SHA-256：`raw/experiments/campaign/crosslang_repo_evidence/`
- campaign adapter、固定参数和输入：`benchmarks/campaign/crosslang_*`
