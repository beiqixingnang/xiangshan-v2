import ast, hashlib, importlib.util, json, py_compile, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'python/Program-System/System-Build/Build-Cpu'; OUT=ROOT/'validation/v2-build-freeze-shared-audit-results.json'
EXCLUDED={'Build-Cpu.Backend.Datapath.VldMergeUnit-Hardware.py','Build-Cpu.Top.UHSCTop-GenerationProbe-Hardware.py'}
files=sorted(p for p in BUILD.rglob('*.py') if p.name not in EXCLUDED); rows=[]
for p in files:
    src=p.read_bytes(); rec={'path':str(p.relative_to(ROOT)).replace('\\','/'),'gates':{},'errors':[]}
    rec['gates']['utf8_lf']=not src.startswith(b'\xef\xbb\xbf') and b'\r' not in src
    try: ast.parse(src.decode('utf-8')); rec['gates']['ast_parse']=True
    except Exception as e: rec['gates']['ast_parse']=False; rec['errors'].append(f'ast:{e}')
    try: py_compile.compile(str(p),doraise=True); rec['gates']['py_compile']=True
    except Exception as e: rec['gates']['py_compile']=False; rec['errors'].append(f'compile:{e}')
    try:
      spec=importlib.util.spec_from_file_location('audit_'+hashlib.sha1(str(p).encode()).hexdigest(),p); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); rec['gates']['exact_import']=True
      rec['gates']['build_verilog_available']=callable(getattr(m,'build_verilog',None))
      if not rec['gates']['build_verilog_available']: rec['errors'].append('missing build_verilog')
    except Exception as e: rec['gates']['exact_import']=False; rec['gates']['build_verilog_available']=False; rec['errors'].append(f'import:{e}')
    try:
      r=subprocess.run(['pyright.cmd','--outputjson',str(p)],capture_output=True,text=True,timeout=60); j=json.loads(r.stdout or '{}'); rec['gates']['single_file_pyright']=j.get('summary',{}).get('errorCount',1)==0; rec['pyright_errors']=j.get('summary',{}).get('errorCount')
    except Exception as e: rec['gates']['single_file_pyright']=False; rec['errors'].append(f'pyright:{e}')
    rec['pass']=all(rec['gates'].values()); rows.append(rec)
summary={k:sum(1 for r in rows if r['gates'].get(k)) for k in ['utf8_lf','ast_parse','py_compile','exact_import','build_verilog_available','single_file_pyright']}
out={'schema_version':1,'kind':'XIANGSHAN_V2_BUILD_FREEZE_SHARED_AUDIT','target_count':len(rows),'excluded_nonclosure':sorted(EXCLUDED),'gates':summary,'pass_count':sum(r['pass'] for r in rows),'fail_count':sum(not r['pass'] for r in rows),'verilator':'NOT_RUN','yosys':'NOT_RUN','results':rows}
OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n'); print(json.dumps({k:out[k] for k in ['target_count','pass_count','fail_count','gates','verilator','yosys']},ensure_ascii=False))
