module EnqPolicy(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7
  input  [21:0] io_canEnq,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output        io_enqSelOHVec_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [21:0] io_enqSelOHVec_0_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output        io_enqSelOHVec_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [21:0] io_enqSelOHVec_1_bits	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
);

  assign io_enqSelOHVec_0_valid = |io_canEnq;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:29
  assign io_enqSelOHVec_0_bits =
    {io_canEnq[21]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14],
          io_canEnq[15],
          io_canEnq[16],
          io_canEnq[17],
          io_canEnq[18],
          io_canEnq[19],
          io_canEnq[20]} == 21'h0,
     io_canEnq[20]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14],
          io_canEnq[15],
          io_canEnq[16],
          io_canEnq[17],
          io_canEnq[18],
          io_canEnq[19]} == 20'h0,
     io_canEnq[19]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14],
          io_canEnq[15],
          io_canEnq[16],
          io_canEnq[17],
          io_canEnq[18]} == 19'h0,
     io_canEnq[18]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14],
          io_canEnq[15],
          io_canEnq[16],
          io_canEnq[17]} == 18'h0,
     io_canEnq[17]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14],
          io_canEnq[15],
          io_canEnq[16]} == 17'h0,
     io_canEnq[16]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14],
          io_canEnq[15]} == 16'h0,
     io_canEnq[15]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14]} == 15'h0,
     io_canEnq[14]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13]} == 14'h0,
     io_canEnq[13]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12]} == 13'h0,
     io_canEnq[12]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11]} == 12'h0,
     io_canEnq[11]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10]} == 11'h0,
     io_canEnq[10]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9]} == 10'h0,
     io_canEnq[9]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8]} == 9'h0,
     io_canEnq[8]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7]} == 8'h0,
     io_canEnq[7]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6]} == 7'h0,
     io_canEnq[6]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5]} == 6'h0,
     io_canEnq[5]
       & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3], io_canEnq[4]} == 5'h0,
     io_canEnq[4] & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3]} == 4'h0,
     io_canEnq[3] & {io_canEnq[0], io_canEnq[1], io_canEnq[2]} == 3'h0,
     io_canEnq[2] & {io_canEnq[0], io_canEnq[1]} == 2'h0,
     io_canEnq[1] & ~(io_canEnq[0]),
     io_canEnq[0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
  assign io_enqSelOHVec_1_valid =
    io_canEnq[0] & (|(io_canEnq[21:1])) | io_canEnq[1] & (|(io_canEnq[21:2]))
    | io_canEnq[2] & (|(io_canEnq[21:3])) | io_canEnq[3] & (|(io_canEnq[21:4]))
    | io_canEnq[4] & (|(io_canEnq[21:5])) | io_canEnq[5] & (|(io_canEnq[21:6]))
    | io_canEnq[6] & (|(io_canEnq[21:7])) | io_canEnq[7] & (|(io_canEnq[21:8]))
    | io_canEnq[8] & (|(io_canEnq[21:9])) | io_canEnq[9] & (|(io_canEnq[21:10]))
    | io_canEnq[10] & (|(io_canEnq[21:11])) | io_canEnq[11] & (|(io_canEnq[21:12]))
    | io_canEnq[12] & (|(io_canEnq[21:13])) | io_canEnq[13] & (|(io_canEnq[21:14]))
    | io_canEnq[14] & (|(io_canEnq[21:15])) | io_canEnq[15] & (|(io_canEnq[21:16]))
    | io_canEnq[16] & (|(io_canEnq[21:17])) | io_canEnq[17] & (|(io_canEnq[21:18]))
    | io_canEnq[18] & (|(io_canEnq[21:19])) | io_canEnq[19] & (|(io_canEnq[21:20]))
    | io_canEnq[20] & io_canEnq[21];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:{22,29}, :258:{16,49}
  assign io_enqSelOHVec_1_bits =
    {io_canEnq[21],
     io_canEnq[20] & ~(io_canEnq[21]),
     io_canEnq[19] & io_canEnq[21:20] == 2'h0,
     io_canEnq[18] & io_canEnq[21:19] == 3'h0,
     io_canEnq[17] & io_canEnq[21:18] == 4'h0,
     io_canEnq[16] & io_canEnq[21:17] == 5'h0,
     io_canEnq[15] & io_canEnq[21:16] == 6'h0,
     io_canEnq[14] & io_canEnq[21:15] == 7'h0,
     io_canEnq[13] & io_canEnq[21:14] == 8'h0,
     io_canEnq[12] & io_canEnq[21:13] == 9'h0,
     io_canEnq[11] & io_canEnq[21:12] == 10'h0,
     io_canEnq[10] & io_canEnq[21:11] == 11'h0,
     io_canEnq[9] & io_canEnq[21:10] == 12'h0,
     io_canEnq[8] & io_canEnq[21:9] == 13'h0,
     io_canEnq[7] & io_canEnq[21:8] == 14'h0,
     io_canEnq[6] & io_canEnq[21:7] == 15'h0,
     io_canEnq[5] & io_canEnq[21:6] == 16'h0,
     io_canEnq[4] & io_canEnq[21:5] == 17'h0,
     io_canEnq[3] & io_canEnq[21:4] == 18'h0,
     io_canEnq[2] & io_canEnq[21:3] == 19'h0,
     io_canEnq[1] & io_canEnq[21:2] == 20'h0,
     io_canEnq[0] & io_canEnq[21:1] == 21'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
endmodule
module EnqPolicy_8(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7
  input  [15:0] io_canEnq,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output        io_enqSelOHVec_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [15:0] io_enqSelOHVec_0_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output        io_enqSelOHVec_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [15:0] io_enqSelOHVec_1_bits	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
);

  assign io_enqSelOHVec_0_valid = |io_canEnq;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:29
  assign io_enqSelOHVec_0_bits =
    {io_canEnq[15]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13],
          io_canEnq[14]} == 15'h0,
     io_canEnq[14]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12],
          io_canEnq[13]} == 14'h0,
     io_canEnq[13]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12]} == 13'h0,
     io_canEnq[12]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11]} == 12'h0,
     io_canEnq[11]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10]} == 11'h0,
     io_canEnq[10]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9]} == 10'h0,
     io_canEnq[9]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8]} == 9'h0,
     io_canEnq[8]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7]} == 8'h0,
     io_canEnq[7]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6]} == 7'h0,
     io_canEnq[6]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5]} == 6'h0,
     io_canEnq[5]
       & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3], io_canEnq[4]} == 5'h0,
     io_canEnq[4] & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3]} == 4'h0,
     io_canEnq[3] & {io_canEnq[0], io_canEnq[1], io_canEnq[2]} == 3'h0,
     io_canEnq[2] & {io_canEnq[0], io_canEnq[1]} == 2'h0,
     io_canEnq[1] & ~(io_canEnq[0]),
     io_canEnq[0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
  assign io_enqSelOHVec_1_valid =
    io_canEnq[0] & (|(io_canEnq[15:1])) | io_canEnq[1] & (|(io_canEnq[15:2]))
    | io_canEnq[2] & (|(io_canEnq[15:3])) | io_canEnq[3] & (|(io_canEnq[15:4]))
    | io_canEnq[4] & (|(io_canEnq[15:5])) | io_canEnq[5] & (|(io_canEnq[15:6]))
    | io_canEnq[6] & (|(io_canEnq[15:7])) | io_canEnq[7] & (|(io_canEnq[15:8]))
    | io_canEnq[8] & (|(io_canEnq[15:9])) | io_canEnq[9] & (|(io_canEnq[15:10]))
    | io_canEnq[10] & (|(io_canEnq[15:11])) | io_canEnq[11] & (|(io_canEnq[15:12]))
    | io_canEnq[12] & (|(io_canEnq[15:13])) | io_canEnq[13] & (|(io_canEnq[15:14]))
    | io_canEnq[14] & io_canEnq[15];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:{22,29}, :258:{16,49}
  assign io_enqSelOHVec_1_bits =
    {io_canEnq[15],
     io_canEnq[14] & ~(io_canEnq[15]),
     io_canEnq[13] & io_canEnq[15:14] == 2'h0,
     io_canEnq[12] & io_canEnq[15:13] == 3'h0,
     io_canEnq[11] & io_canEnq[15:12] == 4'h0,
     io_canEnq[10] & io_canEnq[15:11] == 5'h0,
     io_canEnq[9] & io_canEnq[15:10] == 6'h0,
     io_canEnq[8] & io_canEnq[15:9] == 7'h0,
     io_canEnq[7] & io_canEnq[15:8] == 8'h0,
     io_canEnq[6] & io_canEnq[15:7] == 9'h0,
     io_canEnq[5] & io_canEnq[15:6] == 10'h0,
     io_canEnq[4] & io_canEnq[15:5] == 11'h0,
     io_canEnq[3] & io_canEnq[15:4] == 12'h0,
     io_canEnq[2] & io_canEnq[15:3] == 13'h0,
     io_canEnq[1] & io_canEnq[15:2] == 14'h0,
     io_canEnq[0] & io_canEnq[15:1] == 15'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
endmodule
module EnqPolicy_14(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7
  input  [13:0] io_canEnq,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output        io_enqSelOHVec_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [13:0] io_enqSelOHVec_0_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output        io_enqSelOHVec_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [13:0] io_enqSelOHVec_1_bits	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
);

  assign io_enqSelOHVec_0_valid = |io_canEnq;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:29
  assign io_enqSelOHVec_0_bits =
    {io_canEnq[13]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11],
          io_canEnq[12]} == 13'h0,
     io_canEnq[12]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10],
          io_canEnq[11]} == 12'h0,
     io_canEnq[11]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9],
          io_canEnq[10]} == 11'h0,
     io_canEnq[10]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8],
          io_canEnq[9]} == 10'h0,
     io_canEnq[9]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7],
          io_canEnq[8]} == 9'h0,
     io_canEnq[8]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6],
          io_canEnq[7]} == 8'h0,
     io_canEnq[7]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6]} == 7'h0,
     io_canEnq[6]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5]} == 6'h0,
     io_canEnq[5]
       & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3], io_canEnq[4]} == 5'h0,
     io_canEnq[4] & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3]} == 4'h0,
     io_canEnq[3] & {io_canEnq[0], io_canEnq[1], io_canEnq[2]} == 3'h0,
     io_canEnq[2] & {io_canEnq[0], io_canEnq[1]} == 2'h0,
     io_canEnq[1] & ~(io_canEnq[0]),
     io_canEnq[0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
  assign io_enqSelOHVec_1_valid =
    io_canEnq[0] & (|(io_canEnq[13:1])) | io_canEnq[1] & (|(io_canEnq[13:2]))
    | io_canEnq[2] & (|(io_canEnq[13:3])) | io_canEnq[3] & (|(io_canEnq[13:4]))
    | io_canEnq[4] & (|(io_canEnq[13:5])) | io_canEnq[5] & (|(io_canEnq[13:6]))
    | io_canEnq[6] & (|(io_canEnq[13:7])) | io_canEnq[7] & (|(io_canEnq[13:8]))
    | io_canEnq[8] & (|(io_canEnq[13:9])) | io_canEnq[9] & (|(io_canEnq[13:10]))
    | io_canEnq[10] & (|(io_canEnq[13:11])) | io_canEnq[11] & (|(io_canEnq[13:12]))
    | io_canEnq[12] & io_canEnq[13];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:{22,29}, :258:{16,49}
  assign io_enqSelOHVec_1_bits =
    {io_canEnq[13],
     io_canEnq[12] & ~(io_canEnq[13]),
     io_canEnq[11] & io_canEnq[13:12] == 2'h0,
     io_canEnq[10] & io_canEnq[13:11] == 3'h0,
     io_canEnq[9] & io_canEnq[13:10] == 4'h0,
     io_canEnq[8] & io_canEnq[13:9] == 5'h0,
     io_canEnq[7] & io_canEnq[13:8] == 6'h0,
     io_canEnq[6] & io_canEnq[13:7] == 7'h0,
     io_canEnq[5] & io_canEnq[13:6] == 8'h0,
     io_canEnq[4] & io_canEnq[13:5] == 9'h0,
     io_canEnq[3] & io_canEnq[13:4] == 10'h0,
     io_canEnq[2] & io_canEnq[13:3] == 11'h0,
     io_canEnq[1] & io_canEnq[13:2] == 12'h0,
     io_canEnq[0] & io_canEnq[13:1] == 13'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
endmodule
module EnqPolicy_18(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7
  input  [7:0] io_canEnq,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output       io_enqSelOHVec_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [7:0] io_enqSelOHVec_0_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output       io_enqSelOHVec_1_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
  output [7:0] io_enqSelOHVec_1_bits	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:15:14
);

  assign io_enqSelOHVec_0_valid = |io_canEnq;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:29
  assign io_enqSelOHVec_0_bits =
    {io_canEnq[7]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5],
          io_canEnq[6]} == 7'h0,
     io_canEnq[6]
       & {io_canEnq[0],
          io_canEnq[1],
          io_canEnq[2],
          io_canEnq[3],
          io_canEnq[4],
          io_canEnq[5]} == 6'h0,
     io_canEnq[5]
       & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3], io_canEnq[4]} == 5'h0,
     io_canEnq[4] & {io_canEnq[0], io_canEnq[1], io_canEnq[2], io_canEnq[3]} == 4'h0,
     io_canEnq[3] & {io_canEnq[0], io_canEnq[1], io_canEnq[2]} == 3'h0,
     io_canEnq[2] & {io_canEnq[0], io_canEnq[1]} == 2'h0,
     io_canEnq[1] & ~(io_canEnq[0]),
     io_canEnq[0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
  assign io_enqSelOHVec_1_valid =
    io_canEnq[0] & (|(io_canEnq[7:1])) | io_canEnq[1] & (|(io_canEnq[7:2])) | io_canEnq[2]
    & (|(io_canEnq[7:3])) | io_canEnq[3] & (|(io_canEnq[7:4])) | io_canEnq[4]
    & (|(io_canEnq[7:5])) | io_canEnq[5] & (|(io_canEnq[7:6])) | io_canEnq[6]
    & io_canEnq[7];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:254:{22,29}, :258:{16,49}
  assign io_enqSelOHVec_1_bits =
    {io_canEnq[7],
     io_canEnq[6] & ~(io_canEnq[7]),
     io_canEnq[5] & io_canEnq[7:6] == 2'h0,
     io_canEnq[4] & io_canEnq[7:5] == 3'h0,
     io_canEnq[3] & io_canEnq[7:4] == 4'h0,
     io_canEnq[2] & io_canEnq[7:3] == 5'h0,
     io_canEnq[1] & io_canEnq[7:2] == 6'h0,
     io_canEnq[0] & io_canEnq[7:1] == 7'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala:14:7, :17:29, :23:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/BitUtils.scala:276:{50,54,69}, :293:62
endmodule
