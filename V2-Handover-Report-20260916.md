# V2 交接报告 — Cube（WorkBuddy 侧）→ 执行方

_2026-09-16 23:05_。本报告只写增量事实：我在你 9/16 中断点之后做了什么、做到哪、请先验证什么再往后推。总纲与既有一切约束默认你已知晓并继续生效，不赘述。

## 0. 接手时的断点

- 你的根会话止于 `gptcodex.top` 上游耗尽（9/16 15:12 末次写入），非 Pyright 原因——此前已核实，不再展开。
- 接手时 HEAD：`10bea1a`；聚合 Build 78/78 在盘；核心清单 46 `VALIDATOR_PASS_BOUNDED` + 1 `RETIRED`；锁定层级比对 1976 模块中仅 19 闭环。

## 1. 我新增的基础设施（已随 wave-1 提交）

| 文件 | 内容 |
| --- | --- |
| `validation/v2_locked_hierarchy_extract.py` | 从 WSL 锁定参考 `XSTop.sv` 只读提取**机器可读锁定层级**：1976 模块的精确 ANSI 端口、子实例、Scala 出处 |
| `validation/v2-locked-hierarchy.json` | 上述产物（冻结事实，**只读，勿改**） |
| `validation/v2_hierarchy_coverage.py` → `validation/v2-hierarchy-coverage.json` | 每个锁定模块的覆盖状态视图，接手时 156 core + 722 family + **1098 missing** |

## 2. Wave 1（已提交并推送，commit `8b181bc`）

四个聚合 Build 主题，补上当时最大的四个缺口家族：

| Build 文件 | 覆盖锁定模块 |
| --- | --- |
| `Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py` | ~374（CSRModule 寄存器家族） |
| `Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRLite-Hardware.py` | PMP/PMA/各级 CSR 映射 |
| `Cpu-Core/Build-Cpu.Dependency.Chisel.Decoupled-Hardware.py` | ~216（Queue1/2/68_*、BundleMap、PipeWithFlush） |
| `Cpu-Core/Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py` | ~57（Arbiter*、AsyncQueue*、Repeater 等） |

- 提交时独立复跑：82 文件共享静态审计六门全绿，Pyright 82/82 零错误（无 suppress），Decoupled/Arbiter 家族有 Verilator 对锁定参考的差分证据。
- 覆盖度推进到 **521 core + 973 family + 482 missing**。
- remote 已切为 `git@github.com:beiqixingnang/xiangshan-v2.git`（SSH），push 实测可用。

## 3. Wave 2（已提交；以下状态以当前 HEAD 和证据文件为准）

按计划新增的 wave-2 授权表（`V2-Rewrite-Execution-Plan.md` 未提交改动里有）落了四个主题：

| 主题 | 规模 | 当前状态 |
| --- | --- | --- |
| `Cpu-Core/Build-Cpu.Backend.Issue.Entries-Hardware.py` | 2060 行 | ✅ 已提交；34 模块端口面、确定性、结构向量、Verilator/Yosys 均 PASS；证据 `validation/v2-backend-issue-entries-family-results.json` 完整；状态 `DIRECT_TEST_PASS_BOUNDED`（行为闭包未建立） |
| `Cpu-Memory/Build-Cpu.Memory.Lsqueue.Uncache-Hardware.py` | 1724 行 | ⚠️ 已提交；端口面 42/42、Verilator/Yosys 局部编译 PASS，但锁定参考差分真实 FAIL（FreeList 1107/1200、UncacheEntry_15 23293/37600）；证据整体 `FAIL`，不得升级状态 |
| `Cpu-Core/Build-Cpu.Backend.Exu.FuncUnit-Hardware.py` | ~122KB | ⚠️ Build、validator 与证据已提交；30/30 端口面、确定性、Verilator/Yosys 通过，但 Alu/Bku 有界差分分别为 235/632 mismatches（3072 checks each），状态保持 `FAIL` |
| `Cpu-Core/Build-Cpu.Backend.Regfile.Regfile-Hardware.py` | ~448KB | ✅ Build、`validation/v2-backend-regfile-family-validator.py` 与证据已提交；97/97 端口面/确定性通过，10 个代表模块 Verilator/Yosys 通过；状态 `DIRECT_TEST_PASS_BOUNDED`，完整行为差分仍待补齐 |

配套：每主题有 focused validator（`validation/v2-*-family-validator.py` 或 `_validator.py` 命名）。

## 4. 请你按此顺序接手

1. **先审阅再动手**：复跑验证命令核对上表——重点看 Issue.Entries 证据 JSON 是否可复现（端口面比对、确定性、差分、Verilator/Yosys、Pyright），不要直接信我写的结果。
2. **修 Lsqueue.Uncache**：差分失败按例先查复位值、flow/pipe 旁路时序、full 标志 X 传播、向量 split 的拍序；Yosys 失败读它的报错原文（常见：多驱动、不支持结构）。修完重出证据。
3. **修 Exu.FuncUnit 的 Alu/Bku 差分失败**；Regfile.Regfile 的聚焦结构证据已由协调方补齐并提交，仍不得当作行为闭包。
4. 全部绿之后你再做一次独立核实（共享审计 + 全量 Pyright），然后统一提交 wave-2。
5. 之后继续当前 189 missing 里的其余家族，优先级建议看 `validation/v2-hierarchy-coverage.json` 按 Scala 来源聚类的 top 缺口。

## 6. Coordinator review addendum

The handover claims were independently checked on 2026-09-17. The pinned
hierarchy SHA-256 is unchanged. The independent shared audit reports 86/86
owned closure Build files passing UTF-8/LF, AST, `py_compile`, exact import,
`build_verilog`, and strict single-file Pyright (two non-closure integration
paths are explicitly excluded). Decoupled (216/216) and Arbiter (57) focused
reruns pass their bounded gates. FuncUnit's current evidence is a real FAIL
(Alu 235/3072 and Bku 632/3072 mismatches), Regfile now has a focused structure-only evidence file
(`DIRECT_TEST_PASS_BOUNDED`), and Lsqueue's behavioral checkpoint also fails.
`ACCEPTED` remains locked.

Subsequent coordinator work landed IssueEntries (`3e9f104`), Regfile
structure typing (`13e09c0`), and FuncUnit strict typing (`af425cc` through
`1cc5772`). The shared structure sweep is now 86/86, and the registered
hierarchy coverage is 811 core + 976 family + 189 missing after registering
the additional Regfile-owned Snapshot/RFRead/RFWB/WbFu roots, the CSR event
closure, the already-validated WrBypass family, and source aliases for the
validated Chisel/Lsqueue utility children. Lsqueue's fast
checkpoint is still a real failure (FreeList 1107/1200 and UncacheEntry_15
23293/37600 comparisons), so this report records structure only and does not
promote behavioral equivalence. The working tree also contains untracked
scratch scripts/logs; they are not part of the handover and must not be
blanket-staged.

## 5. 已知未闭合项（非本次引入）

- Pyright 历史 161 条的口径已由 wave-1 全量复扫清零，但若有别的口径残留，以你复扫为准。
- 父闭包 0/8、ACCEPTED=0 等里程碑照旧未动，Phase 1 状态上限不变。

—— Cube 🧊
