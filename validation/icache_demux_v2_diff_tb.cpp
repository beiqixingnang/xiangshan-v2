#include "verilated.h"
#include <cstdint>
#include <cstdio>

#ifdef TARGET
#include "VDeMultiplexer.h"
#else
#ifdef N10
#include "VDeMultiplexer_1.h"
#else
#include "VDeMultiplexer.h"
#endif
#endif

// Drive one packed V2 request through either target or reference ports.
// 将打包的 V2 请求驱动到目标或参考端口。
template <typename Dut>
static void drive_payload(Dut &dut, std::uint64_t bits) {
#ifdef TARGET
  dut.io_in_bits = bits;
#else
  dut.io_in_bits_blkPaddr = bits & ((1ULL << 42) - 1ULL);
  dut.io_in_bits_vSetIdx = (bits >> 42) & 0xFFU;
#endif
}

// Drive ready bits for the selected generated specialization.
// 驱动所选生成特化的 ready 位。
template <typename Dut>
static void drive_ready(Dut &dut, unsigned ready) {
#ifdef N10
  dut.io_out_0_ready = (ready >> 0) & 1U;
  dut.io_out_1_ready = (ready >> 1) & 1U;
  dut.io_out_2_ready = (ready >> 2) & 1U;
  dut.io_out_3_ready = (ready >> 3) & 1U;
  dut.io_out_4_ready = (ready >> 4) & 1U;
  dut.io_out_5_ready = (ready >> 5) & 1U;
  dut.io_out_6_ready = (ready >> 6) & 1U;
  dut.io_out_7_ready = (ready >> 7) & 1U;
  dut.io_out_8_ready = (ready >> 8) & 1U;
  dut.io_out_9_ready = (ready >> 9) & 1U;
#else
  dut.io_out_0_ready = (ready >> 0) & 1U;
  dut.io_out_1_ready = (ready >> 1) & 1U;
  dut.io_out_2_ready = (ready >> 2) & 1U;
  dut.io_out_3_ready = (ready >> 3) & 1U;
#endif
}

// Read the generated output valid mask. / 读取生成的 output-valid 掩码。
template <typename Dut>
static unsigned read_valid(const Dut &dut) {
#ifdef N10
  return unsigned(dut.io_out_0_valid) | (unsigned(dut.io_out_1_valid) << 1)
      | (unsigned(dut.io_out_2_valid) << 2) | (unsigned(dut.io_out_3_valid) << 3)
      | (unsigned(dut.io_out_4_valid) << 4) | (unsigned(dut.io_out_5_valid) << 5)
      | (unsigned(dut.io_out_6_valid) << 6) | (unsigned(dut.io_out_7_valid) << 7)
      | (unsigned(dut.io_out_8_valid) << 8) | (unsigned(dut.io_out_9_valid) << 9);
#else
  return unsigned(dut.io_out_0_valid) | (unsigned(dut.io_out_1_valid) << 1)
      | (unsigned(dut.io_out_2_valid) << 2) | (unsigned(dut.io_out_3_valid) << 3);
#endif
}

// Emit the canonical transaction trace. / 输出规范事务轨迹。
template <typename Dut>
static int run(Dut &dut) {
  constexpr std::uint64_t payloads[] = {0ULL, 1ULL, (1ULL << 50) - 1ULL, 0x2A123456789ABULL};
#ifdef N10
  constexpr unsigned limit = 1024;
#else
  constexpr unsigned limit = 16;
#endif
  for (const auto bits : payloads) {
    for (unsigned ready = 0; ready < limit; ++ready) {
      for (unsigned valid = 0; valid < 2; ++valid) {
        drive_payload(dut, bits);
        drive_ready(dut, ready);
        dut.io_in_valid = valid;
        dut.eval();
#ifdef N10
        std::printf("{\"bits\":%llu,\"ready\":%u,\"valid\":%u,\"in_ready\":%u,\"out_valid\":%u,\"chosen\":%u}\n",
                    static_cast<unsigned long long>(bits), ready, valid,
                    unsigned(dut.io_in_ready), read_valid(dut), unsigned(dut.io_chosen));
#else
        std::printf("{\"bits\":%llu,\"ready\":%u,\"valid\":%u,\"in_ready\":%u,\"out_valid\":%u}\n",
                    static_cast<unsigned long long>(bits), ready, valid,
                    unsigned(dut.io_in_ready), read_valid(dut));
#endif
      }
    }
  }
  return 0;
}

int main(int argc, char **argv) {
  VerilatedContext context;
  context.commandArgs(argc, argv);
#ifdef TARGET
  VDeMultiplexer dut{&context};
#else
#ifdef N10
  VDeMultiplexer_1 dut{&context};
#else
  VDeMultiplexer dut{&context};
#endif
#endif
  return run(dut);
}
