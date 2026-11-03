"""Capacity knob exercises a real ninth/tenth identity, neutral stays production."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import spkrules
with tempfile.TemporaryDirectory() as tmp:
 runner=spkrules.Runner(Path(tmp))
 phrases=[{'samples':48000,'e':[float(j==i) for j in range(11)]} for i in range(11)]
 specs=['production','neutral:capacity=0','ten:capacity=10']
 rules=[spkrules.parse_rule(s,.6) for s in specs]
 a,b,c=runner.runs(phrases,[(r,list(range(11))) for r in rules],32000)
 assert a==b
 assert a[8:]==[(-1,'capacity')]*3
 assert c[8:]==[(8,'new'),(9,'new'),(-1,'capacity')]
print('speaker capacity checks passed')
