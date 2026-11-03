"""Revisions are causal, bounded, and do not feed back into centroids."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
import spkrules
with tempfile.TemporaryDirectory() as tmp:
 runner=spkrules.Runner(Path(tmp))
 def run(p,spec):
  return runner.runs(p,[(spkrules.parse_rule(spec,.6),list(range(len(p))))],32000)[0]
 def phrase(e,n=48000):return {'samples':n,'e':e}
 p=[phrase([1,0],16000),phrase([1,0])]
 baseline=run(p,'production')
 assert baseline==[(-1,'no_match_short'),(0,'new')]
 assert run(p,'defer:defer_steps=3')==[(0,'resolved_after_1'),(0,'new')]
 assert run(p,'disabled:defer_steps=0')==baseline
 # No supporting future phrase -> unknown remains.
 assert run(p[:1],'defer:defer_steps=3')==baseline[:1]
 # Resolve at step three, but never step four.
 filler=phrase([0,1],16000)
 p=[p[0],filler,filler,phrase([1,0])]
 assert run(p,'defer:defer_steps=3')[0]==(0,'resolved_after_3')
 p.insert(1,filler)
 assert run(p,'defer:defer_steps=3')[0]==(-1,'no_match_short')
 # Existing forward decisions are identical: revisions never adapt centroids.
 p=[phrase([1,0]),phrase([0,1]),phrase([.7,.7],16000),phrase([1,0]),phrase([0,1])]
 assert run(p,'defer:defer_steps=3')==run(p,'production')
print('deferred speaker revision checks passed')
