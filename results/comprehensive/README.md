# Comprehensive campaign

本目录承载 `benchmark-protocol/3` 的 B01-B32 综合实验。`suite-implementation-plan.jsonl` 与 `coverage-plan.csv` 是 32 个套件乘 19 个实现/算法变体的确定性执行计划；它们不是测试结果。未执行单元固定为 `run_status=NOT_RUN`、`solution_status=NOT_APPLICABLE`，并用 `input_status`、`capability_status` 和 `termination_reason` 区分来源待补、adapter 待实现、问题投影与明确不支持。

生成和检查计划：

```bash
.venv/bin/python benchmarks/comprehensive/build_plan.py
.venv/bin/python benchmarks/comprehensive/build_plan.py --check
.venv/bin/python benchmarks/comprehensive/import_baseline.py
.venv/bin/python benchmarks/comprehensive/analyze.py
```

实际实例级运行写入 `run-manifest.jsonl`，每条记录遵守 [`run-record.schema.json`](../../benchmarks/comprehensive/run-record.schema.json)。`baseline-import-summary.json` 标明哪些记录来自已有 v1/v2 原始归档；新运行仍必须使用协议规定的 `raw/experiments/comprehensive/` 目录。`coverage.csv` 是计划与实际运行合并后的覆盖表。只有 `VALID_COMPLETE` 或原问题允许的 `VALID_PARTIAL` 且通过独立 validator 的记录才能进入 `rankings/`；`NATIVE`、`COMPOSED`、`EXACT_MODEL` 以及 `FULL_PROBLEM`、`GEOMETRY_PROJECTION` 分榜。

当前导入 2,078 条已有运行，并合并 B03 与 B07 protocol v3 的 4,820 条实例记录，形成 12/32 个 benchmark、19 个实现/算法变体和 68/608 个计划单元的有证据记录；其中 55 个单元仍只有历史基线。这不是综合 campaign 完成声明。其余单元在 `coverage.csv` 中继续显示 `SOURCE_PENDING`、`ADAPTER_MISSING`、`NOT_SUPPORTED` 或 `PLANNED`，不得把其中任何一种改写成已经实测。

现有排行按问题语义拆分：`volume-knapsack-common.csv` 只比较共同实例，`B07-version-pairwise.csv` 比较 fork/upstream 的相同 BR 桶和预算，`identical-bin-packing.csv` 与 pairwise 表比较 B04 的共同 44 例，`profit-knapsack.csv` 分开比较 B03 的固定姿态/全旋转投影，`exact-proof.csv` 比较统一模型的证明能力，`constraint-conformance.csv` 保留 hard-case 行为，`resource-summary.csv` 使用独立计时组而不制造跨语言统一速度榜。所有表都是阶段性结果；尚无运行的 B05、B08、B10-B11、B16、B18-B32 不会出现伪造的数值排行。

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
