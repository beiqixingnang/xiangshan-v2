# Kunminghu V2 完整实现与验收执行计划

本计划落实 2026-10-01 用户授权，延续现有总纲、V2 实施计划和证据规则。目标是完整复刻锁定的处理器实例。文件数量、端口清单覆盖和生成探针通过均不是实现完成条件。

## 1. 锁定范围

第一阶段的行为权威为 vendored Kunminghu V2 提交 `d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af`，配置为 `DefaultConfig`、`E.b`、`--num-cores 1`、`--fpga-platform`。完整参考 `/home/lishuo/xs-v2-local/build/rtl/XSTop.sv` 为 228590583 字节，SHA-256 为 `8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d`。

锁定层级共有 1976 个模块定义。逐模块切片用于阅读和局部证明，完整 XSTop 用于核对实例、连接、时钟域与最终系统行为；Scala 用于解释算法、参数和状态机。三个来源必须一致，均不允许为迁就 DUT 修改。

one-core/FPGA 特化不能冒充所有 Scala 合法配置。生成辅助模块、无输出的仿真/DPI endpoint、RAM、CDC、复位、性能/调试接口也必须逐项登记；无输出端口不自动构成可综合行为等价。不可综合的外部 endpoint 必须明确其测试/环境合同，不能靠全零端口壳隐藏。

## 2. 不遗漏的台账

`validation/v2_complete_closure_inventory.py` 在现有锁定层级、命名清单和已审计证据上生成 `validation/v2-complete-closure-inventory.json`。它是辅助验证视图，不替代产品 Manifest，不作为 Build 运行时依赖。

每个模块记录可达性、精确端口、子实例、来源文件、显式 catalog 候选、宽泛 source-mapping 候选、实现声明、当前证据及下一项门禁。来源相同仅用于安排工作，不授予实现或等价信用。没有精确导出/实现证据的模块保持待确认；`CONTRACT_ONLY`、有界模型、未实现父级和失效证明全部可见。

每个当前 Build 列出当前 SHA-256、固定分区、直接测试、显式成员、合同成员、已审计状态与源码卫生问题。Build 数动态统计，可按真实 family/协议/时钟/父级边界扩展；禁止恢复一 Scala 一 Python，禁止堆叠端口或无用状态增加行数。

台账保存输入哈希和本次 Git 身份。源码在并行批次中变化时重新生成；它不自动把历史账本结果当作当前 PASS，也不修改中央严格计数。

## 3. 批次与分工

最多三个 `gpt-6-luna / max` 子智能体同时实现互不重叠的文件，协调者维护计划、机器台账、提交和正式验证队列。

| 批次 | 完整职责 | 退出条件 |
| --- | --- | --- |
| Backend | Decode、Issue/rename/ROB、数据通路、整数/浮点/向量执行单元、CSR | 每个被选实例有真实组合/状态方程和精确参考对照；FPU/向量不能只保留 op 编码 |
| Frontend | BPU/FTB/TAGE/SC/RAS、FTQ、IFU、IBuffer、Icache/Uncache、ITLB | 预测、训练、冲刷、异常、队列和访存状态都可执行；父级完整 IO 逐边连接 |
| MemBlock/依赖 | LSU/LSQ、MMU/PTW、DCACHE、prefetch、L2/L3、AXI/TL、SRAM、AIA/JTAG/CDC | 地址翻译、权限、事务、仲裁、一致性、回填、异常、复位和存储语义与特化相符 |
| Parent/top | UHSCore、L2Top、UHSTile、UHSCTop、SoC glue | 锁定实例和父子连接全部有明确所有者；缺失边、静默截断/补零、错误时钟复位禁止被计为完整 |

Parent/top 可在其他批次空出槽位时并行，但必须读取实际参考实例 `.port(net)` 关系。不得凭相似名称/前缀推测连接。子对象存在和端口数匹配只代表结构条件；只有子行为证据闭合且边关系验证后才可宣称父级闭合。

## 4. 每族实现与验证

1. 从模块切片和 Scala 冻结真实输入、输出、位宽、符号、复位/时钟、状态、存储和延迟；把有界/合同缺口写清。
2. 在对应聚合 Build 中实现纯标准库 + Amaranth 方程。测试 oracle、来源路径/哈希、锁定参考名与迁移历史放验证器/JSON；产品只保留必要的公开接口和行为。
3. 一次批量完成源格式/五区/AST/精确导入、实际 Amaranth direct、确定性同名 Verilog、ABI、Verilator lint 和结构 Yosys。helper 对 helper 的自比较不能替代实际 DUT 测试。全仓 Pyright 在里程碑运行，日常只核对改变的类型边界。
4. 用同一输入、复位和时钟驱动真实 DUT RTL 与未经行为改写的锁定 SV，比较全部公开输出。Verilator 差分先定位错误；禁止用手写近似参考替代锁定 SV。
5. 静态及差分通过后，协调者串行运行无约束组合 SAT 或时序等价证明。必要的参考 frontend view 必须按规则 5C 保留完整代码/寄存器方程并验证守恒；工具错误不算负控成功。
6. 有状态模块补复位进入和初态对应的证据，再建立保持关系；归纳工具的弱等价假设不能扩大成任意上电状态的证明。CDC/多时钟按实际时钟关系单独处理。
7. baseline 通过后执行双方负控；每个 family 全部所需成员通过、来源绑定和中央审计一致后才增加 Build 严格数。未改 RTL 的成员可按精确缓存键复用，失败只重跑其影响范围。
8. 直接测试按同功能名固化到 `python/Program-System/System-Testing/Testing-Cpu/`；专用迁移验证器、日志、waveform 和生成物留辅助验证目录。

## 5. 顶层与后续集成

所有叶/family 实现完成后，沿实例图闭合 Frontend、Backend、MemBlock、L2/L3 与 SoC glue，再组合 UHSCore/UHSTile/UHSCTop。仅有 204 端口 envelope、全零输出或 injected reduced hierarchy 不算 XSTop。

完整顶层在 24 GB WSL 上优先使用可复用的子闭包 theorem 加父级 glue 证明与实际 RTL 事务差分；若需要分区，必须验证所有分区的假设、完整输出与连接，无假设空洞。完整 CPU/系统验证仍是独立门槛，资源不足明确保留 pending，不能把部分测试升级。

独立验证许可证、最终纯实现和本地化、Manifest/直接测试关系及完整系统证据后，准备 preview 迁移。用户批准进入主仓/main 的权限门槛保持不变。

多核在 one-core 闭合后作为后续独立里程碑：生成并锁定对应 2/4/8/16/32 核参考（按资源与配置支持逐步开展），实现 hart/中断/缓存一致性/互连/复位/地址规划，并分别验证。只接受正整数 `num_cores` 不是多核实现。

## 6. 证据与汇报

辅助仓按实际实现批次提交推送；主仓计划只在实质门槛或严格计数增长后追加真实事件。报告分别列出模块定义映射、明确未实现、已经真实差分/证明、完整 Build 严格计数、父级闭包和整机通过，不能相互替代。

Python 规模用 `splitlines()` 总行、非空行和排除注释/docstring 的代码行分别统计并注明范围；只把 Build 的实际行为新增算实现进展，测试/验证器/JSON 不计。扩大批次靠覆盖职责，不靠行数凑量。
