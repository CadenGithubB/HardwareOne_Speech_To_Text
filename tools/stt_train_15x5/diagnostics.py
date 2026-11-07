"""Training audit primitives. No torch dependency; reports may contain private text."""
import hashlib
import itertools
import json
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def effective_ids(directory, index):
    directory = Path(directory)
    n = len(index['lengths'])
    keep_path = directory / 'keep.json'
    ids = json.loads(keep_path.read_text())['keep'] if keep_path.exists() else list(range(n))
    excluded_path = directory / 'excluded.json'
    excluded = json.loads(excluded_path.read_text()).get('excluded', []) if excluded_path.exists() else []
    for label, values in [('keep', ids), ('excluded', excluded)]:
        if len(values) != len(set(values)) or any(type(i) is not int or not 0 <= i < n for i in values):
            raise ValueError(f'{directory.name}: invalid {label} indices')
    excluded = set(excluded)
    return [i for i in ids if i not in excluded]


def family(name):
    for prefix in ('ami', 'librispeech', 'voxpopuli', 'peoples', 'commonvoice', 'demand', 'musan'):
        if name.startswith(prefix):
            return prefix
    return name


def inspect_store(directory, hash_audio=True):
    directory = Path(directory)
    index = json.loads((directory / 'index.json').read_text())
    n = len(index['lengths'])
    if not n or any(len(index[k]) != n for k in ('offsets', 'texts', 'speakers')):
        raise ValueError(f'{directory.name}: empty or inconsistent index')
    size = (directory / 'audio.bin').stat().st_size
    if size % 2 or any(type(o) is not int or type(l) is not int or o < 0 or l <= 0 or (o+l)*2 > size
                       for o, l in zip(index['offsets'], index['lengths'])):
        raise ValueError(f'{directory.name}: invalid audio ranges')
    ids = effective_ids(directory, index)
    if not ids:
        raise ValueError(f'{directory.name}: no usable examples')
    fingerprints = {p.name: sha256(p) for p in (directory / 'index.json', directory / 'keep.json',
                                               directory / 'excluded.json') if p.exists()}
    audio = {'bytes': size}
    if hash_audio:
        audio['sha256'] = sha256(directory / 'audio.bin')
        if index.get('audio_sha256') and audio['sha256'] != index['audio_sha256']:
            raise ValueError(f'{directory.name}: audio hash differs from writer manifest')
    else:
        audio.update(mtime_ns=(directory / 'audio.bin').stat().st_mtime_ns,
                     verification='metadata only; not content verified')
    record = {'name': directory.name, 'files': fingerprints, 'audio': audio,
              'items': len(ids), 'seconds': sum(index['lengths'][i] for i in ids)/16000}
    return record, index, ids


def audit_stores(root, partitions, hash_audio=True):
    """Compare speaker identities across partitions within each corpus, across ALL shards.

    Dataset names containing 'test' do not define partitions: callers explicitly assign roles.
    Noise environments may share speakers across time-split stores and are excluded from the
    speech-speaker check, but their bytes and indices are still fingerprinted.
    """
    records, groups, issues = {}, {}, []
    for role, names in partitions.items():
        groups[role] = {}
        for name in names:
            record, index, ids = inspect_store(Path(root) / name, hash_audio)
            records[name] = record
            if family(name) in ('musan', 'demand') or name == 'rirs':
                continue
            speakers = {str(index['speakers'][i]) for i in ids}
            if speakers & {'', 'None', 'nan', 'unknown'}:
                issues.append({'kind': 'missing_speaker', 'store': name})
            groups[role].setdefault(family(name), set()).update(speakers)
    for left, right in itertools.combinations(groups, 2):
        for corpus in groups[left].keys() & groups[right].keys():
            overlap = groups[left][corpus] & groups[right][corpus]
            if overlap:
                issues.append({'kind': 'speaker_overlap', 'partitions': [left, right],
                               'corpus': corpus, 'speakers': len(overlap)})
    return {'schema': 1, 'partitions': partitions, 'stores': records, 'issues': issues,
            'content_verified': hash_audio, 'fingerprint': digest(records)}


def error_counts(ref, hyp):
    """Minimum word edits; deterministic ties prefer substitution, deletion, insertion."""
    a, b = ref.split(), hyp.split()
    row = [(j, 0, 0, j) for j in range(len(b)+1)]
    for i, x in enumerate(a, 1):
        nxt = [(i, 0, i, 0)]
        for j, y in enumerate(b, 1):
            if x == y:
                nxt.append(row[j-1])
            else:
                e,s,d,k = row[j-1]; sub = (e+1,s+1,d,k)
                e,s,d,k = row[j]; delete = (e+1,s,d+1,k)
                e,s,d,k = nxt[-1]; insert = (e+1,s,d,k+1)
                nxt.append(min((sub, delete, insert), key=lambda v: v[0]))
        row = nxt
    e,s,d,i = row[-1]
    return dict(errors=e, substitutions=s, deletions=d, insertions=i, words=len(a))


def summarize(rows):
    totals = {k: sum(row[k] for row in rows) for k in
              ('errors', 'substitutions', 'deletions', 'insertions', 'words')}
    seconds = sum(r.get('seconds', 0) for r in rows)
    return {**totals, 'utterances': len(rows), 'wer': totals['errors']/totals['words'] if totals['words'] else None,
            'phantom_words_per_minute': totals['insertions']*60/seconds if not totals['words'] and seconds else None}


def paired_changes(previous, current):
    def keyed(rows):
        result = {r['id']: r for r in rows}
        if len(result) != len(rows):
            raise ValueError('duplicate utterance IDs')
        return result
    old, new = keyed(previous), keyed(current)
    if old.keys() != new.keys():
        raise ValueError('paired evaluation coverage differs')
    changes = []
    for key, row in new.items():
        before = old[key]
        if any(row.get(k) != before.get(k) for k in ('ref', 'pcm_sha256')):
            raise ValueError(f'paired identity differs: {key}')
        changes.append({'id': key, 'error_delta': row['errors']-before['errors']})
    return {'improved': sum(r['error_delta'] < 0 for r in changes),
            'worsened': sum(r['error_delta'] > 0 for r in changes),
            'unchanged': sum(r['error_delta'] == 0 for r in changes), 'changes': changes}


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Read-only dataset audit; exits nonzero on speaker overlap.')
    p.add_argument('--stores', type=Path, required=True)
    p.add_argument('--train', nargs='+', required=True)
    p.add_argument('--dev', nargs='+', required=True)
    p.add_argument('--test', nargs='*', default=[])
    p.add_argument('--metadata-only', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = audit_stores(a.stores, {'train': a.train, 'dev': a.dev, 'test': a.test}, not a.metadata_only)
    atomic_json(a.output, report)
    print(json.dumps({'issues': report['issues'], 'fingerprint': report['fingerprint']}))
    raise SystemExit(bool(report['issues']))
