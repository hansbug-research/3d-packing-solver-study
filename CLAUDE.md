# 研究仓库工作约定

本仓库的评审对象是证据链。每个公开结论都要能回到论文/官方文档、原始实验输出或源码审计；只有通过独立 validator 的布局才算可行。启发式 incumbent、求解器 bound 和已证明最优必须分别标注，不能用体积利用率掩盖漏件或约束违规。

正文使用中文自然段，段落内部不硬换行；命令、字段名、路径、报错和代码保持原样。数字、日期、版本、单位、责任主体和引用标题是 protected spans，润色时不得改变。新增实验必须固定输入、版本、seed、时间/内存/线程限制，并把 stdout、stderr、退出码和资源记录写入 `raw/`。

默认资源门：Python/C++ 外层 timeout 35 s、虚拟内存 4 GiB、常见数值库单线程；PackingSolver 子任务 10 s/1 GiB；Java `-Xmx512m -XX:ActiveProcessorCount=1`。更改门禁或数据格式时必须同步更新 `audit/` 和 `REVIEW.md`。
