
module ImmExtractor(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7
  input  [31:0] io_in_imm,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  input  [3:0]  io_in_immType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  output [63:0] io_out_imm	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
);

  assign io_out_imm =
    io_in_immType == 4'hB
      ? {{32{io_in_imm[31]}}, io_in_imm}
      : io_in_immType == 4'h4
          ? {{52{io_in_imm[11]}}, io_in_imm[11:0]}
          : io_in_immType == 4'h2 ? {{32{io_in_imm[19]}}, io_in_imm[19:0], 12'h0} : 64'h0;	// home/lishuo/xs-v2-local/fudian/src/main/scala/fudian/utils/Multiplier.scala:9:20, :10:{41,46}, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala:572:56, :599:53, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7, :44:46, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20
endmodule


module ImmExtractor_2(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7
  input  [31:0] io_in_imm,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  input  [3:0]  io_in_immType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  output [63:0] io_out_imm	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
);

  assign io_out_imm =
    io_in_immType == 4'h4
      ? {{52{io_in_imm[11]}}, io_in_imm[11:0]}
      : io_in_immType == 4'h3
          ? {{43{io_in_imm[19]}}, io_in_imm[19:0], 1'h0}
          : io_in_immType == 4'h2
              ? {{32{io_in_imm[19]}}, io_in_imm[19:0], 12'h0}
              : io_in_immType == 4'h1
                  ? {{51{io_in_imm[11]}}, io_in_imm[11:0], 1'h0}
                  : 64'h0;	// home/lishuo/xs-v2-local/fudian/src/main/scala/fudian/utils/Multiplier.scala:9:20, :10:{41,46}, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala:572:56, :592:61, :599:53, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7, :44:46, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20
endmodule


module ImmExtractor_12(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7
  input  [31:0]  io_in_imm,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  input  [3:0]   io_in_immType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  output [127:0] io_out_imm	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
);

  assign io_out_imm =
    {64'h0,
     (&io_in_immType)
       ? {58'h0, io_in_imm[5:0]}
       : io_in_immType == 4'hD
           ? {{49{io_in_imm[14]}}, io_in_imm[14:0]}
           : io_in_immType == 4'hC
               ? {{53{io_in_imm[10]}}, io_in_imm[10:0]}
               : io_in_immType == 4'hA
                   ? {59'h0, io_in_imm[4:0]}
                   : io_in_immType == 4'h9
                       ? {{59{io_in_imm[4]}}, io_in_imm[4:0]}
                       : io_in_immType == 4'h4
                           ? {{52{io_in_imm[11]}}, io_in_imm[11:0]}
                           : io_in_immType == 4'h3
                               ? {{43{io_in_imm[19]}}, io_in_imm[19:0], 1'h0}
                               : io_in_immType == 4'h2
                                   ? {{32{io_in_imm[19]}}, io_in_imm[19:0], 12'h0}
                                   : io_in_immType == 4'h1
                                       ? {{51{io_in_imm[11]}}, io_in_imm[11:0], 1'h0}
                                       : 64'h0};	// home/lishuo/xs-v2-local/fudian/src/main/scala/fudian/utils/Multiplier.scala:9:20, :10:{41,46}, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala:572:56, :592:61, :599:53, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7, :44:{14,46}, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20
endmodule


module ImmExtractor_37(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7
  input  [31:0]  io_in_imm,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  input  [3:0]   io_in_immType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  output [127:0] io_out_imm	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
);

  assign io_out_imm =
    {64'h0,
     io_in_immType == 4'hD
       ? {{49{io_in_imm[14]}}, io_in_imm[14:0]}
       : io_in_immType == 4'hC ? {{53{io_in_imm[10]}}, io_in_imm[10:0]} : 64'h0};	// home/lishuo/xs-v2-local/fudian/src/main/scala/fudian/utils/Multiplier.scala:10:41, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala:572:56, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7, :44:{14,46}, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20
endmodule


module ImmExtractor_57(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7
  input  [31:0] io_in_imm,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  input  [3:0]  io_in_immType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
  output [63:0] io_out_imm	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:23:14
);

  assign io_out_imm =
    io_in_immType == 4'hE ? {{52{io_in_imm[11]}}, io_in_imm[11:0]} : 64'h0;	// home/lishuo/xs-v2-local/fudian/src/main/scala/fudian/utils/Multiplier.scala:10:41, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala:572:56, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/ImmExtractor.scala:22:7, :44:46, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:96:20
endmodule
