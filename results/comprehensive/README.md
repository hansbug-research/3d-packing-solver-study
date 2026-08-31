# Comprehensive campaign

本目录承载 `benchmark-protocol/3` 的 B01-B32 综合实验。`suite-implementation-plan.jsonl` 与 `coverage.csv` 是 32 个套件乘 19 个实现/算法变体的确定性执行计划；它们不是测试结果。未执行单元固定为 `run_status=NOT_RUN`、`solution_status=NOT_APPLICABLE`，并用 `input_status`、`capability_status` 和 `termination_reason` 区分来源待补、adapter 待实现、问题投影与明确不支持。

生成和检查计划：

```bash
.venv/bin/python benchmarks/comprehensive/build_plan.py
.venv/bin/python benchmarks/comprehensive/build_plan.py --check
```

实际实例级运行将写入 `run-manifest.jsonl`，每条记录遵守 [`run-record.schema.json`](../../benchmarks/comprehensive/run-record.schema.json)。只有 `VALID_COMPLETE` 或原问题允许的 `VALID_PARTIAL` 且通过独立 validator 的记录才能进入后续 `rankings/`；`NATIVE`、`COMPOSED`、`EXACT_MODEL` 以及 `FULL_PROBLEM`、`GEOMETRY_PROJECTION` 分榜。
