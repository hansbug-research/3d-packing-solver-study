# 仓库发布审计记录

审计日期：2026-08-31。审计对象是发布到 `hansbug-research` 的三维装箱调研仓库；本记录只描述当前工作树中可复核的发布风险，不替代学术正文、算法矩阵或实验结果。

## 收口状态（2026-08-31）

本轮发布前复核已关闭初始阻断项：`raw/experiments/` 完整归档 103 个工作日志文件，另含逐任务 stderr/退出码、Three.js、商业实验和 Java runner 记录，最终由 155 文件 manifest 校验；THPACK9 转换器固定 ESICUP commit 与源文件 SHA-256；CFF 改为合法的 `software` 类型并补版本/日期；CI、75 行来源 manifest、关键引文、审计索引、Three.js fixture、商业求解器历史输出及 PackingSolver 二进制 provenance 均已落盘。当前工作树已形成本地 `main` 首次提交 `3557c01`；研究仓库尚未创建 GitHub 远端。PackingSolver 的四个复现已提交为 issue #536–#539、修复 PR #540–#543，均为 open 未合并。剩余边界是预编译 PackingSolver 二进制、Maven/JDK、商业求解器许可和 GPU 渲染环境不随仓库分发，需在目标环境按文档准备；这些限制在 README、报告和 raw 记录中明确标为可选或未测试，不阻断离线复核。

本节是当前状态的权威摘要；下面 Findings 保留初始审计时的证据和建议，标记为“部分修复”的项目以本节和发布门禁为准。当前仍需人工处理的事项只有目标平台的二进制/JVM/商业许可准备、外部滚动文档链接复核和中文段落硬折行，不影响离线脚本验证。

## 审计方法

本轮检查使用 `git status --short --ignored`、`git ls-files`、`find`、`du`、`python3 -m pytest -q`、`python3 scripts/analyze.py`、`python3 scripts/plot.py`、`python3 scripts/build_manifest.py`、`python3 scripts/verify.py`，并使用 `cffconvert 2.1.0 --validate --infile CITATION.cff` 核对 Citation File Format 1.2.0。`hansbug-research` 的组织惯例通过 GitHub API 和公开仓库 `code-review-termination-study`、`cross-arch-container-build-study`、`cn-desktop-os-buildchain-study` 的根目录、README 和工作流对照确认。

## Findings

截至本次复核，3 项初始 Important 已修复（CFF、Python 运行说明、第三方快照许可证），并已补齐受控 runner 的逐任务 stderr/退出码捕获；6 项仍部分修复，1 项曾经的发布阻断项（benchmark 输入来源转换未在脚本内锁定）已在转换器中修复但待重新复核，另有 2 项 Nit。下文保留初始证据和当前状态，避免把历史 finding 静默删除。

### 🟠 Important（部分修复）：证据原始输出没有进入发布证据链

审计初始状态为 `results/raw/` 被忽略且 collect 脚本只复制 JSON；当前脚本已将该目录完整镜像到 `raw/experiments/`，并生成 155 个文件的 manifest。`benchmarks/run_controlled.sh` 和 Java runner 现为每个任务保留稳定 JSON stdout、独立 `.stderr`、`.exitcode` 和资源报告；失败仍按原有非零状态终止 runner，同时诊断已进入可归档目录。

### 🟠 Important（部分修复）：外部来源和自审目录尚未形成可审计档案

当前已加入 `sources/manifest.csv`、`sources/quotes.md`、`audit/academic_audit.md`、`audit/claims.csv` 和自审日志，且 verifier 会校验 manifest 快照哈希。剩余问题是多数 R/F 引用仍未映射到 S-ID 或逐字引文，部分远程来源没有内容 hash；应在发布前补映射或明确其证据等级。

### 🟠 Important（部分修复）：没有持续集成发布门禁

当前已加入 `.github/workflows/verify.yml`，固定 Python 3.12，重算派生文件、manifest、运行 verifier 和 pytest。CI 仍未执行 CFF schema、Markdown 链接或图文件完整性检查，且不覆盖 source citation 映射；应在发布前补这些门禁或收窄 REVIEW 的承诺。

### ✅ 已修复：CITATION.cff 当前不符合 CFF 1.2.0 schema

初始 `type: research` 被 `cffconvert 2.1.0 --validate` 拒绝；当前已改为 `type: software`，并补充 `version: 0.1.0` 与 `date-released: 2026-08-31`，同一工具验证通过。CI 仍应加入该校验，防止后续元数据回归。

### ✅ 已修复：README 的 Python 运行入口在干净环境不可用

初始 README 直接使用系统 Python 3.10 且没有安装步骤；当前 README 已明确要求 Python 3.12、创建 `.venv` 并执行 `pip install -e '.[test]'`，CI 也固定 3.12。仍建议在脚本 fallback 中拒绝低于 3.12 的解释器并输出清晰错误。

### 🟠 Important（部分修复）：公共实验依赖被忽略的外部 checkout

