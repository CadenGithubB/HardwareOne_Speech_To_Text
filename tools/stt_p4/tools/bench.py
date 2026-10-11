import os
import contextlib,datetime,json,pathlib,re,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_ble_roles','p4_connectivity','p4_mesh')]
from board_control import RolesConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import private_encodings
RUN=pathlib.Path(__file__).resolve().parent
c=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S');record=RUN/('acoustic-'+tag+'.json');results=[]
def emit(v):
 results.append(v);record.write_text(json.dumps(results,indent=2)+'\n');record.chmod(0o600)
 shown=dict(v)
 if 'sttText' in shown:shown['sttText']='<private; '+str(len(shown['sttText']))+' characters>'
 if 'reply' in shown and len(shown['reply'])>1800:shown['reply']=shown['reply'][-1800:]
 print(json.dumps(shown),flush=True)
with RolesConsole(os.environ['HW1_P4_PORT'],RUN/('acoustic-'+tag+'.log'),secrets=private_encodings(c),completion='hardwareone',chunk_delay=.08) as b:
 time.sleep(3)
 def clean(text):
  for val in private_encodings(c):text=text.replace(val,'<redacted>')
  return text
 def cmd(text):
  reply=b.command(text,timeout=50)
  assert not re.search(r'Guru Meditation|panic\(|abort\(|Brownout',b.read_since(0)),'fatal board log'
  return clean(reply)
 def obj(text):
  values=extract_json_objects(cmd(text));assert len(values)==1,(text,values);return values[0]
 def login():
  cmd('login '+command_token(c['username'])+' '+command_token(c['password']))
  assert f'You are {c["username"]} (admin)' in b.command('whoami')
  cmd('loglink on')
 def terminal(token,timeout=40):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   x=obj('stt status '+token)
   if not x['workerActive']:return x
   time.sleep(.3)
  raise TimeoutError('STT worker did not finish')
 def play(path,volume):
  state=subprocess.check_output(['/usr/bin/osascript','-e','get volume settings'],text=True)
  old=(int(re.search(r'output volume:(\d+)',state).group(1)),re.search(r'output muted:(true|false)',state).group(1))
  try:
   subprocess.run(['/usr/bin/osascript','-e',f'set volume output volume {volume} output muted false'],check=True,capture_output=True)
   subprocess.run(['/usr/bin/afplay',str(path)],check=True)
  finally:subprocess.run(['/usr/bin/osascript','-e',f'set volume output volume {old[0]} output muted {old[1]}'],check=True,capture_output=True)
 login();assert obj('espnowstatus json')['mac']==__import__('os').environ.get('HW1_P4_MAC', '02:48:57:31:01:A8').upper()
 emit({'ready':True,'record':str(record)})
 for line in sys.stdin:
  try:
   v=json.loads(line);op=v['op']
   if op=='command':emit({'command':v['text'],'reply':cmd(v['text'])})
   elif op=='acoustic':
    i=v.get('fixture',0);assert i in range(4)
    path=next((RUN/'heldout-tts-v1').glob('heldout-'+str(i)+'-*.wav'))
    seconds=v.get('seconds',8);volume=v.get('volume',40);assert 1<=seconds<=20 and 1<=volume<=50
    token=obj('stt record '+str(seconds))['id']
    end=time.monotonic()+4
    while time.monotonic()<end:
     x=obj('stt status '+token)
     if x['state']=='recording':break
     time.sleep(.1)
    assert x['state']=='recording',x
    play(path,volume)
    if v.get('stop_after_play'):cmd('stt stop '+token)
    state=terminal(token,timeout=50);emit({'acoustic_fixture':path.name,'volume':volume,'status':state})
    if state['state']=='done':
     result=obj('stt result '+token);emit({'id':token,'sttText':result['sttText']})
   elif op=='cancel':
    token=obj('stt record 10')['id'];time.sleep(.5);cmd('stt cancel '+token);emit({'cancel':terminal(token)})
   elif op=='cancel_inference':
    token=obj('stt record 4')['id'];end=time.monotonic()+30
    while time.monotonic()<end:
     state=obj('stt status '+token)
     if state['workerActive'] and state['phase']=='inference':break
     if not state['workerActive']:raise AssertionError(state)
     time.sleep(.1)
    assert state['workerActive'] and state['phase']=='inference',state
    cmd('stt cancel '+token);final=terminal(token);assert final['state']=='cancelled',final
    emit({'cancel_during_inference':final})
   elif op=='maximum':
    token=obj('stt record 20')['id'];state=terminal(token,timeout=65);assert state['samples']==320000 and state['state']=='done',state;emit({'maximum_capture':state})
   elif op=='silence':
    token=obj('stt record 2')['id'];state=terminal(token);emit({'silence':state})
    if state['state']=='done':emit({'id':token,'sttText':obj('stt result '+token)['sttText']})
   elif op=='snapshot':
    emit({'snapshot':v.get('name',''),'stt':obj('stt status'),'mic':obj('micread json'),'heap':obj('memreport json'),'sr':{k:val for k,val in obj('srstatus').items() if k!='voiceArmedUser'}})
   elif op=='logout_cancel':
    token=obj('stt record 10')['id'];time.sleep(.5)
    mark=b.send_line('logout');b.read_until(r'Logged out\.',since=mark,timeout=5);time.sleep(1)
    mark=b.send_line('stt result '+token);b.read_until(r'Authentication required',since=mark,timeout=5)
    login();stale=cmd('stt result '+token);emit({'logout_denied':True,'stale_epoch_denied':stale})
   elif op=='exit':break
   else:raise ValueError(op)
  except Exception as error:
   emit({'error':type(error).__name__,'detail':clean(str(error))});raise
 cmd('loglink off')
