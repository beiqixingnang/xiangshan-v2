module RealWBArbiter_3(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7
  input         io_in_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_in_0_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_in_0_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input  [7:0]  io_in_0_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  input  [63:0] io_in_0_bits_data,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  output        io_out_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_out_bits_rfWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
                io_out_bits_fpWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  output [7:0]  io_out_bits_pdest,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
  output [63:0] io_out_bits_data	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:115:14
);

  assign io_out_valid = io_in_0_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7
  assign io_out_bits_rfWen = io_in_0_bits_rfWen;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7
  assign io_out_bits_fpWen = io_in_0_bits_fpWen;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7
  assign io_out_bits_pdest = io_in_0_bits_pdest;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7
  assign io_out_bits_data = io_in_0_bits_data;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala:114:7
endmodule
