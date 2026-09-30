# V2 验证流程与命名改造结果（2026-09-30）

本轮完成辅助仓库流程和命名改造，并启动第一轮剩余成员验证。严格 Build 计数仍为 **44/118**，`ACCEPTED=0`；不能把改名、缓存命中或单成员通过计为新的整族通过。

## 已落地

- 155 个正式 Build/Testing 脚本按直接父目录前缀改名，17 个项目自有验证文件同步本地化；项目 API 使用 UHSCore、UHSTile、UHSCTop。
- 静态、direct、ABI、确定性、参考 view 和 lint 前置；失败基线阻止 aggregate 与负控。
- 按当前成员 RTL、完整参考闭包、miter、工具版本及 producer/MRO 依赖复用完整 PASS 收据。缓存持久化到被忽略的 `validation/.cache/strict-family`；修改同一 Build 的其他成员，不会让未改变 RTL 的成员重新求解。
- 原 formal 命令、日志、结论和覆盖保留；历史 producer 用 Git 绑定的文本快照保存，当前独立审计核验原收据与当前 DUT。已补 origin 缺失、改锚、布尔零、空成功标记及缓存负控缺失的反向破坏回归。

## 实测与第一轮修复

| 家族 | 冷跑 | 缓存复跑 | 结果 |
| --- | ---: | ---: | --- |
| Prefetch Metadata | 101.852 秒 | 42.665 秒 | 两成员完整证明保留 |
| UHSTile IntBuffer | 10.401 秒 | 5.938 秒 | 三成员完整证明保留 |

WbArbiter 预检在约 10 秒内定位缺直接测试及两处 ABI 缺口，没有启动 formal。
VectorFamily 首轮约 34 秒完成六成员验证，发现 VIAlu 的实际 SAT 反例：`isExt` 与 `isDstMask` 同时有效时，优先级 Mux 丢掉参考按位 OR 的一项。已修正并通过 **8192/8192** 全输入组合、无约束 SAT 和双侧决定性负控。复跑后成员通过数由 2/6 增至 **3/6**，未改变的两成员命中 formal 缓存；整族仍为 `STRICT_PENDING`。

Og2ForVector 仍有 5670 个未证明单元。VTypeBuffer 当前全零候选与参考复位后的 `io_canEnq` 不符；VecExcpDataMergeModule 当前缺真实行为，并且参考 view 存在 Yosys `OP_CAST` 解析阻塞。这些要分别补实现和解决验证器能力，不能用延长超时或改参考绕过。

## 验证和边界

- 共享 rail 回归 12/12、中央审计回归 11/11；聚焦 Pyright 零错误。
- 155 个正式脚本命名审计通过；受影响 Python 内存编译、UTF-8/LF 和 diff 检查通过。
- 1976/1976 锁定参考切片核验通过，写入数 0。严格证明覆盖的公开参考模块为 185/1976；锁定切片存在不等于行为通过。
- 直接脚本 36/37 通过；ClockGate 的旧 `$dlatch` 断言失败在本轮基线 `8ddf8d6` 上复现，保持失败，未放宽测试。
- 中央账本仍记录 6 份非计数 pending 和 4 份历史摘要审计失败；整体审计退出 1，严格数 44/118 仍有独立依据。
- 主仓计划历史 `HW-EVENT-0574` 缺少 `Supersedes`，整份治理失败；本轮 EOF 追加的字节保留和 14 字段顺序独立通过，冻结历史未回写。

`python/**/*.py` 当前总行数 **93280（本轮 +127）**，非空行 **86254（本轮 +109）**。同一基线的 93153 和 86145 分别是总行与非空行，旧交接报告将它们解释为不同时间口径并不准确。

父级和整机闭包、复位启动边界、完整 XSTop 差分、许可证复核、主仓产品迁移和用户验收仍未完成。后续顺序仍是 V2 完整验收后替换现行 CPU，再推进 Vortex Python 版验证、视频输出升级及其他部件/控制器协作内化。

机器证据：`validation/v2-verification-workflow-upgrade-results.json`、`v2-verification-flow-benchmark.json`、`v2-vi-alu-leaf-repair-results.json` 和 `v2-strict-equivalence-progress.json`。
