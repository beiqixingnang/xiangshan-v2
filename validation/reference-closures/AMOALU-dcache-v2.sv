module AMOALU(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:25:7
  input  [7:0]  io_mask,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:30:14
  input  [4:0]  io_cmd,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:30:14
  input  [63:0] io_lhs,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:30:14
                io_rhs,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:30:14
  output [63:0] io_out	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:30:14
);

  wire        _logic_xor_T_1 = io_cmd == 5'hA;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:42:26
  wire        logic_and = _logic_xor_T_1 | io_cmd == 5'hB;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:42:{26,38,48}
  wire        logic_xor = io_cmd == 5'h9 | _logic_xor_T_1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:42:26, :43:{26,39}
  wire [63:0] adder_out_mask = {32'hFFFFFFFF, io_mask[3], 31'h7FFFFFFF};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:47:{16,69,96}
  wire [63:0] wmask =
    {{8{io_mask[7]}},
     {8{io_mask[6]}},
     {8{io_mask[5]}},
     {8{io_mask[4]}},
     {8{io_mask[3]}},
     {8{io_mask[2]}},
     {8{io_mask[1]}},
     {8{io_mask[0]}}};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:47:69, :66:49, :78:30
  assign io_out =
    wmask
    & (io_cmd == 5'h8
         ? (io_lhs & adder_out_mask) + (io_rhs & adder_out_mask)
         : logic_and | logic_xor
             ? (logic_and ? io_lhs & io_rhs : 64'h0)
               | (logic_xor ? io_lhs ^ io_rhs : 64'h0)
             : ((io_mask[4]
                   ? (io_lhs[63] == io_rhs[63]
                        ? io_lhs[63:32] < io_rhs[63:32] | io_lhs[63:32] == io_rhs[63:32]
                          & io_lhs[31:0] < io_rhs[31:0]
                        : io_cmd[1] ? io_rhs[63] : io_lhs[63])
                   : io_lhs[31] == io_rhs[31]
                       ? io_lhs[31:0] < io_rhs[31:0]
                       : io_cmd[1] ? io_rhs[31] : io_lhs[31])
                  ? io_cmd == 5'hC | io_cmd == 5'hE
                  : io_cmd == 5'hD | io_cmd == 5'hF)
                 ? io_lhs
                 : io_rhs) | ~wmask & io_lhs;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala:25:7, :39:{20,33,43}, :40:{20,33,43}, :41:20, :42:38, :43:39, :47:96, :48:{13,21,31}, :54:{26,35,38}, :55:{13,24,27,38,53,69}, :61:17, :63:{10,12,18,23,58}, :66:49, :69:{19,23}, :71:{8,27,42}, :72:{8,27}, :74:8, :75:{8,19}, :78:30, :79:{19,25,27,34}, src/main/scala/chisel3/util/Mux.scala:50:70
endmodule
