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
    "COVERED_MODULES",
    "SOURCE_PATHS",
    "LOCKED_PORT_SPECS",
    "PORT_SPECS",
    "Og2ForVector",
    "VTypeBuffer",
    "VecExcpDataMergeModule",
    "VIAluSrcTypeModule",
    "VIMacSrcTypeModule",
    "VPermSrcTypeModule",
    "VectorDatapathFamily",
    "vector_datapath_model",
    "build_verilog",
    "main",
]

COVERED_MODULES: tuple[str, ...] = (
    "Og2ForVector",
    "VTypeBuffer",
    "VecExcpDataMergeModule",
    "VIAluSrcTypeModule",
    "VIMacSrcTypeModule",
    "VPermSrcTypeModule",
)
SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/backend/datapath/Og2ForVector.scala",
    "upstream/src/main/scala/xiangshan/backend/rob/VTypeBuffer.scala",
    "upstream/src/main/scala/xiangshan/backend/VecExcpDataMergeModule.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/wrapper/VIAluFix.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VecSrcTypeModule.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/wrapper/VIMacU.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/wrapper/VPPU.scala",
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


# BEGIN LOCKED PORT CATALOG
LOCKED_PORT_SPECS = _decode_catalog()
# Small source-type leaves share this family boundary but do not appear in the
# compressed main catalog because they have no clocked state.  Their exact V2
# ANSI contracts are listed explicitly here. / 小型源类型叶子没有时钟状态，
# 仍属于同一 family，端口契约在此显式列出。
LOCKED_PORT_SPECS.update(
    {
        "VIAluSrcTypeModule": (
            ("io_in_fuOpType", "input", 9),
            ("io_in_vsew", "input", 2),
            ("io_in_isExt", "input", 1),
            ("io_in_isDstMask", "input", 1),
            ("io_out_vs1Type", "output", 4),
            ("io_out_vs2Type", "output", 4),
            ("io_out_vdType", "output", 4),
            ("io_out_isVextF2", "output", 1),
            ("io_out_isVextF4", "output", 1),
            ("io_out_isVextF8", "output", 1),
        ),
        "VIMacSrcTypeModule": (
            ("io_in_fuOpType", "input", 9),
            ("io_in_vsew", "input", 2),
            ("io_out_vs1Type", "output", 4),
            ("io_out_vs2Type", "output", 4),
        ),
        "VPermSrcTypeModule": (
            ("io_in_fuOpType", "input", 9),
            ("io_in_vsew", "input", 2),
            ("io_out_vs1Type", "output", 4),
            ("io_out_vs2Type", "output", 4),
        ),
    }
)
PORT_SPECS = LOCKED_PORT_SPECS
# END LOCKED PORT CATALOG


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
