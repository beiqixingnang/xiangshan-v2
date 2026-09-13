module TagArray(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:100:7
  input         clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:100:7
                reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:100:7
  output        io_read_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  input         io_read_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  input  [7:0]  io_read_bits_idx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  output [42:0] io_resp_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
                io_resp_1,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
                io_resp_2,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
                io_resp_3,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  input         io_write_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  input  [7:0]  io_write_bits_idx,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  input  [3:0]  io_write_bits_way_en,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  input  [35:0] io_write_bits_tag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
  input  [6:0]  io_write_bits_ecc,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:101:14
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
  input  [8:0]  boreChildrenBd_bore_1_addr,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_1_addr_rd,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [85:0] boreChildrenBd_bore_1_wdata,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [1:0]  boreChildrenBd_bore_1_wmask,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         boreChildrenBd_bore_1_re,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_1_we,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  output [85:0] boreChildrenBd_bore_1_rdata,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         boreChildrenBd_bore_1_ack,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_1_selectedOH,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [5:0]  boreChildrenBd_bore_1_array,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         sigFromSrams_bore_ram_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_bypass,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_bp_clken,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_aux_clk,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_aux_ckbp,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_ram_mcp_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_cgen,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_1_ram_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_1_ram_bypass,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_1_ram_bp_clken,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_1_ram_aux_clk,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_1_ram_aux_ckbp,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_1_ram_mcp_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
                sigFromSrams_bore_1_cgen	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:122:23
);

  TagSRAMBank tag_arrays_0 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:107:67
    .clock                          (clock),
    .reset                          (reset),
    .io_read_ready                  (/* unused */),
    .io_read_valid                  (io_read_valid),
    .io_read_bits_idx               (io_read_bits_idx),
    .io_resp_0                      (io_resp_0),
    .io_resp_1                      (io_resp_1),
    .io_write_valid                 (io_write_valid),
    .io_write_bits_idx              (io_write_bits_idx),
    .io_write_bits_tag              (io_write_bits_tag),
    .io_write_bits_ecc              (io_write_bits_ecc),
    .io_write_bits_way_en           (io_write_bits_way_en[1:0]),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:112:59
    .boreChildrenBd_bore_addr       (boreChildrenBd_bore_addr),
    .boreChildrenBd_bore_addr_rd    (boreChildrenBd_bore_addr_rd),
    .boreChildrenBd_bore_wdata      (boreChildrenBd_bore_wdata),
    .boreChildrenBd_bore_wmask      (boreChildrenBd_bore_wmask),
    .boreChildrenBd_bore_re         (boreChildrenBd_bore_re),
    .boreChildrenBd_bore_we         (boreChildrenBd_bore_we),
    .boreChildrenBd_bore_rdata      (boreChildrenBd_bore_rdata),
    .boreChildrenBd_bore_ack        (boreChildrenBd_bore_ack),
    .boreChildrenBd_bore_selectedOH (boreChildrenBd_bore_selectedOH),
    .boreChildrenBd_bore_array      (boreChildrenBd_bore_array),
    .sigFromSrams_bore_ram_hold     (sigFromSrams_bore_ram_hold),
    .sigFromSrams_bore_ram_bypass   (sigFromSrams_bore_ram_bypass),
    .sigFromSrams_bore_ram_bp_clken (sigFromSrams_bore_ram_bp_clken),
    .sigFromSrams_bore_ram_aux_clk  (sigFromSrams_bore_ram_aux_clk),
    .sigFromSrams_bore_ram_aux_ckbp (sigFromSrams_bore_ram_aux_ckbp),
    .sigFromSrams_bore_ram_mcp_hold (sigFromSrams_bore_ram_mcp_hold),
    .sigFromSrams_bore_cgen         (sigFromSrams_bore_cgen)
  );
  TagSRAMBank tag_arrays_1 (	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:107:67
    .clock                          (clock),
    .reset                          (reset),
    .io_read_ready                  (io_read_ready),
    .io_read_valid                  (io_read_valid),
    .io_read_bits_idx               (io_read_bits_idx),
    .io_resp_0                      (io_resp_2),
    .io_resp_1                      (io_resp_3),
    .io_write_valid                 (io_write_valid),
    .io_write_bits_idx              (io_write_bits_idx),
    .io_write_bits_tag              (io_write_bits_tag),
    .io_write_bits_ecc              (io_write_bits_ecc),
    .io_write_bits_way_en           (io_write_bits_way_en[3:2]),	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala:112:59
    .boreChildrenBd_bore_addr       (boreChildrenBd_bore_1_addr),
    .boreChildrenBd_bore_addr_rd    (boreChildrenBd_bore_1_addr_rd),
    .boreChildrenBd_bore_wdata      (boreChildrenBd_bore_1_wdata),
    .boreChildrenBd_bore_wmask      (boreChildrenBd_bore_1_wmask),
    .boreChildrenBd_bore_re         (boreChildrenBd_bore_1_re),
    .boreChildrenBd_bore_we         (boreChildrenBd_bore_1_we),
    .boreChildrenBd_bore_rdata      (boreChildrenBd_bore_1_rdata),
    .boreChildrenBd_bore_ack        (boreChildrenBd_bore_1_ack),
    .boreChildrenBd_bore_selectedOH (boreChildrenBd_bore_1_selectedOH),
    .boreChildrenBd_bore_array      (boreChildrenBd_bore_1_array),
    .sigFromSrams_bore_ram_hold     (sigFromSrams_bore_1_ram_hold),
    .sigFromSrams_bore_ram_bypass   (sigFromSrams_bore_1_ram_bypass),
    .sigFromSrams_bore_ram_bp_clken (sigFromSrams_bore_1_ram_bp_clken),
    .sigFromSrams_bore_ram_aux_clk  (sigFromSrams_bore_1_ram_aux_clk),
    .sigFromSrams_bore_ram_aux_ckbp (sigFromSrams_bore_1_ram_aux_ckbp),
    .sigFromSrams_bore_ram_mcp_hold (sigFromSrams_bore_1_ram_mcp_hold),
    .sigFromSrams_bore_cgen         (sigFromSrams_bore_1_cgen)
  );
endmodule
