module SstcInterruptGen(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
  input         clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
                reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
                i_stime_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input  [63:0] i_stime_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input         i_vstime_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input  [63:0] i_vstime_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input         i_stimecmp_wen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input  [63:0] i_stimecmp_rdata,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input         i_vstimecmp_wen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input  [63:0] i_vstimecmp_rdata,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  input         i_htimedeltaWen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
                i_menvcfg_wen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
                i_menvcfg_STCE,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
                i_henvcfg_wen,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
                i_henvcfg_STCE,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:7:13
  output        o_STIP,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:28:13
                o_VSTIP	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:28:13
);

  reg o_STIP_r;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:34:23
  reg o_VSTIP_r;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:35:23
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
    if (reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
      o_STIP_r <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :34:23
      o_VSTIP_r <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :35:23
    end
    else begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
      if (i_stime_valid | i_stimecmp_wen | i_menvcfg_wen)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:34:117
        o_STIP_r <= i_stime_bits >= i_stimecmp_rdata & i_menvcfg_STCE;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:34:{23,37,57}
      if (i_vstime_valid | i_vstimecmp_wen | i_htimedeltaWen | i_menvcfg_wen
          | i_henvcfg_wen)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:35:157
        o_VSTIP_r <= i_vstime_bits >= i_vstimecmp_rdata & i_henvcfg_STCE;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:35:{23,38,59}
    end
  end // always @(posedge, posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
      automatic logic [31:0] _RANDOM[0:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
        _RANDOM[/*Zero width*/ 1'b0] = `RANDOM;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
        o_STIP_r = _RANDOM[/*Zero width*/ 1'b0][0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :34:23
        o_VSTIP_r = _RANDOM[/*Zero width*/ 1'b0][1];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :34:23, :35:23
      `endif // RANDOMIZE_REG_INIT
      if (reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
        o_STIP_r = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :34:23
        o_VSTIP_r = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :35:23
      end
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  assign o_STIP = o_STIP_r;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :34:23
  assign o_VSTIP = o_VSTIP_r;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/SstcInterruptGen.scala:6:7, :35:23
endmodule
