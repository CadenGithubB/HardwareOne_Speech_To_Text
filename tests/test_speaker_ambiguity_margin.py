"""A margin may label an ambiguous phrase without adapting either centroid."""
import math,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import spkrules
with tempfile.TemporaryDirectory() as tmp:
 runner=spkrules.Runner(Path(tmp))
 phrases=[{'samples':48000,'e':[math.cos(math.radians(a)),math.sin(math.radians(a))]} for a in [0,80,30,40]]
 rules=[spkrules.parse_rule(x,.6) for x in ['production','margin:ambiguity_margin=0.08','disabled:ambiguity_margin=0']]
 baseline,margin,disabled=runner.runs(phrases,[(r,list(range(4))) for r in rules],32000)
 assert baseline==disabled
 assert baseline[2]==(-1,'ambiguous')
 assert margin[2]==(0,'ambiguous_margin')
 assert margin[3]==(-1,'ambiguous'), 'ambiguous winner must not move centroid'
print('ambiguity margin checks passed')
