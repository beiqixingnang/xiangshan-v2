module SRAMTemplate_116(	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
  input         clock,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
                reset,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
                io_r_req_valid,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input  [7:0]  io_r_req_bits_setIdx,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  output [42:0] io_r_resp_data_0,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
                io_r_resp_data_1,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input         io_w_req_valid,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input  [7:0]  io_w_req_bits_setIdx,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input  [42:0] io_w_req_bits_data_0,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
                io_w_req_bits_data_1,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input  [1:0]  io_w_req_bits_waymask,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input         io_broadcast_ram_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
                io_broadcast_ram_bypass,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
                io_broadcast_ram_bp_clken,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
                io_broadcast_ram_aux_clk,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
                io_broadcast_ram_aux_ckbp,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
                io_broadcast_ram_mcp_hold,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input  [63:0] io_broadcast_ram_ctl,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input         io_broadcast_cgen,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:214:14
  input  [8:0]  boreChildrenBd_bore_addr,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_addr_rd,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [85:0] boreChildrenBd_bore_wdata,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [1:0]  boreChildrenBd_bore_wmask,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         boreChildrenBd_bore_re,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_we,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  output [85:0] boreChildrenBd_bore_rdata,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input         boreChildrenBd_bore_ack,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
                boreChildrenBd_bore_selectedOH,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
  input  [5:0]  boreChildrenBd_bore_array	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/Mbist.scala:116:46
);

  wire        io_r_req_ready;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:496:35
  wire [85:0] _array_RW0_rdata;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:233:25
  wire        _rcg_out_clock;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:249:43
  wire [8:0]  mbistBd_addr = boreChildrenBd_bore_addr;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire [8:0]  mbistBd_addr_rd = boreChildrenBd_bore_addr_rd;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire [85:0] mbistBd_wdata = boreChildrenBd_bore_wdata;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire [1:0]  mbistBd_wmask = boreChildrenBd_bore_wmask;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire        mbistBd_re = boreChildrenBd_bore_re;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire        mbistBd_we = boreChildrenBd_bore_we;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire        mbistBd_ack = boreChildrenBd_bore_ack;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire        mbistBd_selectedOH = boreChildrenBd_bore_selectedOH;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire [5:0]  mbistBd_array = boreChildrenBd_bore_array;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire        wckEn = mbistBd_ack ? mbistBd_we : io_w_req_valid;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:342:40, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  wire        rckEn = mbistBd_ack ? mbistBd_re : io_r_req_ready & io_r_req_valid;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:343:40, :496:35, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21, src/main/scala/chisel3/util/Decoupled.scala:51:35
  wire        finalRamWen = wckEn & ~io_broadcast_ram_hold;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:342:40, :371:{36,39}
  reg         respReg;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:376:32
  reg  [85:0] rdataReg;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:489:35
  wire [85:0] mbistBd_rdata = rdataReg;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:489:35, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
  assign io_r_req_ready = ~io_w_req_valid;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:496:35
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
    if (reset)	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
      respReg <= 1'h0;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:376:32, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:165:23
    else	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
      respReg <= rckEn;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:343:40, :376:32
  end // always @(posedge, posedge)
  always @(posedge clock) begin	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
    if (respReg)	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:376:32
      rdataReg <= _array_RW0_rdata;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:489:35, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:233:25
  end // always @(posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
      automatic logic [31:0] _RANDOM[0:9];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
        for (logic [3:0] i = 4'h0; i < 4'hA; i += 4'h1) begin
          _RANDOM[i] = `RANDOM;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
        end	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
        respReg = _RANDOM[4'h3][9];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7, :376:32
        rdataReg = {_RANDOM[4'h7][31:10], _RANDOM[4'h8], _RANDOM[4'h9]};	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7, :489:35
      `endif // RANDOMIZE_REG_INIT
      if (reset)	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
        respReg = 1'h0;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:376:32, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:165:23
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  MbistClockGateCell rcg (	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:249:43
    .clock         (clock),
    .mbist_writeen (wckEn),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:342:40
    .mbist_readen  (rckEn),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:343:40
    .mbist_req     (mbistBd_ack),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
    .E             (rckEn | wckEn),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:342:40, :343:40, :389:21
    .dft_cgen      (io_broadcast_cgen),
    .out_clock     (_rcg_out_clock)
  );
  sram_array_1p256x86m43s1h0l1b_dcsh_tag array (	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:233:25
    .mbist_dft_ram_bypass   (io_broadcast_ram_bypass),
    .mbist_dft_ram_bp_clken (io_broadcast_ram_bp_clken),
    .RW0_clk                (_rcg_out_clock),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:249:43
    .RW0_addr
      (mbistBd_ack
         ? mbistBd_addr_rd[7:0]
         : finalRamWen ? io_w_req_bits_setIdx : io_r_req_bits_setIdx),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:344:42, :346:8, :371:36, :372:21, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:180:25, :193:25
    .RW0_en                 (finalRamWen | rckEn),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:343:40, :371:36, :372:21, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:181:23, :194:23
    .RW0_wmode              (finalRamWen),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:371:36
    .RW0_wmask
      (mbistBd_ack ? {2{mbistBd_selectedOH}} & mbistBd_wmask : io_w_req_bits_waymask),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:340:42, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:64:24, :65:15, :160:21
    .RW0_wdata
      (mbistBd_ack ? mbistBd_wdata : {io_w_req_bits_data_1, io_w_req_bits_data_0}),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:295:69, :341:42, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
    .RW0_rdata              (_array_RW0_rdata)
  );
  assign io_r_resp_data_0 = _array_RW0_rdata[42:0];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7, :413:44, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:233:25
  assign io_r_resp_data_1 = _array_RW0_rdata[85:43];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7, :413:44, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:233:25
  assign boreChildrenBd_bore_rdata = mbistBd_rdata;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SRAMTemplate.scala:203:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramHelper.scala:160:21
endmodule
