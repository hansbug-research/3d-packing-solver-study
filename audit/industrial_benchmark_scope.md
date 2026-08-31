# Alonso 与 BAYTP 工业 benchmark 范围审计

审计日期：2026-08-31。本文件回答三个问题：公开数据到底描述什么问题、现有候选实现能否无损表达原问题、哪些实验可以运行且不会把降级后的普通几何装箱冒充成原 benchmark。本文不包含新的求解分数；统计由 [`benchmarks/audit_industrial_datasets.py`](../benchmarks/audit_industrial_datasets.py) 从固定来源重算。

## 结论

- Alonso 2019 与 Alonso 2020 在固定 ESICUP 提交中自包含，分别有 111 和 107 个实例；本轮已经完成格式、字段分布和需求恒等式审计，但没有运行完整优化 benchmark。
- 两套 Alonso 数据都不是普通 3D bin packing。原问题包含产品、层、托盘堆和车辆之间的联合决策，还包含交付日期、重量/轴荷、重心和动态稳定等约束。当前五种实现均不能无损表达完整问题，状态应为 `NOT_SUPPORTED`。
- 固定 ESICUP 提交中的 BAYTP 只有 `README.txt`、`baytp1.txt` 和 `baytp2.txt`，缺少 README 明确要求的共享 `products` 与 `shelves` 文件。因此该快照内的 BAYTP 状态是 `ESICUP_SNAPSHOT_INCOMPLETE` 和 `NOT_RUN`。
- BAYTP 缺失文件仍可从官方 OR-Library 公开地址恢复；本审计核对了内容哈希和统计，但没有把临时下载物写进仓库，也没有把它们视为已经固定归档的数据依赖。
- 可以运行的普通 packer 实验必须命名为 `RELAXED_GEOMETRIC_SUBPROBLEM`，并显式列出外部固定或删除的原始决策。此类结果不能进入完整 Alonso/BAYTP 排名。

## 状态口径

| 标记 | 含义 |
|---|---|
| ✅ | 当前实现有直接、可验证且语义相符的能力 |
| ⚠️ | 只有部分能力、扩展点或需要另建模型；不等于支持完整原问题 |
| ❌ | 当前实现缺少该问题能力 |
| ⛔ | 数据依赖不完整或前置条件未满足，本轮未运行 |
| `NOT_SUPPORTED` | 无法不丢原始字段和约束地映射到当前实现 |
| `NOT_RUN` | 没有产生该 benchmark 的求解结果；不能用 smoke test 代替 |

## 固定来源

ESICUP 数据统一固定到 commit `154a8f006a8e72f65d734f2d1e36777f678f31f8`，与 `sources/manifest.csv` 的 S01、S02、S04、S05 和 `raw/provenance.json` 一致。

