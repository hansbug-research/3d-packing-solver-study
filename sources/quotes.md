# 关键引文登记

这里登记支撑报告核心判断的短引文、定位和解释。完整第三方文档不随仓库复制；PackingSolver 关键源码快照保存在 `sources/snapshots/` 并用 `sources/manifest.csv` 固定 SHA-256。

## Q01：THPACK 数据集语义

来源：S03，`3d_rectangular/thpack/README.txt`。原文：“These problems are single container loading problems, the objective being to maximise the volume utilisation of the container.” 该句只用于 THPACK1–8 的单容器最大体积目标。

同一来源对 thpack9 写明：“These problems involve multiple containers, the objective being to minimise the number of containers required to ship the entire consignment.” 该句用于报告中将 THPACK9 与 THPACK1–8 分开计分。

## Q02：PackingSolver 官方 capability

来源：S07，README 的 box solver 目标列表。原文列出 “Knapsack”、“Bin packing”、“Open dimension X/Y/Z” 和 “Variable-sized bin packing”，并在同一节列出 six allowed rotations 与 bin total weight。该引文只支持官方声明，不替代运行验证。

## Q03：PackingSolver 缺失分支

来源：S08、S09、S10。S08/S09 的 `Solution::operator<` switch 在 `Objective::Feasibility` 后直接进入 default；S10 在对应位置包含：`case Objective::VariableSizedBinPacking: { return strictly_lesser_cost(solution.cost(), cost()); }`。这是源码对照证据，不是根据报错猜测。

## Q04：ESICUP 数据库贡献规则

来源：S01 README。原文要求每个新数据集提供 README、原论文、DOI 和格式说明，并鼓励通过 issue/PR 修订错误。该句用于说明数据集来源和可审计贡献方式。

## Q05：求解状态强度

来源：S12。CP-SAT 文档区分求解状态、目标值和 best bound；本仓库进一步把输出规范为 `FEASIBLE`、`INCUMBENT_WITH_BOUND`、`PROVEN_OPTIMAL`、`TIME_LIMIT` 和 `UNKNOWN`。后半部分是本项目协议，不冒充 OR-Tools 原文。

## Q06：未建模不等于支持

来源：S11、S13、S14 的官方项目定位。OR-Tools 和 SCIP 提供通用整数/约束优化能力，但没有被本项目发现的通用 3D 装箱 global constraint；报告中将它们标为“可自建模型”，没有写成现成 3D packer。


## Q07：BR 论文 DOI 与 THPACK 旋转字段

来源：S03 与 S31。THPACK README 将 THPACK1–7 的来源列为 Bischoff 与 Ratcliff 的 *Issues in the development of approaches to container loading*（OMEGA 23(4), 377–390, 1995），Crossref 登记 DOI 为 `10.1016/0305-0483(95)00015-G`。README 的尺寸字段以每个尺寸后的 0/1 表示该尺寸是否可作为竖直方向；本报告据此不把它解释为三个轴的独立旋转开关。

## Q08：前端 F 编号到来源清单的映射

前端研究稿中的官方事实均有来源清单入口：F1→S76；F2–F3→S77；F4→S78；F5–F6→S79；F7→S80；F8–F11→S81；F12–F16→S82；F17→S83；F18–F21→S84；F22→S85；F23–F24→S86；F25–F26→S87；F27–F29→S88；F30→S89；F31→S90；F32→S91；F33→S92；F34→S93；F35→S94；F36→S95。S29/S30 仍保留为报告早期 Three.js/Tauri 通用入口；新增条目记录了正文所依赖的具体官方页面、版本和许可证来源。

## Q09：协议 v3 reliability fixture

来源：S129。仓库内的 `reliability-fixture.json` 是整数尺寸、八立方体完整装载的版本化基准；`run_reliability.py` 只生成确定性的置换、重命名、轴变换、单位缩放和规模变体。B24-B29 的结果用于检查表示不变量、数值一致性、重复运行方差、资源拐点以及进程取消/非法输入恢复，不作为公开数据集质量排名或工业泛化结论。
