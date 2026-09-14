#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <vector>

#ifdef TARGET
#include "VICacheMSHR.h"
using DutType = VICacheMSHR;
#else
#ifdef PREFETCH
#include "VICacheMSHR_4.h"
using DutType = VICacheMSHR_4;
#else
#include "VICacheMSHR.h"
using DutType = VICacheMSHR;
#endif
#endif

struct Event {
  unsigned reset;
  unsigned fencei;
  unsigned flush;
  unsigned wfi;
  unsigned req;
  std::uint64_t blk;
  std::uint64_t set;
  std::uint64_t lk0_blk;
  std::uint64_t lk0_set;
  std::uint64_t lk1_blk;
  std::uint64_t lk1_set;
  unsigned acq_ready;
  unsigned victim;
  unsigned invalid;
};

static std::uint32_t next_state(std::uint32_t state) {
  state ^= state << 13;
  state ^= state >> 17;
  state ^= state << 5;
  return state;
}

// Produce directed corner cases followed by a deterministic stress stream.
// 先产生定向边界场景，再产生确定性的压力事务流。
static std::vector<Event> events() {
  std::vector<Event> rows;
  auto add = [&rows](unsigned reset, unsigned fencei, unsigned flush,
                     unsigned wfi, unsigned req, std::uint64_t blk,
                     std::uint64_t set, std::uint64_t lk0_blk,
                     std::uint64_t lk0_set, std::uint64_t lk1_blk,
                     std::uint64_t lk1_set, unsigned acq_ready,
                     unsigned victim, unsigned invalid) {
    rows.push_back({reset, fencei, flush, wfi, req, blk, set, lk0_blk,
                    lk0_set, lk1_blk, lk1_set, acq_ready, victim, invalid});
  };

  // Reset assertion is intentionally observable between clock edges.
  add(1, 1, 1, 1, 1, 0x12345, 0x55, 0x12345, 0x55, 0, 0, 1, 3, 1);
  add(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  // Request blocked by fence/flush, then accepted and held under backpressure.
  add(0, 1, 1, 0, 1, 0x2AAAA, 0x12, 0x2AAAA, 0x12, 0, 0, 0, 1, 0);
  add(0, 0, 0, 0, 1, 0x2AAAA, 0x12, 0x2AAAA, 0x12, 0, 0, 0, 1, 0);
  add(0, 0, 0, 1, 0, 0, 0, 0x2AAAA, 0x12, 0x2AAAA, 0x12, 0, 1, 0);
  add(0, 0, 0, 0, 0, 0, 0, 0x2AAAA, 0x12, 0x2AAAA, 0x12, 1, 2, 0);
  // An issued entry survives an external flush until invalidation.
  add(0, 0, 1, 0, 0, 0, 0, 0x2AAAA, 0x12, 0, 0, 0, 2, 0);
  add(0, 0, 0, 0, 0, 0, 0, 0x2AAAA, 0x12, 0, 0, 1, 2, 1);
  add(0, 0, 0, 0, 1, 0x3FFFF, 0xFF, 0x3FFFF, 0xFF, 0x3FFFF, 0xFF, 1, 0, 0);
  // Simultaneous invalid and request exercises Chisel's last assignment rule.
  add(0, 0, 0, 0, 1, 0x15555, 0xA5, 0x15555, 0xA5, 0, 0, 0, 3, 1);
  add(0, 0, 0, 0, 0, 0, 0, 0x15555, 0xA5, 0, 0, 1, 3, 0);

  std::uint32_t state = 0xD15EA5E5U;
  for (unsigned cycle = 0; cycle < 2048; ++cycle) {
    state = next_state(state);
    unsigned reset = (cycle == 511 || cycle == 1537) ? 1U : 0U;
    unsigned fencei = (state >> 0) & 1U;
    unsigned flush = (state >> 1) & 1U;
    unsigned wfi = (state >> 2) & 1U;
    unsigned req = (state >> 3) & 1U;
    if (cycle % 43 == 0) fencei = 1;
    if (cycle % 47 == 0) flush = 1;
    if (cycle % 61 == 0) req = 1;
    if (cycle % 79 == 0) wfi = 1;
    if (reset) {
      fencei = flush = wfi = req = 1;
    }
    add(reset, fencei, flush, wfi, req,
        (state >> 4) & ((1ULL << 42) - 1ULL),
        (state >> 10) & 0xFFU,
        (state >> 12) & ((1ULL << 42) - 1ULL),
        (state >> 18) & 0xFFU,
        (state >> 20) & ((1ULL << 42) - 1ULL),
        (state >> 26) & 0xFFU,
        (state >> 27) & 1U, (state >> 28) & 3U, (state >> 30) & 1U);
  }
  return rows;
}

// Drive all common ports while preserving extracted V2 names.
// 驱动全部公共端口并保留提取的 V2 名称。
static void drive(DutType &dut, const Event &e) {
#ifdef TARGET
  dut.rst = e.reset;
  dut.io_fencei = e.fencei;
  dut.io_flush = e.flush;
#else
  dut.reset = e.reset;
  dut.io_fencei = e.fencei;
#ifdef PREFETCH
  dut.io_flush = e.flush;
#endif
#endif
  dut.io_wfi_wfiReq = e.wfi;
  dut.io_invalid = e.invalid;
  dut.io_req_valid = e.req;
  dut.io_req_bits_blkPaddr = e.blk;
  dut.io_req_bits_vSetIdx = e.set;
  dut.io_acquire_ready = e.acq_ready;
  dut.io_victimWay = e.victim;
  dut.io_lookUps_0_info_bits_blkPaddr = e.lk0_blk;
  dut.io_lookUps_0_info_bits_vSetIdx = e.lk0_set;
  dut.io_lookUps_1_info_bits_blkPaddr = e.lk1_blk;
  dut.io_lookUps_1_info_bits_vSetIdx = e.lk1_set;
#ifdef TARGET
  dut.io_lookUps_0_info_valid = 1;
  dut.io_lookUps_1_info_valid = 1;
#endif
}

// Advance one edge in the selected clock/reset naming convention.
// 按选定的时钟/复位命名约定推进一个时钟边沿。
static void tick(DutType &dut) {
#ifdef TARGET
  dut.clk = 0;
  dut.eval();
  dut.clk = 1;
  dut.eval();
  dut.clk = 0;
  dut.eval();
#else
  dut.clock = 0;
  dut.eval();
  dut.clock = 1;
  dut.eval();
  dut.clock = 0;
  dut.eval();
#endif
}

// Emit the shared observable trace used for target/reference comparison.
// 输出目标/参考比较所用的共享可观测轨迹。
int main(int argc, char **argv) {
  VerilatedContext context;
  context.commandArgs(argc, argv);
  DutType dut{&context};

  Event init{1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
  drive(dut, init);
#ifdef TARGET
  dut.clk = 0;
#else
  dut.clock = 0;
#endif
  dut.eval();
  tick(dut);

  unsigned cycle = 0;
  for (const Event &e : events()) {
    drive(dut, e);
#ifdef TARGET
    dut.clk = 0;
#else
    dut.clock = 0;
#endif
    dut.eval();
    std::printf(
        "{\"cycle\":%u,\"reset\":%u,\"fencei\":%u,\"flush\":%u,\"wfi\":%u,\"req\":%u,\"blk\":%llu,\"set\":%llu,\"lk0_blk\":%llu,\"lk0_set\":%llu,\"lk1_blk\":%llu,\"lk1_set\":%llu,\"acq_ready\":%u,\"victim\":%u,\"invalid\":%u,\"req_ready\":%u,\"acquire_valid\":%u,\"acquire_address\":%llu,\"acquire_v_set_idx\":%u,\"lookup_hit0\":%u,\"lookup_hit1\":%u,\"info_valid\":%u,\"info_blk_paddr\":%llu,\"info_v_set_idx\":%u,\"info_way\":%u,\"wfi_safe\":%u}\n",
        cycle++, e.reset, e.fencei, e.flush, e.wfi, e.req,
        static_cast<unsigned long long>(e.blk),
        static_cast<unsigned long long>(e.set),
        static_cast<unsigned long long>(e.lk0_blk),
        static_cast<unsigned long long>(e.lk0_set),
        static_cast<unsigned long long>(e.lk1_blk),
        static_cast<unsigned long long>(e.lk1_set), e.acq_ready, e.victim,
        e.invalid, static_cast<unsigned>(dut.io_req_ready),
        static_cast<unsigned>(dut.io_acquire_valid),
        static_cast<unsigned long long>(dut.io_acquire_bits_acquire_address),
        static_cast<unsigned>(dut.io_acquire_bits_vSetIdx),
        static_cast<unsigned>(dut.io_lookUps_0_hit),
        static_cast<unsigned>(dut.io_lookUps_1_hit),
        static_cast<unsigned>(dut.io_resp_valid),
        static_cast<unsigned long long>(dut.io_resp_bits_blkPaddr),
        static_cast<unsigned>(dut.io_resp_bits_vSetIdx),
        static_cast<unsigned>(dut.io_resp_bits_way),
        static_cast<unsigned>(dut.io_wfi_wfiSafe));
    tick(dut);
  }
  return 0;
}
