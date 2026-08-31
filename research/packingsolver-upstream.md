# PackingSolver 上游缺陷核查

核查快照：2026-08-31，仓库 `fontanf/packingsolver`，提交
`367ebfdaad11424ded3696b7dae799a30c1375d0`（本地短 hash `367ebfd`）。结论是：
**原始调用方式正确，`box` 和 `boxstacks` 的异构成本目标存在上游缺失分支；该缺陷已向上游提交 issue [#536](https://github.com/fontanf/packingsolver/issues/536) 和 PR [#540](https://github.com/fontanf/packingsolver/pull/540)，截至 2026-08-31 均为 open、尚未合并。**

## 证据链

官方 README 的 box solver 目标列表包含 Knapsack、Bin packing、Open dimension X/Y/Z
和 Variable-sized bin packing，并说明允许 6 种轴向旋转与箱总重量。boxstacks README
还列出 Variable-sized bin packing、6 种旋转、nesting height、最大堆叠数、最大上方重量、
箱总重量、stack density、半挂中/后轴荷和 increasing X/Y 卸货约束。CLI 的
`--objective` 解析器接受 `variable-sized-bin-packing`，源码的 `Objective` 枚举也有
`VariableSizedBinPacking`。

优化控制流并非文档残留：`src/box/optimize.cpp` 和 `src/boxstacks/optimize.cpp`
会为该目标设置一维松弛/算法选择，并把 box 子问题交给 boxstacks。对照
`src/rectangle/solution.cpp:224-226` 和 `src/onedimensional/solution.cpp`，同一目标
已经用 `strictly_lesser_cost(solution.cost(), cost())` 比较方案。

实际缺失位置是：

```text
src/box/solution.cpp:166-199
src/boxstacks/solution.cpp:294-323
```

两个 `Solution::operator<` 的 switch 都从 `Objective::Feasibility` 直接落入 default，
因此抛出 `solution "...::Solution" does not support objective
"VariableSizedBinPacking"`。这不是输入 CSV、目标拼写或 Python binding 的问题。

## 原始复现

使用官方 CSV 形式（本仓库 `benchmarks/data/packingsolver/heterogeneous_*`）：

```bash
packingsolver_box \
  --items heterogeneous_items.csv --bins heterogeneous_bins.csv \
  --objective variable-sized-bin-packing \
  --certificate solution.csv
```

`box` 与 `boxstacks` 都以非零状态退出，且不生成 certificate。未经修复时，`box`
直接报 `box::Solution::operator<`；`boxstacks` 会先调用内部 box bound，因此最先看到的
同样是 `box::Solution::operator<`。只修 box、保留 boxstacks 原样的分段构建会继续报
`boxstacks::Solution::operator<`，由此确认两处都必须修复。输入是两个 `6x5x5`、成本
7、各 1 份，和一个 `12x5x5`、成本 10、1 份；
两件 `6x5x5` 物品应选成本 10 的大箱，而不是因比较阶段异常退出。

## 最小修复候选

分别在两个 switch 的 `Objective::Feasibility` 后加入：

```cpp
case Objective::VariableSizedBinPacking: {
    return strictly_lesser_cost(solution.cost(), cost());
}
```

这与 rectangle/onedimensional 已有实现一致，保留 infeasible/feasible 排序和成本严格
比较语义，不改变搜索、bound 或证书格式。

## 本地验证

官方二进制使用默认 LP 后端和显式 `--linear-programming-solver highs` 各重复 5 次：
`box` 10/10 次、`boxstacks` 10/10 次均返回 1、无证书，排除了 seed、超时和 LP 后端
选择的影响。在隔离的完整源码副本中用 CMake 构建 `box` 和 `boxstacks`，显式启用并
选择 HiGHS 后，完整补丁各重复 5 次均成功。另有一个不属于本 issue 的配置问题：禁用
HiGHS 时，`src/rectangle/conservative_scales.cpp` 的 `solution` 只在
`#ifdef HIGHS_FOUND` 内声明，后续代码仍引用它；本次最初的 no-HiGHS 验证构建将声明
移出条件块作为 workaround。这个改动不应混入成本比较 PR。最小复现结果如下：

| 程序 | 返回码 | 结果 | certificate | 独立 AABB 校验 |
|---|---:|---|---|---|
| patched `box` | 0 | 1 个大箱，成本 10，2/2 件 | 有 | 通过 |
| patched `boxstacks` | 0 | 1 个大箱，成本 10，2/2 件 | 有 | 通过 |

验证二进制 SHA-256：patched `box`
`a1257fca24e3741aacd1686348e54cd0dc8441364a31081b04d0a970b9369c47`；patched
`boxstacks` `6b940a4660d25479058f01b6d3d873855bec9d5158097b67493b4baabdaa1a11`。

额外回归覆盖：小箱/大箱成本方向、有限 copies、box 与 boxstacks 两条路径；公开
THPACK9 instance 1 的普通 bin-packing 也完成 70 件、25 箱，证书通过独立几何校验。
结果文件见 `results/raw/patched-highs/` 和 `results/public/`。

成本反向回归把小箱成本改为 5（两份）、大箱改为 20（1 份），两种程序均选择
2 个小箱、总成本 10；这排除了“只要能运行但比较方向反了”的假修复。

## Issue/PR 状态

标题建议：`box and boxstacks throw for variable-sized-bin-packing objective`。

issue [#536](https://github.com/fontanf/packingsolver/issues/536) 的正文包含上游提交 SHA、最小
CSV、完整命令、实际 stderr、期望行为、两个 `operator<` 路径、对照 rectangle 实现、patch
diff 和 `box`/`boxstacks` 回归测试；对应 PR [#540](https://github.com/fontanf/packingsolver/pull/540)
增加了两类 solution-comparison 测试。与同一轮审计发现的其他问题分别对应 issue/PR：

| 问题 | Issue | PR | 截至 2026-08-31 |
|---|---|---|---|
| 异构成本 comparator 漏分支 | [#536](https://github.com/fontanf/packingsolver/issues/536) | [#540](https://github.com/fontanf/packingsolver/pull/540) | open，未合并 |
| 轴荷 repair 越界读 | [#537](https://github.com/fontanf/packingsolver/issues/537) | [#541](https://github.com/fontanf/packingsolver/pull/541) | open，未合并 |
| 关闭 HiGHS 时构建失败 | [#538](https://github.com/fontanf/packingsolver/issues/538) | [#542](https://github.com/fontanf/packingsolver/pull/542) | open，未合并 |
| 退化卡车几何导致静默空解 | [#539](https://github.com/fontanf/packingsolver/issues/539) | [#543](https://github.com/fontanf/packingsolver/pull/543) | open，未合并 |

PR #540 的评论报告 `ctest` 从 596 增至 598 个通过；#541 的修复使越界复现从 3/3
崩溃变成 3/3 正常退出；#542 是编译修复但 no-HiGHS 的运行时策略仍待决定；#543
只修复退化几何的 axle 计算并保留已有完整几何行为。此前检索到的 #471/#521/#515/#524
涉及 bound、column generation 和终止逻辑，但没有覆盖 comparator 漏分支。

当前 `test/boxstacks/boxstacks_test.cpp::BinCopies` 虽设置了
`VariableSizedBinPacking`，但只检查 copies，从未调用两个 solution 之间的比较；
`test/box/box_test.cpp` 的 optimize 测试则整体被注释。最小单元回归应直接构造成本 14
和成本 10 的两个 feasible solution，断言低成本 solution 的比较方向，而集成回归再运行
上述 CSV，检查返回码、成本、件数和 certificate。

在确认上游维护者接受前，不应直接把本地 patch 当作官方 release；生产端应 pin 源提交或
二进制 SHA-256，子进程隔离，且保留异构成本和轴荷边界回归门禁。
