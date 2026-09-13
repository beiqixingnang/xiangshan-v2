// Scalar observation wrapper around the locked V2 _25 specialization.
// This wrapper only packs/unpacks payload fields; the child bytes are kept
// verbatim in NewPipelineConnectPipe_25-v2.sv.
module NewPipelineConnectPipe(
  input clock,
  input reset,
  input io_in_valid,
  input [63:0] io_in_bits,
  output io_in_ready,
  input io_out_ready,
  output io_out_valid,
  output [63:0] io_out_bits,
  input io_rightOutFire,
  input io_isFlush,
  input io_isOlder
);
  wire [34:0] in_fuType = {19'b0, io_in_bits[15:0]};
  wire [8:0] in_fuOpType = io_in_bits[8:0];
  wire [63:0] in_src0 = io_in_bits;
  wire [63:0] in_src1 = io_in_bits ^ 64'h5a5a5a5a5a5a5a5a;
  wire in_robFlag = io_in_bits[0];
  wire [7:0] in_robValue = io_in_bits[15:8];
  wire [7:0] in_pdest = io_in_bits[23:16];
  wire in_rfWen = io_in_bits[24];
  wire out_robFlag;
  wire [7:0] out_robValue;
  wire [7:0] out_pdest;
  wire out_rfWen;
  wire [34:0] out_fuType;
  wire [8:0] out_fuOpType;
  wire [63:0] out_src0;
  wire [63:0] out_src1;
  // The locked specialization has isOlder optimized away; this parent uses
  // the V2 default false.  The wrapper still exposes the canonical signal so
  // a caller can document that boundary explicitly.
  wire unused_isOlder = io_isOlder;
  NewPipelineConnectPipe_25 core (
    .clock(clock), .reset(reset), .io_in_ready(io_in_ready),
    .io_in_valid(io_in_valid), .io_in_bits_fuType(in_fuType),
    .io_in_bits_fuOpType(in_fuOpType), .io_in_bits_src_0(in_src0),
    .io_in_bits_robIdx_flag(in_robFlag), .io_in_bits_robIdx_value(in_robValue),
    .io_in_bits_sqIdx_flag(1'b0), .io_in_bits_sqIdx_value(6'b0),
    .io_out_ready(io_out_ready), .io_out_valid(io_out_valid),
    .io_out_bits_fuType(out_fuType), .io_out_bits_fuOpType(out_fuOpType),
    .io_out_bits_src_0(out_src0), .io_out_bits_robIdx_flag(out_robFlag),
    .io_out_bits_robIdx_value(out_robValue), .io_out_bits_sqIdx_flag(),
    .io_out_bits_sqIdx_value(), .io_rightOutFire(io_rightOutFire),
    .io_isFlush(io_isFlush)
  );
  assign io_out_bits = out_src0;
endmodule
