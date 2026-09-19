module SubModule(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Alu.scala:37:7
  input  [63:0] io_src_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Alu.scala:38:14
                io_src_1,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Alu.scala:38:14
  output [64:0] io_sub	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Alu.scala:38:14
);

  assign io_sub = {1'h0, io_src_0} + {1'h0, ~io_src_1} + 65'h1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Alu.scala:37:7, :42:{24,28,48}
endmodule
module BranchModule(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:25:7
  input  [63:0] io_src_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:26:14
                io_src_1,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:26:14
  input  [8:0]  io_func,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:26:14
  input         io_pred_taken,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:26:14
  output        io_taken,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:26:14
                io_mispredict	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:26:14
);

  wire [64:0] _subModule_io_sub;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:34:25
  wire        taken =
    (io_func[3:1] == 3'h0 & (io_src_0 ^ io_src_1) == 64'h0 | io_func[3:1] == 3'h2
     & (io_src_0[63] ^ io_src_1[63] ^ ~(_subModule_io_sub[64])) | io_func[3:1] == 3'h4
     & ~(_subModule_io_sub[64])) ^ io_func[0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:34:25, :38:{17,21}, :39:{21,38,49}, :40:22, :43:53, :47:72, home/lishuo/xs-v2-local/src/main/scala/xiangshan/package.scala:461:41, :462:42, home/lishuo/xs-v2-local/utility/src/main/scala/utility/LookupTree.scala:24:34, src/main/scala/chisel3/util/Mux.scala:30:73
  SubModule subModule (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:34:25
    .io_src_0 (io_src_0),
    .io_src_1 (io_src_1),
    .io_sub   (_subModule_io_sub)
  );
  assign io_taken = taken;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:25:7, :47:72
  assign io_mispredict = io_pred_taken ^ taken;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Branch.scala:25:7, :47:72, :50:34
endmodule
