# 跨平台 CLI、桌面 GUI 与 3D 交互技术选型

> 调研日期：2026-08-31。维护状态与版本以该日官方文档、官方发行源和官方仓库为准。本文给出工程选型，不构成开源许可证法律意见；发布商业产品前仍需对实际链接、分发方式和全部传递依赖做法律复核。

## 1. 结论先行

推荐的产品形态是：

- **桌面壳与系统权限边界**：Tauri 2（Rust）；
- **GUI**：React + TypeScript + Vite，面向桌面密集操作设计，不做网页式营销布局；
- **3D**：直接使用 Three.js，不把数千个箱体映射成 React 组件；
- **Python 后端**：打包为由 Tauri Rust core 启动和监管的本地 worker，CLI 与 GUI 共用同一 application service、Schema、求解器适配器和独立验证器；
- **进程协议**：小消息使用有版本的 NDJSON/JSON-RPC 风格 stdio，求解进度由 Rust 转成 Tauri `Channel`，大型方案结果写入作业目录并按页/按容器读取；
- **原生算法**：Python、pybind11/Cython、PyO3/maturin 或 ctypes/cffi 包装的 C/C++/Rust 内核都放在 Python worker 内；原生崩溃只损失该 worker，不拖垮桌面主进程；
- **Java 算法**：仅当本地基准证明其能力明显优于可嵌入方案时，作为可选二级 sidecar 接入同一 engine adapter 协议，不让 GUI 或项目格式依赖 Java；
- **打包**：每个 OS/CPU 在原生 CI runner 上构建。Python worker 第一阶段用 PyInstaller `onedir`，同时基准 Nuitka `standalone`；不要默认 `onefile`，其启动解压、临时目录和嵌套签名更难控制。

这条路线不是因为 Tauri 自己能解决装箱，而是它能提供合适的隔离边界：WebView 只负责高质量表格和 3D，Rust 只负责窗口、文件授权、进程监管和窄 IPC，Python 保持算法编排中心。用户即使不安装 GUI，也能通过 CLI 获得相同结果。

**有条件的第二选择**是 PySide6 + Qt Quick/Qt Widgets。它与 Python 最直接，Qt Model/View 也适合大表格；但当前 Qt Quick 3D 官方文档明确标为 **Commercial 或 GPLv3** [F4]。闭源产品若不采购 Qt 商业许可，不能把“PySide6 总体可走 LGPLv3”误推成“Qt Quick 3D 也可走 LGPLv3”。可改用 LGPL 的 Qt 3D [F5] 或 MIT/BSD 的 PyVista/VTK，但前者更底层，后者使分发体积明显增加。

**Electron 是兼容性后备方案**：若真实客户机器上的 WebKitGTK/WKWebView/WebView2 差异导致 Three.js 无法稳定交付，可把同一 React + Three.js 前端移入 Electron。它随包携带一致的 Chromium，代价是体积、内存和高频安全升级。Flutter 与 Flet 不建议作为本产品主桌面栈。

## 2. 决策前提

装箱桌面端不是普通 CRUD。它同时要求：

1. 可粘贴、批量编辑、校验和筛选成百上千行货物/承载器数据；
2. 编辑面朝向、允许姿态、承压、支撑、站点顺序等强结构约束；
3. 求解可持续数秒到数小时，必须可取消、可恢复地展示候选方案，而不能阻塞 UI；
4. 方案可能含数千到数万实例，需要拾取、剖切、隐藏、分步装载和问题高亮；
5. GUI、CLI、自动化 API 必须有同一语义，不能出现“桌面能设但 CLI 不能复现”的参数；
6. 用户导入的 CSV/XLSX/JSON、名称、备注和将来的外部模型都按不可信输入处理；
7. Python 要能编排纯 Python、C/C++/Rust binding 和必要时的 Java 进程；
8. Linux、Windows、macOS 的安装、更新、签名、崩溃恢复和离线使用都必须可交付。

因此比较框架时，优先级依次是：业务交互与 3D 能力、Python/原生内核边界、发布可靠性、安全边界、可维护性、运行资源和包体。仅仅“能显示一个窗口”没有决策价值。

## 3. 候选桌面框架比较

### 3.1 总表

| 路线 | Python 集成 | 密集表格/产品 UI | 3D 路线 | IPC 与隔离 | 三平台分发 | 体积/性能 | 许可与维护 | 结论 |
|---|---|---|---|---|---|---|---|---|
| **Tauri 2 + React/TS** | Python sidecar，需维护协议；对 C/C++/Rust binding 无额外限制 | React/TanStack 可实现虚拟表格、可访问 primitives 和细粒度桌面交互 | Three.js 原生匹配 | Rust core 集中路由 IPC，capability/permission 可收窄；可隔离 worker 崩溃 [F7-F11] | 官方支持平台安装包、签名和 CI；各 OS 原生构建 [F12-F16] | 不内置浏览器，壳小；最终体积由 Python/求解库主导；长任务不阻塞 UI | Tauri `MIT OR Apache-2.0`；2026-07 发布 2.11.5，持续维护 [F17] | **推荐** |
| **PySide6 + Qt** | 最直接，同进程调用或 `QProcess` worker | Qt Model/View 很成熟；QML 与 Python 状态边界要纪律化 | Qt Quick 3D、Qt 3D、VTK/PyVista 或 QWebEngine+Three | 同进程最简单但原生崩溃会带走 UI；仍建议独立 worker | `pyside6-deploy` 封装 Nuitka，输出 Windows/Linux/macOS 应用 [F2] | 启动和原生控件好；QML/Qt 插件需裁剪，完整 wheels 较大 | PySide6 为 LGPLv3/GPLv3/商业 [F1]；**Qt Quick 3D 是 GPLv3/商业** [F4] | **条件备选** |
| **Electron + React/TS** | Node 主进程监管 Python sidecar，成熟 | 与推荐前端完全相同 | Three.js，且 Chromium 行为最一致 | 可做到 context isolation/sandbox/preload 白名单，但能力面比 Tauri 默认更宽，需严格加固 [F18] | Forge 官方推荐；三平台成熟，签名/更新资料完整 [F19-F21] | 每包带 Chromium+Node，基线体积和常驻内存最高 | MIT；8 周 major 节奏，仅支持最新 3 条 stable，升级负担明确 [F21-F22] | **兼容性后备** |
| **Flutter desktop** | Dart 与 Python 没有一等集成；通常仍是 sidecar；C ABI 可用 FFI [F23-F24] | 原生渲染、一致性和常规 UI 好 | 没有与 Three.js/VTK 同等级的官方成熟工程可视化路线，需插件或自研 | Dart sidecar 协议；引入第三种主语言 | 官方支持 Windows/macOS/Linux 构建，插件需逐平台核查 [F23] | AOT 和 UI 性能好，包体中等 | BSD-3-Clause；2026-08 stable 3.47.2 [F25-F26] | 不选；Python+3D 组合收益不足 |
| **Flet** | Python API 最直接，桌面包内嵌 Python | 快速表单/管理工具好；复杂虚拟表格和细粒度桌面交互受控件层限制 | 需自定义 Flutter 扩展或嵌 WebView，抵消“只写 Python”优势 | Python 与 Flutter 控件协议被框架封装，底层调优空间较少 | `flet build` 可产出三平台包，但 Flutter 必需，桌面目标基本需相应宿主 OS [F27] | 同时含 Flutter 和 Python；精确值需成品测量 | Apache-2.0；2026-08 发布 0.86.5 [F28] | 适合 MVP，不适合本产品主线 |

