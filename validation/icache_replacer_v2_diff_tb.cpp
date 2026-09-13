#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <vector>

#ifdef TARGET
#include "VICacheReplacer.h"
using DutType = VICacheReplacer;
#else
#include "VICacheReplacer.h"
using DutType = VICacheReplacer;
#endif

struct Event { unsigned tv0, ts0, tw0, tv1, ts1, tw1, vv, vs; };

// Generate deterministic two-port replacement transactions.
// 生成确定性的双端口替换事务。
static std::vector<Event> events() {
  std::vector<Event> rows;
  std::uint32_t state = 0xC001D00DU;
  for (unsigned cycle = 0; cycle < 320; ++cycle) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5;
    rows.push_back({state & 1U, (state >> 1) & 0xFFU, (state >> 9) & 3U,
                    (state >> 11) & 1U, (state >> 12) & 0xFFU, (state >> 20) & 3U,
                    (state >> 22) & 1U, (state >> 23) & 0xFFU});
  }
  return rows;
}

// Advance one target or reference clock. / 推进目标或参考时钟。
static void tick(DutType &dut) {
#ifdef TARGET
  dut.rst=0; dut.clk=0; dut.eval(); dut.clk=1; dut.eval(); dut.clk=0; dut.eval();
#else
  dut.reset=0; dut.clock=0; dut.eval(); dut.clock=1; dut.eval(); dut.clock=0; dut.eval();
#endif
}

// Emit the canonical replacement trace. / 输出规范替换轨迹。
int main(int argc, char **argv) {
  VerilatedContext context; context.commandArgs(argc, argv); DutType dut{&context};
#ifdef TARGET
  dut.rst=1; dut.clk=0; dut.eval(); dut.clk=1; dut.eval(); dut.clk=0; dut.eval(); dut.rst=0;
#else
  dut.reset=1; dut.clock=0; dut.eval(); dut.clock=1; dut.eval(); dut.clock=0; dut.eval(); dut.reset=0;
#endif
  unsigned cycle = 0;
  for (const Event &e : events()) {
    dut.io_touch_0_valid=e.tv0; dut.io_touch_0_bits_vSetIdx=e.ts0; dut.io_touch_0_bits_way=e.tw0;
    dut.io_touch_1_valid=e.tv1; dut.io_touch_1_bits_vSetIdx=e.ts1; dut.io_touch_1_bits_way=e.tw1;
    dut.io_victim_vSetIdx_valid=e.vv; dut.io_victim_vSetIdx_bits=e.vs; dut.eval();
    std::printf("{\"cycle\":%u,\"tv0\":%u,\"ts0\":%u,\"tw0\":%u,\"tv1\":%u,\"ts1\":%u,\"tw1\":%u,\"vv\":%u,\"vs\":%u,\"victim_way\":%u}\n",
                cycle++,e.tv0,e.ts0,e.tw0,e.tv1,e.ts1,e.tw1,e.vv,e.vs,unsigned(dut.io_victim_way));
    tick(dut);
  }
  return 0;
}
