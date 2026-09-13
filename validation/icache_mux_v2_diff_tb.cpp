#include "verilated.h"
#include <cstdint>
#include <cstdio>

#ifdef TARGET
#include "VMuxBundle.h"
#else
#include "VMuxBundle.h"
#endif

// Pack the V2 acquire source, address, and set index in canonical order.
// 按规范顺序打包 V2 acquire source、地址和组索引。
static std::uint64_t payload(unsigned index, unsigned seed) {
  const std::uint64_t source = (index + 4U) & 0xFU;
  const std::uint64_t address = (0x123456789000ULL + index + (std::uint64_t(seed) << 20)) & ((1ULL << 48) - 1ULL);
  const std::uint64_t set = (0x80U + index + seed) & 0xFFU;
  return source | (address << 4) | (set << 52);
}

// Drive one input bundle in either scalarized target or reference shape.
// 驱动标量化目标或结构化参考中的一个输入 bundle。
template <typename Dut>
static void drive_input(Dut &dut, unsigned index, unsigned seed) {
  const std::uint64_t value = payload(index, seed);
#ifdef TARGET
  switch (index) {
    case 0: dut.io_in_0_bits = value; break; case 1: dut.io_in_1_bits = value; break;
    case 2: dut.io_in_2_bits = value; break; case 3: dut.io_in_3_bits = value; break;
    case 4: dut.io_in_4_bits = value; break; case 5: dut.io_in_5_bits = value; break;
    case 6: dut.io_in_6_bits = value; break; case 7: dut.io_in_7_bits = value; break;
    case 8: dut.io_in_8_bits = value; break; default: dut.io_in_9_bits = value; break;
  }
#else
  const auto address = (value >> 4) & ((1ULL << 48) - 1ULL);
  const auto set = (value >> 52) & 0xFFU;
  switch (index) {
    case 0: dut.io_in_0_bits_acquire_address = address; dut.io_in_0_bits_vSetIdx = set; break;
    case 1: dut.io_in_1_bits_acquire_address = address; dut.io_in_1_bits_vSetIdx = set; break;
    case 2: dut.io_in_2_bits_acquire_address = address; dut.io_in_2_bits_vSetIdx = set; break;
    case 3: dut.io_in_3_bits_acquire_address = address; dut.io_in_3_bits_vSetIdx = set; break;
    case 4: dut.io_in_4_bits_acquire_address = address; dut.io_in_4_bits_vSetIdx = set; break;
    case 5: dut.io_in_5_bits_acquire_address = address; dut.io_in_5_bits_vSetIdx = set; break;
    case 6: dut.io_in_6_bits_acquire_address = address; dut.io_in_6_bits_vSetIdx = set; break;
    case 7: dut.io_in_7_bits_acquire_address = address; dut.io_in_7_bits_vSetIdx = set; break;
    case 8: dut.io_in_8_bits_acquire_address = address; dut.io_in_8_bits_vSetIdx = set; break;
    default: dut.io_in_9_bits_acquire_address = address; dut.io_in_9_bits_vSetIdx = set; break;
  }
#endif
}

// Set all valid bits for one mask. / 按掩码设置全部 valid 位。
template <typename Dut>
static void drive_valid(Dut &dut, unsigned mask) {
  dut.io_in_0_valid = (mask >> 0) & 1U; dut.io_in_1_valid = (mask >> 1) & 1U;
  dut.io_in_2_valid = (mask >> 2) & 1U; dut.io_in_3_valid = (mask >> 3) & 1U;
  dut.io_in_4_valid = (mask >> 4) & 1U; dut.io_in_5_valid = (mask >> 5) & 1U;
  dut.io_in_6_valid = (mask >> 6) & 1U; dut.io_in_7_valid = (mask >> 7) & 1U;
  dut.io_in_8_valid = (mask >> 8) & 1U; dut.io_in_9_valid = (mask >> 9) & 1U;
}

// Read one input-ready mask. / 读取输入 ready 掩码。
template <typename Dut>
static unsigned read_ready(const Dut &dut) {
  return unsigned(dut.io_in_0_ready) | (unsigned(dut.io_in_1_ready) << 1)
      | (unsigned(dut.io_in_2_ready) << 2) | (unsigned(dut.io_in_3_ready) << 3)
      | (unsigned(dut.io_in_4_ready) << 4) | (unsigned(dut.io_in_5_ready) << 5)
      | (unsigned(dut.io_in_6_ready) << 6) | (unsigned(dut.io_in_7_ready) << 7)
      | (unsigned(dut.io_in_8_ready) << 8) | (unsigned(dut.io_in_9_ready) << 9);
}

// Read the selected output bundle in canonical packed form.
// 以规范打包格式读取所选输出 bundle。
template <typename Dut>
static std::uint64_t read_output(const Dut &dut) {
#ifdef TARGET
  return static_cast<std::uint64_t>(dut.io_out_bits);
#else
  return std::uint64_t(dut.io_out_bits_acquire_source)
      | (std::uint64_t(dut.io_out_bits_acquire_address) << 4)
      | (std::uint64_t(dut.io_out_bits_vSetIdx) << 52);
#endif
}

// Emit the exhaustive selector trace. / 输出穷举选择器轨迹。
template <typename Dut>
static int run(Dut &dut) {
  for (unsigned seed : {0U, 0x5AU}) {
    for (unsigned index = 0; index < 10; ++index) drive_input(dut, index, seed);
    for (unsigned valid_mask = 0; valid_mask < 1024; ++valid_mask) {
      drive_valid(dut, valid_mask);
      for (unsigned sel = 0; sel < 16; ++sel) {
        for (unsigned ready = 0; ready < 2; ++ready) {
          dut.io_sel = sel; dut.io_out_ready = ready; dut.eval();
          const unsigned selected = sel < 10 ? sel : 0;
          std::printf("{\"seed\":%u,\"valid_mask\":%u,\"sel\":%u,\"ready\":%u,\"in_ready\":%u,\"out_valid\":%u,\"out_bits\":%llu}\n",
                      seed, valid_mask, sel, ready, read_ready(dut), unsigned(dut.io_out_valid),
                      static_cast<unsigned long long>(read_output(dut)));
          (void)selected;
        }
      }
    }
  }
  return 0;
}

int main(int argc, char **argv) {
  VerilatedContext context; context.commandArgs(argc, argv); VMuxBundle dut{&context}; return run(dut);
}