按“Python 代码量”单项看，Flet/PySide 的桥接代码更少；按本文给定的优先级，Tauri 同时提供可复用的 React/Three 前端、Rust 权限边界和独立 Python worker，因此作为首选进入 packaged PoC。

### 3.2 Tauri 2：为什么推荐

Tauri 的 core process 是唯一具有完整 OS 访问能力的进程，WebView 的系统能力由 IPC 和 capabilities 暴露；core 还能集中拦截、过滤 IPC [F8-F11]。官方 sidecar 文档明确把 PyInstaller 打包的 Python CLI/API 服务列为常见用例，并要求每个目标架构提供带 target triple 后缀的二进制 [F7]。这与“Rust 监管 Python worker”的设计完全一致。

推荐实现时比官方 JavaScript 直接启动 sidecar 的示例再收紧一步：

- Web 前端**不授予** `shell:allow-spawn` 或通用文件系统权限；
- 只有 Rust core 能启动固定名称、随应用签名的 Python worker；
- 前端只看到 `open_project`、`save_project`、`start_solve`、`cancel_job`、`read_solution_page` 等业务命令；
- Rust 校验窗口来源、job id、路径 scope 和消息大小后才转给 worker；
- worker stdout 专用于协议，stderr 专用于结构化日志，禁止混写；
- 默认不打开 localhost 端口，避免端口抢占、其他本机用户连接和 token 生命周期问题。

Tauri command 底层是 JSON 可序列化的异步消息；普通 event 适合少量状态变化，不适合低延迟/高吞吐流，官方建议有序高吞吐使用 `Channel` [F9-F10]。因此：启动/取消/查询用 command；每秒 5-10 次的进度、日志摘要和候选指标用 typed channel；完整 placement 不在每次进度中重复传输。

主要风险不是 Rust，而是系统 WebView 差异：Windows 使用 Edge WebView2，macOS 使用 WKWebView，Linux 依赖 WebKitGTK 4.1；Tauri 官方前置依赖页也逐发行版列出了 WebKitGTK 包 [F13]。这要求建立真实 GPU/驱动机器测试池。不能用“开发机 Chrome 正常”替代 Tauri 三平台验证。

### 3.3 PySide6：何时反而更合适

以下条件同时成立时可以改选 PySide6：团队几乎全是 Python/Qt；客户界面更偏内部工程工具而非高交互产品；愿意采购 Qt 商业许可，或明确不用 Qt Quick 3D；并且部署原生依赖已有经验。

优点：

- Python 对 Qt signals/slots、Model/View、线程池和 `QProcess` 的调用直接；
- 原生菜单、文件对话框、辅助功能和多屏行为成熟；
- 表格可用 `QAbstractTableModel` 做虚拟数据模型，不必把每个 cell 变成 Python widget；
- `pyside6-deploy` 官方工具封装 Nuitka，可输出 `.exe`、Linux `.bin`、macOS `.app`，支持 `onefile/standalone` 并通过 spec 排除 QML plugins [F2]。

限制：

- Qt Quick 3D 是高层、能混合 Qt Quick 2D/3D，并有 instancing、LOD、自定义材质等能力，但其当前许可是商业或 GPLv3 [F4]；
- Qt 3D 当前文档仍覆盖 Windows、Linux X11 和 macOS，许可为 LGPLv3/GPLv2/商业 [F5]，但 API 更接近通用 entity/component 渲染框架，做剖切、实例拾取和装载步骤产品化需要更多底层工作；
- PyVistaQt 能快速获得工程可视化，但依赖 VTK，分发和冷启动成本高；
- 同进程直接调用 native solver 虽方便，C++ 扩展段错误会直接关闭 GUI，所以仍应把求解放到 `QProcess` worker。

包体不能只看 `PySide6` 的 0.5 MB 元包。2026-08-31 PyPI 上 6.11.2 的 Linux x86_64 compressed wheel 约为 Essentials 76.4 MiB、Addons 167.0 MiB；macOS universal2 更大 [F33]。部署工具可以排除未用插件，最终安装包必须按真实 import 集合测量，不能拿 wheel 总和或“Qt 很轻”作承诺。

### 3.4 Electron：何时启用后备方案

Electron 的优势是自带同一 Chromium 与 Node，Three.js、WebGL、字体、打印和 DevTools 在三平台更一致；React 前端几乎无需改写。若 Tauri 在客户支持矩阵中持续遇到 WebKitGTK GPU/透明排序/字体问题，Electron 是可控的产品妥协。

它不是默认方案，原因有三点：

1. Electron 44.0.0 官方 release 的纯 runtime 压缩包约为 Linux x64 116.8 MiB、macOS arm64 123.7 MiB、Windows x64 150.2 MiB，尚未加入应用和 Python worker [F22]；
2. 官方策略是每 8 周一个 major，只支持最新 3 个 stable major [F21]，需要持续跟进 Chromium/Node 安全版本；
3. Electron 自己的安全清单要求本地可信内容、关闭 renderer Node integration、启用 context isolation 和 sandbox、严格 CSP、限制导航/新窗口、验证每个 IPC sender 等 [F18]。这些不是可选优化。

若采用，使用 Electron Forge [F19]，preload 只暴露窄的 typed API；renderer 不允许 `require`、任意 shell 和任意文件路径。Python worker 仍独立进程，不能把求解搬进 Node 主进程。

### 3.5 Flutter 与 Flet

Flutter desktop 是成熟的跨平台 UI 方案，官方支持 Windows/macOS/Linux，并可通过 Dart FFI/code assets 调 C/C++，也能在 build hook 中下载和校验预编译原生库 [F23-F24]。但本项目的事实中心是 Python，3D 又以 WebGL/Three.js 最合适；引入 Dart 后仍需一套 Python sidecar 协议，却没有得到更好的 3D 生态，所以不划算。

