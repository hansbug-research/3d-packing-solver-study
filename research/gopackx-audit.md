# GoPackX 候选库审计

> 审计日期：2026-09-01。GoPackX 是在协议 v3 的 19 个正式实现冻结后发现的候选库。本文件是独立候选审计，不把它加入当前 `32 x 19` 分母或任何正式排行。

## 来源与可复现性

| 字段 | 值 |
|---|---|
| Repository | <https://github.com/jcoruiz/gopackx> |
| Audited commit | `5e316b83fd9ddf38eb665106234219a86c67f6a1` |
| License | MIT（以该 commit 的 `LICENSE` 为准） |
| Language/runtime | Go 1.22+；本轮使用 Go `1.22.12` linux/amd64 |
| Dependencies | `go.mod` 声明 zero external dependencies；模块 `github.com/jcoruiz/gopackx` |
| Test command | `/tmp/go-toolchain-12212/go/bin/go test ./...` |
| Test result | 全部 package 通过；无失败测试 |
| Test source | `/tmp/gopackx-audit.tifuHW`，由上述 commit checkout |

临时 Go 工具链只放在 `/tmp/go-toolchain-12212`，没有写入项目依赖、构建系统或发布包。

## 能力核验

| 特性 | 证据/结果 | 结论 |
|---|---|---|
| 变尺寸箱型 | `model.Bin` 模板由 TrialPacking/Metaheuristic 无限复制 | ✅ 支持变尺寸选择；不是有限库存 |
| 成本目标 | `BinCost`、`TotalCost`，固定 fixture 选择两个小箱成本 `2.00` 而非大箱 `3.00` | ✅ 有成本目标；⚠️ 仅启发式，未证明全局最优 |
| 有限 copies/库存 | `model.Bin` 没有 copies/max-count 字段，solver 会继续 clone 模板 | ❌ 不支持原生有限库存；B08/B10 需要外层 master |
| 六种旋转 | `AllowedRotations`、`ItemUpright`、`ItemAllowedRotations` | ✅ 离散 6 排列；不表达 24 个面语义或连续任意角 |
| 总重量 | 放置前检查 `RemainingWeight()`；独立 fixture 的超重件未放置 | ✅ 基础 payload 检查通过 |
| fragile | stability-aware engine 会拒绝在 fragile 件上方放置 | ✅ 有规则；需开启对应 stability engine |
| load-bearing | 按重叠面积比例计算上方重量；仅在 stability 开启时作为 placement 检查 | ⚠️ 有近似硬检查；不是一般接触/载荷流模型 |
| support/stability | 支撑比例阈值和四象限 gravity-center 分析 | ⚠️ 支撑比例近似；gravity center 是后验诊断，不是轴荷约束 |
| 多箱完整性 | 固定 THPACK9 instance 1：`70/70` 件，AABB/边界/重叠独立校验通过 | ✅ 可得到完整几何解；质量较弱 |
| 取消/截止时间 | 纳秒 deadline 返回 `context deadline exceeded` | ✅ 可托管；调用方必须保留部分结果和错误状态 |
| 障碍/门洞/卸货/路线 | 源码和公开 API 未发现对应模型 | ❌ |
| 重心/轴荷 | 只有四象限 gravity-center 后验统计 | ❌ 不能替代车辆静力校验 |
| 输出 | `Result` 包含 bin/item 坐标、rotation、stats；无独立 manifest/validator | ⚠️ 需本项目 adapter 和 validator |

## 独立 fixture

审计程序使用固定的 `10 x 10 x 10`/`20 x 20 x 20` 箱型、成本、旋转和超重件，并将 THPACK9 instance 1 转为 20 件 `2 x 6 x 8` 与 50 件 `8 x 4 x 10`。每个输出由外部检查器重算：

- 物品 ID 完整性和 `70/70` 需求完成；
- 旋转后的尺寸与坐标；
- 箱边界；
- 同箱 AABB 严格重叠；
- 箱总重与 `MaxWeight`。

结果：

| Case | Fitted | Bins | Cost | 外部几何/重量校验 | 备注 |
|---|---:|---:|---:|---|---|
| cost-direction | 2/2 | 2 | 2.00 | ✅ | 成本方向 fixture |
| rotation-and-weight | 1/2 | 1 | 0 | ✅ | 超重件被拒绝；直立件保留允许姿态 |
| optimized-cost | 2/2 | 2 | 2.00 | ✅ | Optimize 路径未显示更好成本 |
| THPACK9 instance 1 | 70/70 | 50 | 0 | ✅ | 与 PS fork 的 25 箱和 py3dbp 的 50 箱可作诊断对照 |
| THPACK9 instance 1 + Optimize | 70/70 | 50 | 0 | ✅ | VNS 未改善该分布 |
| cancellation | 返回 `context deadline exceeded` | - | - | - | 取消可传播；不是布局质量结果 |

该结果只证明实现可执行、证书在简单几何规则下合法以及成本/重量 API 的行为。它没有证明 GoPackX 在公开多箱集上的最优性，也不能把 `50` 箱外推为所有实例的排名。

## 与当前协议的映射

在完成 JSON adapter、稳定的独立 validator 和许可证/版本归档后，GoPackX 可以作为以下轨道的候选：

| Benchmark | 可进入的轨道 | 当前状态/原因 |
|---|---|---|
| B04 THPACK9 | `NATIVE` 几何对照 | 建议先跑 44 例；instance 1 已显示完整但质量偏弱 |
| B08/B09 成本 | `COMPOSED` 或 `NATIVE` 成本候选 | 成本 API 存在，但没有有限 copies；需要明确 unlimited-bin 变体 |
| B10 MCLP | `ADAPTER_MISSING` | 无库存/固定箱实例语义 |
| B12 姿态 | `NATIVE`（6 排列/直立） | 24 面语义和连续角不支持 |
| B13 payload | `NATIVE`（基础总重） | 需要独立 validator；不含车辆 tare/轴荷 |
| B14 支撑/上压 | `COMPOSED`/`PROJECTION_ONLY` | 支撑比例和比例分摊近似，不能替代结构载荷模型 |
| B24/B26/B27/B28/B29 | `NATIVE` 工程可靠性候选 | 需要统一 runner、seed、RSS 和 artifact manifest |
| B31 mixed-SKU pallet | `ADAPTER_MISSING` | 没有层型/托盘/完整性模型 |
| B32 online | `ADAPTER_MISSING` | context cancellation 不是增量到货 API |

## 采用建议

GoPackX 的价值在于：纯 Go、MIT、零第三方依赖、成本和基础稳定性 API、可取消调用，适合做轻量 sidecar 或成本候选生成器。它的主要风险是：

1. 变尺寸箱型是无限模板复制，没有有限库存；
2. 成本和 VNS 是启发式，README 的“optimal”不能直接作为最优性声明；
3. THPACK9 instance 1 只达到 50 箱，明显弱于 PackingSolver fork；
4. gravity center 是后验四象限统计，不是轴荷/法规模型；
5. 没有门洞、障碍、路线、卸货和一般支撑载荷流。

因此当前建议为：**保留为候选/对照，不进入生产 shortlist，也不修改正式 19 实现分母**。只有在 44 个 THPACK9、B08/B09 unlimited-cost、B12/B13 以及 B24–B29 统一 runner 通过后，才决定是否扩展协议为第 20 个实现。
