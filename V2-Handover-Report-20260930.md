# XiangShan Kunminghu V2 交接报告

更新时间：2026-09-30（Asia/Shanghai）。本报告用于把 `.agents/xiangshan-v2` 的当前事实交给新的 Codex 对话。报告只描述已核对的盘面；没有把 bounded、端口匹配或单个成员通过写成整机验收。

## 当前盘面

- 辅助仓库：`main`，当前已推送提交 `01ed8df`（`origin/main`）。工作树在本报告生成时干净。
- 硬件主仓库：`preview`，对应记录提交 `403db0e`（`origin/preview`）。候选 Build 尚未搬入主仓库。
- 锁定参考：Kunminghu V2 离线 XSTop 产物，锁定层级为 1976 个模块；参考来源提交锁定为 `d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af`，XSTop SHA-256 为 `8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d`。
- 当前 Build 动态分母：118 个 `python/Program-System/System-Build` 脚本。
- 严格等价计数：**44/118（37.288136%）**。当前有 54 份严格证据记录，其中 44 份 `COMPLETE_EQUIVALENCE`、5 份 `STRICT_PENDING` 记录未计数、5 份因来源摘要或旧验证器摘要不一致而审计失败；其余 Build 尚未形成可计数的严格证据。严格未闭合为 74/118。
- 当前 `python/**/*.py` 的直接行数重算为 86,145 行（命令：在仓库根执行 `Get-ChildItem python -Recurse -Filter '*.py' | Get-Content | Measure-Object -Line`）。较早硬件计划事件记录过 93,153 行，它使用的是当时批次的历史口径；后续报告应继续写明统计路径和命令，避免把两个时间点混在一起。
- 最近闭合的完整 Build 是 `Build-Cpu.Memory.Prefetch.Metadata.Family`，包含 `StreamBitVectorArray` 和 `StrideMetaArray` 两个成员；提交 `01ed8df` 中的证据显示 Yosys 归纳等价分别为 `1256/1256` 和 `818/818`，direct test `4/4`，端口 ABI、确定性导出、锁定参考 Verilator、Pyright、双侧负控和中央来源审计通过。这个结果只增加了 1 个 Build 计数，不代表父级或 XSTop 整机闭合。

## 现行验证流程

每个候选 Build 先按自己的成员表枚举需要覆盖的锁定模块；不能只证明一个代表模块就声明整个 family 完成。验证顺序如下：

1. **锁定来源和范围**：检查 pinned source commit、XSTop hash、精确 `reference-sv/<Module>.sv` 文件和 Scala 来源记录。锁定参考、Scala 和生成的参考 SV 只读，不能为了让 DUT 通过而修改。
2. **纯实现检查**：Build 必须是 Python 标准库加 Amaranth 的可执行 RTL，不能嵌入大段 Verilog/SystemVerilog、Scala 列表、上游身份、源码路径或 provenance 清单。检查固定五区、`__all__`、导入无副作用、`py_compile`、AST、命名和确定性。
3. **ABI 和导出**：从 Python/Amaranth 生成与 Build 同名的 Verilog，核对模块名、端口名称、方向、位宽、时钟和复位；重复导出必须字节一致。文件生成本身不计严格通过。
4. **后端检查**：对锁定参考和 DUT 的真实 Verilog 分别运行 Verilator lint/编译，使用 Yosys 做读取、展开、综合和结构检查。直接测试必须检查输入激励后的输出、状态、握手和错误边界，不能只检查对象可实例化。
5. **行为证明**：组合模块使用无约束 SAT miter，要求 `sat -prove mismatch 0` 的 no-model 成功且检查没有被约束成空问题；带状态的模块把参考和 DUT 接到同一个时钟/复位环境，使用 `equiv_make`、`equiv_induct -undef` 和 `equiv_status -assert`，要求所有 `$equiv` cells proven、无 unproven，并保留变量/子句/输出尾部摘要。
6. **参考 view 审计**：如果旧版参考 SV 含 Yosys 不支持的 Chisel 生成结构，只能建立 5C synthesizable view。view 必须经过行守恒、寄存器更新方程保留、预处理区域和端口检查；它是对锁定参考的可审计投影，不能改写参考行为。
7. **负控和中央账本**：把 DUT 或参考的一条实际方程故意变异，要求等价证明失败，并对两侧分别做负控。最后运行 `validation/v2_strict_equivalence_progress.py`，只有证据状态是 `COMPLETE_EQUIVALENCE`、来源摘要与当前源码匹配、锁定提交匹配、严格证明和负控全部通过且没有重复 Build 声明时，才允许把 1 个 Build 加入 44/118。
8. **父级闭包和系统门禁**：Build 级严格通过仍需父级 family/parent closure、完整 XSTop 差分、许可证复核和用户批准；这些未完成前不能迁移到硬件主仓库，也不能写成 `ACCEPTED`。

## 证明边界

