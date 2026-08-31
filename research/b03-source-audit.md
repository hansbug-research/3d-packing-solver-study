# B03 Egeblad-Pisinger 来源审计

B03 使用 HansBug/PackingSolver 固定提交 `d953148b8f710c06fa6c410949b7272f9e36327b` 中的 `data/box_raw/egeblad2009` 与 `data/box/egeblad2009`。原始格式文件署名 Jens Egeblad，生成器头部署名 David Pisinger 与 Jens Egeblad；相关论文为 Egeblad 与 Pisinger 2009 年的 two- and three-dimensional knapsack packing 工作。PackingSolver 在提交 `03b1e218df45be5e5f33fee1b7901b97610718e1` 加入 3D 原始数据和转换，在提交 `9d83d632edf5686823bb7b5b51e6e3a7dd641234` 加入 benchmark 参照表。

输入由 3 个件数档、5 个形状类、clustered/random 和 50/90 容量档的笛卡尔积组成，共 60 例。逐行审计确认原始 `.3kp` 与转换后的 items/bins CSV 在尺寸、profit 和 copies 上一致。items CSV 没有旋转列，而 PackingSolver 对未声明旋转的 item 默认只允许 `XYZ`，因此 B03 原题轨固定为 `FIXED_XYZ`；允许全部六种正交姿态的结果必须另记 `RELAXED_ALL_ROTATIONS`，不能和原题混排。

PackingSolver 的参照表列名是 `Best known solution value`，不是 optimum 或 proven bound，而且只含 57/60 例。缺少的三个实例为 `ep3d-60-U-C-90.3kp`、`ep3d-60-U-R-50.3kp`、`ep3d-60-U-R-90.3kp`。更严重的是，57 条中有 48 条低于对应实例单个最大 profit 物品的值，因此不可能是当前 3D corpus 的 best-known。该表整体标记为 `INVALID_REFERENCE_TABLE`，原值仅用于上游缺陷审计，禁止计算 gap 或参与排名；所有 60 例只报告合法 incumbent、solver bound 和 exact 轨能够独立证明的结果。

作者生成器的容器适配循环把局部变量 `d` 赋成 `items[i].h`，而不是 `items[i].d`。对已提交的 60 例逐件检查没有发现固定姿态尺寸超过容器，因此现有 corpus 不因该代码缺陷失效；该结论不代表重新生成不同参数时仍安全。生成器和数据没有找到独立数据集许可证，本仓库不复制完整 corpus，只保存来源提交、逐文件哈希、结构摘要和实验输出；取回的数据仍受原始来源条款约束。

机器可读索引由 `benchmarks/comprehensive/audit_b03_source.py` 生成到 `benchmarks/data/comprehensive/b03-source-index.json`。索引固定 60 个实例的原始/转换哈希、容器、件数、总 profit、无效参照状态和整体 corpus hash；正式 runner 在执行前再次逐文件核验。
