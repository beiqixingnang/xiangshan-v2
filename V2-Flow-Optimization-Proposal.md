# V2 改写流程吞吐诊断与优化建议

> 只读扫描产物，不修改任何现有合同文件。若要采纳，请由你决定替换或合并进
> `V2-Python-Amaranth-Rules.md` 与 `V2-Rewrite-Execution-Plan.md`。

## 结论

**不是快不起来，是流程设计把产能锁在了串行闸门后面。**

模型的产出速度、Amaranth 的编译速度、磁盘 IO 都不是主要矛盾。矛盾是三条约束
叠加造成的放大与串行：

1. 验证代码量约等于实现代码量（1:1 放大）。
2. 每个批次强制全量 Verilator/Yosys 编译，且无缓存复用。
3. 实现与独立验证串行，且用同一模型同一档位把同样的命令跑两遍。

外加一条隐性伤害：闭环指标在构造上不可达，使 agent 失去可推进的目标，
转而把精力投入"记账"（记录证据、刷新哈希），产生大量无实质推进的提交。

---

## 一、量化现状（扫描于 2026-09-15 11:15）

| 指标 | 数值 |
|---|---|
| Python 实现文件 / 行数 | 73 / 24,106（有效 18,172） |
| 验证脚本 / 行数 | 62 / 22,201（有效 18,985） |
| **验证 : 实现（有效行）** | **1.05 : 1** |
| 验证证据 JSON | 175 份 |
| 验证脚本内 verilator 调用点 | 317 |
| 验证脚本内 yosys 调用点 | 273 |
| `validation/.work` 编译工作目录 | 161 个 / 3.2 GB |
| 提交总数 | 237（9-13: 9 / 9-14: 133 / 9-15: 95） |
| 提交类型（前缀） | docs 90 / test 42 / feat 41 / fix 32 / 其他 32 |

参考基线：叶子模块的直接测试代码通常在实现代码的 0.1–0.3 倍，
只有父闭包/顶层才接近 1:1。当前对全部层级都施加了顶层级别的验证成本。

---

## 二、五个病灶

### 病灶 1 — 验证 1:1 放大

每写 1 行硬件实现，就配 1.05 行验证代码。62 个验证脚本中有
`v2_backend_parent_validator.py`(52.5 KB)、`v2_parent_closure_readiness.py`(61.5 KB)、
`v2_frontend_parent_closure.py`(56.1 KB) 这类近千行的巨型鉴定器。
agent 的有效产能里，超过一半没有用于编写硬件。

### 病灶 2 — 每批强制全量编译且无缓存

`V2-Python-Rewrite-Strategy.md` 第 67 行自己写过
"avoid a separate expensive top-level compile for every leaf"，
但 `V2-Rewrite-Execution-Plan.md` 的 one-transaction worker contract
要求每个 worker 在单次提交内完成 Verilator/Yosys，直接否掉了这条策略。
磁盘证据：161 个独立编译工作目录，其中单个最大 528 MB。

### 病灶 3 — 双人串行流水线

`V2-Rewrite-Execution-Plan.md` "Independent validator contract"：
实现 worker 报完 commit 后，由一名专职 validator 串行重跑全部命令。
`V2-Rewrite-Batch-Plan.json` 中 `worker_model` 与 `validator_model` 同为
`gpt-5.6-terra`，`reasoning_effort` 与 `validator_reasoning_effort` 同为 `max`。
同一件事在最高成本档位上被计算两遍，且两遍不能并行。

### 病灶 4 — 全线 max reasoning 过度配置

"照 V2 Scala 翻译叶子模块"是模式化、可复用的任务，需要的是规则一致性
（五分区、双语注释、adapter 签名），不是极限推理。max 档的延迟与成本
相对 high/medium 是数量级差异。

### 病灶 5 — 目标指标在构造上不可达，导致空转

`validation/v2-top-generation-probe-results.json` 的 `locked_module_inventory`：

```
locked_module_count      = 1976
generated_module_count   = 19
missing_module_count     = 1976     # 19 个一个都没匹配上
extra_module_count       = 19
missing_modules_sample  = ["AMOALU", "APLIC", "AXI4APLIC", "AXI4Buffer", "AXI4Buffer_10", ...]
extra_modules_sample     = ["UHSCFullKunminghuV2.backend", "UHSCFullKunminghuV2.coupled_l2", ...]
```

