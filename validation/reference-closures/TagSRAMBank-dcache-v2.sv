module TagSRAMBank(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
  input         clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
                reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
  output        io_read_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input         io_read_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input  [7:0]  io_read_bits_idx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  output [42:0] io_resp_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
                io_resp_1,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input         io_write_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input  [7:0]  io_write_bits_idx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input  [35:0] io_write_bits_tag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input  [6:0]  io_write_bits_ecc,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input  [1:0]  io_write_bits_way_en,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:56:14
  input  [8:0]  boreChildrenBd_bore_addr,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_addr_rd,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [85:0] boreChildrenBd_bore_wdata,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [1:0]  boreChildrenBd_bore_wmask,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         boreChildrenBd_bore_re,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_we,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  output [85:0] boreChildrenBd_bore_rdata,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         boreChildrenBd_bore_ack,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_selectedOH,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [5:0]  boreChildrenBd_bore_array,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         sigFromSrams_bore_ram_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_bypass,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_bp_clken,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_aux_clk,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_aux_ckbp,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_mcp_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_cgen	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
);

  reg  [8:0]  rst_cnt;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24
  wire [42:0] wdata = rst_cnt[8] ? {io_write_bits_ecc, io_write_bits_tag} : 43'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:38:10, :66:24, :67:21, :70:18
  wire        wen = ~(rst_cnt[8]) | io_write_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24, :67:21, :81:17
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
    if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
      rst_cnt <= 9'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24
    else if (rst_cnt[8]) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24, :67:21
    end
    else	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:67:21
      rst_cnt <= rst_cnt + 9'h1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24, :74:24
  end // always @(posedge, posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
      automatic logic [31:0] _RANDOM[0:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
        _RANDOM[/*Zero width*/ 1'b0] = `RANDOM;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
        rst_cnt = _RANDOM[/*Zero width*/ 1'b0][8:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7, :66:24
      `endif // RANDOMIZE_REG_INIT
      if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
        rst_cnt = 9'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  SRAMTemplate_116 tag_array (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:77:25
    .clock                          (clock),
    .reset                          (reset),
    .io_r_req_valid                 (~wen & io_read_valid),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:81:17, :92:20, src/main/scala/chisel3/util/Decoupled.scala:51:35
    .io_r_req_bits_setIdx           (io_read_bits_idx),
    .io_r_resp_data_0               (io_resp_0),
    .io_r_resp_data_1               (io_resp_1),
    .io_w_req_valid                 (wen),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:81:17
    .io_w_req_bits_setIdx           (rst_cnt[8] ? io_write_bits_idx : rst_cnt[7:0]),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24, :67:21, :69:18
    .io_w_req_bits_data_0           (wdata),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:70:18
    .io_w_req_bits_data_1           (wdata),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:70:18
    .io_w_req_bits_waymask          (rst_cnt[8] ? io_write_bits_way_en : 2'h3),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:66:24, :67:21, :71:18
    .io_broadcast_ram_hold          (sigFromSrams_bore_ram_hold),
    .io_broadcast_ram_bypass        (sigFromSrams_bore_ram_bypass),
    .io_broadcast_ram_bp_clken      (sigFromSrams_bore_ram_bp_clken),
    .io_broadcast_ram_aux_clk       (sigFromSrams_bore_ram_aux_clk),
    .io_broadcast_ram_aux_ckbp      (sigFromSrams_bore_ram_aux_ckbp),
    .io_broadcast_ram_mcp_hold      (sigFromSrams_bore_ram_mcp_hold),
    .io_broadcast_ram_ctl           (64'h0),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:77:25, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
    .io_broadcast_cgen              (sigFromSrams_bore_cgen),
    .boreChildrenBd_bore_addr       (boreChildrenBd_bore_addr),
    .boreChildrenBd_bore_addr_rd    (boreChildrenBd_bore_addr_rd),
    .boreChildrenBd_bore_wdata      (boreChildrenBd_bore_wdata),
    .boreChildrenBd_bore_wmask      (boreChildrenBd_bore_wmask),
    .boreChildrenBd_bore_re         (boreChildrenBd_bore_re),
    .boreChildrenBd_bore_we         (boreChildrenBd_bore_we),
    .boreChildrenBd_bore_rdata      (boreChildrenBd_bore_rdata),
    .boreChildrenBd_bore_ack        (boreChildrenBd_bore_ack),
    .boreChildrenBd_bore_selectedOH (boreChildrenBd_bore_selectedOH),
    .boreChildrenBd_bore_array      (boreChildrenBd_bore_array)
  );
  assign io_read_ready = ~wen;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:55:7, :81:17, :92:20
endmodule
