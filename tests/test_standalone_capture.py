"""Actual playback metadata and event parser; no audio output or device access."""
import json,sys,tempfile,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/stream'))
from standalone_capture import audio_metadata,product_events
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
print('Standalone capture: real WAV validation at 16/44.1/48 kHz, invalid inputs and product event schema passed')
