# 商业求解器历史记录说明

`gurobi_historical.json` 和 `cplex_historical.json` 是早期受限许可环境留下的结构化记录。复核时发现两份记录把模型写成“9 个 `5x5x5` 立方体、2 个 `10x10x10` 箱”，但同时报告目标值和 bound 为 8；该模型的箱数目标不可能超过候选箱数 2，因此记录无法作为有效求解器结果。

文件保留原始报告值于 `reported_*` 字段，并将规范 `status` 标为 `INVALID_HISTORICAL_INCONSISTENT_FIXTURE`。它们不进入正式 benchmark 表，也不被解释为 Gurobi/CPLEX 当前可复跑结果。当前环境没有 `gurobipy`、`cplex` 或对应运行时许可；重新获得许可后，应使用 `benchmarks/benchmark_gurobi.py` 或 `benchmarks/benchmark_cplex.py`，固定输入和资源限制，归档新的 stdout、stderr、退出码和模型摘要。
