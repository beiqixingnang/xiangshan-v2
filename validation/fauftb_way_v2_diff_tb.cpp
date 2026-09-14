#include "verilated.h"
#include "VFauFTBWay.h"

#include <cstdint>
#include <cstdio>
#include <vector>

struct Event {
  unsigned req_tag;
  unsigned update_tag;
  unsigned write_valid;
  unsigned write_tag;
  std::uint64_t payload;
};

// Generate deterministic hit, miss, write-bypass, and idle transactions.
// 生成确定性的命中、未命中、写旁路和空闲事务。
static std::vector<Event> events() {
  std::vector<Event> rows;
  rows.push_back({0x0000U, 0x0123U, 1U, 0x0123U, 0x0123456789abcdefULL});
  rows.push_back({0x0123U, 0x0123U, 0U, 0U, 0U});
  rows.push_back({0x0123U, 0x0a55U, 1U, 0x0a55U, 0x0fedcba987654321ULL});
  rows.push_back({0x0a55U, 0x0123U, 1U, 0x0a55U, 0x0055aa55aa55aa55ULL});
  std::uint32_t state = 0xFA7FB142U;
  for (unsigned cycle = 0; cycle < 384; ++cycle) {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    const unsigned write_valid = ((state >> 28) & 3U) != 0U;
    const unsigned write_tag = (state >> 4) & 0xffffU;
    const unsigned req_tag = (cycle % 5U == 0U) ? write_tag : ((state >> 16) & 0xffffU);
    const unsigned update_tag = (cycle % 7U == 0U) ? write_tag : ((state >> 1) & 0xffffU);
    const std::uint64_t payload = (static_cast<std::uint64_t>(state) << 32) | (state ^ 0x9e3779b9U);
    rows.push_back({req_tag, update_tag, write_valid, write_tag, payload});
  }
  return rows;
}

// Drive one event's entry fields from its deterministic payload.
// 根据确定性载荷驱动一个事务的条目字段。
static void drive(VFauFTBWay &dut, const Event &event) {
  const std::uint64_t value = event.payload;
  dut.io_req_tag = event.req_tag;
  dut.io_update_req_tag = event.update_tag;
  dut.io_write_valid = event.write_valid;
  dut.io_write_tag = event.write_tag;
  dut.io_write_entry_isCall = (value >> 0) & 1U;
  dut.io_write_entry_isRet = (value >> 1) & 1U;
  dut.io_write_entry_isJalr = (value >> 2) & 1U;
  dut.io_write_entry_valid = (value >> 3) & 1U;
  dut.io_write_entry_brSlots_0_offset = (value >> 4) & 0xfU;
  dut.io_write_entry_brSlots_0_sharing = (value >> 8) & 1U;
  dut.io_write_entry_brSlots_0_valid = (value >> 9) & 1U;
  dut.io_write_entry_brSlots_0_lower = (value >> 10) & 0xfffU;
  dut.io_write_entry_brSlots_0_tarStat = (value >> 22) & 3U;
  dut.io_write_entry_tailSlot_offset = (value >> 24) & 0xfU;
  dut.io_write_entry_tailSlot_sharing = (value >> 28) & 1U;
  dut.io_write_entry_tailSlot_valid = (value >> 29) & 1U;
  dut.io_write_entry_tailSlot_lower = (value >> 30) & 0xfffffU;
  dut.io_write_entry_tailSlot_tarStat = (value >> 50) & 3U;
  dut.io_write_entry_pftAddr = (value >> 52) & 0xfU;
  dut.io_write_entry_carry = (value >> 56) & 1U;
  dut.io_write_entry_last_may_be_rvi_call = (value >> 57) & 1U;
  dut.io_write_entry_strong_bias_0 = (value >> 58) & 1U;
  dut.io_write_entry_strong_bias_1 = (value >> 59) & 1U;
}

// Pack all stored response fields into one canonical 60-bit observation.
// 将所有存储响应字段打包成一个规范化的 60 位观测值。
static std::uint64_t response_pack(const VFauFTBWay &dut) {
  std::uint64_t value = 0;
  value |= static_cast<std::uint64_t>(dut.io_resp_isCall) << 0;
  value |= static_cast<std::uint64_t>(dut.io_resp_isRet) << 1;
  value |= static_cast<std::uint64_t>(dut.io_resp_isJalr) << 2;
  value |= static_cast<std::uint64_t>(dut.io_resp_valid) << 3;
  value |= static_cast<std::uint64_t>(dut.io_resp_brSlots_0_offset) << 4;
  value |= static_cast<std::uint64_t>(dut.io_resp_brSlots_0_sharing) << 8;
  value |= static_cast<std::uint64_t>(dut.io_resp_brSlots_0_valid) << 9;
  value |= static_cast<std::uint64_t>(dut.io_resp_brSlots_0_lower) << 10;
  value |= static_cast<std::uint64_t>(dut.io_resp_brSlots_0_tarStat) << 22;
  value |= static_cast<std::uint64_t>(dut.io_resp_tailSlot_offset) << 24;
  value |= static_cast<std::uint64_t>(dut.io_resp_tailSlot_sharing) << 28;
  value |= static_cast<std::uint64_t>(dut.io_resp_tailSlot_valid) << 29;
  value |= static_cast<std::uint64_t>(dut.io_resp_tailSlot_lower) << 30;
  value |= static_cast<std::uint64_t>(dut.io_resp_tailSlot_tarStat) << 50;
  value |= static_cast<std::uint64_t>(dut.io_resp_pftAddr) << 52;
  value |= static_cast<std::uint64_t>(dut.io_resp_carry) << 56;
  value |= static_cast<std::uint64_t>(dut.io_resp_last_may_be_rvi_call) << 57;
  value |= static_cast<std::uint64_t>(dut.io_resp_strong_bias_0) << 58;
  value |= static_cast<std::uint64_t>(dut.io_resp_strong_bias_1) << 59;
  return value;
}

// Advance one asynchronous-reset clock edge. / 推进一个异步复位时钟沿。
static void tick(VFauFTBWay &dut) {
  dut.clock = 0;
  dut.eval();
  dut.clock = 1;
  dut.eval();
  dut.clock = 0;
  dut.eval();
}

// Emit the canonical FauFTBWay differential trace.
// 输出规范化 FauFTBWay 差分轨迹。
int main(int argc, char **argv) {
  VerilatedContext context;
  context.commandArgs(argc, argv);
  VFauFTBWay dut{&context};
  dut.reset = 1;
  tick(dut);
  dut.reset = 0;

  bool known_response = false;
  unsigned cycle = 0;
  for (const Event &event : events()) {
    drive(dut, event);
    dut.eval();
    const std::uint64_t packed = known_response ? response_pack(dut) : 0U;
    std::printf(
        "{\"cycle\":%u,\"req_tag\":%u,\"update_tag\":%u,\"write_valid\":%u,\"write_tag\":%u,\"resp_hit\":%u,\"update_hit\":%u,\"resp_pack\":%llu}\n",
        cycle++, event.req_tag, event.update_tag, event.write_valid, event.write_tag,
        unsigned(dut.io_resp_hit), unsigned(dut.io_update_hit),
        static_cast<unsigned long long>(packed));
    known_response = known_response || event.write_valid;
    tick(dut);
  }
  return 0;
}
