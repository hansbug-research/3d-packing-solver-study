# 复现审计

审计日期：2026-08-31。目标是验证“从仓库中的 raw 数据可以重算正文中的核心数字”，以及“实验命令不会把未测试项伪装成通过”。

## 当前已执行的链路

| 检查 | 命令 | 结果 |
|---|---|---|
| 公共数据转换 | `.venv/bin/python benchmarks/convert_thpack9.py` | 通过；生成 70 件 THPACK9 instance 1 |
| 受控 Python/C++ 实验 | `bash benchmarks/run_controlled.sh` | 通过；原版 PackingSolver 失败路径仍被保留 |
| 受控 Java 实验 | `bash benchmarks/run_java_controlled.sh` | 通过；Skjolber 增加公共实例场景 |
| 公共 baseline | `.venv/bin/python benchmarks/benchmark_public_thpack9.py` | 通过；py3dbp/Jerry 均 70/70、50 箱 |
| 派生统计 | `bash scripts/collect_and_derive.sh` | 通过；生成 `derived/stats.json`、CSV 和图 |
| manifest | `.venv/bin/python scripts/build_manifest.py` | 通过；当前 raw 文件逐项登记大小和 SHA-256 |
| 机器核对 | `.venv/bin/python scripts/verify.py` | `VERIFY_OK` |
| 单元/结果断言 | `.venv/bin/python -m pytest -q` | `9 passed` |
| PackingSolver 全量 1 s | `bash benchmarks/campaign/run_packingsolver_thpack.sh`，随后 `bash benchmarks/campaign/revalidate_packingsolver_archive.sh` | 762 条记录；759 个合法源 certificate 通过 |
| PackingSolver 全量 10 s | `bash benchmarks/campaign/run_packingsolver_thpack_10s.sh`，随后离线 archive 重验 | 762 条记录；759 个合法源 certificate 通过；campaign exitcode 0 |
| Exact-small 四后端 | `bash benchmarks/campaign/run_exact.sh` 与 `bash benchmarks/campaign/run_exact_sensitivity.sh` | canonical strengthened 四后端各 7/7；失败 formulation 保留非零 exitcode |
| Java THPACK9 | `bash benchmarks/campaign/run_skjolber_thpack.sh` | Plain/LAFF 各 44/44 合法 |
| Go/Rust THPACK9 | `bash benchmarks/campaign/crosslang_run_thpack9.sh` | Go 与 Rust ExtremePoint adapter 各 44/44 合法 |
| Rust 策略重复 | 跨语言 strategy adapter，每策略 THPACK9-1 重复 5 次 | ExtremePoint 5/5 合法；Layer/GA/BRKGA/SA 各 0/5 |
| 工业数据审计 | `.venv/bin/python benchmarks/audit_industrial_datasets.py --esicup-root .cache/esicup-datasets` | Alonso 2019/2020 解析通过；BAYTP 快照缺文件状态保留 |
| Campaign 汇总 | `.venv/bin/python benchmarks/campaign/analyze_campaign.py` | `results/campaign/aggregate.json` 绑定 35 个输入 SHA-256 |

## 证据边界

原始 `results/*.json`、公共 certificate、资源日志和转换输入已复制到 `raw/`；`results/raw/` 是本机临时目录，未作为发布依赖。PackingSolver 修复版的完整 C++ 源码副本和构建目录位于 `.cache/`，该目录被 `.gitignore` 排除；上游关键源码快照及 SHA-256 位于 `sources/snapshots/`，因此无需把大型依赖树提交到仓库。

THPACK9 的 `COPIES` certificate 是聚合表示：一行布局可能代表多个相同箱实例。独立校验必须先按物理 copy 展开，否则会把同一布局重复到同一箱而错误报告重叠。当前 `raw/certificates/thpack9_packingsolver_patched.csv` 已按该规则复核。

公开实例没有 known optimum；`ceil(17920/960)=19` 只是 THPACK9-1 的体积下界。25、28 和 50 箱都是 incumbent，不允许写成 `PROVEN_OPTIMAL`。完整 44 例的跨实现均值也只统计通过 validator 的 certificate；Jerry 的 1 条重叠和 Rust Layer/GA/BRKGA/SA 的越界结果均从质量排名排除。

Go 1.27.0 与 Rust 1.98.0 已用固定下载 hash bootstrap。Go `bp3d` 固定到 `0ba3dcda...`；Rust `u-nesting` 固定主仓及三个 path dependency commit，并使用提交的 `Cargo.lock --locked` 构建。Rust 上游 103 个 unit test 与 3 个 doc test 通过，但不能消除 campaign 发现的 Layer decoder 越界和参数未接线问题。

PackingSolver 1 s/10 s 的原始 solver artifacts 已打包保存。重验器从输入重新核对 certificate 尺寸、rotation、数量、边界、重叠、packed volume 和箱数。`SOLVER_REPORTED_BOUND_CLOSED` 只保留上游自报含义，没有被重命名为独立证明的 `PROVEN_OPTIMAL`。

## 发布前还需人工抽查

1. 从 `sources/manifest.csv` 随机抽取至少 5 个 DOI/官方 URL，核对标题、年份、作者和报告对应关系。
2. 检查 GitHub 渲染后的 Markdown 表格、锚点和 `figures/fig01_thpack9_bins.png` 是否可见。
3. 在干净 clone 中执行 `scripts/analyze.py`、`scripts/plot.py`、`scripts/verify.py` 和 `pytest`，确认没有依赖工作树缓存。
4. 已核对远端默认分支、许可证、CITATION.cff 解析和 raw 文件完整性；后续仅需在内容更新后重复抽查。

## 线上发布核对

- 仓库：<https://github.com/hansbug-research/3d-packing-solver-study>，可见性 `public`，默认分支 `main`。
- 最终内容基线：`365e32cccf0652bf492652a2c4f4e3ae1ae99029`。
- GitHub Actions：<https://github.com/hansbug-research/3d-packing-solver-study/actions/runs/33371401890>，对应提交的 `verify` job 全部通过；仅有 GitHub runner 的 Node 20 弃用提示。此前提交 `e162fa2`/`6536845`/`6dcd8ba`/`cbf9f7b` 的成功运行仍作为历史 CI 记录保留。
- API 抽查确认 README、CITATION.cff、raw/manifest.json 均可访问；本地链接检查和 CFF schema 检查与线上 CI 结果一致。
