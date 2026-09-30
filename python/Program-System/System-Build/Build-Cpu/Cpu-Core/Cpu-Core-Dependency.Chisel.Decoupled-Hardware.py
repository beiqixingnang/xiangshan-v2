"""UHSC V2 Chisel Decoupled queue dependency family boundary.
UHSC V2 Chisel Decoupled 队列依赖 family 边界。

The selected Kunminghu V2 closure links 208 locked modules to
``src/main/scala/chisel3/util/Decoupled.scala``: 134 ``Queue<N>_<Type>``
instances of the parameterised Chisel ``Queue`` (``entries``, ``pipe``,
``flow``, ``hasFlush`` and the ``Mem``-backed payload store), plus the 74
``ram_*`` queue memories that Decoupled.scala materialises.  This single
Build-Cpu file keeps the whole family in one faithful generator instead of one
Python stub per instantiation.  ``BundleMap`` is a payload type of the V2
bundles rather than a module of its own, so it is covered through the six
``Queue<N>_BundleMap`` instances.  ``PipeWithFlush`` belongs to
``src/main/scala/utils/PipeWithFlush.scala`` and is carried here as the second
member of the same queue/pipeline family, so 216 locked modules in total are
covered by this file.  Every payload field is named exactly as the pinned
artifact names it, including the whole-vector ``io_enq_bits``/``io_deq_bits``
form that carries no field suffix.

选定的 Kunminghu V2 闭包把 208 个锁定模块链接到
``src/main/scala/chisel3/util/Decoupled.scala``：参数化 Chisel ``Queue`` 的
134 个 ``Queue<N>_<Type>`` 实例（``entries``、``pipe``、``flow``、``hasFlush``
以及 ``Mem`` 支撑的载荷存储），加上 Decoupled.scala 生成的 74 个 ``ram_*``
队列存储器。本单个 Build-Cpu 文件把整个 family 放在一个忠实生成器里，而不是为
每个实例写一个浅层 Python 桩。``BundleMap`` 是 V2 bundle 的载荷类型而非独立模块，
因此通过六个 ``Queue<N>_BundleMap`` 实例覆盖。``PipeWithFlush`` 属于
``src/main/scala/utils/PipeWithFlush.scala``，作为同一队列/流水线族第二个成员
在此承载，因此本文件共覆盖 216 个锁定模块。每个载荷字段都与钉死产物的命名完全
一致，包括没有字段后缀的整向量 ``io_enq_bits``/``io_deq_bits`` 形式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Memory, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Source family: the parameterised Chisel Queue of chisel3/util/Decoupled.scala,
# the queue memories it materialises, and the XiangShan pipeline-with-flush
# generator.  The public boundary exposes the locked per-instance port surface
# (clock, reset, io_enq_*, io_deq_*, io_count, io_flush, io_enq_bits_*,
# io_deq_bits_*) plus the two structural primitives the family is built from.
# 来源 family：chisel3/util/Decoupled.scala 的参数化 Chisel Queue、其生成的队列
# 存储器，以及 XiangShan 的带 flush 流水线生成器。公共边界暴露锁定的逐实例端口
# 面（clock、reset、io_enq_*、io_deq_*、io_count、io_flush、io_enq_bits_*、
# io_deq_bits_*），以及构成该 family 的两个结构原语。
__all__ = [
    'QueueConfig',
    'QueueInstanceSpec',
    'QueueRamSpec',
    'PipeInstanceSpec',
    'QUEUE_INSTANCE_ROWS',
    'QUEUE_RAM_ROWS',
    'PIPE_INSTANCE_ROWS',
    'parse_queue_instance',
    'parse_queue_ram',
    'parse_pipe_instance',
    'enqueue_port_name',
    'dequeue_port_name',
    'queue_instances',
    'queue_ram_instances',
    'pipe_instances',
    'queue_instance',
    'queue_ram_instance',
    'chisel_queue_ports',
    'bundle_map_payload',
    'ChiselQueue',
    'QueueRam',
    'ChiselPipeWithFlush',
    'build_verilog',
    'main',
]


# Locked behavioural authority for the queue family. / 队列 family 的锁定行为权威来源。


# Locked behavioural authority for the queue memory primitives. / 队列存储器原语的锁定行为权威来源。


# Locked behavioural authority for the pipeline-with-flush member. / 带 flush 流水线成员的锁定行为权威来源。


# Handshake presence flags, in the order they occupy the catalog flag field. /
# 握手存在标志，按其在 catalog 标志字段中的顺序排列。
HANDSHAKE_FLAG_NAMES: tuple[str, ...] = (
    "has_enq_ready",
    "has_enq_valid",
    "has_deq_ready",
    "has_deq_valid",
)


# Flush rule tokens of the pipeline member, one per flushed stage. / 流水线成员每一被 flush 级的规则记号。
PIPE_FLUSH_RULES: tuple[str, ...] = ("r", "ro", "rol")


# =============================================================================
# Configuration
# =============================================================================
# Every locked Queue<N>_<Type> instance, one catalog row each. / 每个锁定的 Queue<N>_<Type> 实例一行 catalog。
# Row: name|entries|flags|word|payload|enq|deq|flow.
QUEUE_INSTANCE_ROWS: tuple[str, ...] = (
    "Queue10_GrantBuffer_Anon|10|1111fc|0|-|-|-|-",
    "Queue10_PutBufferBeatEntry|10|0110|288|data:256,mask:32|data:256,mask:32,corrupt:1|data:0:256,mask:256:32|-",
    "Queue16_DSBeat|16|0110f|256|data:256|data:256|data:0:256|-",
    "Queue16_GrantQueueData|16|0110|256|data_data:256|data_data:256|data_data:0:256|-",
    "Queue16_GrantQueueTask|16|1111c|25|task_isKeyword:1,task_opcode:4,task_param:3,task_sourceId:7,task_denied:1,task_corrupt:1,grantid:8|task_channel:3,task_txChannel:3,task_set:9,task_tag:31,task_off:6,task_alias:2,task_vaddr:44,task_isKeyword:1,task_opcode:4,task_param:3,task_size:3,task_sourceId:7,task_bufIdx:2,task_needProbeAckData:1,task_denied:1,task_corrupt:1,task_mshrTask:1,task_mshrId:8,task_aliasTask:1,task_useProbeData:1,task_mshrRetry:1,task_readProbeDataDown:1,task_fromL2pft:1,task_needHint:1,task_dirty:1,task_way:3,task_meta_dirty:1,task_meta_state:2,task_meta_clients:1,task_meta_alias:2,task_meta_prefetch:1,task_meta_prefetchSrc:3,task_meta_accessed:1,task_meta_tagErr:1,task_meta_dataErr:1,task_metaWen:1,task_tagWen:1,task_dsWen:1,task_wayMask:8,task_replTask:1,task_cmoTask:1,task_cmoAll:1,task_reqSource:5,task_mergeA:1,task_aMergeTask_off:6,task_aMergeTask_alias:2,task_aMergeTask_vaddr:44,task_aMergeTask_isKeyword:1,task_aMergeTask_opcode:3,task_aMergeTask_param:3,task_aMergeTask_sourceId:7,task_aMergeTask_meta_dirty:1,task_aMergeTask_meta_state:2,task_aMergeTask_meta_clients:1,task_aMergeTask_meta_alias:2,task_aMergeTask_meta_prefetch:1,task_aMergeTask_meta_prefetchSrc:3,task_aMergeTask_meta_accessed:1,task_aMergeTask_meta_tagErr:1,task_aMergeTask_meta_dataErr:1,task_snpHitRelease:1,task_snpHitReleaseToInval:1,task_snpHitReleaseToClean:1,task_snpHitReleaseWithData:1,task_snpHitReleaseIdx:8,task_snpHitReleaseMeta_dirty:1,task_snpHitReleaseMeta_state:2,task_snpHitReleaseMeta_clients:1,task_snpHitReleaseMeta_alias:2,task_snpHitReleaseMeta_prefetch:1,task_snpHitReleaseMeta_prefetchSrc:3,task_snpHitReleaseMeta_accessed:1,task_snpHitReleaseMeta_tagErr:1,task_snpHitReleaseMeta_dataErr:1,grantid:8|task_isKeyword:0:1,task_opcode:1:4,task_param:5:3,task_sourceId:8:7,task_denied:15:1,task_corrupt:16:1,grantid:17:8|-",
    "Queue16_HintQueueEntry|16|1111|11|source:7,opcode:3,isKeyword:1|source:7,opcode:3,isKeyword:1|source:0:7,opcode:7:3,isKeyword:10:1|-",
    "Queue16_TaskBundle|16|1111fc|67|set:9,tag:31,off:6,opcode:4,param:3,mshrId:8,dirty:1,reqSource:5|channel:3,txChannel:3,set:9,tag:31,off:6,alias:2,vaddr:44,isKeyword:1,opcode:4,param:3,size:3,sourceId:7,bufIdx:2,needProbeAckData:1,denied:1,corrupt:1,mshrTask:1,mshrId:8,aliasTask:1,useProbeData:1,mshrRetry:1,readProbeDataDown:1,fromL2pft:1,needHint:1,dirty:1,way:3,meta_dirty:1,meta_state:2,meta_clients:1,meta_alias:2,meta_prefetch:1,meta_prefetchSrc:3,meta_accessed:1,meta_tagErr:1,meta_dataErr:1,metaWen:1,tagWen:1,dsWen:1,wayMask:8,replTask:1,cmoTask:1,cmoAll:1,reqSource:5,mergeA:1,aMergeTask_off:6,aMergeTask_alias:2,aMergeTask_vaddr:44,aMergeTask_isKeyword:1,aMergeTask_opcode:3,aMergeTask_param:3,aMergeTask_sourceId:7,aMergeTask_meta_dirty:1,aMergeTask_meta_state:2,aMergeTask_meta_clients:1,aMergeTask_meta_alias:2,aMergeTask_meta_prefetch:1,aMergeTask_meta_prefetchSrc:3,aMergeTask_meta_accessed:1,aMergeTask_meta_tagErr:1,aMergeTask_meta_dataErr:1,snpHitRelease:1,snpHitReleaseToInval:1,snpHitReleaseToClean:1,snpHitReleaseWithData:1,snpHitReleaseIdx:8,snpHitReleaseMeta_dirty:1,snpHitReleaseMeta_state:2,snpHitReleaseMeta_clients:1,snpHitReleaseMeta_alias:2,snpHitReleaseMeta_prefetch:1,snpHitReleaseMeta_prefetchSrc:3,snpHitReleaseMeta_accessed:1,snpHitReleaseMeta_tagErr:1,snpHitReleaseMeta_dataErr:1|set:0:9,tag:9:31,off:40:6,opcode:46:4,param:50:3,mshrId:53:8,dirty:61:1,reqSource:62:5|-",
    "Queue16_grantAckQEntry|16|0111|6|sink:6|source:7,sink:6|sink:0:6|-",
    "Queue1_AXI4BundleAR|1|1111f|87|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:0:1,addr:1:48,len:49:8,size:57:3,burst:60:2,echo_extra_id:74:13|-",
    "Queue1_AXI4BundleARW|1|1111f|90|id:6,addr:48,len:8,size:3,=81:14,echo_tl_state_size:4,echo_tl_state_source:6,wen:1|id:6,addr:48,len:8,size:3,echo_tl_state_size:4,echo_tl_state_source:6,wen:1|id:0:6,addr:6:48,len:54:8,size:62:3,burst:65:2,lock:67:1,cache:68:4,prot:72:3,qos:75:4,echo_tl_state_size:79:4,echo_tl_state_source:83:6,wen:89:1|burst=1,lock=0,cache=0,prot=1,qos=0",
    "Queue1_AXI4BundleARW_1|1|1111f|71|id:5,addr:31,len:8,size:3,=81:14,echo_tl_state_size:4,echo_tl_state_source:5,wen:1|id:5,addr:31,len:8,size:3,echo_tl_state_size:4,echo_tl_state_source:5,wen:1|id:0:5,addr:5:31,len:36:8,size:44:3,burst:47:2,lock:49:1,cache:50:4,prot:54:3,qos:57:4,echo_tl_state_size:61:4,echo_tl_state_source:65:5,wen:70:1|burst=1,lock=0,cache=0,prot=1,qos=0",
    "Queue1_AXI4BundleARW_2|1|1111f|68|=0:1,addr:30,len:8,size:3,=81:14,echo_tl_state_size:4,echo_tl_state_source:7,wen:1|addr:30,len:8,size:3,echo_tl_state_size:4,echo_tl_state_source:7,wen:1|id:0:1,addr:1:30,len:31:8,size:39:3,burst:42:2,lock:44:1,cache:45:4,prot:49:3,qos:52:4,echo_tl_state_size:56:4,echo_tl_state_source:60:7,wen:67:1|id=0,burst=1,lock=0,cache=0,prot=1,qos=0",
    "Queue1_AXI4BundleAW|1|1111f|87|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:0:1,addr:1:48,len:49:8,size:57:3,burst:60:2,echo_extra_id:74:13|-",
    "Queue1_AXI4BundleB|1|1111f|3|id:1,resp:2|id:1,resp:2|id:0:1,resp:1:2|-",
    "Queue1_AXI4BundleR|1|1111f|260|id:1,data:256,resp:2,last:1|id:1,data:256,resp:2,last:1|id:0:1,data:1:256,resp:257:2,last:259:1|-",
    "Queue1_AXI4BundleW|1|1111f|289|data:256,strb:32,last:1|data:256,strb:32,last:1|data:0:256,strb:256:32,last:288:1|-",
    "Queue1_AXI4BundleW_1|1|1111f|73|data:64,strb:8,last:1|data:64,strb:8,last:1|data:0:64,strb:64:8,last:72:1|-",
    "Queue1_AXI4BundleW_2|1|1111f|37|data:32,strb:4,=1:1|data:32,strb:4|data:0:32,strb:32:4,last:36:1|last=1",
    "Queue1_BundleMap|1|1111|10|tl_state_size:4,tl_state_source:6|tl_state_size:4,tl_state_source:6|tl_state_size:0:4,tl_state_source:4:6|-",
    "Queue1_BundleMap_128|1|1111|9|tl_state_size:4,tl_state_source:5|tl_state_size:4,tl_state_source:5|tl_state_size:0:4,tl_state_source:4:5|-",
    "Queue1_BundleMap_162|1|1111|14|extra_id:13,real_last:1|extra_id:13,real_last:1|extra_id:0:13,real_last:13:1|-",
    "Queue1_ChosenQBundle|1|1111|301|bits_valid:1,bits_rdy:1,bits_task_channel:3,=0:3,bits_task_set:9,bits_task_tag:31,bits_task_off:6,bits_task_alias:2,bits_task_vaddr:44,bits_task_isKeyword:1,bits_task_opcode:4,bits_task_param:3,bits_task_size:3,bits_task_sourceId:7,=0:4,bits_task_corrupt:1,=0:13,bits_task_fromL2pft:1,bits_task_needHint:1,=0:31,bits_task_reqSource:5,=0:105,bits_waitMP:4,bits_waitMS:16,id:2|bits_valid:1,bits_rdy:1,bits_task_channel:3,bits_task_set:9,bits_task_tag:31,bits_task_off:6,bits_task_alias:2,bits_task_vaddr:44,bits_task_isKeyword:1,bits_task_opcode:4,bits_task_param:3,bits_task_size:3,bits_task_sourceId:7,bits_task_corrupt:1,bits_task_fromL2pft:1,bits_task_needHint:1,bits_task_reqSource:5,bits_waitMP:4,bits_waitMS:16,id:2|bits_task_channel:2:3,bits_task_txChannel:5:3,bits_task_set:8:9,bits_task_tag:17:31,bits_task_off:48:6,bits_task_alias:54:2,bits_task_vaddr:56:44,bits_task_isKeyword:100:1,bits_task_opcode:101:4,bits_task_param:105:3,bits_task_size:108:3,bits_task_sourceId:111:7,bits_task_bufIdx:118:2,bits_task_needProbeAckData:120:1,bits_task_denied:121:1,bits_task_corrupt:122:1,bits_task_mshrTask:123:1,bits_task_mshrId:124:8,bits_task_aliasTask:132:1,bits_task_useProbeData:133:1,bits_task_mshrRetry:134:1,bits_task_readProbeDataDown:135:1,bits_task_fromL2pft:136:1,bits_task_needHint:137:1,bits_task_dirty:138:1,bits_task_way:139:3,bits_task_meta_dirty:142:1,bits_task_meta_state:143:2,bits_task_meta_clients:145:1,bits_task_meta_alias:146:2,bits_task_meta_prefetch:148:1,bits_task_meta_prefetchSrc:149:3,bits_task_meta_accessed:152:1,bits_task_meta_tagErr:153:1,bits_task_meta_dataErr:154:1,bits_task_metaWen:155:1,bits_task_tagWen:156:1,bits_task_dsWen:157:1,bits_task_replTask:166:1,bits_task_cmoTask:167:1,bits_task_cmoAll:168:1,bits_task_reqSource:169:5,bits_task_mergeA:174:1,bits_task_aMergeTask_off:175:6,bits_task_aMergeTask_alias:181:2,bits_task_aMergeTask_vaddr:183:44,bits_task_aMergeTask_isKeyword:227:1,bits_task_aMergeTask_opcode:228:3,bits_task_aMergeTask_param:231:3,bits_task_aMergeTask_sourceId:234:7,bits_task_aMergeTask_meta_dirty:241:1,bits_task_aMergeTask_meta_state:242:2,bits_task_aMergeTask_meta_clients:244:1,bits_task_aMergeTask_meta_alias:245:2,bits_task_aMergeTask_meta_prefetch:247:1,bits_task_aMergeTask_meta_prefetchSrc:248:3,bits_task_aMergeTask_meta_accessed:251:1,bits_task_aMergeTask_meta_tagErr:252:1,bits_task_aMergeTask_meta_dataErr:253:1,bits_task_snpHitRelease:254:1,bits_task_snpHitReleaseToInval:255:1,bits_task_snpHitReleaseToClean:256:1,bits_task_snpHitReleaseWithData:257:1,bits_task_snpHitReleaseIdx:258:8,bits_task_snpHitReleaseMeta_dirty:266:1,bits_task_snpHitReleaseMeta_state:267:2,bits_task_snpHitReleaseMeta_clients:269:1,bits_task_snpHitReleaseMeta_alias:270:2,bits_task_snpHitReleaseMeta_prefetch:272:1,bits_task_snpHitReleaseMeta_prefetchSrc:273:3,bits_task_snpHitReleaseMeta_accessed:276:1,bits_task_snpHitReleaseMeta_tagErr:277:1,bits_task_snpHitReleaseMeta_dataErr:278:1,id:299:2|-",
    "Queue1_ClientDirWrite|1|1111|16|set:10,way:4,data_0_state:2|set:10,way:4,data_0_state:2|set:0:10,way:10:4,data_0_state:14:2|-",
    "Queue1_ClientTagWrite|1|1111|44|set:10,way:4,tag:30|set:10,way:4,tag:30|set:0:10,way:10:4,tag:14:30|-",
    "Queue1_CtrlReq|1|1111|776|cmd:8,data_0:64,data_1:64,data_2:64,data_3:64,data_4:64,data_5:64,data_6:64,data_7:64,set:64,tag:64,way:64,dir:64|cmd:8,data_0:64,data_1:64,data_2:64,data_3:64,data_4:64,data_5:64,data_6:64,data_7:64,set:64,tag:64,way:64,dir:64|cmd:0:8,data_0:8:64,data_1:72:64,data_2:136:64,data_3:200:64,data_4:264:64,data_5:328:64,data_6:392:64,data_7:456:64,set:520:64,tag:584:64,way:648:64,dir:712:64|-",
    "Queue1_CtrlResp|1|1111|520|cmd:8,data_0:64,data_1:64,data_2:64,data_3:64,data_4:64,data_5:64,data_6:64,data_7:64|cmd:8,data_0:64,data_1:64,data_2:64,data_3:64,data_4:64,data_5:64,data_6:64,data_7:64|cmd:0:8,data_0:8:64,data_1:72:64,data_2:136:64,data_3:200:64,data_4:264:64,data_5:328:64,data_6:392:64,data_7:456:64|-",
    "Queue1_EccInfo|1|1111|72|errCode:8,addr:64|errCode:8,addr:64|errCode:0:8,addr:8:64|-",
    "Queue1_L1PrefetchReq|1|1111|55|paddr:48,alias:2,confidence:1,is_store:1,pf_source_value:3|paddr:48,alias:2,confidence:1,is_store:1,pf_source_value:3|paddr:0:48,alias:48:2,confidence:50:1,is_store:51:1,pf_source_value:52:3|-",
    "Queue1_MSHRRequest|1|1111|119|channel:3,opcode:3,param:3,size:3,source:11,set:12,tag:28,off:6,mask:32,bufIdx:4,needHint:1,isPrefetch:1,isBop:1,preferCache:1,dirty:1,isHit:1,fromProbeHelper:1,fromCmoHelper:1,needProbeAckData:1,reqSource:5|channel:3,opcode:3,param:3,size:3,source:11,set:12,tag:28,off:6,mask:32,bufIdx:4,needHint:1,isPrefetch:1,isBop:1,preferCache:1,dirty:1,isHit:1,fromProbeHelper:1,fromCmoHelper:1,needProbeAckData:1,reqSource:5|channel:0:3,opcode:3:3,param:6:3,size:9:3,source:12:11,set:23:12,tag:35:28,off:63:6,mask:69:32,bufIdx:101:4,needHint:105:1,isPrefetch:106:1,isBop:107:1,preferCache:108:1,dirty:109:1,fromProbeHelper:111:1,fromCmoHelper:112:1,needProbeAckData:113:1,reqSource:114:5|-",
    "Queue1_PipeInfo|1|1111|92|counter:1,beat:1,last:1,needPb:1,need_d:1,isReleaseAck:1,req_sourceId:11,req_set:12,req_tag:28,req_channel:3,req_opcode:3,req_param:3,req_size:3,req_way:4,req_off:6,req_useBypass:1,req_bufIdx:4,req_denied:1,req_sinkId:4,req_bypassPut:1,req_dirty:1,req_isHit:1|counter:1,beat:1,last:1,needPb:1,need_d:1,isReleaseAck:1,req_sourceId:11,req_set:12,req_tag:28,req_channel:3,req_opcode:3,req_param:3,req_size:3,req_way:4,req_off:6,req_useBypass:1,req_bufIdx:4,req_denied:1,req_sinkId:4,req_bypassPut:1,req_dirty:1,req_isHit:1|counter:0:1,beat:1:1,last:2:1,needPb:3:1,need_d:4:1,isReleaseAck:5:1,req_sourceId:6:11,req_set:17:12,req_tag:29:28,req_channel:57:3,req_opcode:60:3,req_param:63:3,req_size:66:3,req_way:69:4,req_off:73:6,req_useBypass:79:1,req_bufIdx:80:4,req_denied:84:1,req_sinkId:85:4,req_bypassPut:89:1,req_dirty:90:1,req_isHit:91:1|-",
    "Queue1_PrefetchReq|1|1111|99|tag:33,set:9,vaddr:44,needT:1,source:7,pfSource:5|tag:33,set:9,vaddr:44,needT:1,source:7,pfSource:5|tag:0:33,set:33:9,vaddr:42:44,needT:86:1,source:87:7,pfSource:94:5|-",
    "Queue1_PrefetchReq_1|1|1111|59|tag:30,set:12,=0:12,pfSource:5|tag:30,set:12,pfSource:5|tag:0:30,set:30:12,needT:42:1,source:43:11,pfSource:54:5|-",
    "Queue1_PrefetchResp|1|1111|0|-|-|-|-",
    "Queue1_PrefetchResp_4|1|1111|0|-|-|-|-",
    "Queue1_PrefetchTrain|1|0111p|104|tag:33,set:9,needT:1,source:7,vaddr:44,hit:1,prefetched:1,pfsource:3,reqsource:5|tag:33,set:9,needT:1,source:7,vaddr:44,hit:1,prefetched:1,pfsource:3,reqsource:5|tag:0:33,set:33:9,needT:42:1,source:43:7,vaddr:50:44,reqsource:99:5|-",
    "Queue1_PrefetchTrain_4|1|1111|0|-|-|-|-",
    "Queue1_RegMapperInput|1|1111|103|read:1,index:23,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:1,index:23,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:0:1,index:1:23,data:24:64,mask:88:8,extra_tlrr_extra_source:96:5,extra_tlrr_extra_size:101:2|-",
    "Queue1_RegMapperInput_1|1|1111|50|read:1,index:13,data:32,mask:4|read:1,index:13,data:32,mask:4|read:0:1,index:1:13,data:14:32,mask:46:4|-",
    "Queue1_RegMapperInput_3|1|1111|89|read:1,index:9,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:1,index:9,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:0:1,index:1:9,data:10:64,mask:74:8,extra_tlrr_extra_source:82:5,extra_tlrr_extra_size:87:2|-",
    "Queue1_RegMapperInput_5|1|1111|84|read:1,index:4,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:1,index:4,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:0:1,index:1:4,data:5:64,mask:69:8,extra_tlrr_extra_source:77:5,extra_tlrr_extra_size:82:2|-",
    "Queue1_RegMapperInput_6|1|1111|83|read:1,index:4,data:64,mask:8,extra_tlrr_extra_source:4,extra_tlrr_extra_size:2|read:1,index:4,data:64,mask:8,extra_tlrr_extra_source:4,extra_tlrr_extra_size:2|read:0:1,index:1:4,data:5:64,mask:69:8,extra_tlrr_extra_source:77:4,extra_tlrr_extra_size:81:2|-",
    "Queue1_RegMapperInput_7|1|1111|93|read:1,index:13,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:1,index:13,data:64,mask:8,extra_tlrr_extra_source:5,extra_tlrr_extra_size:2|read:0:1,index:1:13,data:14:64,mask:78:8,extra_tlrr_extra_source:86:5,extra_tlrr_extra_size:91:2|-",
    "Queue1_RegMapperInput_8|1|1111|47|=0:1,index:10,data:32,mask:4|index:10,data:32,mask:4|read:0:1,index:1:10,data:11:32,mask:43:4|-",
    "Queue1_SelfDirWrite|1|1111|22|set:12,way:4,data_dirty:1,data_state:2,data_clientStates_0:2,data_prefetch:1|set:12,way:4,data_dirty:1,data_state:2,data_clientStates_0:2,data_prefetch:1|set:0:12,way:12:4,data_dirty:16:1,data_state:17:2,data_clientStates_0:19:2,data_prefetch:21:1|-",
    "Queue1_SelfTagWrite|1|1111|44|set:12,way:4,tag:28|set:12,way:4,tag:28|set:0:12,way:12:4,tag:16:28|-",
    "Queue1_TLBundleA|1|1111|333|opcode:4,param:3,size:3,source:3,address:31,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:3,address:31,mask:32,data:256,corrupt:1|opcode:0:4,size:7:3,source:10:3|-",
    "Queue2_AXI4BundleAR|2|1111|87|id:14,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:14,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:14,addr:14:48,len:62:8,size:70:3,burst:73:2,lock:75:1,cache:76:4,prot:80:3,qos:83:4|-",
    "Queue2_AXI4BundleAR_10|2|1111|56|id:1,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:1,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:1,addr:1:30,len:31:8,size:39:3,burst:42:2,lock:44:1,cache:45:4,prot:49:3,qos:52:4|-",
    "Queue2_AXI4BundleAR_3|2|1111|61|id:5,addr:31,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:5,addr:31,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:5,addr:5:31,len:36:8,size:44:3,burst:47:2,lock:49:1,cache:50:4,prot:54:3,qos:57:4|-",
    "Queue2_AXI4BundleAR_7|2|1111|87|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:0:1,addr:1:48,len:49:8,size:57:3,burst:60:2,lock:62:1,cache:63:4,prot:67:3,qos:70:4,echo_extra_id:74:13|-",
    "Queue2_AXI4BundleAR_9|2|1111|71|id:16,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:16,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:16,addr:16:30,len:46:8,size:54:3,burst:57:2,lock:59:1,cache:60:4,prot:64:3,qos:67:4|-",
    "Queue2_AXI4BundleAW|2|1111|87|id:14,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:14,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:14,addr:14:48,len:62:8,size:70:3,burst:73:2,lock:75:1,cache:76:4,prot:80:3,qos:83:4|-",
    "Queue2_AXI4BundleAW_10|2|1111|56|id:1,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:1,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:1,addr:1:30,len:31:8,size:39:3,burst:42:2,lock:44:1,cache:45:4,prot:49:3,qos:52:4|-",
    "Queue2_AXI4BundleAW_3|2|1111|61|id:5,addr:31,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:5,addr:31,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:5,addr:5:31,len:36:8,size:44:3,burst:47:2,lock:49:1,cache:50:4,prot:54:3,qos:57:4|-",
    "Queue2_AXI4BundleAW_7|2|1111|87|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:1,addr:48,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4,echo_extra_id:13|id:0:1,addr:1:48,len:49:8,size:57:3,burst:60:2,lock:62:1,cache:63:4,prot:67:3,qos:70:4,echo_extra_id:74:13|-",
    "Queue2_AXI4BundleAW_9|2|1111|71|id:16,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:16,addr:30,len:8,size:3,burst:2,lock:1,cache:4,prot:3,qos:4|id:0:16,addr:16:30,len:46:8,size:54:3,burst:57:2,lock:59:1,cache:60:4,prot:64:3,qos:67:4|-",
    "Queue2_AXI4BundleB|2|1111|16|id:14,resp:2|id:14,resp:2|id:0:14,resp:14:2|-",
    "Queue2_AXI4BundleB_10|2|1111|2|resp:2|resp:2|resp:0:2|-",
    "Queue2_AXI4BundleB_3|2|1111|7|id:5,resp:2|id:5,resp:2|id:0:5,resp:5:2|-",
    "Queue2_AXI4BundleB_7|2|1111|16|id:1,resp:2,echo_extra_id:13|id:1,resp:2,echo_extra_id:13|id:0:1,resp:1:2,echo_extra_id:3:13|-",
    "Queue2_AXI4BundleB_9|2|1111|18|id:16,resp:2|id:16,resp:2|id:0:16,resp:16:2|-",
    "Queue2_AXI4BundleR|2|1111|273|id:14,data:256,resp:2,last:1|id:14,data:256,resp:2,last:1|id:0:14,data:14:256,resp:270:2,last:272:1|-",
    "Queue2_AXI4BundleR_3|2|1110|275|id:6,data:256,resp:2,echo_tl_state_size:4,echo_tl_state_source:6,last:1|id:6,data:256,resp:2,echo_tl_state_size:4,echo_tl_state_source:6,last:1|id:0:6,data:6:256,resp:262:2,echo_tl_state_size:264:4,echo_tl_state_source:268:6,last:274:1|-",
    "Queue2_AXI4BundleR_67|2|1111|72|id:5,data:64,resp:2,last:1|id:5,data:64,resp:2,last:1|id:0:5,data:5:64,resp:69:2,last:71:1|-",
    "Queue2_AXI4BundleR_71|2|1111|81|id:5,data:64,resp:2,echo_tl_state_size:4,echo_tl_state_source:5,last:1|id:5,data:64,resp:2,echo_tl_state_size:4,echo_tl_state_source:5,last:1|id:0:5,data:5:64,resp:69:2,echo_tl_state_size:71:4,echo_tl_state_source:75:5,last:80:1|-",
    "Queue2_AXI4BundleR_72|2|1111|273|id:1,data:256,resp:2,echo_extra_id:13,last:1|id:1,data:256,resp:2,echo_extra_id:13,last:1|id:0:1,data:1:256,resp:257:2,echo_extra_id:259:13,last:272:1|-",
    "Queue2_AXI4BundleR_74|2|1111|51|id:16,data:32,resp:2,last:1|id:16,data:32,resp:2,last:1|id:0:16,data:16:32,resp:48:2,last:50:1|-",
    "Queue2_AXI4BundleR_75|2|1111|35|data:32,resp:2,last:1|data:32,resp:2,last:1|data:0:32,resp:32:2,last:34:1|-",
    "Queue2_AXI4BundleW|2|1111|289|data:256,strb:32,last:1|data:256,strb:32,last:1|data:0:256,strb:256:32,last:288:1|-",
    "Queue2_AXI4BundleW_3|2|1111|73|data:64,strb:8,last:1|data:64,strb:8,last:1|data:0:64,strb:64:8,last:72:1|-",
    "Queue2_AXI4BundleW_9|2|1111|37|data:32,strb:4,last:1|data:32,strb:4,last:1|data:0:32,strb:32:4,last:36:1|-",
    "Queue2_DSData|2|1111|256|data:256|data:256,corrupt:1|data:0:256|-",
    "Queue2_TLBundleA|2|1111|354|opcode:4,param:3,size:3,source:7,address:48,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:7,address:48,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:7,address:17:48,mask:65:32,data:97:256,corrupt:353:1|-",
    "Queue2_TLBundleA_10|2|1111|350|opcode:4,param:3,size:3,source:3,address:48,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:3,address:48,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:3,address:13:48,mask:61:32,data:93:256,corrupt:349:1|-",
    "Queue2_TLBundleA_14|2|1111|362|opcode:4,param:3,size:3,source:10,address:48,user_reqSource:5,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:10,address:48,user_reqSource:5,echo_blockisdirty:1,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:10,address:20:48,user_reqSource:68:5,mask:73:32,data:105:256,corrupt:361:1|-",
    "Queue2_TLBundleA_15|2|1111|348|opcode:4,=0:3,size:3,=0:1,address:48,mask:32,data:256,=0:1|opcode:4,size:3,address:48,mask:32,data:256|opcode:0:4,param:4:3,size:7:3,source:10:1,address:11:48,mask:59:32,data:91:256,corrupt:347:1|-",
    "Queue2_TLBundleA_16|2|1111|117|opcode:4,param:3,size:2,source:5,address:30,mask:8,data:64,corrupt:1|opcode:4,param:3,size:2,source:5,address:30,mask:8,data:64,corrupt:1|opcode:0:4,param:4:3,size:7:2,source:9:5,address:14:30,mask:44:8,data:52:64,corrupt:116:1|-",
    "Queue2_TLBundleA_2|2|1111|136|opcode:4,param:3,size:3,source:5,address:48,mask:8,data:64,corrupt:1|opcode:4,param:3,size:3,source:5,address:48,mask:8,data:64,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:5,address:15:48,mask:63:8,data:71:64,corrupt:135:1|-",
    "Queue2_TLBundleA_20|2|1111|356|opcode:4,param:3,size:3,source:4,address:48,user_reqSource:5,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:4,address:48,user_reqSource:5,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:4,address:14:48,user_reqSource:62:5,mask:67:32,data:99:256,corrupt:355:1|-",
    "Queue2_TLBundleA_21|2|1111|406|opcode:4,param:3,size:3,source:6,address:48,user_alias:2,user_vaddr:44,user_reqSource:5,user_needHint:1,echo_isKeyword:1,mask:32,=0:257|opcode:4,param:3,size:3,source:6,address:48,user_alias:2,user_vaddr:44,user_reqSource:5,user_needHint:1,echo_isKeyword:1,mask:32|opcode:0:4,param:4:3,size:7:3,source:10:6,address:16:48,user_alias:64:2,user_vaddr:66:44,user_reqSource:110:5,user_needHint:115:1,echo_isKeyword:116:1,mask:117:32,data:149:256,corrupt:405:1|-",
    "Queue2_TLBundleA_22|2|1111|359|opcode:4,param:3,size:3,source:4,address:48,user_alias:2,user_reqSource:5,user_needHint:1,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:4,address:48,user_alias:2,user_reqSource:5,user_needHint:1,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:4,address:14:48,user_alias:62:2,user_reqSource:64:5,user_needHint:69:1,mask:70:32,data:102:256,corrupt:358:1|-",
    "Queue2_TLBundleA_26|2|1111|132|opcode:4,param:3,size:3,source:1,address:48,mask:8,data:64,corrupt:1|opcode:4,param:3,size:3,source:1,address:48,mask:8,data:64,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:1,address:11:48,mask:59:8,data:67:64,corrupt:131:1|-",
    "Queue2_TLBundleA_28|2|1111|135|opcode:4,param:3,size:3,source:4,address:48,mask:8,data:64,corrupt:1|opcode:4,param:3,size:3,source:4,address:48,mask:8,data:64,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:4,address:14:48,mask:62:8,data:70:64,corrupt:134:1|-",
    "Queue2_TLBundleA_29|2|1111|116|opcode:4,param:3,size:2,source:4,address:30,mask:8,data:64,corrupt:1|opcode:4,param:3,size:2,source:4,address:30,mask:8,data:64,corrupt:1|opcode:0:4,param:4:3,size:7:2,source:9:4,address:13:30,mask:43:8,data:51:64,corrupt:115:1|-",
    "Queue2_TLBundleA_33|2|1111|407|opcode:4,param:3,size:3,source:7,address:48,user_reqSource:5,user_alias:2,user_vaddr:44,user_needHint:1,echo_isKeyword:1,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:7,address:48,user_reqSource:5,user_alias:2,user_vaddr:44,user_needHint:1,echo_isKeyword:1,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:7,address:17:48,user_reqSource:65:5,user_alias:70:2,user_vaddr:72:44,user_needHint:116:1,echo_isKeyword:117:1,mask:118:32,data:150:256,corrupt:406:1|-",
    "Queue2_TLBundleA_39|2|1111|361|opcode:4,param:3,size:3,source:8,address:48,user_reqSource:5,echo_blockisdirty:1,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:8,address:48,user_reqSource:5,echo_blockisdirty:1,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:8,address:18:48,user_reqSource:66:5,echo_blockisdirty:71:1,mask:72:32,data:104:256,corrupt:360:1|-",
    "Queue2_TLBundleA_5|2|1111|355|opcode:4,param:3,size:3,source:8,address:48,mask:32,data:256,corrupt:1|opcode:4,param:3,size:3,source:8,address:48,mask:32,data:256,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:8,address:18:48,mask:66:32,data:98:256,corrupt:354:1|-",
    "Queue2_TLBundleA_50|2|1111|351|opcode:4,param:3,size:3,source:4,address:48,mask:32,data:256,=0:1|opcode:4,param:3,size:3,source:4,address:48,mask:32,data:256|opcode:0:4,param:4:3,size:7:3,source:10:4,address:14:48,mask:62:32,data:94:256,corrupt:350:1|-",
    "Queue2_TLBundleA_7|2|1111|119|opcode:4,param:3,size:3,source:5,address:31,mask:8,data:64,corrupt:1|opcode:4,param:3,size:3,source:5,address:31,mask:8,data:64,corrupt:1|opcode:0:4,param:4:3,size:7:3,source:10:5,address:15:31,mask:46:8,data:54:64,corrupt:118:1|-",
    "Queue2_TLBundleB|2|1111|345|opcode:3,param:2,size:3,address:48,mask:32,data:256,=0:1|opcode:3,param:2,size:3,address:48,mask:32,data:256|opcode:0:3,param:3:2,size:5:3,address:8:48,mask:56:32,data:88:256,corrupt:344:1|-",
    "Queue2_TLBundleB_1|2|1111|309|opcode:3,param:2,address:48,data:256|opcode:3,param:2,size:3,source:6,address:48,mask:32,data:256,corrupt:1|opcode:0:3,param:3:2,address:5:48,data:53:256|-",
    "Queue2_TLBundleB_10|2|0011|0|-|-|opcode:-1:3,param:-1:2,size:-1:3,source:-1:4,address:-1:48,mask:-1:32,data:-1:256|-",
    "Queue2_TLBundleB_2|2|1111|352|opcode:3,param:2,size:3,source:7,address:48,mask:32,data:256,corrupt:1|opcode:3,param:2,size:3,source:7,address:48,mask:32,data:256,corrupt:1|opcode:0:3,param:3:2,size:5:3,source:8:7,address:15:48,mask:63:32,data:95:256,corrupt:351:1|-",
    "Queue2_TLBundleB_6|2|1111|312|opcode:3,param:2,size:3,address:48,data:256|opcode:3,param:2,size:3,source:8,address:48,mask:32,data:256,corrupt:1|opcode:0:3,param:3:2,size:5:3,address:8:48,data:56:256|-",
    "Queue2_TLBundleC|2|1111|324|opcode:3,param:3,size:3,source:10,address:48,echo_blockisdirty:1,data:256|opcode:3,param:3,size:3,source:10,address:48,user_reqSource:5,echo_blockisdirty:1,data:256,corrupt:1|opcode:0:3,param:3:3,size:6:3,source:9:10,address:19:48,echo_blockisdirty:67:1,data:68:256|-",
    "Queue2_TLBundleC_1|2|1111|373|opcode:3,param:3,size:3,source:6,address:48,=0:53,data:256,corrupt:1|opcode:3,param:3,size:3,source:6,address:48,data:256,corrupt:1|opcode:0:3,param:3:3,size:6:3,source:9:6,address:15:48,user_alias:63:2,user_vaddr:65:44,user_reqSource:109:5,user_needHint:114:1,echo_isKeyword:115:1,data:116:256,corrupt:372:1|-",
    "Queue2_TLBundleC_2|2|1111|374|opcode:3,param:3,size:3,source:7,address:48,user_reqSource:5,user_alias:2,user_vaddr:44,user_needHint:1,echo_isKeyword:1,data:256,corrupt:1|opcode:3,param:3,size:3,source:7,address:48,user_reqSource:5,user_alias:2,user_vaddr:44,user_needHint:1,echo_isKeyword:1,data:256,corrupt:1|opcode:0:3,param:3:3,size:6:3,source:9:7,address:16:48,user_reqSource:64:5,user_alias:69:2,user_vaddr:71:44,user_needHint:115:1,echo_isKeyword:116:1,data:117:256,corrupt:373:1|-",
    "Queue2_TLBundleC_6|2|1111|315|opcode:3,size:3,source:4,address:48,data:256,corrupt:1|opcode:3,param:3,size:3,source:4,address:48,data:256,corrupt:1|opcode:0:3,size:3:3,source:6:4,address:10:48,data:58:256,corrupt:314:1|-",
    "Queue2_TLBundleD|2|1111|275|opcode:4,param:2,size:3,source:7,sink:1,denied:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:7,sink:1,denied:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:7,sink:16:1,denied:17:1,data:18:256,corrupt:274:1|-",
    "Queue2_TLBundleD_12|2|1111|276|opcode:4,param:2,size:3,source:3,sink:6,denied:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:3,sink:6,denied:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:3,sink:12:6,denied:18:1,data:19:256,corrupt:275:1|-",
    "Queue2_TLBundleD_16|2|1111|284|opcode:4,param:2,size:3,source:10,sink:6,denied:1,echo_blockisdirty:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:10,sink:6,denied:1,echo_blockisdirty:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:10,sink:19:6,denied:25:1,echo_blockisdirty:26:1,data:27:256,corrupt:283:1|-",
    "Queue2_TLBundleD_17|2|1111|10|denied:1,data:8,corrupt:1|opcode:4,param:2,size:3,source:1,sink:6,denied:1,data:8,corrupt:1|denied:0:1,data:1:8,corrupt:9:1|-",
    "Queue2_TLBundleD_18|2|1111|274|opcode:4,param:2,size:3,=0:1,sink:6,denied:1,data:256,corrupt:1|opcode:4,param:2,size:3,sink:6,denied:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:1,sink:10:6,denied:16:1,data:17:256,corrupt:273:1|-",
    "Queue2_TLBundleD_19|2|1111|80|opcode:4,param:2,size:2,source:5,sink:1,denied:1,data:64,corrupt:1|opcode:4,param:2,size:2,source:5,sink:1,denied:1,data:64,corrupt:1|opcode:0:4,param:4:2,size:6:2,source:8:5,sink:13:1,denied:14:1,data:15:64,corrupt:79:1|-",
    "Queue2_TLBundleD_2|2|1111|273|opcode:4,=0:2,size:3,source:6,=0:258|opcode:4,size:3,source:6|opcode:0:4,param:4:2,size:6:3,source:9:6,denied:15:1,data:16:256,corrupt:272:1|-",
    "Queue2_TLBundleD_23|2|1111|281|opcode:4,param:2,size:3,source:4,sink:10,denied:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:4,sink:10,denied:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:4,sink:13:10,denied:23:1,data:24:256,corrupt:280:1|-",
    "Queue2_TLBundleD_24|2|1111|284|opcode:4,param:2,size:3,source:6,sink:10,denied:1,echo_isKeyword:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:6,sink:10,denied:1,echo_isKeyword:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:6,sink:15:10,denied:25:1,echo_isKeyword:26:1,data:27:256,corrupt:283:1|-",
    "Queue2_TLBundleD_29|2|1111|77|opcode:4,param:2,size:3,source:1,sink:1,denied:1,data:64,corrupt:1|opcode:4,param:2,size:3,source:1,sink:1,denied:1,data:64,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:1,sink:10:1,denied:11:1,data:12:64,corrupt:76:1|-",
    "Queue2_TLBundleD_31|2|1111|80|opcode:4,param:2,size:3,source:4,sink:1,denied:1,data:64,corrupt:1|opcode:4,param:2,size:3,source:4,sink:1,denied:1,data:64,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:4,sink:13:1,denied:14:1,data:15:64,corrupt:79:1|-",
    "Queue2_TLBundleD_32|2|1111|79|opcode:4,param:2,size:2,source:4,sink:1,denied:1,data:64,corrupt:1|opcode:4,param:2,size:2,source:4,sink:1,denied:1,data:64,corrupt:1|opcode:0:4,param:4:2,size:6:2,source:8:4,sink:12:1,denied:13:1,data:14:64,corrupt:78:1|-",
    "Queue2_TLBundleD_36|2|1111|283|opcode:4,param:2,size:3,source:7,sink:8,denied:1,echo_isKeyword:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:7,sink:8,denied:1,echo_isKeyword:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:7,sink:16:8,denied:24:1,echo_isKeyword:25:1,data:26:256,corrupt:282:1|-",
    "Queue2_TLBundleD_4|2|1111|81|opcode:4,param:2,size:3,source:5,sink:1,denied:1,data:64,corrupt:1|opcode:4,param:2,size:3,source:5,sink:1,denied:1,data:64,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:5,sink:14:1,denied:15:1,data:16:64,corrupt:80:1|-",
    "Queue2_TLBundleD_42|2|1101|281|opcode:4,param:2,size:3,source:8,sink:6,echo_blockisdirty:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:8,sink:6,denied:1,echo_blockisdirty:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:8,sink:17:6,echo_blockisdirty:23:1,data:24:256,corrupt:280:1|-",
    "Queue2_TLBundleD_53|2|1111|273|opcode:4,param:2,size:3,source:4,sink:3,denied:1,data:256|opcode:4,param:2,size:3,source:4,sink:3,denied:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:4,sink:13:3,denied:16:1,data:17:256|-",
    "Queue2_TLBundleD_7|2|1111|276|opcode:4,param:2,size:3,source:8,sink:1,denied:1,data:256,corrupt:1|opcode:4,param:2,size:3,source:8,sink:1,denied:1,data:256,corrupt:1|opcode:0:4,param:4:2,size:6:3,source:9:8,sink:17:1,denied:18:1,data:19:256,corrupt:275:1|-",
    "Queue2_TLBundleE|2|1111|6|sink:6|sink:6|sink:0:6|-",
    "Queue2_TLBundleE_1|2|1111|10|sink:10|sink:10|sink:0:10|-",
    "Queue2_TLBundleE_10|2|1111|3|sink:3|sink:3|sink:0:3|-",
    "Queue2_TLBundleE_2|2|1111|8|sink:8|sink:8|sink:0:8|-",
    "Queue2_UInt2|2|1111f|2|:2|:2|:0:2|-",
    "Queue2_UInt3|2|1111f|3|:3|:3|:0:3|-",
    "Queue40_L2TlbMQBundle|40|1111l|47|req_info_vpn:38,req_info_s2xlate:2,req_info_source:2,=0:1,isLLptw:1,=0:3|req_info_vpn:38,req_info_s2xlate:2,req_info_source:2,isLLptw:1|req_info_vpn:0:38,req_info_s2xlate:38:2,req_info_source:40:2,isHptwReq:42:1,isLLptw:43:1,hptwId:44:3|-",
    "Queue4_BundleMap|4|1111|3|extra_id:3|extra_id:3|extra_id:0:3|-",
    "Queue4_HintQueueEntry|4|1111f|11|source:7,opcode:3,isKeyword:1|source:7,opcode:3,isKeyword:1|source:0:7,opcode:7:3,isKeyword:10:1|-",
    "Queue4_TPmetaReq|4|1111|525|hartid:6,set:10,way:4,=1:1,rawData_0:42,rawData_1:42,rawData_2:42,rawData_3:42,rawData_4:42,rawData_5:42,rawData_6:42,rawData_7:42,rawData_8:42,rawData_9:42,rawData_10:42,rawData_11:42|hartid:6,set:10,way:4,rawData_0:42,rawData_1:42,rawData_2:42,rawData_3:42,rawData_4:42,rawData_5:42,rawData_6:42,rawData_7:42,rawData_8:42,rawData_9:42,rawData_10:42,rawData_11:42|hartid:0:6,set:6:10,way:16:4,wmode:20:1,rawData_0:21:42,rawData_1:63:42,rawData_2:105:42,rawData_3:147:42,rawData_4:189:42,rawData_5:231:42,rawData_6:273:42,rawData_7:315:42,rawData_8:357:42,rawData_9:399:42,rawData_10:441:42,rawData_11:483:42|-",
    "Queue4_triggerBundle|4|1111c|52|paddr:48,way:4|vaddr:50,paddr:48,way:4|paddr:0:48,way:48:4|-",
    "Queue5_BundleMap|5|1111|3|extra_id:3|extra_id:3|extra_id:0:3|-",
    "Queue5_MSHRRequest|5|1111c|119|=cb2:12,source:11,set:12,tag:28,=1a00000000000:56|source:11,set:12,tag:28|channel:0:3,opcode:3:3,param:6:3,size:9:3,source:12:11,set:23:12,tag:35:28,off:63:6,mask:69:32,bufIdx:101:4,needHint:105:1,isPrefetch:106:1,isBop:107:1,preferCache:108:1,dirty:109:1,isHit:110:1,fromProbeHelper:111:1,fromCmoHelper:112:1,needProbeAckData:113:1,reqSource:114:5|-",
    "Queue68_BundleMap|68|1111|11|tl_state_size:4,tl_state_source:7|tl_state_size:4,tl_state_source:7|tl_state_size:0:4,tl_state_source:4:7|-",
    "Queue6_DSData|6|1110f|257|data:256,corrupt:1|data:256,corrupt:1|data:0:256,corrupt:256:1|-",
    "Queue8_TPmetaReq|8|0111|525|hartid:6,set:10,way:4,=0:505|hartid:6,set:10,way:4|hartid:0:6,set:6:10,way:16:4,wmode:20:1,rawData_0:21:42,rawData_1:63:42,rawData_2:105:42,rawData_3:147:42,rawData_4:189:42,rawData_5:231:42,rawData_6:273:42,rawData_7:315:42,rawData_8:357:42,rawData_9:399:42,rawData_10:441:42,rawData_11:483:42|-",
    "Queue8_UInt12|8|1111|12|:12|:12|:0:12|-",
    "Queue9_TLBundleC|9|0111fc|318|opcode:3,param:3,=6:3,source:4,address:48,data:256,corrupt:1|opcode:3,param:3,source:4,address:48,data:256,corrupt:1|opcode:0:3,param:3:3,size:6:3,source:9:4,address:13:48,data:61:256,corrupt:317:1|size=6",
    "Queue9_tpDataEntry|9|1111c|504|rawData_0:42,rawData_1:42,rawData_2:42,rawData_3:42,rawData_4:42,rawData_5:42,rawData_6:42,rawData_7:42,rawData_8:42,rawData_9:42,rawData_10:42,rawData_11:42|rawData_0:42,rawData_1:42,rawData_2:42,rawData_3:42,rawData_4:42,rawData_5:42,rawData_6:42,rawData_7:42,rawData_8:42,rawData_9:42,rawData_10:42,rawData_11:42|rawData_0:0:42,rawData_1:42:42,rawData_2:84:42,rawData_3:126:42,rawData_4:168:42,rawData_5:210:42,rawData_6:252:42,rawData_7:294:42,rawData_8:336:42,rawData_9:378:42,rawData_10:420:42,rawData_11:462:42|-",
)


# Every locked queue memory primitive, one catalog row each. / 每个锁定的队列存储器原语一行 catalog。
# Row: name|depth|width.
QUEUE_RAM_ROWS: tuple[str, ...] = (
    "ram_10x288|10|288",
    "ram_16x11|16|11",
    "ram_16x25|16|25",
    "ram_16x6|16|6",
    "ram_16x67|16|67",
    "ram_2x10|2|10",
    "ram_2x116|2|116",
    "ram_2x117|2|117",
    "ram_2x119|2|119",
    "ram_2x132|2|132",
    "ram_2x135|2|135",
    "ram_2x136|2|136",
    "ram_2x16|2|16",
    "ram_2x18|2|18",
    "ram_2x2|2|2",
    "ram_2x256|2|256",
    "ram_2x273|2|273",
    "ram_2x274|2|274",
    "ram_2x275|2|275",
    "ram_2x276|2|276",
    "ram_2x281|2|281",
    "ram_2x283|2|283",
    "ram_2x284|2|284",
    "ram_2x289|2|289",
    "ram_2x3|2|3",
    "ram_2x309|2|309",
    "ram_2x312|2|312",
    "ram_2x315|2|315",
    "ram_2x324|2|324",
    "ram_2x345|2|345",
    "ram_2x348|2|348",
    "ram_2x35|2|35",
    "ram_2x350|2|350",
    "ram_2x351|2|351",
    "ram_2x352|2|352",
    "ram_2x354|2|354",
    "ram_2x355|2|355",
    "ram_2x356|2|356",
    "ram_2x359|2|359",
    "ram_2x361|2|361",
    "ram_2x362|2|362",
    "ram_2x37|2|37",
    "ram_2x373|2|373",
    "ram_2x374|2|374",
    "ram_2x406|2|406",
    "ram_2x407|2|407",
    "ram_2x51|2|51",
    "ram_2x56|2|56",
    "ram_2x61|2|61",
    "ram_2x7|2|7",
    "ram_2x71|2|71",
    "ram_2x72|2|72",
    "ram_2x73|2|73",
    "ram_2x77|2|77",
    "ram_2x79|2|79",
    "ram_2x80|2|80",
    "ram_2x81|2|81",
    "ram_2x87|2|87",
    "ram_40x47|40|47",
    "ram_4x11|4|11",
    "ram_4x52|4|52",
    "ram_4x525|4|525",
    "ram_5x119|5|119",
    "ram_68x11|68|11",
    "ram_6x257|6|257",
    "ram_8x12|8|12",
    "ram_8x525|8|525",
    "ram_9x318|9|318",
    "ram_9x504|9|504",
    "ram_data_16x256|16|256",
    "ram_extra_id_4x3|4|3",
    "ram_extra_id_5x3|5|3",
    "ram_sink_2x6|2|6",
    "ram_sink_2x8|2|8",
)


# Every locked PipeWithFlush instance, one catalog row each. / 每个锁定的 PipeWithFlush 实例一行 catalog。
# Row: name|fields|flush|latency|rules|shifts.
PIPE_INSTANCE_ROWS: tuple[str, ...] = (
    "PipeWithFlush|fuType:35,pdest:8,rfWen:1,loadDependency_0:2,loadDependency_1:2,loadDependency_2:2||0||",
    "PipeWithFlush_1|fuType:35,robIdx_flag:1,robIdx_value:8,pdest:8,rfWen:1,loadDependency_0:2,loadDependency_1:2,loadDependency_2:2|redirect_valid:1,redirect_bits_robIdx_flag:1,redirect_bits_robIdx_value:8,redirect_bits_level:1,ldCancel_0_ld2Cancel:1,ldCancel_1_ld2Cancel:1,ldCancel_2_ld2Cancel:1,og0Fail:1|2|rol|s:loadDependency_0,loadDependency_1,loadDependency_2",
    "PipeWithFlush_10|robIdx_flag:1,robIdx_value:8,pdest:8,fpWen:1||1||",
    "PipeWithFlush_11|robIdx_flag:1,robIdx_value:8,pdest:8,fpWen:1|redirect_valid:1,redirect_bits_robIdx_flag:1,redirect_bits_robIdx_value:8,redirect_bits_level:1,og0Fail:1|3|ro,r|;",
    "PipeWithFlush_6|fuType:35,robIdx_flag:1,robIdx_value:8,pdest:8,fpWen:1,vecWen:1,v0Wen:1||1||",
    "PipeWithFlush_7|fuType:35,robIdx_flag:1,robIdx_value:8,pdest:8,fpWen:1,vecWen:1,v0Wen:1|redirect_valid:1,redirect_bits_robIdx_flag:1,redirect_bits_robIdx_value:8,redirect_bits_level:1,og0Fail:1|2|ro|",
    "PipeWithFlush_8|fuType:35,pdest:8,fpWen:1,vecWen:1,v0Wen:1||0||",
    "PipeWithFlush_9|fuType:35,robIdx_flag:1,robIdx_value:8,pdest:8,fpWen:1,vecWen:1,v0Wen:1|redirect_valid:1,redirect_bits_robIdx_flag:1,redirect_bits_robIdx_value:8,redirect_bits_level:1,og0Fail:1|3|ro,r|;",
)
# Report the locked enqueue port of one payload field. / 返回某个载荷字段的锁定入队端口。
def enqueue_port_name(field: str) -> str:
    """Return the pinned enqueue port name of ``field``. / 返回 ``field`` 钉死的入队端口名。"""

    # A whole-vector payload carries no field suffix, so its pinned port is
    # exactly ``io_enq_bits``. / 整向量载荷没有字段后缀，其钉死端口正是 ``io_enq_bits``。
    return "io_enq_bits" if field == "" else "io_enq_bits_" + field


# Report the locked dequeue port of one payload field. / 返回某个载荷字段的锁定出队端口。
def dequeue_port_name(field: str) -> str:
    """Return the pinned dequeue port name of ``field``. / 返回 ``field`` 钉死的出队端口名。"""

    return "io_deq_bits" if field == "" else "io_deq_bits_" + field


@dataclass(frozen=True)
class QueueInstanceSpec:
    """One locked ``Queue<N>_<Type>`` instance of the V2 Decoupled family. / V2 Decoupled family 中的一个锁定 ``Queue<N>_<Type>`` 实例。"""

    module: str
    entries: int
    flow: bool
    pipe: bool
    flush: bool
    count: bool
    has_enq_ready: bool
    has_enq_valid: bool
    has_deq_ready: bool
    has_deq_valid: bool
    word_bits: int
    payload: tuple[tuple[str | None, int, int | None], ...]
    enq_fields: tuple[tuple[str, int], ...]
    deq_fields: tuple[tuple[str, int, int], ...]
    flow_defaults: tuple[tuple[str, int], ...]

    # Reject geometry that the locked artifact never contains. / 拒绝锁定产物中不存在的几何参数。
    def __post_init__(self) -> None:
        if self.entries < 1:
            raise ValueError("queue entries must be positive")
        if self.pipe and self.entries != 1:
            raise ValueError("the locked pipe bypass only occurs on single-entry queues")
        if self.count and self.entries < 2:
            raise ValueError("io_count requires at least two entries")
        if self.flow and not self.has_enq_valid:
            raise ValueError("a flow queue needs its enqueue valid")
        if sum(width for _, width, _ in self.payload) != self.word_bits:
            raise ValueError("payload widths must sum to the stored word width")
        for name, _, width in self.deq_fields:
            if width < 1:
                raise ValueError("dequeue field widths must be positive")
            if self.flow and name not in [item for item, _ in self.flow_defaults]:
                if name not in [field for field, _ in self.enq_fields]:
                    raise ValueError("a flow field needs an override or a matching enqueue field")
        for name, value in self.flow_defaults:
            if value < 0:
                raise ValueError("flow defaults must be non-negative")

    # Report the pointer width used by the ring pointers. / 返回环形指针使用的指针宽度。
    @property
    def pointer_bits(self) -> int:
        """Return ``ceil(log2(entries))``, matching the Chisel ``Counter`` width. / 返回 ``ceil(log2(entries))``，与 Chisel ``Counter`` 宽度一致。"""

        return max(1, (self.entries - 1).bit_length())

    # Report the ``io_count`` port width of the locked instance. / 返回锁定实例的 ``io_count`` 端口宽度。
    @property
    def count_bits(self) -> int:
        """Return 0 when ``io_count`` is absent, else the locked port width. / ``io_count`` 缺失时返回 0，否则返回锁定端口宽度。"""

        if not self.count:
            return 0
        if self.entries & (self.entries - 1) == 0:
            return self.pointer_bits + 1
        return self.pointer_bits

    # List the exact locked port surface in declaration order. / 按声明顺序列出精确的锁定端口面。
    def locked_ports(self) -> list[tuple[str, str, int]]:
        """Return ``(name, direction, width)`` triples of the pinned artifact. / 返回钉死产物的 ``(名称, 方向, 宽度)`` 三元组。"""

        ports: list[tuple[str, str, int]] = [("clock", "input", 1), ("reset", "input", 1)]
        if self.has_enq_ready:
            ports.append(("io_enq_ready", "output", 1))
        if self.has_enq_valid:
            ports.append(("io_enq_valid", "input", 1))
        ports.extend(
            (enqueue_port_name(name), "input", width) for name, width in self.enq_fields)
        if self.has_deq_ready:
            ports.append(("io_deq_ready", "input", 1))
        if self.has_deq_valid:
            ports.append(("io_deq_valid", "output", 1))
        ports.extend(
            (dequeue_port_name(name), "output", width) for name, _, width in self.deq_fields)
        if self.count:
            ports.append(("io_count", "output", self.count_bits))
        if self.flush:
            ports.append(("io_flush", "input", 1))
        return ports


@dataclass(frozen=True)
class QueueRamSpec:
    """One locked queue memory primitive ``ram_<depth>x<width>``. / 一个锁定的队列存储器原语 ``ram_<depth>x<width>``。"""

    module: str
    depth: int
    width: int

    # Reject degenerate memory geometry. / 拒绝退化存储器几何。
    def __post_init__(self) -> None:
        if self.depth < 2 or self.width < 1:
            raise ValueError("queue ram geometry must have at least two words")

    # Report the read/write address width of the locked primitive. / 返回锁定原语的读写地址宽度。
    @property
    def address_bits(self) -> int:
        """Return ``ceil(log2(depth))``, matching the pinned ``R0_addr`` width. / 返回 ``ceil(log2(depth))``，与钉死的 ``R0_addr`` 宽度一致。"""

        return (self.depth - 1).bit_length()


@dataclass(frozen=True)
class PipeInstanceSpec:
    """One locked ``PipeWithFlush`` pipeline instance. / 一个锁定的 ``PipeWithFlush`` 流水线实例。"""

    module: str
    latency: int
    fields: tuple[tuple[str, int], ...]
    flush_fields: tuple[tuple[str, int], ...]
    stage_rules: tuple[str, ...]
    stage_shifts: tuple[tuple[str, ...], ...]

    # Reject pipeline geometry the locked artifact never contains. / 拒绝锁定产物中不存在的流水线几何。
    def __post_init__(self) -> None:
        if self.latency < 0:
            raise ValueError("pipe latency must be non-negative")
        if len(self.stage_rules) != max(0, self.latency - 1):
            raise ValueError("one flush rule is required per flushed stage")
        if len(self.stage_shifts) != max(0, self.latency - 1):
            raise ValueError("one modification entry is required per flushed stage")
        for rule in self.stage_rules:
            if rule not in PIPE_FLUSH_RULES:
                raise ValueError("unknown pipeline flush rule")

    # List the exact locked port surface in declaration order. / 按声明顺序列出精确的锁定端口面。
    def locked_ports(self) -> list[tuple[str, str, int]]:
        """Return ``(name, direction, width)`` triples of the pinned artifact. / 返回钉死产物的 ``(名称, 方向, 宽度)`` 三元组。"""

        ports: list[tuple[str, str, int]] = []
        if self.latency > 0:
            ports.extend([("clock", "input", 1), ("reset", "input", 1)])
        ports.extend(("io_flush_" + name, "input", width) for name, width in self.flush_fields)
        ports.append(("io_enq_valid", "input", 1))
        ports.extend(("io_enq_bits_" + name, "input", width) for name, width in self.fields)
        ports.append(("io_deq_valid", "output", 1))
        ports.extend(("io_deq_bits_" + name, "output", width) for name, width in self.fields)
        return ports


@dataclass(frozen=True)
class QueueConfig:
    """Selection record for one deterministic family export. / 单次确定性 family 导出的选择记录。"""

    module: str = "Queue2_UInt2"
    top_name: str = "UHSCChiselQueueFamily"

    # Reject an export name that could not be a Verilog module identifier. / 拒绝不能作为 Verilog 模块标识符的导出名。
    def __post_init__(self) -> None:
        for text in (self.module, self.top_name):
            if not text or not text.replace("_", "a").isalnum() or not text[0].isalpha():
                raise ValueError("module and top_name must be Verilog identifiers")


# =============================================================================
# Implementation
# =============================================================================
# Split a comma separated ``name:width`` catalog list. / 拆分逗号分隔的 ``name:width`` catalog 列表。
def split_widened(text: str) -> tuple[tuple[str, int], ...]:
    """Return the ``(name, width)`` pairs encoded in a catalog list. / 返回 catalog 列表中编码的 ``(名称, 宽度)`` 对。"""

    if text in ("-", ""):
        return ()
    pairs = []
    for item in text.split(","):
        name, width = item.rsplit(":", 1)
        pairs.append((name, int(width)))
    return tuple(pairs)


# Parse the packed stored-word layout of one queue row. / 解析一条队列行中打包的存储字布局。
def parse_payload(text: str) -> tuple[tuple[str | None, int, int | None], ...]:
    """Return the LSB-first ``(field, width, constant)`` layout of the stored word. / 返回存储字按 LSB 优先的 ``(字段, 宽度, 常量)`` 布局。"""

    if text == "-":
        return ()
    layout: list[tuple[str | None, int, int | None]] = []
    for item in text.split(","):
        name, width = item.rsplit(":", 1)
        if name.startswith("="):
            layout.append((None, int(width), int(name[1:], 16)))
        else:
            layout.append((name, int(width), None))
    return tuple(layout)


# Parse the ``name:offset:width`` slices exposed on the dequeue side. / 解析出队侧暴露的 ``name:offset:width`` 切片。
def parse_deq_fields(text: str) -> tuple[tuple[str, int, int], ...]:
    """Return the dequeue field slices of one queue row. / 返回一条队列行的出队字段切片。"""

    if text == "-":
        return ()
    fields = []
    for item in text.split(","):
        name, offset, width = item.split(":")
        fields.append((name, int(offset), int(width)))
    return tuple(fields)


# Parse the flow-through constants overriding the enqueue fields. / 解析覆盖入队字段的直通常量。
def parse_flow_defaults(text: str) -> tuple[tuple[str, int], ...]:
    """Return the empty-state override values of a flow queue. / 返回 flow 队列空态的覆盖取值。"""

    if text == "-":
        return ()
    pairs = []
    for item in text.split(","):
        name, value = item.split("=")
        pairs.append((name, int(value, 0)))
    return tuple(pairs)


# Build one locked queue instance record from its catalog row. / 从 catalog 行构造一个锁定队列实例记录。
def parse_queue_instance(row: str) -> QueueInstanceSpec:
    """Decode one ``name|entries|flags|word|payload|enq|deq|flow`` catalog row. / 解码一条 catalog 队列行。"""

    name, entries, flags, word, payload, enq, deq, flow = row.split("|")
    structure = flags[len(HANDSHAKE_FLAG_NAMES):]
    return QueueInstanceSpec(
        module=name,
        entries=int(entries),
        flow="f" in structure,
        pipe="p" in structure,
        flush="l" in structure,
        count="c" in structure,
        has_enq_ready=flags[0] == "1",
        has_enq_valid=flags[1] == "1",
        has_deq_ready=flags[2] == "1",
        has_deq_valid=flags[3] == "1",
        word_bits=int(word),
        payload=parse_payload(payload),
        enq_fields=split_widened(enq),
        deq_fields=parse_deq_fields(deq),
        flow_defaults=parse_flow_defaults(flow),
    )


# Build one locked queue memory record from its catalog row. / 从 catalog 行构造一个锁定队列存储器记录。
def parse_queue_ram(row: str) -> QueueRamSpec:
    """Decode one ``name|depth|width`` catalog row. / 解码一条 catalog 存储器行。"""

    name, depth, width = row.split("|")
    return QueueRamSpec(module=name, depth=int(depth), width=int(width))


# Build one locked pipeline record from its catalog row. / 从 catalog 行构造一个锁定流水线记录。
def parse_pipe_instance(row: str) -> PipeInstanceSpec:
    """Decode one ``name|fields|flush|latency|rules|shifts`` catalog row. / 解码一条 catalog 流水线行。"""

    name, fields, flush, latency, rules, shifts = row.split("|")
    stages = max(0, int(latency) - 1)
    stage_rules = tuple(rules.split(",")) if stages else ()
    stage_shifts = (tuple(() if item == "" else tuple(item[2:].split(","))
                          for item in shifts.split(";")) if stages else ())
    return PipeInstanceSpec(
        module=name,
        latency=int(latency),
        fields=split_widened(fields),
        flush_fields=split_widened(flush),
        stage_rules=stage_rules,
        stage_shifts=stage_shifts,
    )


# Materialise the locked queue instances at import time. / 在导入时物化锁定的队列实例。
def queue_instances() -> tuple[QueueInstanceSpec, ...]:
    """Return every locked ``Queue*`` instance covered by this family file. / 返回本 family 文件覆盖的所有锁定 ``Queue*`` 实例。"""

    return tuple(parse_queue_instance(row) for row in QUEUE_INSTANCE_ROWS)


# Materialise the locked queue memories at import time. / 在导入时物化锁定的队列存储器。
def queue_ram_instances() -> tuple[QueueRamSpec, ...]:
    """Return every locked queue memory primitive covered by this file. / 返回本文件覆盖的所有锁定队列存储器原语。"""

    return tuple(parse_queue_ram(row) for row in QUEUE_RAM_ROWS)


# Materialise the locked pipeline instances at import time. / 在导入时物化锁定的流水线实例。
def pipe_instances() -> tuple[PipeInstanceSpec, ...]:
    """Return every locked ``PipeWithFlush`` instance covered by this file. / 返回本文件覆盖的所有锁定 ``PipeWithFlush`` 实例。"""

    return tuple(parse_pipe_instance(row) for row in PIPE_INSTANCE_ROWS)


# Select one queue instance by its locked module name. / 按锁定模块名选择一个队列实例。
def queue_instance(name: str) -> QueueInstanceSpec:
    """Return the locked queue instance named ``name``. / 返回名为 ``name`` 的锁定队列实例。"""

    for spec in queue_instances():
        if spec.module == name:
            return spec
    raise KeyError(name)


# Select one queue memory by its locked module name. / 按锁定模块名选择一个队列存储器。
def queue_ram_instance(name: str) -> QueueRamSpec:
    """Return the locked queue memory named ``name``. / 返回名为 ``name`` 的锁定队列存储器。"""

    for spec in queue_ram_instances():
        if spec.module == name:
            return spec
    raise KeyError(name)


# Report the locked port surface of a queue instance. / 返回队列实例的锁定端口面。
def chisel_queue_ports(name: str) -> list[tuple[str, str, int]]:
    """Return the pinned ``(name, direction, width)`` list of ``name``. / 返回 ``name`` 钉死的 ``(名称, 方向, 宽度)`` 列表。"""

    return queue_instance(name).locked_ports()


# Describe the BundleMap payload carried by a ``Queue<N>_BundleMap`` instance. / 描述 ``Queue<N>_BundleMap`` 实例携带的 BundleMap 载荷。
def bundle_map_payload(name: str) -> tuple[tuple[str, int], ...]:
    """Return the stored BundleMap fields of a ``Queue<N>_BundleMap`` instance. / 返回 ``Queue<N>_BundleMap`` 实例存储的 BundleMap 字段。"""

    spec = queue_instance(name)
    if not spec.module.endswith("_BundleMap"):
        raise KeyError(name)
    return tuple((field, width) for field, width, _ in spec.payload if field is not None)


class ChiselQueue(Elaboratable):
    """Faithful Amaranth model of the parameterised Chisel ``Queue``. / 参数化 Chisel ``Queue`` 的忠实 Amaranth 模型。"""

    # Resolve runtime-created port attributes for static type checking. / 为静态类型检查解析运行时创建的端口属性。
    def __getattr__(self, name: str) -> Signal:
        raise AttributeError(name)

    # Construct the locked port surface of one queue instance. / 构造一个队列实例的锁定端口面。
    def __init__(self, spec: QueueInstanceSpec, top_name: str = "UHSCChiselQueue") -> None:
        self.spec = spec
        self.top_name = top_name
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.enq_ready: Signal | None = Signal(name="io_enq_ready") if spec.has_enq_ready else None
        self.enq_valid: Signal | None = Signal(name="io_enq_valid") if spec.has_enq_valid else None
        self.deq_ready: Signal | None = Signal(name="io_deq_ready") if spec.has_deq_ready else None
        self.deq_valid: Signal | None = Signal(name="io_deq_valid") if spec.has_deq_valid else None
        self.flush_in: Signal | None = Signal(name="io_flush") if spec.flush else None
        self.count_out: Signal | None = Signal(spec.count_bits, name="io_count") if spec.count else None
        self.enq_bits: dict[str, Signal] = {
            name: Signal(width, name=enqueue_port_name(name)) for name, width in spec.enq_fields}
        self.deq_bits: dict[str, Signal] = {
            name: Signal(width, name=dequeue_port_name(name))
            for name, _, width in spec.deq_fields}
        self.port_surface: list[Signal] = [self.clock, self.reset]
        for signal in (self.enq_ready, self.enq_valid):
            if signal is not None:
                self.port_surface.append(signal)
        self.port_surface.extend(self.enq_bits[name] for name, _ in spec.enq_fields)
        for signal in (self.deq_ready, self.deq_valid):
            if signal is not None:
                self.port_surface.append(signal)
        self.port_surface.extend(self.deq_bits[name] for name, _, _ in spec.deq_fields)
        for signal in (self.count_out, self.flush_in):
            if signal is not None:
                self.port_surface.append(signal)

    # Elaborate the ring pointers, occupancy flags, storage and payload slices. / 展开环形指针、占用标志、存储与载荷切片。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the Decoupled queue equations. / 展开 Decoupled 队列方程。"""

        del platform
        spec = self.spec
        # The control flow builder is a generated context manager in Amaranth;
        # type it locally while keeping the exact Module object at runtime.
        # Amaranth 的控制流构造器是生成的上下文管理器；在此局部标注类型，
        # 运行时仍保持完全相同的 Module 对象。
        m: Any = Module()
        domain = ClockDomain("queue", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.queue = domain
        single = spec.entries == 1
        maybe_full = Signal(name="maybe_full")
        enq_ptr: Any = Const(0, 1)
        deq_ptr: Any = Const(0, 1)
        if not single:
            enq_ptr = Signal(spec.pointer_bits, name="enq_ptr_value")
            deq_ptr = Signal(spec.pointer_bits, name="deq_ptr_value")
        ptr_match: Any = Const(1, 1) if single else cast(Any, enq_ptr) == cast(Any, deq_ptr)
        empty: Any = ~maybe_full if single else cast(Any, ptr_match) & ~maybe_full
        full: Any = maybe_full if single else cast(Any, ptr_match) & maybe_full
        enq_valid: Any = self.enq_valid if self.enq_valid is not None else Const(0, 1)
        deq_ready: Any = self.deq_ready if self.deq_ready is not None else Const(0, 1)
        enq_ready: Any = (~full | deq_ready) if spec.pipe else ~cast(Any, full)
        deq_valid: Any = (cast(Any, enq_valid) | ~empty) if spec.flow else ~cast(Any, empty)
        if self.enq_ready is not None:
            m.d.comb += self.enq_ready.eq(enq_ready)
        if self.deq_valid is not None:
            m.d.comb += self.deq_valid.eq(deq_valid)

        # Enqueue and dequeue fire exactly as the pinned expressions do. / 入队与出队触发严格遵循钉死表达式。
        flow_pass = (cast(Any, empty) & deq_ready) if spec.flow else Const(0, 1)
        do_enq: Any = cast(Any, enq_ready) & enq_valid & ~cast(Any, flow_pass)
        do_deq: Any = ~cast(Any, empty) & deq_ready

        # Storage: one register for a single entry, a Decoupled memory otherwise.
        # 存储：单条目使用一个寄存器，其余使用 Decoupled 存储器。
        write_word = self.pack_enqueue_word()
        read_data: Any = Const(0, 1)
        if spec.word_bits == 0:
            pass
        elif single:
            # The pinned single-entry storage is a bare ``Reg`` with no reset
            # assignment; it keeps its value across a mid-run reset.
            # 钉死的单条目存储是无复位赋值的裸 ``Reg``；运行中复位时保持原值。
            ram = Signal(spec.word_bits, name="ram", reset_less=True)
            with m.If(do_enq):
                m.d.queue += ram.eq(write_word)
            read_data = ram
        else:
            memory = Memory(width=spec.word_bits, depth=spec.entries, init=[])
            write_port = memory.write_port(domain="queue")
            read_port = memory.read_port(domain="comb")
            m.submodules.queue_memory = memory
            m.d.comb += [read_port.addr.eq(deq_ptr),
                         write_port.addr.eq(enq_ptr), write_port.en.eq(do_enq),
                         write_port.data.eq(write_word)]
            read_data = read_port.data
        self.connect_dequeue(m, read_data, empty)

        # Ring pointer and occupancy update, including the flush reset. / 环形指针与占用更新，含 flush 复位。
        next_enq: Any = cast(Any, enq_ptr) + 1
        next_deq: Any = cast(Any, deq_ptr) + 1
        if not single and spec.entries & (spec.entries - 1):
            next_enq = Mux(cast(Any, enq_ptr) == spec.entries - 1, 0, cast(Any, enq_ptr) + 1)
            next_deq = Mux(cast(Any, deq_ptr) == spec.entries - 1, 0, cast(Any, deq_ptr) + 1)
        flush_in: Any = self.flush_in if self.flush_in is not None else Const(0, 1)
        if spec.flush:
            with m.If(cast(Any, flush_in)):
                m.d.queue += maybe_full.eq(0)
                if not single:
                    m.d.queue += [enq_ptr.eq(0), deq_ptr.eq(0)]
            with m.Else():
                self.emit_pointer_updates(m, do_enq, do_deq, enq_ptr, deq_ptr, next_enq, next_deq, maybe_full)
        else:
            self.emit_pointer_updates(m, do_enq, do_deq, enq_ptr, deq_ptr, next_enq, next_deq, maybe_full)
        self.connect_count(m, ptr_match, maybe_full, enq_ptr, deq_ptr)
        return m

    # Emit the conditional pointer and occupancy register updates. / 发出条件化的指针与占用寄存器更新。
    def emit_pointer_updates(self, m: Any, do_enq: Any, do_deq: Any, enq_ptr: Any, deq_ptr: Any,
                             next_enq: Any, next_deq: Any, maybe_full: Signal) -> None:
        """Emit enqueue, dequeue and occupancy updates under their fire conditions. / 在各自触发条件下发出入队、出队与占用更新。"""

        if self.spec.entries > 1:
            with m.If(do_enq):
                m.d.queue += enq_ptr.eq(next_enq)
            with m.If(do_deq):
                m.d.queue += deq_ptr.eq(next_deq)
        with m.If(do_enq != do_deq):
            m.d.queue += maybe_full.eq(do_enq)

    # Pack the enqueue side into the locked stored-word layout. / 将入队侧按锁定存储字布局打包。
    def pack_enqueue_word(self) -> Any:
        """Return the stored word built from the present enqueue fields. / 返回由存在的入队字段构造的存储字。"""

        # Enqueue fields the pinned store does not keep stay unused inputs,
        # exactly as the artifact leaves them. / 钉死存储不保留的入队字段保持为
        # 未使用输入，与产物行为完全一致。
        spec = self.spec
        word: Any = Const(0, spec.word_bits)
        position = 0
        for field, width, constant in spec.payload:
            if constant is not None:
                word = cast(Any, word) | (Const(constant, width) << position)
            elif field is not None and field in self.enq_bits:
                word = cast(Any, word) | (cast(Any, self.enq_bits[field]) << position)
            position += width
        return word

    # Drive every dequeue payload field from the locked slice map. / 按锁定切片映射驱动每一个出队载荷字段。
    def connect_dequeue(self, m: Module, read_data: Any, empty: Any) -> None:
        """Connect ``io_deq_bits_*`` to the stored word or the flow-through value. / 将 ``io_deq_bits_*`` 连到存储字或直通值。"""

        spec = self.spec
        defaults = dict(spec.flow_defaults)
        for name, offset, width in spec.deq_fields:
            signal = self.deq_bits[name]
            if offset < 0:
                m.d.comb += signal.eq(Const(0, width))
                continue
            stored: Any = cast(Any, read_data)[offset:offset + width]
            if not spec.flow:
                m.d.comb += signal.eq(stored)
                continue
            fallback: Any = Const(0, width)
            if name in defaults:
                fallback = Const(defaults[name], width)
            elif name in self.enq_bits:
                fallback = self.enq_bits[name]
            m.d.comb += signal.eq(Mux(~cast(Any, empty), stored, fallback))

    # Drive the locked occupancy count output with the pinned formula. / 以钉死公式驱动锁定的占用计数输出。
    def connect_count(self, m: Module, ptr_match: Any, maybe_full: Signal, enq_ptr: Any, deq_ptr: Any) -> None:
        """Connect ``io_count`` for the power-of-two and wrap cases. / 为 2 的幂与回绕情形连接 ``io_count``。"""

        spec = self.spec
        if self.count_out is None:
            return
        difference: Any = cast(Any, enq_ptr) - cast(Any, deq_ptr)
        if spec.entries & (spec.entries - 1) == 0:
            value: Any = Cat(difference, maybe_full & ptr_match)
        else:
            offset = (1 << spec.pointer_bits) - spec.entries
            value = Mux(ptr_match, Mux(maybe_full, spec.entries, 0),
                        Mux(cast(Any, deq_ptr) > cast(Any, enq_ptr), difference - offset, difference))
        m.d.comb += self.count_out.eq(value)


class QueueRam(Elaboratable):
    """Faithful Amaranth model of the locked ``ram_<N>x<W>`` queue memory. / 锁定 ``ram_<N>x<W>`` 队列存储器的忠实 Amaranth 模型。"""

    # Construct the synchronous-write, combinational-read queue memory. / 构造同步写、组合读的队列存储器。
    def __init__(self, spec: QueueRamSpec, top_name: str = "UHSCQueueRam") -> None:
        self.spec = spec
        self.top_name = top_name
        self.read_address = Signal(spec.address_bits, name="R0_addr")
        self.read_enable = Signal(name="R0_en")
        self.read_clock = Signal(name="R0_clk")
        self.read_data = Signal(spec.width, name="R0_data")
        self.write_address = Signal(spec.address_bits, name="W0_addr")
        self.write_enable = Signal(name="W0_en")
        self.write_clock = Signal(name="W0_clk")
        self.write_data = Signal(spec.width, name="W0_data")
        self.port_surface: list[Signal] = [
            self.read_address, self.read_enable, self.read_clock, self.read_data,
            self.write_address, self.write_enable, self.write_clock, self.write_data]

    # Elaborate the memory array and its synchronous write, combinational read ports.
    # 展开存储器阵列及其同步写、组合读端口。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the queue memory primitive. / 展开队列存储器原语。"""

        del platform
        m = Module()
        # The pinned primitive has no reset; the storage clock domain is given a
        # tied-off reset so that the write port stays purely synchronous.
        # 钉死原语没有复位；存储时钟域使用恒零复位，使写端口保持纯同步。
        queue_reset = Signal(name="queue_reset")
        domain = ClockDomain("queue", async_reset=True)
        domain.clk = self.write_clock
        domain.rst = queue_reset
        m.domains.queue = domain
        m.d.comb += queue_reset.eq(0)
        memory = Memory(width=self.spec.width, depth=self.spec.depth, init=[])
        write_port = memory.write_port(domain="queue")
        read_port = memory.read_port(domain="comb")
        m.submodules.memory = memory
        # ``R0_en`` is always high in the queue; the pinned primitive would drive
        # ``x`` when low, which a deterministic two-state model reads as zero.
        # 队列中 ``R0_en`` 恒为高；钉死原语在低电平时输出 ``x``，确定性二态模型读作零。
        m.d.comb += [read_port.addr.eq(self.read_address),
                     self.read_data.eq(Mux(self.read_enable, read_port.data, 0)),
                     write_port.addr.eq(self.write_address),
                     write_port.en.eq(self.write_enable),
                     write_port.data.eq(self.write_data)]
        return m


class ChiselPipeWithFlush(Elaboratable):
    """Faithful Amaranth model of the XiangShan ``PipeWithFlush`` generator. / XiangShan ``PipeWithFlush`` 生成器的忠实 Amaranth 模型。"""

    # Construct the locked valid/bits pipeline of one instance. / 构造一个实例的锁定 valid/bits 流水线。
    def __init__(self, spec: PipeInstanceSpec, top_name: str = "UHSCChiselPipeWithFlush") -> None:
        self.spec = spec
        self.top_name = top_name
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.enq_valid = Signal(name="io_enq_valid")
        self.deq_valid = Signal(name="io_deq_valid")
        self.enq_bits: dict[str, Signal] = {
            name: Signal(width, name="io_enq_bits_" + name) for name, width in spec.fields}
        self.deq_bits: dict[str, Signal] = {
            name: Signal(width, name="io_deq_bits_" + name) for name, width in spec.fields}
        self.flush_ports: dict[str, Signal] = {
            name: Signal(width, name="io_flush_" + name) for name, width in spec.flush_fields}
        self.port_surface: list[Signal] = []
        if spec.latency > 0:
            self.port_surface.extend([self.clock, self.reset])
        self.port_surface.extend(self.flush_ports[name] for name, _ in spec.flush_fields)
        self.port_surface.append(self.enq_valid)
        self.port_surface.extend(self.enq_bits[name] for name, _ in spec.fields)
        self.port_surface.append(self.deq_valid)
        self.port_surface.extend(self.deq_bits[name] for name, _ in spec.fields)

    # Elaborate the register chain and its per-stage flush gating. / 展开寄存器链及其逐级 flush 门控。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate the pipeline valid/bits chain. / 展开流水线 valid/bits 链。"""

        del platform
        spec = self.spec
        # Same localised typing as the queue: generated context manager at
        # runtime, exact Module instance preserved.
        # 与队列相同的局部类型标注：运行时是生成的上下文管理器，
        # 保留完全相同的 Module 实例。
        m: Any = Module()
        if spec.latency == 0:
            m.d.comb += self.deq_valid.eq(self.enq_valid)
            m.d.comb += [self.deq_bits[name].eq(self.enq_bits[name]) for name, _ in spec.fields]
            return m
        domain = ClockDomain("pipe", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.pipe = domain
        valids = [Signal(name="valids_%d" % index) for index in range(1, spec.latency + 1)]
        stages = [{name: Signal(width, name="bits_%d_%s" % (index, name)) for name, width in spec.fields}
                  for index in range(1, spec.latency + 1)]
        m.d.comb += self.deq_valid.eq(valids[-1])
        m.d.comb += [self.deq_bits[name].eq(stages[-1][name]) for name, _ in spec.fields]
        previous_valid: Any = self.enq_valid
        previous_bits: dict[str, Signal] = self.enq_bits
        for index in range(1, spec.latency + 1):
            if index == 1:
                m.d.pipe += valids[0].eq(previous_valid)
            else:
                gate = self.flush_condition(spec.stage_rules[index - 2], stages[index - 2])
                m.d.pipe += valids[index - 1].eq(cast(Any, previous_valid) & ~gate)
            with m.If(previous_valid):
                m.d.pipe += [stages[index - 1][name].eq(self.modify_stage(index, name, previous_bits))
                             for name, _ in spec.fields]
            previous_valid = valids[index - 1]
            previous_bits = stages[index - 1]
        return m

    # Build the redirect/flush predicate of one pipeline stage. / 构造某一流水线级的 redirect/flush 谓词。
    def flush_condition(self, rule: str, stage_bits: dict[str, Signal]) -> Any:
        """Return the stage flush predicate described by ``rule``. / 返回 ``rule`` 描述的该级 flush 谓词。"""

        ports = self.flush_ports
        if "redirect_valid" not in ports:
            return Const(0, 1)
        rob_flag = stage_bits["robIdx_flag"]
        rob_value = stage_bits["robIdx_value"]
        redirect_flag = ports["redirect_bits_robIdx_flag"]
        redirect_value = ports["redirect_bits_robIdx_value"]
        match: Any = Cat(rob_flag, rob_value) == Cat(redirect_flag, redirect_value)
        order: Any = rob_flag ^ redirect_flag ^ (rob_value > redirect_value)
        condition: Any = ports["redirect_valid"] & (Mux(ports["redirect_bits_level"], match, 0) | order)
        if rule == "r":
            return condition
        if "og0Fail" in ports:
            condition = cast(Any, condition) | ports["og0Fail"]
        if rule == "rol":
            for name, port in ports.items():
                if not name.endswith("_ld2Cancel"):
                    continue
                dependency = stage_bits.get("loadDependency_" + name.split("_")[1])
                if dependency is not None:
                    condition = cast(Any, condition) | (port & dependency[1])
        return condition

    # Apply the per-stage modification function to one payload field. / 对某一载荷字段应用该级的修改函数。
    def modify_stage(self, index: int, name: str, previous_bits: dict[str, Signal]) -> Any:
        """Return the stage modification of one field, identity unless shifted. / 返回该级对某字段的修改，未移位时保持恒等。"""

        shifts = self.spec.stage_shifts[index - 2] if index >= 2 else ()
        if name in shifts:
            return Cat(previous_bits[name][0], 0)
        return previous_bits[name]


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic UHSC-localized Verilog for one family member. / 为某个 family 成员导出确定性的 UHSC Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog text for the selected Decoupled family member. / 返回所选 Decoupled family 成员的 Verilog 文本。"""

    del injected_dependencies
    if isinstance(configuration, QueueConfig):
        cfg = configuration
    elif isinstance(configuration, dict):
        fields = QueueConfig.__dataclass_fields__
        kwargs: dict[str, Any] = {}
        for key, value in configuration.items():
            if key in fields:
                kwargs[key] = str(value)
        cfg = QueueConfig(**kwargs)
    elif configuration is None:
        cfg = QueueConfig()
    else:
        raise TypeError("configuration must be QueueConfig, dict, or None")
    member: Elaboratable
    if cfg.module.startswith("Queue"):
        member = ChiselQueue(queue_instance(cfg.module), top_name=cfg.top_name)
    elif cfg.module.startswith("ram"):
        member = QueueRam(queue_ram_instance(cfg.module), top_name=cfg.top_name)
    else:
        member = ChiselPipeWithFlush(next(spec for spec in pipe_instances() if spec.module == cfg.module),
                                     top_name=cfg.top_name)
    ports = cast(Any, member).port_surface
    return verilog.convert(member, name=cfg.top_name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export for direct smoke tests. / 为 direct smoke 测试打印确定性默认导出。
def main() -> None:
    """Print the default family export. / 打印默认 family 导出。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
