module RealWBCollideChecker(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:47:7
  input         io_in_14_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_14_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_14_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_14_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_14_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_13_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_13_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_13_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_13_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_13_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_12_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_12_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_12_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_12_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_12_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_11_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_11_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_11_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_11_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_11_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_10_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_10_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_10_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_10_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_10_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_10_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_9_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_9_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_9_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_9_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_9_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_8_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_8_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_8_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_8_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_8_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_7_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_7_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_7_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_7_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_7_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_6_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_6_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_6_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_6_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_5_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_5_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_5_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_5_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_5_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_5_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_4_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_4_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_4_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_4_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_4_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_3_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_3_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_3_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_3_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_3_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_2_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_2_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_2_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_2_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_2_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_1_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_1_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_1_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_1_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_in_0_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input         io_in_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_in_0_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [7:0]  io_in_0_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  input  [63:0] io_in_0_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_7_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_7_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_7_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_7_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_6_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_6_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_6_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_6_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_5_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_5_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_5_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_5_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_4_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_4_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_4_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_4_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_3_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_3_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_3_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_3_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_2_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_2_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_2_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_2_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_1_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_1_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_1_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output        io_out_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
                io_out_0_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [7:0]  io_out_0_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
  output [63:0] io_out_0_bits_data	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:48:14
);

  RealWBArbiter arbiters_0 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_ready      (io_in_0_ready),
    .io_in_0_valid      (io_in_0_valid),
    .io_in_0_bits_rfWen (io_in_0_bits_rfWen),
    .io_in_0_bits_pdest (io_in_0_bits_pdest),
    .io_in_0_bits_data  (io_in_0_bits_data),
    .io_in_1_ready      (io_in_1_ready),
    .io_in_1_valid      (io_in_1_valid),
    .io_in_1_bits_rfWen (io_in_1_bits_rfWen),
    .io_in_1_bits_pdest (io_in_1_bits_pdest),
    .io_in_1_bits_data  (io_in_1_bits_data),
    .io_in_2_ready      (io_in_8_ready),
    .io_in_2_valid      (io_in_8_valid),
    .io_in_2_bits_rfWen (io_in_8_bits_rfWen),
    .io_in_2_bits_pdest (io_in_8_bits_pdest),
    .io_in_2_bits_data  (io_in_8_bits_data),
    .io_out_valid       (io_out_0_valid),
    .io_out_bits_rfWen  (io_out_0_bits_rfWen),
    .io_out_bits_pdest  (io_out_0_bits_pdest),
    .io_out_bits_data   (io_out_0_bits_data)
  );
  RealWBArbiter_1 arbiters_1 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_ready      (io_in_2_ready),
    .io_in_0_valid      (io_in_2_valid),
    .io_in_0_bits_rfWen (io_in_2_bits_rfWen),
    .io_in_0_bits_pdest (io_in_2_bits_pdest),
    .io_in_0_bits_data  (io_in_2_bits_data),
    .io_in_1_ready      (io_in_3_ready),
    .io_in_1_valid      (io_in_3_valid),
    .io_in_1_bits_rfWen (io_in_3_bits_rfWen),
    .io_in_1_bits_pdest (io_in_3_bits_pdest),
    .io_in_1_bits_data  (io_in_3_bits_data),
    .io_in_2_ready      (io_in_11_ready),
    .io_in_2_valid      (io_in_11_valid),
    .io_in_2_bits_rfWen (io_in_11_bits_rfWen),
    .io_in_2_bits_pdest (io_in_11_bits_pdest),
    .io_in_2_bits_data  (io_in_11_bits_data),
    .io_in_3_ready      (io_in_9_ready),
    .io_in_3_valid      (io_in_9_valid),
    .io_in_3_bits_rfWen (io_in_9_bits_rfWen),
    .io_in_3_bits_pdest (io_in_9_bits_pdest),
    .io_in_3_bits_data  (io_in_9_bits_data),
    .io_out_valid       (io_out_1_valid),
    .io_out_bits_rfWen  (io_out_1_bits_rfWen),
    .io_out_bits_pdest  (io_out_1_bits_pdest),
    .io_out_bits_data   (io_out_1_bits_data)
  );
  RealWBArbiter_2 arbiters_2 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_ready      (io_in_4_ready),
    .io_in_0_valid      (io_in_4_valid),
    .io_in_0_bits_rfWen (io_in_4_bits_rfWen),
    .io_in_0_bits_fpWen (1'h0),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:47:7, :48:14, :54:18
    .io_in_0_bits_pdest (io_in_4_bits_pdest),
    .io_in_0_bits_data  (io_in_4_bits_data),
    .io_in_1_ready      (io_in_10_ready),
    .io_in_1_valid      (io_in_10_valid),
    .io_in_1_bits_rfWen (io_in_10_bits_rfWen),
    .io_in_1_bits_fpWen (io_in_10_bits_fpWen),
    .io_in_1_bits_pdest (io_in_10_bits_pdest),
    .io_in_1_bits_data  (io_in_10_bits_data),
    .io_out_valid       (io_out_2_valid),
    .io_out_bits_rfWen  (io_out_2_bits_rfWen),
    .io_out_bits_fpWen  (/* unused */),
    .io_out_bits_pdest  (io_out_2_bits_pdest),
    .io_out_bits_data   (io_out_2_bits_data)
  );
  RealWBArbiter_3 arbiters_3 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_valid      (io_in_6_valid),
    .io_in_0_bits_rfWen (io_in_6_bits_rfWen),
    .io_in_0_bits_fpWen (1'h0),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:47:7, :48:14, :54:18
    .io_in_0_bits_pdest (io_in_6_bits_pdest),
    .io_in_0_bits_data  (io_in_6_bits_data),
    .io_out_valid       (io_out_3_valid),
    .io_out_bits_rfWen  (io_out_3_bits_rfWen),
    .io_out_bits_fpWen  (/* unused */),
    .io_out_bits_pdest  (io_out_3_bits_pdest),
    .io_out_bits_data   (io_out_3_bits_data)
  );
  RealWBArbiter_2 arbiters_4 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_ready      (io_in_5_ready),
    .io_in_0_valid      (io_in_5_valid),
    .io_in_0_bits_rfWen (io_in_5_bits_rfWen),
    .io_in_0_bits_fpWen (io_in_5_bits_fpWen),
    .io_in_0_bits_pdest (io_in_5_bits_pdest),
    .io_in_0_bits_data  (io_in_5_bits_data),
    .io_in_1_ready      (io_in_7_ready),
    .io_in_1_valid      (io_in_7_valid),
    .io_in_1_bits_rfWen (io_in_7_bits_rfWen),
    .io_in_1_bits_fpWen (1'h0),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:47:7, :48:14, :54:18
    .io_in_1_bits_pdest (io_in_7_bits_pdest),
    .io_in_1_bits_data  (io_in_7_bits_data),
    .io_out_valid       (io_out_4_valid),
    .io_out_bits_rfWen  (io_out_4_bits_rfWen),
    .io_out_bits_fpWen  (/* unused */),
    .io_out_bits_pdest  (io_out_4_bits_pdest),
    .io_out_bits_data   (io_out_4_bits_data)
  );
  RealWBArbiter_3 arbiters_5 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_valid      (io_in_12_valid),
    .io_in_0_bits_rfWen (io_in_12_bits_rfWen),
    .io_in_0_bits_fpWen (io_in_12_bits_fpWen),
    .io_in_0_bits_pdest (io_in_12_bits_pdest),
    .io_in_0_bits_data  (io_in_12_bits_data),
    .io_out_valid       (io_out_5_valid),
    .io_out_bits_rfWen  (io_out_5_bits_rfWen),
    .io_out_bits_fpWen  (/* unused */),
    .io_out_bits_pdest  (io_out_5_bits_pdest),
    .io_out_bits_data   (io_out_5_bits_data)
  );
  RealWBArbiter_3 arbiters_6 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_valid      (io_in_13_valid),
    .io_in_0_bits_rfWen (io_in_13_bits_rfWen),
    .io_in_0_bits_fpWen (io_in_13_bits_fpWen),
    .io_in_0_bits_pdest (io_in_13_bits_pdest),
    .io_in_0_bits_data  (io_in_13_bits_data),
    .io_out_valid       (io_out_6_valid),
    .io_out_bits_rfWen  (io_out_6_bits_rfWen),
    .io_out_bits_fpWen  (/* unused */),
    .io_out_bits_pdest  (io_out_6_bits_pdest),
    .io_out_bits_data   (io_out_6_bits_data)
  );
  RealWBArbiter_3 arbiters_7 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala:54:18
    .io_in_0_valid      (io_in_14_valid),
    .io_in_0_bits_rfWen (io_in_14_bits_rfWen),
    .io_in_0_bits_fpWen (io_in_14_bits_fpWen),
    .io_in_0_bits_pdest (io_in_14_bits_pdest),
    .io_in_0_bits_data  (io_in_14_bits_data),
    .io_out_valid       (io_out_7_valid),
    .io_out_bits_rfWen  (io_out_7_bits_rfWen),
    .io_out_bits_fpWen  (/* unused */),
    .io_out_bits_pdest  (io_out_7_bits_pdest),
    .io_out_bits_data   (io_out_7_bits_data)
  );
endmodule
