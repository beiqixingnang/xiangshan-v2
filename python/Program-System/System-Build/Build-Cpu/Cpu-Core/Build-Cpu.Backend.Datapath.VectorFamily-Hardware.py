"""UHSC V2 vector datapath family aggregate.

Bounded,搬运-ready surfaces for the three vector datapath closures that are
visible as independent modules in the locked Kunminghu V2 hierarchy. The
port catalog is content-addressed from that hierarchy; behavior is kept
reset-safe and deterministic until the parent differential closure is run.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog

__all__ = [
    'COVERED_MODULES',
    'PORT_SPECS',
    'Og2ForVector',
    'VTypeBuffer',
    'VecExcpDataMergeModule',
    'VIAluSrcTypeModule',
    'VIMacSrcTypeModule',
    'VPermSrcTypeModule',
    'VectorDatapathFamily',
    'vector_datapath_model',
    'build_verilog',
    'main',
]

COVERED_MODULES: tuple[str, ...] = (
    "Og2ForVector",
    "VTypeBuffer",
    "VecExcpDataMergeModule",
    "VIAluSrcTypeModule",
    "VIMacSrcTypeModule",
    "VPermSrcTypeModule",
)

# The bytes below are zlib+base85 JSON generated from
# validation/v2-locked-hierarchy.json. Keeping this catalog in the Build
# makes the target self-contained and prevents accidental port drift.
_LOCKED_CATALOG_B85 = """c-oy^O>f&u68tYd=TI}G?Cjq15N8o!^PF|Eeup3sWNBmzp+$wH>|_`F-&bGO7s=_Wxg>B{-E2;gUDedc`R~Qega1%gcVXO=)y3bxeY+SJ<@m?Nn~T}S8~6Rqw~H#&p*i|_Rt~4dvVI&skBZr(>%jf2sfSg0|8eqb^)I6b3$seJ3|r9KHmC^Cp*TxXl}|Sh?r!?7nl+C@KSXCSZPX^=bour7Vt2l5V1jQJ2l(F%bX|>y*j3@*5@4r*y#me@aL$7JS&avDQQQ-;n1p(Fzg-#7=P>>&%(+6IK|`mD<?v;Fi8Yyeg@1k;3E)Nn*WqQ0_6)jsTJD~fj4E3xq#0EWN8$#*EEg;8Nh((Xv-<j1!`Cyb{~T3S`JzO;ubWS!`iBy7v*05pqh|D_Tvp>yZ+p_~O`i*aE;Z1n24<;&IT7f#7i4tjHHz-eM_{5m@6k+mJ^?!g>=kgPfO8hicIWc|yF2eAj=Hl2oi417yN42u{D1`wB^&u6HPOgV!Hoj88u=;OY~*KUD}|Vi`~*MU^uZ5hG5K1${e3P6=Ba^ig-ate=OmyQ)y==l1%C!gb<QFf)!B!r8qyi)QUiTzV3r!lX$U9{fubRhGz5x<K+zB=8UjT_plAqG4S}p7w8M9T!*{&HccR00io<t`!*`Oycbda@g2Q*B!*{B~cbda@vcq?}!*{a7cc~8Fr8<0<>hN8v!*{6;AC$v~;_x9kd?*edio=KE@S!+-C=MU0!-wqf!8`mz@~PEv!4Crvh5_)yzyVqa#ZvMBWp02nH$a*jpv?^s<_3s!15)P(q|OaUog1Le4N&I>$a4eqxdEwj15)P(q|OaUog0ukH-MTOpv(=B<_0Kp1C+S|%G>~DZh$g3K%E;P&kf+`1_*Nl__+b%+yG^6fHF5gnj4_a4G`uAh;swfxdGbT0C{eJJ~u#~8<09TAa!m)>fC_TxdHOr5XPUvll4;P0J3{?3ma?AXW(dO?!Y<$>ji8kU~>{{Hsx-7q$i&RL|XD0GS-pLp`eikjf{2TE^H%Ud;4$~xW5f|mMm1!--Ns1u^!xkj~d?Y#oqTuPt-G?@{1CL^`6ytMVL;x9@G4k9+w^d=yAC;18%0%{eGG}j-D@{{#joaVRsK0O|RB!uf@^}Eq!sG-nhkReT>Ap#5kWAmnFvKLfq>14dc(N2m3ZGiqUWG@eAWE`pBMKvLW~TrqEp(7}bWL+E7#*f@(uhZ3wCjLA4>MHbm8is@kAc8@y_RR&CI#4MDXbs5TVUhNRlyRU4XWLsV^ustr-K!K*eD)rP3r5LFwhYC}?ONU9A@wIQlDG}VTv+DKGwB&s$NRU3(_ojTDXLA9Z)HU!oF`1JH~J}p<PJbT*Rk(rM`4g&m|s3~`Y{`IfrW*1-;Mw7EkYGGa-LK(rF8iex5AoM}^{-8YggKq4rJt&X+SU=S9P|rg%9-4E|Q)gf<?wK(t4-(UjfAt0B;lb|)?rnit!mBH=Z-nDlt9IJGG2oyL58c{=@*q<Y?9LUG2LX(g%a^e81SVmpmcXX%=v69J$<d2c5`TD&N(Ss-qMG<_u_+^+Dxx(~m`@AK(!z2x?08Fc-?FtgRQGn+uI<!)9k#WZy1#3+wo;Q&&qFgFnsZRD!}e{U?t5Tc+ow(7>wXEd0<#sjHcs1j4AY7`HcfNThKI&map!jFzE<4cEKQbRv|?kUG<A~pc87$pxAY~MdeO5%n#xWnM(^fmGeA=SV`H=w=F`Hmv@k{iY#;6jAMSV`?gSt1cpvU~AMSV`?sy;WcpvUGAMQjS?pPo0XdmuaAMPX{?sy;WcpvTrAMO+%?r0zGBp>cHAMO+%?nEE%R3Gj{AMVn8xJ&clF3pF#G#~ELd^iXn4&H}D@ZsQnICvip-iL$t;oyBZG#?JphlBOutu4+ry$cd(_H3|*y|uNOD3WOI;GI2qXAi;ILvi+?ojoLHk2GhGG-r=AXAjNULv!{Jojp`%k2GhGG-r=AXOA>zk2Gfw!r6mx_TZg81ZNN4*@JiX;GI2qXAj=lLv!{Jojq7*58By-b@q^)J$Ppi-q}NN_E4NXXlD<}*+X;oP@FwPXAjlcLv;2?bM{Dc_DFN~NOSg3oc-qG)%fd`6G(RtK7mAAa2K+t1Gk}l4Y(WWXr!l+8I8;-WUTl0qPtsf8{XY{+qj;_+W`cLD@a^V!|g#fG_tGR_CPzkZC|PM`8#`U54fk*cBA_oZ13Xk+n_fq+3akh79!B=d)U=vc8rrfO(gp0QMfeV`~6Ij2H4uoR33ISbwBA!&9zi=p`<R(Q%7$kM)cxQE-A_<MP*4*IUUvBxnw?CXZx1QqkT(8!2SMF@2Uy52*Va(&>{?8gh7iiXb}c2!k|SMv<O2IVQ3-@QiQ>ZFh~&wDZ-#d7_<n37hwn@3|54ph%h7(h9ts}L>R0HgBM{)A`D4{p@}dA5r!bbP(&D#2tyHJNFt0R5k`^-BT0mjB*JM^Cu9+ZD#9Q|c>3{QHxK?c)Qi}5-c!(45LQ36U+x@$k*#aTAaEe+lweK?=9Gw?a<#(56|_)XK2Z6h_5JaCF{<l7L-SHrKhC#>mq**eW6*;w%D;bqb8)x+`H$sv8tC60UWLi53gf2hOJr5}+5PRZ?SaU*#Et+PIhYkiZ-&k<6`db%jN`2@51j+rUl=+=)Qd2_v+CS{j9NFChQL@gZ$QzySB<HI(EZ`gZyT+TyFOB#MXIw%bq1-<Ak|r<I+Ik#km?9h9YLyNNOcscE>5a5NcDZBdW%$Vk?IXny+NwCNcASEo*~r}q<Vr>&yeaVQhl6MZ;+bxk(ybgW)`WLL271@npvb~CaD=iYDSQn5u|1esToCT7AG|`NX`35%`H-Mi`3j8H8)7jEmCun)SMwTCrHf+QgepXoFX-klbRc(4*EzPSfmatQU?a91B29oMe4vLb-<81AV?h$qz)KT2NbD;IH`jOsq3#}-j?^nmr?QK%j`cLU+{fBdOe?XhmOmqr&-euuIGzp^T+l4=V|2r$otTBWLbwVtG|0<zJy}s<WHAsb8z$D_pGMQ{jX@~Jm_Kvee7U%dT>0NZ!fGo|F;ii^?p__M$P!~d~$jp#^ofem|Bfa%cpR67;RdZ^_qVz-&NyB3$;1kJ*l-&+Z&}Q!o#TGz#VTUdw>lK?07HPgY0@Oxr1(RyWO=n)(W)I#7gu8^{+@@K%)lquTWnExl)g#O_O*&yX3kVHOu<wIo}*x58GjU{cF5<KWavwLiG?nm6K%=xVd}NAy(00(ag&EKf=5%9&O0(`VYUL;wlb2?V5eCz`@SjYY*=97f|$oX7!h*noR<6xwHD?d=h?z35EUZu`IZ(E4gUlZb$dSqI{T*KR^Dy4G*72i>|jH{m`wHRN>*c*&Fc19)1;tJH8O772>o)JYR^{3h`PY8DB`I6_RO%<a{ByR!FWDGT;jtXoU=-g*5B8*EhxFZt{8kd1B<DX(QKpiIk2`>DZK>PU+c{8J#j?Q|5HaoJ~2PQw}02!4eLVZ?JTOWE(8mAh`xhHAtqx5)G1Pur$MF`EF57ht>K6vtE8rAcrKcA0(e+oSnuIX}q1r6KOI#O-7{23Cw`NToRb8HfHmY*yr01!>Z#Gsgr}R#s^WrXfmmeJ|8{;xLA5;Mf+H^x1zIHbY?~8vFO}dnA}P~h@~G`(U-C4ODp;+7JU_ueu>>NFV-Ei2h79E-Q->590$~TR65yfa)fiSS{!vMN1n>ZPUWdndGb_Q>{J<bsw{r0-FSMxtoQp8zW?w4k`&}A"""


