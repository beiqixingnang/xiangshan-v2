module DeMultiplexer(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  output        io_in_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_in_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input  [41:0] io_in_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input  [7:0]  io_in_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_0_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_0_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_0_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_1_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_1_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_1_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_2_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_2_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_2_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_2_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_3_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_3_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_3_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_3_bits_vSetIdx	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
);

  wire grant_2 = io_out_0_ready | io_out_1_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:42:97
  wire grant_3 = grant_2 | io_out_2_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:42:97
  assign io_in_ready = grant_3 | io_out_3_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :48:29
  assign io_out_0_valid = io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_0_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_0_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_1_valid = ~io_out_0_ready & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :45:{24,34}
  assign io_out_1_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_1_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_2_valid = ~grant_2 & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_2_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_2_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_3_valid = ~grant_3 & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_3_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_3_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
endmodule
