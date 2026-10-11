import os
import datetime,hashlib,json,pathlib,re,serial,sys,termios,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_connectivity','p4_mesh')]
from connectivity_redaction import ConnectivityConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import private_encodings
class NoControlSerial(serial.Serial):
 def _update_dtr_state(self):pass
 def _update_rts_state(self):pass
 def open(self):
  super().open();settings=termios.tcgetattr(self.fd);settings[2]&=~termios.HUPCL;termios.tcsetattr(self.fd,termios.TCSANOW,settings)
RUN=pathlib.Path(__file__).resolve().parent
c=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S');result={}
with ConnectivityConsole(os.environ['HW1_P4_PORT'],RUN/('transcription-usb-'+tag+'.log'),secrets=private_encodings(c),completion='hardwareone',chunk_delay=.12,serial_factory=NoControlSerial) as b:
 time.sleep(2)
 b.command('login '+command_token(c['username'])+' '+command_token(c['password']),timeout=30)
 assert f'You are {c["username"]} (admin)' in b.command('whoami')
 b.command('loglink off')
 def obj(cmd):
  for _ in range(3):
   values=extract_json_objects(b.command(cmd,timeout=30))
   if len(values)==1:return values[0]
  raise AssertionError('Missing JSON for '+cmd.split()[0])
 assert obj('espnowstatus json')['mac']==__import__('os').environ.get('HW1_P4_MAC', '02:48:57:31:01:A8').upper(),'Wrong P4 radio'
 caps=obj('transcription status')
 for _ in range(20):
  if caps.get('available'):break
  time.sleep(1);caps=obj('transcription status')
 assert caps['success'] and caps['available'] and caps['continuous'],'App capability missing'
 result['app_commands_available']=True
 listing=obj('transcripts list internal 0');assert listing['success'],'Listing failed'
 result['saved_files_on_first_page']=len(listing['entries']);result['more_files']=listing['more']
 assert not obj('transcripts read "/stt/u4294967295/nonexistent.txt" 0')['success'],'Other-account path accepted'
 result['other_account_path_denied']=True
 if listing['entries']:
  path=listing['entries'][0]['path'];offset=0;content=bytearray();windows=0;eof=False
  while windows<64:
   part=obj('transcripts read '+command_token(path)+' '+str(offset))
   assert part['success'] and part['offset']==offset,'File window failed'
   data=part['sttText'].encode();assert len(data)<=512 and part['nextOffset']==offset+len(data),'Invalid bounded offset'
   content.extend(data);windows+=1;eof=part['eof']
   if eof:break
   assert data,'Nonadvancing window';offset=part['nextOffset']
  result['saved_file_windows']={'windows':windows,'bytes':len(content),'eof':eof,'sha256':hashlib.sha256(content).hexdigest()}
 sd=obj('transcripts list sd 0');assert not sd['success'],'Expected unavailable SD'
 result['sd_unavailable_reported']=True
 assert not re.search(r'Guru Meditation|panic\(|abort\(|Brownout',b.read_since(0)),'Fatal board log'
 result['fatal_log']=False
out=RUN/('transcription-usb-'+tag+'.json');out.write_text(json.dumps(result,indent=2)+'\n');out.chmod(0o600)
print(json.dumps({'checks':result,'record':str(out)}),flush=True)
