# Protocol v3 自审记录

审阅日期：2026-09-01

审阅对象：[`test-protocol.md`](test-protocol.md)、[`suites.json`](../benchmarks/comprehensive/suites.json)、[`implementations.json`](../benchmarks/comprehensive/implementations.json)、[`run-record.schema.json`](../benchmarks/comprehensive/run-record.schema.json)、执行计划和验证脚本。

## 审阅结论

协议可以作为后续全库实验的冻结规范。没有发现会把不支持能力误写成求解结果、把 projection 混入 native、或把非法证书纳入质量排行的 blocking contradiction。当前未完成项是执行进度、来源或 adapter 缺口，不是协议定义缺口；它们必须继续显示为状态记录，不能用已有 THPACK9 数字替代。

## 逐项核对

| 检查项 | 证据 | 结果 |
|---|---|---|
| 套件覆盖 | `test-protocol.md` B01-B32；`test_comprehensive_contracts.py` 断言 32×19=608 | PASS |
| 候选覆盖 | `implementations.json` 固定 19 个 implementation id，包含 fork/upstream、`boxstacks`、Python、Go、Rust 五策略、Skjolber 三策略和四个 exact backend | PASS |
| 状态正交性 | `input_status`、`capability_status`、`run_status`、`solution_status`、`proof_status` 分列，schema 和 `model.validate_run_record` 均拒绝伪造组合 | PASS |
| 原生/组合/投影隔离 | `comparison_track`、`problem_scope`、`adapter` 和 `problem_variant` 必填；分析脚本按 track 和 common-instance set 分榜 | PASS |
| 独立验证 | 协议固定 identity/copies、姿态、边界、碰撞、重量、支撑、轴荷、障碍、卸货、相容性和 objective 重算顺序 | PASS |
| 非法证书处理 | `INVALID_CERTIFICATE`/`CONSTRAINT_VIOLATION` 不进入质量均值；原始 artifact、首个错误和 hash 必须保留 | PASS |
| 预算与计时 | 1/10 s heuristic、20 s exact、单线程、JVM/Rust/BLAS 限制以及 solver/wall/CPU/RSS 分开记录 | PASS |
| 统计与排名 | all-common intersection、nearest-rank、seed 先按实例聚合、hard feasibility 优先、禁止跨问题族总分 | PASS |
| 来源和许可证 | source manifest、commit/version、SHA-256、许可证和 B05/B33/B34 的未就绪状态有明确规则 | PASS |
| 可重算门禁 | `build_plan.py --check`、`analyze.py`、`scripts/verify.py`、pytest、Markdown/link 检查及 `git diff --check` 均列入 ready gate | PASS |

## 已知但非 blocking 的缺口

- B05 MPV 三维输入仍未完成可复现来源审计；保持 `SOURCE_INCOMPLETE/SOURCE_PENDING`。
- B08、B10、B19-B23、B32 仍缺完整公开来源或 full adapter；B31 fixture 来源已冻结，但仍缺 full adapter；projection 不能升级为原题结果。
- B24-B29 的跨库统一运行尚未完成；已有局部专项不代表全套可靠性结果。
- B33 Q4RealBPP（GPLv3）和 B34 3DBPPsi（CC BY 4.0）只能在许可证、canonical converter 和 validator 审计后加入下一版协议。
- 非规则几何、鲁棒/随机装载、软包装物理、连续机器人运动和 2D cutting/nesting 不在 B01-B32 的结论范围内，需另立 suite。

## 审阅后的执行不变量

1. 每个 `benchmark × implementation × variant × budget` 都有计划/状态记录，即使不能运行。
2. 只有输入、语义、预算、validator 版本一致且证书合法的记录进入对应榜单。
3. `NOT_SUPPORTED`、`ADAPTER_MISSING`、`PROJECTION_ONLY`、超时、崩溃和非法证书都是结果，不删除、不补值、不改写为最优。
4. 每轮新增实验先保存 source/input/runner/binary/validator hash，再更新 aggregate、ranking 和 `report.md`。