`flutter_3d_controller` 只能作为待核验插件候选：其 pub.dev 元数据列出 Android、iOS、Web 和 macOS，未列 Windows/Linux [F35]，不能据此承诺 Flutter 三平台桌面 3D。

Flet 的 `flet build` 会创建 Flutter 工程、用 `serious_python` 打包 Python、再执行 Flutter build；官方矩阵和文档说明了 Windows/macOS/Linux/web 等目标与对应宿主要求 [F27]。它适合快速做目录、表单、任务列表，但本产品的虚拟化编辑表、Three.js 级 3D、精确指针交互最终都要写 Dart extension 或嵌 WebView [F29]。届时团队同时维护 Flet、Flutter extension 和 Python，反而比 Tauri+React 更绕。

## 4. 3D 引擎选择

### 4.1 比较

| 引擎 | 与候选 GUI 的结合 | 本产品关键能力 | 体积/性能 | 许可/维护 | 判断 |
|---|---|---|---|---|---|
| **Three.js** | Tauri/Electron WebView 原生；React 外由 imperative scene controller 管理 | `InstancedMesh`、instance picking、raycaster、clipping planes、自定义 shader、正交/透视相机和 glTF export 均有维护中的 API [F30] | 一次 draw call 可表达同材质大量箱体；最终受系统 WebView/GPU 限制 | MIT；2026-07 r185，持续维护 [F30] | **推荐** |
| **Qt Quick 3D** | QML 原生，可混合 2D/3D | instancing、LOD、picking、PBR、custom material，适合 Qt 产品 [F4] | 原生渲染，避免浏览器层 | 当前为 GPLv3/商业，闭源需采购 [F4] | 仅 PySide 商业路线 |
| **Qt 3D** | Qt C++/QML/PySide binding | entity/component、framegraph、input、collision 等通用基础 [F5] | 可控但需较多低层产品代码 | LGPLv3/GPLv2/商业；Qt 6.11 文档仍在 [F5] | LGPL Qt 的可行但次优路线 |
| **VTK/PyVista/PyVistaQt** | PySide/Python 最方便 | clipping、slice、picking、mesh/标量场、科学可视化工具成熟 [F31] | 对纯长方体装箱能力过剩；VTK 9.7.0 wheel 已约 76.7-133.2 MiB compressed（按 OS）[F34] | VTK BSD-style，PyVista/PyVistaQt MIT；持续维护 [F31-F34] | 后续结构/热场插件，不做主视图 |

Three.js 的选择不是说它能验证几何。它只负责展示由后端验证过的数据。碰撞、边界、方向、支撑和载荷结果仍以 Python/C++/Rust validator 的整数/高精度计算为准；前端浮点网格不可回写为“修正后的可行方案”。

### 4.2 受限资源烟雾测试

为排除“文档有 API、当前包却无法组合”的低级风险，在 Node 24.14.1、Three.js 0.185.1/r185 上做了非渲染数据层测试：

- 在 256 MiB V8 heap 上限和 30 秒 timeout 下创建 10,000 个 `InstancedMesh` 箱体；
- 计算实例整体 bounding box/sphere；
- 从正上方 raycast，成功返回 `instanceId=5050`；
- material 接受一个 clipping plane；
- 本次归档运行进程 23.211 ms 完成，`/usr/bin/time -v` 最大 RSS 68,120 KiB，V8 `heapUsed` 约 7.6 MiB；重复运行的时间和 RSS 会随 Node/主机抖动。

这只证明 r185 的实例矩阵、包围体、instance picking 和 clipping plane 配置可组合，不证明 WebGL 帧率。Node 没有创建 renderer/GPU context，不能把该 RSS 或耗时当成桌面渲染基准。正式原型必须在三个系统的实际 Tauri WebView 上测 1k/10k/50k 箱体的 FPS、显存、拾取延迟、透明/剖切正确性和 GPU 恢复。脚本、fixture 与原始输出见 [`smoke.mjs`](../benchmarks/frontend-three-smoke/smoke.mjs)、[`smoke.stdout`](../raw/experiments/frontend-three-smoke/smoke.stdout) 和 [`smoke.resources.txt`](../raw/experiments/frontend-three-smoke/smoke.resources.txt)。

### 4.3 坐标、精度与实例布局

后端统一保留整数微单位，例如尺寸与坐标用 `int64` 微米或毫米量化值。渲染时再缩放成 Three.js 浮点场景：

| 求解模型 | Three.js | 说明 |
|---|---|---|
| `x`：承载器长度方向 | `scene.x` | 门/车头方向另存语义，不靠正负号猜 |
| `y`：承载器宽度方向 | `scene.z` | Three.js 默认 Y-up |
| `z`：高度 | `scene.y` | 重力方向是 `-scene.y` |
| 放置原点 `(x,y,z)` | box center `(x+l/2, z+h/2, y+w/2)` | 再乘单位缩放 |
| `pose_id`/四元数 | instance matrix | 面语义和 pose id 同时保留 |

前端不能只按长宽高排列推断姿态；立方体旋转后尺寸相同但 `top/front` 面可能不同。每个 instance 保存稳定 `item_instance_id`、`placement_id`、`pose_id`，颜色和拾取都通过 id 映射，不能依赖数组顺序长期不变。

渲染策略：同一几何/材质/SKU 组用 `InstancedMesh`；边线只给选中、问题项和当前步骤生成；标签只显示选中/搜索结果，不能给每个箱体常驻 DOM 标签；透明容器壁单独渲染，默认使用剖切而不是把全部货物半透明，以避免透明排序噪声。

## 5. 推荐进程与模块架构

```text
                    +-----------------------------+
                    | React/TypeScript desktop UI |
                    | tables / compare / Three.js |
                    +--------------+--------------+
                                   | narrow Tauri commands + Channel
                    +--------------v--------------+
                    | Tauri Rust core             |
                    | ACL, dialogs, job supervisor|
                    | path scope, update, crash   |
                    +--------------+--------------+
                                   | versioned stdio protocol
                    +--------------v--------------+
                    | Python worker               |
                    | application service         |
                    | model / adapters / validator|
                    +------+------+---------------+
                           |      |
            in-process API |      | optional child protocol
       +-------------------v--+  +-v--------------------+
       | Python/C/C++/Rust    |  | Java/native sidecar  |
       | bindings and solvers |  | only selected engines|
       +----------------------+  +----------------------+
```

### 5.1 代码边界

