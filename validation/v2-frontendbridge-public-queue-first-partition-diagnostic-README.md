# FrontendBridge 首个公开队列分区诊断

本轮修正了诊断 wrapper 的比较边界：参考与目标使用不同的内部实例名，先各自 flatten，再执行 `equiv_make`。`instr_uncache_a` 现恰有 54 个公开输出比较点，不再把旧轨道的内部队列状态点误算为公开输出义务。全部输入端口保持连接，失效周期的 Decoupled payload 仍按对应 `valid` 门控。

当前锁定参考比对结果为 0/54 proven，54 个未证明。参考/目标 Verilator lint 和 direct test 通过。两侧输出变异都导致形式失败，但未变异 baseline 本身也是 0/54 proven，因此负控不具决定性，记录为 `INCONCLUSIVE`。其余五个队列分区和完整 950-bit public-output proof 均未运行。因此本记录只是 `STRICT_PENDING` 的分区诊断，整 Build strict 完成计数增量为 0，不能标记 `ACCEPTED`。

当前 Build、验证器和锁定参考的 SHA-256、实际 Yosys 命令、退出状态、输出捕获摘要及负控结果见 [v2-frontendbridge-public-queue-first-partition-diagnostic.json](v2-frontendbridge-public-queue-first-partition-diagnostic.json)。