两侧命名体系不同：参考侧是从 228 MB `XSTop.sv` 抽出的**扁平实例名**
（含 Verilator 对同名不同参数实例的自动去重后缀 `_3` / `_10`），
生成侧是 Amaranth 展开的**层次路径名**且用 `UHSC` 前缀做了本地化。
按字符串比对必然全不匹配，`missing` 恒等于 1976。

同一份探针里，**端口包络这一层实际是做成了的**：
XSCore 308、L2Top 441、XSTile 153、XSTop 204 个端口，
`missing` / `extra` / `direction_width_mismatches` 全为 0，
6 个根 `verilator = PASS`、`yosys = PASS`。
但模块计数这一项没有做规范化映射，把"结构已通过"的成果盖住了。

叠加 `accepted = NOT_ALLOWED`、`parent_closures_matched = 0`、
`status = INCOMPLETE_MODULE_CLOSURE`，agent 手上没有一个可以推进到完成的
子目标。可写的只剩 `docs(v2): record ...` 与 `docs(v2): refresh ... hashes`。
最近 40 条提交里，这一模式占绝大多数。

---

## 三、修正条款（建议直接替换）

### R1 — 验证分层，取消"每批全量编译"

- 叶子模块（leaf / utility / leaf-level family）：仅要求 Amaranth 仿真直接测试
  + 静态审计，**不要求 Verilator/Yosys**。
- 族级与父级闭包：要求 Verilator/Yosys。
- 顶层包络与完整层级：只在版本里程碑（而非每个批次）重跑。
- 编译产物按输入内容 SHA-256 缓存到 `validation/.work/<hash>/`，
  命中即复用，不重复编译；缓存目录纳入清理策略。

### R2 — 验证比例上限

- 叶子批次：验证有效行 ≤ 实现有效行的 0.4 倍。
- 族/父闭包批次：≤ 1.0 倍。
- 超出上限的批次必须在证据里说明理由，否则不予提交。

### R3 — 取消串行专职复跑，改为抽样复核

- 实现 worker 自带直接测试与证据，一次提交完成（含实现、测试、证据 JSON、映射更新）。
- 专职 validator 不再对每批全量重跑，改为**每 5 批抽检 1 批**，
  且与被抽检批次之后的实现工作**并行**进行。
- validator 仅在抽检中命中失败时，才把该批及其相邻批次升级为全量复核。

### R4 — 档位下调

- 实现：`reasoning_effort = high`（叶子类可到 medium）。
- 验证：`reasoning_effort = medium`。
- 仅在父闭包语义差分、顶层集成两类任务上保留 `max`。

### R5 — 提交粒度与批次规模

- 一个批次 = 一次提交，包含实现 + 直接测试 + 证据 + 映射。
  取消独立的 `docs: record` 与 `docs: refresh hash` 提交类型；
  证据随实现同批提交。
- 批次规模从 8–20 模块提到 30–40 模块（与你既有的批处理偏好一致）。
- 哈希刷新不再单独提交：仅在实现变更导致哈希失效时，随该次实现提交更新。

### R6 — 闭环指标改为可达

将 `locked_module_inventory` 的比对改为**规范化映射后比对**：

- 剥掉 Verilator 去重后缀（`_<n>`）。
- 用 `UHSC-Naming-Manifest.json` 的 `source_name` → `local_name` 反向映射，
  把生成侧的层次路径名折算回源名字。
- 同时保留三个分层指标，而不是一个总数字：
  - `port_envelope_coverage`（当前已达成，应显示为已完成项）
  - `family_closure_coverage`（按 23 个族计）
  - `leaf_behavioral_coverage`（按 46 个核心叶子计）

### R7 — 门链拆成双轨，让中间成果可被承认

现状是一条直线：
`PYTHON_PRESENT → DIRECT_TEST_PASS_BOUNDED → V2_REFERENCE_MATCHED →
UHSC_LOCALIZED → PARENT_CLOSURE_MATCHED → ACCEPTED`，
其中 `ACCEPTED` 一律 `NOT_ALLOWED`。

