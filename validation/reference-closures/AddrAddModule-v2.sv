module AddrAddModule(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:12:7
  input  [50:0] io_pcExtend,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:13:14
  input         io_taken,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:13:14
  input  [31:0] io_imm,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:13:14
  output [63:0] io_target,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:13:14
  input  [4:0]  io_nextPcOffset	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:13:14
);

  wire [50:0] _io_target_T_8 =
    io_taken
      ? io_pcExtend + {{36{io_imm[14]}}, io_imm[14:0]}
      : io_pcExtend + {45'h0, io_nextPcOffset, 1'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:23:27, :24:{17,33}, :25:17, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20, :97:46
  assign io_target = {{13{_io_target_T_8[50]}}, _io_target_T_8};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/wrapper/BranchUnit.scala:12:7, :23:27, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20, :97:{41,46}
endmodule
