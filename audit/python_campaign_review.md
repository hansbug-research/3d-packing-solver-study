# Python THPACK 全量实验审计

审计日期：2026-08-31。本文只审计 `py3dbp 1.1.2` 与 `jerry800416/3D-bin-packing` 固定提交的 THPACK1-9 campaign，不把无法精确表达的姿态约束、格式损坏的源实例或非法装载证书计作有效求解结果。

## 结论摘要

- 固定 ESICUP 数据提交
  `154a8f006a8e72f65d734f2d1e36777f678f31f8` 共解析 762 个实例：
  THPACK1-7 各 100 个、THPACK8 15 个、THPACK9 47 个。
- THPACK9 的 18、19、20 号实例各有一条缺字段记录，因此源数据有效实例为
  759 个。缺失值没有猜测或补零。
- `py3dbp` 只能精确表达 53 个实例，Jerry 能精确表达 87 个实例；以
  “库-实例”计共 140 对。每对运行降序和升序两种件序，共实际求解 280 次。
- 280 次执行中 276 次得到独立验证合法的证书，4 次 Jerry 结果包含物件重叠。
  没有 timeout、worker error 或 THPACK9 漏装结果。
- Jerry 的 4 次非法结果可定位到 `fix_point=True` 吸附坐标后没有重新检查碰撞。
  两套独立 AABB 校验器一致拒绝；同例改为 `fix_point=False` 后 4/4 均合法。
- 上游文档把 `fix_point` 作为解决悬空并提高装箱率的正常功能，API 默认值也是
  `True`；截至审计日，没有找到明确报告“fix-point 吸附后未复检碰撞”的 issue。
  因此这不是姿态映射错误或调用了未公开接口，而是固定提交中可复现、适合提交
  issue 和回归 PR 的缺陷。

## 数据集语义与来源

来源 README 明确区分两类问题：THPACK1-8 是单箱装载，最大化箱体体积利用率，允许物件不装；THPACK9 是多箱装载，要求运输完整批货，最小化使用箱数。物件行的八个字段为：

```text
ID L vertical_L W vertical_W H vertical_H copies
```

