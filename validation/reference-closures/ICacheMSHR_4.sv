module ICacheMSHR_4(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
  input         clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
                reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
                io_fencei,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
                io_flush,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
                io_wfi_wfiReq,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output        io_wfi_wfiSafe,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input         io_invalid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output        io_req_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input         io_req_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input  [41:0] io_req_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input  [7:0]  io_req_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input         io_acquire_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output        io_acquire_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output [47:0] io_acquire_bits_acquire_address,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output [7:0]  io_acquire_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input  [41:0] io_lookUps_0_info_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input  [7:0]  io_lookUps_0_info_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output        io_lookUps_0_hit,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input  [41:0] io_lookUps_1_info_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input  [7:0]  io_lookUps_1_info_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output        io_lookUps_1_hit,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
                io_resp_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output [41:0] io_resp_bits_blkPaddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output [7:0]  io_resp_bits_vSetIdx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  output [1:0]  io_resp_bits_way,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
  input  [1:0]  io_victimWay	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:114:28
);

  reg         valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:116:30
  reg         flush;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:118:31
  reg         fencei;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:119:31
  reg         issue;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:121:30
  reg  [41:0] blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:123:33
  reg  [7:0]  vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:124:33
  reg  [1:0]  way;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:125:33
  wire        io_req_ready_0 = ~valid & ~io_flush & ~io_fencei;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:116:30, :150:{19,29,39,42}
  wire        io_acquire_valid_0 =
    valid & ~issue & ~io_flush & ~io_fencei & ~io_wfi_wfiReq;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:116:30, :121:30, :150:{29,42}, :161:{32,66,69}
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
    if (reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
      valid <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30
      flush <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :118:31
      fencei <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :119:31
      issue <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :121:30
      blkPaddr <= 42'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:123:33
      vSetIdx <= 8'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:124:33
      way <= 2'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :125:33
    end
    else begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
      automatic logic _GEN = io_fencei | io_flush;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:141:18
      automatic logic _GEN_0 = io_req_ready_0 & io_req_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:150:39, src/main/scala/chisel3/util/Decoupled.scala:51:35
      automatic logic _GEN_1 = io_acquire_ready & io_acquire_valid_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:161:66, src/main/scala/chisel3/util/Decoupled.scala:51:35
      valid <= ~io_invalid & (_GEN_0 | ~(_GEN & ~issue) & valid);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:116:30, :121:30, :141:{18,31}, :144:{10,18}, :145:13, :151:21, :152:14, :179:20, :180:11, src/main/scala/chisel3/util/Decoupled.scala:51:35
      flush <= ~_GEN_0 & (_GEN | flush);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:118:31, :141:{18,31}, :143:12, :151:21, :153:14, src/main/scala/chisel3/util/Decoupled.scala:51:35
      fencei <= ~_GEN_0 & (_GEN | fencei);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:119:31, :141:{18,31}, :142:12, :151:21, :153:14, :155:14, src/main/scala/chisel3/util/Decoupled.scala:51:35
      issue <= _GEN_1 | ~_GEN_0 & issue;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:121:30, :141:31, :151:21, :153:14, :154:14, :173:25, :174:11, src/main/scala/chisel3/util/Decoupled.scala:51:35
      if (_GEN_0) begin	// src/main/scala/chisel3/util/Decoupled.scala:51:35
        blkPaddr <= io_req_bits_blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:123:33
        vSetIdx <= io_req_bits_vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:124:33
      end
      if (_GEN_1)	// src/main/scala/chisel3/util/Decoupled.scala:51:35
        way <= io_victimWay;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:125:33
    end
  end // always @(posedge, posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
      automatic logic [31:0] _RANDOM[0:1];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
        for (logic [1:0] i = 2'h0; i < 2'h2; i += 2'h1) begin
          _RANDOM[i[0]] = `RANDOM;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
        end	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
        valid = _RANDOM[1'h0][0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30
        flush = _RANDOM[1'h0][1];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :118:31
        fencei = _RANDOM[1'h0][2];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :119:31
        issue = _RANDOM[1'h0][3];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :121:30
        blkPaddr = {_RANDOM[1'h0][31:4], _RANDOM[1'h1][13:0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :123:33
        vSetIdx = _RANDOM[1'h1][21:14];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :123:33, :124:33
        way = _RANDOM[1'h1][23:22];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :123:33, :125:33
      `endif // RANDOMIZE_REG_INIT
      if (reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
        valid = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30
        flush = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :118:31
        fencei = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :119:31
        issue = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :121:30
        blkPaddr = 42'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:123:33
        vSetIdx = 8'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:124:33
        way = 2'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :125:33
      end
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  assign io_wfi_wfiSafe = ~(valid & issue);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :121:30, :190:{21,29}
  assign io_req_ready = io_req_ready_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :150:39
  assign io_acquire_valid = io_acquire_valid_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :161:66
  assign io_acquire_bits_acquire_address = {blkPaddr, 6'h0};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :123:33, :164:20
  assign io_acquire_bits_vSetIdx = vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :124:33
  assign io_lookUps_0_hit =
    valid & ~fencei & ~flush & io_lookUps_0_info_bits_vSetIdx == vSetIdx
    & io_lookUps_0_info_bits_blkPaddr == blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :118:31, :119:31, :123:33, :124:33, :129:{14,25,61,74}, :130:32
  assign io_lookUps_1_hit =
    valid & ~fencei & ~flush & io_lookUps_1_info_bits_vSetIdx == vSetIdx
    & io_lookUps_1_info_bits_blkPaddr == blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :118:31, :119:31, :123:33, :124:33, :129:{14,25,61,74}, :130:32
  assign io_resp_valid = valid & ~flush & ~fencei;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :116:30, :118:31, :119:31, :129:{14,25}, :184:34
  assign io_resp_bits_blkPaddr = blkPaddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :123:33
  assign io_resp_bits_vSetIdx = vSetIdx;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :124:33
  assign io_resp_bits_way = way;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala:113:7, :125:33
endmodule
