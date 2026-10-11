import argparse,hashlib,json,pathlib,re,subprocess,sys
import serial
from esptool.reset import HardReset
p=argparse.ArgumentParser();p.add_argument('model',type=pathlib.Path);p.add_argument('sha');p.add_argument('stem');a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent;baseline=r.parents[1]/'speech_portable/private/run-20260928'
sha=lambda x:hashlib.sha256(x).hexdigest()
meta=json.loads((baseline/'p4-backup.json').read_text());backup=(baseline/'p4-full-flash.bin').read_bytes()
assert meta['verified'] and sha(backup)==meta['sha256']
assert sha(a.model.read_bytes())==a.sha
paths={k:r/(a.stem+'-'+v) for k,v in [('log','install.log'),('before','littlefs-before.bin'),('after','littlefs-after.bin'),('table','partition.bin'),('record','stage.json')]}
assert all(not x.exists() for x in paths.values())
base=[sys.executable,'-m','esptool','--chip',meta['chip'],'--port',meta['port'],'--baud','921600','--after','no_reset']
try:
 identity=subprocess.run(base+['flash_id'],capture_output=True,check=True).stdout
 assert re.search(rb'MAC:\s*'+re.escape(meta['mac'].encode()),identity,re.I)
 with paths['log'].open('xb') as log:
  log.write(identity)
  def esp(args):subprocess.run(base+args,stdout=log,stderr=subprocess.STDOUT,check=True)
  esp(['read_flash','0x8000','0x1000',str(paths['table'])]);assert paths['table'].read_bytes()==backup[0x8000:0x9000]
  esp(['read_flash','0x625000','0x9DB000',str(paths['before'])]);esp(['verify_flash','0x625000',str(paths['before'])]);paths['before'].chmod(0o600)
  subprocess.run(['/private/tmp/hw1-speech-lfs-venv/bin/python',str(r.parent/'stage_model.py'),str(paths['before']),str(paths['after']),str(a.model),a.sha,str(paths['record'])],check=True)
  esp(['write_flash','0x625000',str(paths['after'])]);esp(['verify_flash','0x625000',str(paths['after'])])
 print(json.dumps({'model_sha256':a.sha,'filesystem_verified':True}),flush=True)
finally:
 s=serial.Serial(port=None,baudrate=115200,timeout=.1);s.dtr=False;s.rts=False;s.port=meta['port'];s.open()
 with s:HardReset(s,uses_usb=True)()