每个尺寸后的 0/1 表示“该尺寸是否允许朝竖直方向”，不是三个旋转轴的独立开关。权威语义说明见固定提交的 [THPACK README](https://github.com/ESICUP/datasets/blob/154a8f006a8e72f65d734f2d1e36777f678f31f8/3d_rectangular/thpack/README.txt)。

| 家族 | 实例 | 问题 | 目标 | 源文件 SHA-256 |
|---|---:|---|---|---|
| THPACK1 | 100 | 单箱 knapsack | 最大 packed volume | `d6f0b99b4cc6e51c5753565b175a778a40422dc92cffee3204bf16cc1d23f341` |
| THPACK2 | 100 | 单箱 knapsack | 最大 packed volume | `a31e6400d46926574068524172b1e38495cfd5ad6725f92c58a0af8d92721700` |
| THPACK3 | 100 | 单箱 knapsack | 最大 packed volume | `3359b278aa20a6874d5a63467be6064e8d489014df45f5410a7d85a852ef876d` |
| THPACK4 | 100 | 单箱 knapsack | 最大 packed volume | `9668bae0abd2ad513c6f8bcb5ed8845c4526f08b452f1b7fa9426b6990fbc4d6` |
| THPACK5 | 100 | 单箱 knapsack | 最大 packed volume | `5ece29990ab5034d75728c7ee777379475b16b9218fa9dded17f327de7fa126f` |
| THPACK6 | 100 | 单箱 knapsack | 最大 packed volume | `5c3604cad7a47f7ee38c3c6a4e74c0e846db1eea9ca4ac637106843311abe196` |
| THPACK7 | 100 | 单箱 knapsack | 最大 packed volume | `43fc06212473bbb12ec575678232e444e021642cec7b649be1d43282edec7f2a` |
| THPACK8 | 15 | 单箱 knapsack | 最大 packed volume | `fcda8cfac55592c41095efcab55f362bb3866eb25ad2d7192e6bfdce9629eae2` |
| THPACK9 | 47 | 同构多箱 BPP | 完整装载后最小箱数 | `a4f5e3a748709217cdc749f7d27940f15b9f2a31b3e840e725642237036f82cc` |
| 合计 | 762 | 两种问题，不能混为一个指标 | 见上 | - |

### 源数据损坏

THPACK9 的物理行 107、113、119 分别属于实例 18、19、20，三行内容相同：

```text
3 6 1 9 12 1 20
```

它们只有 7 个字段，无法判断缺失的是尺寸、竖直标志还是 copies。campaign 为 3 个实例乘 2 个库乘 2 种顺序明确写出 12 条 `MALFORMED_SOURCE_EXCLUDED`，没有调用求解器，也没有把这些实例纳入件数、体积、下界或质量统计。

## 姿态能力矩阵

图例：✅ 可无损表达；❌ API 无法表达；⚠️ 可调用但本次发现证书风险。

| 库/版本 | 原生 Python 后端 | `(1,1,1)` 任意维竖直 | `(0,0,1)` 仅原 H 竖直 | `(0,1,1)` 两维可竖直 | 单箱漏装 | 完整多箱 | 本次合法性 |
|---|---|---|---|---|---|---|---|
| `py3dbp 1.1.2` | ✅ | ✅ 六排列 | ❌ 只能放宽成六排列 | ❌ 只能放宽成六排列 | ✅ | ✅ | ✅ 106/106 次执行合法 |
| Jerry `75764a` | ✅ | ✅ `updown=True` | ✅ `updown=False` 两种平面旋转 | ❌ 无对应模式 | ✅ | ✅ | ⚠️ 170/174 合法；4 次 `fix_point` 后重叠 |

Jerry 的固定源码把 `RotationType.ALL` 定义为六种排列，把 `RotationType.Notupdown` 定义为 `WHD/HWD` 两种保持竖直尺寸的平面旋转；官方 [README](https://github.com/jerry800416/3D-bin-packing/blob/75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a/README.md#L44-L45) 也只暴露逐件 `updown` 布尔值。`py3dbp 1.1.2` 对每件总是遍历六种旋转。因此：

- `(1,1,1)` 对两库均为精确映射；
- `(0,0,1)` 仅 Jerry 的 `updown=False` 精确；
- `(0,1,1)` 两库均不能表达，不能用“允许更多旋转”的放宽问题冒充原题结果。

按家族统计的语义可表达实例数如下。THPACK9 的 44 是扣除 3 个损坏实例后的数量。

| 家族 | py3dbp | Jerry | 主要限制 |
|---|---:|---:|---|
| THPACK1 | 9/100 | 22/100 | 大量实例混有 `(0,1,1)` 或 `(0,0,1)` |
| THPACK2 | 0/100 | 5/100 | 同上 |
| THPACK3 | 0/100 | 1/100 | 同上 |
| THPACK4-7 | 0/400 | 0/400 | 均存在无法精确表达的姿态组合 |
| THPACK8 | 0/15 | 15/15 | 全部为 `(0,0,1)` |
| THPACK9 | 44/47 | 44/47 | 全部为 `(1,1,1)`，另有 3 个损坏实例 |
| 合计 | 53/762 | 87/762 | 覆盖率不是求解成功率 |

## 实验协议

| 项目 | 设置 |
|---|---|
| Python | 3.12.1 |
| py3dbp | PyPI wheel `1.1.2` |
| Jerry | Git commit `75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a` |
| 输入顺序 | 体积降序、体积升序各一次 |
| 单次 wall timeout | 60 秒 |
| 单 worker 地址空间 | 2 GiB |
| 数值线程 | OMP/OpenBLAS/MKL/NumExpr 均固定为 1 |
| 哈希随机性 | `PYTHONHASHSEED=0` |
| 数值精度 | `number_of_decimals=3` |
| Jerry | `distribute_items=True, fix_point=True, check_stable=False` |
| THPACK1-8 | 只提供 1 个容器，漏装合法，按 packed volume 评分 |
| THPACK9 | 提供足量同构候选箱，必须完整装载，按 used bins 评分 |

`check_stable=False` 是有意保持 THPACK 的几何问题定义：数据没有承压、支撑面阈值或装载操作约束。官方文档把稳定性检查列为单独的可选功能，并说明启用它需要 `fix_point=True`；关闭稳定性不应允许几何重叠。`fix_point=True` 则是公开参数、API 默认值，且 README 明确宣称它用于消除悬空并提高装箱率，因而本次不是调用了未支持的参数组合。

两库在这些参数下不暴露随机种子；本实验检查的是固定输入顺序下的确定性启发式结果，不是多随机种子分布。

## 覆盖与状态

必须同时报告以下五层口径：

| 层级 | 数量 | 含义 |
|---|---:|---|
| total instances | 762 | 原文件声明并成功切分的实例 |
| source-valid instances | 759 | 没有损坏物件行的实例 |
| semantic-supported library-instance pairs | 140 | 某库可无损表达某实例姿态语义 |
| executed records | 280 | 140 对乘两种件序，实际调用求解器 |
| valid records | 276 | 执行后证书通过独立校验 |

全 3,048 条计划记录的状态为：

| 状态 | 条数 |
|---|---:|
| `FEASIBLE_COMPLETE` | 192 |
| `FEASIBLE_PARTIAL` | 84 |
| `INVALID` | 4 |
| `MALFORMED_SOURCE_EXCLUDED` | 12 |
| `UNSUPPORTED_ORIENTATION_SEMANTICS` | 2,756 |

不存在静默跳过；没有 `TIMEOUT`、`ERROR` 或 THPACK9 `INCOMPLETE`。

## 库级结果

| 库 | 可表达实例 | 执行 | 合法 | 非法 | wall 中位数 | wall p95 | 最大 RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| py3dbp | 53 | 106 | 106 | 0 | 0.283 s | 2.219 s | 26,112 KiB |
| Jerry | 87 | 174 | 170 | 4 | 1.087 s | 12.923 s | 71,836 KiB |

这些运行时不能直接解释为同覆盖集的性能排名：Jerry 多执行了 34 个实例、68 次运行，且家族/件数构成不同。

以降序结果观察可表达子集：

| 家族 | py3dbp 合法/可表达 | py3dbp 中位利用率 | Jerry 合法/可表达 | Jerry 中位利用率 |
|---|---:|---:|---:|---:|
| THPACK1 | 9/9 | 82.14% | 22/22 | 79.78% |
| THPACK2 | 0/0 | - | 5/5 | 81.61% |
| THPACK3 | 0/0 | - | 1/1 | 82.63% |
| THPACK8 | 0/0 | - | 13/15 | 62.81% |

不同库的行不是同一实例集合，不能用上述中位数宣称一库整体优于另一库。真正共同可比且两边都合法的 105 条“实例-顺序”记录中：85 次打平、Jerry 胜 18 次、py3dbp 胜 2 次。THPACK1 与 THPACK9 的分组明细在 `paired-differences.csv`。

### THPACK9

降序且源数据有效的 44 个 THPACK9 实例上：

| 库 | 完整合法 | 非法 | 箱数 min/median/max | 相对体积下界 gap 中位数 |
|---|---:|---:|---|---:|
| py3dbp | 44/44 | 0 | 2 / 14 / 56 | 35.83% |
| Jerry | 43/44 | 1 | 2 / 14 / 56 | 35.29% |

体积下界为 `ceil(total item volume / container volume)`，只是合法下界，不是 known optimum；不能把 gap 写成 optimality gap，也不能把最小箱数相同写成证明最优。

## 输入顺序敏感性

`bigger_first=True` 对应体积降序，`False` 对应升序。

| 库 | 支持实例对 | 两序均合法 | 合法性随顺序变化 | 目标改变 | 降序更好 | 升序更好 | 中位绝对相对变化 | 最大变化 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| py3dbp | 53 | 53 | 0 | 41 | 41 | 0 | 15.38% | 41.03% |
| Jerry | 87 | 83 | 4 | 66 | 62 | 4 | 13.88% | 41.03% |

这说明两者都是明显依赖件序的启发式。生产使用不能只报一次默认顺序；至少要保存输入顺序，并把多种确定性排序或多起点策略纳入评估。

## Jerry 非法证书与根因

主 campaign 的 4 条非法记录如下：

| 实例 | 顺序 | 装入件数 | 箱数 | 重叠对数 |
|---|---|---:|---:|---:|
| THPACK8-001 | 降序 | 100 | 1 | 2 |
| THPACK8-002 | 降序 | 137 | 1 | 28 |
| THPACK8-005 | 升序 | 112 | 1 | 8 |
| THPACK9-035 | 降序 | 84 | 3 | 1 |

campaign validator 检查物件身份、完整性、允许姿态、边界和两两 AABB 重叠。为排除自身坐标轴映射错误，又将完全相同的 placement 交给已有且实现独立的 `benchmarks.validation.validate_aabbs`：四例仍分别得到 2、28、8、1 个重叠，逐对一致。交叉验证原始结果为 `independent-invalid-validation.json`。

THPACK8-002 尤其明显：8 号类型的多个副本被写入完全相同的坐标，形成 8 件之间的 `C(8,2)=28` 个重叠，不是容差边界问题。

固定提交的 [`Bin.putItem`](https://github.com/jerry800416/3D-bin-packing/blob/75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a/py3dbp/main.py#L145-L224) 控制流为：

1. 在原始 `pivot` 上检查边界和 `intersect`；
2. `fix_point=True` 时由 `checkHeight/checkWidth/checkDepth` 改写 `x/y/z`；
3. 没有在吸附后的新位置再次调用 `intersect`；
4. 直接把新 AABB 写入 `fit_items`，并 append 到 `self.items`。

因此先前的碰撞结论对新坐标已经失效。作为因果对照，仅对四个失败配置关闭 `fix_point`，其余输入、顺序和参数不变：

| 实例 | 原结果 | `fix_point=False` | 质量变化 |
|---|---|---|---|
| THPACK8-001 降序 | 100 件，2 重叠 | 100 件，合法 | 件数相同 |
| THPACK8-002 降序 | 137 件，28 重叠 | 133 件，合法 | 少 4 件 |
| THPACK8-005 升序 | 112 件，8 重叠 | 105 件，合法 | 少 7 件 |
| THPACK9-035 降序 | 84 件，3 箱，1 重叠 | 84 件，3 箱，合法 | 箱数相同 |

THPACK8-002/005 的部分“装载提升”实际来自占用同一空间，不能计为算法质量。关闭 `fix_point` 只用于定位，不作为推荐配置：它可能重新引入官方所说的悬空问题。

## 官方文档与 issue 核查

官方 README 的 `Improvement` 部分称 `fix_point` 用于消除悬空并“improved the boxing rate”，示例和 `Packer.pack` 默认值均使用 `True`；文档没有提示吸附后可能发生碰撞，也没有要求必须启用 `check_stable` 才能保证不重叠。

截至 2026-08-31，通过 GitHub Issues API 核查该仓库全部 40 条 issue/PR 条目及公开评论，并对 overlap、intersect、collision、fix point、floating 等关键词复查：

- [issue #4](https://github.com/jerry800416/3D-bin-packing/issues/4) 报告的是
  `fix_point` 下悬空/支撑面不足，2023 年通过新增稳定性规则关闭；不是吸附后 AABB
  重叠复检缺失。
- [issue #33](https://github.com/jerry800416/3D-bin-packing/issues/33) 是用户自定义
  stacking constraint，并贴出相同 `putItem` 流程；它提示吸附后前置判定可能失效，
  但没有给出或确认本次的几何重叠 bug。
- [issue #34](https://github.com/jerry800416/3D-bin-packing/issues/34) 是
  `fix_point=True` 下 600 件运行缓慢，与证书非法不同。

结论应写成“未找到明确覆盖本次根因的上游 issue”，而不是断言整个项目历史上从未有人遇到。当前证据支持新开 issue。

### issue/PR 建议

issue 应附：固定 commit、四个实例/顺序、完整参数、两个 validator 的同一重叠对、THPACK8-002 的同坐标副本，以及 `fix_point=False` 对照。PR 的最小原则是在吸附后的坐标写入 `fit_items` 和 `self.items` 前重新检查边界与所有已放物件；若失败，应恢复原位置并尝试下一旋转/候选点，而不是保留失效的 `fit=True`。

伪代码方向：

```python
item.position = snapped_position
if out_of_bounds(item) or any(intersect(current, item) for current in self.items):
    fit = False
    item.position = valid_item_position
    continue
```

实现时还需确保每次旋转开始前重新把 `item.position` 设为 `pivot`，并增加最小合成回归例与上述四个真实实例回归。此次审计没有代表用户向外部仓库创建 issue 或 PR。

## 数据集与结论边界

经典 THPACK 很适合测量矩形件的几何可行性、体积利用率、同构箱数和件序敏感性，但不包含价格/箱型成本、异构可选箱、重量与载重、逐件承压、支撑/动态稳定、重心、轴荷、禁叠关系、装卸顺序、门/障碍物或在线到货。因此本 campaign 不能证明库支持这些工业约束，也不能用几何 smoke test 替代对应字段齐全的数据集。

## 可复现材料

- runner/parser/validator：`benchmarks/campaign/python_thpack/`
- 3,048 条逐实例记录：`raw/experiments/campaign/python_thpack/records.jsonl`
- 环境、固定提交、源哈希：`raw/experiments/campaign/python_thpack/run-metadata.json`
- 第二校验器结果：`raw/experiments/campaign/python_thpack/independent-invalid-validation.json`
- `fix_point=False` 对照：`raw/experiments/campaign/python_thpack/jerry-fixpoint-diagnostics.jsonl`
- 汇总与逐库/逐家族/逐顺序 CSV：`results/campaign/python_thpack/`

重算命令：

```bash
.venv/bin/python benchmarks/campaign/python_thpack/self_check.py
.venv/bin/python benchmarks/campaign/python_thpack/cross_validate_invalid.py
.venv/bin/python benchmarks/campaign/python_thpack/analyze.py
```
