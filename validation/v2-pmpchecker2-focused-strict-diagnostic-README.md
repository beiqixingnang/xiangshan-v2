# PMPChecker_2 聚焦严格等价证据

本记录只覆盖 `Build-Cpu.Backend.Fu.PMP.Family` 中的 `PMPChecker_2` 成员，不覆盖整族。Build 使用纯 Python/Amaranth 实现 PMP/PMA 首项匹配、执行拒绝与 MMIO 位；输出仅在 `io_req_valid` 时钟沿更新。地址基址使用 Amaranth 低位优先的 `Cat(Const(0, 2), address)`，对应参考中的 `{address, 2'b00}`。

修复前的聚焦 rail 为 0/2 输出点 proven。一次有效的 reset-equalized bounded SAT 给出公开输出反例：`req=0x40000`、PMP/PMA 第 0 项地址为 `0x40000`、`A=3`、`mask=0` 时，错误的 `Cat(address, Const(0, 2))` 把零接在高位，误将请求判作命中。修复该位序并补非零地址 direct vector 后，当前源码的 locked-reference `equiv_induct -undef` 证明 2/2 输出点，Yosys exit 0；target 与 locked Verilator lint、327/327 ABI、重复同名导出、direct test 2/2 和 target/reference 双侧输出变异负控全部通过。

机器可读的当前源码哈希、命令、退出码、输出摘要、负控和 direct 结果在 [v2-pmpchecker2-focused-strict-diagnostic.json](v2-pmpchecker2-focused-strict-diagnostic.json)。验证器为 [v2_pmpchecker2_focused_validator.py](v2_pmpchecker2_focused_validator.py)。

此证据的状态是 `COMPLETE_EQUIVALENCE_VARIANT_ONLY`。`PMP`、`PMPChecker`、`PMPChecker_12` 和 `PMPEntryHandleModule` 仍未完成；整族仍是 `STRICT_PENDING`，Build strict 完成计数增量为 0，不能标记 `ACCEPTED` 或迁移到主仓库。
