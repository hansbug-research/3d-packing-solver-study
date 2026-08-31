# 真实装载工况、问题定义与数据元模型

> 调研日期：2026-08-31。本文讨论的是能形成可执行装载计划的数据与约束，不等同于承运人批准、危险品申报、结构计算或法规合规证明。所有法规规则必须按实际运输方式、司法辖区、路线和生效版本复核。

## 1. 结论先行

这个产品不能只把问题建模成“若干长方体放进一个大长方体”。真实业务至少有五层：

1. **几何层**：容器、门、障碍物、禁入区，货物外形、间隙与允许姿态；
2. **力学层**：质量、局部地板载荷、承压、支撑、稳定性、重心、轴荷、运输加速度与系固；
3. **作业层**：装卸门、装入路径、设备可达性、多站点顺序、少倒货、分组与装载班次；
4. **环境与合规层**：危险品、温区、通风、防潮、食品/气味污染、检疫和运输方式规则；
5. **经济与不确定性层**：箱型数量上限、使用价格、漏装代价、测量误差、安全余量和数据可信度。

建议采用“**目录 + 任务 + 规则配置 + 方案 + 校核报告**”五部分模型，而不是一个巨大的 `Box` 类。求解器只消费已经归一化的 `ProblemSpec`；GUI、CLI 和导入器共用同一 JSON Schema；结果必须再交给与启发式算法独立的验证器重算。

另一个关键设计是把两个维度分开：

- **业务语义**：`HARD`（不满足则方案不可执行）、`SOFT`（允许违反但计入代价）、`INFO`（仅提示）；
- **执行阶段**：`PRECHECK`、`IN_SOLVER`、`POSTCHECK`、`OPERATOR_SIGNOFF`。

例如危险品隔离是 `HARD`，即使第一版只能在 `POSTCHECK` 中验证，失败也必须淘汰方案，绝不能因为它不在核心装箱算法里就被降成软约束。

## 2. 问题定义与边界

### 2.1 优化问题属于什么

按切割与装箱问题的经典分类 [R1]，产品会同时覆盖几种不同问题，不能只叫“3D bin packing”：

| 业务意图 | 数学问题 | 必须装完 | 容器选择 | 常见主目标 |
|---|---|---:|---|---|
| 固定一个车厢，尽量多装 | 三维装箱/背包问题 | 否 | 固定 | 货值、优先级或体积最大 |
| 同型容器，全部装完且数量最少 | 三维 Bin Packing Problem | 是 | 同型无限/有限 | 容器数最少 |
| 多种箱型、价格和数量上限 | 异型/变尺寸 Bin Packing | 是 | 多型有限或无限 | 总成本最小 |
| 一批车已经确定 | 多容器装载 | 通常是 | 实例固定 | 可行性、均衡和作业成本 |
| 带多站点配送 | Container Loading + Multi-drop | 是 | 固定或可选 | 车辆成本 + 倒货/访问成本 |

Wäscher 等的改进分类 [R1]适合定义顶层问题类型；Bortfeldt 与 Wäscher 的综述 [R2]则系统整理了真实集装箱装载中的方向、承压、稳定性、载荷分布、完整装运、分组、隔离、多站点和优先位置等约束。产品接口应显式声明 `problem_kind`，否则相同数据在“必须全装”和“允许挑选”两种语义下会产生完全不同的结果。

### 2.2 基本决策变量

对货物实例 `i`、承载器实例 `b` 和承载器类型 `t`，核心决策包括：

- 是否选择/使用某个承载器以及各类型数量 `y_t`；
- 货物分配到哪个承载器 `a(i)`；
- 放置中心 `p_i=(x_i,y_i,z_i)`；
- 姿态 `R_i`，正交模式下是允许的有限姿态 ID，自由角模式下是旋转矩阵或四元数；
- 直接支撑关系、装载/卸载次序；
- 可选的隔板、衬垫、填充气袋、托盘和系固件配置。

至少要满足：数量、边界内、互不相交、姿态允许、质量/容量限制。其余约束不能都塞进一条几何可行性判断，应由分层规则和独立校核器处理。

### 2.3 正交旋转与“允许斜放”

正交长方体的六种轴向姿态只是三条边的排列；“不得倒置”通常不是简单的 `can_rotate=false`，而是允许六种姿态的一个子集。推荐用货物局部坐标面的语义标签表达：`top/bottom/front/back/left/right`，再列出允许的 `pose_id`。

任意斜角会把轴对齐长方体变成有向包围盒（OBB），碰撞、边界、门通过、接触支撑和承压都会变成连续非凸问题。实务上应优先采用三档策略：

1. `ORTHOGONAL_SET`：从 24 个带面朝向语义的立方体旋转中选允许姿态；长方体尺寸只有 6 种排列，但面朝向可能影响标签、开口和承压；
2. `DISCRETE_POSES`：工程师预先给出少量经验证的斜放姿态，例如绕局部 Y 轴 `15°/30°`；
3. `CONTINUOUS_ENVELOPE`：角度区间，仅给专用连续优化器使用，并要求 OBB/SAT 碰撞、真实接触和装入路径校核。

“斜放几何可行”并不等于“运输稳定”。连续姿态结果还必须验证重心投影、支撑面、摩擦/系固以及包装允许受力面。第一版主求解器宜完整支持前两档；第三档作为受控专家功能，不能用 AABB 不相交冒充 OBB 可行。

## 3. 典型真实工况

### 3.1 仓库、料箱与托盘

仓储场景的重点通常不是运输加速度，而是安全堆码、货架/库位载荷和取货可达性：

- 库位、周转箱、托盘、笼车和货架层均可作为 `LoadCarrier`，可以嵌套；
- 货架层有总载荷、每梁/每托位载荷，地面还有面载荷和点载荷；
- 纸箱需要面向相关的堆码上限、承压力、最大层数、最小支撑面积和最大悬空比例；
- 拣选面、条码面、开箱面可能必须朝向通道；叉车孔和托盘入口不得被遮挡；
- FIFO/FEFO、批次隔离、同订单聚类、补货/拣选优先级应作为作业规则，而非几何属性；
- 库位深处货物若被近处货物挡住，会产生重搬，需用可达性或取货顺序模型表达。