建议仓库最终分为：

```text
packages/
  packing-core/          # Python 领域模型、application service、验证器、engine adapters
  packing-cli/           # 只依赖 packing-core
  packing-worker/        # stdio 协议与 job lifecycle
  packing-api/           # 可选 FastAPI 服务，不被桌面默认启动
apps/
  desktop-ui/            # React/TS/Three.js
  desktop-shell/         # Tauri Rust core
schemas/
  problem.schema.json
  solution.schema.json
  worker-protocol.schema.json
```

领域模型研究稿提出的 Catalog + Task + Rule Profile + Solution + Validation Report 应是唯一真相。Python/Pydantic 生成 JSON Schema；TypeScript 类型从冻结的 schema 生成；前端 Ajv 提供即时校验，但 Python 仍做权威校验。每个 artifact 带 `schema_version`，迁移是显式命令，不在读取时静默改义。

### 5.2 Worker 协议

推荐每行一个完整 JSON envelope，控制消息保持小而有界：

```json
{"protocol":"packing-worker/1","id":"req-17","type":"solve.start","job_id":"job-42","payload":{"problem_path":"...","profile_id":"balanced","seed":7,"time_limit_s":120}}
```

worker 回应：

```json
{"protocol":"packing-worker/1","id":"req-17","type":"accepted","job_id":"job-42"}
{"protocol":"packing-worker/1","type":"progress","job_id":"job-42","seq":18,"payload":{"phase":"search","elapsed_ms":8300,"best":{"cost":4200,"containers":3,"utilization":0.84},"bound":null}}
{"protocol":"packing-worker/1","type":"completed","job_id":"job-42","payload":{"run_manifest":"run/manifest.json","solution_count":8}}
```

关键规则：

- 启动先 handshake，拒绝不兼容 major；
- request/response 有 id，stream 有单调 `seq`，GUI 可检测丢失/乱序；
- 进度允许 coalesce，完成/失败/取消不能丢；
- `cancel` 先协作中止，超过 grace period 由 Rust kill 整个进程；
- 每个 job 独立工作目录，结果先写临时文件、fsync 后原子改名；
- placement 大数组不塞入频繁 JSON channel。manifest 只给路径、hash、计数和分页索引；
- 协议 stdout 不能打印库日志。无法控制的 native/Java stdout 在 adapter 内重定向；
- worker 崩溃时 Rust 记录 exit code/signal 和 stderr tail，保留已完成 candidate，提供“重新启动 worker”，不自动把未验证的半成品标为成功。

若后续 profiling 证明 JSON 解析成为瓶颈，可在协议 v2 对 placement page 引入 MessagePack/Arrow IPC；不能在没有测量前增加双协议复杂度。

### 5.3 Python、C/C++、Rust binding

Python worker 内定义统一 `EngineAdapter`：`capabilities()`、`validate_support(problem)`、`solve(problem, limits, progress, cancel)`、`normalize(raw)`。纯 Python、pybind11/Cython、PyO3/maturin、cffi/ctypes 都实现这个接口。

部署差异：

- Python wheel：按 Python minor/ABI 和平台锁定；
- pybind11/Cython/PyO3：必须为 Windows x64、macOS arm64/x64、Linux x64 等目标产 wheel，并用 `auditwheel`/`delocate`/Windows dependency inspection 检查动态库；
- Rust `abi3`/PyO3 可减少 Python minor 组合，但不能消除 OS/arch wheel；
- LGPL 动态库、商业 solver runtime、OpenMP runtime 各自检查重分发权、NOTICE 和冲突；
- native extension 无法由 Python 捕获 segmentation fault，因此独立 worker 是必要的故障域，不是额外绕路；
- 每个引擎声明线程、内存和可中止能力。父进程统一设置线程环境变量和 OS resource/job-object 限额，防止 solver 与 BLAS/OpenMP 过度订阅。

### 5.4 Java sidecar 的纳入门槛

Java 不应因为“有库”就进入默认安装包。只有同时满足以下条件才纳入：

1. 在统一问题集上产生现有 Python/native 引擎做不到或显著更好的可行性、约束覆盖、成本/装载率或求解时间；
2. 许可允许商业分发，依赖树和安全更新责任可接受；
3. 可提供稳定的非交互 CLI/服务 API，固定 seed、time limit、线程与内存；
4. 能被独立 validator 校核，而不是只能相信 Java 库自己的结果；
5. 增加的运行时和签名体积与收益相称。

实现为 Python worker 启动的二级 sidecar，继续使用有版本 stdio 协议。用 `jlink` 生成最小 runtime image 而非要求用户预装 Java；启动加 `-Xms/-Xmx` 和处理器数上限；stderr 单独采集。macOS/Windows 发布时对 JVM/JNI 等 Mach-O/PE 文件分别执行 OS code signing（macOS 还要公证）；若分发 JAR，则按需要用 `jarsigner` 或 release manifest hash 校验，不能把 JAR 当作 OS 签名对象。UI 只看到 engine id 和 capability，不知道它是 Java。这样将来移除或替换该引擎不会迁移前端和项目格式。

## 6. 本地安全模型

桌面应用处理的“本地文件”仍可能来自邮件、供应商或共享盘，不能默认可信。

### 6.1 最小权限

- WebView 不加载远程脚本、字体或模型；生产 CSP 至少 `default-src 'self'`，按 Three shader/worker 的实际需要逐项开放，禁止任意 `connect-src`；
- Rust capability 绑定具体 window label 和具体业务 command；不把 shell plugin 暴露给前端；
- 文件只通过系统对话框选择，Rust canonicalize 后授予单文件/目录 scope；项目中的相对路径不能逃逸项目根；
- UI 展示的 SKU、备注、路径、solver 日志全部作为 text，不使用未经清洗的 HTML；
- 导入解压设置文件数、单文件大小、总展开大小和递归层级上限；
- Python worker 默认无监听端口、无继承敏感环境变量、无任意命令模板；
- Tauri updater 的更新签名与 OS code signing 是两层不同校验，都要配置，私钥只在发布环境；
- crash report 默认去除项目内容、绝对路径和货主信息，上传必须获用户明确许可。

### 6.2 若需要 HTTP API

GUI 默认仍走 stdio。只有外部系统集成时显式启动 `packd`：

- 本机模式绑定 `127.0.0.1` 随机端口，启动时生成高熵 bearer token，通过继承 pipe/受限文件传给授权客户端；
- 多用户/远程模式作为独立服务部署，TLS、身份认证、租户隔离、队列和审计都由服务端实现；
- 不能把无认证的 FastAPI 端口随着桌面应用常驻；
- OpenAPI 与 CLI/worker 共享 DTO 和 application service，但 transport-specific 字段不进入 ProblemSpec。

