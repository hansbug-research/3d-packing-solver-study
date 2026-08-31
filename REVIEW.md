# 本仓库的评审规则

这是一个实证型技术调研仓库，评审重点是证据链和结论强度，不是文案是否漂亮。

## L1 机器检查

```bash
.venv/bin/python scripts/analyze.py
.venv/bin/python scripts/plot.py
.venv/bin/python benchmarks/campaign/analyze_campaign.py
.venv/bin/python benchmarks/comprehensive/build_plan.py --check
.venv/bin/python benchmarks/comprehensive/import_baseline.py --check
.venv/bin/python benchmarks/comprehensive/analyze.py --check
.venv/bin/python scripts/verify.py
.venv/bin/python -m pytest -q
```

任一命令非零都不能进入人工评审。`verify.py` 检查 raw/derived/正文中登记的核心数量、结果状态、公共实例结果和文件校验；它没有覆盖的数字仍需人工抽查。

## L2 证据链

1. 外部事实必须在 `sources/manifest.csv` 或 `sources/quotes.md` 中有 URL、访问日期和归属。
2. 原始结果放在 `raw/`，不直接修改；发现错误时修改脚本并记录 `audit/`。
3. 失败、超时、崩溃、许可证限制和未测试项必须保留，不能只发布成功结果。
4. 每个 benchmark 结果必须带输入、版本、参数、资源限制和独立 validator 状态。
5. `results/campaign/aggregate.json` 的每个消费源必须登记 SHA-256；新增 campaign 结果要同时更新机器断言和 `results/campaign/README.md` 的运行状态矩阵。
6. 综合 campaign 必须遵守 [`research/test-protocol.md`](research/test-protocol.md)：B01-B32 的每个候选 × benchmark 产生计划状态，原生/adapter/投影/精确模型分轨，非法 certificate 不得进入排名。
7. 公共质量 benchmark、构造约束套件、工业综合问题和故障测试不得合并成一个总分；BAYTP 的完整源文件、B31/B32 生成器 provenance 和所有问题投影必须逐项校验。

## L3 结论强度

1. 单个实例只能支持该实例结论；没有 known optimum 时不得写“最优”。
2. “可建模”与“库原生支持”分开写；未测试与失败分开写。
3. x86-64 实测不得外推到其他架构；缺少力学/法规数据时必须写 `NOT_APPLICABLE` 或 `UNKNOWN`。
4. 上游 bug、临时 patch 和官方 release 必须分别标注。
5. adapter 提供的能力必须写成 adapter 能力；无效 certificate、malformed source 和 `NOT_SUPPORTED` 不进入质量均值。

## L4 文本与发布

中文正文使用自然段且段内不硬换行；代码块、表格、路径和错误原文不做风格改写。发布前运行 `scripts/verify.py`，检查登记的 raw/source SHA-256、核心引用入口、CFF 必要字段、图表文件和审计目录；Markdown 链接、论文元数据与未快照的法规正文仍需人工抽查。

`scripts/check_markdown.py` 会在 CI 中拒绝普通 Markdown 段落的硬换行，同时忽略代码块、表格、列表、上游源码快照和依赖缓存。

`scripts/check_links.py` 会校验仓库内 Markdown 的相对链接、图片目标和路径越界；外部 URL 仍以 `sources/manifest.csv` 登记，并在发布后抽查。
