# Comprehensive campaign

本目录承载 `benchmark-protocol/3` 的 B01-B32 综合实验。`suite-implementation-plan.jsonl` 与 `coverage-plan.csv` 是 32 个套件乘 19 个实现/算法变体的确定性执行计划；它们不是测试结果。未执行单元固定为 `run_status=NOT_RUN`、`solution_status=NOT_APPLICABLE`，并用 `input_status`、`capability_status` 和 `termination_reason` 区分来源待补、adapter 待实现、问题投影与明确不支持。

生成和检查计划：

```bash
.venv/bin/python benchmarks/comprehensive/build_plan.py
.venv/bin/python benchmarks/comprehensive/build_plan.py --check
.venv/bin/python benchmarks/comprehensive/import_baseline.py
.venv/bin/python benchmarks/comprehensive/analyze.py
```

Wave-1 fresh exact/Skjolber 结果的执行与协议导入命令为：`bash benchmarks/campaign/run_exact.sh`、`bash benchmarks/campaign/run_skjolber_thpack.sh`、`.venv/bin/python benchmarks/comprehensive/import_fresh_protocol.py`；导入器只消费这两组 runner 的当前输出，记录 `FRESH_SOLVER_INVOCATION`，并将结果、runner、输入 hash 和独立 validator 引用写入 `runs/wave1-fresh-protocol.jsonl`。

实际实例级运行写入 `run-manifest.jsonl`，每条记录遵守 [`run-record.schema.json`](../../benchmarks/comprehensive/run-record.schema.json)。`baseline-import-summary.json` 标明哪些记录来自已有 v1/v2 原始归档；新运行仍必须使用协议规定的 `raw/experiments/comprehensive/` 目录。`coverage.csv` 是计划与实际运行合并后的覆盖表。只有 `VALID_COMPLETE` 或原问题允许的 `VALID_PARTIAL` 且通过独立 validator 的记录才能进入 `rankings/`；`NATIVE`、`COMPOSED`、`EXACT_MODEL` 以及 `FULL_PROBLEM`、`GEOMETRY_PROJECTION` 分榜。

`run-manifest.jsonl` 通过 Git LFS 跟踪（当前对象约 141 MB）；检出仓库后请执行 `git lfs install` 与 `git lfs pull`，否则工作区中会只看到 pointer 文件，不能运行本目录的导入、分析和验证脚本。

B30/B31 的 `exact-calibrations.jsonl` 是四条可手工复核的小 fixture 真值记录：B30 证明两个声明 shelf 必须使用两个 shelf，B31 覆盖平铺/堆叠最优和总重量不可行。它们都带 `metrics.calibration_only=true`，只用于 validator/adapter 校准，不替代完整 BAYTP 或 mixed-SKU 订单 corpus。复现命令为 `python benchmarks/comprehensive/run_exact_calibrations.py`，然后依次运行 `python benchmarks/comprehensive/import_baseline.py` 和 `python benchmarks/comprehensive/analyze.py`。

B24-B29 reliability-v3 已完成 347 条全库记录，分别输出 metamorphic、numeric、repeatability、scalability 和 fault/cancellation 表；这些结果只回答工程稳定性、资源边界和托管行为，不与几何质量或成本排行合并。复现实验使用 `.venv/bin/python benchmarks/comprehensive/run_reliability.py`，输入和 runner hash 见 [`reliability-source-audit.json`](reliability-source-audit.json)，原始产物位于 `raw/experiments/comprehensive/reliability-v3/`。

B21 ESICUP VRPTW-CLP 的来源审计见 [`b21-source-audit.json`](b21-source-audit.json)。46 个实例文件中 23 个含缺失高度标志的 8 字段货物行，另有 1 个客户行缺字段，因此 suite catalog 使用 `SOURCE_INVALID`，所有 B21 cells 只保留 `SOURCE_PENDING` 状态记录；不得通过猜补或删除行后继续使用原 benchmark 名称。

B19/B20 已新增 Alonso source-derived geometry projection 首轮：2019/2020 各取需求件数不超过 600 的最小实例，PY/JE/GO/RS 五策略按 1 s、升序/降序运行，共 84 条记录。该轨道明确删除层、托盘、交付日、成本和轴荷语义，结果仅用于几何迁移诊断；FULL 轨仍保持 `ADAPTER_MISSING`。排行见 [`industrial-projection.csv`](rankings/industrial-projection.csv)。

