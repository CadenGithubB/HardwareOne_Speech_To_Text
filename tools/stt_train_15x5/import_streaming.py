#!/usr/bin/env python3
"""Import one complete, aligned device recording per input into a linked stage report.

Manifest: {provenance: {...}, cases: [{id, pcm, ref, capture, alignment,
capture_complete: true}]}. Paths are relative to the manifest. pcm is the exact
16-kHz mono signed-int16 little-endian input used by the offline stages.
Capture is standalone final-event JSONL or a bench JSON object with captions.
Alignment is a JSON evidence file with passed=true and a nonempty method.
No board access is performed. Imported evidence is required, not independently
re-measured here; use the existing reference-alignment tools to create it.
"""
import argparse
import json
import re
from pathlib import Path
from diagnostics import atomic_json, sha256
from compare_stages import stage_report


def raw_caption_text(path):
    text = Path(path).read_text()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(value, dict) and 'captions' in value:
        rows = value['captions']
        field = 'sttText'
    else:
        rows = [r for r in (value if isinstance(value,list) else [value]) if r.get('type') == 'final']
        field = 'rawText'
    keys = [(r.get('sessionId'),r['sequence']) for r in rows]
    if len(keys) != len(set(keys)) or len({k[0] for k in keys}) > 1:
        raise ValueError('Capture has duplicate finals or multiple sessions')
    if any(field not in r for r in rows):
        raise ValueError('Raw caption text missing; formatted text is not an acoustic result')
    # Match the character model reference alphabet without semantic rewriting.
    text = ' '.join(r[field] for r in sorted(rows,key=lambda r:r['sequence'])).lower().replace('-', ' ')
    text = re.sub(r"[^a-z' ]", ' ', text)
    text = re.sub(r"\s+'|'\s+", ' ', f' {text} ')
    return ' '.join(text.split())


def import_capture(manifest_path):
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    records = []
    for case in manifest['cases']:
        pcm, capture, alignment = [path.parent / case[k] for k in ('pcm','capture','alignment')]
        evidence = json.loads(alignment.read_text())
        if case.get('capture_complete') is not True or evidence.get('passed') is not True or not evidence.get('method'):
            raise ValueError('A complete capture and passed alignment evidence are required')
        pcm_hash, capture_hash = sha256(pcm), sha256(capture)
        if evidence.get('pcm_sha256') != pcm_hash or evidence.get('capture_sha256') != capture_hash:
            raise ValueError('Alignment evidence is not bound to these audio/capture bytes')
        size = pcm.stat().st_size
        if not size or size % 2:
            raise ValueError('Invalid signed-int16 PCM size')
        records.append({'id':case['id'],'ref':case['ref'],'hyp':raw_caption_text(capture),
                        'pcm_sha256':pcm_hash,'seconds':size/32000,'capture_sha256':capture_hash,
                        'alignment_passed':True,'alignment_sha256':sha256(alignment)})
    return stage_report('streaming',manifest['provenance'],records)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    report=import_capture(a.manifest)
    atomic_json(a.output,report)
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    main()
