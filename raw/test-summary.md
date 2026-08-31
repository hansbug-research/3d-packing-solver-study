# 本地受控实测摘要

> 最后复跑：2026-08-31。平台为 Linux x86-64、Python 3.12.1、OpenJDK 21。这里的“通过”只表示给定小型测试及独立几何校验通过，不代表覆盖所有业务工况或其他操作系统。

## 资源控制

- Python/C++ 测试由 [`benchmarks/run_controlled.sh`](../benchmarks/run_controlled.sh) 启动：外层 35 秒超时、4 GiB 虚拟内存上限，并设置常见数值库线程数为 1。
- PackingSolver 每个子任务另设 10 秒和 1 GiB 内部上限；精确模型显式设置单 worker/单线程。
- Java 测试使用 `-Xmx512m -XX:ActiveProcessorCount=1`。JVM 启动、JIT 或 GC 仍可能短时创建辅助线程，因此不能把它描述为严格单线程进程。
- 结果 JSON 位于本目录；本表的 wall time 与最大 RSS 取 canonical `raw/experiments/*.resources.txt`。`results/raw/` 是运行工作目录并被 `.gitignore` 排除，`raw/resources/` 保留更早的资源快照，不用于本表当前数字。

## 结果总表

| 候选 | 本次覆盖 | 结果 | 整进程 wall / 最大 RSS | 结论 |
|---|---|---|---:|---|
| PackingSolver `latest-2026-07-28` | 规则网格、旋转子集、禁旋、重量、上压、异构成本、半挂轴荷边界例 | 基础几何/旋转/重量/上压通过；禁旋实例正确不装；异构成本与轴荷边界例异常退出 | 5.07 s / 15,232 KiB（8 个子任务合计） | 最接近真实工况，但只能 pin SHA 后有条件采用；两条失败路径是上线门禁 |
| OR-Tools 9.15.6755 CP-SAT | 9 个 `5x5x5` 立方体装入 `10x10x10` 同型箱的直接三维模型 | `OPTIMAL`，箱数 2，best bound 2；几何校验通过 | 0.41 s / 100,212 KiB | 成本主问题与 exact-small 首选；不是现成 3D packer |
| PySCIPOpt 6.2.1 / SCIP | 与 CP-SAT 相同的连续坐标 MIP | `optimal`，目标 2，dual bound 2，gap 0；几何校验通过 | 0.15 s / 61,016 KiB | 开源 MIP/CIP 扩展轨；同样需要自建 3D 模型 |
| `py3dbp` 1.1.2 | 网格、需旋转、重量、多箱型顺序反转 | 基础场景通过；小箱先输入用 2 箱，大箱先输入只用 1 箱 | 0.03 s / 13,696 KiB | 很快但顺序敏感，只作基线 |
| Jerry Python 分支 | `loadbear` 承压反例 | 几何通过，但脆弱件上方实际放置重量 20；`loadbear` 仅参与排序 | 0.40 s / 67,684 KiB | 不能作为承压约束求解器 |
| Skjolber Java `c73d521...` LAFF | 网格、三维旋转、仅平面旋转、重量、100 件 | 所有预期通过；100 件库内 21.275 ms，THPACK9-1 为 8.315 ms | 约 0.43 s / 78,336 KiB（当前 raw 资源快照） | 强几何备选/对照；高级力学只是扩展点，暂不足以抵消 JVM 集成成本 |

wall time 包含解释器/JVM/进程启动，不等于库内求解时间；PackingSolver 一行还包含多个固定约 1 秒停止粒度的子任务。不同语言的微型测试不能仅凭该列作性能排名。

## 已复现的关键差异

### PackingSolver

- `box` 与 `boxstacks` 的 `variable-sized-bin-packing` 均在方案比较阶段退出，错误为 `Solution::operator<` 不支持该 objective，且没有证书。普通 `bin-packing` 会受箱型输入顺序影响，不能替代价格优化。
- 半挂轴荷合成边界例没有生成证书：受控全量复跑为 `std::bad_alloc`，此前单独复跑为 `std::bad_array_new_length`。据此只能判定该输入路径未通过，不能推断所有正常参数下的轴荷功能失效。
- `rotation_forbidden` 的 `packed=0` 是期望行为：物品只有旋转后才可装入，而输入禁止相应旋转。汇总脚本的 `validation_errors` 记录“未装到 expected=1”，不应误读为求解器违反方向限制。

### 精确模型

CP-SAT 与 SCIP 的小例均闭合上下界，因此只对这个模型和实例可写“已证明最优”。两者都没有内建通用三维装箱约束；直接模型含随物品对数增长的六向不相交析取，不能把本次 9 件结果外推到数百件。

### Java 与原生 binding

Skjolber 的实测说明 Java 不是能力上不可用：LAFF 的基础几何速度和行为都合格。但它没有原生实现本项目要求的通用承压、稳定、轴荷和箱价目标。若后续在真实基准上显著优于主引擎，可通过常驻 sidecar 纳入；首版不应仅为相近的几何启发式增加裁剪 JRE、IPC、签名和三平台打包成本。

C/C++/Rust 实现不因语言被排除。优先级依次是可审计的官方 wheel（pybind11/PyO3/cffi）、在 Python worker 内加载的稳定 ABI binding、受限 CLI 子进程。原生模块仍放在独立 worker，避免崩溃拖垮桌面 UI。Rust `u-nesting` 因项目新、3D 仍为 axis-aligned 且本机无 Cargo，未进入 shortlist，也未伪称已经实测。

## 判定边界

- **通过**：测试输入完整、输出几何/方向/重量等本场景硬约束经独立校验通过。
- **功能缺失**：库没有对应模型或接口，不能用样例偶然满足冒充支持。
- **已复现缺陷/失败路径**：同一固定输入可得到异常或错误语义；上线前必须回归关闭。
- **未测试**：不进入 shortlist、环境不具备，或授权/平台不可用；不会据此作通过判断。

完整算法、复杂度、最优性和源码证据见 [`research/algorithms.md`](../research/algorithms.md)，工况与元模型见 [`research/domain-model.md`](../research/domain-model.md)。

## 公共 THPACK9 对照

从 ESICUP `3d_rectangular/thpack/thpack9.txt` 转换了 instance 1（`10x6x16` 箱，20 件 `2x6x8`、50 件 `8x4x10`）。同一实例用 80 个候选箱运行。`py3dbp`/Jerry 使用共享的 `benchmarks.validation.validate_aabbs`，Skjolber 使用 runner 内的边界与 `intersects3D` 检查，PackingSolver patched certificate 使用 `COPIES` 展开审计；三者均通过各自的独立几何检查：

| 实现 | 完整件数 | 使用箱数 | 结果状态 |
|---|---:|---:|---|
| PackingSolver patched `box` | 70/70 | 25 | feasible incumbent |
| Skjolber LAFF | 70/70 | 28 | feasible incumbent |
| `py3dbp` | 70/70 | 50 | feasible incumbent |
| Jerry fork | 70/70 | 50 | feasible incumbent |

该实例体积下界为 19 箱，但没有在数据文件中提供 known optimum；25 不能标记为 `PROVEN_OPTIMAL`。原始库/修复版差异、聚合 `COPIES` certificate 的展开规则和复现命令见 [`research/packingsolver-upstream.md`](../research/packingsolver-upstream.md)，统一数据和 baseline 命令见 [`research/benchmarks.md`](../research/benchmarks.md)。
