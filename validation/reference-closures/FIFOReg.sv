module FIFOReg(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
  input        clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
               reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
  output       io_enq_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
  input        io_enq_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
  input  [3:0] io_enq_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
  input        io_deq_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
  output       io_deq_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
  output [3:0] io_deq_bits,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
  input        io_flush	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
);

  reg  [3:0]       regFiles_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_2;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_3;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_4;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_5;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_6;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_7;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_8;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg  [3:0]       regFiles_9;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
  reg              enq_ptr_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33
  reg  [3:0]       enq_ptr_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33
  reg              deq_ptr_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:53:33
  reg  [3:0]       deq_ptr_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:53:33
  wire             full = enq_ptr_value == deq_ptr_value & (enq_ptr_flag ^ deq_ptr_flag);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33, :53:33, :56:{38,57,74}
  wire [15:0][3:0] _GEN =
    {{regFiles_0},
     {regFiles_0},
     {regFiles_0},
     {regFiles_0},
     {regFiles_0},
     {regFiles_0},
     {regFiles_9},
     {regFiles_8},
     {regFiles_7},
     {regFiles_6},
     {regFiles_5},
     {regFiles_4},
     {regFiles_3},
     {regFiles_2},
     {regFiles_1},
     {regFiles_0}};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :74:15
  wire             io_deq_valid_0 =
    {enq_ptr_flag, enq_ptr_value} != {deq_ptr_flag, deq_ptr_value};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33, :53:33, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:61:{40,47,56}
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
    if (reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
      regFiles_0 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_1 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_2 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_3 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_4 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_5 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_6 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_7 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_8 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      regFiles_9 <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
      enq_ptr_flag <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :52:33
      enq_ptr_value <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33, :72:29
      deq_ptr_flag <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :53:33
      deq_ptr_value <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:53:33, :72:29
    end
    else begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
      automatic logic       _GEN_0;	// src/main/scala/chisel3/util/Decoupled.scala:51:35
      automatic logic [4:0] enq_ptr_new_value;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34
      automatic logic [5:0] _enq_ptr_diff_T_4;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:42:50
      automatic logic       enq_ptr_reverse_flag;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:43:31
      automatic logic       _GEN_1;	// src/main/scala/chisel3/util/Decoupled.scala:51:35
      automatic logic [4:0] deq_ptr_new_value;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34
      automatic logic [5:0] _deq_ptr_diff_T_4;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:42:50
      automatic logic       deq_ptr_reverse_flag;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:43:31
      _GEN_0 = ~full & io_enq_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:56:57, :77:19, src/main/scala/chisel3/util/Decoupled.scala:51:35
      enq_ptr_new_value = {1'h0, enq_ptr_value} + 5'h1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :52:33, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34
      _enq_ptr_diff_T_4 = {1'h0, enq_ptr_new_value} - 6'hA;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34, :42:50
      enq_ptr_reverse_flag = $signed(_enq_ptr_diff_T_4) > -6'sh1;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:42:50, :43:31
      _GEN_1 = io_deq_ready & io_deq_valid_0;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:61:47, src/main/scala/chisel3/util/Decoupled.scala:51:35
      deq_ptr_new_value = {1'h0, deq_ptr_value} + 5'h1;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :53:33, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34
      _deq_ptr_diff_T_4 = {1'h0, deq_ptr_new_value} - 6'hA;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34, :42:50
      deq_ptr_reverse_flag = $signed(_deq_ptr_diff_T_4) > -6'sh1;	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:42:50, :43:31
      if (_GEN_0 & enq_ptr_value == 4'h0)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_0 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h1)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_1 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h2)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_2 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h3)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_3 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h4)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_4 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h5)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_5 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h6)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_6 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h7)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_7 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h8)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_8 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      if (_GEN_0 & enq_ptr_value == 4'h9)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :52:33, :71:21, :72:29, src/main/scala/chisel3/util/Decoupled.scala:51:35
        regFiles_9 <= io_enq_bits;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33
      enq_ptr_flag <= ~io_flush & (_GEN_0 & enq_ptr_reverse_flag ^ enq_ptr_flag);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33, :58:21, :59:13, :64:15, :66:19, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:43:31, src/main/scala/chisel3/util/Decoupled.scala:51:35
      if (io_flush) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
        enq_ptr_value <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33, :72:29
        deq_ptr_value <= 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:53:33, :72:29
      end
      else begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:38:28
        if (_GEN_0)	// src/main/scala/chisel3/util/Decoupled.scala:51:35
          enq_ptr_value <=
            enq_ptr_reverse_flag ? _enq_ptr_diff_T_4[3:0] : enq_ptr_new_value[3:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34, :42:50, :43:31, :45:27
        if (_GEN_1)	// src/main/scala/chisel3/util/Decoupled.scala:51:35
          deq_ptr_value <=
            deq_ptr_reverse_flag ? _deq_ptr_diff_T_4[3:0] : deq_ptr_new_value[3:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:53:33, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:41:34, :42:50, :43:31, :45:27
      end
      deq_ptr_flag <= ~io_flush & (_GEN_1 & deq_ptr_reverse_flag ^ deq_ptr_flag);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:53:33, :58:21, :61:21, :62:13, :64:15, :66:19, :68:19, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:43:31, src/main/scala/chisel3/util/Decoupled.scala:51:35
    end
  end // always @(posedge, posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
      automatic logic [31:0] _RANDOM[0:1];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
        for (logic [1:0] i = 2'h0; i < 2'h2; i += 2'h1) begin
          _RANDOM[i[0]] = `RANDOM;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
        end	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
        regFiles_0 = _RANDOM[1'h0][3:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_1 = _RANDOM[1'h0][7:4];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_2 = _RANDOM[1'h0][11:8];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_3 = _RANDOM[1'h0][15:12];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_4 = _RANDOM[1'h0][19:16];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_5 = _RANDOM[1'h0][23:20];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_6 = _RANDOM[1'h0][27:24];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_7 = _RANDOM[1'h0][31:28];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_8 = _RANDOM[1'h1][3:0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        regFiles_9 = _RANDOM[1'h1][7:4];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33
        enq_ptr_flag = _RANDOM[1'h1][8];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33, :52:33
        enq_ptr_value = _RANDOM[1'h1][12:9];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33, :52:33
        deq_ptr_flag = _RANDOM[1'h1][13];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33, :53:33
        deq_ptr_value = _RANDOM[1'h1][17:14];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :51:33, :53:33
      `endif // RANDOMIZE_REG_INIT
      if (reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
        regFiles_0 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_1 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_2 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_3 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_4 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_5 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_6 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_7 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_8 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        regFiles_9 = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:51:33, :72:29
        enq_ptr_flag = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :52:33
        enq_ptr_value = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:52:33, :72:29
        deq_ptr_flag = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :53:33
        deq_ptr_value = 4'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:53:33, :72:29
      end
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  assign io_enq_ready = ~full;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :56:57, :77:19
  assign io_deq_valid = io_deq_valid_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, home/lishuo/xs-v2-local/utility/src/main/scala/utility/CircularQueuePtr.scala:61:47
  assign io_deq_bits = _GEN[deq_ptr_value];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/frontend/icache/FIFO.scala:30:7, :53:33, :74:15
endmodule