## 7. 产品信息架构

### 7.1 顶层导航

桌面应用打开后直接进入工作区，不做 landing page。左侧窄导航固定为：

1. **项目**：任务、版本、最近运行；
2. **目录**：货物类型、承载器类型、姿态、辅材、设备；
3. **规则**：约束配置、目标配置、法规/企业规则包；
4. **求解运行**：队列、当前运行、历史与复现；
5. **方案**：候选比较、3D 检查、验证和审批；
6. **导入导出**：映射模板、批次历史、报告；
7. **设置**：单位、引擎、资源限额、更新、许可证。

“帮助用户完成任务”的提示放在字段错误、空状态和 issue detail 中，不在页面堆大段功能介绍。

### 7.2 主工作流

```text
创建/导入任务
      |
      v
预检与单位归一化 --> 修正数据/映射
      |
      v
编辑承载器、货物、姿态、堆码、作业约束
      |
      v
选择目标、引擎组合、时间/资源预算
      |
      v
运行并观察可行解/界/告警 --> 可取消、追加时间、派生运行
      |
      v
多方案 Pareto 比较 --> 3D、表格和 validator issue 联动检查
      |
      v
批准方案 --> 装载顺序、清单、报告、JSON/CSV/glTF 导出
```

用户可保存任一步的草稿；但“可批准”只在输入版本、引擎、seed、validator 版本和验证报告都固化后出现。

## 8. 核心界面原型

### 8.1 任务编辑器

建议使用顶部项目/任务 breadcrumb，中间是全宽表格，右侧是当前行 inspector；不要把页面区块做成多层卡片。

```text
+--------------------------------------------------------------------------------+
| 项目 / 任务 A          [预检 12] [保存]                      单位:mm / kg       |
+-----------+--------------------------------------------------------------------+
| 货物      | SKU | 数量 | L | W | H | 重量 | 姿态 | 承压 | 站点 | 状态         |
| 承载器    | ... 可冻结列、筛选、批量粘贴、虚拟滚动、行级错误 ...              |
| 约束      |                                                                    |
| 目标      |------------------------------------------------+-------------------|
|           |                                                | 当前行检查器      |
|           |                                                | 面语义/允许姿态   |
|           |                                                | 支撑/承压/来源    |
+-----------+------------------------------------------------+-------------------+
```

表格必须支持：

- CSV/XLSX 导入预览、字段映射、单位识别和失败行下载；
- 从电子表格复制/粘贴矩形区域、填充柄或批量赋值、undo/redo；
- 固定 id/name/状态列，列显隐、保存视图、数万行虚拟化；
- cell 即时格式校验，row 聚合业务校验，顶部问题计数；点击问题定位 cell；
- 数值字段显示单位但内部传 canonical integer；小数精度和 rounding policy 可见；
- 类型数量与 serialized item 分开，用户可展开个体例外；
- 未知值不是 `0`；使用明确的空值/待确认状态；
- 导入数据保留 source、时间和原始值，人工修改可追踪。

姿态编辑器显示一个有 `top/front/left` 面标记的可旋转立方体，旁边是 24 个 face-aware 正交姿态的复选网格；常用策略用 segmented control：直立、允许平放、六种尺寸排列、专家姿态集。离散斜角用角度列表；连续角区间放专家模式并明确需要哪些引擎/验证能力。

约束编辑不做一个无穷表单。按几何、承压/支撑、质量/重心、作业顺序、兼容/环境、空隙/固定分 tab。每条规则同时展示：HARD/SOFT/INFO、PRECHECK/IN_SOLVER/POSTCHECK/SIGNOFF、参数来源和当前 engine 支持状态。`POSTCHECK HARD` 失败仍淘汰方案，不能因求解器未内建就变黄提示。

### 8.2 求解设置与进度

求解前展示 capability matrix：所选问题中的每类 hard constraint 是“求解内保证、求解后验证、该引擎不支持”。不支持 hard constraint 时禁止开始，除非另一个组合阶段有权威验证且失败会淘汰。

用户设置：目标优先级/epsilon 或 lexicographic 顺序、容器供给、引擎/portfolio、time limit、CPU threads、memory、seed、候选上限。高级引擎参数折叠在 engine namespace 中，并随 run manifest 固化。

运行页需要：

- phase、elapsed、剩余预算、CPU/RSS、worker 状态；
- 当前最好可行方案的总价、容器数、漏装、利用率、重心/作业指标；
- 若算法有合法 bound，显示 gap；没有 bound 就显示“无可证明界”，不能拿启发式估计冒充 gap；
- 候选到达时间轴与指标变化；
- 暂停只在引擎真支持 checkpoint 时提供，否则只有取消；
- 取消后明确区分 `cancelled_with_candidates` 与 `cancelled_no_solution`；
- worker crash、OOM、timeout、用户取消和 infeasible 是不同终态。

### 8.3 多方案与 Pareto 比较

方案列表第一列固定可行状态与 validator 版本，后面是总价、箱型数量、总容器数、未装必需件、体积/重量利用率、重心偏差、倒货、固定需求、求解时间。可 pin 2-4 个方案并看逐项 delta。

Pareto 图用两个可选轴、颜色和大小编码第三/第四指标，但硬不可行方案不进入 Pareto front。默认轴建议总成本 vs 容器数/利用率，用户可切换；hover 联动 3D 缩略状态和容器构成。避免生成未经业务归一化的“综合分 87”。

比较页同时展示箱型用量差：

| 箱型 | 方案 A | 方案 B | 差值 | 数量上限 | 成本影响 |
|---|---:|---:|---:|---:|---:|
| 40HC | 2 | 1 | -1 | 3 | -X |

再展示新增/移除/姿态改变/换箱的货物实例集合。点击差异直接选中对应 3D 实例。

### 8.4 3D 方案检查器

主视图是全宽、无装饰框的 3D 工作面；左侧为容器树/步骤，右侧为 selection/issue inspector，底部为装载时间轴。工具栏用图标与 tooltip：透视/正交、六向视图、适配、测量、剖切、隐藏/隔离、容器壁、重心、支撑、问题、截图。

必须实现：