美国 OSHA 29 CFR 1910.176(b) 明确要求分层存放的物料应堆叠、垫块或联锁并限制高度，使其稳定且避免滑动或倒塌 [R3]。这说明“体积装下”不能替代稳定性和堆码规则。

### 3.2 卡车、厢式车和半挂车

道路运输至少增加以下约束：

- 额定载荷、最大总质量、前后/多轴轴荷及必要的最小转向轴荷；
- 车厢地板面载荷、轮压/点载荷、侧壁、前壁、后壁和系固点能力；
- 轮拱、冷机、立柱、尾板、卷帘门盒等障碍物；门洞常小于内部包络；
- 货物纵横向重心和整车重心范围，左右偏载；
- 急刹、转弯和颠簸下的滑移、倾覆与系固能力；
- 多站点配送的后装先卸、侧门/后门选择、倒货数量和卸货设备可达性；
- 线路对应的车高、车宽、总重与轴荷法规。

欧盟 Directive 2014/47/EU 附件 III 要求道路货物固定承受前向 `0.8 × 货重`、横向与后向 `0.5 × 货重`，防止倾覆，并在分配货物时考虑最大授权轴荷和必要的最小轴荷 [R4]。美国 49 CFR 393.102 对系固装置规定了前向 `0.8 g`、后向与横向 `0.5 g` 等性能条件，393.106(d) 还规定一般情况下系固件合计工作载荷限值至少为被固定货物重量的一半 [R5]。这些数值相近但条文结构、适用对象和例外不同，证明规则必须版本化，不能在算法里写成单一全球常数。

轴荷不能用“车厢左右各一半”替代。最少要接受制造商或承运人给出的载荷分布图/允许重心包络；已知支点几何时可通过静力反力计算，但多轴悬架、牵引座、整车空载轴荷和法定最小轴荷必须进入车辆配置。CTU Code 附件 7 也给出了刚性卡车和半挂车的载荷分布图示例，并指出最大货物质量通常只有在重心处于较窄范围时才能使用 [R6]。

### 3.3 海运集装箱与联运 CTU

ISO 箱的名义外形不应被硬编码为实际可用空间。每个箱型或实例还需要：

- 实测内部尺寸与门洞尺寸；波纹板、角柱、绑扎环等会侵入空间；
- 铭牌最大总质量、皮重、允许载荷、堆码/横向刚度信息；
- 地板轮载、集中载荷的铺垫要求，侧/端壁与门的承载能力；
- 箱门方向、开门安全空间、装卸设备和货物防坠挡门措施；
- 纵横向重心、偏载和联运各方式的载荷分布限制；
- 冷藏箱冷机、T 型地板、回风/送风禁入区、设定温度与通风；
- 海程温湿度变化、凝露、木质衬垫检疫和熏蒸状态；
- 货物与衬垫、系固材料加入后的准确总质量。

IMO/ILO/UNECE CTU Code 是这类模型最重要的公开基线。其关键要求包括正确的重心位置、避免偏心载荷、必要时填充空隙、危险品不相容隔离、温控设定、载荷分布、摩擦与系固计算 [R6]。CTU Code 还强调：原始“空白体积”本身不是固定需求的判据；要看货物可能滑动/倾覆的方向、空隙几何、接触面摩擦、运输加速度和边界强度。填充气袋的允许载荷取决于接触面积、爆破压力、间隙和安全系数，而不是一个 `max_void_volume` 字段。

集装箱最大总质量和堆码能力应来自该实例的 CSC 安全批准牌及适用规则 [R7]。海上运输还涉及 SOLAS 集装箱验证总质量（VGM）：装船前必须按批准方法取得并传递 VGM [R8]。求解结果里的理论质量只能辅助申报，不能代替称重/认可计算流程。

ISO 668 和 ISO 1496-1 分别定义系列 1 集装箱的分类/尺寸/额定值及通用货箱规范与试验 [R9][R10]；它们适合做箱型目录来源，但软件仍应允许运营方覆盖为具体设备实测值。标准正文通常需要授权，不能只根据营销尺寸表推断门、地板或墙体能力。

### 3.4 航空货运与 ULD

航空货运不能使用一个“标准机舱大箱子”模型。实际限制由机型、飞机配置、位置和运营人 Weight and Balance Manual（WBM）共同决定：

- 主/下货舱门洞、舱段和每个装载位置的轮廓；
- ULD 类型、底板、网罩/集装箱、锁止和适航状态；
- 每位置/舱段最大质量、面积载荷、线载荷、地板和滚轮限制；
- 纵向重心包线、横向不平衡、零燃油重量等航班级限制；
- ULD 与机型/位置兼容，缺失或失效锁止件造成的降载；
- 烟雾屏障、通道、消防/检查可达性，危险品的位置和隔离；
- 活性温控 ULD 的电源、预处理、运行与装载方向。

FAA AC 120-85B 明确把 WBM、ULD 轮廓、门洞、最大位置载荷、地板面积/线载荷、缺失锁止件限制和 W&B 流程作为运营人程序的一部分 [R11]。因此通用软件可以生成候选 ULD build-up 和位置分配，但只有导入运营人批准的数据并通过航班 W&B 系统后才可称为可执行。14 CFR 121.665 要求货物正确装载、分布和固定且不超过舱面结构限制 [R12]。

IATA ULD Regulations 汇集 ULD 技术和运营要求 [R13]，但属于受许可出版物。建议数据模型保留 `authority_document`、`operator_revision` 和 `aircraft_configuration_id`，而不是复制一个可能过期的全局 ULD 表。

## 4. 约束的可计算定义

### 4.1 箱型、数量、价格与需求

承载器类型不是单纯的尺寸：

- `availability.min_count/max_count`；`max_count=null` 表示无业务上限，JSON 中禁止 `Infinity`；
- `economics.fixed_use_cost`、币种、税费/附加费是否包含；
- 质量、几何、温控和合规能力；
- 可选实例列表，用于设备状态、位置或实际测量不同的情况。

