module sram_array_1p256x86m43s1h0l1b_dcsh_tag(	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:99:2
  input         mbist_dft_ram_bypass,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:54:43
                mbist_dft_ram_bp_clken,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:54:43
                RW0_clk,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:60:12
  input  [7:0]  RW0_addr,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:60:12
  input         RW0_en,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:60:12
                RW0_wmode,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:60:12
  input  [1:0]  RW0_wmask,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:60:12
  input  [85:0] RW0_wdata,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:60:12
  output [85:0] RW0_rdata	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:60:12
);

  wire array_RW0_rdata_MPORT_wmask_1;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:111:37
  wire array_RW0_rdata_MPORT_wmask_0;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:111:37
  assign array_RW0_rdata_MPORT_wmask_0 = RW0_wmode & RW0_wmask[0];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:111:37, :114:21
  assign array_RW0_rdata_MPORT_wmask_1 = RW0_wmode & RW0_wmask[1];	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:111:37, :114:21
  array_256x86 array_ext (	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28
    .RW0_addr  (RW0_addr),
    .RW0_en    (RW0_en),
    .RW0_clk   (RW0_clk),
    .RW0_wmode (RW0_en & RW0_wmode & (|RW0_wmask)),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28, :111:37
    .RW0_wdata (RW0_wdata),
    .RW0_rdata (RW0_rdata),
    .RW0_wmask ({array_RW0_rdata_MPORT_wmask_1, array_RW0_rdata_MPORT_wmask_0})	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/sram/SramProto.scala:110:28, :111:37
  );
endmodule
