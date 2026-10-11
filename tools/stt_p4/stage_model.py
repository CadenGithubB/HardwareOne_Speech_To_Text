"""Stage an additive model install against a fresh filesystem image; no USB IO."""
import argparse,hashlib,json
from pathlib import Path
from littlefs import LittleFS
from littlefs.context import UserContext
p=argparse.ArgumentParser();p.add_argument('original',type=Path);p.add_argument('output',type=Path);p.add_argument('model',type=Path);p.add_argument('sha256');p.add_argument('record',type=Path);a=p.parse_args()
sha=lambda x:hashlib.sha256(x).hexdigest()
original=a.original.read_bytes();model=a.model.read_bytes()
assert len(original)==0x9DB000 and sha(model)==a.sha256
assert not a.output.exists() and not a.record.exists()
ctx=UserContext(len(original));ctx.buffer[:]=original
fs=LittleFS(context=ctx,mount=False,block_size=4096,block_count=len(original)//4096,read_size=128,prog_size=128,cache_size=512,lookahead_size=128)
fs.mount()
def inventory():
 files={};dirs=[]
 for folder,subdirs,names in fs.walk('/'):
  dirs.append(folder)
  for name in names:
   path=folder.rstrip('/')+'/'+name
   with fs.open(path,'rb') as f:data=f.read()
   files[path]={'size':len(data),'sha256':sha(data)}
 return {'files':files,'directories':sorted(dirs)}
before=inventory();assert bytes(ctx.buffer)==original
folder='/STT Models';dest=folder+'/quartznet5x5.p4.stt'
assert dest not in before['files'], 'Refusing to replace an existing model; inspect it first'
assert before['files']['/ESP-SR Models/srmodels.bin']['sha256']=='16f3ef0bd4d961da5811acded6a1f7c9b64dfa1ebd120705d7b6a3f7906e8a17'
if folder not in before['directories']:fs.mkdir(folder)
with fs.open(dest,'wb') as f:assert f.write(model)==len(model)
after=inventory()
assert all(after['files'][path]==info for path,info in before['files'].items())
assert set(after['files'])==set(before['files'])|{dest}
assert set(after['directories'])-set(before['directories'])<={folder}
assert set(before['directories'])<=set(after['directories'])
assert after['files'][dest]['sha256']==sha(model)
fs.unmount()
with a.output.open('xb') as f:f.write(ctx.buffer)
a.output.chmod(0o600)
record={'all_existing_files_unchanged':True,'added_only':dest,'before_sha256':sha(original),'after_sha256':sha(ctx.buffer),'model_sha256':sha(model),'model_bytes':len(model),'before':before,'after':after}
a.record.write_text(json.dumps(record,indent=2)+'\n');a.record.chmod(0o600)
print(json.dumps({k:v for k,v in record.items() if k not in ('before','after')}),flush=True)
