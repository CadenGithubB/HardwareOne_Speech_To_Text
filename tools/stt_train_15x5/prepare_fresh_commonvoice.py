#!/usr/bin/env python3
"""Freeze a speaker-disjoint screening/reserve pair from locally downloaded CV audio.

Eligibility excludes ALL speakers in ALL existing CV stores, ignoring keep filters
conservatively. No model is used for selection. Does not establish disjointness from
NVIDIA pretraining or undocumented past experiments. Source archives are read-only.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import tarfile
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from common import normalize_text, encode, ctc_min_frames
from diagnostics import atomic_json, sha256


def rank(seed, value):
    return hashlib.sha256((seed+':'+value).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-stores',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--speakers-per-partition',type=int,default=32)
    p.add_argument('--clips-per-speaker',type=int,default=2)
    p.add_argument('--seed',default='stt-fresh-speakers-20261103-v1')
    a=p.parse_args()
    if a.speakers_per_partition<1 or a.clips_per_speaker<1: p.error('Counts must be positive')
    names=('commonvoice-fresh-dev','commonvoice-fresh-test')
    if any((a.output_root/'stores'/n).exists() for n in names): p.error('Fresh stores already exist')
    known=set(); known_texts=set(); sources={}
    for path in sorted(a.source_stores.glob('commonvoice*/index.json')):
        index=json.loads(path.read_text());known.update(str(s) for s in index['speakers'])
        known_texts.update(index['texts']);sources[path.parent.name]=sha256(path)
    rows={}
    bad=re.compile(r'[0-9]|[^\x00-\x7f]')
    with a.metadata.open(newline='') as f:
        for row in csv.DictReader(f,delimiter='\t',quoting=csv.QUOTE_NONE):
            speaker=row['client_id'][:16]
            raw=row['sentence'].replace('\u2019',"'").replace('\u2018',"'")
            if not speaker or speaker in known or bad.search(raw): continue
            text=normalize_text(raw)
            if text:rows[row['path']]={'speaker':speaker,'text':text,'client_id':row['client_id']}
    print(json.dumps({'event':'metadata_ready','known_speakers':len(known),'candidate_rows':len(rows)}),flush=True)
    by_speaker={}
    with tarfile.open(a.archive) as archive:
        for member in archive:
            filename=Path(member.name).name
            if member.isfile() and filename in rows:
                row=rows[filename]
                by_speaker.setdefault(row['speaker'],[]).append((member,row))
        chosen=[]; decode_rejections=0
        for speaker in sorted(by_speaker,key=lambda s:rank(a.seed,s)):
            accepted=[]
            for member,row in sorted(by_speaker[speaker],key=lambda x:rank(a.seed,x[0].name)):
                blob=archive.extractfile(member).read()
                try:x,rate=sf.read(io.BytesIO(blob),dtype='float32')
                except (RuntimeError,sf.LibsndfileError): decode_rejections+=1;continue
                if x.ndim==2:x=x.mean(axis=1)
                if not 2.0<=len(x)/rate<=10.0 or not np.isfinite(x).all():
                    decode_rejections+=1;continue
                if rate!=16000:
                    divisor=math.gcd(rate,16000)
                    x=resample_poly(x,16000//divisor,rate//divisor).astype(np.float32)
                if ctc_min_frames(encode(row['text']))>(len(x)//160)//2-1:
                    decode_rejections+=1;continue
                pcm=np.clip(np.round(x*32767),-32768,32767).astype('<i2').tobytes()
                accepted.append({'pcm':pcm,'row':row,'member':member.name,
                                 'source_mp3_sha256':hashlib.sha256(blob).hexdigest()})
                if len(accepted)==a.clips_per_speaker:break
            if len(accepted)==a.clips_per_speaker:chosen.append((speaker,accepted))
            if len(chosen)==a.speakers_per_partition*2:break
    if len(chosen)!=a.speakers_per_partition*2:raise ValueError('Insufficient new eligible speakers')
    # Alternate speakers in the fixed hash ordering to split independently of transcript/error scores.
    summary={}; all_records={}
    for partition,name in enumerate(names):
        target=a.output_root/'stores'/name;target.mkdir(parents=True)
        offsets=[];lengths=[];texts=[];speakers=[];records=[];offset=0
        with (target/'audio.bin').open('wb') as f:
            for speaker,clips in chosen[partition::2]:
                for clip in clips:
                    pcm=clip['pcm'];f.write(pcm)
                    offsets.append(offset);lengths.append(len(pcm)//2);offset+=len(pcm)//2
                    texts.append(clip['row']['text']);speakers.append(speaker)
                    records.append({'index':len(records),'speaker':speaker,'member':clip['member'],
                                    'source_mp3_sha256':clip['source_mp3_sha256'],
                                    'pcm_sha256':hashlib.sha256(pcm).hexdigest()})
        atomic_json(target/'index.json',{'offsets':offsets,'lengths':lengths,'texts':texts,'speakers':speakers,
            'audio_sha256':sha256(target/'audio.bin'),'source':{'archive':str(a.archive.resolve()),
            'metadata_sha256':sha256(a.metadata),'selection_seed':a.seed,
            'scope':'Speakers absent from all current CV store indices; pretraining membership unknown'}})
        all_records[name]=records
        summary[name]={'items':len(lengths),'speakers':len(set(speakers)),'seconds':sum(lengths)/16000,
                       'references_also_in_prior_cv_stores':sum(t in known_texts for t in texts)}
    receipt={'schema':1,'seed':a.seed,'source_store_indices':sources,'archive':str(a.archive.resolve()),
        'archive_sha256':sha256(a.archive),'metadata_sha256':sha256(a.metadata),'known_speakers':len(known),
        'available_candidate_speakers':len(by_speaker),'decode_or_length_rejections':decode_rejections,
        'partitions':summary,'records':all_records,
        'reserve_policy':'commonvoice-fresh-test remains unscored; commonvoice-fresh-dev becomes development once evaluated',
        'limits':['Current-store and recorded-recipe evidence, not proof against undocumented history',
                  'Pretrained model speaker/content exposure is unknown','Read speech, not conversational/far-field qualification']}
    atomic_json(a.output_root/'fresh-selection.json',receipt)
    print(json.dumps(summary),flush=True)


if __name__=='__main__': main()
