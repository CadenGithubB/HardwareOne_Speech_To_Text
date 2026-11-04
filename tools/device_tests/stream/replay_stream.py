#!/usr/bin/env python3
"""Deterministic actual scheduler/frontend traces; no neural inference or device claim."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--component',type=Path,default=ROOT/'firmware/components/hw1_stt')
p.add_argument('--out',type=Path,required=True)
p.add_argument('--metrics',action='store_true')
a=p.parse_args()
if 'private' not in a.out.resolve().parts:p.error('traces must stay in ignored private storage')
a.out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='stt-trace-') as folder:
 exe=Path(folder)/'trace'
 command=['clang++','-std=c++17','-O2','-pthread','-ffp-contract=off','-Wall','-Wextra','-Werror','-Wno-unused-private-field','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 if a.metrics:command+=['-DHW1_STT_STREAM_METRICS=1']
 command+=['-I'+str(a.component),str(ROOT/'tests/stream_trace.cpp'),str(a.component/'stt/stt_stream.cpp'),str(a.component/'stt/quartznet_frontend.cpp'),'-o',str(exe)]
 subprocess.run(command,check=True)
 report={'scope':'Deterministic scheduler/frontend only; synthetic PCM, no acoustic model/LM inference','component':str(a.component.resolve()),'metrics':a.metrics,'traces':[]}
 for pacing in ['legacy','x2f']:
  for scenario in range(6):
   payload=a.out/f'{pacing}-{scenario}.bin'
   output=subprocess.check_output([str(exe),pacing,str(scenario),str(payload.resolve())],text=True,timeout=60)
   rows=[json.loads(line) for line in output.splitlines()];assert rows[-1]['type']=='summary'
   file=a.out/f'{pacing}-{scenario}.jsonl';file.write_text(output)
   report['traces'].append({'pacing':pacing,'scenario':scenario,'sha256':hashlib.sha256(output.encode()).hexdigest(),'payload_sha256':hashlib.sha256(payload.read_bytes()).hexdigest(),'payload_bytes':payload.stat().st_size,'summary':rows[-1]})
 (a.out/'report.json').write_text(json.dumps(report,indent=2))
 print('Passed',len(report['traces']),'deterministic actual scheduler/frontend traces')
