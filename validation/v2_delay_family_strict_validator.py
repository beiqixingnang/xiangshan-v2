"""Complete delay-family proofs with independent field driver cones."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import v2_registered_family_strict_validator as producer
from v2_strict_family_rail import FamilyRail, ROOT, declared_ports


class DelayFieldRail(FamilyRail):
    """Partition wide DelayReg banks while still asserting the whole design."""

    def inductive_steps(self, name: str) -> str:
        if not name.startswith("DelayReg"):
            return super().inductive_steps(name)
        ports = declared_ports((ROOT / f"validation/reference-sv/{name}.sv").read_text(encoding="utf-8"), name)
        outputs = [port for port, (direction, _width) in ports.items() if direction == "output"]
        if not outputs:
            raise ValueError("DelayReg has no observable output driver cones")
        commands = []
        for index, output in enumerate(outputs):
            commands.extend((
                f"select -set p{index} w:{output} %x t:$equiv %i %ci*",
                f"equiv_induct -undef @p{index}",
            ))
        commands.extend(("select -clear", "equiv_induct -undef"))
        return "; ".join(commands)


def main() -> int:
    producer.FamilyRail = DelayFieldRail
    sys.argv = [str(Path(__file__).resolve()), "--build", "Build-Cpu.Dependency.Utility.DelayFamily",
                "--scala", "upstream/utility/src/main/scala/utility/Hold.scala",
                "--scala", "upstream/difftest/src/main/scala/util/Delayer.scala",
                "--scala", "upstream/src/main/scala/utils/PipeWithFlush.scala",
                "--evidence", "v2-build-cpu-dependency-utility-delayfamily-strict-evidence.json"]
    result = producer.main()
    evidence = ROOT / "validation/v2-build-cpu-dependency-utility-delayfamily-strict-evidence.json"
    if not evidence.is_file():
        return result
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["validator"] = Path(__file__).resolve().relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = producer.source_record(Path(__file__).resolve())
    producer_path = Path(__file__).resolve().with_name("v2_registered_family_strict_validator.py")
    payload["sources"]["validator_dependencies"]["registered_family_producer"] = producer.source_record(producer_path)
    payload["audit_policy"]["partition_policy"] = "DelayReg full output driver cones; final unrestricted induction and whole-design equiv_status -assert; no cutpoint assumptions"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
