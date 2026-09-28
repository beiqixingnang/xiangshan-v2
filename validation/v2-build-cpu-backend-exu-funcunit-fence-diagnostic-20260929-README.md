# FuncUnit Fence 当前源码诊断

本轮修复了 Fence VMID `sfence` ID 的位序：锁定参考要求高两位为零、输入源 ID 的低十四位保持在输出低十四位，Python/Amaranth 现在使用 `Cat(id_r[0:14], Const(0, 2))`。

修复后的当前源码导出满足 ABI、确定性和 target/locked Verilator lint，但 Fence strict rail 仍为 2/94 proven、92 个 `$equiv` cells 未证明，Yosys 返回 1。因此本记录只证明修复方向和当前诊断，strict 完成数增量为 0，canonical FuncUnit evidence 未覆盖，不能标记 `ACCEPTED`。

后续必须在 ASCII 临时目录串行重跑 FuncUnit 全 30-member catalog、双侧负控和父级闭包；仍需修复 DivUnit 等其他时序行为缺口。