货物需求应区分：

- `required_count`：必须装的有限整数；
- `optional_count` 和每件价值/未装惩罚：背包语义；
- `min_fulfilled_count`：允许缺货但有最低履约量；
- `serialised_items`：个体质量、尺寸、批次或危险品属性不同，不能只展开类型数量。

无限适合描述承载器供应上限，不适合描述一次求解要输出的货物数量。任务中的货物数量必须有限，否则无法生成有限方案。

典型词典序目标为：先最小化硬约束违反数（理论上必须为 0），再最小化未装必装件，再最小化总成本，然后优化容器数、装载率、重搬、重心偏差和衬垫量。不要把金额、危险品违规和毫米空隙未经量纲化直接加成一个加权和。

### 4.2 方向、翻转和姿态

建议字段：

```yaml
orientation_policy:
  mode: ORTHOGONAL_SET       # ORTHOGONAL_SET | DISCRETE_POSES | CONTINUOUS_ENVELOPE
  allowed_pose_ids: [UPRIGHT_0, UPRIGHT_90]
  max_tilt_from_up_deg: 5.0  # 运输状态，而非求解容差
  keep_face_up: local_top
  pose_catalog_ref: pose-catalog-v1
```

验证器必须比较完整姿态而不只是排序后的尺寸。例如立方体旋转后尺寸不变，但“此面向上”仍可能被违反。带液体、设备减震器、瓶装、带门/阀门物品通常需要 `keep_face_up`、最大倾角或禁止某些面受压。

### 4.3 承压、脆弱和支撑面积

单一 `max_weight_on_top` 只适用于保守的第一版。更可靠的模型应包含：

- 每个允许承载面的最大长期压缩力和局部压力；
- 试验方向、持续时间、温湿度、动态/老化安全系数和数据来源；
- 最小有效支撑面积比例、最大边缘悬空和允许支撑区域；
- 是否允许桥接多个下层件、托盘/隔板是否传播载荷；
- `do_not_stack`、最大层数、允许上层货物类别。

对放置 `i`，可以由接触面生成有向支撑图。最小几何稳定条件是重心竖直投影位于有效支撑区域的凸包内；更保守的业务条件再要求接触面积比 `A_supported/A_base >= rho_i`。上层重力如何在多个接触件之间分配并非唯一，不能简单把整件质量重复加给每个下层件。可以采用经文档化的载荷分摊规则（按接触面积、刚度或最不利线性规划），并把最大压缩力作为硬门槛。

纸箱压缩能力取决于材料、箱型、开孔、湿度、时间、堆码错位和支撑方式。ASTM D642 是容器、部件和单位载荷抗压试验的标准入口 [R14]，ISO 2234 涉及完整运输包装件和单位载荷的静态堆码试验 [R15]。软件应保存供应商或试验得到的允许值及条件，不应凭尺寸自动生成“认证承压力”。

### 4.4 稳定性、摩擦和系固

需要区分三件事：

1. **静态堆码稳定**：重心投影、支撑凸包、倾覆边和堆叠几何；
2. **运输动态稳定**：在规定纵/横/竖向加速度与摩擦下是否滑移或倾覆；
3. **系固方案**：墙体限位、挡块、绑带、网、气袋等的 WLL/MSL、方向、角度和锚点能力。

字段至少包括接触面的摩擦系数及来源、货物重心相对几何中心的偏移、可用锚点、系固件额定载荷和规则配置。CTU Code 附件 7 给出摩擦、加速度、滑动/倾覆和填充气袋计算 [R6]；道路规则另有各自适用条件 [R4][R5]。核心装箱器可用保守的“靠墙/空隙/重心投影”约束，但最终可执行方案必须由专用系固校核器或人工工程审核通过。

### 4.5 总质量、重心、地板载荷与轴荷

总重心按所有货物、托盘、衬垫和系固材料计算：

`G = sum(m_k * g_k) / sum(m_k)`。

但还需要载具皮重及其重心才能得到整车/整 ULD 重心。数据模型应分别保存：

- 载荷质量、最大总质量、设备皮重和称量状态；
- 允许载荷重心包络或位置相关最大载荷曲线；
- 地板面载荷、线载荷、点载荷/轮载与承载梁区域；
- 车辆空载各轴质量、轴位置、牵引座/支点和每轴最小/最大值；
- 左右轮/舱段不平衡限制。

简单两支点模型可用力矩求反力；复杂车辆优先导入制造商载荷分布图，表达为分段线性允许区域。局部地板载荷必须基于实际接触脚、托盘底梁或铺垫后的受力面积，不能拿箱体底面面积替代。

### 4.6 装卸顺序、多站点与可达性

只用 `stop_index` 并要求沿 X 轴单调是一种快速但过强的近似。完整模型包括：

- 路线和站点，货物的装货站/卸货站；
- 可用门、每站允许从哪扇门操作；
- 装载设备包络、最小通道、抬升/转弯空间；
- 货物通过门洞和从门到最终位置的无碰撞扫掠路径；
- 卸货前允许移动多少非本站货物、移动一次成本和是否必须复位；
- 先后约束图，例如 `A before B`、同批装载、不可叠放在晚卸件之上。

推荐提供三种服务等级：

- `STRICT_NO_REHANDLE`：每一站目标货物都能直接取出，是硬约束；
- `BOUNDED_REHANDLE(k)`：倒货件数/次数不超过 `k`；
- `MINIMIZE_REHANDLE`：可行但把倒货时间作为软目标。

多站点装箱已有专门研究，不能把体积利用率最优等同于配送作业最优 [R16]。输出必须给出装载序列和逐站卸载序列；若未进行扫掠路径验证，状态只能写 `geometric_layout`，不能写 `executable_loading_plan`。

### 4.7 危险品、隔离与温区

危险品不能建成一个布尔值。最少要保存：

