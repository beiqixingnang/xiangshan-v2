#include "verilated.h"
#include "VNewPipelineConnectPipe.h"
#include <cstdio>

int main(int argc, char **argv) {
  VerilatedContext context; context.commandArgs(argc, argv);
  VNewPipelineConnectPipe dut{&context};
  dut.reset = 1; dut.clock = 0; dut.eval(); dut.clock = 1; dut.eval(); dut.clock = 0; dut.reset = 0;
  const unsigned v[][5] = {{1,0x11,0,0,0},{1,0x22,0,0,0},{0,0,1,0,0},{1,0x33,1,0,0},{1,0x44,0,1,0},{1,0x55,1,0,0},{0,0,1,0,0},{1,0x66,1,0,0},{1,0x77,1,0,1},{1,0x88,1,0,0},{0,0,1,1,0},{1,0x99,1,0,0}};
  for (unsigned i=0;i<sizeof(v)/sizeof(v[0]);++i) {
    dut.io_in_valid=v[i][0]; dut.io_in_bits=v[i][1]; dut.io_out_ready=v[i][2]; dut.io_rightOutFire=v[i][3]; dut.io_isFlush=v[i][4]; dut.io_isOlder=0; dut.clock=0; dut.eval();
    std::printf("{\"index\":%u,\"in_valid\":%u,\"bits\":%u,\"out_ready\":%u,\"right\":%u,\"flush\":%u,\"in_ready\":%u,\"out_valid\":%u,\"out_bits\":%u}\n",i,v[i][0],v[i][1],v[i][2],v[i][3],v[i][4],unsigned(dut.io_in_ready),unsigned(dut.io_out_valid),unsigned(dut.io_out_bits));
    dut.clock=1; dut.eval(); dut.clock=0; dut.eval();
  }
  return 0;
}
