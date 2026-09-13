#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <vector>

#ifdef TARGET
#include "VFIFOReg.h"
#else
#include "VFIFOReg.h"
#endif

struct Event { unsigned enq; unsigned bits; unsigned deq; unsigned flush; };

// Advance one synchronous cycle for either generated clock naming convention.
// 为任一生成时钟命名约定推进一个同步周期。
template <typename Dut>
static void tick(Dut &dut) {
#ifdef TARGET
  dut.rst = 0; dut.clk = 0; dut.eval(); dut.clk = 1; dut.eval(); dut.clk = 0; dut.eval();
#else
  dut.reset = 0; dut.clock = 0; dut.eval(); dut.clock = 1; dut.eval(); dut.clock = 0; dut.eval();
#endif
}

// Generate boundary, wrap, and pseudo-random FIFO transactions.
// 生成边界、回绕及伪随机 FIFO 事务。
static std::vector<Event> events() {
  std::vector<Event> rows;
  for (unsigned value = 0; value < 10; ++value) rows.push_back({1, value, 0, 0});
  rows.push_back({1, 0xF, 0, 0});
  rows.push_back({0, 0, 1, 0});
  rows.push_back({0, 0, 1, 0});
  rows.push_back({1, 9, 1, 0});
  rows.push_back({0, 0, 0, 1});
  std::uint32_t state = 0x13579BDFU;
  for (unsigned cycle = 0; cycle < 512; ++cycle) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5;
    unsigned flush = (state >> 2) & 1U;
    if (cycle % 64U == 0U) flush = 1;
    unsigned enq = state & 1U, deq = (state >> 1) & 1U;
    if (cycle % 37U == 0U) enq = deq = 1;
    rows.push_back({enq, (state >> 8) & 0xFU, deq, flush});
  }
  return rows;
}

// Emit the canonical FIFO observation stream. / 输出规范 FIFO 观测流。
template <typename Dut>
static int run(Dut &dut) {
#ifdef TARGET
  dut.rst = 1; dut.clk = 0; dut.eval(); dut.clk = 1; dut.eval(); dut.clk = 0; dut.eval(); dut.rst = 0;
#else
  dut.reset = 1; dut.clock = 0; dut.eval(); dut.clock = 1; dut.eval(); dut.clock = 0; dut.eval(); dut.reset = 0;
#endif
  unsigned cycle = 0;
  for (const Event event : events()) {
    dut.io_enq_valid = event.enq; dut.io_enq_bits = event.bits; dut.io_deq_ready = event.deq; dut.io_flush = event.flush;
    dut.eval();
#ifdef TARGET
    std::printf("{\"cycle\":%u,\"enq\":%u,\"bits\":%u,\"deq\":%u,\"flush\":%u,\"enq_ready\":%u,\"deq_valid\":%u,\"deq_bits\":%u}\n",
                cycle++, event.enq, event.bits, event.deq, event.flush,
                unsigned(dut.io_enq_ready), unsigned(dut.io_deq_valid), unsigned(dut.io_deq_bits));
#else
    std::printf("{\"cycle\":%u,\"enq\":%u,\"bits\":%u,\"deq\":%u,\"flush\":%u,\"enq_ready\":%u,\"deq_valid\":%u,\"deq_bits\":%u}\n",
                cycle++, event.enq, event.bits, event.deq, event.flush,
                unsigned(dut.io_enq_ready), unsigned(dut.io_deq_valid), unsigned(dut.io_deq_bits));
#endif
    tick(dut);
  }
  return 0;
}

int main(int argc, char **argv) {
  VerilatedContext context; context.commandArgs(argc, argv); VFIFOReg dut{&context}; return run(dut);
}
