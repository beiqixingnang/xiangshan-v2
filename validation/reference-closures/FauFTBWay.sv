module FauFTBWay(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
  input         clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
                reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
  input  [15:0] io_req_tag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output        io_resp_isCall,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_isRet,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_isJalr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output [3:0]  io_resp_brSlots_0_offset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output        io_resp_brSlots_0_sharing,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_brSlots_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output [11:0] io_resp_brSlots_0_lower,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output [1:0]  io_resp_brSlots_0_tarStat,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output [3:0]  io_resp_tailSlot_offset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output        io_resp_tailSlot_sharing,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_tailSlot_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output [19:0] io_resp_tailSlot_lower,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output [1:0]  io_resp_tailSlot_tarStat,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output [3:0]  io_resp_pftAddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output        io_resp_carry,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_last_may_be_rvi_call,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_strong_bias_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_strong_bias_1,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_resp_hit,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [15:0] io_update_req_tag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  output        io_update_hit,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input         io_write_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_isCall,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_isRet,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_isJalr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [3:0]  io_write_entry_brSlots_0_offset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input         io_write_entry_brSlots_0_sharing,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_brSlots_0_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [11:0] io_write_entry_brSlots_0_lower,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [1:0]  io_write_entry_brSlots_0_tarStat,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [3:0]  io_write_entry_tailSlot_offset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input         io_write_entry_tailSlot_sharing,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_tailSlot_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [19:0] io_write_entry_tailSlot_lower,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [1:0]  io_write_entry_tailSlot_tarStat,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [3:0]  io_write_entry_pftAddr,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input         io_write_entry_carry,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_last_may_be_rvi_call,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_strong_bias_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
                io_write_entry_strong_bias_1,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
  input  [15:0] io_write_tag	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
);

  reg        data_isCall;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_isRet;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_isJalr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [3:0]  data_brSlots_0_offset;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_brSlots_0_sharing;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_brSlots_0_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [11:0] data_brSlots_0_lower;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [1:0]  data_brSlots_0_tarStat;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [3:0]  data_tailSlot_offset;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_tailSlot_sharing;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_tailSlot_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [19:0] data_tailSlot_lower;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [1:0]  data_tailSlot_tarStat;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [3:0]  data_pftAddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_carry;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_last_may_be_rvi_call;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_strong_bias_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg        data_strong_bias_1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
  reg [15:0] tag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:57:18
  reg        valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:58:22
  always @(posedge clock) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
    if (io_write_valid) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:44:14
      data_isCall <= io_write_entry_isCall;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_isRet <= io_write_entry_isRet;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_isJalr <= io_write_entry_isJalr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_valid <= io_write_entry_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_brSlots_0_offset <= io_write_entry_brSlots_0_offset;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_brSlots_0_sharing <= io_write_entry_brSlots_0_sharing;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_brSlots_0_valid <= io_write_entry_brSlots_0_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_brSlots_0_lower <= io_write_entry_brSlots_0_lower;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_brSlots_0_tarStat <= io_write_entry_brSlots_0_tarStat;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_tailSlot_offset <= io_write_entry_tailSlot_offset;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_tailSlot_sharing <= io_write_entry_tailSlot_sharing;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_tailSlot_valid <= io_write_entry_tailSlot_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_tailSlot_lower <= io_write_entry_tailSlot_lower;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_tailSlot_tarStat <= io_write_entry_tailSlot_tarStat;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_pftAddr <= io_write_entry_pftAddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_carry <= io_write_entry_carry;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_last_may_be_rvi_call <= io_write_entry_last_may_be_rvi_call;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_strong_bias_0 <= io_write_entry_strong_bias_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      data_strong_bias_1 <= io_write_entry_strong_bias_1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:56:18
      tag <= io_write_tag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:57:18
    end
  end // always @(posedge)
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
    if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
      valid <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:58:22
    else	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
      valid <= io_write_valid & ~valid | valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:58:22, :67:24, :68:{10,18}, :69:13
  end // always @(posedge, posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
      automatic logic [31:0] _RANDOM[0:2];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
        for (logic [1:0] i = 2'h0; i < 2'h3; i += 2'h1) begin
          _RANDOM[i] = `RANDOM;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
        end	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
        data_isCall = _RANDOM[2'h0][0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_isRet = _RANDOM[2'h0][1];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_isJalr = _RANDOM[2'h0][2];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_valid = _RANDOM[2'h0][3];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_brSlots_0_offset = _RANDOM[2'h0][7:4];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_brSlots_0_sharing = _RANDOM[2'h0][8];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_brSlots_0_valid = _RANDOM[2'h0][9];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_brSlots_0_lower = _RANDOM[2'h0][21:10];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_brSlots_0_tarStat = _RANDOM[2'h0][23:22];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_tailSlot_offset = _RANDOM[2'h0][27:24];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_tailSlot_sharing = _RANDOM[2'h0][28];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_tailSlot_valid = _RANDOM[2'h0][29];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_tailSlot_lower = {_RANDOM[2'h0][31:30], _RANDOM[2'h1][17:0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_tailSlot_tarStat = _RANDOM[2'h1][19:18];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_pftAddr = _RANDOM[2'h1][23:20];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_carry = _RANDOM[2'h1][24];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_last_may_be_rvi_call = _RANDOM[2'h1][25];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_strong_bias_0 = _RANDOM[2'h1][26];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        data_strong_bias_1 = _RANDOM[2'h1][27];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
        tag = {_RANDOM[2'h1][31:28], _RANDOM[2'h2][11:0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18, :57:18
        valid = _RANDOM[2'h2][12];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :57:18, :58:22
      `endif // RANDOMIZE_REG_INIT
      if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
        valid = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:58:22
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  assign io_resp_isCall = data_isCall;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_isRet = data_isRet;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_isJalr = data_isJalr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_valid = data_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_brSlots_0_offset = data_brSlots_0_offset;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_brSlots_0_sharing = data_brSlots_0_sharing;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_brSlots_0_valid = data_brSlots_0_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_brSlots_0_lower = data_brSlots_0_lower;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_brSlots_0_tarStat = data_brSlots_0_tarStat;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_tailSlot_offset = data_tailSlot_offset;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_tailSlot_sharing = data_tailSlot_sharing;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_tailSlot_valid = data_tailSlot_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_tailSlot_lower = data_tailSlot_lower;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_tailSlot_tarStat = data_tailSlot_tarStat;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_pftAddr = data_pftAddr;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_carry = data_carry;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_last_may_be_rvi_call = data_last_may_be_rvi_call;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_strong_bias_0 = data_strong_bias_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_strong_bias_1 = data_strong_bias_1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :56:18
  assign io_resp_hit = tag == io_req_tag & valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :57:18, :58:22, :61:{22,37}
  assign io_update_hit =
    tag == io_update_req_tag & valid | io_write_tag == io_update_req_tag & io_write_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/FauFTB.scala:43:7, :57:18, :58:22, :63:{26,49,59}, :64:{20,43}
endmodule
