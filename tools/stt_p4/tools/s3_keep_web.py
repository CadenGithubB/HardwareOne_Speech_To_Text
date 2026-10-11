import os
import datetime,json,pathlib,re,serial,sys,termios,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_connectivity','p4_mesh')]
from connectivity_redaction import ConnectivityConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import private_encodings,HttpS3Probe
class NoControlSerial(serial.Serial):
 def _update_dtr_state(self):pass
 def _update_rts_state(self):pass
 def open(self):
  super().open();settings=termios.tcgetattr(self.fd);settings[2]&=~termios.HUPCL;termios.tcsetattr(self.fd,termios.TCSANOW,settings)
c=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')
with ConnectivityConsole(os.environ['HW1_S3_PORT'],ROOT/('experiments/stt_p4/private/s3-keep-web-'+tag+'.log'),secrets=private_encodings(c),completion='hardwareone',chunk_delay=.12,serial_factory=NoControlSerial) as b:
 time.sleep(2)
 b.command('login '+command_token(c['username'])+' '+command_token(c['password']),timeout=30)
 assert f'You are {c["username"]} (admin)' in b.command('whoami')
 def cmd(text):return b.command(text,timeout=45)
 def obj(text):
  vals=extract_json_objects(cmd(text));assert len(vals)==1,'Missing JSON for '+text.split()[0];return vals[0]
 def state():
  w=obj('wifistatus json');h=obj('httpstatus json');p=HttpS3Probe(b,c).rpc('status')
  out={'wifi':{k:v for k,v in w.items() if k in ('connected','ip','radioOn','radioHeldForEspnow')},'savedNetwork':bool(w.get('savedSsid')),'savedNetworkIsPriorFixture':w.get('savedSsid')==c.get('ap_ssid','HW1_P4_TEST'),'http':h,'probe':{k:v for k,v in p.items() if k in ('connected','ip','apIp','channel','bridge')},'usbResetObserved':bool(re.search(r'rst:|\[Boot\] Setup complete',b.read_since(0)))}
  print(json.dumps(out),flush=True)
 state()
 if '--verify-self' in sys.argv:
  page=HttpS3Probe(b,c).request('/login')
  assert page.status==200 and page.metadata.get('hasUsername') and page.metadata.get('hasPassword'),'S3 local login page unavailable'
  print(json.dumps({'s3LocalLoginHttp':page.status,'bytes':page.metadata['bytes'],'sha256':page.metadata['sha256']}),flush=True)
 if '--restore' in sys.argv:
  mark=b.send_line('openwifi')
  b.read_until(r'\[CMD\][^\r\n]*openwifi -> (?:OK|FAIL)',since=mark,timeout=65)
  connected=False
  for _ in range(12):
   time.sleep(3);w=obj('wifistatus json')
   if w.get('connected'):connected=True;break
  if connected:cmd('openhttp')
  state()
  print(json.dumps({'restoredSavedConnection':connected}),flush=True)
 print(json.dumps({'ready':True}),flush=True)
 for line in sys.stdin:
  v=json.loads(line)
  if v['op']=='state':state()
  elif v['op']=='command':
   assert v['text'] in ('openwifi','openhttp','httpenabled','wifiautoconnect','wifistatus json','httpstatus json')
   out=cmd(v['text'])
   for secret in private_encodings(c):out=out.replace(secret,'<redacted>')
   print(json.dumps({'command':v['text'],'reply':out}),flush=True)
  elif v['op']=='exit':break
  else:raise ValueError('Unknown action')
