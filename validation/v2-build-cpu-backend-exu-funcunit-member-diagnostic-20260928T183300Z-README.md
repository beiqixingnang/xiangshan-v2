# FuncUnit 当前源码成员级 strict 诊断

本记录对当前 FuncUnit Build 的 7 个时序成员重新运行了成员级等价证明。结论是 **7/7 仍失败，548 个 `$equiv` cells 未证明，strict count delta 为 0**。canonical strict evidence 保持原样，未把失败改写成 `ACCEPTED`。

机器可读结果：[v2-build-cpu-backend-exu-funcunit-member-diagnostic-20260928T183300Z.json](v2-build-cpu-backend-exu-funcunit-member-diagnostic-20260928T183300Z.json)

## 本轮结果

| 成员 | rail | 单元总数 | 已证明 | 未证明 | Yosys | 用时 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Bku | `equiv_simple -undef -short -seq 1` | 83 | 18 | 65 | exit 1 | 12.236 s |
| BlockCipherModule | `equiv_simple -undef -short -seq 1` | 64 | 0 | 64 | exit 1 | 7.702 s |
| CryptoModule | `equiv_simple -undef -short -seq 1` | 64 | 0 | 64 | exit 1 | 8.337 s |
| DivUnit | `equiv_simple -undef -short -seq 1` | 84 | 0 | 84 | exit 1 | 4.324 s |
| ExeUnit | `equiv_simple -undef -short -seq 1` | 117 | 2 | 115 | exit 1 | 72.442 s |
| Fence | `equiv_induct -undef` | 94 | 2 | 92 | exit 1 | 0.437 s |
| MulUnit | `equiv_induct -undef` | 83 | 19 | 64 | exit 1 | 51.704 s |
| **Total** |  | **589** | **41** | **548** |  |  |

所有 7 项的 target Verilator lint 和 locked-reference Verilator lint 均通过；所有 Yosys 命令均正常结束且未超时，但 strict success markers 均为 false。完整 stdout/stderr 原文、每条命令、视图与生成的 SV 输入保存在本机忽略目录 `validation/.work/funcunit-member-diagnostics-20260928T183300Z/`。JSON 记录了每个正式证明输出的 SHA-256 与字节数。

官方 FuncUnit 专用负控通过 4/4：组合 SAT 两侧对 `AddrAddModule.io_target` 注入变异；时序两侧对 `HashModule.io_out` 注入变异（target 侧使用专用 child-output 变异）。四种情况均检测到显式失败且未残留 success marker。负控诊断报告位于 `validation/.work/funcunit-member-diagnostics-20260928T183929Z/report.json`。

## 证据边界

本轮使用 Build SHA `362067ff…`、shared rail SHA `08c703d2…` 和 validator SHA `ef501889…`。旧 canonical evidence 仍记录 Build SHA `22a79c07…` 与 rail SHA `dbbe43ac…`。旧 aggregate SAT 的 PASS 仅覆盖 19 个组合成员，不能代替以上时序成员证明。

本轮只重跑 7 个此前失败的成员与 rail 负控，没有重新证明 catalog 其余成员，也没有复跑全部构建接受门禁。因此 canonical evidence 仍是 `STRICT_PENDING`，严格等价计数增量为 0，不能据此宣告 FuncUnit strict complete 或接受。

首次诊断曾把 formal 中间文件放在含中文字符的工作区路径，Yosys 读取时没有注册模块；该尝试已排除。正式结果来自随后使用 ASCII 临时路径的 fresh rerun。该问题及两次诊断报告的哈希均记录在 JSON 中。
