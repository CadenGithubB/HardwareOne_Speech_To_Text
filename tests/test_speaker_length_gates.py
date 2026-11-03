"""Separate admission from adaptation; guard both edges of each sample threshold."""
import math,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import spkrules

def phrase(deg,n):
 return {'samples':n,'e':[math.cos(math.radians(deg)),math.sin(math.radians(deg))]}
with tempfile.TemporaryDirectory() as tmp:
 runner=spkrules.Runner(Path(tmp))
 def run(spec,p):return runner.runs(p,[(spkrules.parse_rule(spec,.6),list(range(len(p))))],32000)[0]
 for n in [23999,24000,31999,32000]:
  r=run('short:create_ms=1500',[phrase(0,n)])
  assert (r[0][0]>=0)==(n>=24000)
 # A 1.5s phrase matches but cannot adapt the original profile: 70deg stays new.
 p=[phrase(0,48000),phrase(40,24000),phrase(70,48000)]
 assert run('short:create_ms=1500',p)==[(0,'new'),(0,'short_match'),(1,'new')]
 # Raising adaptation to 3s leaves 2s profile creation intact, and prevents drift.
 p=[phrase(0,32000),phrase(40,47999),phrase(70,48000)]
 assert run('update:update_ms=3000',p)==[(0,'new'),(0,'short_match'),(1,'new')]
 p[1]=phrase(40,48000)
 assert run('update:update_ms=3000',p)[1]==(0,'match')
 assert run('neutral:create_ms=0,update_ms=0',p)==run('production',p)
print('speaker length gate checks passed')
