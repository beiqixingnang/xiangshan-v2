"""Combinational bit selection and priority mux utility family."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal, Value
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    "PrioritySource",
    "PriorityMuxConfig",
    "BitSelectConfig",
    "BitSelectFamily",
    "COVERED_MODULES",
    "IMPLEMENTED_MEMBERS",
    "CONTRACT_ONLY_MEMBERS",
    "family_configuration",
    "build_verilog",
    "main",
]

COVERED_MODULES = (
    "PriorityMuxModule",
    "PriorityMuxModule_4",
    "PriorityMuxModule_8",
    "PriorityMuxModule_12",
    "PriorityMuxModule_16",
    "PriorityMuxModule_20",
    "UIntCompressor_27_000011100000000000001010101",
    "UIntCompressor_27_000000000000001010100000000",
    "UIntExtractor_27_000011100000000000001010101",
    "UIntExtractor_27_000000000000001010100000000",
)
IMPLEMENTED_MEMBERS = COVERED_MODULES
CONTRACT_ONLY_MEMBERS: tuple[str, ...] = ()


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class PrioritySource:
    """One priority input bundle; a missing selector marks the fallback."""

    selector: str | None
    data_prefix: str


@dataclass(frozen=True)
class PriorityMuxConfig:
    """Exact flattened fields and priority order for one mux member."""

    member_name: str
    output_prefix: str
    fields: tuple[tuple[str, int], ...]
    sources: tuple[PrioritySource, ...]


@dataclass(frozen=True)
class BitSelectConfig:
    """A finite compressor/extractor bit geometry derived from its member mask."""

    member_name: str
    operation: Literal["compress", "extract"]
    input_width: int
    output_width: int
    selected_bits: tuple[int, ...]


HISTORY_GEOMETRY = (
    (17, 11), (16, 11), (15, 7), (14, 8), (13, 9), (12, 4),
    (11, 8), (10, 9), (9, 7), (8, 8), (7, 7), (6, 9), (5, 7),
    (4, 8), (3, 8), (2, 8), (1, 11),
)
AFHOB_ROW_GEOMETRY = ((5, 4), (4, 3), (3, 4), (2, 4), (1, 4), (0, 4))


def history_fields() -> tuple[tuple[str, int], ...]:
    return tuple((f"hist_{index}_folded_hist", width)
                 for index, width in HISTORY_GEOMETRY)


def afhob_fields() -> tuple[tuple[str, int], ...]:
    return tuple((f"afhob_{row}_bits_{bit}", 1)
                 for row, count in AFHOB_ROW_GEOMETRY
                 for bit in range(count))


PRIORITY_MUX_CONFIGS = (
    PriorityMuxConfig(
        "PriorityMuxModule", "out_res", (("", 50),),
        (PrioritySource("s2_target_sel", "s2_target_src"),
         PrioritySource("s1_target_sel", "s1_target_src"),
         PrioritySource("s3_target_sel", "s3_target_src"),
         PrioritySource("redirect_target_sel", "redirect_target_src"),
         PrioritySource(None, "stallPC_src")),
    ),
    PriorityMuxConfig(
        "PriorityMuxModule_4", "out_res_", history_fields(),
        (PrioritySource("s2_FGH_sel", "s2_FGH_src_"),
         PrioritySource("s1_FGH_sel", "s1_FGH_src_"),
         PrioritySource("s3_FGH_sel", "s3_FGH_src_"),
         PrioritySource("redirect_FGHT_sel", "redirect_FGHT_src_"),
         PrioritySource(None, "stallFGH_src_")),
    ),
    PriorityMuxConfig(
        "PriorityMuxModule_8", "out_res_", (("flag", 1), ("value", 8)),
        (PrioritySource("s2_GHPtr_sel", "s2_GHPtr_src_"),
         PrioritySource("s1_GHPtr_sel", "s1_GHPtr_src_"),
         PrioritySource("s3_GHPtr_sel", "s3_GHPtr_src_"),
         PrioritySource("redirect_GHPtr_sel", "redirect_GHPtr_src_"),
         PrioritySource(None, "stallGHPtr_src_")),
    ),
    PriorityMuxConfig(
        "PriorityMuxModule_12", "out_res_", afhob_fields(),
        (PrioritySource("s2_AFHOB_sel", "s2_AFHOB_src_"),
         PrioritySource("s1_AFHOB_sel", "s1_AFHOB_src_"),
         PrioritySource("s3_AFHOB_sel", "s3_AFHOB_src_"),
         PrioritySource("redirect_AFHOB_sel", "redirect_AFHOB_src_"),
         PrioritySource(None, "stallAFHOB_src_")),
    ),
    PriorityMuxConfig(
        "PriorityMuxModule_16", "out_res", (("", 3),),
        (PrioritySource("s2_BrNumOH_sel", "s2_BrNumOH_src"),
         PrioritySource("s1_BrNumOH_sel", "s1_BrNumOH_src"),
         PrioritySource("s3_BrNumOH_sel", "s3_BrNumOH_src"),
         PrioritySource("redirect_BrNumOH_sel", "redirect_BrNumOH_src"),
         PrioritySource(None, "stallBrNumOH_src")),
    ),
    PriorityMuxConfig(
        "PriorityMuxModule_20", "out_res", (("", 1),),
        (PrioritySource("s2_new_bit_0_sel", "s2_new_bit_0_src"),
         PrioritySource("s1_new_bit_0_sel", "s1_new_bit_0_src"),
         PrioritySource("s3_new_bit_0_sel", "s3_new_bit_0_src"),
         PrioritySource(None, "redirect_new_bit_0_src")),
    ),
)

BITSELECT_MASKS = (
    ("UIntCompressor_27_000011100000000000001010101",
     "000011100000000000001010101"),
    ("UIntCompressor_27_000000000000001010100000000",
     "000000000000001010100000000"),
    ("UIntExtractor_27_000011100000000000001010101",
     "000011100000000000001010101"),
    ("UIntExtractor_27_000000000000001010100000000",
     "000000000000001010100000000"),
)


def bit_positions(mask: str) -> tuple[int, ...]:
    if len(mask) != 27 or set(mask) - {"0", "1"}:
        raise ValueError("bit selection mask must contain exactly 27 binary digits")
    return tuple(index for index, selected in enumerate(reversed(mask)) if selected == "1")


BITSELECT_CONFIGS = tuple(
    BitSelectConfig(
        member_name=name,
        operation="compress" if name.startswith("UIntCompressor_") else "extract",
        input_width=len(bit_positions(mask)) if name.startswith("UIntExtractor_") else 27,
        output_width=27 if name.startswith("UIntExtractor_") else len(bit_positions(mask)),
        selected_bits=bit_positions(mask),
    )
    for name, mask in BITSELECT_MASKS
)

_CONFIGURATIONS: dict[str, PriorityMuxConfig | BitSelectConfig] = {
    configuration.member_name: configuration
    for configuration in (*PRIORITY_MUX_CONFIGS, *BITSELECT_CONFIGS)
}


# =============================================================================
# Implementation
# =============================================================================
class BitSelectFamily(Elaboratable):
    """Elaborate one exact priority mux or bit selection member."""

    def __init__(self, configuration: PriorityMuxConfig | BitSelectConfig | str | None = None) -> None:
        self.configuration = resolve_configuration(configuration)
        self.inputs: dict[str, Signal] = {}
        self.outputs: dict[str, Signal] = {}
        self.port_directions: dict[str, Literal["input", "output"]] = {}

        config = self.configuration
        if isinstance(config, PriorityMuxConfig):
            for source in config.sources:
                if source.selector is not None:
                    self.inputs[source.selector] = Signal(name=source.selector)
                for suffix, width in config.fields:
                    name = source.data_prefix + suffix
                    self.inputs[name] = Signal(width, name=name)
            for suffix, width in config.fields:
                name = config.output_prefix + suffix
                self.outputs[name] = Signal(width, name=name)
        else:
            self.inputs["io_in"] = Signal(config.input_width, name="io_in")
            self.outputs["io_out"] = Signal(config.output_width, name="io_out")

        self.port_directions.update({name: "input" for name in self.inputs})
        self.port_directions.update({name: "output" for name in self.outputs})
        self.ports = tuple(self.inputs.values()) + tuple(self.outputs.values())

    def elaborate(self, platform: object) -> Module:
        del platform
        module = Module()
        config = self.configuration
        if isinstance(config, PriorityMuxConfig):
            fallback = config.sources[-1]
            for suffix, _width in config.fields:
                selected = self.inputs[fallback.data_prefix + suffix]
                for source_index in range(len(config.sources) - 2, -1, -1):
                    source = config.sources[source_index]
                    if source.selector is None:
                        raise ValueError("only the final priority source may omit a selector")
                    boundary = Signal(
                        len(selected),
                        name=f"priority_{source_index}_{config.member_name}_{suffix or 'value'}",
                    )
                    module.d.comb += boundary.eq(Mux(
                        self.inputs[source.selector],
                        self.inputs[source.data_prefix + suffix],
                        selected,
                    ))
                    selected = boundary
                module.d.comb += self.outputs[config.output_prefix + suffix].eq(selected)
            return module

        if config.operation == "compress":
            module.d.comb += self.outputs["io_out"].eq(
                Cat(*(self.inputs["io_in"][index] for index in config.selected_bits))
            )
            return module

        result_bits: list[Value] = [Const(0, 1) for _ in range(config.output_width)]
        for source_index, destination_bit in enumerate(config.selected_bits):
            result_bits[destination_bit] = Value.cast(self.inputs["io_in"][source_index])
        module.d.comb += self.outputs["io_out"].eq(Cat(*result_bits))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def family_configuration(member_name: str) -> PriorityMuxConfig | BitSelectConfig:
    try:
        return _CONFIGURATIONS[member_name]
    except KeyError as exc:
        raise ValueError(f"unknown bit-select family member: {member_name}") from exc


def resolve_configuration(
    configuration: PriorityMuxConfig | BitSelectConfig | dict[str, object] | str | None,
) -> PriorityMuxConfig | BitSelectConfig:
    if configuration is None:
        return family_configuration(COVERED_MODULES[0])
    if isinstance(configuration, str):
        return family_configuration(configuration)
    if isinstance(configuration, (PriorityMuxConfig, BitSelectConfig)):
        registered = _CONFIGURATIONS.get(configuration.member_name)
        if registered != configuration:
            raise ValueError("configuration must match a declared family member")
        return configuration
    if isinstance(configuration, dict):
        member_name = configuration.get("module", COVERED_MODULES[0])
        if not isinstance(member_name, str):
            raise TypeError("configuration['module'] must be a string")
        return family_configuration(member_name)
    raise TypeError("configuration must be a member name, family configuration, dict, or None")


def build_verilog(
    configuration: PriorityMuxConfig | BitSelectConfig | dict[str, object] | str | None = None,
    injected_dependencies: dict[str, object] | None = None,
) -> str:
    del injected_dependencies
    selected = resolve_configuration(configuration)
    top = BitSelectFamily(selected)
    return verilog.convert(top, name=selected.member_name, ports=top.ports,
                           emit_src=False, strip_internal_attrs=True)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> int:
    print(build_verilog())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