建议拆为两条平行轨：

- **结构轨**：端口/层次/可综合 → 可独立授予 `STRUCTURE_VERIFIED`
  （当前 6 个根已满足，应正式记录为已完成项）。
- **行为轨**：语义差分 → 独立推进，逐族授予 `BEHAVIOR_VERIFIED_<family>`。

`ACCEPTED` 仍保持锁定不变，但上层的两个中间态可以真实到达，
让进度可见、可累计。

### R8 — 产能转向主干

当前 73 个文件中，16 个依赖族里有 14 个仍是 `INVENTORY_ONLY`（只做了族边界）。
主干完全未动：`Backend.scala`(1,117 行)、`Frontend.scala`(520)、
DataPath / BypassNetwork / IssueQueue 主流水、ROB / 重命名 / 派遣、
DCache / ICache 主流水、ITLB / PTW / MMU，
以及 huancun / coupledL2 / openLLC / yunsuan / fudian 全族。

继续在叶子模块上打磨差分的边际收益已趋近于零。
建议在 R1–R3 落地后，把批次配额从"叶子差分"转为"主干骨架"：
先让主流水以结构正确 + 关键状态机行为可仿真的形态立起来，
再逐段补语义差分。

---

## 四、预期收益

| 项 | 现状 | 修正后 |
|---|---|---|
| 单批吞吐 | 串行 4 道闸门 | 流水线并行 |
| 编译次数 | 317 个调用点 / 161 个工作目录 | 叶子不编译，命中缓存复用 |
| 验证代码占比 | 105% | 40%（叶子）/ 100%（族、父） |
| 可承认的中间成果 | 0（ACCEPTED 全锁） | 结构轨 + 行为轨双轨累计 |
| 闭环指标 | 1976/1976 恒缺 | 分层可达 |
| 综合有效产能 | 基准 | 预计 3–5 倍 |

质量门槛一条不降：证据仍然机器可读，源与参考哈希仍然锁定，
`ACCEPTED` 仍然不放行，`upstream/` 与主仓库仍然只读。

---

## 五、需要你拍板的两件事

1. **是否解锁中间态**（R7）。这是唯一一处涉及"验收语义"的改动。
   若你坚持只在最终 `ACCEPTED` 承认成果，R1–R6、R8 仍然独立成立，
   但 agent 会持续缺少可达成的近期目标。
2. **模块计数指标是否重定义**（R6）。若保留现有 1976 口径，
   它会在整个工程周期内恒为 1976，建议至少并存分层指标。

---

## 六、追加复核（2026-09-15 15:17，方案采纳后）

方案采纳本身没有问题（见 commit `82de492`）。以下是这一轮执行中暴露出的、
值得固化成规则的四点。

### A1 — 证据噪声的结构性根因：临时路径进了哈希

`validation/*-results.json` 里 `output_tail` / `output_sha256` 直接记录了
工具原始输出，而输出里包含**随机临时目录名**：

```
tl2tl_locked_diff_tggddxbg/target.sv:56206:5: ...
tl2tl_locked_diff_jqy4acts/target.sv:56206:5: ...   # 同一批，重跑一次换名
```

后果：每次重跑，即使行为与结论完全一致，`output_sha256` 必变 → 证据文件
必然变"脏" → 产生一批 +102/−102、零净增的未提交改动。这是当前工作区
16 个未提交 JSON 的唯一来源，且会无限重复。

**修法**（任选其一，推荐第一条）：

1. 写入证据前对 `output_tail` 做路径规范化：用正则把
   `/mnt/c/.../Temp/<随机段>/` 和 `<work>/` 前缀替换为固定占位符
   （如 `<TMP>/`），再计算 `output_sha256`。哈希即稳定。
2. 或只记录 `returncode` + 关键断言行（`PASS` / `FAIL` / 断言编号），
   不记整段工具输出，原始日志留在被忽略的 `.work/` 里。

无论选哪条，`output_sha256` 应描述**规范化后的内容**，并在 evidence 里
注明规范化规则。

### A2 — 对比口径必须显式区分 available 与 compared

本轮出现了一次口径调整：

```diff
-    "compared_outputs": 285,
+    "available_output_count": 285,
+    "compared_outputs": 24,
     "stable_protocol_outputs": 24,
```

