module array_256x86(	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
  input  [7:0]  RW0_addr,
  input         RW0_en,
                RW0_clk,
                RW0_wmode,
  input  [85:0] RW0_wdata,
  output [85:0] RW0_rdata,
  input  [1:0]  RW0_wmask
);

  reg [85:0] Memory[0:255];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
  reg [7:0]  _RW0_raddr_d0;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
  reg        _RW0_ren_d0;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
  reg        _RW0_rmode_d0;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
  always @(posedge RW0_clk) begin	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    _RW0_raddr_d0 <= RW0_addr;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    _RW0_ren_d0 <= RW0_en;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    _RW0_rmode_d0 <= RW0_wmode;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    if (RW0_en & RW0_wmask[0] & RW0_wmode)	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
      Memory[RW0_addr][32'h0 +: 43] <= RW0_wdata[42:0];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    if (RW0_en & RW0_wmask[1] & RW0_wmode)	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
      Memory[RW0_addr][32'h2B +: 43] <= RW0_wdata[85:43];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
  end // always @(posedge)
  `ifdef ENABLE_INITIAL_MEM_	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
      reg [31:0] _RANDOM;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    `endif // RANDOMIZE_REG_INIT
    reg [95:0] _RANDOM_MEM;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    initial begin	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
      `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
      `ifdef RANDOMIZE_MEM_INIT	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
        for (logic [8:0] i = 9'h0; i < 9'h100; i += 9'h1) begin
          for (logic [6:0] j = 7'h0; j < 7'h60; j += 7'h20) begin
            _RANDOM_MEM[j +: 32] = `RANDOM;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
          end	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
          Memory[i[7:0]] = _RANDOM_MEM[85:0];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
        end	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
      `endif // RANDOMIZE_MEM_INIT
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
        _RANDOM = {`RANDOM};	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
        _RW0_raddr_d0 = _RANDOM[7:0];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
        _RW0_ren_d0 = _RANDOM[8];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
        _RW0_rmode_d0 = _RANDOM[9];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
      `endif // RANDOMIZE_REG_INIT
    end // initial
  `endif // ENABLE_INITIAL_MEM_
  assign RW0_rdata = _RW0_ren_d0 & ~_RW0_rmode_d0 ? Memory[_RW0_raddr_d0] : 86'bx;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
endmodule
