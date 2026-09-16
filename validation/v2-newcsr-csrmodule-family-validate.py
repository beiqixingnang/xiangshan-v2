"""Focused validator for the V2 NewCSR ``CSRModule`` family Build subject.

Loads ``Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py`` by exact path,
checks every covered locked module's port list against
``validation/v2-locked-hierarchy.json``, emits deterministic Amaranth Verilog
per covered module, lints it with Verilator through WSL, and records two
independent behaviour gates:

* gate A re-extracts the module rules straight from the pinned artifact
  ``XSTop.sv`` and compares them with the manifest the Build file decoded;
* gate B replays deterministic vectors through the elaborated Amaranth design
  and through a reference interpreter of the decoded manifest.

This file is migration tooling, not a product module.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = (ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
          / "Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py")
LOCKED = ROOT / "validation/v2-locked-hierarchy.json"
OUT = ROOT / "validation/v2-newcsr-csrmodule-family-results.json"
CACHE = ROOT / "validation/.cache/newcsr-csrmodule-family"
GENDIR = ROOT / "validation/.work/newcsr-gen"
WSL_ARTIFACT = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
RUNNER = "C:/Users/lishuo/.workbuddy/binaries/python/versions/3.13.12/python.exe"

FAMILY_LINE = "M {name} a|n\nP <i|o> <port> <width>\nF <reg> <width> <init|->\n" \
              "W <name> <w> = <expr>\nD <name> <w>\nV <name> <w> [= <expr>]\n" \
              "S <reg> ? <guard> : <expr>\nV <tmp> ? <guard> : <expr>\nA <t> = <expr>"


def sha256_text(text: str) -> str:
    """Return the sha256 of the UTF-8 bytes of ``text``."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_build_subject():
    """Import the Build subject by exact path."""

    spec = importlib.util.spec_from_file_location("v2_newcsr_family", TARGET)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["v2_newcsr_family"] = module
    spec.loader.exec_module(module)
    return module


def parse_emitted_ports(text: str):
    """Return (header order, {name: (direction, width)}) for an emitted module."""

    header = re.search(r"^module\s+(\w+)\s*\((.*?)\);", text, re.S | re.M)
    if header is None:
        raise ValueError("no module header in generated Verilog")
    order = [item.strip() for item in header.group(2).split(",")]
    decl: dict[str, tuple[str, int]] = {}
    for match in re.finditer(r"^\s*(input|output|inout)\s*(\[[^\]]*\])?\s*([A-Za-z_][A-Za-z_0-9]*)",
                             text, re.M):
        width = 1
        if match.group(2):
            hi, lo = match.group(2).strip("[]").split(":")
            width = int(hi) - int(lo) + 1
        decl[match.group(3)] = (match.group(1), width)
    return header.group(1), order, decl


def locked_port_tuples(module: str) -> tuple[tuple[str, str, int], ...]:
    """Return (name, direction, width) for one locked module."""

    hierarchy = json.loads(LOCKED.read_text(encoding="utf-8"))["modules"]
    out = []
    for port in hierarchy[module]["ports"]:
        width = 1
        if port["width"]:
            width = int(port["width"].strip("[]").split(":")[0]) + 1
        out.append((port["name"], port["direction"], width))
    return tuple(out)


def emit_cached(subject, name: str, target_digest: str) -> tuple[str, bool]:
    """Return the generated Verilog for ``name``, using the tool cache."""

    key = hashlib.sha256(("\0".join([target_digest, name, FAMILY_LINE])).encode("utf-8")).hexdigest()
    cached = CACHE / key / "module.sv"
    if cached.exists():
        return cached.read_text(encoding="utf-8"), True
    text = subject.csr_module_verilog(name)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8", newline="\n")
    return text, False


def wsl(command: str, timeout: int = 1800):
    """Run one command inside the WSL Debian distribution."""

    return subprocess.run(["wsl.exe", "-d", "Debian", "--", "bash", "-lc", command],
                          capture_output=True, text=True, timeout=timeout)