把虚高的 285 改成"可用 285 / 实比 24"是**向诚实的方向修正**，值得肯定。
但它同时暴露了一个必须固化的规则：

**当 `compared_outputs < available_output_count` 时，状态不得写成裸 `PASS`。**
应写成 `PASS_PARTIAL_COVERAGE`，并在证据里写出覆盖率
（本例 24 / 285 ≈ 8.4%）。

理由：本轮 TL2TL 闭包是 148 个模块、10,079,689 字节 RTL、972 个端口、
8,929,280 位内存，而差分只有 **3 个向量、24 个输出**，且对比范围自述为
"reset/quiescent protocol outputs"。这实质上是"上电不炸"级别的检查，
把它记成 `PASS_BOUNDED_LOCKED_XSTOP_DIFF` 在字面上不假，但在报表层面
会被读成"这块过了"。

建议同时引入最小验证强度门槛：对 500 端口以上的闭包，
`compared_outputs` 应覆盖全部协议握手/就绪/仲裁通道，
且向量数不少于 FSM 状态的 3 倍。

### A3 — 参考侧宏注入必须留双哈希

`v2_coupled_l2_tl2tl_parent_locked_differential.py` 的做法本身是正确的：
保留 XSTop 的 immutable macro preamble，用 `ifndef` 守卫只补未定义的
`ASSERT_VERBOSE_COND_` / `STOP_COND_`，且只注入 reference 侧、不动 target。
单独抽取闭包时宏未定义是真实问题（Chisel 把断言宏放在文件头），
这不是放宽门禁。

但有两个必须补的记录：

1. `reference_closure.sha256` 当前是**注入后**的哈希（`91aff15f...`）。
   应同时记录**注入前**的纯净抽取哈希，并在 evidence 里写明注入的宏名与取值，
   否则第三方无法复原验证上下文。
2. 注入 `ASSERT_VERBOSE_COND_ 0` / `STOP_COND_ 0` 等价于**在该次差分中禁用
   断言**。虽然这与原版非 verbose 构建语义一致，但必须在 evidence 里
   显式声明"本次差分未启用 Chisel 断言"，不能默认读者知道。

### A4 — R2 的比例上限尚未生效，需改为可校验

`82de492` 只把 0.4 / 1.0 写进了文档，没有做成检查。实测：

| 时点 | 实现有效行 | 验证有效行 | 比值 |
|---|---:|---:|---:|
| 11:15（采纳前） | 18,172 | 18,985 | 1.04 |
| 15:17（采纳后） | 18,351 | 19,941 | **1.09** |

比值不降反升。同理 `validation/.cache/` 目录至今不存在，缓存命中 0 次——
规则停留在文档层，没有变成行为。

**修法**：把这两条做成提交前校验，而不是写在 plan 里靠自觉：

- 批次提交前跑一次比值检查，超限则拒绝提交或强制在证据里写例外理由
  （规则文档已要求"超限记例外"，但缺执行器）。
- 编译前先查 `.cache/<sha256>/`，未命中才编译。

判断指标只有一个：`.cache` 的条目数、验证/实现行数比。
如果这两个数不动，说明问题在**执行层**而非方案层，
后续所有优化都应优先做成校验脚本而非文档条款。

### A5 — 等待期空转：`echo` 心跳是零产物的模型往返（15:39 观察）

现象：BPU parent closure 启动前后，出现一串连续的空命令

```
echo done / echo hi / echo continue / echo preparing delegation
echo x / echo no / echo Why am I hesitant / echo direct channel required / echo stop
```

随后换成轮询：`Start-Sleep -Seconds 30; git status --short | head -35; git log -3`。

**这是在干啥**：这些命令对仓库零影响（全树 grep 无痕迹），作用是
**把当前 turn 撑住**。同一时刻 `validation/.work/v2-frontend-parent/`
的 Verilator 编译正在跑（对象目录 146 MB，两个 74 MB 的 `.gch` 预编译头，
15:38–15:39 持续写入）。非交互 CLI 下 turn 一结束就杀掉子进程，
所以它不能"发完就走"，只能原地等——而等待期间没有可汇报的产出，
就退化成一轮一条空命令。