def _decode_catalog() -> dict[str, tuple[tuple[str, str, int], ...]]:
    decoded = json.loads(
        zlib.decompress(base64.b85decode(_LOCKED_CATALOG_B85)).decode("utf-8")
    )
    result: dict[str, tuple[tuple[str, str, int], ...]] = {}
    for module, entries in cast(dict[str, list[list[Any]]], decoded).items():
        result[module] = tuple(
            (
                str(entry[0]),
                "input" if str(entry[1]) == "i" else "output",
                int(entry[2]),
            )
            for entry in entries
        )
    return result


PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'Og2ForVector': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_flush_valid', 'input', 1),
        ('io_flush_bits_robIdx_flag', 'input', 1),
        ('io_flush_bits_robIdx_value', 'input', 8),
        ('io_flush_bits_level', 'input', 1),
        ('io_fromOg1VfArith_2_0_valid', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_fuType', 'input', 35),
        ('io_fromOg1VfArith_2_0_bits_fuOpType', 'input', 9),
        ('io_fromOg1VfArith_2_0_bits_src_0', 'input', 128),
        ('io_fromOg1VfArith_2_0_bits_src_1', 'input', 128),
        ('io_fromOg1VfArith_2_0_bits_src_2', 'input', 128),
        ('io_fromOg1VfArith_2_0_bits_src_3', 'input', 128),
        ('io_fromOg1VfArith_2_0_bits_src_4', 'input', 128),
        ('io_fromOg1VfArith_2_0_bits_robIdx_flag', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_robIdx_value', 'input', 8),
        ('io_fromOg1VfArith_2_0_bits_pdest', 'input', 7),
        ('io_fromOg1VfArith_2_0_bits_vecWen', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_v0Wen', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_fpu_wflags', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_vpu_vma', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_vpu_vta', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_vpu_vsew', 'input', 2),
        ('io_fromOg1VfArith_2_0_bits_vpu_vlmul', 'input', 3),
        ('io_fromOg1VfArith_2_0_bits_vpu_vm', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_vpu_vstart', 'input', 8),
        ('io_fromOg1VfArith_2_0_bits_vpu_vuopIdx', 'input', 7),
        ('io_fromOg1VfArith_2_0_bits_vpu_isExt', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_vpu_isNarrow', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_vpu_isDstMask', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_vpu_isOpMask', 'input', 1),
        ('io_fromOg1VfArith_2_0_bits_dataSources_0_value', 'input', 4),
        ('io_fromOg1VfArith_2_0_bits_dataSources_1_value', 'input', 4),
        ('io_fromOg1VfArith_2_0_bits_dataSources_2_value', 'input', 4),
        ('io_fromOg1VfArith_2_0_bits_dataSources_3_value', 'input', 4),
        ('io_fromOg1VfArith_2_0_bits_dataSources_4_value', 'input', 4),
        ('io_fromOg1VfArith_1_1_valid', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_fuType', 'input', 35),
        ('io_fromOg1VfArith_1_1_bits_fuOpType', 'input', 9),
        ('io_fromOg1VfArith_1_1_bits_src_0', 'input', 128),
        ('io_fromOg1VfArith_1_1_bits_src_1', 'input', 128),
        ('io_fromOg1VfArith_1_1_bits_src_2', 'input', 128),
        ('io_fromOg1VfArith_1_1_bits_src_3', 'input', 128),
        ('io_fromOg1VfArith_1_1_bits_src_4', 'input', 128),
        ('io_fromOg1VfArith_1_1_bits_robIdx_flag', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_robIdx_value', 'input', 8),
        ('io_fromOg1VfArith_1_1_bits_pdest', 'input', 8),
        ('io_fromOg1VfArith_1_1_bits_fpWen', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vecWen', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_v0Wen', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_fpu_wflags', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_vma', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_vta', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_vsew', 'input', 2),
        ('io_fromOg1VfArith_1_1_bits_vpu_vlmul', 'input', 3),
        ('io_fromOg1VfArith_1_1_bits_vpu_vm', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_vstart', 'input', 8),
        ('io_fromOg1VfArith_1_1_bits_vpu_fpu_isFoldTo1_2', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_fpu_isFoldTo1_4', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_fpu_isFoldTo1_8', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_vuopIdx', 'input', 7),
        ('io_fromOg1VfArith_1_1_bits_vpu_lastUop', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_isNarrow', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_vpu_isDstMask', 'input', 1),
        ('io_fromOg1VfArith_1_1_bits_dataSources_0_value', 'input', 4),
        ('io_fromOg1VfArith_1_1_bits_dataSources_1_value', 'input', 4),
        ('io_fromOg1VfArith_1_1_bits_dataSources_2_value', 'input', 4),
        ('io_fromOg1VfArith_1_1_bits_dataSources_3_value', 'input', 4),
        ('io_fromOg1VfArith_1_1_bits_dataSources_4_value', 'input', 4),
        ('io_fromOg1VfArith_1_0_valid', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_fuType', 'input', 35),
        ('io_fromOg1VfArith_1_0_bits_fuOpType', 'input', 9),
        ('io_fromOg1VfArith_1_0_bits_src_0', 'input', 128),
        ('io_fromOg1VfArith_1_0_bits_src_1', 'input', 128),
        ('io_fromOg1VfArith_1_0_bits_src_2', 'input', 128),
        ('io_fromOg1VfArith_1_0_bits_src_3', 'input', 128),
        ('io_fromOg1VfArith_1_0_bits_src_4', 'input', 128),
        ('io_fromOg1VfArith_1_0_bits_robIdx_flag', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_robIdx_value', 'input', 8),
        ('io_fromOg1VfArith_1_0_bits_pdest', 'input', 7),
        ('io_fromOg1VfArith_1_0_bits_vecWen', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_v0Wen', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_fpu_wflags', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_vpu_vma', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_vpu_vta', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_vpu_vsew', 'input', 2),
        ('io_fromOg1VfArith_1_0_bits_vpu_vlmul', 'input', 3),
        ('io_fromOg1VfArith_1_0_bits_vpu_vm', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_vpu_vstart', 'input', 8),
        ('io_fromOg1VfArith_1_0_bits_vpu_vuopIdx', 'input', 7),
        ('io_fromOg1VfArith_1_0_bits_vpu_isExt', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_vpu_isNarrow', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_vpu_isDstMask', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_vpu_isOpMask', 'input', 1),
        ('io_fromOg1VfArith_1_0_bits_dataSources_0_value', 'input', 4),
        ('io_fromOg1VfArith_1_0_bits_dataSources_1_value', 'input', 4),
        ('io_fromOg1VfArith_1_0_bits_dataSources_2_value', 'input', 4),
        ('io_fromOg1VfArith_1_0_bits_dataSources_3_value', 'input', 4),
        ('io_fromOg1VfArith_1_0_bits_dataSources_4_value', 'input', 4),
        ('io_fromOg1VfArith_0_1_valid', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_fuType', 'input', 35),
        ('io_fromOg1VfArith_0_1_bits_fuOpType', 'input', 9),
        ('io_fromOg1VfArith_0_1_bits_src_0', 'input', 128),
        ('io_fromOg1VfArith_0_1_bits_src_1', 'input', 128),
        ('io_fromOg1VfArith_0_1_bits_src_2', 'input', 128),
        ('io_fromOg1VfArith_0_1_bits_src_3', 'input', 128),
        ('io_fromOg1VfArith_0_1_bits_src_4', 'input', 128),
        ('io_fromOg1VfArith_0_1_bits_robIdx_flag', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_robIdx_value', 'input', 8),
        ('io_fromOg1VfArith_0_1_bits_pdest', 'input', 8),
        ('io_fromOg1VfArith_0_1_bits_rfWen', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_fpWen', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vecWen', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_v0Wen', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vlWen', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_fpu_wflags', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_vma', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_vta', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_vsew', 'input', 2),
        ('io_fromOg1VfArith_0_1_bits_vpu_vlmul', 'input', 3),
        ('io_fromOg1VfArith_0_1_bits_vpu_vm', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_vstart', 'input', 8),
        ('io_fromOg1VfArith_0_1_bits_vpu_fpu_isFoldTo1_2', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_fpu_isFoldTo1_4', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_fpu_isFoldTo1_8', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_vuopIdx', 'input', 7),
        ('io_fromOg1VfArith_0_1_bits_vpu_lastUop', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_isNarrow', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_vpu_isDstMask', 'input', 1),
        ('io_fromOg1VfArith_0_1_bits_dataSources_0_value', 'input', 4),
        ('io_fromOg1VfArith_0_1_bits_dataSources_1_value', 'input', 4),
        ('io_fromOg1VfArith_0_1_bits_dataSources_2_value', 'input', 4),
        ('io_fromOg1VfArith_0_1_bits_dataSources_3_value', 'input', 4),
        ('io_fromOg1VfArith_0_1_bits_dataSources_4_value', 'input', 4),
        ('io_fromOg1VfArith_0_0_valid', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_fuType', 'input', 35),
        ('io_fromOg1VfArith_0_0_bits_fuOpType', 'input', 9),
        ('io_fromOg1VfArith_0_0_bits_src_0', 'input', 128),
        ('io_fromOg1VfArith_0_0_bits_src_1', 'input', 128),
        ('io_fromOg1VfArith_0_0_bits_src_2', 'input', 128),
        ('io_fromOg1VfArith_0_0_bits_src_3', 'input', 128),
        ('io_fromOg1VfArith_0_0_bits_src_4', 'input', 128),
        ('io_fromOg1VfArith_0_0_bits_robIdx_flag', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_robIdx_value', 'input', 8),
        ('io_fromOg1VfArith_0_0_bits_pdest', 'input', 7),
        ('io_fromOg1VfArith_0_0_bits_vecWen', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_v0Wen', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_fpu_wflags', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_vpu_vma', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_vpu_vta', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_vpu_vsew', 'input', 2),
        ('io_fromOg1VfArith_0_0_bits_vpu_vlmul', 'input', 3),
        ('io_fromOg1VfArith_0_0_bits_vpu_vm', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_vpu_vstart', 'input', 8),
        ('io_fromOg1VfArith_0_0_bits_vpu_vuopIdx', 'input', 7),
        ('io_fromOg1VfArith_0_0_bits_vpu_isExt', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_vpu_isNarrow', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_vpu_isDstMask', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_vpu_isOpMask', 'input', 1),
        ('io_fromOg1VfArith_0_0_bits_dataSources_0_value', 'input', 4),
        ('io_fromOg1VfArith_0_0_bits_dataSources_1_value', 'input', 4),
        ('io_fromOg1VfArith_0_0_bits_dataSources_2_value', 'input', 4),
        ('io_fromOg1VfArith_0_0_bits_dataSources_3_value', 'input', 4),
        ('io_fromOg1VfArith_0_0_bits_dataSources_4_value', 'input', 4),
        ('io_fromOg1VecMem_1_0_valid', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_fuType', 'input', 35),
        ('io_fromOg1VecMem_1_0_bits_fuOpType', 'input', 9),
        ('io_fromOg1VecMem_1_0_bits_src_0', 'input', 128),
        ('io_fromOg1VecMem_1_0_bits_src_1', 'input', 128),
        ('io_fromOg1VecMem_1_0_bits_src_2', 'input', 128),
        ('io_fromOg1VecMem_1_0_bits_src_3', 'input', 128),
        ('io_fromOg1VecMem_1_0_bits_src_4', 'input', 128),
        ('io_fromOg1VecMem_1_0_bits_robIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_robIdx_value', 'input', 8),
        ('io_fromOg1VecMem_1_0_bits_pdest', 'input', 7),
        ('io_fromOg1VecMem_1_0_bits_vecWen', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_v0Wen', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_vlWen', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_vpu_vma', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_vpu_vta', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_vpu_vsew', 'input', 2),
        ('io_fromOg1VecMem_1_0_bits_vpu_vlmul', 'input', 3),
        ('io_fromOg1VecMem_1_0_bits_vpu_vm', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_vpu_vstart', 'input', 8),
        ('io_fromOg1VecMem_1_0_bits_vpu_vuopIdx', 'input', 7),
        ('io_fromOg1VecMem_1_0_bits_vpu_lastUop', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_vpu_vmask', 'input', 128),
        ('io_fromOg1VecMem_1_0_bits_vpu_nf', 'input', 3),
        ('io_fromOg1VecMem_1_0_bits_vpu_veew', 'input', 2),
        ('io_fromOg1VecMem_1_0_bits_vpu_isVleff', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_ftqIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_ftqIdx_value', 'input', 6),
        ('io_fromOg1VecMem_1_0_bits_ftqOffset', 'input', 4),
        ('io_fromOg1VecMem_1_0_bits_numLsElem', 'input', 5),
        ('io_fromOg1VecMem_1_0_bits_sqIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_sqIdx_value', 'input', 6),
        ('io_fromOg1VecMem_1_0_bits_lqIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_lqIdx_value', 'input', 7),
        ('io_fromOg1VecMem_1_0_bits_dataSources_0_value', 'input', 4),
        ('io_fromOg1VecMem_1_0_bits_dataSources_1_value', 'input', 4),
        ('io_fromOg1VecMem_1_0_bits_dataSources_2_value', 'input', 4),
        ('io_fromOg1VecMem_1_0_bits_dataSources_3_value', 'input', 4),
        ('io_fromOg1VecMem_1_0_bits_dataSources_4_value', 'input', 4),
        ('io_fromOg1VecMem_1_0_bits_isVecPartReplay', 'input', 1),
        ('io_fromOg1VecMem_1_0_bits_vecReplayMask', 'input', 16),
        ('io_fromOg1VecMem_1_0_bits_vecReplayMbIdx', 'input', 4),
        ('io_fromOg1VecMem_0_0_valid', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_fuType', 'input', 35),
        ('io_fromOg1VecMem_0_0_bits_fuOpType', 'input', 9),
        ('io_fromOg1VecMem_0_0_bits_src_0', 'input', 128),
        ('io_fromOg1VecMem_0_0_bits_src_1', 'input', 128),
        ('io_fromOg1VecMem_0_0_bits_src_2', 'input', 128),
        ('io_fromOg1VecMem_0_0_bits_src_3', 'input', 128),
        ('io_fromOg1VecMem_0_0_bits_src_4', 'input', 128),
        ('io_fromOg1VecMem_0_0_bits_robIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_robIdx_value', 'input', 8),
        ('io_fromOg1VecMem_0_0_bits_pdest', 'input', 7),
        ('io_fromOg1VecMem_0_0_bits_vecWen', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_v0Wen', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_vlWen', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_vpu_vma', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_vpu_vta', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_vpu_vsew', 'input', 2),
        ('io_fromOg1VecMem_0_0_bits_vpu_vlmul', 'input', 3),
        ('io_fromOg1VecMem_0_0_bits_vpu_vm', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_vpu_vstart', 'input', 8),
        ('io_fromOg1VecMem_0_0_bits_vpu_vuopIdx', 'input', 7),
        ('io_fromOg1VecMem_0_0_bits_vpu_lastUop', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_vpu_vmask', 'input', 128),
        ('io_fromOg1VecMem_0_0_bits_vpu_nf', 'input', 3),
        ('io_fromOg1VecMem_0_0_bits_vpu_veew', 'input', 2),
        ('io_fromOg1VecMem_0_0_bits_vpu_isVleff', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_ftqIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_ftqIdx_value', 'input', 6),
        ('io_fromOg1VecMem_0_0_bits_ftqOffset', 'input', 4),
        ('io_fromOg1VecMem_0_0_bits_numLsElem', 'input', 5),
        ('io_fromOg1VecMem_0_0_bits_sqIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_sqIdx_value', 'input', 6),
        ('io_fromOg1VecMem_0_0_bits_lqIdx_flag', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_lqIdx_value', 'input', 7),
        ('io_fromOg1VecMem_0_0_bits_dataSources_0_value', 'input', 4),
        ('io_fromOg1VecMem_0_0_bits_dataSources_1_value', 'input', 4),
        ('io_fromOg1VecMem_0_0_bits_dataSources_2_value', 'input', 4),
        ('io_fromOg1VecMem_0_0_bits_dataSources_3_value', 'input', 4),
        ('io_fromOg1VecMem_0_0_bits_dataSources_4_value', 'input', 4),
        ('io_fromOg1VecMem_0_0_bits_isVecPartReplay', 'input', 1),
        ('io_fromOg1VecMem_0_0_bits_vecReplayMask', 'input', 16),
        ('io_fromOg1VecMem_0_0_bits_vecReplayMbIdx', 'input', 4),
        ('io_fromOg1ImmInfo_1_imm', 'input', 32),
        ('io_fromOg1ImmInfo_1_immType', 'input', 4),
        ('io_toVfArithExu_2_0_ready', 'input', 1),
        ('io_toVfArithExu_2_0_valid', 'output', 1),
        ('io_toVfArithExu_2_0_bits_fuType', 'output', 35),
        ('io_toVfArithExu_2_0_bits_fuOpType', 'output', 9),
        ('io_toVfArithExu_2_0_bits_src_0', 'output', 128),
        ('io_toVfArithExu_2_0_bits_src_1', 'output', 128),
        ('io_toVfArithExu_2_0_bits_src_2', 'output', 128),
        ('io_toVfArithExu_2_0_bits_src_3', 'output', 128),
        ('io_toVfArithExu_2_0_bits_src_4', 'output', 128),
        ('io_toVfArithExu_2_0_bits_robIdx_flag', 'output', 1),
        ('io_toVfArithExu_2_0_bits_robIdx_value', 'output', 8),
        ('io_toVfArithExu_2_0_bits_pdest', 'output', 7),
        ('io_toVfArithExu_2_0_bits_vecWen', 'output', 1),
        ('io_toVfArithExu_2_0_bits_v0Wen', 'output', 1),
        ('io_toVfArithExu_2_0_bits_fpu_wflags', 'output', 1),
        ('io_toVfArithExu_2_0_bits_vpu_vma', 'output', 1),
        ('io_toVfArithExu_2_0_bits_vpu_vta', 'output', 1),
        ('io_toVfArithExu_2_0_bits_vpu_vsew', 'output', 2),
        ('io_toVfArithExu_2_0_bits_vpu_vlmul', 'output', 3),
        ('io_toVfArithExu_2_0_bits_vpu_vm', 'output', 1),
        ('io_toVfArithExu_2_0_bits_vpu_vstart', 'output', 8),
        ('io_toVfArithExu_2_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_toVfArithExu_2_0_bits_vpu_isExt', 'output', 1),
        ('io_toVfArithExu_2_0_bits_vpu_isNarrow', 'output', 1),
        ('io_toVfArithExu_2_0_bits_vpu_isDstMask', 'output', 1),
        ('io_toVfArithExu_2_0_bits_vpu_isOpMask', 'output', 1),
        ('io_toVfArithExu_2_0_bits_dataSources_0_value', 'output', 4),
        ('io_toVfArithExu_2_0_bits_dataSources_1_value', 'output', 4),
        ('io_toVfArithExu_2_0_bits_dataSources_2_value', 'output', 4),
        ('io_toVfArithExu_2_0_bits_dataSources_3_value', 'output', 4),
        ('io_toVfArithExu_2_0_bits_dataSources_4_value', 'output', 4),
        ('io_toVfArithExu_1_1_valid', 'output', 1),
        ('io_toVfArithExu_1_1_bits_fuType', 'output', 35),
        ('io_toVfArithExu_1_1_bits_fuOpType', 'output', 9),
        ('io_toVfArithExu_1_1_bits_src_0', 'output', 128),
        ('io_toVfArithExu_1_1_bits_src_1', 'output', 128),
        ('io_toVfArithExu_1_1_bits_src_2', 'output', 128),
        ('io_toVfArithExu_1_1_bits_src_3', 'output', 128),
        ('io_toVfArithExu_1_1_bits_src_4', 'output', 128),
        ('io_toVfArithExu_1_1_bits_robIdx_flag', 'output', 1),
        ('io_toVfArithExu_1_1_bits_robIdx_value', 'output', 8),
        ('io_toVfArithExu_1_1_bits_pdest', 'output', 8),
        ('io_toVfArithExu_1_1_bits_fpWen', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vecWen', 'output', 1),
        ('io_toVfArithExu_1_1_bits_v0Wen', 'output', 1),
        ('io_toVfArithExu_1_1_bits_fpu_wflags', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_vma', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_vta', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_vsew', 'output', 2),
        ('io_toVfArithExu_1_1_bits_vpu_vlmul', 'output', 3),
        ('io_toVfArithExu_1_1_bits_vpu_vm', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_vstart', 'output', 8),
        ('io_toVfArithExu_1_1_bits_vpu_fpu_isFoldTo1_2', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_fpu_isFoldTo1_4', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_fpu_isFoldTo1_8', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_vuopIdx', 'output', 7),
        ('io_toVfArithExu_1_1_bits_vpu_lastUop', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_isNarrow', 'output', 1),
        ('io_toVfArithExu_1_1_bits_vpu_isDstMask', 'output', 1),
        ('io_toVfArithExu_1_1_bits_dataSources_0_value', 'output', 4),
        ('io_toVfArithExu_1_1_bits_dataSources_1_value', 'output', 4),
        ('io_toVfArithExu_1_1_bits_dataSources_2_value', 'output', 4),
        ('io_toVfArithExu_1_1_bits_dataSources_3_value', 'output', 4),
        ('io_toVfArithExu_1_1_bits_dataSources_4_value', 'output', 4),
        ('io_toVfArithExu_1_0_ready', 'input', 1),
        ('io_toVfArithExu_1_0_valid', 'output', 1),
        ('io_toVfArithExu_1_0_bits_fuType', 'output', 35),
        ('io_toVfArithExu_1_0_bits_fuOpType', 'output', 9),
        ('io_toVfArithExu_1_0_bits_src_0', 'output', 128),
        ('io_toVfArithExu_1_0_bits_src_1', 'output', 128),
        ('io_toVfArithExu_1_0_bits_src_2', 'output', 128),
        ('io_toVfArithExu_1_0_bits_src_3', 'output', 128),
        ('io_toVfArithExu_1_0_bits_src_4', 'output', 128),
        ('io_toVfArithExu_1_0_bits_robIdx_flag', 'output', 1),
        ('io_toVfArithExu_1_0_bits_robIdx_value', 'output', 8),
        ('io_toVfArithExu_1_0_bits_pdest', 'output', 7),
        ('io_toVfArithExu_1_0_bits_vecWen', 'output', 1),
        ('io_toVfArithExu_1_0_bits_v0Wen', 'output', 1),
        ('io_toVfArithExu_1_0_bits_fpu_wflags', 'output', 1),
        ('io_toVfArithExu_1_0_bits_vpu_vma', 'output', 1),
        ('io_toVfArithExu_1_0_bits_vpu_vta', 'output', 1),
        ('io_toVfArithExu_1_0_bits_vpu_vsew', 'output', 2),
        ('io_toVfArithExu_1_0_bits_vpu_vlmul', 'output', 3),
        ('io_toVfArithExu_1_0_bits_vpu_vm', 'output', 1),
        ('io_toVfArithExu_1_0_bits_vpu_vstart', 'output', 8),
        ('io_toVfArithExu_1_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_toVfArithExu_1_0_bits_vpu_isExt', 'output', 1),
        ('io_toVfArithExu_1_0_bits_vpu_isNarrow', 'output', 1),
        ('io_toVfArithExu_1_0_bits_vpu_isDstMask', 'output', 1),
        ('io_toVfArithExu_1_0_bits_vpu_isOpMask', 'output', 1),
        ('io_toVfArithExu_1_0_bits_dataSources_0_value', 'output', 4),
        ('io_toVfArithExu_1_0_bits_dataSources_1_value', 'output', 4),
        ('io_toVfArithExu_1_0_bits_dataSources_2_value', 'output', 4),
        ('io_toVfArithExu_1_0_bits_dataSources_3_value', 'output', 4),
        ('io_toVfArithExu_1_0_bits_dataSources_4_value', 'output', 4),
        ('io_toVfArithExu_0_1_valid', 'output', 1),
        ('io_toVfArithExu_0_1_bits_fuType', 'output', 35),
        ('io_toVfArithExu_0_1_bits_fuOpType', 'output', 9),
        ('io_toVfArithExu_0_1_bits_src_0', 'output', 128),
        ('io_toVfArithExu_0_1_bits_src_1', 'output', 128),
        ('io_toVfArithExu_0_1_bits_src_2', 'output', 128),
        ('io_toVfArithExu_0_1_bits_src_3', 'output', 128),
        ('io_toVfArithExu_0_1_bits_src_4', 'output', 128),
        ('io_toVfArithExu_0_1_bits_robIdx_flag', 'output', 1),
        ('io_toVfArithExu_0_1_bits_robIdx_value', 'output', 8),
        ('io_toVfArithExu_0_1_bits_pdest', 'output', 8),
        ('io_toVfArithExu_0_1_bits_rfWen', 'output', 1),
        ('io_toVfArithExu_0_1_bits_fpWen', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vecWen', 'output', 1),
        ('io_toVfArithExu_0_1_bits_v0Wen', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vlWen', 'output', 1),
        ('io_toVfArithExu_0_1_bits_fpu_wflags', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_vma', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_vta', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_vsew', 'output', 2),
        ('io_toVfArithExu_0_1_bits_vpu_vlmul', 'output', 3),
        ('io_toVfArithExu_0_1_bits_vpu_vm', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_vstart', 'output', 8),
        ('io_toVfArithExu_0_1_bits_vpu_fpu_isFoldTo1_2', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_fpu_isFoldTo1_4', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_fpu_isFoldTo1_8', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_vuopIdx', 'output', 7),
        ('io_toVfArithExu_0_1_bits_vpu_lastUop', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_isNarrow', 'output', 1),
        ('io_toVfArithExu_0_1_bits_vpu_isDstMask', 'output', 1),
        ('io_toVfArithExu_0_1_bits_dataSources_0_value', 'output', 4),
        ('io_toVfArithExu_0_1_bits_dataSources_1_value', 'output', 4),
        ('io_toVfArithExu_0_1_bits_dataSources_2_value', 'output', 4),
        ('io_toVfArithExu_0_1_bits_dataSources_3_value', 'output', 4),
        ('io_toVfArithExu_0_1_bits_dataSources_4_value', 'output', 4),
        ('io_toVfArithExu_0_0_ready', 'input', 1),
        ('io_toVfArithExu_0_0_valid', 'output', 1),
        ('io_toVfArithExu_0_0_bits_fuType', 'output', 35),
        ('io_toVfArithExu_0_0_bits_fuOpType', 'output', 9),
        ('io_toVfArithExu_0_0_bits_src_0', 'output', 128),
        ('io_toVfArithExu_0_0_bits_src_1', 'output', 128),
        ('io_toVfArithExu_0_0_bits_src_2', 'output', 128),
        ('io_toVfArithExu_0_0_bits_src_3', 'output', 128),
        ('io_toVfArithExu_0_0_bits_src_4', 'output', 128),
        ('io_toVfArithExu_0_0_bits_robIdx_flag', 'output', 1),
        ('io_toVfArithExu_0_0_bits_robIdx_value', 'output', 8),
        ('io_toVfArithExu_0_0_bits_pdest', 'output', 7),
        ('io_toVfArithExu_0_0_bits_vecWen', 'output', 1),
        ('io_toVfArithExu_0_0_bits_v0Wen', 'output', 1),
        ('io_toVfArithExu_0_0_bits_fpu_wflags', 'output', 1),
        ('io_toVfArithExu_0_0_bits_vpu_vma', 'output', 1),
        ('io_toVfArithExu_0_0_bits_vpu_vta', 'output', 1),
        ('io_toVfArithExu_0_0_bits_vpu_vsew', 'output', 2),
        ('io_toVfArithExu_0_0_bits_vpu_vlmul', 'output', 3),
        ('io_toVfArithExu_0_0_bits_vpu_vm', 'output', 1),
        ('io_toVfArithExu_0_0_bits_vpu_vstart', 'output', 8),
        ('io_toVfArithExu_0_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_toVfArithExu_0_0_bits_vpu_isExt', 'output', 1),
        ('io_toVfArithExu_0_0_bits_vpu_isNarrow', 'output', 1),
        ('io_toVfArithExu_0_0_bits_vpu_isDstMask', 'output', 1),
        ('io_toVfArithExu_0_0_bits_vpu_isOpMask', 'output', 1),
        ('io_toVfArithExu_0_0_bits_dataSources_0_value', 'output', 4),
        ('io_toVfArithExu_0_0_bits_dataSources_1_value', 'output', 4),
        ('io_toVfArithExu_0_0_bits_dataSources_2_value', 'output', 4),
        ('io_toVfArithExu_0_0_bits_dataSources_3_value', 'output', 4),
        ('io_toVfArithExu_0_0_bits_dataSources_4_value', 'output', 4),
        ('io_toVecMemExu_1_0_ready', 'input', 1),
        ('io_toVecMemExu_1_0_valid', 'output', 1),
        ('io_toVecMemExu_1_0_bits_fuType', 'output', 35),
        ('io_toVecMemExu_1_0_bits_fuOpType', 'output', 9),
        ('io_toVecMemExu_1_0_bits_src_0', 'output', 128),
        ('io_toVecMemExu_1_0_bits_src_1', 'output', 128),
        ('io_toVecMemExu_1_0_bits_src_2', 'output', 128),
        ('io_toVecMemExu_1_0_bits_src_3', 'output', 128),
        ('io_toVecMemExu_1_0_bits_src_4', 'output', 128),
        ('io_toVecMemExu_1_0_bits_robIdx_flag', 'output', 1),
        ('io_toVecMemExu_1_0_bits_robIdx_value', 'output', 8),
        ('io_toVecMemExu_1_0_bits_pdest', 'output', 7),
        ('io_toVecMemExu_1_0_bits_vecWen', 'output', 1),
        ('io_toVecMemExu_1_0_bits_v0Wen', 'output', 1),
        ('io_toVecMemExu_1_0_bits_vlWen', 'output', 1),
        ('io_toVecMemExu_1_0_bits_vpu_vma', 'output', 1),
        ('io_toVecMemExu_1_0_bits_vpu_vta', 'output', 1),
        ('io_toVecMemExu_1_0_bits_vpu_vsew', 'output', 2),
        ('io_toVecMemExu_1_0_bits_vpu_vlmul', 'output', 3),
        ('io_toVecMemExu_1_0_bits_vpu_vm', 'output', 1),
        ('io_toVecMemExu_1_0_bits_vpu_vstart', 'output', 8),
        ('io_toVecMemExu_1_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_toVecMemExu_1_0_bits_vpu_lastUop', 'output', 1),
        ('io_toVecMemExu_1_0_bits_vpu_vmask', 'output', 128),
        ('io_toVecMemExu_1_0_bits_vpu_nf', 'output', 3),
        ('io_toVecMemExu_1_0_bits_vpu_veew', 'output', 2),
        ('io_toVecMemExu_1_0_bits_vpu_isVleff', 'output', 1),
        ('io_toVecMemExu_1_0_bits_ftqIdx_flag', 'output', 1),
        ('io_toVecMemExu_1_0_bits_ftqIdx_value', 'output', 6),
        ('io_toVecMemExu_1_0_bits_ftqOffset', 'output', 4),
        ('io_toVecMemExu_1_0_bits_numLsElem', 'output', 5),
        ('io_toVecMemExu_1_0_bits_sqIdx_flag', 'output', 1),
        ('io_toVecMemExu_1_0_bits_sqIdx_value', 'output', 6),
        ('io_toVecMemExu_1_0_bits_lqIdx_flag', 'output', 1),
        ('io_toVecMemExu_1_0_bits_lqIdx_value', 'output', 7),
        ('io_toVecMemExu_1_0_bits_dataSources_0_value', 'output', 4),
        ('io_toVecMemExu_1_0_bits_dataSources_1_value', 'output', 4),
        ('io_toVecMemExu_1_0_bits_dataSources_2_value', 'output', 4),
        ('io_toVecMemExu_1_0_bits_dataSources_3_value', 'output', 4),
        ('io_toVecMemExu_1_0_bits_dataSources_4_value', 'output', 4),
        ('io_toVecMemExu_1_0_bits_isVecPartReplay', 'output', 1),
        ('io_toVecMemExu_1_0_bits_vecReplayMask', 'output', 16),
        ('io_toVecMemExu_1_0_bits_vecReplayMbIdx', 'output', 4),
        ('io_toVecMemExu_0_0_ready', 'input', 1),
        ('io_toVecMemExu_0_0_valid', 'output', 1),
        ('io_toVecMemExu_0_0_bits_fuType', 'output', 35),
        ('io_toVecMemExu_0_0_bits_fuOpType', 'output', 9),
        ('io_toVecMemExu_0_0_bits_src_0', 'output', 128),
        ('io_toVecMemExu_0_0_bits_src_1', 'output', 128),
        ('io_toVecMemExu_0_0_bits_src_2', 'output', 128),
        ('io_toVecMemExu_0_0_bits_src_3', 'output', 128),
        ('io_toVecMemExu_0_0_bits_src_4', 'output', 128),
        ('io_toVecMemExu_0_0_bits_robIdx_flag', 'output', 1),
        ('io_toVecMemExu_0_0_bits_robIdx_value', 'output', 8),
        ('io_toVecMemExu_0_0_bits_pdest', 'output', 7),
        ('io_toVecMemExu_0_0_bits_vecWen', 'output', 1),
        ('io_toVecMemExu_0_0_bits_v0Wen', 'output', 1),
        ('io_toVecMemExu_0_0_bits_vlWen', 'output', 1),
        ('io_toVecMemExu_0_0_bits_vpu_vma', 'output', 1),
        ('io_toVecMemExu_0_0_bits_vpu_vta', 'output', 1),
        ('io_toVecMemExu_0_0_bits_vpu_vsew', 'output', 2),
        ('io_toVecMemExu_0_0_bits_vpu_vlmul', 'output', 3),
        ('io_toVecMemExu_0_0_bits_vpu_vm', 'output', 1),
        ('io_toVecMemExu_0_0_bits_vpu_vstart', 'output', 8),
        ('io_toVecMemExu_0_0_bits_vpu_vuopIdx', 'output', 7),
        ('io_toVecMemExu_0_0_bits_vpu_lastUop', 'output', 1),
        ('io_toVecMemExu_0_0_bits_vpu_vmask', 'output', 128),
        ('io_toVecMemExu_0_0_bits_vpu_nf', 'output', 3),
        ('io_toVecMemExu_0_0_bits_vpu_veew', 'output', 2),
        ('io_toVecMemExu_0_0_bits_vpu_isVleff', 'output', 1),
        ('io_toVecMemExu_0_0_bits_ftqIdx_flag', 'output', 1),
        ('io_toVecMemExu_0_0_bits_ftqIdx_value', 'output', 6),
        ('io_toVecMemExu_0_0_bits_ftqOffset', 'output', 4),
        ('io_toVecMemExu_0_0_bits_numLsElem', 'output', 5),
        ('io_toVecMemExu_0_0_bits_sqIdx_flag', 'output', 1),
        ('io_toVecMemExu_0_0_bits_sqIdx_value', 'output', 6),
        ('io_toVecMemExu_0_0_bits_lqIdx_flag', 'output', 1),
        ('io_toVecMemExu_0_0_bits_lqIdx_value', 'output', 7),
        ('io_toVecMemExu_0_0_bits_dataSources_0_value', 'output', 4),
        ('io_toVecMemExu_0_0_bits_dataSources_1_value', 'output', 4),
        ('io_toVecMemExu_0_0_bits_dataSources_2_value', 'output', 4),
        ('io_toVecMemExu_0_0_bits_dataSources_3_value', 'output', 4),
        ('io_toVecMemExu_0_0_bits_dataSources_4_value', 'output', 4),
        ('io_toVecMemExu_0_0_bits_isVecPartReplay', 'output', 1),
        ('io_toVecMemExu_0_0_bits_vecReplayMask', 'output', 16),
        ('io_toVecMemExu_0_0_bits_vecReplayMbIdx', 'output', 4),
        ('io_toVfIQOg2Resp_2_0_valid', 'output', 1),
        ('io_toVfIQOg2Resp_2_0_bits_resp', 'output', 2),
        ('io_toVfIQOg2Resp_1_1_valid', 'output', 1),
        ('io_toVfIQOg2Resp_1_0_valid', 'output', 1),
        ('io_toVfIQOg2Resp_1_0_bits_resp', 'output', 2),
        ('io_toVfIQOg2Resp_0_1_valid', 'output', 1),
        ('io_toVfIQOg2Resp_0_0_valid', 'output', 1),
        ('io_toVfIQOg2Resp_0_0_bits_resp', 'output', 2),
        ('io_toMemIQOg2Resp_1_0_valid', 'output', 1),
        ('io_toMemIQOg2Resp_1_0_bits_resp', 'output', 2),
        ('io_toMemIQOg2Resp_0_0_valid', 'output', 1),
        ('io_toMemIQOg2Resp_0_0_bits_resp', 'output', 2),
        ('io_toBypassNetworkImmInfo_1_imm', 'output', 32),
        ('io_toBypassNetworkImmInfo_1_immType', 'output', 4),
    ),
    'VTypeBuffer': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_redirect_valid', 'input', 1),
        ('io_req_0_valid', 'input', 1),
        ('io_req_0_bits_fuOpType', 'input', 9),
        ('io_req_0_bits_vpu_vill', 'input', 1),
        ('io_req_0_bits_vpu_vma', 'input', 1),
        ('io_req_0_bits_vpu_vta', 'input', 1),
        ('io_req_0_bits_vpu_vsew', 'input', 2),
        ('io_req_0_bits_vpu_vlmul', 'input', 3),
        ('io_req_0_bits_vpu_specVill', 'input', 1),
        ('io_req_0_bits_vpu_specVma', 'input', 1),
        ('io_req_0_bits_vpu_specVta', 'input', 1),
        ('io_req_0_bits_vpu_specVsew', 'input', 2),
        ('io_req_0_bits_vpu_specVlmul', 'input', 3),
        ('io_req_0_bits_isVset', 'input', 1),
        ('io_req_0_bits_lastUop', 'input', 1),
        ('io_req_1_valid', 'input', 1),
        ('io_req_1_bits_fuOpType', 'input', 9),
        ('io_req_1_bits_vpu_vill', 'input', 1),
        ('io_req_1_bits_vpu_vma', 'input', 1),
        ('io_req_1_bits_vpu_vta', 'input', 1),
        ('io_req_1_bits_vpu_vsew', 'input', 2),
        ('io_req_1_bits_vpu_vlmul', 'input', 3),
        ('io_req_1_bits_vpu_specVill', 'input', 1),
        ('io_req_1_bits_vpu_specVma', 'input', 1),
        ('io_req_1_bits_vpu_specVta', 'input', 1),
        ('io_req_1_bits_vpu_specVsew', 'input', 2),
        ('io_req_1_bits_vpu_specVlmul', 'input', 3),
        ('io_req_1_bits_isVset', 'input', 1),
        ('io_req_1_bits_lastUop', 'input', 1),
        ('io_req_2_valid', 'input', 1),
        ('io_req_2_bits_fuOpType', 'input', 9),
        ('io_req_2_bits_vpu_vill', 'input', 1),
        ('io_req_2_bits_vpu_vma', 'input', 1),
        ('io_req_2_bits_vpu_vta', 'input', 1),
        ('io_req_2_bits_vpu_vsew', 'input', 2),
        ('io_req_2_bits_vpu_vlmul', 'input', 3),
        ('io_req_2_bits_vpu_specVill', 'input', 1),
        ('io_req_2_bits_vpu_specVma', 'input', 1),
        ('io_req_2_bits_vpu_specVta', 'input', 1),
        ('io_req_2_bits_vpu_specVsew', 'input', 2),
        ('io_req_2_bits_vpu_specVlmul', 'input', 3),
        ('io_req_2_bits_isVset', 'input', 1),
        ('io_req_2_bits_lastUop', 'input', 1),
        ('io_req_3_valid', 'input', 1),
        ('io_req_3_bits_fuOpType', 'input', 9),
        ('io_req_3_bits_vpu_vill', 'input', 1),
        ('io_req_3_bits_vpu_vma', 'input', 1),
        ('io_req_3_bits_vpu_vta', 'input', 1),
        ('io_req_3_bits_vpu_vsew', 'input', 2),
        ('io_req_3_bits_vpu_vlmul', 'input', 3),
        ('io_req_3_bits_vpu_specVill', 'input', 1),
        ('io_req_3_bits_vpu_specVma', 'input', 1),
        ('io_req_3_bits_vpu_specVta', 'input', 1),
        ('io_req_3_bits_vpu_specVsew', 'input', 2),
        ('io_req_3_bits_vpu_specVlmul', 'input', 3),
        ('io_req_3_bits_isVset', 'input', 1),
        ('io_req_3_bits_lastUop', 'input', 1),
        ('io_req_4_valid', 'input', 1),
        ('io_req_4_bits_fuOpType', 'input', 9),
        ('io_req_4_bits_vpu_vill', 'input', 1),
        ('io_req_4_bits_vpu_vma', 'input', 1),
        ('io_req_4_bits_vpu_vta', 'input', 1),
        ('io_req_4_bits_vpu_vsew', 'input', 2),
        ('io_req_4_bits_vpu_vlmul', 'input', 3),
        ('io_req_4_bits_vpu_specVill', 'input', 1),
        ('io_req_4_bits_vpu_specVma', 'input', 1),
        ('io_req_4_bits_vpu_specVta', 'input', 1),
        ('io_req_4_bits_vpu_specVsew', 'input', 2),
        ('io_req_4_bits_vpu_specVlmul', 'input', 3),
        ('io_req_4_bits_isVset', 'input', 1),
        ('io_req_4_bits_lastUop', 'input', 1),
        ('io_req_5_valid', 'input', 1),
        ('io_req_5_bits_fuOpType', 'input', 9),
        ('io_req_5_bits_vpu_vill', 'input', 1),
        ('io_req_5_bits_vpu_vma', 'input', 1),
        ('io_req_5_bits_vpu_vta', 'input', 1),
        ('io_req_5_bits_vpu_vsew', 'input', 2),
        ('io_req_5_bits_vpu_vlmul', 'input', 3),
        ('io_req_5_bits_vpu_specVill', 'input', 1),
        ('io_req_5_bits_vpu_specVma', 'input', 1),
        ('io_req_5_bits_vpu_specVta', 'input', 1),
        ('io_req_5_bits_vpu_specVsew', 'input', 2),
        ('io_req_5_bits_vpu_specVlmul', 'input', 3),
        ('io_req_5_bits_isVset', 'input', 1),
        ('io_req_5_bits_lastUop', 'input', 1),
        ('io_fromRob_walkSize', 'input', 6),
        ('io_fromRob_walkEnd', 'input', 1),
        ('io_fromRob_commitSize', 'input', 6),
        ('io_snpt_snptEnq', 'input', 1),
        ('io_snpt_snptDeq', 'input', 1),
        ('io_snpt_useSnpt', 'input', 1),
        ('io_snpt_snptSelect', 'input', 2),
        ('io_snpt_flushVec_0', 'input', 1),
        ('io_snpt_flushVec_1', 'input', 1),
        ('io_snpt_flushVec_2', 'input', 1),
        ('io_snpt_flushVec_3', 'input', 1),
        ('io_canEnq', 'output', 1),
        ('io_canEnqForDispatch', 'output', 1),
        ('io_toDecode_isResumeVType', 'output', 1),
        ('io_toDecode_walkToArchVType', 'output', 1),
        ('io_toDecode_walkVType_valid', 'output', 1),
        ('io_toDecode_walkVType_bits_illegal', 'output', 1),
        ('io_toDecode_walkVType_bits_vma', 'output', 1),
        ('io_toDecode_walkVType_bits_vta', 'output', 1),
        ('io_toDecode_walkVType_bits_vsew', 'output', 2),
        ('io_toDecode_walkVType_bits_vlmul', 'output', 3),
        ('io_toDecode_commitVType_vtype_valid', 'output', 1),
        ('io_toDecode_commitVType_vtype_bits_illegal', 'output', 1),
        ('io_toDecode_commitVType_vtype_bits_vma', 'output', 1),
        ('io_toDecode_commitVType_vtype_bits_vta', 'output', 1),
        ('io_toDecode_commitVType_vtype_bits_vsew', 'output', 2),
        ('io_toDecode_commitVType_vtype_bits_vlmul', 'output', 3),
        ('io_toDecode_commitVType_hasVsetvl', 'output', 1),
        ('io_status_walkEnd', 'output', 1),
    ),
    'VecExcpDataMergeModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('i_fromExceptionGen_valid', 'input', 1),
        ('i_fromExceptionGen_bits_vstart', 'input', 7),
        ('i_fromExceptionGen_bits_vsew', 'input', 2),
        ('i_fromExceptionGen_bits_veew', 'input', 2),
        ('i_fromExceptionGen_bits_vlmul', 'input', 3),
        ('i_fromExceptionGen_bits_nf', 'input', 3),
        ('i_fromExceptionGen_bits_isStride', 'input', 1),
        ('i_fromExceptionGen_bits_isIndexed', 'input', 1),
        ('i_fromExceptionGen_bits_isWhole', 'input', 1),
        ('i_fromExceptionGen_bits_isVlm', 'input', 1),
        ('i_fromRab_logicPhyRegMap_0_valid', 'input', 1),
        ('i_fromRab_logicPhyRegMap_0_bits_lreg', 'input', 6),
        ('i_fromRab_logicPhyRegMap_0_bits_preg', 'input', 7),
        ('i_fromRab_logicPhyRegMap_1_valid', 'input', 1),
        ('i_fromRab_logicPhyRegMap_1_bits_lreg', 'input', 6),
        ('i_fromRab_logicPhyRegMap_1_bits_preg', 'input', 7),
        ('i_fromRab_logicPhyRegMap_2_valid', 'input', 1),
        ('i_fromRab_logicPhyRegMap_2_bits_lreg', 'input', 6),
        ('i_fromRab_logicPhyRegMap_2_bits_preg', 'input', 7),
        ('i_fromRab_logicPhyRegMap_3_valid', 'input', 1),
        ('i_fromRab_logicPhyRegMap_3_bits_lreg', 'input', 6),
        ('i_fromRab_logicPhyRegMap_3_bits_preg', 'input', 7),
        ('i_fromRab_logicPhyRegMap_4_valid', 'input', 1),
        ('i_fromRab_logicPhyRegMap_4_bits_lreg', 'input', 6),
        ('i_fromRab_logicPhyRegMap_4_bits_preg', 'input', 7),
        ('i_fromRab_logicPhyRegMap_5_valid', 'input', 1),
        ('i_fromRab_logicPhyRegMap_5_bits_lreg', 'input', 6),
        ('i_fromRab_logicPhyRegMap_5_bits_preg', 'input', 7),
        ('i_fromRat_vecOldVdPdest_0_valid', 'input', 1),
        ('i_fromRat_vecOldVdPdest_0_bits', 'input', 7),
        ('i_fromRat_vecOldVdPdest_1_valid', 'input', 1),
        ('i_fromRat_vecOldVdPdest_1_bits', 'input', 7),
        ('i_fromRat_vecOldVdPdest_2_valid', 'input', 1),
        ('i_fromRat_vecOldVdPdest_2_bits', 'input', 7),
        ('i_fromRat_vecOldVdPdest_3_valid', 'input', 1),
        ('i_fromRat_vecOldVdPdest_3_bits', 'input', 7),
        ('i_fromRat_vecOldVdPdest_4_valid', 'input', 1),
        ('i_fromRat_vecOldVdPdest_4_bits', 'input', 7),
        ('i_fromRat_vecOldVdPdest_5_valid', 'input', 1),
        ('i_fromRat_vecOldVdPdest_5_bits', 'input', 7),
        ('i_fromRat_v0OldVdPdest_0_valid', 'input', 1),
        ('i_fromRat_v0OldVdPdest_0_bits', 'input', 7),
        ('i_fromRat_v0OldVdPdest_1_valid', 'input', 1),
        ('i_fromRat_v0OldVdPdest_1_bits', 'input', 7),
        ('i_fromRat_v0OldVdPdest_2_valid', 'input', 1),
        ('i_fromRat_v0OldVdPdest_2_bits', 'input', 7),
        ('i_fromRat_v0OldVdPdest_3_valid', 'input', 1),
        ('i_fromRat_v0OldVdPdest_3_bits', 'input', 7),
        ('i_fromRat_v0OldVdPdest_4_valid', 'input', 1),
        ('i_fromRat_v0OldVdPdest_4_bits', 'input', 7),
        ('i_fromRat_v0OldVdPdest_5_valid', 'input', 1),
        ('i_fromRat_v0OldVdPdest_5_bits', 'input', 7),
        ('i_fromVprf_rdata_0_valid', 'input', 1),
        ('i_fromVprf_rdata_0_bits', 'input', 128),
        ('i_fromVprf_rdata_1_valid', 'input', 1),
        ('i_fromVprf_rdata_1_bits', 'input', 128),
        ('i_fromVprf_rdata_2_valid', 'input', 1),
        ('i_fromVprf_rdata_2_bits', 'input', 128),
        ('i_fromVprf_rdata_3_valid', 'input', 1),
        ('i_fromVprf_rdata_3_bits', 'input', 128),
        ('i_fromVprf_rdata_4_bits', 'input', 128),
        ('i_fromVprf_rdata_5_bits', 'input', 128),
        ('i_fromVprf_rdata_6_bits', 'input', 128),
        ('i_fromVprf_rdata_7_bits', 'input', 128),
        ('o_toVPRF_r_0_valid', 'output', 1),
        ('o_toVPRF_r_0_bits_isV0', 'output', 1),
        ('o_toVPRF_r_0_bits_addr', 'output', 7),
        ('o_toVPRF_r_1_valid', 'output', 1),
        ('o_toVPRF_r_1_bits_addr', 'output', 7),
        ('o_toVPRF_r_2_valid', 'output', 1),
        ('o_toVPRF_r_2_bits_addr', 'output', 7),
        ('o_toVPRF_r_3_valid', 'output', 1),
        ('o_toVPRF_r_3_bits_addr', 'output', 7),
        ('o_toVPRF_r_4_valid', 'output', 1),
        ('o_toVPRF_r_4_bits_isV0', 'output', 1),
        ('o_toVPRF_r_4_bits_addr', 'output', 7),
        ('o_toVPRF_r_5_valid', 'output', 1),
        ('o_toVPRF_r_5_bits_addr', 'output', 7),
        ('o_toVPRF_r_6_valid', 'output', 1),
        ('o_toVPRF_r_6_bits_addr', 'output', 7),
        ('o_toVPRF_r_7_valid', 'output', 1),
        ('o_toVPRF_r_7_bits_addr', 'output', 7),
        ('o_toVPRF_w_0_valid', 'output', 1),
        ('o_toVPRF_w_0_bits_isV0', 'output', 1),
        ('o_toVPRF_w_0_bits_newVdAddr', 'output', 7),
        ('o_toVPRF_w_0_bits_newVdData', 'output', 128),
        ('o_toVPRF_w_1_valid', 'output', 1),
        ('o_toVPRF_w_1_bits_newVdAddr', 'output', 7),
        ('o_toVPRF_w_1_bits_newVdData', 'output', 128),
        ('o_toVPRF_w_2_valid', 'output', 1),
        ('o_toVPRF_w_2_bits_newVdAddr', 'output', 7),
        ('o_toVPRF_w_2_bits_newVdData', 'output', 128),
        ('o_toVPRF_w_3_valid', 'output', 1),
        ('o_toVPRF_w_3_bits_newVdAddr', 'output', 7),
        ('o_toVPRF_w_3_bits_newVdData', 'output', 128),
        ('o_status_busy', 'output', 1),
    ),
    'VIAluSrcTypeModule': (
        ('io_in_fuOpType', 'input', 9),
        ('io_in_vsew', 'input', 2),
        ('io_in_isExt', 'input', 1),
        ('io_in_isDstMask', 'input', 1),
        ('io_out_vs1Type', 'output', 4),
        ('io_out_vs2Type', 'output', 4),
        ('io_out_vdType', 'output', 4),
        ('io_out_isVextF2', 'output', 1),
        ('io_out_isVextF4', 'output', 1),
        ('io_out_isVextF8', 'output', 1),
    ),
    'VIMacSrcTypeModule': (
        ('io_in_fuOpType', 'input', 9),
        ('io_in_vsew', 'input', 2),
        ('io_out_vs1Type', 'output', 4),
        ('io_out_vs2Type', 'output', 4),
    ),
    'VPermSrcTypeModule': (
        ('io_in_fuOpType', 'input', 9),
        ('io_in_vsew', 'input', 2),
        ('io_out_vs1Type', 'output', 4),
        ('io_out_vs2Type', 'output', 4),
    ),
}







def vector_datapath_model(
    module: str, inputs: dict[str, int] | None = None
) -> dict[str, int]:
    """Return the bounded reset-safe output oracle for one family member.

    The V2 parent closure owns scheduling and arithmetic; this leaf contract
    intentionally exposes zero-valued outputs until that closure is selected.
    """

    del inputs
    if module not in PORT_SPECS:
        raise ValueError(module)
    return {
        name: 0
        for name, direction, _width in PORT_SPECS[module]
        if direction == "output"
    }


class VectorDatapathFamily(Elaboratable):
    """One exact locked-hierarchy vector datapath member."""

    def __init__(self, member: str = "Og2ForVector") -> None:
        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True)
            domain.clk = self.ports["clock"]
            domain.rst = self.ports["reset"]
            module.domains += domain
        # The three source-type leaves are pure combinational decoders.  Keep
        # their equations explicit (rather than using the old all-zero stub)
        # so every input valuation is observable in the strict SAT miter.
        if self.member == "VIAluSrcTypeModule":
            op = self.ports["io_in_fuOpType"]
            vsew = self.ports["io_in_vsew"]
            is_ext = self.ports["io_in_isExt"]
            is_mask = self.ports["io_in_isDstMask"]
            fmt = op[7:9]
            sign = op[6]
            x2 = (vsew + 1)[:2]
            f2 = (vsew - 1)[:2]
            f4 = (vsew - 2)[:2]
            f8 = (vsew - 3)[:2]
            # Chisel Cat(a,b,c) places a at the high end.
            add_vv = Cat(vsew, vsew, vsew)
            add_vvw = Cat(x2, vsew, vsew)
            add_wvw = Cat(x2, vsew, x2)
            add_wvv = Cat(vsew, vsew, x2)
            add = Mux(fmt == 0, add_vv,
                      Mux(fmt == 1, add_vvw,
                          Mux(fmt == 2, add_wvw, add_wvv)))
            # Mux1H has a zero default for the unsupported fourth format.
            ext = Mux(fmt == 0, Cat(vsew, f2, f2),
                      Mux(fmt == 1, Cat(vsew, f4, f4),
                          Mux(fmt == 2, Cat(vsew, f8, f8), Const(0, 6))))
            # VVM/VVMM use the signedness bit and current SEW; MMM is all
            # mask-typed (4'hf) for each operand.
            mask_type = Mux((fmt == 1) | (fmt == 2),
                            Cat(vsew, sign, Const(0, 1)),
                            Mux(fmt == 3, Const(0xF, 4), Const(0, 4)))
            add_vs2 = Cat(add[4:6], sign, Const(0, 1))
            add_vs1 = Cat(add[2:4], sign, Const(0, 1))
            add_vd = Cat(add[0:2], sign, Const(0, 1))
            ext_vs2 = Cat(ext[4:6], sign, Const(0, 1))
            ext_vs1 = Cat(ext[2:4], sign, Const(0, 1))
            ext_vd = Cat(ext[0:2], sign, Const(0, 1))
            module.d.comb += [
                self.ports["io_out_vs1Type"].eq(
                    Mux(is_mask, mask_type,
                        Mux(is_ext, ext_vs1, add_vs1))),
                self.ports["io_out_vs2Type"].eq(
                    Mux(is_mask, mask_type,
                        Mux(is_ext, ext_vs2, add_vs2))),
                self.ports["io_out_vdType"].eq(
                    Mux(is_mask, Mux(fmt == 0, Const(0, 4), Const(0xF, 4)),
                        Mux(is_ext, ext_vd, add_vd))),
                self.ports["io_out_isVextF2"].eq((op[:6] == 2) & (fmt == 0)),
                self.ports["io_out_isVextF4"].eq((op[:6] == 2) & (fmt == 1)),
                self.ports["io_out_isVextF8"].eq((op[:6] == 2) & (fmt == 2)),
            ]
            return module
        if self.member == "VIMacSrcTypeModule":
            op = self.ports["io_in_fuOpType"]
            vsew = self.ports["io_in_vsew"]
            module.d.comb += [
                self.ports["io_out_vs1Type"].eq(Cat(vsew, op[5], Const(0, 1))),
                self.ports["io_out_vs2Type"].eq(Cat(vsew, op[6], Const(0, 1))),
            ]
            return module
        if self.member == "VPermSrcTypeModule":
            op = self.ports["io_in_fuOpType"]
            vsew = self.ports["io_in_vsew"]
            vrgatherei16 = cast(Any, op[5]) & ~cast(Any, op[1])
            vs1 = Mux(vrgatherei16, Const(1, 4),
                      Mux(cast(Any, op[5]) & cast(Any, op[1]), Const(0xF, 4),
                          Cat(vsew, op[6], op[6])))
            module.d.comb += [
                self.ports["io_out_vs1Type"].eq(vs1),
                self.ports["io_out_vs2Type"].eq(Cat(vsew, Const(0, 2))),
            ]
            return module
        for name, direction, _width in self.specs:
            if direction == "output":
                module.d.comb += self.ports[name].eq(0)
        return module


class Og2ForVector(VectorDatapathFamily):
    """Locked V2 Og2ForVector boundary."""

    def __init__(self) -> None:
        super().__init__("Og2ForVector")


class VTypeBuffer(VectorDatapathFamily):
    """Locked V2 VTypeBuffer boundary."""

    def __init__(self) -> None:
        super().__init__("VTypeBuffer")


class VecExcpDataMergeModule(VectorDatapathFamily):
    """Locked V2 vector exception-data merge boundary."""

    def __init__(self) -> None:
        super().__init__("VecExcpDataMergeModule")


class VIAluSrcTypeModule(VectorDatapathFamily):
    """Locked V2 integer-vector source-type decoder leaf."""

    def __init__(self) -> None:
        super().__init__("VIAluSrcTypeModule")


class VIMacSrcTypeModule(VectorDatapathFamily):
    """Locked V2 integer-MAC source-type decoder leaf."""

    def __init__(self) -> None:
        super().__init__("VIMacSrcTypeModule")


class VPermSrcTypeModule(VectorDatapathFamily):
    """Locked V2 permutation source-type decoder leaf."""

    def __init__(self) -> None:
        super().__init__("VPermSrcTypeModule")


def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Emit one same-name member with its exact V2 ANSI surface."""

    del injected_dependencies
    member = "Og2ForVector"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = VectorDatapathFamily(member)
    return verilog.convert(
        top,
        name=member,
        ports=[top.ports[name] for name, _direction, _width in top.specs],
        emit_src=False,
    )


def main() -> None:
    print(build_verilog({"module": "Og2ForVector"}, {}))


if __name__ == "__main__":
    main()