B11 已完成 fork-owned open-X 校准运行：fork/upstream `box` 各 3/3 个 case 通过独立 validator，fork `boxstacks` 3/3 因非同底面 stack 语义报错并保留原始证据；上游 `boxstacks` 因当前工作区缺少对应二进制保持未运行。另对 py3dbp、Jerry、Go `bp3d` 和 u-nesting 五策略运行逐整数 X 外层搜索，共 24 条 projection 记录，其中 23/24 为完整合法证书；Rust Layer 的 `open_dimension_x_xz` 无完整候选。结果见 [`open-dimension.csv`](rankings/open-dimension.csv)，原生与投影不与 BR/LN 或封闭箱数排行混排。

当前导入 2,122 条已有运行，并合并 B03、B07、B09 composed cost-master、B11 open-X 外层搜索、B32 online composed policy、约束 gauntlet、B30 shelf/bay projection、B31 mixed-SKU pallet projection、来源/能力状态、B01/B02 Python/Go/Rust projection、B01/B02/B04 PackingSolver native certificate revalidation，以及 Wave-1 fresh exact/Skjolber 记录的 60,927 条 protocol-v3 记录，形成 `26/32` 个实际执行 benchmark、`32/32` 个有状态记录的 benchmark、19 个实现/算法变体和 `554/608` 个有证据计划单元；其中 `257` 个单元是 status-only，`19` 个单元仍只有历史基线。B21 的 19 个 status-only cells 由来源审计阻断，详见 [`b21-source-audit.json`](b21-source-audit.json)。B11 外层搜索新增 24 条记录（23/24 完整合法），B30 的 8 条 projection 记录全部通过几何放置但被 shelf/bay validator 判为 `CONSTRAINT_VIOLATION`，单列于 `rankings/industrial-baytp.csv`；B31 的 24 条 projection 记录按 3 个 case 统计，单列于 `rankings/industrial-mixed-pallet.csv`；B32 新增 48 条组合 online 记录（2 条 arrival trace × 8 个实现 × 3 个 policy），全部为 `VALID_COMPLETE`，单列于 `rankings/industrial-online.csv`，上述三类结果都不与自由 3D-BPP 排名混合。B31 fixture 已通过独立来源审计并标记 `VALID`，但 FULL `boxstacks`/exact adapter 仍未完成。B01/B02 projection 有 22,880 条实例记录，PackingSolver native revalidation 新增 1,524 条 BR/LN/IMM 记录，B07 projection 新增 30,600 条实例记录（Go/Rust 21,600，Python 7,200，Jerry `fix_point=False` control 1,800）；B07 又增加 4 条 source-rotation exact calibration 记录；B09 composed runner 为 py3dbp/Jerry/Go/Rust 各生成两个成本方向记录，并保留全部箱型组合候选。所有 fresh 记录明确标为 `FRESH_SOLVER_INVOCATION`，并保留结果 hash、runner hash、输入 hash 和独立验证引用。projection 显式标为 `RELAXED_ALL_ROTATIONS`、`GEOMETRY_PROJECTION`，exact calibration 保留 `SOURCE_ROTATION_FLAGS`，三者均不覆盖另一条语义轨。native revalidation 明确标为 `ARCHIVED_CERTIFICATE_REVALIDATION`，不是一次新的 solver invocation；其输入 hash、fork commit、binary hash 和原始验证行均保留。status-only 记录只证明来源/能力边界，不是求解运行；其余单元在 `coverage.csv` 中继续显示 `SOURCE_PENDING`、`ADAPTER_MISSING`、`NOT_SUPPORTED` 或 `PLANNED`，不得把其中任何一种改写成已经实测。

历史快照（B11、FastBruteForce、B30 加入前）仅用于追溯；当前权威统计以 `aggregate.json`、`coverage.csv` 和 `baseline-import-summary.json` 为准。B04 的 FastBruteForce 44 个源实例中仅 7/44 通过独立 validator，37/44 保留为非法证书；该失败比例进入共同实例表，不被成功样本掩盖。

