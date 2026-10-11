"""Private physical qualification; inference is on P4, Mac plays test sound only."""
import os
import contextlib,datetime,json,pathlib,re,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_ble_roles','p4_connectivity','p4_mesh')]
from board_control import RolesConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import private_encodings
RUN=pathlib.Path(__file__).resolve().parent
creds=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
record=RUN/('continuous-'+tag+'.json');records=[]
def emit(value):
 records.append(value);record.write_text(json.dumps(records,indent=2)+'\n');record.chmod(0o600)
 shown=dict(value)
 if 'sttText' in shown:shown['sttText']='<private; '+str(len(shown['sttText']))+' characters>'
 if 'reply' in shown:shown['reply']=shown['reply'][-1600:]
 print(json.dumps(shown),flush=True)
def clean(text):
 for secret in private_encodings(creds):text=text.replace(secret,'<redacted>')
 return text
@contextlib.contextmanager
def playback_volume(volume):
 state=subprocess.check_output(['/usr/bin/osascript','-e','get volume settings'],text=True)
 old=(int(re.search(r'output volume:(\d+)',state).group(1)),re.search(r'output muted:(true|false)',state).group(1))
 try:
  subprocess.run(['/usr/bin/osascript','-e',f'set volume output volume {volume} output muted false'],check=True,capture_output=True)
  yield
 finally:subprocess.run(['/usr/bin/osascript','-e',f'set volume output volume {old[0]} output muted {old[1]}'],check=True,capture_output=True)