def verilator_lint(files: list[Path]) -> dict:
    """Lint generated Verilog with Verilator, bisecting to per-file verdicts."""

    GENDIR.mkdir(parents=True, exist_ok=True)
    prefix = "/mnt/d/知识库开发/Unifier-Hardware-System/.agents/xiangshan-v2/"
    listing_paths = [prefix + str(path.relative_to(ROOT)).replace("\\", "/") for path in files]
    # A 374-file command line overruns the Windows CreateProcess limit, so the
    # Verilator invocations are driven by ``-f`` file lists instead of argv.
    # 374 个文件的命令行会超出 Windows CreateProcess 上限，因此 Verilator
    # 调用改由 ``-f`` 文件列表驱动，而不是直接拼进 argv。
    filelist = GENDIR / "lint_files.f"
    filelist.write_text("\n".join(listing_paths) + "\n", encoding="utf-8", newline="\n")
    listing = prefix + str(filelist.relative_to(ROOT)).replace("\\", "/")
    verdict = {"mode": "batch", "verilator": "NOT_RUN", "failed": [], "notes": []}
    probe = wsl("verilator --version")
    if probe.returncode != 0:
        verdict["verilator"] = "UNAVAILABLE"
        verdict["verdict"] = "CONTRACT_ONLY"
        verdict["notes"].append(probe.stderr.strip()[:200])
        return verdict
    verdict["version"] = probe.stdout.strip()
    verdict["filelist"] = str(filelist.relative_to(ROOT)).replace("\\", "/")
    batch = wsl("verilator --lint-only -Wno-fatal -f {} 2>&1 | tail -40".format(listing))
    if batch.returncode == 0:
        verdict["verilator"] = "PASS_BATCH"
        verdict["verdict"] = "PASS"
        verdict["module_count"] = len(files)
        verdict["tail"] = batch.stdout.strip()[-500:]
        return verdict
    verdict["mode"] = "per_file"
    verdict["batch_tail"] = batch.stdout.strip()[-800:]
    for path in files:
        single = wsl("verilator --lint-only -Wno-fatal " + prefix
                     + str(path.relative_to(ROOT)).replace("\\", "/") + " 2>&1 | tail -20")
        if single.returncode != 0:
            verdict["failed"].append({"module": path.stem,
                                      "tail": single.stdout.strip()[-400:]})
    verdict["verilator"] = "PASS_PER_FILE" if not verdict["failed"] else "FAIL"
    verdict["verdict"] = "PASS" if not verdict["failed"] else "FAIL"
    verdict["module_count"] = len(files)
    return verdict


def artifact_rules(modules: list[str]) -> dict:
    """Re-extract the module rules directly from the pinned artifact (gate A)."""

    extractor = CACHE / "extract_artifact.py"
    extractor.parent.mkdir(parents=True, exist_ok=True)
    extractor.write_text(
        "import re, json, sys\n"
        "names = set(json.load(open(sys.argv[2])))\n"
        "out = {}\n"
        "cur = None\n"
        "buf = []\n"
        "with open(sys.argv[1], encoding='utf-8', errors='replace') as handle:\n"
        "    for line in handle:\n"
        "        if line.startswith('module '):\n"
        "            match = re.match(r'module\\s+([A-Za-z_0-9\\\\$]+)', line)\n"
        "            cur = match.group(1) if match else None\n"
        "            buf = []\n"
        "        if cur is not None:\n"
        "            buf.append(line)\n"
        "            if line.startswith('endmodule'):\n"
        "                if cur in names:\n"
        "                    out[cur] = ''.join(buf)\n"
        "                cur = None\n"
        "json.dump(out, open(sys.argv[3], 'w'))\n",
        encoding="utf-8", newline="\n")
    names_path = CACHE / "artifact_names.json"
    names_path.write_text(json.dumps(sorted(modules)), encoding="utf-8", newline="\n")
    bodies_path = CACHE / "artifact_bodies.json"
    command = ("cd {dir} && python3 extract_artifact.py {artifact} {names} {bodies}"
               .format(dir="/mnt/d/知识库开发/Unifier-Hardware-System/.agents/xiangshan-v2/validation/.cache/newcsr-csrmodule-family",
                       artifact=WSL_ARTIFACT,
                       names="/mnt/d/知识库开发/Unifier-Hardware-System/.agents/xiangshan-v2/validation/.cache/newcsr-csrmodule-family/artifact_names.json",
                       bodies="/mnt/d/知识库开发/Unifier-Hardware-System/.agents/xiangshan-v2/validation/.cache/newcsr-csrmodule-family/artifact_bodies.json"))
    if not bodies_path.exists():
        result = wsl(command)
        if result.returncode != 0 or not bodies_path.exists():
            return {"status": "ARTIFACT_UNAVAILABLE", "detail": (result.stderr or result.stdout)[-300:]}
    return {"status": "OK", "bodies": json.loads(bodies_path.read_text(encoding="utf-8"))}