- orbit/pan/zoom，单击拾取、框选、按 SKU/批次/站点搜索；
- 容器、层、SKU、站点、问题类型的隐藏/ghost/isolate；
- X/Y/Z 三轴剖切 slider，剖切位置可输入精确数值；
- 装载步骤播放、逐件/逐批前进、跳到 issue；时间轴不改变最终坐标；
- 可选爆炸视图按容器、层或步骤分离实例；它只改变展示偏移，不修改权威坐标或验证结果；
- 选中件显示实例 id、尺寸、质量、pose、位置、直接支撑、上方传递载荷、站点和来源；
- 统一 issue visual spec：碰撞红、越界橙、姿态黄、超重/承压紫红；同件多问题用 badge 列表、叠加 outline/hatch 和 inspector 表达，不能用最后一种填充色覆盖前一种；
- 碰撞显示 collision pair 与穿透面，支撑/承压显示 support footprint 和 load path；物品显示 top/front 面标记或局部轴，使对称件的禁姿态仍可检查；issue list 与 3D 双向联动；
- 箱体重心、总重心、允许包络、轴/地板载荷 overlay；没有数据时不画“安全绿色”；
- 门、障碍物、keepout、冷机/轮拱等使用不同几何语义，不能当普通货物；
- 顶/侧/端 2D 正投影，可带坐标、编号和装载顺序打印；
- glTF 仅作为交流视图导出，权威方案仍是带 schema/hash 的 JSON 和验证报告。

如果算法只给最终布局、没有做门通过和无碰撞装入路径，播放的只是“展示顺序”，界面必须标成 `layout animation`，不能称“可执行装载路径”。只有 path validator 通过后才显示 `executable loading sequence`。

### 8.5 报告与审批

审批前固定：problem hash、catalog/rule revision、engine/version、seed、limits、solution hash、validator/version、所有 hard issue、人工 signoff。批准是新 revision，不能修改原 run。

导出至少包括：

- PDF：执行摘要、容器用量与成本、每箱装载清单、六向/分层图、步骤、问题和免责声明；
- CSV/XLSX/JSONL：每个 placement 的 container、position、orientation、load step、stop；这些是由 manifest 绑定 canonical JSON 的明细/流，不能脱离 problem/solution hash、单位、预期件数和 validator/version 单独作为有效证书；
- JSON：完整 ProblemSpec/Solution/ValidationReport 与 schema version；
- glTF/PNG：只作可视化交换；
- Parquet：用于实验分析和归档的派生表；Arrow IPC 只在 profiling 证明 JSON 分页传输是瓶颈后作为协议 v2，不替代 JSON 权威结果；
- job bundle：输入、配置、日志摘要、候选 manifest、最终报告和 checksums，支持离线复现。

## 9. 前端具体技术栈

建议：

| 关注点 | 选择 | 原因 |
|---|---|---|
| UI | React + TypeScript + Vite | 团队和生态广，Tauri/Electron 可复用 |
| 组件基础 | React Aria/Radix 一类无样式可访问 primitives + 自有密集主题 | 避免被网页卡片风格绑架；菜单、dialog、tooltip、focus 由成熟 primitive 处理 |
| 表格 | TanStack Table + TanStack Virtual，编辑层自建 | MIT、headless、能严格按领域状态建模；若采购预算允许，可 PoC AG Grid Enterprise 的批量编辑/Excel 能力 |
| Schema | Python Pydantic -> JSON Schema；TS codegen + Ajv runtime validation | 同一契约、前后端都能报告路径化错误 |
| 状态 | Zustand/Redux Toolkit 二选一；server/run state 与 unsaved form state 分离 | 避免把 3D scene 和大 placement 数组塞进全局响应式树 |
| 3D | Three.js direct scene controller | 实例、拾取、剖切可精细调优；React 只传选择/过滤意图 |
| Pareto/图表 | Apache ECharts 或轻量定制 Canvas/SVG | scatter、tooltip、brush 成熟；按实际 bundle tree-shake |
| 测试 | Vitest + Testing Library + Playwright；每 OS packaged smoke | 浏览器逻辑与桌面壳分层验证 |

不要默认引入 react-three-fiber。它适合声明式场景，但本产品的大量实例矩阵、颜色 buffer 和步骤增量最好由一个有明确生命周期的 Three scene controller 管理，避免 React reconciliation 进入热路径。原型后若证明其不会造成性能/调试负担，再重新评估。

视觉上采用安静、工作导向的中性底色，错误/警告/可行状态使用独立语义色，不做单一蓝紫色主题。表格与 3D 是主角；card 只用于重复实体或 modal，不把 section 做成浮动卡片，也不嵌套 card。桌面默认信息密度高，但所有工具栏、计数器和表格轨道使用稳定尺寸，防止加载文字或长 SKU 推动布局。

## 10. CLI 与自动化 API

CLI 名称示例为 `packctl`：

YAML 是便捷导入格式，不是规范存储。导入器必须拒绝重复 key、隐式日期/布尔值等 YAML 歧义，完成单位换算和默认值展开，输出带 `schema_version` 的 canonical ProblemSpec JSON；后续 hash、求解和复现都绑定该 JSON。

```bash
packctl project import job.yaml --out job.json
packctl project validate job.json --format json
packctl solve job.json --profile balanced --engine portfolio --time-limit 120s --threads 4 --seed 7 --out run-001
packctl verify run-001/solution.json --problem job.json --strict
packctl inspect run-001 --solutions --format table
packctl export run-001/solution.json --format pdf --out load-plan.pdf
packctl engines list --capabilities
packctl schema print problem --version 1
```

CLI 规则：

- 交互友好的日志写 stderr；`--format json` 的机器结果只写 stdout；
- 长任务可用 `--progress ndjson` 在 stderr 或指定 fd 输出，不能破坏最终 JSON；
- `SIGINT` 触发协作取消并保存已验证候选，再次中断才强杀；
- exit code 稳定：`0` 成功且有合格解，`2` 输入无效，`3` 无可行解，`4` timeout/cancel 且无合格解，`5` engine/worker 故障，`6` 验证失败；具体表写入 CLI 契约；
- manifest 固化 effective config、env 中非敏感求解参数、引擎 binary hash、seed 和资源限制；
- GUI 的“复制 CLI 命令”从 run spec 生成，保证可复现；反向也能从 run bundle 在 GUI 打开。

FastAPI 只作为可选 `packing-api` transport，资源模型建议：

```text
POST   /v1/problems:validate
POST   /v1/jobs
GET    /v1/jobs/{id}
POST   /v1/jobs/{id}:cancel
GET    /v1/jobs/{id}/events       # SSE/WebSocket，仅服务模式
GET    /v1/jobs/{id}/solutions
GET    /v1/solutions/{id}
POST   /v1/solutions/{id}:verify
POST   /v1/solutions/{id}:export
```

桌面 command、CLI、HTTP controller 都只调用同一 application service，不各自调用 solver。这样 C++/Rust binding 或 Java adapter 的加入不会改变三个入口的行为。

