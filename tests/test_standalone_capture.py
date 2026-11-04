"""Actual playback metadata and event parser; no audio output or device access."""
import json,sys,tempfile,wave
import re,itertools
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/stream'))
from standalone_capture import audio_metadata,product_events
import standalone_capture as runner
with tempfile.TemporaryDirectory(prefix='standalone-fixture-') as folder:
 p=Path(folder)/'fixture.wav'
 for rate in [16000,44100,48000]:
  with wave.open(str(p),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(bytes(320))
  meta=audio_metadata(p);assert meta['wav_sample_rate']==rate and meta['duration_s']==160/rate
 for channels,width,frames in [(2,2,160),(1,1,160),(1,2,0)]:
  with wave.open(str(p),'wb') as out:out.setnchannels(channels);out.setsampwidth(width);out.setframerate(48000);out.writeframes(bytes(frames*channels*width))
  try:audio_metadata(p)
  except ValueError:pass
  else:raise AssertionError('Invalid playback metadata accepted')
row={'schema':1,'type':'final','rawText':'synthetic test'}
assert product_events(['unrelated','123 STT_EVENT '+json.dumps(row)])==[row]
try:product_events(['STT_EVENT '+json.dumps({'schema':2,'type':'final'})])
except AssertionError:pass
else:raise AssertionError('Unknown event schema accepted')
# Execute the probes-off control branch without a serial port or audio device.
# A stray probe must reject the control before playback, and close the Console.
class Console:
 instances=[];stray=False
 def __init__(self,path):
  self.closed=False;self.lines=['Capture feature pool: 1 bytes','Optional background speaker labels ready',
   'STT_EVENT '+json.dumps({'schema':1,'type':'start','sessionId':'test'})]
  if self.stray:self.lines+=['STT_PERF '+json.dumps({'type':'level'})]
  self.instances.append(self)
 def wait(self,*args):return re.search(r'.*','STT_EVENT '+json.dumps({'schema':1,'type':'status','state':'listening'}))
 def command(self,command,*args):
  event={'schema':1,'type':'status','lmStrength':1,'customWords':0}
  if command=='vocab list':event={'schema':1,'type':'vocabulary','words':[]}
  self.lines.append('STT_EVENT '+json.dumps(event))
 def since(self,*args):return self.lines
 def close(self):self.closed=True
class Player:
 returncode=0
 def __init__(self,args):assert args[0]=='afplay'
 def poll(self):return 0
remote=SimpleNamespace(Console=Console,PANIC=re.compile('panic'))
with tempfile.TemporaryDirectory(prefix='standalone-control-') as folder:
 root=Path(folder)/'private';root.mkdir();wav=root/'test.wav'
 with wave.open(str(wav),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(bytes(320))
 for stray in [False,True]:
  Console.stray=stray;ticks=itertools.count(0,30);destination=root/str(stray)
  with patch.object(runner,'audio_setup'),patch.object(runner.subprocess,'Popen',Player),patch.object(runner.time,'monotonic',side_effect=lambda:next(ticks)):
   if stray:
    try:runner.capture(remote,wav,destination,'test',metrics=False)
    except AssertionError:pass
    else:raise AssertionError('Probes-off capture accepted probe events')
   else:
    result=runner.capture(remote,wav,destination,'test',metrics=False)
    assert result['phase']=='complete' and result['final_report'] is None and result['metrics'] is False
    assert not result['telemetry']['events'] and result['lm_strength']==1 and result['custom_words']==0
  assert Console.instances[-1].closed
print('Standalone capture: real WAV validation at 16/44.1/48 kHz, invalid inputs and product event schema passed')
