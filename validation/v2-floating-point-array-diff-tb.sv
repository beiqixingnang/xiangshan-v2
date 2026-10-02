module array_locked_diff_tb;
  reg clock = 0;
  reg [64:0] a = 0, b = 0;
  reg en0 = 0, en1 = 0;
  wire [129:0] ref_result, dut_result;
  integer i, mode;
  REF_ArrayMulDataModule refmod(.clock(clock), .io_a(a), .io_b(b), .io_regEnables_0(en0), .io_regEnables_1(en1), .io_result(ref_result));
  ArrayMulDut dut(.clock(clock), .io_a(a), .io_b(b), .io_regEnables_0(en0), .io_regEnables_1(en1), .io_result(dut_result));
  task tick;
    begin #5 clock = 1; #1; clock = 0; #4; end
  endtask
  task multiply(input [64:0] av, input [64:0] bv);
    begin
      a = av; b = bv; en0 = 1; en1 = 0; tick;
      en0 = 0; en1 = 1; tick;
      en1 = 0; #1;
      if (ref_result !== dut_result) begin
        $display("MISMATCH a=%h b=%h ref=%h dut=%h", av, bv, ref_result, dut_result);
        $fatal(1);
      end
    end
  endtask
  initial begin
    multiply(65'h1,65'h1);
    multiply(65'h3,65'h5);
    multiply(65'h1ffffffffffffffff,65'h1);
    multiply(65'h10000000000000000,65'h2);
    multiply(65'h1ffffffffffffffff,65'h1ffffffffffffffff);
    for (mode = 0; mode < 4; mode = mode + 1)
      for (i = 0; i < 16; i = i + 1)
        multiply({$random, $random}, {$random, $random});
    $display("ARRAY_LOCKED_DIFF_PASS");
    $finish;
  end
endmodule