CLI 发布提供两种明确渠道：Python 环境用户安装 signed wheel/lock 后得到 `packctl`；无 Python 环境的操作员下载每平台独立签名的 standalone CLI。桌面包内部的 worker executable 不是公共 CLI 路径，不能让脚本依赖应用安装目录；CLI 和 worker 可复用同一构建输入，但有各自入口、版本输出和 release artifact。

## 11. 发布、签名与更新

### 11.1 构建矩阵

至少建立：

| 平台 | 首发目标 | 构建/分发 | 特别验证 |
|---|---|---|---|
| Windows | Windows 10/11 x64 | 原生 runner，NSIS/MSI，Authenticode | WebView2 最低版本/离线安装、SmartScreen、长路径、GPU blacklist |
| macOS | 当前受支持的 macOS arm64；x64 单独包 | macOS runner，`.app` + DMG，Developer ID 签名、公证、staple | nested Python/dylib 全签名、Gatekeeper、arm64/x64；确认是否做 universal2 |
| Linux | 明确列出的 Ubuntu LTS/Fedora 等 x64 | 对应老 glibc 基线构建，AppImage + deb/rpm 按客户选择 | WebKitGTK 4.1、Mesa/NVIDIA、Wayland/X11、字体、沙箱/挂载限制 |

Tauri 官方分发文档提供 Linux 包、DMG/App Store、Windows installer/Store 与签名入口 [F12]；macOS 外部分发需签名和 notarization，Windows 未签名虽可能运行但会有 SmartScreen 信任问题 [F14-F15]。官方 GitHub pipeline 示例本身也是 macOS、Ubuntu、Windows matrix [F16]。因此不要宣称“一台 Linux 交叉编译全部桌面包”。

Python/native wheel、Tauri shell、Web assets 和可选 JVM 必须在同一 release manifest 中有 SHA-256 与 SBOM。生成第三方 NOTICE；LGPL 路线保留相应源码/offer、动态替换权和许可证文本。Qt 官方也明确说明 LGPLv3 的动态链接、用户替换/逆向权、通知与源码提供义务，不能只在 About 页写一句 Qt [F6]。

### 11.2 Python worker 打包取舍

先对同一 worker 做两个受控产物：

- **PyInstaller onedir**：生态 hooks 成熟，启动无 onefile 解压；目录中文件多但便于检查、签名和增量定位；
- **Nuitka standalone**：可能改善源码分发和部分启动/性能，但编译时间、插件兼容与商业 edition 功能要实测；PySide 官方 deploy 也基于 Nuitka [F2]。

验收测：冷/热启动、空任务 RSS、10k placement 序列化、每个 solver import、取消、崩溃、签名、公证、杀毒误报、安装包大小。最终选择基于每 OS 的成品，不基于打包器宣传。`onefile` 仅在运维明确要求单文件时评估。

### 11.3 更新

应用更新与 solver 数据/规则包更新分开：

- 应用更新：签名 manifest、分阶段 rollout、可回滚到上一兼容版本；
- engine/plugin：只加载 release manifest 允许的签名/hash，版本能力写入 run；
- 法规/企业规则包：内容签名、authority、effective date、不可静默覆盖历史 run；
- schema migration：可预览、备份、生成新 project revision；
- 离线环境允许导入签名 update bundle。

## 12. 性能与可用性预算

第一版就设预算，原型验证后再调整：

- UI 输入响应 p95 < 100 ms；滚动不因 cell 校验阻塞；
- 求解进度刷新 5-10 Hz，CPU/RSS 采样 1 Hz；
- 10k placements 首次构建场景目标 < 1 s，拾取 p95 < 50 ms；50k 使用实例化和按容器加载；
- 不在 channel 上每帧传完整方案；候选 geometry 只在选中时加载；
- 关闭方案视图时显式 dispose geometry/material/texture，检测 GPU context loss；
- 表格只渲染 viewport + overscan；筛选/排序可在 Web Worker 或后端分页，视数据量测量；
- Python worker 的 CPU/内存上限由 run spec 与 OS 机制共同执行；Tauri UI 始终保留至少一个响应核；
- Java sidecar 必须有 `-Xmx`，native/BLAS/OpenMP 有线程上限，portfolio 不允许每个引擎各占满机器。

3D 是辅助通道：所有选中项、问题和步骤都能在表格/树中访问；色觉缺陷用户不仅靠红绿，状态还用图标、线型和文字。键盘可在问题列表、实例树和步骤间移动；3D canvas 无法表达的信息有等价 inspector。

## 13. 测试与验收

### 13.1 分层测试

1. **契约**：Problem/Solution/Worker schema golden files；Python/TS/Rust 对同一 fixtures 编解码；旧 minor 可读、新 major 明确拒绝。
2. **UI 单元**：单位换算、批量粘贴、undo、字段错误定位、run 状态机、issue filtering。
3. **3D 几何映射**：已知 placement 的中心、pose、面朝向、拾取 id、剖切、层过滤与截图像素基线。
4. **worker 故障**：syntax/log pollution、半行 JSON、seq gap、timeout、SIGTERM、segfault、OOM、Java crash；UI 不挂死且不误报成功。
5. **浏览器级 E2E**：Playwright 测 React 工作流和 WebGL screenshot，不依赖 Tauri 壳即可快速回归。
6. **打包级 E2E**：每 OS 真机安装、启动、导入、运行小实例、3D 操作、导出、卸载、升级和签名验证。
7. **兼容性矩阵**：WebView2/WKWebView/WebKitGTK 的最低与当前版本、Intel/Apple Silicon、Wayland/X11、常见集显/独显。

### 13.2 决策门

在正式锁定 Tauri 前做 2-3 周 vertical slice，必须同时通过：

- 50k 货物行的导入/校验/虚拟表格；
- 10k/50k 箱体 Three.js 实例化、拾取、剖切、步骤和 issue 联动；
- Python worker 启动/取消/强杀/崩溃恢复；
- 一个 pybind11/PyO3 或现有 native solver 的实际打包；
- Windows/macOS/Linux 各一份签名或开发签名成品安装；
- 最低支持 Linux 机器的 WebKitGTK/GPU 验证。

若只有 Linux WebView 3D 稳定性未通过，先尝试固定支持发行版、驱动 workaround 和渲染降级；仍无法达到门槛时，切 Electron，保留 React/Three/Python 协议。若 Web 技术整体不被团队接受且已批准 Qt 商业许可，再切 PySide6 + Qt Quick 3D。不要在产品中长期维护 Tauri、Electron、Qt 三套 GUI。

