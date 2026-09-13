module RealWBArbiter_2(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7
  output        io_in_0_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input         io_in_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_in_0_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_in_0_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input  [7:0]  io_in_0_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input  [63:0] io_in_0_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  output        io_in_1_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input         io_in_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_in_1_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_in_1_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input  [7:0]  io_in_1_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input  [63:0] io_in_1_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  output        io_out_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_out_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_out_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  output [7:0]  io_out_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  output [63:0] io_out_bits_data	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
);

  assign io_in_0_ready = 1'h1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:49:84, :114:7
  assign io_in_1_ready = ~io_in_0_valid | ~io_in_1_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:49:84, :114:7, :128:{20,23}
  assign io_out_valid = io_in_0_valid | io_in_1_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7, :129:31
  assign io_out_bits_rfWen = io_in_0_valid ? io_in_0_bits_rfWen : io_in_1_bits_rfWen;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7, :118:15, :120:26, :122:19
  assign io_out_bits_fpWen = io_in_0_valid ? io_in_0_bits_fpWen : io_in_1_bits_fpWen;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7, :118:15, :120:26, :122:19
  assign io_out_bits_pdest = io_in_0_valid ? io_in_0_bits_pdest : io_in_1_bits_pdest;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7, :118:15, :120:26, :122:19
  assign io_out_bits_data = io_in_0_valid ? io_in_0_bits_data : io_in_1_bits_data;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7, :118:15, :120:26, :122:19
endmodule
