module FliHTable(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:20:7
  input  [4:0]  src,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:8:15
  output [15:0] out	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:9:15
);

  wire [4:0] out_invInputs = ~src;	// src/main/scala/chisel3/util/pla.scala:78:21
  wire [3:0] _out_andMatrixOutputs_T =
    {out_invInputs[0], out_invInputs[1], out_invInputs[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :91:29, :98:53
  wire [4:0] _out_andMatrixOutputs_T_1 =
    {out_invInputs[0],
     out_invInputs[1],
     out_invInputs[2],
     out_invInputs[3],
     out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :91:29, :98:53
  wire [4:0] _out_andMatrixOutputs_T_6 =
    {out_invInputs[0], src[1], src[2], out_invInputs[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_8 = {out_invInputs[2], src[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [1:0] _out_andMatrixOutputs_T_12 = {src[2], src[3]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  wire [2:0] _out_andMatrixOutputs_T_14 = {out_invInputs[2], out_invInputs[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [1:0] _out_andMatrixOutputs_T_20 = {src[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  assign out =
    {&_out_andMatrixOutputs_T_1,
     |{&{src[2], src[4]}, &_out_andMatrixOutputs_T_20},
     |{&_out_andMatrixOutputs_T_1,
       &{src[0], src[2], out_invInputs[4]},
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_12,
       &_out_andMatrixOutputs_T_14},
     |{&_out_andMatrixOutputs_T,
       &{src[0], src[1], src[2], out_invInputs[4]},
       &_out_andMatrixOutputs_T_8,
       &{src[1], src[3]},
       &_out_andMatrixOutputs_T_12,
       &_out_andMatrixOutputs_T_14},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_12,
       &_out_andMatrixOutputs_T_14,
       &_out_andMatrixOutputs_T_20},
     |{&_out_andMatrixOutputs_T,
       &{src[0], out_invInputs[1], out_invInputs[2]},
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_14,
       &{src[0], src[1], src[4]},
       &{src[0], src[3], src[4]},
       &{src[1], src[2], src[3], src[4]}},
     |{&{src[0], src[1], out_invInputs[2], out_invInputs[3]},
       &{src[1], src[3], out_invInputs[4]},
       &{src[0], src[1], src[2], src[3]},
       &{out_invInputs[0], src[1], out_invInputs[3], src[4]}},
     |{&{out_invInputs[0], src[1], out_invInputs[2], out_invInputs[3], out_invInputs[4]},
       &{src[0], src[3], out_invInputs[4]},
       &{src[0], out_invInputs[1], out_invInputs[3], src[4]},
       &{src[0], out_invInputs[2], out_invInputs[3], src[4]}},
     8'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:20:7, src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:{53,70}, :102:36, :114:{19,36}
endmodule
module FliSTable(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:57:7
  input  [4:0]  src,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:8:15
  output [15:0] out	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:9:15
);

  wire [4:0] out_invInputs = ~src;	// src/main/scala/chisel3/util/pla.scala:78:21
  wire [2:0] _out_andMatrixOutputs_T =
    {out_invInputs[0], out_invInputs[2], out_invInputs[3]};	// src/main/scala/chisel3/util/pla.scala:78:21, :91:29, :98:53
  wire [3:0] _out_andMatrixOutputs_T_2 =
    {out_invInputs[0], out_invInputs[1], out_invInputs[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :91:29, :98:53
  wire [3:0] _out_andMatrixOutputs_T_5 =
    {out_invInputs[0], src[1], out_invInputs[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_6 = {src[0], src[1], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_7 = {out_invInputs[0], src[2], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_8 = {src[0], src[2], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_10 = {out_invInputs[2], src[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [1:0] _out_andMatrixOutputs_T_14 = {src[2], src[3]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  wire [3:0] _out_andMatrixOutputs_T_17 =
    {src[0], out_invInputs[2], out_invInputs[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [3:0] _out_andMatrixOutputs_T_19 =
    {src[1], out_invInputs[2], out_invInputs[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [1:0] _out_andMatrixOutputs_T_22 = {src[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  wire [3:0] _out_andMatrixOutputs_T_24 = {src[1], src[2], src[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  assign out =
    {&{out_invInputs[0],
       out_invInputs[1],
       out_invInputs[2],
       out_invInputs[3],
       out_invInputs[4]},
     |{&{src[2], src[4]}, &_out_andMatrixOutputs_T_22},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_24},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_24},
     |{&{out_invInputs[0], out_invInputs[1], out_invInputs[2], out_invInputs[3]},
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_19,
       &_out_andMatrixOutputs_T_24},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_5,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_14,
       &_out_andMatrixOutputs_T_17},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_2,
       &{src[0], src[1], src[2], out_invInputs[4]},
       &_out_andMatrixOutputs_T_10,
       &{src[1], src[3]},
       &_out_andMatrixOutputs_T_14,
       &_out_andMatrixOutputs_T_17},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_14,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_22},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_2,
       &{src[0], out_invInputs[1], out_invInputs[2]},
       &_out_andMatrixOutputs_T_5,
       &_out_andMatrixOutputs_T_10,
       &{src[0], src[1], src[4]},
       &{src[0], src[3], src[4]},
       &_out_andMatrixOutputs_T_24},
     |{&{src[1], src[3], out_invInputs[4]},
       &{src[0], src[1], src[2], src[3]},
       &{out_invInputs[0], src[1], out_invInputs[3], src[4]},
       &_out_andMatrixOutputs_T_19},
     |{&{src[0], src[3], out_invInputs[4]},
       &{src[0], out_invInputs[1], out_invInputs[3], src[4]},
       &_out_andMatrixOutputs_T_17},
     5'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:57:7, src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:{53,70}, :102:36, :114:{19,36}
endmodule
module FliDTable(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:94:7
  input  [4:0]  src,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:8:15
  output [15:0] out	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:9:15
);

  wire [4:0] out_invInputs = ~src;	// src/main/scala/chisel3/util/pla.scala:78:21
  wire [2:0] _out_andMatrixOutputs_T =
    {out_invInputs[0], out_invInputs[2], out_invInputs[3]};	// src/main/scala/chisel3/util/pla.scala:78:21, :91:29, :98:53
  wire [3:0] _out_andMatrixOutputs_T_2 =
    {out_invInputs[0], out_invInputs[1], out_invInputs[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :91:29, :98:53
  wire [3:0] _out_andMatrixOutputs_T_5 =
    {out_invInputs[0], src[1], out_invInputs[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_6 = {src[0], src[1], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_7 = {out_invInputs[0], src[2], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_8 = {src[0], src[2], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [2:0] _out_andMatrixOutputs_T_10 = {out_invInputs[2], src[3], out_invInputs[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [1:0] _out_andMatrixOutputs_T_14 = {src[2], src[3]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  wire [3:0] _out_andMatrixOutputs_T_17 =
    {src[0], out_invInputs[2], out_invInputs[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [3:0] _out_andMatrixOutputs_T_19 =
    {src[1], out_invInputs[2], out_invInputs[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:53
  wire [1:0] _out_andMatrixOutputs_T_22 = {src[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  wire [3:0] _out_andMatrixOutputs_T_24 = {src[1], src[2], src[3], src[4]};	// src/main/scala/chisel3/util/pla.scala:90:45, :98:53
  assign out =
    {&{out_invInputs[0],
       out_invInputs[1],
       out_invInputs[2],
       out_invInputs[3],
       out_invInputs[4]},
     |{&{src[2], src[4]}, &_out_andMatrixOutputs_T_22},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_24},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_24},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_24},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_24},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_24},
     |{&{out_invInputs[0], out_invInputs[1], out_invInputs[2], out_invInputs[3]},
       &_out_andMatrixOutputs_T_6,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_19,
       &_out_andMatrixOutputs_T_24},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_5,
       &_out_andMatrixOutputs_T_8,
       &_out_andMatrixOutputs_T_10,
       &_out_andMatrixOutputs_T_14,
       &_out_andMatrixOutputs_T_17},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_2,
       &{src[0], src[1], src[2], out_invInputs[4]},
       &_out_andMatrixOutputs_T_10,
       &{src[1], src[3]},
       &_out_andMatrixOutputs_T_14,
       &_out_andMatrixOutputs_T_17},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_7,
       &_out_andMatrixOutputs_T_14,
       &_out_andMatrixOutputs_T_17,
       &_out_andMatrixOutputs_T_22},
     |{&_out_andMatrixOutputs_T,
       &_out_andMatrixOutputs_T_2,
       &{src[0], out_invInputs[1], out_invInputs[2]},
       &_out_andMatrixOutputs_T_5,
       &_out_andMatrixOutputs_T_10,
       &{src[0], src[1], src[4]},
       &{src[0], src[3], src[4]},
       &_out_andMatrixOutputs_T_24},
     |{&{src[1], src[3], out_invInputs[4]},
       &{src[0], src[1], src[2], src[3]},
       &{out_invInputs[0], src[1], out_invInputs[3], src[4]},
       &_out_andMatrixOutputs_T_19},
     |{&{src[0], src[3], out_invInputs[4]},
       &{src[0], out_invInputs[1], out_invInputs[3], src[4]},
       &_out_andMatrixOutputs_T_17},
     2'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/fpu/FliTable.scala:94:7, src/main/scala/chisel3/util/pla.scala:78:21, :90:45, :91:29, :98:{53,70}, :102:36, :114:{19,36}
endmodule