当前严格 rail 的核心证明是状态转移关系的等价归纳。Yosys 的 `equiv_induct` 使用弱归纳定义：它证明两边在已经相等的可观察状态之后不会分歧，因此测试或额外证明仍需覆盖复位/启动时双方初态同步。现有严格计数没有 FPGA 依赖，但也不能把它描述成“任意未知上电状态下完全相同”。下一轮应优先补一条可重复的软件复位启动证据，例如：将锁定参考与 DUT 放入同一 wrapper，显式驱动异步/同步复位和时钟，证明复位释放后的首个状态与后续归纳假设一致，并对复位极性、复位保持周期和释放边界做负控。若该证据无法对某个模块建立，应在该模块证据中标记边界，不得静默扩大 `COMPLETE_EQUIVALENCE` 的含义。

## 尚未闭合的重点

- `Build-Cpu.Memory.Dcache.MissQueue.Family`：7 个成员都有锁定参考，但目前主要是 ABI/导出或 bounded 证据；`MissEntry` 与 `WritebackEntry` 仍是主要行为缺口，不能按 family 计数。
- `Build-Cpu.Frontend.Icache.Prefetch.Family`：成员行为和状态时序较复杂，正在审查锁定参考与 Python 状态机的差异。
- PMP family：5 个成员，当前包含 `CONTRACT_ONLY`/历史反例；`PMPChecker_2` 只有 variant-level 证明，不能代表整个 family。`PMPChecker_12` 的 PMA、请求有效位锁存和响应时序需要重新对照锁定 Scala/SV。
- 现有 5 个失败审计记录涉及 validator 或 Python Build 的来源摘要不一致，需先重新生成与当前源码对应的证据，不能直接改 JSON 数字。
- 父级闭包、完整 XSTop 差分、许可证复核、用户批准和主仓迁移仍未完成。

## 新对话的建议任务

新的执行者应先读根 `AGENTS.md`、硬件总纲/计划、辅助仓 `README.md`、`V2-Python-Rewrite-Strategy.md`、本报告和 `validation/v2_strict_equivalence_progress.py`。之后可以尝试一种更快且仍可审计的验证思路：

- 先按锁定层级把 Build 聚成一个“可观察边界相同”的 family，生成统一 wrapper，一次性把多个同类成员的端口、时钟、复位和公共输出接入同一 Yosys miter；把每个成员的证明结果保留为可定位的子结果。
- 对有状态成员，把“复位启动证明”和“无界归纳证明”拆成两个明确命题：启动 wrapper 证明复位释放后的第一拍状态一致，随后 `equiv_induct` 证明转移关系保持一致。这样不会用弱归纳假设替代初态证据。
- 对组合或小状态成员，先运行无约束 SAT miter；对复杂 family，先用相同输入轨迹做 Verilator 参考/DUT differential 作为快速定位，再只把失败成员送入串行 formal。轨迹只用于定位和补充证据，不能替代无界证明。
- 使用“先静态筛选、后一次 formal”的批处理：同一 family 内先批量完成 ABI、纯 Python、确定性、lint 和 direct tests；只有整族静态门禁通过后，串行运行一次正式 Yosys rail，避免每修一行就重跑全仓。
- 为每个 family 输出 `family_manifest.json`，记录成员、锁定参考 hash、DUT hash、端口/输出覆盖、复位命题、formal 命令、负控结果和失败原因；中央账本只读取这些证据，不接受手工计数。

可以直接把下面的提示粘贴到新对话：

> 你接手的是 `D:\知识库开发\Unifier-Hardware-System\.agents\xiangshan-v2` 的 Kunminghu V2 严格等价任务。先读取根 `AGENTS.md`、硬件总纲与计划、辅助仓 `README.md`、`V2-Python-Rewrite-Strategy.md` 和 `V2-Handover-Report-20260930.md`。当前真实状态是 118 个 Build、1976 个锁定模块、严格等价 44/118；最近闭合提交为 `01ed8df`，硬件主仓记录提交为 `403db0e`。只能修改辅助仓的纯 Python/Amaranth Build、验证器和证据；不得修改 locked Scala、reference SV、主仓产品代码或把证据当运行时依赖。严格计数只能来自完整 `COMPLETE_EQUIVALENCE`：精确 ABI、确定性同名 Verilog、direct test、Verilator/Yosys、锁定参考差分、无界 SAT/induction、复位启动边界、双侧负控、来源 hash 和中央审计全部通过；`DIRECT_TEST_PASS_BOUNDED`、`PASS_BOUNDED_PARTIAL_FORMAL`、variant-only 和 `CONTRACT_ONLY` 都不能计数。请先提出并小范围验证一种更快的 family-wrapper + 复位启动证明方案，再选择一个完整 family 实施；WSL formal 串行运行，避免并发占用 24GB 内存。每次只有严格计数真实增加时才更新计划和提交推送，报告必须写严格 `N/118`、已覆盖/1976、当前及本轮 Python 行数、Build 数、完成行为验证的 Build `N/118`、pending/CONTRACT_ONLY、未运行门禁、提交身份和实际命令退出码。`

