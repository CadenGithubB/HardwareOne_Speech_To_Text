"""Only adaptation is gated: retain the current label, protect future centroids."""
from pathlib import Path
import tempfile,sys,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import spkrules
with tempfile.TemporaryDirectory() as tmp:
 runner=spkrules.Runner(Path(tmp))
 p=[{'samples':48000,'e':[math.cos(math.radians(d)),math.sin(math.radians(d))]} for d in [0,106,51,65]]
 rules=[spkrules.parse_rule(s,.6) for s in ['production','neutral:update_margin=0','margin:update_margin=0.08']]
 a,b,c=runner.runs(p,[(r,list(range(4))) for r in rules],32000)
 assert a==b
 assert a[:3]==[(0,'new'),(1,'new'),(0,'match')]
 assert c[:3]==[(0,'new'),(1,'new'),(0,'match_no_update')]
 assert a[3]==(-1,'ambiguous') and c[3]==(1,'match')
 # No competitor -> gate does not prevent learning a sole speaker.
 p=[{'samples':48000,'e':[1.,0.]}]*3
 assert runner.runs(p,[(rules[2],[0,1,2])],32000)[0]==[(0,'new'),(0,'match'),(0,'match')]
print('speaker update margin checks passed')
