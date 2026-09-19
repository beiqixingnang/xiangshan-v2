module JumpDataModule(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:34:7
  input  [63:0] io_src,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
                io_pc,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
  input  [32:0] io_imm,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
  input  [4:0]  io_nextPcOffset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
  input  [8:0]  io_func,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
  output [63:0] io_result,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
                io_target,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
  output        io_isAuipc	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:35:14
);

  wire [63:0] _GEN = {{31{io_imm[32]}}, io_imm};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:52:56, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20, :97:46
  wire [63:0] target = io_func[0] ? io_src + _GEN : io_pc + _GEN;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:52:{19,56,69}, home/lishuo/xs-v2-local/src/main/scala/xiangshan/package.scala:268:36
  assign io_result = io_func[1] ? target : io_pc + {58'h0, io_nextPcOffset, 1'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:34:7, :51:17, :52:19, :57:19, :58:19, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20, :97:46
  assign io_target = {target[63:1], 1'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:34:7, home/lishuo/xs-v2-local/src/main/scala/xiangshan/package.scala:269:37
  assign io_isAuipc = io_func[1];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/Jump.scala:34:7, home/lishuo/xs-v2-local/src/main/scala/xiangshan/package.scala:269:37
endmodule
