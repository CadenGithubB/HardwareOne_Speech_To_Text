"""Existing S3 USB HTTP bridge exercises P4 UI adapter; no firmware changes."""
import os
import base64,contextlib,datetime,hashlib,json,pathlib,re,subprocess,sys,time,urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_connectivity','p4_mesh')]
from connectivity_redaction import ConnectivityConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import HttpS3Probe,validate_reply,private_encodings
from esptool.reset import HardReset
RUN=pathlib.Path(__file__).resolve().parent
c=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S');record=RUN/('transcription-ui-'+tag+'.json')
report={'checks':{},'http':[]}
def emit(key,value=True):
 report['checks'][key]=value;record.write_text(json.dumps(report,indent=2)+'\n');record.chmod(0o600)
 print(json.dumps({key:value}),flush=True)
def play():
 fixture=next((RUN/'heldout-tts-v1').glob('heldout-0-*.wav'))
 state=subprocess.check_output(['/usr/bin/osascript','-e','get volume settings'],text=True)
 old=(int(re.search(r'output volume:(\d+)',state).group(1)),re.search(r'output muted:(true|false)',state).group(1))
 try:
  subprocess.run(['/usr/bin/osascript','-e','set volume output volume 40 output muted false'],check=True,capture_output=True)
  subprocess.run(['/usr/bin/afplay',str(fixture)],check=True)
 finally:subprocess.run(['/usr/bin/osascript','-e',f'set volume output volume {old[0]} output muted {old[1]}'],check=True,capture_output=True)
