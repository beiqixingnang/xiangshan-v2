
module RVCExpander(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/PreDecode.scala:282:7
  input  [31:0] io_in,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/PreDecode.scala:283:14
  input         io_fsIsOff,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/PreDecode.scala:283:14
  output [31:0] io_out_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/PreDecode.scala:283:14
  output        io_ill	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/PreDecode.scala:283:14
);

  wire [2:0]      _io_out_s_funct_T_2 = {io_in[12], io_in[6:5]};	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:45:20, :52:30, :129:68
  wire [2:0]      _io_out_s_funct_T_4 = {_io_out_s_funct_T_2 == 3'h1, 2'h0};	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:41:24, :83:24, :129:68, home/lishuo/xs-v2-local/rocket-chip/src/main/scala/util/package.scala:33:{76,86}
  wire [7:0][2:0] _GEN =
    {{3'h3},
     {3'h0},
     {3'h0},
     {3'h0},
     {3'h7},
     {3'h6},
     {_io_out_s_funct_T_4},
     {_io_out_s_funct_T_4}};	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:51:29, :63:15, :67:23, home/lishuo/xs-v2-local/rocket-chip/src/main/scala/util/package.scala:33:{76,86}
  wire [3:0]      _GEN_0 = {4{io_in[12]}};	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:52:30, :121:24
  wire [6:0]      io_out_s_load_opc = (|(io_in[11:7])) ? 7'h3 : 7'h1F;	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:40:13, :62:20, :66:22, :166:{23,27}
  wire [4:0]      _io_out_T_2 = {io_in[1:0], io_in[15:13]};	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:207:{10,12,20}
  wire [31:0]     _io_out_T_26_bits =
    _io_out_T_2 == 5'hC
      ? ((&(io_in[11:10]))
           ? ((&{io_in[12], io_in[6:5]})
                ? ((&(io_in[4:2])) | io_in[4:2] == 3'h6
                     ? 32'h0
                     : io_in[4:2] == 3'h5
                         ? {14'h3FFD, io_in[9:7], 5'h11, io_in[9:7], 7'h13}
                         : {1'h0,
                            io_in[4:2] == 3'h4
                              ? {13'h201, io_in[9:7], 5'h1, io_in[9:7], 7'h3B}
                              : io_in[4:2] == 3'h3
                                  ? {13'h1815, io_in[9:7], 5'h5, io_in[9:7], 7'h13}
                                  : io_in[4:2] == 3'h2
                                      ? {13'h201, io_in[9:7], 5'h11, io_in[9:7], 7'h3B}
                                      : {io_in[4:2] == 3'h1
                                           ? {13'h1811, io_in[9:7], 5'h5}
                                           : {13'h3FD, io_in[9:7], 5'h1D},
                                         io_in[9:7],
                                         7'h13}})
                : {1'h0,
                   io_in[6:5] == 2'h0,
                   4'h0,
                   {io_in[12], io_in[6:5]} == 3'h6,
                   2'h1,
                   io_in[4:2],
                   2'h1,
                   io_in[9:7],
                   _GEN[_io_out_s_funct_T_2],
                   2'h1,
                   io_in[9:7],
                   io_in[12] ? {3'h3, ~(io_in[6]), 3'h3} : 7'h33})
           : {io_in[11:10] == 2'h2
                ? {{7{io_in[12]}}, io_in[6:2], 2'h1, io_in[9:7], 5'h1D}
                : {1'h0,
                   io_in[11:10] == 2'h1,
                   4'h0,
                   io_in[12],
                   io_in[6:2],
                   2'h1,
                   io_in[9:7],
                   5'h15},
              io_in[9:7],
              7'h13})
      : _io_out_T_2 == 5'hB
          ? (io_in[7] & io_in[6:2] == 5'h0 & io_in[12:11] == 2'h0
               ? 32'h13
               : {{3{io_in[12]}},
                  io_in[11:7] == 5'h2
                    ? {io_in[4:3],
                       io_in[5],
                       io_in[2],
                       io_in[6],
                       4'h0,
                       io_in[11:7],
                       3'h0,
                       io_in[11:7],
                       (|{{7{io_in[12]}}, io_in[6:2]}) ? 7'h13 : 7'h1F}
                    : {{12{io_in[12]}},
                       io_in[6:2],
                       io_in[11:7],
                       3'h3,
                       {{7{io_in[12]}}, io_in[6:2]} == 12'h0,
                       3'h7}})
          : _io_out_T_2 == 5'hA
              ? {{7{io_in[12]}}, io_in[6:2], 8'h0, io_in[11:7], 7'h13}
              : _io_out_T_2 == 5'h9
                  ? {{7{io_in[12]}},
                     io_in[6:2],
                     io_in[11:7],
                     3'h0,
                     io_in[11:7],
                     4'h3,
                     io_in[11:7] == 5'h0,
                     2'h3}
                  : _io_out_T_2 == 5'h8
                      ? ((|(io_in[11:7]))
                           ? {{7{io_in[12]}},
                              io_in[6:2],
                              io_in[11:7],
                              3'h0,
                              io_in[11:7],
                              7'h13}
                           : 32'h13)
                      : _io_out_T_2 == 5'h7
                          ? {4'h0,
                             io_in[6:5],
                             io_in[12],
                             2'h1,
                             io_in[4:2],
                             2'h1,
                             io_in[9:7],
                             3'h3,
                             io_in[11:10],
                             10'h23}
                          : _io_out_T_2 == 5'h6
                              ? {5'h0,
                                 io_in[5],
                                 io_in[12],
                                 2'h1,
                                 io_in[4:2],
                                 2'h1,
                                 io_in[9:7],
                                 3'h2,
                                 io_in[11:10],
                                 io_in[6],
                                 9'h23}
                              : _io_out_T_2 == 5'h5
                                  ? {4'h0,
                                     io_in[6:5],
                                     io_in[12],
                                     2'h1,
                                     io_in[4:2],
                                     2'h1,
                                     io_in[9:7],
                                     3'h3,
                                     io_in[11:10],
                                     10'h27}
                                  : _io_out_T_2 == 5'h4
                                      ? {7'h0,
                                         (&(io_in[11:10]))
                                           ? {2'h1,
                                              io_in[4:2],
                                              2'h1,
                                              io_in[9:7],
                                              6'h8,
                                              io_in[5],
                                              8'h23}
                                           : io_in[11:10] == 2'h2
                                               ? {2'h1,
                                                  io_in[4:2],
                                                  2'h1,
                                                  io_in[9:7],
                                                  6'h0,
                                                  io_in[5],
                                                  io_in[6],
                                                  7'h23}
                                               : {3'h0,
                                                  io_in[5],
                                                  io_in[11:10] == 2'h1
                                                    ? {3'h1,
                                                       io_in[9:7],
                                                       ~(io_in[6]),
                                                       4'h5}
                                                    : {io_in[6], 2'h1, io_in[9:7], 5'h11},
                                                  io_in[4:2],
                                                  7'h3}}
                                      : _io_out_T_2 == 5'h3
                                          ? {4'h0,
                                             io_in[6:5],
                                             io_in[12:10],
                                             5'h1,
                                             io_in[9:7],
                                             5'hD,
                                             io_in[4:2],
                                             7'h3}
                                          : _io_out_T_2 == 5'h2
                                              ? {5'h0,
                                                 io_in[5],
                                                 io_in[12:10],
                                                 io_in[6],
                                                 4'h1,
                                                 io_in[9:7],
                                                 5'h9,
                                                 io_in[4:2],
                                                 7'h3}
                                              : _io_out_T_2 == 5'h1
                                                  ? {4'h0,
                                                     io_in[6:5],
                                                     io_in[12:10],
                                                     5'h1,
                                                     io_in[9:7],
                                                     5'hD,
                                                     io_in[4:2],
                                                     7'h7}
                                                  : {2'h0,
                                                     io_in[10:7],
                                                     io_in[12:11],
                                                     io_in[5],
                                                     io_in[6],
                                                     12'h41,
                                                     io_in[4:2],
                                                     (|(io_in[12:5])) ? 7'h13 : 7'h1F};	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:29:14, :37:{17,29}, :38:{17,29}, :40:13, :41:{24,26,35,45,51}, :43:18, :45:{20,28}, :51:{24,29,42,56}, :52:{20,25,30,38}, :62:{20,22,29}, :63:15, :66:22, :67:23, :72:22, :73:22, :74:{23,30,63}, :81:20, :83:24, :84:12, :86:19, :87:19, :89:34, :97:25, :98:{10,14,35}, :101:{20,24}, :102:15, :108:22, :110:{20,29}, :111:15, :114:29, :115:24, :116:{20,34,42,54}, :118:{10,26,30}, :127:21, :129:68, :130:30, :131:{22,33}, :132:{26,42}, :133:59, :136:24, :137:26, :138:26, :154:{12,16,32}, :192:21, :207:10, home/lishuo/xs-v2-local/rocket-chip/src/main/scala/util/package.scala:33:{76,86}
  wire [4:0]      _io_ill_T_2 = {io_in[1:0], io_in[15:13]};	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:207:{12,20}, :252:10
  assign io_out_bits =
    (&_io_out_T_2) | _io_out_T_2 == 5'h1E | _io_out_T_2 == 5'h1D | _io_out_T_2 == 5'h1C
    | _io_out_T_2 == 5'h1B | _io_out_T_2 == 5'h1A | _io_out_T_2 == 5'h19
    | _io_out_T_2 == 5'h18
      ? io_in
      : _io_out_T_2 == 5'h17
          ? {3'h0, io_in[9:7], io_in[12], io_in[6:2], 8'h13, io_in[11:10], 10'h23}
          : _io_out_T_2 == 5'h16
              ? {4'h0, io_in[8:7], io_in[12], io_in[6:2], 8'h12, io_in[11:9], 9'h23}
              : _io_out_T_2 == 5'h15
                  ? {3'h0, io_in[9:7], io_in[12], io_in[6:2], 8'h13, io_in[11:10], 10'h27}
                  : _io_out_T_2 == 5'h14
                      ? (io_in[12]
                           ? {7'h0,
                              (|(io_in[6:2]))
                                ? {io_in[6:2], io_in[11:7], 3'h0, io_in[11:7], 7'h33}
                                : (|(io_in[11:7]))
                                    ? {io_in[6:2], io_in[11:7], 15'hE7}
                                    : {io_in[6:3], 1'h1, io_in[11:7], 15'h73}}
                           : (|(io_in[6:2]))
                               ? {12'h0, io_in[6:2], 3'h0, io_in[11:7], 7'h13}
                               : {7'h0,
                                  io_in[6:2],
                                  io_in[11:7],
                                  (|(io_in[11:7])) ? 15'h67 : 15'h1F})
                      : _io_out_T_2 == 5'h13
                          ? {3'h0,
                             io_in[4:2],
                             io_in[12],
                             io_in[6:5],
                             11'h13,
                             io_in[11:7],
                             io_out_s_load_opc}
                          : _io_out_T_2 == 5'h12
                              ? {4'h0,
                                 io_in[3:2],
                                 io_in[12],
                                 io_in[6:4],
                                 10'h12,
                                 io_in[11:7],
                                 io_out_s_load_opc}
                              : _io_out_T_2 == 5'h11
                                  ? {3'h0,
                                     io_in[4:2],
                                     io_in[12],
                                     io_in[6:5],
                                     11'h13,
                                     io_in[11:7],
                                     7'h7}
                                  : _io_out_T_2 == 5'h10
                                      ? {6'h0,
                                         io_in[12],
                                         io_in[6:2],
                                         io_in[11:7],
                                         3'h1,
                                         io_in[11:7],
                                         7'h13}
                                      : _io_out_T_2 == 5'hF
                                          ? {_GEN_0,
                                             io_in[6:5],
                                             io_in[2],
                                             7'h1,
                                             io_in[9:7],
                                             3'h1,
                                             io_in[11:10],
                                             io_in[4:3],
                                             io_in[12],
                                             7'h63}
                                          : _io_out_T_2 == 5'hE
                                              ? {_GEN_0,
                                                 io_in[6:5],
                                                 io_in[2],
                                                 7'h1,
                                                 io_in[9:7],
                                                 3'h0,
                                                 io_in[11:10],
                                                 io_in[4:3],
                                                 io_in[12],
                                                 7'h63}
                                              : _io_out_T_2 == 5'hD
                                                  ? {io_in[12],
                                                     io_in[8],
                                                     io_in[10:9],
                                                     io_in[6],
                                                     io_in[7],
                                                     io_in[2],
                                                     io_in[11],
                                                     io_in[5:3],
                                                     {9{io_in[12]}},
                                                     12'h6F}
                                                  : _io_out_T_26_bits;	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:29:14, :37:{17,29}, :38:29, :40:13, :41:51, :45:20, :46:{22,37}, :48:22, :51:{24,42,56}, :52:{25,30,38}, :53:{36,42,69,76}, :62:20, :63:15, :67:23, :72:22, :73:22, :74:{23,30,63}, :83:24, :89:34, :97:25, :116:20, :120:21, :121:24, :122:24, :131:33, :133:59, :166:23, :169:24, :170:25, :176:{24,65}, :177:25, :188:19, :189:25, :190:{33,37}, :191:{22,27}, :192:21, :193:{23,46}, :194:{33,37}, :195:{25,30}, :196:10, :207:10, home/lishuo/xs-v2-local/rocket-chip/src/main/scala/util/package.scala:33:{76,86}, home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/PreDecode.scala:282:7
  assign io_ill =
    ~((&_io_ill_T_2) | _io_ill_T_2 == 5'h1E | _io_ill_T_2 == 5'h1D | _io_ill_T_2 == 5'h1C
      | _io_ill_T_2 == 5'h1B | _io_ill_T_2 == 5'h1A | _io_ill_T_2 == 5'h19
      | _io_ill_T_2 == 5'h18 | _io_ill_T_2 == 5'h17 | _io_ill_T_2 == 5'h16)
    & (_io_ill_T_2 == 5'h15
         ? io_fsIsOff
         : _io_ill_T_2 == 5'h14
             ? io_in[12:2] == 11'h0
             : _io_ill_T_2 == 5'h13
                 ? ~(|(io_in[11:7]))
                 : _io_ill_T_2 == 5'h12
                     ? ~(|(io_in[11:7]))
                     : _io_ill_T_2 == 5'h11
                         ? io_fsIsOff
                         : ~(_io_ill_T_2 == 5'h10 | _io_ill_T_2 == 5'hF
                             | _io_ill_T_2 == 5'hE | _io_ill_T_2 == 5'hD)
                           & (_io_ill_T_2 == 5'hC
                                ? (&(io_in[12:10])) & (&(io_in[6:3]))
                                : _io_ill_T_2 == 5'hB
                                    ? ~(io_in[12] | (|(io_in[6:2])))
                                      & ~(~(io_in[11]) & io_in[7])
                                    : _io_ill_T_2 != 5'hA
                                      & (_io_ill_T_2 == 5'h9
                                           ? ~(|(io_in[11:7]))
                                           : ~(_io_ill_T_2 == 5'h8 | _io_ill_T_2 == 5'h7
                                               | _io_ill_T_2 == 5'h6)
                                             & (_io_ill_T_2 == 5'h5
                                                  ? io_fsIsOff
                                                  : _io_ill_T_2 == 5'h4
                                                      ? io_in[12] | io_in[11] & io_in[10]
                                                        & io_in[6]
                                                      : ~(_io_ill_T_2 == 5'h3
                                                          | _io_ill_T_2 == 5'h2)
                                                        & (_io_ill_T_2 == 5'h1
                                                             ? io_fsIsOff
                                                             : io_in[12:5] == 8'h0)))));	// home/lishuo/xs-v2-local/rocket-chip/src/main/scala/rocket/RVC.scala:40:13, :41:51, :45:28, :52:{30,38}, :53:69, :62:{22,29}, :63:15, :98:14, :116:20, :192:21, :211:27, :221:{26,40,45}, :226:47, :227:{16,24,34}, :228:{15,22}, :229:{24,27}, :230:{29,34,38,45}, :235:18, :245:{21,29}, :252:10, home/lishuo/xs-v2-local/rocket-chip/src/main/scala/util/package.scala:33:{76,86}, home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/PreDecode.scala:282:7
endmodule
