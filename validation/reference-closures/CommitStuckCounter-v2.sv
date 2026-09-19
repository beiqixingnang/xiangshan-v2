module CommitStuckCounter(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
  input  clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
         reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
         io_stuck,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:6:14
         io_runtimeEnable,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:6:14
  output io_overflow	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:6:14
);

  reg [20:0] count;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:14:30
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
    if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
      count <= 21'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:14:30
    else if (io_runtimeEnable & io_stuck)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:17:40, :18:11, :20:11
      count <= count + 21'h1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:14:30, :20:20
    else	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:17:40, :18:11, :20:11
      count <= 21'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:14:30
  end // always @(posedge, posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
      automatic logic [31:0] _RANDOM[0:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
        _RANDOM[/*Zero width*/ 1'b0] = `RANDOM;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
        count = _RANDOM[/*Zero width*/ 1'b0][20:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7, :14:30
      `endif // RANDOMIZE_REG_INIT
      if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
        count = 21'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:14:30
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  assign io_overflow = &count;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/rob/CommitStuckCounter.scala:5:7, :14:30, :24:24
endmodule

