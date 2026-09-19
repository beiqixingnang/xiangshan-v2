
module ByteMaskTailGen(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:46:7
  input  [7:0]  io_in_begin,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
                io_in_end,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
  input         io_in_vma,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
                io_in_vta,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
  input  [1:0]  io_in_vsew,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
  input  [15:0] io_in_maskUsed,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
  input  [2:0]  io_in_vdIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
  output [15:0] io_out_activeEn,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
                io_out_agnosticEn	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:57:14
);

  wire [15:0]  _maskEn_maskExtractor_io_out_mask;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:40:31
  wire [254:0] _tailEn_uintToContTail0sMod128Bits_io_dataOut;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:34:37
  wire [254:0] _bodyEn_uintToContTail1sMod128Bits_io_dataOut;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:34:37
  wire [254:0] _bodyEn_uintToContTail0sMod128Bits_io_dataOut;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:34:37
  wire [254:0] _prestartEn_uintToContTail1sMod128Bits_io_dataOut;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:34:37
  wire [3:0]   eewOH_sew_oneHot =
    {&io_in_vsew, io_in_vsew == 2'h2, io_in_vsew == 2'h1, io_in_vsew == 2'h0};	// home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/vector/VectorALU/VAluBundles.scala:113:19, :114:{53,63}
  wire [7:0]   startBytes =
    (eewOH_sew_oneHot[0] ? io_in_begin : 8'h0)
    | (eewOH_sew_oneHot[1] ? {io_in_begin[6:0], 1'h0} : 8'h0)
    | (eewOH_sew_oneHot[2] ? {io_in_begin[5:0], 2'h0} : 8'h0)
    | (eewOH_sew_oneHot[3] ? {io_in_begin[4:0], 3'h0} : 8'h0);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:61:{73,99}, home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/vector/VectorALU/VAluBundles.scala:113:19, :114:53, src/main/scala/chisel3/util/Mux.scala:30:73, :32:36
  wire [7:0]   vlBytes =
    (eewOH_sew_oneHot[0] ? io_in_end : 8'h0)
    | (eewOH_sew_oneHot[1] ? {io_in_end[6:0], 1'h0} : 8'h0)
    | (eewOH_sew_oneHot[2] ? {io_in_end[5:0], 2'h0} : 8'h0)
    | (eewOH_sew_oneHot[3] ? {io_in_end[4:0], 3'h0} : 8'h0);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:61:99, :62:{71,97}, home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/vector/VectorALU/VAluBundles.scala:113:19, :114:53, src/main/scala/chisel3/util/Mux.scala:30:73, :32:36
  wire [127:0] prestartEn = _prestartEn_uintToContTail1sMod128Bits_io_dataOut[127:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:34:37, :38:37
  wire [127:0] bodyEn =
    _bodyEn_uintToContTail0sMod128Bits_io_dataOut[127:0]
    & _bodyEn_uintToContTail1sMod128Bits_io_dataOut[127:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:66:62, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:34:37, :38:37, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:34:37, :38:37
  wire [127:0] tailEn = _tailEn_uintToContTail0sMod128Bits_io_dataOut[127:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:34:37, :38:37
  wire         _tailEnInVd_T_8 = io_in_vdIdx == 3'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:61:99, home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34
  wire         _tailEnInVd_T_9 = io_in_vdIdx == 3'h1;	// home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34
  wire         _tailEnInVd_T_10 = io_in_vdIdx == 3'h2;	// home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34
  wire         _tailEnInVd_T_11 = io_in_vdIdx == 3'h3;	// home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34
  wire         _tailEnInVd_T_12 = io_in_vdIdx == 3'h4;	// home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34
  wire         _tailEnInVd_T_13 = io_in_vdIdx == 3'h5;	// home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34
  wire         _tailEnInVd_T_14 = io_in_vdIdx == 3'h6;	// home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34
  wire [15:0]  prestartEnInVd =
    (_tailEnInVd_T_8 ? prestartEn[15:0] : 16'h0)
    | (_tailEnInVd_T_9 ? prestartEn[31:16] : 16'h0)
    | (_tailEnInVd_T_10 ? prestartEn[47:32] : 16'h0)
    | (_tailEnInVd_T_11 ? prestartEn[63:48] : 16'h0)
    | (_tailEnInVd_T_12 ? prestartEn[79:64] : 16'h0)
    | (_tailEnInVd_T_13 ? prestartEn[95:80] : 16'h0)
    | (_tailEnInVd_T_14 ? prestartEn[111:96] : 16'h0)
    | ((&io_in_vdIdx) ? prestartEn[127:112] : 16'h0);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:68:95, :78:29, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:38:37, home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34, src/main/scala/chisel3/util/Mux.scala:30:73
  wire [15:0]  bodyEnInVd =
    (_tailEnInVd_T_8 ? bodyEn[15:0] : 16'h0) | (_tailEnInVd_T_9 ? bodyEn[31:16] : 16'h0)
    | (_tailEnInVd_T_10 ? bodyEn[47:32] : 16'h0)
    | (_tailEnInVd_T_11 ? bodyEn[63:48] : 16'h0)
    | (_tailEnInVd_T_12 ? bodyEn[79:64] : 16'h0)
    | (_tailEnInVd_T_13 ? bodyEn[95:80] : 16'h0)
    | (_tailEnInVd_T_14 ? bodyEn[111:96] : 16'h0)
    | ((&io_in_vdIdx) ? bodyEn[127:112] : 16'h0);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:66:62, :69:87, :78:29, home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34, src/main/scala/chisel3/util/Mux.scala:30:73
  wire [15:0]  tailEnInVd =
    (_tailEnInVd_T_8 ? tailEn[15:0] : 16'h0) | (_tailEnInVd_T_9 ? tailEn[31:16] : 16'h0)
    | (_tailEnInVd_T_10 ? tailEn[47:32] : 16'h0)
    | (_tailEnInVd_T_11 ? tailEn[63:48] : 16'h0)
    | (_tailEnInVd_T_12 ? tailEn[79:64] : 16'h0)
    | (_tailEnInVd_T_13 ? tailEn[95:80] : 16'h0)
    | (_tailEnInVd_T_14 ? tailEn[111:96] : 16'h0)
    | ((&io_in_vdIdx) ? tailEn[127:112] : 16'h0);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:70:87, :78:29, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:38:37, home/lishuo/xs-v2-local/yunsuan/src/main/scala/yunsuan/util/LookupTree.scala:24:34, src/main/scala/chisel3/util/Mux.scala:30:73
  wire [15:0]  maskOffEn = ~_maskEn_maskExtractor_io_out_mask;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:73:28, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:40:31
  wire [15:0]  maskAgnosticEn = (io_in_vma ? maskOffEn : 16'h0) & bodyEnInVd;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:73:28, :74:{35,63}, :78:29, src/main/scala/chisel3/util/Mux.scala:30:73
  wire [15:0]  tailAgnosticEn = io_in_vta ? tailEnInVd : 16'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:76:35, :78:29, src/main/scala/chisel3/util/Mux.scala:30:73
  wire         _agnosticEn_T = io_in_begin >= io_in_end;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:78:42
  UIntToContLow1s prestartEn_uintToContTail1sMod128Bits (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:34:37
    .io_dataIn  (startBytes),	// src/main/scala/chisel3/util/Mux.scala:30:73
    .io_dataOut (_prestartEn_uintToContTail1sMod128Bits_io_dataOut)
  );
  UIntToContLow0s bodyEn_uintToContTail0sMod128Bits (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:34:37
    .io_dataIn  (startBytes),	// src/main/scala/chisel3/util/Mux.scala:30:73
    .io_dataOut (_bodyEn_uintToContTail0sMod128Bits_io_dataOut)
  );
  UIntToContLow1s bodyEn_uintToContTail1sMod128Bits (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:34:37
    .io_dataIn  (vlBytes),	// src/main/scala/chisel3/util/Mux.scala:30:73
    .io_dataOut (_bodyEn_uintToContTail1sMod128Bits_io_dataOut)
  );
  UIntToContLow0s tailEn_uintToContTail0sMod128Bits (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:34:37
    .io_dataIn  (vlBytes),	// src/main/scala/chisel3/util/Mux.scala:30:73
    .io_dataOut (_tailEn_uintToContTail0sMod128Bits_io_dataOut)
  );
  MaskExtractor maskEn_maskExtractor (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:40:31
    .io_in_mask  (io_in_maskUsed),
    .io_in_vsew  (io_in_vsew),
    .io_out_mask (_maskEn_maskExtractor_io_out_mask)
  );
  assign io_out_activeEn =
    _agnosticEn_T ? 16'h0 : bodyEnInVd & _maskEn_maskExtractor_io_out_mask;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:46:7, :78:{29,42,84}, home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:40:31, src/main/scala/chisel3/util/Mux.scala:30:73
  assign io_out_agnosticEn = _agnosticEn_T ? 16'h0 : maskAgnosticEn | tailAgnosticEn;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala:46:7, :74:63, :76:35, :78:{29,42}, :79:{31,90}
endmodule


module MaskExtractor(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:19:7
  input  [15:0] io_in_mask,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:22:14
  input  [1:0]  io_in_vsew,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:22:14
  output [15:0] io_out_mask	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:22:14
);

  assign io_out_mask =
    (io_in_vsew == 2'h0 ? io_in_mask : 16'h0)
    | (io_in_vsew == 2'h1
         ? {{2{io_in_mask[7]}},
            {2{io_in_mask[6]}},
            {2{io_in_mask[5]}},
            {2{io_in_mask[4]}},
            {2{io_in_mask[3]}},
            {2{io_in_mask[2]}},
            {2{io_in_mask[1]}},
            {2{io_in_mask[0]}}}
         : 16'h0)
    | (io_in_vsew == 2'h2
         ? {{4{io_in_mask[3]}},
            {4{io_in_mask[2]}},
            {4{io_in_mask[1]}},
            {4{io_in_mask[0]}}}
         : 16'h0) | ((&io_in_vsew) ? {{8{io_in_mask[1]}}, {8{io_in_mask[0]}}} : 16'h0);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/MaskExtrator.scala:19:7, :29:11, :30:{11,41,74}, :31:{11,74}, :32:{11,74}, src/main/scala/chisel3/util/Mux.scala:30:73
endmodule


module UIntToContLow0s(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:10:7
  input  [7:0]   io_dataIn,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:13:14
  output [254:0] io_dataOut	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:13:14
);

  wire [126:0] _io_dataOut_T_507 =
    io_dataIn[6]
      ? {io_dataIn[5]
           ? {io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}},
              32'h0}
           : {32'hFFFFFFFF,
              io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}}},
         64'h0}
      : {64'hFFFFFFFFFFFFFFFF,
         io_dataIn[5]
           ? {io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}},
              32'h0}
           : {32'hFFFFFFFF,
              io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}}}};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:21:18, :22:18, :23:11, :24:{10,22}, :25:10
  wire [126:0] _io_dataOut_T_1015 =
    io_dataIn[6]
      ? {io_dataIn[5]
           ? {io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}},
              32'h0}
           : {32'hFFFFFFFF,
              io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}}},
         64'h0}
      : {64'hFFFFFFFFFFFFFFFF,
         io_dataIn[5]
           ? {io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}},
              32'h0}
           : {32'hFFFFFFFF,
              io_dataIn[4]
                ? {io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}},
                   16'h0}
                : {16'hFFFF,
                   io_dataIn[3]
                     ? {io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}},
                        8'h0}
                     : {8'hFF,
                        io_dataIn[2]
                          ? {io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])},
                             4'h0}
                          : {4'hF,
                             io_dataIn[1]
                               ? {~(io_dataIn[0]), 2'h0}
                               : {2'h3, ~(io_dataIn[0])}}}}}};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:21:18, :22:18, :23:11, :24:{10,22}, :25:10
  assign io_dataOut =
    io_dataIn[7]
      ? {_io_dataOut_T_507, 128'h0}
      : {128'hFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF, _io_dataOut_T_1015};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont0s.scala:10:7, :22:18, :23:11, :24:10, :25:10
endmodule


module UIntToContLow1s(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:10:7
  input  [7:0]   io_dataIn,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:13:14
  output [254:0] io_dataOut	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:13:14
);

  assign io_dataOut =
    io_dataIn[7]
      ? {io_dataIn[6]
           ? {io_dataIn[5]
                ? {io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}},
                   32'hFFFFFFFF}
                : {32'h0,
                   io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}}},
              64'hFFFFFFFFFFFFFFFF}
           : {64'h0,
              io_dataIn[5]
                ? {io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}},
                   32'hFFFFFFFF}
                : {32'h0,
                   io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}}}},
         128'hFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF}
      : {128'h0,
         io_dataIn[6]
           ? {io_dataIn[5]
                ? {io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}},
                   32'hFFFFFFFF}
                : {32'h0,
                   io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}}},
              64'hFFFFFFFFFFFFFFFF}
           : {64'h0,
              io_dataIn[5]
                ? {io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}},
                   32'hFFFFFFFF}
                : {32'h0,
                   io_dataIn[4]
                     ? {io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}},
                        16'hFFFF}
                     : {16'h0,
                        io_dataIn[3]
                          ? {io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}},
                             8'hFF}
                          : {8'h0,
                             io_dataIn[2]
                               ? {io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]},
                                  4'hF}
                               : {4'h0,
                                  io_dataIn[1]
                                    ? {io_dataIn[0], 2'h3}
                                    : {2'h0, io_dataIn[0]}}}}}}};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/vector/utils/UIntToCont1s.scala:10:7, :22:18, :23:11, :24:{10,22}, :25:10
endmodule