现有排行按问题语义拆分：`volume-knapsack.csv` 显式保留 `problem_variant/problem_scope`，`volume-knapsack-common.csv` 只比较共同实例，`B07-version-pairwise.csv` 比较 fork/upstream 的相同 BR 桶和预算，`B07-projection-common.csv` 比较八个 projection 实现的共同合法实例，`B07-jerry-fixpoint-pairwise.csv` 记录 Jerry `fix_point` 参数的合法性/质量权衡，`identical-bin-packing.csv` 与 pairwise 表比较 B04 的共同 44 例，`profit-knapsack.csv` 分开比较 B03 的固定姿态/全旋转投影，`exact-proof.csv` 比较 B03/B06/B07/B09 的统一模型或校准模型证明能力，`variable-cost.csv` 只比较带独立验证 `total_cost` 的 B08/B09 记录，`constraint-conformance.csv` 保留 B09、B12-B18 hard-case 行为，`industrial-baytp.csv` 单独报告 B30 shelf/bay 合规，`industrial-mixed-pallet.csv` 单独报告 B31 mixed-SKU pallet 合规，`industrial-online.csv` 单独报告 B32 composed online policy，`resource-summary.csv` 使用独立计时组而不制造跨语言统一速度榜。B05 当前只有来源审计和状态记录，没有质量排行。约束 gauntlet runner 和 fixture 说明见 [`research/constraint-gauntlet.md`](../../research/constraint-gauntlet.md)。所有表都是阶段性结果；尚无运行的 B05、B08、B10、B19-B23 不会出现伪造的数值排行；B32 只有组合 projection，不代表原生 online 支持。

B09 composed cost-master 的复现命令为：

```bash
python3 benchmarks/comprehensive/run_b09_python_composed.py
python3 benchmarks/comprehensive/run_b09_external_composed.py
python3 benchmarks/comprehensive/import_baseline.py
python3 benchmarks/comprehensive/analyze.py
```

外部 runner 默认使用已固定的 Go binary 和 Rust release binary；若本机没有对应构建，应保持 `ADAPTER_MISSING`，不能改用未审计的 rolling binary。两个 runner 都把每一个箱型组合和 item order 的失败候选保存在 artifact archive，只有独立 validator 通过的完整候选才参与成本选择。

B11 open-X 校准复现命令：

```bash
python3 benchmarks/comprehensive/audit_b11_source.py --output results/comprehensive/b11-source-audit.json
python3 benchmarks/comprehensive/run_b11_packingsolver.py --time-limit 2 \
  --implementation packingsolver_fork_box \
  --implementation packingsolver_fork_boxstacks \
  --implementation packingsolver_upstream_box
python3 benchmarks/comprehensive/import_baseline.py
python3 benchmarks/comprehensive/analyze.py
```

该套件是 fork 测试回归派生的三例 `open-dimension-x`、固定 `XYZ` 姿态；它校准开放长度和证书验证链，不是独立公开质量集。`packingsolver_boxstacks` 需要同底面 stack 输入，因而在本 fixture 上的错误退出会作为可靠性证据保留。

B07 source-rotation exact calibration 可复现为：

```bash
.venv/bin/python benchmarks/comprehensive/run_b07_exact.py \
  --max-items 60 --time-limit 20
```

默认选择 4 个总件数不超过 60 的实例。模型保留源文件中的垂直方向 flags，`VALID_PARTIAL` 只表示通过独立几何/姿态校验的 incumbent；`PROVEN_OPTIMAL` 只有 CP-SAT 上下界闭合时才出现。本轮 4/4 在 20 秒内有合法 incumbent，但均未证明最优，gap 为 `21.95%–27.08%`，因此只用于 B07 projection/native 质量校准，不进入大规模速度排名。

Skjolber Plain/LAFF 的原生 B07 尝试没有进入排行：两个算法在 900 个单箱实例上共 1,800 次调用均返回空结果。原因是其 `Packager` 接口没有 optional-subset objective，不能把 B07 当作“允许漏装、最大化体积”的问题；审计摘要见 [`B07-skjolber-subset-api-audit.json`](B07-skjolber-subset-api-audit.json)。

## B03 复现命令

