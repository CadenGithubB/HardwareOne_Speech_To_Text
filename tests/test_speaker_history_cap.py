"""Capped history adapts to changed voice direction; neutral mode stays equivalent."""
import math,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import spkrules
with tempfile.TemporaryDirectory() as tmp:
 r=spkrules.Runner(Path(tmp))
 p=[{'samples':48000,'e':[math.cos(math.radians(a)),math.sin(math.radians(a))]} for a in [0]*12+[40]*8+[78]]
 rules=[spkrules.parse_rule(x,.6) for x in ['production','neutral:history_cap=0','cap:history_cap=8']]
 a,b,c=r.runs(p,[(x,list(range(len(p)))) for x in rules],32000)
 assert a==b
 assert a[-1]==(1,'new')
 assert c[-1]==(0,'match')
 assert c[:8]==a[:8]
print('speaker history cap checks passed')