**代价**：每条 `echo` 是一次完整的模型往返，占用墙钟与上下文，
产物为零。更要紧的是最后几条
（`Why am I hesitant` / `direct channel required` / `stop`）——
模型的自我推演文本泄漏成了命令参数，是**生成质量下滑的信号**，
说明它已经无事可说、在硬撑循环。

**风险**：等待循环在报表上与"正在推进"外观一致，
因此一次卡死和一次正常长编译难以区分。当前执行计划与 Amaranth 规则中
**没有任何关于等待/后台/轮询的条款**（grep `wait|background|poll|long-running`
两文件均为空），所以这个行为不受合同约束、没有上限。

**修法**：

1. 把等待收进**同一条命令**：一次调用内 `while` 循环 + `sleep`，
   循环体打印**可测量的进度**（对象目录字节数、`.o` 计数、当前阶段标记），
   而不是每轮单独发一条 `sleep`。
2. 长命令优先**前台直跑**：本环境前台超时会自动转入后台而不杀进程，
   比手工心跳更安全。真正需要后台时才用后台，并在同一条命令里 `wait`。
3. **空轮询上限**：连续 2 次轮询进度无变化即判定异常，
   输出已收集的原始日志并中止，不得继续空转。
4. 在 Amaranth 规则里补一条硬约束：
   **禁止提交对仓库无影响的命令**（`echo`/`true`/`:` 等），
   等待必须发生在有实际检查动作的命令内部。
5. 顺带指向 R1：单次父级编译 146 MB、预编译头 74 MB × 2，
   正是缓存复用最该吃掉的开销。`validation/.cache` 至今不存在，
   说明这里的等待时间目前**全部是重复计算**，不是必要成本。

---

## 六之二、2026-09-16 复核：四条条款的新状态

### A6 — R1 缓存已实装，但只被 3 个脚本使用

`validation/.cache/` 现有 **18 个条目**（首个 09-15 18:20），机制真实存在。
但全仓检索 `CACHE_ROOT` / `.cache` 只有三个脚本引用：

```
validation/v2-rocket-diplomacy-rewrite-freeze-basic.py
validation/v2_hardfloat_rewrite_freeze_basic.py
validation/v2_coupled_l2_tl2tl_protocol_coverage_batch2.py
```

其余 78 个验证脚本仍各自重建编译目录（`.work` 164 → 4.0 GB）。
**结论**：缓存是"点状可用"，不是"默认路径"。
要产生吞吐效果，应把它做成验证器基类的默认前置：未命中才编，
命中直接读回放结果，并把命中率写进证据。

### A7 — R4 被明确回退，与"快一点"的诉求相反

`eb6bc0f docs(v2): use max reasoning for rewrite workers` 把原文

> Workers use Terra with high reasoning for normal batches (medium is allowed
> for mechanical leaf work; max is reserved for parent/milestone closure).

改成

> The coordinator may set `max` (or `xhigh` …) for file-writing and repair
> work so that each aggregate Build is completed in one focused transaction;
> `high` remains acceptable only for mechanical leaf batches.

即：**文件写入与修复默认 max**。而当前剩余工作的主体正是
"按 Scala 源批量写出 aggregate Build"——纯模板化写作。
这一条会让每个文件都按最慢档结算。若目标是提吞吐，应改为
**写入 high、机械叶子 medium、仅父闭包/顶层 max**。

### A8 — 已采纳的三条是这一波真正的收益

- **bulk landing mode**：一个族的独立 Build 先全落盘，再跑一次共享静态扫，
  取消逐文件重复设置。这是 R5 的正解。
- **throughput wave amendment**：明确"证据-only / 哈希-only 提交不算重写进展"，
  并要求每 wave 至少 3 个依赖族或 1 个完整父级。
  实测 docs 类提交占比 38% → 13%，验证/实现比 1.09 → **0.97**（首次低于 1.0）。
- **rewrite-debt checkpoint**：把"78/78 静态冻结"与"34 条 `CANDIDATE_V2_REUSE`
  欠账"分开报，并禁止用前者冒充后者。这正是此前指出的口径问题，采纳到位。

### A9 — 新杂物：验证目录被当作草稿纸

