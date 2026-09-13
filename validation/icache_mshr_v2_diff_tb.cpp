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
  unsigned fencei, flush, wfi, req;
  std::uint64_t blk, set, lk0_blk, lk0_set, lk1_blk, lk1_set;
  unsigned acq_ready, victim, invalid;
};

// Generate the deterministic MSHR stream shared by direct and reference runs.
// 生成 direct 与参考运行共用的确定性 MSHR 流。
static std::vector<Event> events() {
  std::vector<Event> rows;
  std::uint32_t state = 0xA5A55A5AU;
  for (unsigned cycle = 0; cycle < 320; ++cycle) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5;
    rows.push_back({
      state & 1U,
#ifdef PREFETCH
      (state >> 1) & 1U,
#else
      0U,
#endif
      (state >> 2) & 1U, (state >> 3) & 1U,
      (state >> 4) & ((1ULL << 42) - 1ULL), (state >> 10) & 0xFFU,
      (state >> 12) & ((1ULL << 42) - 1ULL), (state >> 18) & 0xFFU,
      (state >> 20) & ((1ULL << 42) - 1ULL), (state >> 26) & 0xFFU,
      (state >> 27) & 1U, (state >> 28) & 3U, (state >> 30) & 1U});
  }
  return rows;
}

// Drive common ports, retaining the exact extracted V2 field names.
// 驱动公共端口并保留精确提取的 V2 字段名。
static void drive(DutType &dut, const Event &e) {
#ifdef TARGET
  dut.io_fencei=e.fencei; dut.io_flush=e.flush; dut.io_wfi_wfiReq=e.wfi; dut.io_invalid=e.invalid;
  dut.io_req_valid=e.req; dut.io_req_bits_blkPaddr=e.blk; dut.io_req_bits_vSetIdx=e.set;
  dut.io_acquire_ready=e.acq_ready; dut.io_victimWay=e.victim;
  dut.io_lookUps_0_info_valid=1; dut.io_lookUps_1_info_valid=1;
#else
  dut.io_fencei=e.fencei;
#ifdef PREFETCH
  dut.io_flush=e.flush;
#endif
  dut.io_wfi_wfiReq=e.wfi; dut.io_invalid=e.invalid;
  dut.io_req_valid=e.req; dut.io_req_bits_blkPaddr=e.blk; dut.io_req_bits_vSetIdx=e.set;
  dut.io_acquire_ready=e.acq_ready; dut.io_victimWay=e.victim;
#endif
  dut.io_lookUps_0_info_bits_blkPaddr=e.lk0_blk; dut.io_lookUps_0_info_bits_vSetIdx=e.lk0_set;
  dut.io_lookUps_1_info_bits_blkPaddr=e.lk1_blk; dut.io_lookUps_1_info_bits_vSetIdx=e.lk1_set;
}

// Advance one generated clock cycle. / 推进一个生成时钟周期。
static void tick(DutType &dut) {
#ifdef TARGET
  dut.rst=0; dut.clk=0; dut.eval(); dut.clk=1; dut.eval(); dut.clk=0; dut.eval();
#else
  dut.reset=0; dut.clock=0; dut.eval(); dut.clock=1; dut.eval(); dut.clock=0; dut.eval();
#endif
}

// Emit the common observable MSHR trace. / 输出 MSHR 公共可观测轨迹。
int main(int argc, char **argv) {
  VerilatedContext context; context.commandArgs(argc, argv); DutType dut{&context};
#ifdef TARGET
  dut.rst=1; dut.clk=0; dut.eval(); dut.clk=1; dut.eval(); dut.clk=0; dut.eval(); dut.rst=0;
#else
  dut.reset=1; dut.clock=0; dut.eval(); dut.clock=1; dut.eval(); dut.clock=0; dut.eval(); dut.reset=0;
#endif
  unsigned cycle = 0;
  for (const Event &e : events()) {
    drive(dut,e); dut.eval();
    std::printf("{\"cycle\":%u,\"fencei\":%u,\"flush\":%u,\"wfi\":%u,\"req\":%u,\"blk\":%llu,\"set\":%llu,\"lk0_blk\":%llu,\"lk0_set\":%llu,\"lk1_blk\":%llu,\"lk1_set\":%llu,\"acq_ready\":%u,\"victim\":%u,\"invalid\":%u,\"req_ready\":%u,\"acquire_valid\":%u,\"acquire_address\":%llu,\"acquire_v_set_idx\":%u,\"lookup_hit0\":%u,\"lookup_hit1\":%u,\"info_valid\":%u,\"info_blk_paddr\":%llu,\"info_v_set_idx\":%u,\"info_way\":%u,\"wfi_safe\":%u}\n",
      cycle++,e.fencei,e.flush,e.wfi,e.req,(unsigned long long)e.blk,(unsigned long long)e.set,
      (unsigned long long)e.lk0_blk,(unsigned long long)e.lk0_set,(unsigned long long)e.lk1_blk,(unsigned long long)e.lk1_set,
      e.acq_ready,e.victim,e.invalid,unsigned(dut.io_req_ready),unsigned(dut.io_acquire_valid),
      (unsigned long long)dut.io_acquire_bits_acquire_address,unsigned(dut.io_acquire_bits_vSetIdx),
      unsigned(dut.io_lookUps_0_hit),unsigned(dut.io_lookUps_1_hit),unsigned(dut.io_resp_valid),
      (unsigned long long)dut.io_resp_bits_blkPaddr,unsigned(dut.io_resp_bits_vSetIdx),unsigned(dut.io_resp_bits_way),unsigned(dut.io_wfi_wfiSafe));
    tick(dut);
  }
  return 0;
}