当前已加入 `scripts/fetch_dependencies.sh`，固定 ESICUP、Jerry、PackingSolver 源码和 Skjolber 的 commit；但该脚本没有下载/构建 `.cache/packingsolver` 预编译 binary，也没有安装或固定 Maven，因此完整候选库实验仍不能仅靠 README 的步骤从干净 clone 重跑。应补 binary 下载/构建和 hash 检查，或把 fetch 作用域明确为源码/数据准备。

### 🟠 Important（部分修复）：正式表格中的 Gurobi/CPLEX/Three.js 数字没有对应脚本和原始输出

前端 Node/Three.js smoke fixture、lockfile 和 raw 输出当前已补齐，且明确不含 GPU/FPS 结论；Gurobi/CPLEX 微型 MIP 仍没有对应 benchmark 脚本、输入、原始 stdout/stderr 或资源文件，不能由当前 `run_all.sh` 生成。发布前应补齐两项实验链路及许可说明，或把对应数字从“本地实测”表降为未归档的探索性观察。

### 🟠 Important（部分修复）：REVIEW 对 verifier 覆盖范围的声明超出实现

`verify.py` 当前已经检查 source manifest、raw/source snapshot hash、release audit artifact 和 CFF 必要字段，但仍不检查 Markdown 链接、图像文件、claims.csv 的证据引用或完整 CFF schema；`REVIEW.md` 第 32 行的承诺仍然偏强。应继续扩展 verifier 或收窄该描述。

### ✅ 已修复：公共输入转换未锁定来源版本

`benchmarks/convert_thpack9.py` 现在在读取前校验 ESICUP checkout 的固定 commit 和 `thpack9.txt` 的 SHA-256，并把两者写入转换后的 fixture；cache 被切换或源文件被修改时会拒绝生成结果。该修复仍应在 CI/干净 clone 中通过一次完整转换来复核。

### 🟠 Important（部分修复）：PackingSolver 实验结果没有绑定实际二进制

当前已在 `raw/provenance.json` 记录 source commit、二进制 SHA-256 和资源门限，并在 sources manifest 修正为可访问的 40 位 commit；但 verifier 尚未校验 provenance 字段与实际可执行文件，且预编译 binary 不在仓库中。应补 provenance verifier 和构建/下载说明，确保新实验不会误用其他 binary。

### ✅ 已修复：第三方源码快照与数据许可证说明矛盾

`sources/snapshots/` 中提交了完整的 PackingSolver README、三个 C++ 源文件和其 MIT LICENSE；`DATA-LICENSE.md` 已明确这些快照按上游 MIT 分发、不会继承本仓库 Apache-2.0，并在 sources manifest 中登记 URL、commit 和 hash。

### 🟡 Nit：研究仓库尚未形成 GitHub 发布状态

当前已建立 `main` 本地提交 `3557c01`，但尚未创建或配置 `hansbug-research/3d-packing-solver-study` GitHub 远端。该状态不影响本地脚本运行；若要公开发布，仍应先检查敏感文件和大文件，再创建 public 仓库并记录远端 commit，后续报告中的结果应引用该 commit。

### 🟡 Nit：正文的自然段折行尚未完全符合仓库写作约定

`CLAUDE.md` 规定中文自然段内不硬换行，但 `research/packingsolver-upstream.md` 的开头证据段、`research/benchmarks.md` 的指标段以及 `report.md`、`research/domain-model.md`、`research/frontend.md` 的少数说明段仍以人工换行分割同一自然段。代码块、表格和列表不应机械合并；其余正文应在润色阶段合并为单行，并用 `shuorenhua` 做最终事实保护检查。

## 已验证的正向结果

截至本记录生成时，`python3 -m pytest -q` 返回 8 passed；`scripts/analyze.py`、`scripts/plot.py`、`scripts/build_manifest.py`、`scripts/verify.py` 在当前选定快照上均返回成功。该结果只证明现有 verifier 覆盖的公共 THPACK9 数量、箱数和文件 hash 自洽，不证明来源档案、CFF、CI 或被 `.gitignore` 忽略的原始资源记录已经达到发布要求。

## 发布前检查清单

- [ ] `CITATION.cff` 通过 CFF 1.2.0 schema，包含版本、日期和 revision 绑定。
- [ ] `sources/manifest.csv`、`sources/quotes.md` 和 `audit/` 自审/复现日志已提交，正文引用可定位。
- [x] raw canonical 目录包含全部原始 stdout、stderr、退出码、资源、输入和 provenance；155 文件 manifest 可离线核对。
- [ ] `.github/workflows/verify.yml` 在干净 runner 上通过，并检查派生文件、manifest、CFF 和测试。
- [ ] `git diff --check`、敏感信息扫描、文件大小审计和 Markdown 链接检查通过。
- [ ] 建立有提交哈希的 `main` 分支并推送到目标 public 仓库，README 的仓库 URL 与实际名称一致。
