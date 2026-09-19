module CSA3_2(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:40:7
  input  io_in_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:23:14
         io_in_1,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:23:14
         io_in_2,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:23:14
  output io_out_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:23:14
         io_out_1	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:23:14
);

  wire a_xor_b = io_in_0 ^ io_in_1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:44:21
  assign io_out_0 = a_xor_b ^ io_in_2;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:40:7, :44:21, :46:23
  assign io_out_1 = io_in_0 & io_in_1 | a_xor_b & io_in_2;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/util/CSA.scala:40:7, :44:21, :45:21, :47:{24,35}
endmodule