以下命令均从仓库根目录执行。三条轨道必须分别保存结果：PackingSolver 是原生 `FIXED_XYZ/NATIVE`，Python/Go/Rust 是显式标注的 `COMPOSED`（其中 Python/Go 为 `RELAXED_ALL_ROTATIONS/GEOMETRY_PROJECTION`），CP-SAT 是 `EXACT_MODEL` 的 20 件小规模校准。运行前应先准备协议中固定提交的源目录和对应二进制；`--source-root`、`--binary-source-root` 与 `--binary` 不应指向未审计的 rolling checkout。

```bash
# PackingSolver fork，原生固定姿态 profit knapsack
.venv/bin/python benchmarks/comprehensive/run_b03_packingsolver.py \
  --implementation-id packingsolver_fork_box \
  --binary .cache/packingsolver-fork/build/packingsolver_box \
  --binary-source-root .cache/packingsolver-fork \
  --time-limit 1 --label 1s

# Python/Go/Rust adapter；将 implementation-id 替换为 py3dbp、jerry、go_bp3d、
# rust_extreme_point、rust_layer、rust_ga、rust_brkga 或 rust_sa
.venv/bin/python benchmarks/comprehensive/run_b03_adapters.py \
  --implementation-id py3dbp --time-limit 1 --label 1s

# 固定姿态 exact CP-SAT，只运行 20 件层，不能外推到 40/60 件
.venv/bin/python benchmarks/comprehensive/run_b03_exact.py \
  --source-root .cache/packingsolver-fork --time-limit 20
```

重算汇总与门禁：

```bash
.venv/bin/python benchmarks/comprehensive/import_baseline.py
.venv/bin/python benchmarks/comprehensive/analyze.py
.venv/bin/python scripts/verify.py
```

## Constraint gauntlet 复现

## B07 全库 projection 复现

B07 的 Python、Go 和 Rust 轨都使用固定 fork 数据目录；Python/Jerry 通过 canonical JSON 输入，Go/Rust 通过 external CLI。下面的命令分别生成 900 例 × 两排序的 protocol-v3 JSONL 和原始 artifact tarball；Jerry 的 `fix_point=False` 是已知 overlap 路径的独立 control，不覆盖默认轨。

```bash
python benchmarks/comprehensive/run_b07_python_projection.py \
  --library py3dbp --time-limit 1 --workers 16
python benchmarks/comprehensive/run_b07_python_projection.py \
  --library py3dbp --time-limit 10 --workers 16
python benchmarks/comprehensive/run_b07_python_projection.py \
  --library jerry --time-limit 1 --workers 16
python benchmarks/comprehensive/run_b07_python_projection.py \
  --library jerry --time-limit 10 --workers 16
python benchmarks/comprehensive/run_b07_python_projection.py \
  --library jerry --time-limit 10 --jerry-fix-point false --workers 16
python benchmarks/comprehensive/run_b07_external_projection.py \
  --library go_bp3d --library rust_unesting \
  --strategy extremepoint --strategy bottomleftfill --strategy ga \
  --strategy brkga --strategy sa --time-limit 1 --time-limit 10 --workers 16
```

运行完成后执行 `python benchmarks/comprehensive/import_baseline.py`、`python benchmarks/comprehensive/analyze.py` 和 `python scripts/verify.py`。`B07-projection-common.csv` 只在共同合法实例上比较八个 projection 实现；`B07-jerry-fixpoint-pairwise.csv` 单独报告 Jerry 参数导致的合法性/质量变化。

四条 PackingSolver protocol-v3 原生轨分别执行 B09、B12、B13、B14、B15 和 B17 的小型边界套件，共 30 条实例记录。fork 的 `box` 与 `boxstacks` 15/15 个行为均符合预期；已打补丁的 upstream `box` 同样 5/5，upstream `boxstacks` 的正常约束均通过，但两个轴荷反例在 solver 内部报错，保留为 `ERROR` 而不是成功或“不可行证明”。`rotation_forbidden` 与 fork 的两个轴荷反例是预期不可行，证书为空且独立 validator 无错误；这类行为通过率只在 `constraint-conformance.csv` 中按 `expected_behavior_pass` 统计，不进入几何质量均值。

运行命令示例：

```bash
.venv/bin/python benchmarks/comprehensive/run_constraint_gauntlet.py \
  --implementation-id packingsolver_fork_box \
  --binary .cache/build-fork/src/box/packingsolver_box \
  --source-root .cache/packingsolver-fork --time-limit 10
```
