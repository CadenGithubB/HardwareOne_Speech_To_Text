#!/usr/bin/env python3
"""Create independent corrected manifests with read-only-use links to source audio.

Never edits the source root. Test speakers take precedence over development;
all reserved speakers and unknown identities are excluded from training shards.
This repairs future data use, not historical training exposure.
"""
import argparse
import json
from pathlib import Path
import shutil
import re
from diagnostics import atomic_json, audit_stores, effective_ids, family, sha256

UNKNOWN = {'', 'none', 'nan', 'unknown', 'null'}
AUGMENTATION = {'musan-noise', 'musan-speech', 'rirs', 'demand-noise-train'}


def missing(value):
    return str(value).strip().lower() in UNKNOWN


def role(name):
    if name in AUGMENTATION:
        return 'augmentation'
    if 'test' in name.split('-') or name == 'voxpopuli-validation' or name == 'voxpopuli-validation-g2':
        return 'test'
    if any(re.fullmatch(r'train[0-9]*', token) for token in name.split('-')):
        return 'train'
    if 'dev' in name.split('-') or 'validation' in name.split('-'):
        return 'dev'
    raise ValueError('Unclassified store: ' + name)


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination must be new')
    directories = sorted(p for p in source.iterdir() if (p/'index.json').exists())
    indices, usable, partitions, preserved = {}, {}, {}, {}
    for directory in directories:
        name = directory.name
        indices[name] = json.loads((directory/'index.json').read_text())
        usable[name] = effective_ids(directory, indices[name])
        partitions.setdefault(role(name), []).append(name)
        preserved[name] = {p.name:sha256(p) for p in (directory/'index.json',directory/'keep.json',directory/'excluded.json') if p.exists()}
    reserved = {'dev':{}, 'test':{}}
    for partition in reserved:
        for name in partitions.get(partition, []):
            if family(name) in ('musan','demand'):
                continue
            reserved[partition].setdefault(family(name),set()).update(
                str(indices[name]['speakers'][i]) for i in usable[name] if not missing(indices[name]['speakers'][i]))
    destination.mkdir(parents=True)
    summary = []
    for directory in directories:
        name = directory.name; partition = role(name); index = indices[name]
        target=destination/'stores'/name; target.mkdir(parents=True)
        archive=destination/'original-manifests'/name; archive.mkdir(parents=True)
        for filename in preserved[name]:
            shutil.copy2(directory/filename,archive/filename)
            shutil.copy2(directory/filename,target/filename)
        # The loader maps this audio with mode='r'. No preparation command is run on these links.
        (target/'audio.bin').symlink_to(directory/'audio.bin')
        old_path=target/'excluded.json'
        excluded=set(json.loads(old_path.read_text()).get('excluded',[])) if old_path.exists() else set()
        reasons={'missing_speaker':0,'reserved_speaker':0}
        if partition != 'augmentation' and family(name) not in ('musan','demand'):
            held=set()
            if partition == 'train':
                held=reserved['dev'].get(family(name),set()) | reserved['test'].get(family(name),set())
            elif partition == 'dev':
                held=reserved['test'].get(family(name),set())
            for i in usable[name]:
                speaker=index['speakers'][i]
                if missing(speaker): excluded.add(i); reasons['missing_speaker']+=1
                elif str(speaker) in held: excluded.add(i); reasons['reserved_speaker']+=1
        atomic_json(old_path,{'excluded':sorted(excluded),'policy':'unknown excluded; test > dev > train',
                             'source_manifest_sha256':preserved[name]['index.json']})
        kept=effective_ids(target,index)
        if not kept: raise ValueError('Repair leaves no usable items: '+name)
        removed=set(usable[name])-set(kept)
        summary.append({'store':name,'partition':partition,'before_items':len(usable[name]),
                        'after_items':len(kept),'removed_items':len(removed),
                        'removed_hours':sum(index['lengths'][i] for i in removed)/57600000,
                        'reasons':reasons})
    audit=audit_stores(destination/'stores',partitions,hash_audio=False)
    atomic_json(destination/'split-audit.json',audit)
    if audit['issues']: raise ValueError('Repaired split still fails: '+str(audit['issues']))
    for name,files in preserved.items():
        for filename,expected in files.items():
            if sha256(source/name/filename)!=expected: raise ValueError('Source changed during preparation')
    receipt={'schema':1,'source':str(source),'source_manifests':preserved,'partitions':partitions,
             'changes':summary,'audit_fingerprint':audit['fingerprint'],
             'scope':'Corrected future-use manifests; source audio linked, not copied or certified unseen',
             'source_unchanged':True,'audio_verification':'metadata only; full content audit is separate'}
    atomic_json(destination/'split-receipt.json',receipt)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=prepare(a.source,a.output)
    print(json.dumps({'stores':len(result['changes']),'changed':[x for x in result['changes'] if x['removed_items']],
                      'source_unchanged':result['source_unchanged']}))


if __name__ == '__main__': main()
