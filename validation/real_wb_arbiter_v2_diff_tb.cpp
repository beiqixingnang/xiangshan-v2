#include "verilated.h"
#include "VRealWBArbiter.h"

#include <cstdint>
#include <cstdio>

int main(int argc, char **argv) {
    VerilatedContext context;
    context.commandArgs(argc, argv);
    VRealWBArbiter dut{&context};
    unsigned index = 0;
    for (unsigned ready = 0; ready < 2; ++ready) {
        for (unsigned mask = 0; mask < 8; ++mask) {
#ifdef TARGET
            dut.io_out_ready = ready;
            dut.io_in_0_bits_vecWen = 0; dut.io_in_1_bits_vecWen = 0; dut.io_in_2_bits_vecWen = 0;
            dut.io_in_0_bits_v0Wen = 0; dut.io_in_1_bits_v0Wen = 0; dut.io_in_2_bits_v0Wen = 0;
            dut.io_in_0_bits_vlWen = 0; dut.io_in_1_bits_vlWen = 0; dut.io_in_2_bits_vlWen = 0;
#endif
            for (unsigned i = 0; i < 3; ++i) {
                const unsigned valid = (mask >> i) & 1U;
                const std::uint64_t data = 0x1000000000000000ULL + i * 0x1111111111111111ULL + mask;
                const unsigned pdest = (i * 37U + mask * 3U) & 0xffU;
                const unsigned rf = (i + mask) & 1U;
                const unsigned fp = ((i + mask) >> 1) & 1U;
                if (i == 0) { dut.io_in_0_valid = valid; dut.io_in_0_bits_data = data; dut.io_in_0_bits_pdest = pdest; dut.io_in_0_bits_rfWen = rf; }
                if (i == 1) { dut.io_in_1_valid = valid; dut.io_in_1_bits_data = data; dut.io_in_1_bits_pdest = pdest; dut.io_in_1_bits_rfWen = rf; }
                if (i == 2) { dut.io_in_2_valid = valid; dut.io_in_2_bits_data = data; dut.io_in_2_bits_pdest = pdest; dut.io_in_2_bits_rfWen = rf; }
#ifdef TARGET
                if (i == 0) dut.io_in_0_bits_fpWen = fp;
                if (i == 1) dut.io_in_1_bits_fpWen = fp;
                if (i == 2) dut.io_in_2_bits_fpWen = fp;
#endif
            }
            dut.eval();
            std::printf("{\"index\":%u,\"ready\":%u,\"mask\":%u,\"out_valid\":%u,\"data\":%llu,\"pdest\":%u,\"rfWen\":%u,\"in_ready\":[%u,%u,%u]",
                        index++, ready, mask, unsigned(dut.io_out_valid),
                        static_cast<unsigned long long>(dut.io_out_bits_data),
                        unsigned(dut.io_out_bits_pdest), unsigned(dut.io_out_bits_rfWen),
                        unsigned(dut.io_in_0_ready), unsigned(dut.io_in_1_ready), unsigned(dut.io_in_2_ready));
#ifdef TARGET
            std::printf(",\"chosen\":%u", unsigned(dut.io_chosen));
#endif
            std::printf("}\n");
        }
    }
    return 0;
}
