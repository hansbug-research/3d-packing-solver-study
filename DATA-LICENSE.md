# 数据许可说明

本仓库中的代码、实验脚本和原创报告按 Apache-2.0 发布。外部数据集仍受其原始许可和来源条款约束：ESICUP 数据库标注为 CC0-1.0，PackingSolver、py3dbp、Jerry、Skjolber 和其他第三方项目各自的许可证以其上游仓库为准。仓库只保存为复现实验所需的极小转换实例、摘要和校验信息，不重新声明第三方论文或完整数据集的版权。

`sources/snapshots/` 中的 PackingSolver README、C++ 源文件和 LICENSE 是提交 `367ebfdaad11424ded3696b7dae799a30c1375d0` 的审计快照，按其上游 MIT License 分发；对应许可证全文与 URL、SHA-256 已登记在 `sources/manifest.csv` 的 S07–S10、S32。快照只用于核对 capability 和缺失分支，不构成官方 release，也不把本仓库的 Apache-2.0 施加到这些文件上。

同目录中的 Go `bp3d.go` 与 LICENSE 是 commit `0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7` 的审计快照，按其 MIT License 分发；来源 URL、版本和 SHA-256 登记在 S106–S107。Rust `u-nesting` 只登记了固定仓库 commit，没有把未运行的源码复制为本仓库快照。