## 14. 建议实施顺序

1. 固化 Problem/Solution/ValidationReport JSON Schema 与 Python application service；先做 CLI。
2. 实现 worker protocol、取消、资源限制、run bundle；用假 solver 和一个真实 solver 做 fault tests。
3. 做 Tauri vertical slice：导入表、求解进度、候选列表、10k/50k Three instances。
4. 完成目录/任务/约束编辑与独立 validator issue 联动。
5. 完成 Pareto 比较、3D 分步/剖切/拾取、PDF/CSV/JSON 导出。
6. 建立三平台 CI、签名、公证、SBOM、更新和真实 GPU 测试池。
7. 只有算法基准证明价值后，增加 native/Java engine plugin；每个新 engine 都通过同一能力声明和验证器。

这个顺序保证即使 GUI 选型后来从 Tauri 改成 Electron/PySide，Python 模型、CLI、算法适配器、验证和 run artifacts 都不会推倒重来。

## 15. 官方证据与维护状态

以下版本是本研究在 2026-08-31 核查或固定的版本，不等同于各项目当前 latest；产品应在 lockfile 和 release manifest 固定实际版本。

| 项目 | 2026-08-31 可核实版本/状态 | 许可 |
|---|---|---|
| PySide6 | PyPI 6.11.2，上传于 2026-08-18 [F33]；官方仓库维护状态见 [F36] | LGPLv3/GPLv3/Qt Commercial [F1] |
| Tauri | 2.11.5，2026-07-01 release；官方仓库持续更新 [F17] | MIT OR Apache-2.0 |
| Electron | 44.0.0，2026-08-25 release [F22] | MIT |
| Flutter | stable 3.47.2，2026-08-27 [F25] | BSD-3-Clause [F26] |
| Flet | 0.86.5，2026-08-01 [F28] | Apache-2.0 |
| Three.js | r185/0.185.x，2026-07 release [F30] | MIT |
| VTK | PyPI 9.7.0，2026-08-15 [F34] | BSD-style [F32] |
| PyVista / PyVistaQt | 0.48.x / 0.12.0，按 2026-08-31 PyPI 元数据核查 [F34] | MIT |

### Qt / PySide

- [F1] Qt for Python overview（许可声明）: https://doc.qt.io/qtforpython-6/
- [F2] `pyside6-deploy` 官方部署文档: https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html
- [F3] Qt 6 supported platforms: https://doc.qt.io/qt-6/supported-platforms.html
- [F4] Qt Quick 3D 官方文档、功能与许可: https://doc.qt.io/qt-6/qtquick3d-index.html
- [F5] Qt 3D 官方文档、平台与许可: https://doc.qt.io/qt-6/qt3d-index.html
- [F6] Qt 官方 LGPL/GPL obligations: https://www.qt.io/licensing/open-source-lgpl-obligations

### Tauri

- [F7] 官方 sidecar 文档: https://v2.tauri.app/develop/sidecar/
- [F8] 官方 process model: https://v2.tauri.app/concept/process-model/
- [F9] 官方 IPC 概览: https://v2.tauri.app/concept/inter-process-communication/
- [F10] 从 Rust 调前端、Event 与 Channel: https://v2.tauri.app/develop/calling-frontend/
- [F11] 安全模型与 capabilities: https://v2.tauri.app/security/ 和 https://v2.tauri.app/security/capabilities/
- [F12] 分发总览: https://v2.tauri.app/distribute/
- [F13] 三平台前置依赖与系统 WebView: https://v2.tauri.app/start/prerequisites/
- [F14] macOS 签名与公证: https://v2.tauri.app/distribute/sign/macos/
- [F15] Windows code signing: https://v2.tauri.app/distribute/sign/windows/
- [F16] 官方 GitHub Actions pipeline: https://v2.tauri.app/distribute/pipelines/github/
- [F17] Tauri 官方仓库、release 与许可证: https://github.com/tauri-apps/tauri 和 https://github.com/tauri-apps/tauri/releases/tag/tauri-v2.11.5

### Electron / Flutter / Flet

- [F18] Electron security checklist: https://www.electronjs.org/docs/latest/tutorial/security
- [F19] Electron packaging（官方推荐 Forge）: https://www.electronjs.org/docs/latest/tutorial/application-distribution
- [F20] Electron code signing: https://www.electronjs.org/docs/latest/tutorial/code-signing
- [F21] Electron release timeline/support policy: https://www.electronjs.org/docs/latest/tutorial/electron-timelines
- [F22] Electron 44 release 与官方二进制 assets: https://github.com/electron/electron/releases/tag/v44.0.0
- [F23] Flutter desktop support: https://docs.flutter.dev/platform-integration/desktop
- [F24] Flutter native code/FFI: https://docs.flutter.dev/platform-integration/bind-native-code
- [F25] Flutter 官方 release manifest: https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json
- [F26] Flutter 官方仓库与 BSD 许可: https://github.com/flutter/flutter
- [F27] Flet 官方发布/打包文档: https://flet.dev/docs/publish/
- [F28] Flet 官方仓库和 release: https://github.com/flet-dev/flet 和 https://github.com/flet-dev/flet/releases/tag/v0.86.5
- [F29] Flet 官方 user extension 文档: https://flet.dev/docs/extend/user-extensions

### 3D 与发行包体

- [F30] Three.js 官方 docs、仓库、release 与 MIT 许可: https://threejs.org/docs/ 、https://github.com/mrdoob/three.js 、https://github.com/mrdoob/three.js/releases/tag/r185
- [F31] PyVista/PyVistaQt 官方文档与仓库: https://docs.pyvista.org/ 、https://qtdocs.pyvista.org/ 、https://github.com/pyvista/pyvista 、https://github.com/pyvista/pyvistaqt
- [F32] VTK 官方版权/许可: https://vtk.org/about/#license 和 https://gitlab.kitware.com/vtk/vtk/-/blob/master/Copyright.txt
- [F33] PySide6/PySide6-Essentials/PySide6-Addons 官方 PyPI 发行元数据: https://pypi.org/project/PySide6/ 、https://pypi.org/project/PySide6-Essentials/ 、https://pypi.org/project/PySide6-Addons/
- [F34] VTK/PyVista/PyVistaQt 官方 PyPI 发行元数据: https://pypi.org/project/vtk/ 、https://pypi.org/project/pyvista/ 、https://pypi.org/project/pyvistaqt/
- [F35] `flutter_3d_controller` pub.dev 平台元数据: https://pub.dev/packages/flutter_3d_controller
- [F36] PySide 官方仓库与提交记录: https://github.com/pyside/pyside-setup