- UN 编号、proper shipping name、主/次危险性类别、division、packing group；
- 包装种类、每件净含量/总量、limited/excepted quantity 状态；
- 海运 segregation group、温控/通风/远离热源要求；
- 运输方式、路线、司法辖区、规则版本和运营人更严格规则；
- 单证与分类数据的责任人、来源和时间戳。

美国公路危险品隔离表见 49 CFR 177.848 [R17]；ADR 2025 是 UNECE 发布的道路危险货物规则版本 [R18]；海运使用 IMDG Code [R19]，航空使用 ICAO Technical Instructions/IATA DGR [R20]。同一类别组合会因方式、数量、包装和例外条款得到不同结果，系统应调用带版本的合规规则包，不能手写一张“通用危化矩阵”。法规要求是硬门槛；求解器可以先按规则包输出的 `incompatible`、`min_distance`、`requires_partition` 和 `position_zone` 约束求解。

温控同样不只是容器 `temperature`：

- 货物可接受运输温度区间、允许偏离时间、是否冻结损坏；
- 容器温控能力、设定点、环境设计范围、预冷和电源要求；
- 多温舱的几何区域、隔断和各区域能力；
- 回风/送风禁入区、最小顶部/侧面间隙、通风与热源；
- 食品、药品、气味、过敏原等共载相容性。

区间无交集可以作为硬约束；设定点偏好可作为软目标；真实气流、热渗透和开门过程通常要由热工模型或标准作业复核。UNECE ATP 对易腐食品国际运输的设备和温度条件提供规则框架 [R21]。不要宣称仅凭几何规划完成冷链验证。

### 4.8 空隙、固定、衬垫和余量

“空白空间超过多少就需要固定”不是可泛化的物理规则。至少应分别表达：

- 货物与墙/货物之间的方向性允许间隙；
- 为防碰撞预留的保护间隙；
- 为手/叉车/吊具预留的操作间隙；
- 加速度方向上可能形成滑移的连续空隙；
- 可用填充件的尺寸范围、接触面积、允许压力、成本和库存；
- 易损面禁止接触或禁止由气袋施压。

求解器可先输出 `void_regions` 和每个方向的潜在移动量，再由固定模块选择挡块、蜂窝纸板、气袋、木方或绑带。CTU Code 对气袋的压力、接触面积、安全系数和开门风险有明确讨论 [R6]。如果没有固定模块，输出应标记 `requires_securing_design=true`，而不是用高体积利用率代替固定评估。

木质包装/衬垫还可能受 ISPM 15 的处理和标识要求约束 [R22]，需要保存材料类型、处理状态和标识证据。

### 4.9 门、障碍物与装入路径

容器可用空间推荐建成：一个或多个轴对齐主舱室减去 `obstacles` 和 `keepout_zones`。障碍物第一版用 AABB/长方体并集即可；可视化网格不能直接作为求解几何的权威来源。

每个 `Portal` 需要：所在平面、开口多边形或矩形、内向法向、门扇扫掠禁区、门槛高度、允许设备和站点。检查分三级：

1. 最终位置在可用空间且不与障碍物相交；
2. 货物当前姿态能通过门洞；
3. 从门到最终位置存在满足设备运动学和间隙的扫掠路径。

第 1 级不是第 2/3 级的证明。斜放穿门尤其需要连续碰撞检测。

### 4.10 尺寸、质量公差与不确定性

每个测量值宜保存 `min/nominal/max` 或 `value ± tolerance`、测量时间、设备/来源和置信等级。保守可行性采用：

- 货物外尺寸取上界并向上量化；
- 容器内尺寸/门洞取下界并向下量化；
- 货物质量取上界，载荷能力取下界；
- 间隙和保护厚度向上量化。

对相关批次可以用场景集合或机会约束；不要默认所有误差同时取最坏值而又不告知用户，否则可能过度浪费空间。结果应报告 `nominal_utilization` 与 `robust_utilization`，并说明假设。

测量方法也需要一致。GS1 Package Measurement Rules 提供消费品/包装尺寸测量的一致规则入口 [R23]。它不能替代具体设备实测，但可避免不同供应商对“长宽高”取向不同。

## 5. 硬约束、软目标与校核阶段

下表给出默认建议。`POST-HARD` 表示生成后校核，但失败必须淘汰，不是软条件。

| 约束/指标 | 默认语义 | 默认执行 | 说明 |
|---|---|---|---|
| 必装件数量、承载器可用数量 | HARD | PRECHECK + IN_SOLVER | 可选货物必须显式声明 |
| 边界内、互不相交、障碍物/禁区 | HARD | IN_SOLVER + 独立 POSTCHECK | 任意角使用 OBB/SAT |
| 允许姿态、不得倒置、最大倾角 | HARD | IN_SOLVER + POSTCHECK | 面语义不能只看尺寸 |
| 最小保护/操作间隙 | HARD | IN_SOLVER | 若是偏好才可 SOFT |
| 门洞通过 | HARD | IN_SOLVER 或 POST-HARD | 只验证最终位置不够 |
| 完整装入/取出路径 | HARD（若声称可执行） | POST-HARD | 无路径验证则降级结果状态 |
| 载荷、最大总质量、局部地板载荷 | HARD | IN_SOLVER + POSTCHECK | 含衬垫/托盘质量 |
| 重心包络、轴荷、左右偏载 | HARD | IN_SOLVER + POSTCHECK | 参数缺失时不得宣称合规 |
| `do_not_stack`、承压、最小支撑面积 | HARD | IN_SOLVER + POSTCHECK | 需可靠材料参数 |
| 静态稳定、支撑图无环 | HARD | IN_SOLVER + POSTCHECK | 支撑凸包只是简化模型 |
| 动态滑移/倾覆和系固能力 | HARD | POST-HARD/工程签核 | 规则与运输方式相关 |
| 危险品相容、距离、隔断、位置 | HARD | PRECHECK + IN_SOLVER + 合规校核 | 由版本化规则包生成 |
| 温度区间相容 | HARD | PRECHECK + IN_SOLVER | 气流/热工另行校核 |
| 气流、凝露、开门温升 | HARD 或风险阈值 | POST-HARD/签核 | 需要工况模型 |
| 严格多站点无倒货 | HARD | IN_SOLVER + 路径校核 | 用户可改成有界/软目标 |
| 少倒货、同单聚类、标签朝外 | SOFT，个别业务可 HARD | IN_SOLVER/评分 | 记录违反项和代价 |
| 容器总价格、容器数 | OBJECTIVE | IN_SOLVER | 建议词典序或 Pareto |
| 体积/质量利用率、重心居中 | OBJECTIVE | IN_SOLVER | 安全约束之后优化 |
| 衬垫量、装载时间、方案规则性 | OBJECTIVE | IN_SOLVER/评分 | 需明确量纲和权重 |
| VGM、设备检查、单证、操作员确认 | HARD 流程门 | OPERATOR_SIGNOFF | 算法不能代替现场流程 |

