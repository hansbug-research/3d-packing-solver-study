# 仓库发布审计记录

审计日期：2026-08-31。审计对象是发布到 `hansbug-research` 的三维装箱调研仓库；本记录只描述当前工作树中可复核的发布风险，不替代学术正文、算法矩阵或实验结果。

## 收口状态（2026-08-31）

本轮发布前复核已关闭初始阻断项：`raw/experiments/` 当前归档 123 个实验文件，另含逐任务 stderr/退出码、Three.js、商业实验和 Java runner 记录，最终由 156 文件 manifest 校验；THPACK9 转换器固定 ESICUP commit 与源文件 SHA-256；CFF 改为合法的 `software` 类型并补版本/日期；CI、105 行来源 manifest、关键引文、审计索引、Three.js fixture、商业求解器历史输出及 PackingSolver 二进制 provenance 均已落盘。仓库已发布到 `hansbug-research/3d-packing-solver-study` 的 public `main` 分支，发布提交和线上 Actions 运行记录见 `audit/reproducibility_audit.md`。PackingSolver 的四个复现已提交为 issue #536–#539、修复 PR #540–#543，均为 open 未合并。剩余边界是预编译 PackingSolver 二进制、Maven/JDK、商业求解器许可和 GPU 渲染环境不随仓库分发，需在目标环境按文档准备；这些限制在 README、报告和 raw 记录中明确标为可选或未测试，不阻断离线复核。

本节是当前状态的权威摘要；下面 Findings 保留初始审计时的证据和建议，历史“部分修复”标签不再表示当前阻断项。当前仍需人工处理的事项只有目标平台的二进制/JVM/商业许可准备、外部滚动文档链接复核，以及远端 GitHub 渲染和 Actions 结果抽查，不影响离线脚本验证。

## 审计方法

本轮检查使用 `git status --short --ignored`、`git ls-files`、`find`、`du`、`python3 -m pytest -q`、`python3 scripts/analyze.py`、`python3 scripts/plot.py`、`python3 scripts/build_manifest.py`、`python3 scripts/verify.py`，并使用 `cffconvert 2.1.0 --validate --infile CITATION.cff` 核对 Citation File Format 1.2.0。`hansbug-research` 的组织惯例通过 GitHub API 和公开仓库 `code-review-termination-study`、`cross-arch-container-build-study`、`cn-desktop-os-buildchain-study` 的根目录、README 和工作流对照确认。

## Findings

截至本次复核，初始 Important 均已完成代码或文档层面的收口：CFF、Python 运行说明、第三方快照许可证、raw 归档、来源清单、CI 门禁、benchmark 来源锁定、商业/前端原始记录、provenance 校验和 Markdown/链接检查均已落盘。下文保留初始证据和建议，避免把历史 finding 静默删除。

### 🟠 Important（部分修复）：证据原始输出没有进入发布证据链

审计初始状态为 `results/raw/` 被忽略且 collect 脚本只复制 JSON；当前脚本已将该目录完整镜像到 `raw/experiments/`，并生成 156 个文件的 manifest。`benchmarks/run_controlled.sh` 和 Java runner 现为每个任务保留稳定 JSON stdout、独立 `.stderr`、`.exitcode` 和资源报告；失败仍按原有非零状态终止 runner，同时诊断已进入可归档目录。

### 🟠 Important（部分修复）：外部来源和自审目录尚未形成可审计档案

当前已加入 `sources/manifest.csv`、`sources/quotes.md`、`audit/academic_audit.md`、`audit/claims.csv` 和自审日志，且 verifier 会校验 manifest 快照哈希。R1–R23 已登记在来源清单，前端 F1–F36 通过 `sources/quotes.md` 的 Q08 映射到 S76–S95；远程来源仍没有本地内容 hash，需按“未快照/访问日期/版本”边界进行人工抽查。

### 🟠 Important（部分修复）：没有持续集成发布门禁

当前已加入 `.github/workflows/verify.yml`，固定 Python 3.12，重算派生文件、manifest，执行 CFF schema、provenance verifier、Markdown 排版/链接检查和 pytest；图文件通过重绘后的 `git diff --exit-code -- figures/` 与 manifest/存在性检查。外部 URL、论文元数据和 claims.csv 证据映射仍保留人工抽查边界。

### ✅ 已修复：CITATION.cff 当前不符合 CFF 1.2.0 schema

初始 `type: research` 被 `cffconvert 2.1.0 --validate` 拒绝；当前已改为 `type: software`，并补充 `version: 0.1.0` 与 `date-released: 2026-08-31`，同一工具验证通过，CI 已执行该校验以防止元数据回归。

### ✅ 已修复：README 的 Python 运行入口在干净环境不可用

初始 README 直接使用系统 Python 3.10 且没有安装步骤；当前 README 已明确要求 Python 3.12、创建 `.venv` 并执行 `pip install -e '.[test]'`，CI 也固定 3.12。仍建议在脚本 fallback 中拒绝低于 3.12 的解释器并输出清晰错误。

### 🟠 Important（部分修复）：公共实验依赖被忽略的外部 checkout

