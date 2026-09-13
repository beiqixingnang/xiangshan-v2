module MbistClockGateCell(	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:35:7
  input  clock,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:35:7
         mbist_writeen,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:36:17
         mbist_readen,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:36:17
         mbist_req,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:36:17
         E,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:41:13
         dft_cgen,	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:42:15
  output out_clock	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:43:21
);

  ClockGate CG (	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:45:26
    .TE (dft_cgen),
    .E  (mbist_req ? mbist_readen | mbist_writeen : E),	// home/lishuo/xs-v2-local/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala:57:{19,44}
    .CK (clock),
    .Q  (out_clock)
  );
endmodule
