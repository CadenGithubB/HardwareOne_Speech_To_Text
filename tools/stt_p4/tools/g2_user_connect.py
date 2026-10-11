import os
import datetime,json,pathlib,re,serial,sys,termios,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_ble_roles','p4_connectivity','p4_mesh')]
from board_control import RolesConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import private_encodings
class NoControlSerial(serial.Serial):
 def _update_dtr_state(self):pass
 def _update_rts_state(self):pass
 def open(self):
  super().open();s=termios.tcgetattr(self.fd);s[2]&=~termios.HUPCL;termios.tcsetattr(self.fd,termios.TCSANOW,s)
c=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
log=pathlib.Path(__file__).resolve().parent/('g2-user-connect-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.log')
with RolesConsole(os.environ['HW1_P4_PORT'],log,secrets=private_encodings(c),completion='hardwareone',chunk_delay=.12,serial_factory=NoControlSerial) as b:
 time.sleep(1)
 b.command('login '+command_token(c['username'])+' '+command_token(c['password']),timeout=30)
 assert f'You are {c["username"]} (admin)' in b.command('whoami')
 identities=extract_json_objects(b.command('espnowstatus json',timeout=30))
 assert any(x.get('mac')==__import__('os').environ.get('HW1_P4_MAC', '02:48:57:31:01:A8').upper() for x in identities),'Unexpected board identity'
 print(json.dumps({'ready':True,'board':'p4','usbResetObserved':bool(re.search('USB_UART_CHIP_RESET',b.read_since(0)))}),flush=True)
 for line in sys.stdin:
  try:
   job=json.loads(line)
   if job.get('exit'):break
   cmd=job['command'];out=b.command(cmd,timeout=job.get('timeout',30))
   print(json.dumps({'command':cmd,'response':b.redact(out)}),flush=True)
  except Exception as ex:
   print(json.dumps({'error':type(ex).__name__,'detail':str(ex)}),flush=True)
 print(json.dumps({'closed':True}),flush=True)