### 5.1 缺失数据策略

缺失值不能一律解释为“无限制”。每个规则域应有 `unknown_policy`：

- `REJECT`：安全/法规约束的默认值，例如质量、承压力、危化分类；
- `CONSERVATIVE_DEFAULT`：使用组织批准的保守值，并在报告中醒目标注；
- `ALLOW_WITH_WARNING`：仅用于偏好或探索性方案；
- `NOT_APPLICABLE`：必须有责任人明确确认，而不是空字段。

## 6. 分层元模型

### 6.1 聚合边界

```text
Catalog
  CargoType / CarrierType / AuxiliaryType / PoseCatalog
        |
        v
PackingJob ---- Route / DemandLine / RegulatoryProfile / ObjectiveProfile
        |
        v
NormalizedProblemSpec ---- SolverRun
        |                      |
        v                      v
PackingSolution -------- ValidationReport
        |
        v
ExecutionPlan / OperatorSignoff
```

目录保存可复用主数据；任务只保存本次需求和覆盖值；归一化问题是可复现实验输入；方案保存每件位置与顺序；验证报告不信任求解器自报；执行计划增加衬垫、系固、现场检查和签核。

### 6.2 `CargoType` 与货物实例

| 分组 | 推荐字段 | 说明 |
|---|---|---|
| 标识 | `id`, `revision`, `name`, `sku`, `tags` | ID 稳定，名称可变 |
| 几何 | `shape.kind`, `outer_dimensions`, `local_frame`, `cog_offset` | 第一版 `CUBOID` |
| 测量 | `nominal/min/max`, `source`, `measured_at` | 支持鲁棒求解 |
| 质量 | `mass`, `net_mass`, `mass_tolerance` | 危险品需净含量 |
| 姿态 | `orientation_policy`, `allowed_pose_ids`, `max_tilt` | 面朝向语义 |
| 力学 | `do_not_stack`, `compression_limits`, `min_support_ratio`, `max_overhang`, `friction` | 值要带试验来源 |
| 环境 | `temperature_range`, `humidity`, `ventilation`, `food/odor/allergen tags` | 范围与能力分开 |
| 合规 | `dangerous_goods`, `handling_marks`, `documents` | 不使用单一 hazmat 布尔值 |
| 作业 | `allowed_portals`, `handling_equipment`, `pick_face`, `stop_ref` | 任务可覆盖 |
| 间隙 | 六个局部面的 `clearance` 与 `no_contact` | 各向异性 |

相同 SKU 的具体件如有序列号、批次、实测质量或卸货站差异，用 `CargoItemOverride` 覆盖。数量很大时不要在输入中展开所有同质件；方案用 `(demand_line_id, ordinal)` 生成稳定实例 ID。

### 6.3 `CarrierType`、舱室与实例

| 分组 | 推荐字段 | 说明 |
|---|---|---|
| 标识 | `id`, `revision`, `mode`, `equipment_code` | `WAREHOUSE/TRUCK/CTU/AIR` |
| 经济 | `availability`, `fixed_use_cost`, `currency` | 实例和类型数量可分开 |
| 主几何 | `compartments[]`, `inner_bounds`, `obstacles[]`, `keepouts[]` | 可用空间而非外尺寸 |
| 入口 | `portals[]` | 门洞、法向、门槛、站点 |
| 质量 | `tare_mass`, `payload_limit`, `gross_mass_limit` | 保留来源与下界 |
| 结构 | `floor_limits`, `wall_limits`, `anchor_points` | 面/线/点载荷 |
| 平衡 | `cog_envelope`, `axle_model`, `lateral_imbalance` | 可导入分段曲线 |
| 环境 | `temperature_zones`, `airflow_keepouts`, `ventilation` | 冷机能力不等于货物温度 |
| 合规 | `approval_plate`, `operator_config`, `authority_documents` | 具体设备可覆盖 |
| 状态 | `inspection_status`, `damage`, `measured_geometry` | 设备实例层字段 |

`Compartment` 是独立容量与温区的空间；`Carrier` 可以含多个舱室。货物不能跨舱室，除非另有明确的跨舱支撑模型。

### 6.4 规则对象

不要为每个新约束不断给 `Box` 增加布尔字段。通用规则对象建议为：

```yaml
id: rule-hazmat-001
kind: SEPARATION                  # GROUP | SEPARATION | PRECEDENCE | POSITION | CAPACITY ...
scope: [demand-line-a, demand-line-b]
severity: HARD
enforcement_stage: IN_SOLVER
parameters:
  min_distance_mm: 1200
  metric: HORIZONTAL
authority:
  profile_id: us-road-49cfr
  citation: 49 CFR 177.848
  effective_at: 2026-08-27
```

法规规则对象应由规则包生成并锁定，普通用户不能把 `severity` 改成软约束。用户自定义偏好则允许调整权重。

### 6.5 方案与证据

`PackingSolution` 至少包括：

- 输入哈希、目录修订、规则包版本、求解器名称/版本/参数/随机种子；
- 使用的每个承载器实例、类型、价格和分配货物；
- 每件货物的位置、姿态、最终包络、直接支撑对象；
- 装载序列和逐站卸载序列；
- 托盘、隔板、衬垫、气袋、系固件等辅助物料；
- 未装件及结构化原因；
- 成本、利用率、重心、轴荷、最大承压利用率等重算指标；
- `validation_report_ref` 与结果状态。