with contextlib.ExitStack() as stack:
 boards={k:stack.enter_context(ConnectivityConsole(p,RUN/('transcription-ui-'+k+'-'+tag+'.log'),secrets=private_encodings(c),completion='hardwareone',chunk_delay=.12)) for k,p in {'p4':os.environ['HW1_P4_PORT'],'s3':os.environ['HW1_S3_PORT']}.items()}
 time.sleep(3)
 p4,s3=boards['p4'],boards['s3']
 def cmd(b,text):return b.command(text,timeout=45)
 def obj(b,text):
  for _ in range(3):
   values=extract_json_objects(cmd(b,text))
   if len(values)==1:return values[0]
  raise AssertionError('Missing JSON: '+text.split()[0])
 def login(b):
  cmd(b,'login '+command_token(c['username'])+' '+command_token(c['password']))
  assert f'You are {c["username"]} (admin)' in cmd(b,'whoami'),'Named login failed'
  cmd(b,'loglink off')
 for b in boards.values():login(b)
 assert obj(p4,'espnowstatus json')['mac']==__import__('os').environ.get('HW1_P4_MAC', '02:48:57:31:01:A8').upper(),'Wrong P4 radio identity'
 probe=HttpS3Probe(s3,c)
 assert probe.rpc('status')['bridge']=='s3-http-v1','Wrong S3 HTTP fixture'
 def req(path,fields=None):
  method='POST' if fields is not None else 'GET'
  arguments='request '+method+' '+path
  if fields is not None:arguments+=' '+base64.b64encode(urllib.parse.urlencode(fields).encode()).decode()
  value=validate_reply(probe.rpc(arguments));report['http'].append({'method':method,'path':path.split('?')[0],**value.metadata})
  return value
 def api(path='/api/transcription',fields=None,status=200):
  value=req(path,fields);assert value.status==status,'Unexpected HTTP status for '+path.split('?')[0]+': '+str(value.status)
  parsed=json.loads(value.text());assert isinstance(parsed,dict),'Expected JSON object'
  return parsed
 session=None;joined=False
 try:
  old_save='= true' in cmd(p4,'sttsavetranscripts')
  assert not obj(p4,'srstatus')['running'],'ESP-SR busy'
  ap=obj(p4,'probeap '+command_token(c.get('ap_ssid','HW1_P4_TEST'))+' '+command_token(c['ap_password']))
  assert ap['channel']==6 and ap['http'],'Test AP failed'
  probe.join();joined=True;probe.rpc('clear')
  assert req('/api/transcription').status in (401,403),'API accessible without login'
  login_http=req('/login',{k:c[k] for k in ('username','password')})
  assert login_http.status==303 and login_http.metadata['cookiePresent'],'HTTP login failed'
  emit('named_cookie_and_private_api')
  page=req('/sensors');assert page.status==200 and page.metadata['htmlOpen'] and page.metadata['htmlClose'],'Incomplete Sensors page'
  emit('sensors_page',{'bytes':page.metadata['bytes'],'sha256':page.metadata['sha256']})
  caps=api();assert caps['available'] and caps['continuous'],'Local provider unavailable'
  emit('local_continuous_provider')
  for tier in ('internal','sd'):
   files=obj(p4,'transcripts list '+tier+' 0')
   if tier=='internal':assert files['success'],'Internal transcript listing failed'
  # Persistent preference is restored in finally; only accepted text is saved.
  assert req('/api/cli',{'cmd':'sttsavetranscripts 1','capture':'1'}).status==200
  session=api(fields={'action':'start'})['id'];assert re.fullmatch('[0-9a-f]{16}',session),'Invalid App lease'
  recovered=api();assert recovered['id']==session,'Lost-reply lease recovery failed'
  emit('same_cookie_lease_recovery')
  deadline=time.monotonic()+65;pieces=[];receipts=set();ack_retry=False;played=False;stopped=False
  while time.monotonic()<deadline:
   state=api('/api/transcription?id='+session)
   if state.get('captureActive') and not played:play();played=True
   if state.get('textPending'):
    r=state['receipt'];key=(r['sequence'],r['offset'],r['length']);assert key not in receipts,'Duplicate accepted receipt'
    receipts.add(key);pieces.append(state['sttText'])
    form={'id':session,**r};api('/api/transcription/ack',form)
    if not ack_retry:api('/api/transcription/ack',form);ack_retry=True
   if len(receipts)>=2 and not stopped:
    api(fields={'action':'stop','id':session});stopped=True
   if stopped and not state['active'] and not state.get('textPending'):break
   time.sleep(.35)
  if not stopped:
   api(fields={'action':'stop','id':session});stopped=True
   for _ in range(60):
    state=api('/api/transcription?id='+session)
    if state.get('textPending'):
     r=state['receipt'];key=(r['sequence'],r['offset'],r['length']);assert key not in receipts
     receipts.add(key);pieces.append(state['sttText']);api('/api/transcription/ack',{'id':session,**r})
    if not state['active'] and not state.get('textPending'):break
    time.sleep(.4)
  assert not state['active'],'App did not drain on stop'
  assert pieces and ack_retry,'No recognized text received'
  assert state['transcriptEnabled'] and state['transcriptSaved'] and state['transcriptComplete'] and not state['transcriptError'],'Transcript not finalized'
  path=state['transcriptPath'];assert path.startswith('/stt/u'),'Unexpected saved location'
  emit('start_live_ack_retry_stop',{'pieces':len(pieces),'characters':sum(map(len,pieces)),'completed':True})
  saved=req('/api/files/read?'+urllib.parse.urlencode({'name':path}))
  assert saved.status==200 and saved.body and b'[End: done]' in saved.body,'Saved HTTP transcript unavailable'
  emit('saved_http_read',{'bytes':len(saved.body),'sha256':hashlib.sha256(saved.body).hexdigest()})
  listed=obj(p4,'transcripts list internal 0');assert listed['success']
  window=obj(p4,'transcripts read '+command_token(path)+' 0');assert window['success'] and window['sttText'],'OLED/G2 file adapter failed'
  emit('shared_file_adapter',{'windowBytes':len(window['sttText'].encode()),'eof':window['eof']})
  old_session=session;session=api(fields={'action':'start'})['id'];assert session!=old_session
  api(fields={'action':'cancel','id':old_session},status=409)
  assert api('/api/transcription?id='+session)['active'],'Old lease cancelled replacement'
  api(fields={'action':'cancel','id':session});emit('stale_lease_cannot_cancel_replacement')
  req('/logout');assert req('/api/transcription').status in (401,403);emit('logout_revokes_api')
  session=None
 finally:
  if joined:
   with contextlib.suppress(Exception):
    if session:api(fields={'action':'cancel','id':session})
    req('/logout')
   with contextlib.suppress(Exception):probe.rpc('clear')
  with contextlib.suppress(Exception):cmd(p4,'sttsavetranscripts '+('1' if old_save else '0'))
  for name,b in boards.items():
   mark=b.marker();HardReset(b._port,uses_usb=True)();b.read_until(r'\[Boot\] Setup complete',since=mark,timeout=60);login(b)
   assert not re.search(r'Guru Meditation|panic\(|abort\(|Brownout',b.read_since(mark)),'Fatal boot after cleanup'
  emit('boards_rebooted_runtime_test_network_cleared')
 print(json.dumps({'record':str(record)}),flush=True)
