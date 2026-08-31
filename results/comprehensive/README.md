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

当前导入 2,078 条已有运行，形成 10/32 个 benchmark、18/19 个实现和 55/608 个计划单元的历史证据，但 `protocol_v3_executed_cells` 仍为 0。这是历史基线，不是综合 campaign 完成声明。其余单元在 `coverage.csv` 中继续显示 `SOURCE_PENDING`、`ADAPTER_MISSING`、`NOT_SUPPORTED` 或 `PLANNED`，不得把其中任何一种改写成已经实测。

现有排行按问题语义拆分：`volume-knapsack-common.csv` 只比较共同实例，`identical-bin-packing.csv` 与 pairwise 表比较 B04 的共同 44 例，`exact-proof.csv` 比较统一模型的证明能力，`constraint-conformance.csv` 保留 hard-case 行为，`resource-summary.csv` 使用独立计时组而不制造跨语言统一速度榜。所有表都是阶段性结果；尚无运行的 B03、B05、B07-B08、B10-B11、B16、B18-B32 不会出现伪造的数值排行。