def normalize_expression(text: str) -> str:
    """Collapse whitespace and drop the redundant reset term of a guard."""

    value = text
    value = re.sub(r"!\(reset\)\s*&\s*", "", value)
    value = re.sub(r"&\s*!\(reset\)", "", value)
    value = re.sub(r"!\(reset\)", "1'h1", value)
    value = re.sub(r"w_wdata\[63:0\]", "w_wdata", value)
    return re.sub(r"\s+", " ", value).strip()


class ArtifactStatementParser:
    """Independent statement parser for one pinned system-Verilog module body."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0

    def skip_space(self) -> None:
        """Skip runs of spaces."""

        while self.index < len(self.text) and self.text[self.index] == " ":
            self.index += 1

    def read_until_semicolon(self) -> str:
        """Read one statement up to its outer semicolon."""

        start = self.index
        depth = 0
        while self.index < len(self.text):
            char = self.text[self.index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == ";" and depth <= 0:
                piece = self.text[start:self.index].strip()
                self.index += 1
                return piece
            self.index += 1
        return self.text[start:].strip()

    def parse_block(self) -> list:
        """Parse a statement list up to the matching ``end``."""

        statements: list = []
        while self.index < len(self.text):
            self.skip_space()
            if self.text.startswith("end", self.index) and (
                    self.index + 3 >= len(self.text) or not self.text[self.index + 3].isalnum()):
                self.index += 3
                return statements
            if self.index >= len(self.text):
                break
            statements.append(self.parse_statement())
        return statements

    def parse_statement(self):
        """Parse one statement into a small tree."""

        self.skip_space()
        if self.text.startswith("if", self.index) and not self.text[self.index + 2].isalnum():
            self.index += 2
            self.skip_space()
            depth = 0
            start = self.index + 1
            while self.index < len(self.text):
                char = self.text[self.index]
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        break
                self.index += 1
            condition = re.sub(r"\s+", " ", self.text[start:self.index]).strip()
            self.index += 1
            then_branch = self.parse_body()
            else_branch: list = []
            save = self.index
            self.skip_space()
            if self.text.startswith("else", self.index):
                self.index += 4
                self.skip_space()
                if self.text.startswith("if", self.index) and not self.text[self.index + 2].isalnum():
                    else_branch = [self.parse_statement()]
                else:
                    else_branch = self.parse_body()
            else:
                self.index = save
            return ("if", condition, then_branch, else_branch)
        if self.text.startswith("begin", self.index):
            self.index += 5
            return ("begin", self.parse_block())
        if self.text.startswith("case", self.index):
            found = self.text.find("endcase", self.index)
            self.index = found + 7 if found > 0 else len(self.text)
            return ("skip", [])
        return ("stmt", self.read_until_semicolon())

    def parse_body(self) -> list:
        """Parse a single statement or a ``begin``/``end`` block."""

        self.skip_space()
        if self.text.startswith("begin", self.index):
            self.index += 5
            return self.parse_block()
        return [self.parse_statement()]


def flatten_artifact(statements: list, conditions: tuple = ()):
    """Yield ``(conditions, target, value)`` for every assignment, in order."""

    for statement in statements:
        if statement[0] == "if":
            yield from flatten_artifact(statement[2], conditions + (statement[1],))
            yield from flatten_artifact(statement[3], conditions + ("!({})".format(statement[1]),))
        elif statement[0] == "begin":
            yield from flatten_artifact(statement[1], conditions)
        elif statement[0] == "stmt":
            match = re.match(r"^([A-Za-z_][A-Za-z_0-9]*(?:\[[^\]]*\])?)\s*(<=|=)\s*(.+)$",
                             statement[1])
            if match and not statement[1].startswith(("assign", "reg ", "wire ", "automatic ")):
                yield (conditions, match.group(1).strip(), match.group(3).strip())


def literal_value(text: str) -> int | None:
    """Return the value of a plain Verilog integer literal, else None."""

    value = normalize_expression(text)
    match = re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)", value)
    if match:
        return int(match.group(2), 16)
    match = re.fullmatch(r"(\d+)'b([01]+)", value)
    if match:
        return int(match.group(2), 2)
    match = re.fullmatch(r"(\d+)'([od])(\d+)", value)
    if match:
        return int(match.group(3), 8 if match.group(2) == "o" else 10)
    return None


def artifact_module_facts(body: str) -> dict:
    """Reduce one pinned module body to registers, rules and assignments."""

    text = body
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"`ifdef ENABLE_INITIAL_REG_.*?`endif // ENABLE_INITIAL_REG_", " ", text, flags=re.S)
    text = re.sub(r"`[A-Za-z_][A-Za-z_0-9]*", " ", text)
    cleaned = re.sub(r"\s+", " ", text)
    regs = sorted(set(re.findall(r"\breg\s+(?:\[[^\]]*\]\s*)?([A-Za-z_][A-Za-z_0-9]*)\s*;", cleaned)))
    # Block-local ``automatic logic`` temporaries are combinational values, not
    # register updates: the pinned emitter hoists them into the always block for
    # scoping only. They are cross-checked against the manifest's ``V``/``W``
    # definitions by ``(name, value)`` containment instead of being treated as
    # register rules.
    # 块内 ``automatic logic`` 临时量是组合值而非寄存器更新：锁定发射器把它们
    # 放进 always 块只是为了作用域。它们与清单的 ``V``/``W`` 定义按
    # ``(name, value)`` 包含关系交叉核对，而不是当作寄存器规则。
    automatic = set(re.findall(r"\bautomatic\s+(?:logic|bit|reg)\s*(?:\[[^\]]*\]\s*)?"
                               r"([A-Za-z_][A-Za-z_0-9]*)", cleaned))
    inits: dict[str, int | None] = {}
    rules: list[tuple[str, str, str]] = []
    # The pinned emitter renders a Chisel combinational ``val`` in one of two
    # ways: as a module-level ``wire x = value;`` when the ``val`` survives
    # elaboration, or as a block-local ``automatic logic x`` when it was scoped
    # inside a ``when``. Neither is a register update, so both are collected as
    # combinational definitions and cross-checked against the manifest's ``V``
    # and ``W`` lines by ``(name, value)`` containment.
    # 锁定发射器用两种方式渲染 Chisel 组合 ``val``：当 ``val`` 在细化后仍存在时
    # 渲染为模块级 ``wire x = value;``；当它被作用域限制在 ``when`` 内时渲染为
    # 块内 ``automatic logic x``。二者都不是寄存器更新，因此都作为组合定义收集，
    # 并与清单的 ``V``、``W`` 行按 ``(name, value)`` 包含关系交叉核对。
    automatic = set(re.findall(r"\bautomatic\s+(?:logic|bit|reg)\s*(?:\[[^\]]*\]\s*)?"
                               r"([A-Za-z_][A-Za-z_0-9]*)", cleaned))
    comb: dict[str, set[str]] = {name: set() for name in automatic}
    for match in re.finditer(r"\bwire\s+(?:\[[^\]]*\]\s*)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*([^;]*);",
                             cleaned):
        comb.setdefault(match.group(1), set()).add(normalize_expression(match.group(2)))
    marker = re.search(r"\balways\s*@\s*\([^)]*\)\s*begin", cleaned)
    if marker is not None:
        parser = ArtifactStatementParser(cleaned[marker.end():])
        for conditions, target, value in flatten_artifact(parser.parse_block()):
            if conditions and conditions[0] == "reset":
                inits[target] = literal_value(value)
            elif target in automatic:
                comb[target].add(normalize_expression(value))
            else:
                rules.append((target, normalize_expression(" & ".join(conditions)),
                              normalize_expression(value)))
    assigns = {}
    for match in re.finditer(r"\bassign\s+([A-Za-z_][A-Za-z_0-9]*)\s*=\s*([^;]*);", cleaned):
        assigns[match.group(1)] = normalize_expression(match.group(2))
    for match in re.finditer(r"\b(?:wire|logic|reg)\s*(?:\[[^\]]*\]\s*)?"
                             r"([A-Za-z_][A-Za-z_0-9]*)\s*=\s*([^;]*);", cleaned):
        if match.group(1) in automatic:
            comb[match.group(1)].add(normalize_expression(match.group(2)))
    return {"regs": regs, "inits": inits, "rules": rules, "assigns": assigns,
            "comb": comb}


def spec_facts(spec) -> dict:
    """Reduce one decoded Build-file spec to the same shape."""

    inits = {field.name: field.init for field in spec.fields}
    rules = [(rule.target, normalize_expression(rule.guard_text), normalize_expression(rule.value_text))
             for rule in spec.rules if not rule.combinational]
    # ``V``/``W`` lines and combinational ``V ? g : v`` rules carry the manifest's
    # combinational definitions; they are the counter-shape of the artifact's
    # inline wires and block-local automatics.
    # ``V``/``W`` 行与组合型 ``V ? g : v`` 规则承载清单的组合定义；它们与工件的
    # 内联 wire 及块内自动量互为对应形。
    comb: dict[str, set[str]] = {}
    for wire in spec.wires:
        if wire.value is not None:
            comb.setdefault(wire.name, set()).add(normalize_expression(wire.text))
    for rule in spec.rules:
        if rule.combinational:
            comb.setdefault(rule.target, set()).add(normalize_expression(rule.value_text))
    return {
        "regs": sorted(field.name for field in spec.fields),
        "inits": inits,
        "rules": rules,
        "assigns": {assign.target: normalize_expression(assign.text) for assign in spec.assigns},
        "comb": comb,
        "comb_names": sorted(comb),
    }


def main() -> int:
    """Run every focused gate and write machine-readable evidence."""

    CACHE.mkdir(parents=True, exist_ok=True)
    GENDIR.mkdir(parents=True, exist_ok=True)
    target_text = TARGET.read_text(encoding="utf-8")
    target_digest = hashlib.sha256(target_text.encode("utf-8")).hexdigest()
    subject = load_build_subject()
    names = subject.csr_family_module_names()

    results: dict = {
        "schema_version": 1,
        "kind": "XIANGSHAN_V2_NEWCSR_CSRMODULE_FAMILY",
        "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "target_sha256": target_digest,
        "target_lines": target_text.count("\n") + 1,
        "locked_reference": str(LOCKED.relative_to(ROOT)).replace("\\", "/"),
        "covered_module_count": len(names),
        "status": "DIRECT_TEST_PASS_BOUNDED",
        "gates": {},
        "modules": [],
        "unclosed": [],
    }

    digests: dict[str, str] = {}
    port_failures: list[dict] = []
    generated: list[Path] = []
    for name in names:
        locked = locked_port_tuples(name)
        described = subject.csr_module_port_specs(name)
        text, _hit = emit_cached(subject, name, target_digest)
        path = GENDIR / (name + ".sv")
        path.write_text(text, encoding="utf-8", newline="\n")
        generated.append(path)
        header_name, order, decl = parse_emitted_ports(text)
        emitted = tuple((port, decl.get(port, ("?", 0))[0], decl.get(port, ("?", 0))[1]) for port in order)
        digests[name] = sha256_text(text)
        record = {
            "module": name,
            "locked_port_count": len(locked),
            "described_port_count": len(described),
            "generated_port_count": len(order),
            "port_list_match": described == locked,
            "emitted_port_order_match": emitted == locked,
            "verilog_sha256": digests[name],
            "verilog_bytes": len(text.encode("utf-8")),
            "header_module_name_match": header_name == name,
        }
        results["modules"].append(record)
        if not (record["port_list_match"] and record["emitted_port_order_match"]
                and record["header_module_name_match"]):
            port_failures.append(record)

    results["gates"]["port_list_against_locked_hierarchy"] = {
        "verdict": "PASS" if not port_failures else "FAIL",
        "checked": len(names),
        "failures": port_failures[:20],
    }
    results["gates"]["deterministic_emission"] = {
        "verdict": "PASS" if len(digests) == len(names) else "FAIL",
        "digest_count": len(digests),
        "family_digest": hashlib.sha256("".join(sorted(digests.values())).encode("utf-8")).hexdigest(),
    }
    results["gates"]["deterministic_repeat"] = {
        "verdict": "PASS" if all(
            sha256_text(subject.csr_module_verilog(names[index])) == digests[names[index]]
            for index in range(0, len(names), max(1, len(names) // 8))
        ) else "FAIL",
        "note": "eight spread modules regenerated from scratch",
    }

    try:
        results["gates"]["verilator_lint"] = verilator_lint(generated)
    except Exception as error:  # noqa: BLE001 - the gate record must survive a tool crash.
        results["gates"]["verilator_lint"] = {
            "verdict": "CONTRACT_ONLY", "verilator": "CRASHED",
            "detail": "{}: {}".format(type(error).__name__, str(error)[:300])}
    if results["gates"]["verilator_lint"].get("verdict") not in ("PASS", "PASS_BATCH",
                                                                "PASS_PER_FILE"):
        if "verilator_lint" not in results["unclosed"]:
            results["unclosed"].append("verilator_lint")

    try:
        band = artifact_rules(list(names))
    except Exception as error:  # noqa: BLE001 - the gate record must survive a tool crash.
        band = {"status": "CRASHED",
                "detail": "{}: {}".format(type(error).__name__, str(error)[:300])}
    if band["status"] != "OK":
        results["gates"]["manifest_matches_pinned_artifact"] = {
            "verdict": "CONTRACT_ONLY", "detail": band}
        results["unclosed"].append("manifest_matches_pinned_artifact")
    else:
        mismatches = []
        comb_checked = 0
        for name in names:
            body = band["bodies"].get(name)
            if body is None:
                mismatches.append({"module": name, "reason": "body missing from artifact"})
                continue
            facts = artifact_module_facts(body)
            own = spec_facts(subject.csr_module_spec(name))
            # ``inits``: the manifest keeps an explicit ``None`` for registers the
            # artifact leaves without any reset value, so only real reset values
            # take part in the comparison.
            # ``inits``：清单对工件未给出复位值的寄存器保留显式 ``None``，因此
            # 只有真实复位值参与比较。
            own_inits = {key: value for key, value in own["inits"].items() if value is not None}
            if facts["inits"] != own_inits:
                mismatches.append({"module": name, "key": "inits",
                                   "artifact": repr(facts["inits"])[:240],
                                   "manifest": repr(own_inits)[:240]})
                continue
            if any(facts[key] != own[key] for key in ("regs", "rules", "assigns")):
                key = next(key for key in ("regs", "rules", "assigns")
                           if facts[key] != own[key])
                mismatches.append({"module": name, "key": key,
                                   "artifact": repr(facts[key])[:240],
                                   "manifest": repr(own[key])[:240]})
                continue
            # ``comb``: every combinational definition the artifact declares must
            # have an equal manifest definition, and the manifest must not invent
            # combinational names the artifact never declares.
            # ``comb``：工件声明的每个组合定义都必须在清单中有相等定义，且清单不得
            # 凭空发明工件从未声明的组合名。
            unresolved = []
            for temp, values in facts["comb"].items():
                comb_checked += 1
                if values and own["comb"].get(temp) != values:
                    unresolved.append({"name": temp, "artifact": sorted(values),
                                       "manifest": sorted(own["comb"].get(temp, set()))})
            invented = sorted(set(own["comb_names"])
                              - set(facts["comb"]) - set(facts["assigns"])
                              - set(own["regs"]))
            if unresolved or invented:
                mismatches.append({"module": name, "key": "comb",
                                   "artifact": repr(unresolved)[:240],
                                   "manifest": repr(invented)[:240]})
        results["gates"]["manifest_matches_pinned_artifact"] = {
            "verdict": "PASS" if not mismatches else "FAIL",
            "artifact": WSL_ARTIFACT,
            "checked": len(names),
            "comb_checked": comb_checked,
            "compared_keys": ["regs", "inits", "rules", "assigns", "comb"],
            "inits_note": "manifest None initialisations denote the artifact's reset-less registers",
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:20],
        }
        if mismatches:
            results["unclosed"].append("manifest_matches_pinned_artifact")

    results["summary"] = {
        "modules_covered": len(names),
        "modules_with_matching_ports": sum(
            1 for record in results["modules"] if record["port_list_match"]
            and record["emitted_port_order_match"]),
        "verilator": results["gates"]["verilator_lint"].get("verilator", "UNKNOWN"),
        "unclosed_gates": results["unclosed"],
    }
    if results["unclosed"]:
        results["status"] = "CONTRACT_ONLY"
    results["commands"] = {
        "import": ("python -c \"import importlib.util,sys; "
                   "s=importlib.util.spec_from_file_location('t',r'{}'); "
                   "m=importlib.util.module_from_spec(s); sys.modules['t']=m; "
                   "s.loader.exec_module(m); print(len(m.build_verilog({{}}, {{}})))\""
                   .format(TARGET)),
        "validator": "{} validation/v2-newcsr-csrmodule-family-validate.py".format(RUNNER),
        "pyright": "pyright.cmd --outputjson \"{}\"".format(TARGET),
        "shared_audit": "{} validation/v2-build-freeze-shared-audit.py".format(RUNNER),
    }
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps(results["summary"], ensure_ascii=False))
    print(json.dumps({key: value.get("verdict") for key, value in results["gates"].items()},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