结果状态建议：`LAYOUT_ONLY -> GEOMETRY_VALIDATED -> PHYSICS_VALIDATED -> COMPLIANCE_VALIDATED -> EXECUTION_APPROVED`。每一级都需要明确证据，不能一次求解直接跳到最后一级。

## 7. 单位、坐标和精度策略

### 7.1 外部 API 与内部归一化

API 可接受带单位的十进制字符串：

```json
{"value": "1200.5", "unit": "mm"}
```

归一化后保存原值与来源，并按任务 `geometry_tick` 转成整数 tick。建议默认：

- 长度：`1 mm/tick`，精密包装可选 `0.1 mm/tick`；
- 质量：整数 `g`；
- 力：`N`，压力：`Pa` 或业务显示 `kPa`；
- 角度：API 使用 `deg`，连续几何内部用 `rad` 双精度；
- 温度：API 明确 `degC/degF/K`，内部绝对温度可用 K；
- 金额：ISO 4217 币种 + 十进制字符串或最小货币单位整数，禁止二进制浮点累加；
- 时间：ISO 8601，明确时区。

整数 tick 能让正交边界/相交判断跨平台可重复。体积乘积可能超过 64 位，Python 可用任意精度整数；向 C/C++ 求解器传递时要检查溢出。JSON 禁止 `NaN`、`Infinity` 和隐式单位。

量化采用保守方向：货物尺寸/间隙向上，容器尺寸/能力向下。量化误差必须出现在验证报告中。

### 7.2 坐标系

统一右手坐标：默认 `+Z` 与重力反向；`+X` 从主装卸门指向舱内；面对舱内时 `+Y` 向右。由于车辆/飞机的“前后”未必等于主门方向，另用语义轴 `FORWARD/AFT/LEFT/RIGHT/UP/DOWN` 映射到坐标轴，不能靠猜。

放置统一使用物体局部原点（建议几何中心）在承载器坐标系中的 `position` 与四元数 `quaternion_xyzw`。正交结果仍输出 `pose_id`；四元数可作为派生字段。若两者同时出现，验证器必须检查一致。四元数需归一化、约定主动/被动旋转和乘法顺序，避免 GUI 与后端镜像。

### 7.3 几何容差

- 正交整数几何不使用任意浮点 epsilon；接触定义为端点相等；
- 连续 OBB 采用与尺度相关、记录在任务中的 `collision_epsilon`；
- “允许接触”和“必须留缝”分开，禁止用 epsilon 偷掉保护间隙；
- 可视化渲染误差不参与权威验证。

## 8. 输入 Schema 建议

采用 JSON Schema Draft 2020-12，顶层 `additionalProperties: false`；每个枚举用稳定机器码，显示文案由前端本地化。几何、质量、法规规则使用带版本的 `$defs`。下面是面向 API 的缩略实例，不是完整标准值：

```json
{
  "schema_version": "1.0.0",
  "job_id": "job-20260831-001",
  "problem_kind": "VARIABLE_SIZED_3D_BIN_PACKING",
  "units": {"length": "mm", "mass": "g", "angle": "deg"},
  "precision": {"geometry_tick": "1", "robust_mode": "BOUNDS"},
  "regulatory_profiles": [
    {"id": "road-cn-example", "mode": "ROAD", "jurisdiction": "CN", "revision": "operator-approved-revision"}
  ],
  "carrier_types": [
    {
      "id": "truck-a",
      "mode": "TRUCK",
      "availability": {"min_count": 0, "max_count": null},
      "fixed_use_cost": {"amount": "1250.00", "currency": "CNY"},
      "compartments": [{
        "id": "main",
        "inner_bounds": {"length": 9600, "width": 2400, "height": 2500},
        "obstacles": [],
        "keepout_zones": []
      }],
      "portals": [{
        "id": "rear-door",
        "compartment_id": "main",
        "shape": {"kind": "RECTANGLE", "width": 2350, "height": 2450},
        "inward_normal": [1, 0, 0]
      }],
      "limits": {
        "payload_mass": {"max": 12000000},
        "gross_mass": {"max": 18000000},
        "cog_envelope_ref": "truck-a-cog-v3",
        "axle_model_ref": "truck-a-axles-v3"
      }
    }
  ],
  "cargo_types": [
    {
      "id": "sku-fragile-1",
      "shape": {
        "kind": "CUBOID",
        "dimensions": {
          "length": {"nominal": 600, "max": 604},
          "width": {"nominal": 400, "max": 403},
          "height": {"nominal": 350, "max": 354}
        }
      },
      "mass": {"nominal": 18000, "max": 18500},
      "orientation_policy": {
        "mode": "ORTHOGONAL_SET",
        "allowed_pose_ids": ["UPRIGHT_0", "UPRIGHT_90"]
      },
      "mechanics": {
        "min_support_area_ratio": "0.80",
        "max_top_compressive_force_n": "1500",
        "do_not_stack": false
      },
      "clearance_mm": {"top": 5, "bottom": 0, "front": 3, "back": 3, "left": 3, "right": 3}
    }
  ],
  "demand_lines": [{
    "id": "line-1",
    "cargo_type_id": "sku-fragile-1",
    "required_count": 100,
    "stop_id": "stop-2"
  }],
  "route": {
    "stops": [{"id": "depot", "sequence": 0}, {"id": "stop-2", "sequence": 1}],
    "access_policy": "STRICT_NO_REHANDLE"
  },
  "objectives": [
    {"priority": 1, "kind": "MINIMIZE_UNLOADED_REQUIRED"},
    {"priority": 2, "kind": "MINIMIZE_TOTAL_COST"},
    {"priority": 3, "kind": "MINIMIZE_REHANDLES"}
  ],
  "unknown_policy": {"safety": "REJECT", "preference": "ALLOW_WITH_WARNING"}
}
```

