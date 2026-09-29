# FrontendBridge reset-entry 首分区诊断

当前 Queue(2) 指针实现与锁定参考保留全部公开输入；验证 wrapper 在首个时钟沿为两侧分别施加 reset，之后恢复共同外部 reset，并只在启动期屏蔽输出。`instr_uncache_a` 仍恰有 54 个公开输出比较点，Yosys 返回 1，0/54 proven、54 个未证明。参考/目标 Verilator、direct、ABI 和确定性检查通过。两侧变异在 baseline 未证明时不构成决定性负控。

这个结果否定了“只缺共同首拍 reset 即可证明”的假设；它没有给出行为反例，也没有完成其他五个分区或完整 950-bit 输出证明。整 Build 保持 `STRICT_PENDING`，严格计数增量为 0。机器记录见 [JSON](v2-frontendbridge-reset-entry-first-partition-diagnostic-20260929.json)。