with RolesConsole(os.environ['HW1_P4_PORT'],RUN/('continuous-'+tag+'.log'),secrets=private_encodings(creds),completion='hardwareone',chunk_delay=.12) as board:
 time.sleep(3)
 fatal_marker=board.marker();fatal_tail=""
 def cmd(text):
  global fatal_marker,fatal_tail
  value=board.command(text,timeout=45)
  mark=board.marker();fresh=fatal_tail+board.read_since(fatal_marker);fatal_marker=mark
  assert not re.search(r'Guru Meditation|panic\(|abort\(|Brownout',fresh),'fatal board log'
  fatal_tail=fresh[-128:]
  return clean(value)
 def obj(text):
  retryable=text.startswith(('stt status ', 'stt next ')) or text in ('memreport json','espnowstatus json')
  for attempt in range(3 if retryable else 1):
   values=extract_json_objects(cmd(text))
   if len(values)==1:return values[0]
   emit({'read_retry':text.split()[0:2],'attempt':attempt+1,'reason':'interleaved or incomplete JSON reply'})
   time.sleep(.5)
  raise AssertionError((text,values))
 def login():
  cmd('login '+command_token(creds['username'])+' '+command_token(creds['password']))
  assert f'You are {creds["username"]} (admin)' in board.command('whoami')
  cmd('loglink off')
 def chunk(token,last,verify=True):
  value=obj('stt next '+token)
  if not value.get('available'):return last
  assert value['sequence']==last+1,value
  if verify:
   retried=obj('stt next '+token)
   keys=('id','available','sequence','startSample','endSample','forcedBoundary','sttText')
   assert all(retried.get(k)==value.get(k) for k in keys),'Retry changed an unacknowledged chunk'
  snap=obj('stt status '+token)
  value['received_at_seconds']=time.monotonic()-started
  if snap['segmentsCompleted']==value['sequence']:
   value['engineStats']={k:snap[k] for k in ('weightsReused','loadMs','frontendMs','inferenceMs','decodeMs','featureFrames','outputFrames','modelBytes') if k in snap}
  received.append(value)
  emit(value)
  assert 'acknowledged' in cmd('stt ack '+token+' '+str(value['sequence']))
  if verify:assert 'acknowledged' in cmd('stt ack '+token+' '+str(value['sequence']))
  return value['sequence']
 def terminal(token,last=0,drain=True,timeout=90):
  until=time.monotonic()+timeout
  while time.monotonic()<until:
   state=obj('stt status '+token)
   if drain:
    while state['pendingTexts']:
     assert time.monotonic()<until,'Text drain exceeded deadline'
     previous=last;last=chunk(token,last,verify=False)
     assert last>previous,'Pending text was not readable'
     state=obj('stt status '+token)
   if not state['workerActive']:return state,last
   time.sleep(.3)
  raise TimeoutError('Continuous worker did not join')
 try:
  login();assert obj('espnowstatus json')['mac']==__import__('os').environ.get('HW1_P4_MAC', '02:48:57:31:01:A8').upper()
  emit({'ready':True,'record':str(record)})
  for line in sys.stdin:
   try:
    request=json.loads(line);op=request['op']
    if op=='exit':break
    if op=='command':emit({'command':request['text'],'reply':cmd(request['text'])});continue
    assert op in ('stream','silence','backpressure','cancel_inference','logout'),op
    seconds=request.get('seconds',120);assert 1<=seconds<=1800
    play=op!='silence' and request.get('play',True)
    volume=request.get('volume',50);assert 1<=volume<=60
    received=[]
    emit({'memory_before':obj('memreport json'),'test':op})
    token=obj('stt start')['id'];last=0;overlap=False;playing=None;next_play=0;fixture=0
    started=time.monotonic();stop_at=started+seconds;next_report=started;next_memory=started+60
    cancelled=False;logged_out=False;states=[]
    next_camera=started+15 if request.get("camera_every") else float("inf")
    try:
     with playback_volume(volume) if play else contextlib.nullcontext():
      while time.monotonic()<stop_at:
       state=obj('stt status '+token);states.append(state)
       if state['captureActive'] and state['inferenceActive']:overlap=True
       now=time.monotonic()
       if now>=next_report:
        emit({'progress':state});next_report=now+10
       if now>=next_memory:
        emit({'memory_during':obj('memreport json')});next_memory=now+60
       if not state['workerActive']:break
       if now>=next_camera:
        reply=cmd('cameracapture');assert 'Captured frame:' in reply,reply
        emit({'camera_capture':reply,'during_inference':state['inferenceActive'],'at_seconds':now-started})
        next_camera=now+request['camera_every']
       if play and state['captureActive'] and state['state']=='recording' and now>=next_play and (not playing or playing.poll() is not None):
        path=next((RUN/'heldout-tts-v1').glob('heldout-'+str(fixture%4)+'-*.wav'))
        playing=subprocess.Popen(['/usr/bin/afplay',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        emit({'play_fixture':path.name,'at_seconds':now-started});fixture+=1;next_play=now+request.get('interval',9)
       if op=='cancel_inference' and state['inferenceActive'] and state['phase']=='inference':
        cmd('stt cancel '+token);cancelled=True;break
       if op=='logout' and state['inferenceActive']:
        mark=board.send_line('logout');board.read_until(r'Logged out\.',since=mark,timeout=5);logged_out=True;time.sleep(3)
        login();reply=cmd('stt next '+token);assert 'no STT run belongs' in reply,reply
        emit({'logout_old_result_denied':True,'reply':reply});logged_out=True;break
       if op!='backpressure' and state['pendingTexts']:
        last=chunk(token,last)
       time.sleep(1.2)
      capture_wall=time.monotonic()-started
      if playing and playing.poll() is None:playing.terminate();playing.wait(timeout=5)
      if op=='logout':assert logged_out,'Inference logout trigger was never reached'
      if not logged_out:
       if not cancelled and state['workerActive']:cmd('stt stop '+token)
       final,last=terminal(token,last,drain=op!='backpressure')
       emit({'final':final,'acknowledged':last,'capture_and_inference_overlapped':overlap,
             'elapsed_wall_seconds':time.monotonic()-started,'capture_wall_seconds':capture_wall,'test':op})
       if op=='cancel_inference':assert cancelled and final['state']=='cancelled',final
       elif op=='backpressure':assert final['state']=='failed' and final['error']=='STT text queue full; receiver must acknowledge results' and final['pendingTexts']==8,final
       else:assert final['state']=='done',final
       assert not final['captureActive'] and not final['inferenceActive']
       if op in ('stream','silence'):
        assert capture_wall>=seconds,'Session ended before the requested duration'
        assert final['pendingTexts']==0 and last==final['segmentsCompleted']==final['segmentsCaptured'],final
        assert final['audioOverruns']==0 and all(x['audioOverruns']==0 for x in states),final
       if op=='silence':assert final['segmentsCaptured']==0,final
       if op=='stream':assert overlap and len([x for x in received if x.get('sttText')])>=2,(overlap,len(received))
      emit({'memory_after':obj('memreport json')})
    finally:
     if playing and playing.poll() is None:playing.terminate();playing.wait(timeout=5)
     if not logged_out:
      cmd('stt cancel '+token)
      terminal(token,drain=False)
     if request.get('camera_every'):emit({'camera_cleanup':cmd('closecamera')})
   except Exception as error:
    emit({'error':type(error).__name__,'detail':clean(str(error))});raise
 finally:
  try:cmd('loglink off')
  except Exception:pass
