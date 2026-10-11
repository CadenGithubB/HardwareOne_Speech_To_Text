import argparse, hashlib, json, pathlib, re, subprocess, sys, time
import serial
from esptool.reset import HardReset
p=argparse.ArgumentParser()
p.add_argument('board',choices=['p4','s3']);p.add_argument('image');p.add_argument('sha256');p.add_argument('stem')
p.add_argument('--seconds',type=float,default=40);p.add_argument('--camera',action='store_true')
a=p.parse_args();outroot=pathlib.Path(__file__).resolve().parent;root=outroot.parents[1]/'speech_portable/private/run-20260928'
meta=json.loads((root/f'{a.board}-backup.json').read_text())
limit={'p4':0x615000,'s3':0x5b5000}[a.board]
img=pathlib.Path(a.image).resolve();data=img.read_bytes()
assert hashlib.sha256(data).hexdigest()==a.sha256
assert 0<len(data)<=limit
partition=img.parent/'partition_table/partition-table.bin'
assert (root/f'{a.board}-full-flash.bin').read_bytes()[0x8000:0x8000+partition.stat().st_size]==partition.read_bytes(), 'Partition layout changed'
assert meta['verified']
assert hashlib.sha256((root/f'{a.board}-full-flash.bin').read_bytes()).hexdigest()==meta['sha256']
flashlog=outroot/(a.stem+'-flash.log');logpath=outroot/(a.stem+'-serial.log')
assert not flashlog.exists() and not logpath.exists()
base=[sys.executable,'-m','esptool','--chip',meta['chip'],'--port',meta['port'],'--baud','921600','--after','no_reset']
identity=subprocess.run(base+['flash_id'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True).stdout
assert re.search(rb'MAC:\s*'+re.escape(meta['mac'].encode()),identity,re.I), 'Wrong physical board'
with flashlog.open('xb') as log:
 log.write(identity)
 subprocess.run(base+['write_flash','0x10000',str(img)],stdout=log,stderr=subprocess.STDOUT,check=True)
 subprocess.run(base+['verify_flash','0x10000',str(img)],stdout=log,stderr=subprocess.STDOUT,check=True)
print(json.dumps({'board':a.board,'flashed':len(data),'verified':True,'sha256':a.sha256}),flush=True)
s=serial.Serial(port=None,baudrate=115200,timeout=.1)
s.dtr=False;s.rts=False;s.port=meta['port'];s.open()
with s,logpath.open('xb') as log:
 HardReset(s,uses_usb=True)()
 end=time.monotonic()+a.seconds;captured=bytearray()
 while time.monotonic()<end:
  chunk=s.read(min(max(s.in_waiting,1),4096))
  if chunk:
   log.write(chunk);log.flush();captured.extend(chunk)
   if a.camera and re.search(rb'CAM_RESULT[^\r\n]*\r?\n',captured):break
text=captured.decode('utf-8','replace')
summary={'board':a.board,'serial_log':str(logpath),'capture_bytes':len(captured),'panic':bool(re.search(r'Guru Meditation|panic\(|abort\(\)',text))}
if a.camera:
 summary['camera_lines']=[s for s in text.splitlines() if s.startswith('CAM_') and not s.startswith('CAM_JPEG offset=')]
 summary['result']=re.findall(r'CAM_RESULT[^\r\n]*',text)
(outroot/(a.stem+'-result.json')).write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
if summary['panic'] or (a.camera and not summary['result']):sys.exit(3)
