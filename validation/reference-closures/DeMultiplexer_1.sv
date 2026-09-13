module DeMultiplexer_1(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
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
  output [7:0]  io_out_3_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_4_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_4_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_4_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_4_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_5_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_5_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_5_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_5_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_6_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_6_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_6_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_6_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_7_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_7_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_7_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_7_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_8_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_8_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_8_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_8_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  input         io_out_9_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output        io_out_9_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [41:0] io_out_9_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [7:0]  io_out_9_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
  output [3:0]  io_chosen	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:40:34
);

  wire grant_2 = io_out_0_ready | io_out_1_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:42:97
  wire grant_9 =
    grant_2 | io_out_2_ready | io_out_3_ready | io_out_4_ready | io_out_5_ready
    | io_out_6_ready | io_out_7_ready | io_out_8_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:42:97
  assign io_in_ready = grant_9 | io_out_9_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :48:29
  assign io_out_0_valid = io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_0_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_0_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_1_valid = ~io_out_0_ready & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :45:{24,34}
  assign io_out_1_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_1_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_2_valid = ~grant_2 & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_2_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_2_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_3_valid = ~(grant_2 | io_out_2_ready) & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_3_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_3_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_4_valid = ~(grant_2 | io_out_2_ready | io_out_3_ready) & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_4_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_4_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_5_valid =
    ~(grant_2 | io_out_2_ready | io_out_3_ready | io_out_4_ready) & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_5_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_5_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_6_valid =
    ~(grant_2 | io_out_2_ready | io_out_3_ready | io_out_4_ready | io_out_5_ready)
    & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_6_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_6_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_7_valid =
    ~(grant_2 | io_out_2_ready | io_out_3_ready | io_out_4_ready | io_out_5_ready
      | io_out_6_ready) & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_7_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_7_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_8_valid =
    ~(grant_2 | io_out_2_ready | io_out_3_ready | io_out_4_ready | io_out_5_ready
      | io_out_6_ready | io_out_7_ready) & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_8_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_8_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_9_valid = ~grant_9 & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, :42:97, :45:{24,34}
  assign io_out_9_bits_blkPaddr = io_in_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_out_9_bits_vSetIdx = io_in_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7
  assign io_chosen =
    io_out_0_ready
      ? 4'h0
      : io_out_1_ready
          ? 4'h1
          : io_out_2_ready
              ? 4'h2
              : io_out_3_ready
                  ? 4'h3
                  : io_out_4_ready
                      ? 4'h4
                      : io_out_5_ready
                          ? 4'h5
                          : io_out_6_ready
                              ? 4'h6
                              : io_out_7_ready ? 4'h7 : {3'h4, ~io_out_8_ready};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:38:7, src/main/scala/chisel3/util/Mux.scala:50:70
endmodule