| 对象 | 固定来源 | 用途与状态 |
|---|---|---|
| Alonso 2019 数据说明 | [ESICUP readme.txt](https://github.com/ESICUP/datasets/blob/154a8f006a8e72f65d734f2d1e36777f678f31f8/3d_rectangular/alonso_2019/readme.txt) | 字段、层/托盘/车辆语义；固定提交内自包含 |
| Alonso 2019 论文 | [DOI 10.1016/j.cie.2018.11.012](https://doi.org/10.1016/j.cie.2018.11.012) | 完整问题、约束与实验背景 |
| Alonso 2020 数据说明 | [ESICUP readme.txt](https://github.com/ESICUP/datasets/blob/154a8f006a8e72f65d734f2d1e36777f678f31f8/3d_rectangular/alonso_2020/readme.txt) | stock/case/rest 需求字段；固定提交内自包含 |
| Alonso 2020 论文 | [DOI 10.1007/s10288-018-0397-z](https://doi.org/10.1007/s10288-018-0397-z) | GRASP 和 practical constraints；卷期年份 2020、online 2019 |
| BAYTP 数据说明 | [ESICUP README.txt](https://github.com/ESICUP/datasets/blob/154a8f006a8e72f65d734f2d1e36777f678f31f8/3d_rectangular/baytp/README.txt) | 明确要求 bay、products、shelves 三类文件；固定提交缺后两类 |
| BAYTP 论文 | [DOI 10.1057/palgrave.jors.2601130](https://doi.org/10.1057/palgrave.jors.2601130) | *Placing boxes on shelves: a case study*，原问题和主目标 |
| BAYTP products 恢复源 | [OR-Library products.txt](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/products.txt) | 可访问但未归档；SHA-256 `f814947ad7f2cfe2bf43fa3a5ee8d087ecf35f442376a25afa50f72f6147e52e` |
| BAYTP shelves 恢复源 | [OR-Library shelves.txt](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/shelves.txt) | 可访问但未归档；SHA-256 `914231bd5a53ad890a4e9817e7381d967658bffed4989343eabbc623a845cef7` |

OR-Library 两个 URL 没有 commit 标识，因此可复现身份由下载 URL、访问日期和内容 SHA-256 共同界定。若未来下载哈希变化，统计脚本会拒绝继续，不能静默把新内容混入本次结果。

## Alonso 2019

### 数据规模

| Section | 总行数 | 每实例 min / median / max |
|---|---:|---:|
| products | 4,455 | 3 / 24 / 398 |
| layers | 4,455 | 3 / 24 / 398 |
| pallets | 111 | 1 / 1 / 1 |
| trucks | 111 | 1 / 1 / 1 |

111 个实例的总 product demand 为 3,025,923。全部文件均具有 `products → layers → pallets → trucks` 四段，字段数和段内声明行数一致。

### 字段与实测分布

| 层级 | 字段 |
|---|---|
| product | `id, delivery_day, demand, W, L, H, weight, rotation_X, rotation_Y, rotation_Z, stacking_group, always_top, always_bottom, layer_id` |
| layer | `id, W, L, H, weight, rotation_Z, items_per_layer, max_layers_per_stack` |
| pallet | `id, W, L, H, weight` |
| truck | `id, W, L, H, max_weight, axle_1_position, axle_2_position, axle_1_max_weight, axle_2_max_weight` |

| 字段 | 实测值 |
|---|---|
| `delivery_day` | 0 / 1 / 2：1,484 / 1,487 / 1,484 行 |
| product `rotation_XYZ` | `111`：4,455 行 |
| `stacking_group` | 1：4,455 行 |
| `always_top` / `always_bottom` | 0 / 0：各 4,455 行 |
| layer `rotation_Z` | 0：4,455 行 |

当前实例中某些字段取值退化为常数，不代表模型语义可以删除。尤其是日期、层组成、最大层堆数量、托盘和车辆轴荷仍是数据合同的一部分；一个只读取尺寸和 demand 的 adapter 已经发生语义丢失。

### 原问题与评价口径

论文和数据说明描述 products → layers → pallet stacks → trucks 的多层决策。除三维几何和不重叠外，完整问题还涉及车辆总重量与两轴载荷、货物重心、避免空隙和限制相邻托盘高差的动态稳定、交付日期，以及 heavy-load 布局扩展。

| 维度 | 完整 benchmark 应报告的量 |
|---|---|
| 主目标 | 使用车辆数；必须同时声明需求是否全部满足 |
| 原始可行性 | 产品/层/托盘数量守恒、几何不重叠和边界、日期匹配 |
| 车辆工程约束 | 总重量、两轴载荷、重心限制 |
| 稳定性 | 原模型中的空隙和相邻托盘高度差等违规数/幅度 |
| 算法证据 | runtime、终止状态、best bound 和 optimality gap；启发式无 bound 时明确写 `N/A` |

单独报告体积利用率不能衡量该问题，也不能证明车辆数目标或工程约束可行。

## Alonso 2020

### 数据规模

| Section | 总行数 | 每实例 min / median / max |
|---|---:|---:|
| products | 1,483 | 1 / 8 / 142 |
| layers | 1,483 | 1 / 8 / 142 |
| pallets | 107 | 1 / 1 / 1 |
| trucks | 107 | 1 / 1 / 1 |

107 个实例的总 demand 为 2,936,014。每个实例含一个 pallet type 和一个 truck type。

### 需求恒等式与分布

product 行有 25 列。前 14 列依次包含 id、README 所称的 delivery-day 列、总需求、stock 总需求、case 总需求，以及 rest/stock/case 在 day 1、2、3 的分日需求；之后是尺寸、重量、X/Y/Z 旋转、stacking group、top/bottom 和 layer id。

统计脚本逐行验证以下恒等式，107 个实例全部通过：

```text
total = stock_total + case_total + rest_day1 + rest_day2 + rest_day3
stock_total = stock_day1 + stock_day2 + stock_day3
case_total = case_day1 + case_day2 + case_day3
```

| 汇总维度 | 数量 |
|---|---:|
| stock | 1,269,261 |
| case | 1,653,455 |
| rest | 13,298 |
| day 1 | 1,002,734 |
| day 2 | 939,653 |
| day 3 | 993,627 |

| 字段 | 实测值 |
|---|---|
| product `rotation_XYZ` | `000` / `100` / `111`：22 / 477 / 984 行 |
| `stacking_group` | 1：1,483 行 |
| `always_top` / `always_bottom` | 0 / 0：各 1,483 行 |
| layer `rotation_Z` | 0：1,483 行 |

### 文档与文件冲突

README 把 product 第 2 列描述为 `delivery day (0,1,2)`，但文件中的实值为 1、2、3、4，计数分别为 219、8、1,253、3。现有公开说明不足以证明这些值应如何解释；本审计保留原值并标记 `DOCUMENT_DATA_SEMANTIC_MISMATCH`，不得擅自减一、合并或把 4 当作异常值删除。

### 原问题与评价口径

原题要求先建立 homogeneous stock pallets，再建立每层为单一产品的 case pallets，最后用剩余产品建立 strongly heterogeneous rest pallets，然后把托盘装入车辆。几何、重量/轴荷、重心、动态稳定和交付日期均属于完整问题。

评价口径应在 Alonso 2019 的车辆数、完整性、可行性、工程约束、runtime/bound/gap 基础上，再报告 stock/case/rest 三类需求守恒与托盘构造合法性。任何预先把三类托盘物化的实验都已经固定了原问题中的决策变量，只能称降级子问题。

## BAYTP

### ESICUP 快照完整性

| 检查 | 结果 |
|---|---|
| `README.txt` | ✅ 存在 |
| `baytp1.txt` | ✅ 存在；350 行，1 种不同 bay 记录，均为 `1200 2400 650 3000` |
| `baytp2.txt` | ✅ 存在；350 行，10 种不同 bay 记录 |
| README 要求的共享 `products` | ❌ 缺失 |
| README 要求的共享 `shelves` | ❌ 缺失 |
| 完整 benchmark 可运行 | ⛔ `ESICUP_SNAPSHOT_INCOMPLETE / NOT_RUN` |

bay 行字段是 `width, height, depth, available_height`，并且 bay 必须按文件给定顺序使用。缺少产品和候选 shelf 后，只有空的 bay 几何，无法构造目标函数或判断可行性。

### 官方 OR-Library 恢复文件

| 对象 | 实测统计 |
|---|---:|
| product rows | 6,000 |
| product families | 67 |
| total quantity | 17,793 |
| quantity min / max | 1 / 5 |
| candidate shelf rows | 49 |

product 字段为 `family, quantity, L, W, H`。README 允许所有正交方向，并禁止物品越过 shelf。shelf 字段为 `shelf_number, thickness, position, top_gap, left_gap, inter_gap, right_gap`；这些厚度、位置和间隙会改变可用空间，不能在转换时丢弃。

### 原问题与评价口径

BAYTP 的目标是最小化使用的 stockroom space，而不是单个 shelf compartment 的体积利用率。完整评测至少要报告 stockroom space 或 bay/shelf 使用、17,793 件需求是否全部满足、overhang/gap/sequence 违规、runtime，以及有证明型求解器时的 bound/gap。

## 候选实现能力矩阵

本节分别列出 PackingSolver 官方 `367ebfdaad11424ded3696b7dae799a30c1375d0` 和已整合 #540–#543 的 HansBug fork `d953148b8f710c06fa6c410949b7272f9e36327b`，并同时覆盖 py3dbp `1.1.2`、Jerry `75764a2b8a5c8e0a6713a4f672c0a8ff81b1107a`、Skjolber `c73d52190c029a14e64f1bbdd2ea70452d1eb83d` 及当前 `benchmarks/campaign/exact_suite.py`。⚠️ 表示局部能力或扩展点，不得读作完整支持。

| 实现 | 姿态白名单 | 总重量 | 层构造 | 托盘构造 | stock/case/rest | 硬堆叠/承压 | 车辆轴荷 | 原题重心 | 动态稳定 | 日期/卸货 | shelf 厚度/gap | bay 顺序 | 原题目标 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PackingSolver 官方 `367ebf` `boxstacks` | ✅ 六姿态白名单 | ✅ | ❌ | ❌ | ❌ | ⚠️ stackability、堆数、上方重量 | ⚠️ 半挂字段存在，但轴荷修复路径有 #537 | ❌ | ⚠️ 通用堆叠约束，不等于相邻高差/空隙模型 | ⚠️ 部分 unloading，不等于日期联合模型 | ❌ | ❌ | ❌ |
| PackingSolver fixed `d953148b` `boxstacks` | ✅ 六姿态白名单 | ✅ | ❌ | ❌ | ❌ | ✅ 上方重量/堆数专项通过 | ✅ 正常、边界、不可行轴荷专项通过 | ❌ | ⚠️ 已测堆叠约束仍不等于原题动态稳定 | ⚠️ 两种 unloading 专项通过，不等于日期联合模型 | ❌ | ❌ | ❌ |
| py3dbp 1.1.2 | ⚠️ 固定遍历六姿态，不能表达 `000/100` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Jerry `75764a` | ⚠️ `updown` 只有六姿态/两种平面姿态两档 | ✅ | ❌ | ❌ | ❌ | ⚠️ `level/loadbear` 与排序逻辑，不是完整硬模型 | ❌ | ❌ | ⚠️ 可选支撑检查不等于原题动态稳定，且 `fix_point` 有重叠 bug | ❌ | ❌ | ❌ | ❌ |
| Skjolber `c73d521` | ✅ 可定义 rotation surfaces | ✅ | ❌ | ❌ | ❌ | ⚠️ control/constraint 扩展点，需自行实现 | ❌ | ❌ | ⚠️ 扩展点，未实现原题模型 | ❌ | ⚠️ obstacle/control 可扩展，不是 shelf 求解器 | ❌ | ❌ |
| 当前 `exact_suite.py` | ✅ 任意离散姿态 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ 只有候选箱成本/最少成本，不是原题目标 |

PackingSolver fixed fork 的 [`packingsolver-boxstacks.json`](../results/campaign/packingsolver-boxstacks.json) 记录 9/9 专项 `PASS`：异构成本、最大上方重量、最大堆数、嵌套高度、正常轴荷、边界轴荷回归、不可行轴荷，以及两种 unloading。轴荷边界与不可行例按预期返回不完整装载，证书校验无错误；这足以把 fixed fork 的已测轴荷和堆叠单元标为 ✅，但不补齐 Alonso 的层/托盘联合构造、重心、日期和动态稳定，也不补齐 BAYTP 的 shelf/bay 模型。Skjolber 的 control/obstacle API 和通用 MIP/CP 的可建模性仍只是开发入口；没有已经实现和验证的模型时，不能标 ✅。

## 数据集 × 实现状态

| 数据集 | PackingSolver 官方 `367ebf` | PackingSolver fixed `d953148b` | py3dbp | Jerry | Skjolber | 当前 exact suite |
|---|---|---|---|---|---|---|
| Alonso 2019 | ⚠️ `NOT_SUPPORTED`：缺层/托盘联合构造、日期类别、完整重心和动态稳定，另有固定版本问题 | ⚠️ `NOT_SUPPORTED`：4 个补丁和 9 个专项通过，但工业语义缺口不变 | ❌ `NOT_SUPPORTED`：缺层/托盘、逐件姿态白名单、轴荷、重心、稳定、日期和原目标 | ❌ `NOT_SUPPORTED`：缺硬承压、层/托盘、姿态白名单、轴荷、重心、日期；另有 `fix_point` bug | ⚠️ `NOT_SUPPORTED`：只有几何/重量及扩展点，没有现成工业联合模型 | ❌ `NOT_SUPPORTED`：需要新增层/托盘、时间、堆叠、轴荷、重心和稳定模型 |
| Alonso 2020 | ⚠️ `NOT_SUPPORTED`：同上，另缺 stock/case/rest 托盘物化决策 | ⚠️ `NOT_SUPPORTED`：软件缺陷已修，仍缺原问题联合模型 | ❌ `NOT_SUPPORTED`：同上 | ❌ `NOT_SUPPORTED`：同上 | ⚠️ `NOT_SUPPORTED`：同上 | ❌ `NOT_SUPPORTED`：同上，需要新模型而非 adapter |
| BAYTP | ⛔ `NOT_RUN`；数据不完整，补源后仍缺 shelf/bay 联合模型 | ⛔ `NOT_RUN`；补丁不提供 shelf/bay 模型 | ⛔ `NOT_RUN`；补源后仍 `NOT_SUPPORTED` | ⛔ `NOT_RUN`；补源后仍 `NOT_SUPPORTED` | ⛔ `NOT_RUN`；扩展点不等于 shelf/bay 模型 | ⛔ `NOT_RUN`；需新增 shelf 选择、gap、顺序和 stockroom-space 目标 |

## 可运行的严格降级子问题

### Alonso 2019

外部固定 layer 组成、pallet 构造、pallet 的日期归属和 truck candidates 后，可以把已经物化的 pallet 当作刚性长方体，只测 pallet-to-truck 的 `RELAXED_GEOMETRIC_SUBPROBLEM`。PackingSolver 还可在明确版本和 certificate 验证边界的前提下测总重量及部分轴荷；所有被固定的原始决策都必须写入实验 manifest。

### Alonso 2020

必须先在 solver 外固定 stock/case/rest 三类 pallet 的物化结果、日期和车辆候选，之后才可以运行 truck-loading 几何子问题。该实验不能比较三类托盘构造算法，也不能引用原论文目标声称端到端能力。

### BAYTP

先按本文件哈希固定恢复 `products` 和 `shelves`，再外部固定 shelf 选择与位置，才可以把每个 shelf compartment 当作独立容器做几何 packing。该转换删除了 shelf 选择、bay 使用顺序和最小 stockroom-space 目标，因此只能作为局部几何回归，不是 BAYTP benchmark。

## 统计复现

只重算固定 ESICUP 快照中的统计：

```bash
git clone https://github.com/ESICUP/datasets.git .cache/esicup-datasets
git -C .cache/esicup-datasets checkout --detach 154a8f006a8e72f65d734f2d1e36777f678f31f8
python benchmarks/audit_industrial_datasets.py \
  --esicup-root .cache/esicup-datasets
```

同时核对官方 OR-Library 恢复文件：

```bash
BENCH_TMP="$(mktemp -d)"
curl -fsSLo "$BENCH_TMP/products.txt" \
  https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/products.txt
curl -fsSLo "$BENCH_TMP/shelves.txt" \
  https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/shelves.txt
sha256sum "$BENCH_TMP/products.txt" "$BENCH_TMP/shelves.txt"
python benchmarks/audit_industrial_datasets.py \
  --esicup-root .cache/esicup-datasets \
  --baytp-products "$BENCH_TMP/products.txt" \
  --baytp-shelves "$BENCH_TMP/shelves.txt"
```

脚本会校验 ESICUP `HEAD`、四段声明行数、字段宽度、Alonso 2020 三组需求恒等式和两个 BAYTP 恢复文件的 SHA-256，然后输出机器可读 JSON。本轮完整输出归档在 [`results/campaign/industrial-dataset-audit.json`](../results/campaign/industrial-dataset-audit.json)。脚本只做数据审计，不调用求解器，也不会生成完整 benchmark 分数。

## 最终运行声明

| 数据集 | 公开状态 | 本轮动作 | 求解状态 |
|---|---|---|---|
| Alonso 2019 | 固定 ESICUP commit 自包含 | 已解析、统计和字段审计 | `NOT_SUPPORTED / NOT_RUN`（完整问题） |
| Alonso 2020 | 固定 ESICUP commit 自包含；第 2 列存在文档/文件冲突 | 已解析、验证需求恒等式和字段分布 | `NOT_SUPPORTED / NOT_RUN`（完整问题） |
| BAYTP | ESICUP 快照不完整；官方 OR-Library 可按哈希恢复 | 已核对恢复文件，未纳入仓库数据归档 | `ESICUP_SNAPSHOT_INCOMPLETE / NOT_RUN` |

后续若实现新模型，进入完整排名的最低条件是：逐字段说明映射、对所有原始约束生成可独立验证的 certificate、报告主目标与完整性、保留固定数据 provenance，并把任何预处理固定的决策从完整 benchmark 中剔除。