当前已加入 `scripts/fetch_dependencies.sh`，固定 ESICUP、Jerry、PackingSolver 源码和 Skjolber 的 commit；但该脚本没有下载/构建 `.cache/packingsolver` 预编译 binary，也没有安装或固定 Maven，因此完整候选库实验仍不能仅靠 README 的步骤从干净 clone 重跑。应补 binary 下载/构建和 hash 检查，或把 fetch 作用域明确为源码/数据准备。

### 🟠 Important（部分修复）：正式表格中的 Gurobi/CPLEX/Three.js 数字没有对应脚本和原始输出

前端 Node/Three.js smoke fixture、lockfile 和 raw 输出已补齐，且明确不含 GPU/FPS 结论；Gurobi/CPLEX 微型 MIP 脚本、输入、历史 stdout/stderr、资源文件和许可边界已归档，当前环境缺少对应 Python 包时稳定返回 `NOT_RUN_MISSING_PACKAGE`，不能把历史数字解读为本机当前可重跑结果。历史商业 JSON 进一步发现模型字段与目标值矛盾，已规范标为 `INVALID_HISTORICAL_INCONSISTENT_FIXTURE`，原报告值仅保留在 `reported_*` 字段并排除出正式表；详见 `raw/experiments/commercial/README.md`。

### 🟠 Important（部分修复）：REVIEW 对 verifier 覆盖范围的声明超出实现

`verify.py` 当前检查 source manifest、raw/source snapshot hash、release audit artifact、CFF 必要字段、PackingSolver source/binary provenance 和线上 issue/PR 跟踪；`check_markdown.py`、`check_links.py` 分别承担段内硬折行和本地链接/图片目标检查，完整 CFF schema 由 CI 中的 `cffconvert` 负责。claims.csv 的证据映射仍由人工审阅。

### ✅ 已修复：公共输入转换未锁定来源版本

`benchmarks/convert_thpack9.py` 现在在读取前校验 ESICUP checkout 的固定 commit 和 `thpack9.txt` 的 SHA-256，并把两者写入转换后的 fixture；cache 被切换或源文件被修改时会拒绝生成结果。该修复仍应在 CI/干净 clone 中通过一次完整转换来复核。

### 🟠 Important（部分修复）：PackingSolver 实验结果没有绑定实际二进制

当前已在 `raw/provenance.json` 记录 source commit、二进制 SHA-256 和资源门限，并在 sources manifest 修正为可访问的 40 位 commit；`verify.py` 已校验 provenance 中的提交、二进制 hash 格式和 issue/PR 跟踪，预编译 binary 本体仍不随仓库分发，需按文档在目标环境构建或获取并重新核对 hash。

### ✅ 已修复：第三方源码快照与数据许可证说明矛盾

`sources/snapshots/` 中提交了完整的 PackingSolver README、三个 C++ 源文件和其 MIT LICENSE；`DATA-LICENSE.md` 已明确这些快照按上游 MIT 分发、不会继承本仓库 Apache-2.0，并在 sources manifest 中登记 URL、commit 和 hash。

### ✅ 已修复：研究仓库已形成 GitHub 发布状态

当前已创建并推送 `hansbug-research/3d-packing-solver-study` public 仓库，默认分支为 `main`；发布提交和 Actions 运行链接记录在 `audit/reproducibility_audit.md`。README、CITATION.cff、raw/manifest.json 已通过 GitHub API 抽查，剩余人工边界是外部滚动 URL、许可证条款和渲染器三平台实测。

### ✅ 已修复：正文的自然段折行已符合仓库写作约定

`CLAUDE.md` 规定中文自然段内不硬换行；当前 `scripts/check_markdown.py` 已扫描正文并在 CI 中拒绝普通段落硬折行，同时忽略代码块、表格、列表、快照和依赖缓存。代码块、表格和列表仍不做机械合并，并已用 `shuorenhua` 做事实保护检查。

## 已验证的正向结果

截至本记录生成时，`.venv/bin/python -m pytest -q` 返回 9 passed；`scripts/analyze.py`、`scripts/plot.py`、`scripts/build_manifest.py`、`scripts/verify.py`、`scripts/check_markdown.py`、`scripts/check_links.py` 在当前选定快照上均返回成功。该结果证明已纳入 verifier 的公共 THPACK9 数量、箱数、raw/source hash、元数据和本地链接自洽；不替代外部 URL、论文元数据、商业许可和远端 Actions 的人工核对。

## 发布前检查清单

- [x] `CITATION.cff` 通过 CFF 1.2.0 schema，包含版本、日期和 revision 绑定。
- [x] `sources/manifest.csv`、`sources/quotes.md` 和 `audit/` 自审/复现日志已提交，正文引用可定位。
- [x] raw canonical 目录包含全部原始 stdout、stderr、退出码、资源、输入和 provenance；156 文件 manifest 可离线核对。
- [x] `.github/workflows/verify.yml` 定义了干净 runner 的派生文件、manifest、图、CFF、verifier、Markdown 检查和测试门禁；线上运行结果已记录并通过。
- [x] `git diff --check`、敏感信息扫描、文件大小审计和 Markdown 链接检查通过。
- [x] 建立有提交哈希的 `main` 分支并推送到目标 public 仓库，README 的仓库 URL 与实际名称一致。
