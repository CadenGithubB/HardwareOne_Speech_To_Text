import os
import contextlib,json,pathlib,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'experiments'/x) for x in ('p4_connectivity','p4_mesh')]
from connectivity_redaction import ConnectivityConsole
from console import extract_json_objects
from test_mesh import command_token
from test_http_s3 import private_encodings,HttpS3Probe
c=json.loads(pathlib.Path(__import__('os').environ.get('HW1_CREDENTIALS', 'experiments/p4_ble_roles/private/credentials.json')).read_text())
with contextlib.ExitStack() as stack:
 for board,port in {'p4':os.environ['HW1_P4_PORT'],'s3':os.environ['HW1_S3_PORT']}.items():
  b=stack.enter_context(ConnectivityConsole(port,ROOT/('experiments/stt_p4/private/ui-preflight-'+board+'.log'),secrets=private_encodings(c),completion='hardwareone',chunk_delay=.12))
  time.sleep(2);b.command('login '+command_token(c['username'])+' '+command_token(c['password']),timeout=30)
  assert f'You are {c["username"]} (admin)' in b.command('whoami')
  b.command('loglink off')
  objects=extract_json_objects(b.command('espnowstatus json',timeout=30));assert len(objects)==1
  radio=objects[0]
  if board=='p4':assert radio['mac']==__import__('os').environ.get('HW1_P4_MAC', '02:48:57:31:01:A8').upper()
  result={'board':board,'authenticated':True,'channel':radio.get('channel')}
  if board=='s3':result['http_fixture']=HttpS3Probe(b,c).rpc('status').get('bridge')=='s3-http-v1'
  print(json.dumps(result),flush=True)