这里的载荷数字只是 Schema 示例，不能作为任何车型或地区的默认法规参数。

### 8.1 推荐拆分的 Schema 文件

实际实现宜拆成：

- `common.schema.json`：ID、版本、单位量、区间、证据来源；
- `geometry.schema.json`：Cuboid、AABB、OBB、Portal、Pose、坐标系；
- `cargo.schema.json`：CargoType、CargoItemOverride、力学/环境/合规属性；
- `carrier.schema.json`：CarrierType、Compartment、障碍物、结构/轴荷模型；
- `job.schema.json`：需求、路线、规则、目标和求解预算；
- `solution.schema.json`：承载器实例、Placement、序列、辅助材料和指标；
- `validation.schema.json`：逐规则状态、裕量、证据和签核。

## 9. 输出 Schema 建议

缩略输出示例：

```json
{
  "schema_version": "1.0.0",
  "solution_id": "sol-001",
  "job_id": "job-20260831-001",
  "input_sha256": "...",
  "status": "GEOMETRY_VALIDATED",
  "solver": {"name": "...", "version": "...", "seed": 42, "parameters": {}},
  "used_carriers": [{
    "instance_id": "truck-a#1",
    "carrier_type_id": "truck-a",
    "placements": [{
      "item_ref": {"demand_line_id": "line-1", "ordinal": 0},
      "compartment_id": "main",
      "position_center_mm": [302, 203, 177],
      "orientation": {"pose_id": "UPRIGHT_0"},
      "supports": [{"kind": "FLOOR", "contact_area_mm2": 241200}],
      "load_sequence": 1,
      "unload_sequence": 100
    }],
    "metrics": {
      "payload_mass_g": 1800000,
      "nominal_volume_utilization": "0.73",
      "robust_volume_utilization": "0.70",
      "cargo_cog_mm": [4800, 1190, 860]
    }
  }],
  "unplaced": [],
  "auxiliaries": [],
  "validation_report_ref": "validation-sol-001.json",
  "warnings": ["Securing design and operator signoff are still required"]
}
```

输出中不要只返回旋转后的 `length/width/height`，否则无法恢复面朝向；也不要只返回利用率而省略未装件。所有关键指标由验证器重算，求解器自报值仅作诊断。

## 10. 验证规则与独立校核器

### 10.1 输入静态验证

1. Schema 版本受支持，未知字段拒绝或经过显式迁移；
2. ID 唯一、引用完整、修订可解析；
3. 尺寸、质量、能力为有限正数；计数为非负整数；金额带币种；
4. `min <= nominal <= max`，温区下界不大于上界；
5. `required_count` 有限，`availability.max_count=null` 才代表无上限；
6. 允许姿态非空，姿态矩阵正交/行列式为 1，四元数归一化；
7. 障碍物与门属于有效舱室，舱室边界不自相矛盾；
8. 载荷限制来源和单位明确；`gross >= tare`，声明 payload 不超过两者差值；
9. 危险品关键分类缺失按 `REJECT`，规则版本与运输日期相容；
10. 目标优先级无冲突，权重有单位或已归一化策略。

### 10.2 求解前可行性下界

- 总货物质量与所有可用承载器最大载荷的下界比较；
- 每件货物至少存在一个可用承载器、舱室、允许姿态和门洞候选；
- 温区、危险品和禁止混装形成的分组是否至少有可用承载器；
- 必装件总体积下界只能用于快速排除，不能证明可装；
- 有限承载器价格/数量与 `required_count` 是否一致。

### 10.3 方案独立验证

验证器不得调用求解器内部“已可行”标志，而应从输出重建：

1. 每个必装实例恰好一次，可选实例不超数量，承载器不超供应上限；
2. 使用费用、未装惩罚和总目标重算；
3. 姿态在允许集合/角度包络内；
4. 货物膨胀保护间隙后仍在舱室内，且不碰障碍/禁区；
5. 每对物体 AABB 或 OBB/SAT 不相交；
6. 门洞通过与声明的装入/卸出扫掠路径有效；
7. 总质量、总重心、局部地板载荷、舱段载荷和轴荷逐项重算；
8. 支撑图无环、接触面积/悬空比例合格、重心投影稳定；
9. 按明确的载荷分摊模型重算每件压缩力和局部压力；
10. 多站点顺序、遮挡、倒货上限和装卸设备可达性；
11. 危险品相容、距离、隔断、温区、气流禁区和共载规则；
12. 系固/固定能力及各运输方向的安全裕量；
13. 规则包和数据缺失产生的所有 `UNKNOWN`，不能被统计为 `PASS`。

每条结果输出 `rule_id/status(PASS|FAIL|UNKNOWN|NOT_APPLICABLE)/actual/limit/margin/evidence`。总体状态只有在所有适用的 HARD 规则为 `PASS` 时才能升级。

### 10.4 现场门槛

以下项目本质上不能仅靠离线几何软件完成：设备损伤检查、货物实际尺寸/质量确认、VGM/称量、包装状态、危险品单证、温控预处理、系固件实物状态、装载后封门和责任人签字。它们应成为 `ExecutionChecklist`，而不是被隐藏在一个 `validated=true` 中。

## 11. 落地优先级

### 第一阶段：可可信使用的正交内核

- 轴对齐长方体、允许姿态子集、有限/无限箱型数量和价格；
- 货物必装/可选语义、障碍物、门洞、各向间隙；
- 质量、简单重心包络、分段线性轴荷/位置载荷；
- `do_not_stack`、最小支撑面积、保守顶载上限；
- 同组/分离和严格的简化多站点顺序；
- 独立几何、数量、质量、姿态、支撑验证器；
- 完整输入/结果版本和数据来源。

### 第二阶段：真实运输作业

- 装入/卸出路径与设备包络；有界倒货和逐站作业计划；
- 多温舱、气流禁区、危险品规则包接口；
- 载荷分配图、复杂轴荷、局部地板载荷；
- 辅助物料目录、空隙区域和固定需求输出；
- 鲁棒尺寸/质量边界和方案敏感性分析。

### 第三阶段：专家工程模块

