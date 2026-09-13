module NewPipelineConnectPipe_25(	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
  input         clock,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
                reset,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
  output        io_in_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input         io_in_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input  [34:0] io_in_bits_fuType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input  [8:0]  io_in_bits_fuOpType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input  [63:0] io_in_bits_src_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input         io_in_bits_robIdx_flag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input  [7:0]  io_in_bits_robIdx_value,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input         io_in_bits_sqIdx_flag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input  [5:0]  io_in_bits_sqIdx_value,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input         io_out_ready,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output        io_out_valid,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output [34:0] io_out_bits_fuType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output [8:0]  io_out_bits_fuOpType,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output [63:0] io_out_bits_src_0,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output        io_out_bits_robIdx_flag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output [7:0]  io_out_bits_robIdx_value,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output        io_out_bits_sqIdx_flag,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  output [5:0]  io_out_bits_sqIdx_value,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
  input         io_rightOutFire,	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
                io_isFlush	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14
);

  reg         valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:42:24
  wire        io_in_ready_0 = io_out_ready | ~valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:42:24, :44:{31,34}
  wire        _data_T = io_in_ready_0 & io_in_valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:44:31, src/main/scala/chisel3/util/Decoupled.scala:51:35
  reg  [34:0] data_fuType;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
  reg  [8:0]  data_fuOpType;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
  reg  [63:0] data_src_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
  reg         data_robIdx_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
  reg  [7:0]  data_robIdx_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
  reg         data_sqIdx_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
  reg  [5:0]  data_sqIdx_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
  always @(posedge clock or posedge reset) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
    if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
      valid <= 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14, :42:24
    else	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
      valid <= ~io_isFlush & (_data_T | ~io_rightOutFire & valid);	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:42:24, :47:{25,33}, :48:{22,30}, :49:{20,28}, src/main/scala/chisel3/util/Decoupled.scala:51:35
  end // always @(posedge, posedge)
  always @(posedge clock) begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
    if (_data_T) begin	// src/main/scala/chisel3/util/Decoupled.scala:51:35
      data_fuType <= io_in_bits_fuType;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
      data_fuOpType <= io_in_bits_fuOpType;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
      data_src_0 <= io_in_bits_src_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
      data_robIdx_flag <= io_in_bits_robIdx_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
      data_robIdx_value <= io_in_bits_robIdx_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
      data_sqIdx_flag <= io_in_bits_sqIdx_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
      data_sqIdx_value <= io_in_bits_sqIdx_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:45:25
    end
  end // always @(posedge)
  `ifdef ENABLE_INITIAL_REG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
    `ifdef FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
      `FIRRTL_BEFORE_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
      automatic logic [31:0] _RANDOM[0:6];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
      `ifdef INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
        `INIT_RANDOM_PROLOG_	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
      `endif // INIT_RANDOM_PROLOG_
      `ifdef RANDOMIZE_REG_INIT	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
        for (logic [2:0] i = 3'h0; i < 3'h7; i += 3'h1) begin
          _RANDOM[i] = `RANDOM;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
        end	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
        valid = _RANDOM[3'h0][0];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :42:24
        data_fuType = {_RANDOM[3'h0][31:1], _RANDOM[3'h1][3:0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :42:24, :45:25
        data_fuOpType = _RANDOM[3'h1][12:4];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
        data_src_0 = {_RANDOM[3'h1][31:13], _RANDOM[3'h2], _RANDOM[3'h3][12:0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
        data_robIdx_flag = _RANDOM[3'h5][13];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
        data_robIdx_value = _RANDOM[3'h5][21:14];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
        data_sqIdx_flag = _RANDOM[3'h5][27];	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
        data_sqIdx_value = {_RANDOM[3'h5][31:28], _RANDOM[3'h6][1:0]};	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
      `endif // RANDOMIZE_REG_INIT
      if (reset)	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
        valid = 1'h0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:23:14, :42:24
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
      `FIRRTL_AFTER_INITIAL	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  assign io_in_ready = io_in_ready_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :44:31
  assign io_out_valid = valid;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :42:24
  assign io_out_bits_fuType = data_fuType;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
  assign io_out_bits_fuOpType = data_fuOpType;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
  assign io_out_bits_src_0 = data_src_0;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
  assign io_out_bits_robIdx_flag = data_robIdx_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
  assign io_out_bits_robIdx_value = data_robIdx_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
  assign io_out_bits_sqIdx_flag = data_sqIdx_flag;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
  assign io_out_bits_sqIdx_value = data_sqIdx_value;	// home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala:22:7, :45:25
endmodule
