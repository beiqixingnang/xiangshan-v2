module MuxBundle(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7
  input  [3:0]  io_sel,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_0_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_0_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_0_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_1_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_1_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_1_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_2_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_2_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_2_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_2_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_3_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_3_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_3_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_3_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_4_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_4_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_4_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_4_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_5_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_5_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_5_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_5_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_6_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_6_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_6_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_6_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_7_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_7_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_7_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_7_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_8_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_8_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_8_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_8_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_in_9_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_in_9_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [47:0] io_in_9_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input  [7:0]  io_in_9_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  input         io_out_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output        io_out_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output [3:0]  io_out_bits_acquire_source,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output [47:0] io_out_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
  output [7:0]  io_out_bits_vSetIdx	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30
);

  wire _io_in_1_ready_T = io_sel == 4'h1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:65:17
  wire _io_in_2_ready_T = io_sel == 4'h2;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:65:17
  wire _io_in_3_ready_T = io_sel == 4'h3;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:65:17
  wire _io_in_4_ready_T = io_sel == 4'h4;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :60:30, :65:17
  wire _io_in_5_ready_T = io_sel == 4'h5;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30, :65:17
  wire _io_in_6_ready_T = io_sel == 4'h6;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30, :65:17
  wire _io_in_7_ready_T = io_sel == 4'h7;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30, :65:17
  wire _io_in_8_ready_T = io_sel == 4'h8;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30, :65:17
  wire _io_in_9_ready_T = io_sel == 4'h9;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:60:30, :65:17
  assign io_in_0_ready = io_sel == 4'h0 & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_1_ready = _io_in_1_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_2_ready = _io_in_2_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_3_ready = _io_in_3_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_4_ready = _io_in_4_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_5_ready = _io_in_5_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_6_ready = _io_in_6_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_7_ready = _io_in_7_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_8_ready = _io_in_8_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_in_9_ready = _io_in_9_ready_T & io_out_ready;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:17, :68:40
  assign io_out_valid =
    _io_in_9_ready_T
      ? io_in_9_valid
      : _io_in_8_ready_T
          ? io_in_8_valid
          : _io_in_7_ready_T
              ? io_in_7_valid
              : _io_in_6_ready_T
                  ? io_in_6_valid
                  : _io_in_5_ready_T
                      ? io_in_5_valid
                      : _io_in_4_ready_T
                          ? io_in_4_valid
                          : _io_in_3_ready_T
                              ? io_in_3_valid
                              : _io_in_2_ready_T
                                  ? io_in_2_valid
                                  : _io_in_1_ready_T ? io_in_1_valid : io_in_0_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:{17,26}, :66:14
  assign io_out_bits_acquire_source =
    _io_in_9_ready_T
      ? 4'hD
      : _io_in_8_ready_T
          ? 4'hC
          : _io_in_7_ready_T
              ? 4'hB
              : _io_in_6_ready_T
                  ? 4'hA
                  : _io_in_5_ready_T
                      ? 4'h9
                      : _io_in_4_ready_T
                          ? 4'h8
                          : _io_in_3_ready_T
                              ? 4'h7
                              : _io_in_2_ready_T ? 4'h6 : {3'h2, _io_in_1_ready_T};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :60:30, :65:{17,26}, :66:14
  assign io_out_bits_acquire_address =
    _io_in_9_ready_T
      ? io_in_9_bits_acquire_address
      : _io_in_8_ready_T
          ? io_in_8_bits_acquire_address
          : _io_in_7_ready_T
              ? io_in_7_bits_acquire_address
              : _io_in_6_ready_T
                  ? io_in_6_bits_acquire_address
                  : _io_in_5_ready_T
                      ? io_in_5_bits_acquire_address
                      : _io_in_4_ready_T
                          ? io_in_4_bits_acquire_address
                          : _io_in_3_ready_T
                              ? io_in_3_bits_acquire_address
                              : _io_in_2_ready_T
                                  ? io_in_2_bits_acquire_address
                                  : _io_in_1_ready_T
                                      ? io_in_1_bits_acquire_address
                                      : io_in_0_bits_acquire_address;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:{17,26}, :66:14
  assign io_out_bits_vSetIdx =
    _io_in_9_ready_T
      ? io_in_9_bits_vSetIdx
      : _io_in_8_ready_T
          ? io_in_8_bits_vSetIdx
          : _io_in_7_ready_T
              ? io_in_7_bits_vSetIdx
              : _io_in_6_ready_T
                  ? io_in_6_bits_vSetIdx
                  : _io_in_5_ready_T
                      ? io_in_5_bits_vSetIdx
                      : _io_in_4_ready_T
                          ? io_in_4_bits_vSetIdx
                          : _io_in_3_ready_T
                              ? io_in_3_bits_vSetIdx
                              : _io_in_2_ready_T
                                  ? io_in_2_bits_vSetIdx
                                  : _io_in_1_ready_T
                                      ? io_in_1_bits_vSetIdx
                                      : io_in_0_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:58:7, :65:{17,26}, :66:14
endmodule
