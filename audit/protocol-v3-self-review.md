# Protocol v3 自审记录

审查日期：2026-09-01

审查对象：`research/test-protocol.md`、`benchmarks/comprehensive/run-record.schema.json`、`benchmarks/comprehensive/suites.json`、`benchmarks/comprehensive/implementations.json`、`results/comprehensive/README.md` 及其生成脚本。

## 审查结论

协议设计本身没有 blocking finding，可以作为后续 runner 和结果聚合的执行基线。实验覆盖尚未完成，不把下方 execution gap 误报为协议通过；在所有 gap 关闭前，仓库仍不能宣布最终技术选型 ready。

## 规则一致性检查

| 检查项 | 结果 | 证据/说明 |
|---|---|---|
| B01-B32 是否逐一登记 | PASS | `suites.json` 由 `model.validate_catalogs` 检查恰好 32 个 suite |
| 实现是否覆盖全部 capability profile | PASS | `implementations.json` 的 19 个实现覆盖 catalog 中每个 profile |
| 计划是否是 32×19 笛卡尔积 | PASS | `build_plan.py` 与 `test_comprehensive_contracts.py` 断言 608 cells |
| 状态是否正交且有枚举 | PASS | schema 和协议分别约束 input/capability/run/solution/proof 五维 |
| native/composed/projection/exact 是否分轨 | PASS | `comparison_track`、`problem_scope` 和排行文件分开生成 |
| 原始输出与 validator 是否隔离 | PASS | 协议要求独立 validator；历史 Jerry/Go/Rust/PackingSolver 反例有回归 |
| hard constraint 是否先于 objective | PASS | B12-B18 的词典序门禁和 invalid 排除规则已写明 |
| time limit 是否允许合法 incumbent | PASS | `TIME_LIMIT` 与 `VALID_*` 可并存，proof 单独记录 |
| seed/order/repetition 是否防止伪样本 | PASS | 固定顺序集合、至少五个 seed、实例内先聚合 |
| 跨语言性能是否避免误排 | PASS | timing group、warm-up、生命周期和边界规则已定义 |
| source/projection/license 是否可追溯 | PASS | canonical provenance、输入 hash、projection_of 和 source 状态均要求记录 |
| known bug 是否可升级 | PASS | 失败分类要求最小复现、回归、issue/PR 和不升级结论 |
| report 是否需要保留未完成缺口 | PASS | ready gate 明确禁止用“未发现错误”替代证据 |

## 当前 execution gap

以下是实验进度而非协议缺陷，必须在后续波次关闭：B05-B11 全库统一 adapter；B12-B18 的跨库 conformance；Alonso/VRPTW-CLP full/projection；B22 irregular 边界记录；B23 脱敏真实订单；B24-B29 跨库可靠性；B30 shelf adapter；B31 生成器联合约束；B32 online adapter。当前聚合是 `12/32` benchmark 实际执行、`32/32` benchmark 有状态记录、`549/608` cells 有证据，其中 `465` 个 cell 仅为 status-only，`65` 个 cell 已执行 protocol-v3；新增的 1,524 条 B01/B02/B04 native revalidation 仍是已归档 certificate 的协议化重验，另有 116 条 Wave-1 fresh exact/Skjolber 记录，二者都不能写成全量完成。

## 本次自审命令

```text
.venv/bin/python benchmarks/comprehensive/build_plan.py --check
.venv/bin/python benchmarks/comprehensive/analyze.py --check
.venv/bin/python scripts/verify.py
.venv/bin/python scripts/check_markdown.py
.venv/bin/python scripts/check_links.py
.venv/bin/python -m pytest -q
git diff --check
```

协议变更提交前必须再次执行上面命令，并由后续每一个 benchmark campaign 的结果摘要引用本文件和协议版本。
