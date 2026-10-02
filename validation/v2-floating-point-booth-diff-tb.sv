module booth_diff_tb;
  reg [52:0] a, b;
  reg is64, is32;
  wire [106:0] ref_pp [0:26];
  wire [106:0] dut_pp [0:26];
  integer i, j, mode64, mode32, seed;
  BoothEncoderF64F32F16 refmod(
    .io_in_a(a), .io_in_b(b), .io_is_fp64(is64), .io_is_fp32(is32),
    .io_out_pp_0(ref_pp[0]), .io_out_pp_1(ref_pp[1]), .io_out_pp_2(ref_pp[2]),
    .io_out_pp_3(ref_pp[3]), .io_out_pp_4(ref_pp[4]), .io_out_pp_5(ref_pp[5]),
    .io_out_pp_6(ref_pp[6]), .io_out_pp_7(ref_pp[7]), .io_out_pp_8(ref_pp[8]),
    .io_out_pp_9(ref_pp[9]), .io_out_pp_10(ref_pp[10]), .io_out_pp_11(ref_pp[11]),
    .io_out_pp_12(ref_pp[12]), .io_out_pp_13(ref_pp[13]), .io_out_pp_14(ref_pp[14]),
    .io_out_pp_15(ref_pp[15]), .io_out_pp_16(ref_pp[16]), .io_out_pp_17(ref_pp[17]),
    .io_out_pp_18(ref_pp[18]), .io_out_pp_19(ref_pp[19]), .io_out_pp_20(ref_pp[20]),
    .io_out_pp_21(ref_pp[21]), .io_out_pp_22(ref_pp[22]), .io_out_pp_23(ref_pp[23]),
    .io_out_pp_24(ref_pp[24]), .io_out_pp_25(ref_pp[25]), .io_out_pp_26(ref_pp[26]));
  BoothDut dut(
    .io_in_a(a), .io_in_b(b), .io_is_fp64(is64), .io_is_fp32(is32),
    .io_out_pp_0(dut_pp[0]), .io_out_pp_1(dut_pp[1]), .io_out_pp_2(dut_pp[2]),
    .io_out_pp_3(dut_pp[3]), .io_out_pp_4(dut_pp[4]), .io_out_pp_5(dut_pp[5]),
    .io_out_pp_6(dut_pp[6]), .io_out_pp_7(dut_pp[7]), .io_out_pp_8(dut_pp[8]),
    .io_out_pp_9(dut_pp[9]), .io_out_pp_10(dut_pp[10]), .io_out_pp_11(dut_pp[11]),
    .io_out_pp_12(dut_pp[12]), .io_out_pp_13(dut_pp[13]), .io_out_pp_14(dut_pp[14]),
    .io_out_pp_15(dut_pp[15]), .io_out_pp_16(dut_pp[16]), .io_out_pp_17(dut_pp[17]),
    .io_out_pp_18(dut_pp[18]), .io_out_pp_19(dut_pp[19]), .io_out_pp_20(dut_pp[20]),
    .io_out_pp_21(dut_pp[21]), .io_out_pp_22(dut_pp[22]), .io_out_pp_23(dut_pp[23]),
    .io_out_pp_24(dut_pp[24]), .io_out_pp_25(dut_pp[25]), .io_out_pp_26(dut_pp[26]));
  task check;
    begin
      #1;
      for (j = 0; j < 27; j = j + 1)
        if (ref_pp[j] !== dut_pp[j]) begin
          $display("MISMATCH mode=%b%b a=%h b=%h i=%0d ref=%h dut=%h", is64, is32, a, b, j, ref_pp[j], dut_pp[j]);
          $fatal(1);
        end
    end
  endtask
  initial begin
    seed = 32'h4f1a2b3c;
    for (mode64 = 0; mode64 <= 1; mode64 = mode64 + 1)
      for (mode32 = 0; mode32 <= 1; mode32 = mode32 + 1) begin
        is64 = mode64;
        is32 = mode32;
        for (i = 0; i < 64; i = i + 1) begin
          a = {$random(seed), $random(seed)};
          b = {$random(seed), $random(seed)};
          check;
        end
      end
    $display("BOOTH_DIFF_PASS");
    $finish(0);
  end
endmodule
