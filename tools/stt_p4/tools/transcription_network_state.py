import os
import contextlib,datetime,json,pathlib,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_connectivity','p4_mesh')]
from connectivity_redaction import ConnectivityConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import private_encodings,HttpS3Probe
c=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S');result={}
with contextlib.ExitStack() as stack:
 for board,port in {'p4':os.environ['HW1_P4_PORT'],'s3':os.environ['HW1_S3_PORT']}.items():
  b=stack.enter_context(ConnectivityConsole(port,ROOT/('experiments/stt_p4/private/ui-network-'+board+'-'+tag+'.log'),secrets=private_encodings(c),completion='hardwareone',chunk_delay=.12))
  time.sleep(1);b.command('login '+command_token(c['username'])+' '+command_token(c['password']),timeout=30)
  assert f'You are {c["username"]} (admin)' in b.command('whoami')
  state={}
  for cmd in ('wifistatus json','httpstatus json'):
   objects=extract_json_objects(b.command(cmd,timeout=30));assert len(objects)==1,'Missing status JSON';state[cmd]=objects[0]
  if board=='s3':state['probe']=HttpS3Probe(b,c).rpc('status')
  result[board]=state
  public={key:{k:v for k,v in val.items() if k in ('connected','running','enabled','mode','ip','apIp','port','channel','state','bridge')} for key,val in state.items()}
  public['keys']={k:list(v) for k,v in state.items()}
  print(json.dumps({'board':board,'state':public}),flush=True)
p=ROOT/('experiments/stt_p4/private/ui-network-'+tag+'.json');p.write_text(json.dumps(result,indent=2)+'\n');p.chmod(0o600)
print(json.dumps({'record':str(p)}),flush=True)