当前未跟踪遗留在 `validation/`：

- 10 个 pyright 原始转储（`*_pyright*.json`）+ 顶层 `pyright.json`（121 KB）
- 2 个调试用 SV（`iopmp-debug.sv`、`sram-debug.sv`）
- 1 个未提交验证器 `v2_backend_full_child_closure_batch2.py`

这些是过程产物，不属于证据。建议统一写进 `.work/` 或加 `.gitignore`，
证据目录只保留机器可读的结论 JSON。

### A10 — 覆盖口径提醒（给报表用）

三种口径差距很大，报数时必须标明用的是哪一种：

| 口径 | 数值 |
|---|---|
| 计划闭合对象（文件数） | 78 / 78 = 100% |
| 核心 Scala 被引用 | 93 / 325 文件（28.6%）· 47,170 / 113,941 行（41.4%） |
| 其中真正的硬件连线方程 | 2,247 行，占 Python 有效行 9.3% |

未覆盖的核心 Scala 还有 **232 文件 / 66,771 行**，最大缺口：
DecodeUnitComp 2082、NewCSR 1752、StoreQueue 1597、PageTableCache 1471、
PageTableWalker 1441、MissQueue 1371、SMSPrefetcher 1361。
建议后续报表固定三行并报，避免单一口径造成误读。

### A11 — 欠账被台账清空，但硬件只多了 30 条方程（14:51 观察）

`c5eec43` 刚把"34 条 `CANDIDATE_V2_REUSE` 欠账"确立为必须单独如实报出的指标。
4 小时后，这个数字的演化是：

| | 10:30 | 14:51 |
|---|---:|---:|
| `CANDIDATE_V2_REUSE` | 34 | **0** |
| `VALIDATOR_PASS_BOUNDED` | 12 | 46 |
| `.eq()` 硬件方程 | 2,247 | **2,277（+30）** |
| Python 有效行 | 24,060 | 24,770（+710） |
| 新增 `*_observation()` 纯 Python 函数 | — | +29 |

**34 条晋升全部由 `docs(v2)` 提交完成**，只改 `V2-Core-Rewrite-Inventory.json`
里两个字段（`id` 行顺带把 CRLF 转 LF，所以 diff 里出现"内容相同的增删行"）。
配对结构是：

```
feat(v2): expose signed counter replacement observations   ← 动 2 个文件约 20 行
docs(v2): promote signed replacement entries               ← 只改台账 2 条状态
```

那批 `feat` 动的是**纯 Python 观测函数**（返回 dict，如
`replacement_observation` / `signed_counter_observation`），今天共 29 个。
它们是有价值的——等于给每个模块建一个可差分的行为 oracle——
但**不生成硬件**，且每条平均 10 行，无法承载 SRT16Divider、CSRs 这类模块的完整语义。

**这不是作弊，但是口径风险**：报表上"重写欠账 34 → 0"读起来像欠账还清了，
而同期新增硬件语义是 30 条连线方程。建议：

1. 报表里把「台账晋升条数」与「新增 `.eq()` 方程数」**并排显示**，
   两者当前是 34 : 30，不该只出现前者。
2. `*_observation()` 应在证据里显式标注为 `PYTHON_ORACLE` 类型，
   与生成 RTL 的实现区分开，避免计入"已重写硬件"。
3. 明确一条：**台账状态变更不能单独构成一个 wave**。
   现在 `docs(v2): promote X entries` 是独立提交，
   按 `09ea342` 的原文精神（"Evidence-only, hash-only… do not reduce this
   rewrite debt"）应当并入对应的 `feat` 提交。

### A12 — 两本台账对欠账说法不一致

- `V2-Core-Rewrite-Inventory.json` → `CANDIDATE_V2_REUSE = 0`
- `validation/v2-core-wave-progress-20260916.json` →
  `{"core_entries_validator_pass_bounded": 25, "core_entries_candidate_v2_reuse": 21}`
  （其 `implemented_commits` 停在 `6278c65`，即 09:28 的快照）

两本账对同一个"剩余欠账"给出 0 与 21。既然新政策专门要求如实报这个数，
就让其中一个成为唯一权威（建议以 core inventory 为准），
另一个改为引用它的计数，而不是各自维护。
