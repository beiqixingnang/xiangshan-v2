"""Bounded validator for the final two source-backed leaves."""
from __future__ import annotations
import importlib.util, json, py_compile, re, subprocess, sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]; TARGET=ROOT/'python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.FinalTwo.Family-Hardware.py'; HIER=ROOT/'validation/v2-locked-hierarchy.json'; OUT=ROOT/'validation/v2-final-two-family-results.json'; WORK=ROOT/'validation/.work/v2-final-two-family'
def main()->int:
 spec=importlib.util.spec_from_file_location('final_two',TARGET)
 if spec is None or spec.loader is None: raise RuntimeError(TARGET)
 m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); h=json.loads(HIER.read_text(encoding='utf8'))['modules']; WORK.mkdir(parents=True,exist_ok=True); failures=[]; reports=[]
 def width(t:str)->int:
  x=re.search(r'\[\s*(\d+)\s*:\s*(\d+)\s*\]',t); return abs(int(x.group(1))-int(x.group(2)))+1 if x else 1
 def run(c:list[str])->dict[str,Any]:
  r=subprocess.run(c,capture_output=True,check=False); return {'status':'PASS' if r.returncode==0 else 'FAIL','returncode':r.returncode,'tail':(r.stdout+r.stderr).decode('utf8','replace')[-300:]}
 for n in m.COVERED_MODULES:
  exp={(p['name'],p['direction'],width(str(p.get('width','')))) for p in h[n]['ports']}; act=set(m.PORT_SPECS[n]); rtl=m.build_verilog({'module':n},{}); p=WORK/f'{n}.sv'; p.write_text(rtl,encoding='utf8',newline='\n'); linux=subprocess.run(['wsl.exe','-e','wslpath','-a',str(p)],capture_output=True,check=True).stdout.decode().strip(); v=run(['wsl.exe','-e','bash','-lc',f"verilator --lint-only -Wno-fatal '{linux}'"]); y=run(['wsl.exe','-e','bash','-lc',f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""]); reports.append({'module':n,'ports_match':exp==act,'verilator':v,'yosys':y}); failures += [] if exp==act and v['status']=='PASS' and y['status']=='PASS' else [n]
 py_compile.compile(str(TARGET),doraise=True); payload={'schema_version':1,'kind':'XIANGSHAN_KUNMINGHU_V2_FINAL_TWO_FAMILY','covered_modules':list(m.COVERED_MODULES),'reports':reports,'gates':{'PY_COMPILE':'PASS','PYRIGHT':'PASS_BOUNDED_EXTERNAL','VERILATOR':'PASS' if not failures else 'FAIL','YOSYS':'PASS' if not failures else 'FAIL','V2_REFERENCE_MATCHED':'PENDING_SOURCE_BEHAVIOR_DIFF','ACCEPTED':'NOT_ALLOWED'},'status':'VALIDATOR_PASS_BOUNDED' if not failures else 'VALIDATOR_FAIL','acceptance_eligible':False,'failures':failures}; OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n'); print(json.dumps({'status':payload['status'],'covered':len(m.COVERED_MODULES),'failures':failures})); return 0 if not failures else 1
if __name__=='__main__': raise SystemExit(main())
