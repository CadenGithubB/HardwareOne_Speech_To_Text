#!/usr/bin/env python3
"""Prepare a P4-only build copy over the immutable qualified speech snapshot."""
import argparse,hashlib,importlib.util,json,shutil,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent
BASE='f9bfe98'
SPEECH=HERE.parent/'speech_portable'
DEST=HERE/'private/app-p4'
DEP='components/hardwareone/idf_component.yml'
LOCK='dependencies.lock.esp32p4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module():
 s=importlib.util.spec_from_file_location('stt_speech',SPEECH/'prepare.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def changes():
 scope=['components/hardwareone','CMakeLists.txt','config/sdkconfig.defaults']
 names=subprocess.check_output(['git','diff','--name-only',BASE,'--',*scope],cwd=REPO).decode().splitlines()
 names+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','--','components/hardwareone'],cwd=REPO).decode().splitlines()
 return sorted(set(p for p in names if '/test/' not in p and (Path(p).suffix in ('.h','.cpp','.txt','.yml') and p!=DEP or p=='config/sdkconfig.defaults' or p.startswith('components/hardwareone/web_assets/') and Path(p).suffix in ('.js','.py'))))
def external_inputs():
 paths=[HERE/'prepare.py',HERE/'features-p4.h',HERE/'sdkconfig.stt.defaults',HERE/'radio_backend.cpp',HERE/'radio_backend.h',HERE/'build.sh',SPEECH/'sdkconfig.speech.defaults',SPEECH/'sdkconfig.p4.speech.defaults',HERE.parent/'p4_ble_roles/sdkconfig.connectivity.defaults',HERE.parent/'p4_ble_roles/sdkconfig.p4.bluetooth.defaults',HERE.parent/'camera_portable/sdkconfig.p4.camera.defaults']
 for parent in ('speech_portable','audio_portable','camera_portable','jpeg_portable','p4_ble_roles'):
  paths.extend(HERE.parent/parent/name for name in ('radio_backend.cpp','radio_backend.h'))
 return {str(p.relative_to(REPO)):sha(p) for p in paths}
def capture():
 tracked=set(subprocess.check_output(['git','ls-files'],cwd=REPO).decode().splitlines());parts=[]
 for p in changes():
  if p in tracked:parts.append(subprocess.check_output(['git','diff','--unified=2','--binary',BASE,'--',p],cwd=REPO))
  else:
   cmd=subprocess.run(['git','diff','--no-index','--binary','--','/dev/null',p],cwd=REPO,capture_output=True)
   assert cmd.returncode==1;parts.append(cmd.stdout)
 (HERE/'integration.patch').write_bytes(b''.join(parts))
 d={'base':BASE,'external':external_inputs(),'sources':{p:sha(REPO/p) for p in changes()},'dependency_sha256':sha(REPO/DEP),'patch_sha256':sha(HERE/'integration.patch')}
 (HERE/'integration-inputs.json').write_text(json.dumps(d,indent=2)+'\n')
def inputs():
 d=json.loads((HERE/'integration-inputs.json').read_text());assert d['base']==BASE
 assert d['sources']=={p:sha(REPO/p) for p in changes()}
 assert d['external']==external_inputs()
 assert d['patch_sha256']==sha(HERE/'integration.patch') and d['dependency_sha256']==sha(REPO/DEP)
 return d
def check(current=True,external=True):
 d=json.loads((DEST/'stt-build-manifest.json').read_text())
 if current:assert d['inputs']==inputs()
 if external and 'external' in d['inputs']:assert d['inputs']['external']==external_inputs()
 assert d['baseline_manifest_sha256']==sha(SPEECH/'private/app-p4/speech-build-manifest.json')
 for p,h in d['sources'].items():
  if p!=LOCK:assert sha(DEST/p)==h,p
 # Component manager may update aggregate hashes, but cannot replace any dependency.
 import yaml
 old=yaml.safe_load((SPEECH/'dependencies-p4.lock').read_text());new=yaml.safe_load((DEST/LOCK).read_text())
 def canonical(v):
  if isinstance(v,dict):return {k:(value.rstrip('/') if k=='registry_url' else canonical(value)) for k,value in v.items()}
  if isinstance(v,list):return [canonical(x) for x in v]
  return v
 for key in ('dependencies','target','version'):assert canonical(old[key])==canonical(new[key]),key
 assert set(new['direct_dependencies'])==set(old['direct_dependencies'])|{'espressif/esp-dl'}
 return len(d['sources'])
def prepare(refresh=False):
 if DEST.exists():
  assert refresh,'Existing build copy; use --check or --refresh'
  # A refresh may deliberately change the sealed profile/build inputs. Verify
  # the old source/dependency copy, then verify the new inputs before staging.
  check(False,external=False)
 m=module();m.check('p4',SPEECH/'private/app-p4',current=False)
 source,expected,common=m.baseline('p4');expected=dict(expected)
 expected.update(json.loads((SPEECH/'private/app-p4/speech-build-manifest.json').read_text())['overlay'])
 source=SPEECH/'private/app-p4';data=inputs()
 with tempfile.TemporaryDirectory(prefix='.stt-stage-',dir=HERE/'private') as directory:
  stage=Path(directory)
  for p in expected:
   out=stage/p;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/p,out)
  result=subprocess.run(['patch','-f','-F','0','-p','1'],input=(HERE/'integration.patch').read_bytes(),cwd=stage,capture_output=True)
  report=(result.stdout+result.stderr).decode()
  if result.returncode or 'fuzz' in report:raise ValueError(report)
  # Retire the earlier camera qualification command from this STT image.
  # Its production JPEG backend stays enabled; only the injected test entry and
  # include are removed. Exact anchors keep the inherited snapshot checkable.
  filesystem=stage/'components/hardwareone/System_Filesystem.cpp'
  body=filesystem.read_text()
  retired_lines=[
   '#include "Experiment_CameraJpegProbe.h"\n',
   '  { "camerajpegprobe", "Experiment only: validate a stored JPEG using the software decoder.", true, cmd_camerajpegprobe },\n',
  ]
  for line in retired_lines:
   assert body.count(line)==1,'Inherited JPEG probe changed'
   body=body.replace(line,'',1)
  assert 'cmd_camerajpegprobe' not in body
  filesystem.write_text(body)
  dep=stage/DEP
  assert 'espressif/esp-dl:' not in dep.read_text()
  dep.write_text(dep.read_text()+'\n  espressif/esp-dl:\n    version: "==3.3.12"\n')
  import yaml
  lock=yaml.safe_load((stage/LOCK).read_text());lock['direct_dependencies'].append('espressif/esp-dl')
  (stage/LOCK).write_text(yaml.safe_dump(lock,sort_keys=False))
  names=set(expected)|set(data['sources'])|{DEP,LOCK}
  record={'base':BASE,'retired_experiment_commands':['camerajpegprobe'],'inputs':data,'baseline_manifest_sha256':sha(source/'speech-build-manifest.json'),'sources':{p:sha(stage/p) for p in sorted(names)}}
  (stage/'stt-build-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
  if not DEST.exists():
   shutil.copytree(stage,DEST)
   shutil.copytree(source/'managed_components',DEST/'managed_components')
  else:
   for p in names:
    if not (DEST/p).exists() or sha(DEST/p)!=sha(stage/p):
     (DEST/p).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stage/p,DEST/p)
   shutil.copy2(stage/'stt-build-manifest.json',DEST/'stt-build-manifest.json')
 print('Verified',check(),'sources')
def main():
 p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group();g.add_argument('--capture',action='store_true');g.add_argument('--check',action='store_true');g.add_argument('--check-frozen',action='store_true');g.add_argument('--refresh',action='store_true');a=p.parse_args()
 if a.capture:capture()
 elif a.check or a.check_frozen:print('Verified',check(not a.check_frozen),'sources')
 else:prepare(a.refresh)
if __name__=='__main__':main()