- 离散斜放与受控连续角度 OBB 求解；
- 动态滑移/倾覆、锚点和系固件选型；
- 更可靠的接触载荷/包装压缩模型；
- 冷链热工、凝露或外部仿真接口；
- 航空 WBM/ULD 和承运人批准数据的受控集成。

危险品、航空 W&B、结构和系固属于高责任域。成熟路线是“通用装箱器生成候选 + 专域规则/校核器硬门禁 + 责任人签核”，而不是试图让一个启发式分数同时代表所有安全结论。

## 12. 权威来源与进一步阅读

以下链接均在 2026-08-31 核对；法规应以实际运输日有效文本为准。

| 编号 | 来源 | 本文用途 |
|---|---|---|
| R1 | Wäscher, Haußner, Schumann, *An improved typology of cutting and packing problems*, EJOR 183(3), 2007, DOI: <https://doi.org/10.1016/j.ejor.2005.12.047> | 装箱/背包/多容器问题分类 |
| R2 | Bortfeldt, Wäscher, *Constraints in container loading – A state-of-the-art review*, EJOR 229(1), 2013, DOI: <https://doi.org/10.1016/j.ejor.2012.12.006> | 真实装载约束分类综述 |
| R3 | U.S. eCFR, 29 CFR 1910.176, *Handling materials—general*: <https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1910/subpart-N/section-1910.176> | 仓储堆码稳定 |
| R4 | EU Directive 2014/47/EU, Annex III: <https://eur-lex.europa.eu/eli/dir/2014/47/oj> | 道路货物加速度、轴荷与固定原则 |
| R5 | U.S. eCFR, 49 CFR 393.102 与 393.106: <https://www.ecfr.gov/current/title-49/subtitle-B/chapter-III/subchapter-B/part-393/subpart-I/section-393.102>；<https://www.ecfr.gov/current/title-49/subtitle-B/chapter-III/subchapter-B/part-393/subpart-I/section-393.106> | 公路系固性能与 WLL |
| R6 | IMO, MSC.1/Circ.1497, *IMO/ILO/UNECE CTU Code*: <https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/1497.pdf>；补充材料 MSC.1/Circ.1498: <https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/1498.pdf> | CTU 载荷分布、重心、堆码、危险品、温控、空隙与系固 |
| R7 | IMO, *International Convention for Safe Containers (CSC)*: <https://www.imo.org/en/About/Conventions/Pages/International-Convention-for-Safe-Containers-(CSC).aspx> | 集装箱批准牌、结构安全框架 |
| R8 | IMO, *Verification of the gross mass of a packed container*: <https://www.imo.org/en/OurWork/Safety/Pages/Verification-of-the-gross-mass.aspx> | SOLAS VGM 流程 |
| R9 | ISO 668:2020, *Series 1 freight containers — Classification, dimensions and ratings*: <https://www.iso.org/standard/76912.html> | 集装箱分类、尺寸和额定值标准入口 |
| R10 | ISO 1496-1:2013, *Series 1 freight containers — Specification and testing — Part 1*: <https://www.iso.org/standard/60720.html> | 通用货箱规范/试验标准入口 |
| R11 | FAA AC 120-85B, *Air Cargo Operations*: <https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_120-85B.pdf> | 航空 WBM、ULD、轮廓、地板与位置载荷、系固 |
| R12 | U.S. eCFR, 14 CFR 121.665, *Loading requirements*: <https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-121/subpart-U/section-121.665> | 航空货物装载、分布、固定与结构限制 |
| R13 | IATA, *ULD Regulations*: <https://www.iata.org/en/publications/manuals/uld-regulations/> | ULD 技术/运营出版物入口（需许可） |
| R14 | ASTM D642-25, *Standard Test Method for Determining Compressive Resistance of Shipping Containers, Components, and Unit Loads*, DOI: <https://doi.org/10.1520/D0642-25> | 包装抗压试验入口 |
| R15 | ISO 2234:2000, *Packaging — Complete, filled transport packages and unit loads — Stacking tests using a static load*: <https://www.iso.org/standard/25752.html> | 静态堆码试验入口 |
| R16 | Christensen, Rousøe, *Container loading with multi-drop constraints*, International Transactions in Operational Research 16(6), 2009, DOI: <https://doi.org/10.1111/j.1475-3995.2009.00714.x> | 多站点装卸约束 |
| R17 | U.S. eCFR, 49 CFR 177.848, *Segregation of hazardous materials*: <https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-177/subpart-C/section-177.848> | 美国公路危险品隔离规则示例 |
| R18 | UNECE, *ADR 2025 files*: <https://unece.org/transport/dangerous-goods/adr-2025-files> | 国际道路危险品版本入口 |
| R19 | IMO, *International Maritime Dangerous Goods (IMDG) Code*: <https://www.imo.org/en/publications/pages/imdg%20code.aspx> | 海运危险品规则入口 |
| R20 | IATA, *Dangerous Goods Regulations*: <https://www.iata.org/en/publications/dgr/>；ICAO, *Dangerous Goods*: <https://www.icao.int/safety/dangerousgoods> | 航空危险品规则入口 |
| R21 | UNECE, *About the ATP*: <https://unece.org/about-atp> | 易腐食品国际运输与温控设备框架 |
| R22 | IPPC, ISPM 15, *Regulation of wood packaging material in international trade*: <https://www.ippc.int/en/publications/640/> | 木质包装与衬垫检疫处理 |
| R23 | GS1, *Package Measurement Rules Standard*: <https://www.gs1.org/standards/gs1-package-measurement-rules-standard/current-standard> | 包装尺寸测量一致性 |

### 来源使用限制

- CTU Code 是跨行业最实用的公开工程指南，但不取代各运输方式和国家法规；
- ISO、ASTM、IATA 等部分全文需要购买或许可，产品不能未经授权内置全文/表格；
- 法规网页会滚动更新，生产任务必须保存生效日期、版本快照或内容哈希；
- 论文中的约束模型说明“算法可以如何表示”，不自动构成工程安全认证。
