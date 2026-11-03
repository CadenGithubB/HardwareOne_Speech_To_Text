#!/usr/bin/env python3
"""Compare speaker-labelling rules offline on saved voiceprints: the production rule against candidates.

  spkrules.py embed OUT.json [--manifest M ...] [--session S ...] [--stores A,B] [--convs 30] [--turns 24]
  spkrules.py compare SETS.json [...] [--rules default] [--shuffles 200] [--threshold 0.6] [--sets]

embed needs proto.py's environment, as spkreplay.py does. It writes phrase sets: each phrase's unit
voiceprint, reference speaker and length (no audio or text; keep the file under private/):
  --manifest  every clip of a conversation playlist, cut as spkreplay.py's clip mode   group "clean"
  --session   the phrases a device session clustered, at their played spans            group "session"
  --stores    synthetic conversations from proto.py's speech stores: 2, 3 or 4 speakers in turn (another
              speaker 80% of the time), each turn a different 1-10 s utterance          group "corpus:<store>"
Clip and corpus phrase lengths include the device's 300 ms pre-roll and 500 ms tail (--pre-ms, --tail-ms);
corpus voiceprints are of the utterance alone, as neighbouring store audio is another recording.

compare runs every rule over every set: in the recorded order and, for clean and session sets, --shuffles
seeded random orders shared by all rules (sensitivity only: real turns are not random). "production" is
firmware/components/hw1_stt/stt/speaker_cluster.h itself; candidates are cluster_candidates.h:
  hold   a long phrase matching no speaker starts one only below new_below, else stays unknown
         (young=N: only while the closest speaker holds fewer than N phrases)
  merge  a phrase matching exactly two speakers merges them when the smaller holds fewer than merge_young
         phrases and their centroids are at least merge_sim alike
A rule is NAME or NAME:key=value,... (threshold, new_below, young, merge_young, merge_sim, ambiguity_margin, create_ms, update_ms, history_cap, defer_steps); --rules default
is the built-in list. Rules without candidate keys run the production class.

Per group (and pooled corpus and all) and rule, over all orders and over the recorded order alone:
coverage, accuracy of labelled phrases (best one-to-one mapping per run), split phrases (labelled phrases
outside their speaker's largest label) and merge phrases (labelled phrases in a label dominated by another
speaker) per 100 scored phrases, and the share of runs with any split or merge. versus_production gives
each rule's change and whether it meets the criterion: fewer split phrases and no more merge phrases over all
orders. Phrases without a reference or spanning two speakers are clustered but not scored. Labels already
given are never rewritten, so a merged speaker's earlier phrases still count as split. Numbers and IDs only.
"""
import argparse
import collections
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spkdiag  # noqa: E402
import spkreplay  # noqa: E402
from spkeval import best_mapping  # noqa: E402

DEFAULT_RULES = ['production', 'production_0.55:threshold=0.55', 'production_0.65:threshold=0.65',
                 'hold_0.50:new_below=0.5', 'hold_0.45:new_below=0.45', 'hold_0.50_young4:new_below=0.5,young=4',
                 'merge_young3:merge_young=3', 'merge_young3_sim0.45:merge_young=3,merge_sim=0.45',
                 'hold_0.50+merge_young3:new_below=0.5,merge_young=3']
CANDIDATE_KEYS = ('defer_steps', 'history_cap', 'create_ms', 'update_ms', 'ambiguity_margin', 'new_below', 'young', 'merge_young', 'merge_sim')


# ---- embed

def phrase(pid, ref, mixed, samples, e):
    return {'id': pid, 'ref': ref, 'mixed': mixed, 'samples': samples, 'e': [round(v, 6) for v in spkreplay.unit(e)]}


def clip_set(manifest, embed, min_new, pre, tail):
    man = json.loads(Path(manifest).read_text())
    rate, pcm = spkreplay.read_wav(spkreplay.playlist_wav(manifest, man))
    segs = spkreplay.segments(man, None, min_new, pre, tail)[0]
    return {'name': Path(manifest).parent.name, 'group': 'clean',
            'phrases': [phrase(s['id'], s['ref'], s['mixed'], s['samples'], embed(spkreplay.cut(rate, pcm, s['span'])))
                        for s in segs]}


def session_set(session, embed, min_new):
    session = Path(session)
    manifest = json.loads((session / 'session.json').read_text())['manifest']
    man = json.loads(Path(manifest).read_text())
    rate, pcm = spkreplay.read_wav(spkreplay.playlist_wav(manifest, man))
    segs, uncut = spkreplay.segments(man, session, min_new, 0, 0)
    return {'name': f'{session.parent.name}/{session.name}', 'group': 'session', 'uncut': uncut,
            'phrases': [phrase(s['id'], s['ref'], s['mixed'], s['samples'], embed(spkreplay.cut(rate, pcm, s['span'])))
                        for s in segs]}


def corpus_conversations(d, n_convs, n_turns, seed, lo=1.0, hi=10.0):
    """[(speaker, utterance index)] per conversation, no utterance used twice in one conversation."""
    sr = spkreplay.SR
    by = collections.defaultdict(list)
    for i, (s, n) in enumerate(zip(d['speakers'], d['lengths'])):
        if lo * sr <= n <= hi * sr:
            by[s].append(i)
    spks = sorted((s for s, v in by.items() if len(v) >= n_turns // 2 + 2), key=str)
    rng, out = random.Random(seed), []
    for c in range(n_convs):
        k = (2, 3, 4)[c % 3]
        if len(spks) < k:
            break
        chosen = rng.sample(spks, k)
        pools = {s: rng.sample(by[s], len(by[s])) for s in chosen}
        turns, last = [], None
        for _ in range(n_turns):
            s = rng.choice([x for x in chosen if x != last] if last is not None and rng.random() < 0.8 else chosen)
            if not pools[s]:
                break
            turns.append((s, pools[s].pop()))
            last = s
        out.append(turns)
    return out


def corpus_sets(store, d, audio, embed, convs, pad_samples):
    out = []
    for c, turns in enumerate(convs):
        phrases = []
        for s, i in turns:
            x = audio[d['offsets'][i]:d['offsets'][i] + d['lengths'][i]]
            x = x / 32768.0 if hasattr(x, 'dtype') else [v / 32768.0 for v in x]
            phrases.append(phrase(i, s, False, d['lengths'][i] + pad_samples, embed(x)))
        out.append({'name': f'{store}/{c}', 'group': f'corpus:{store}', 'phrases': phrases})
    return out


def load_store(name):
    sys.path.insert(0, str(spkreplay.SPEAKER_TOOLS))
    import proto
    return proto.load_store(name)


# ---- compare

def parse_rule(text, threshold):
    name, _, spec = text.partition(':')
    rule = {'name': name, 'threshold': threshold, 'new_below': 2.0, 'young': 0, 'merge_young': 0,
            'merge_sim': -2.0, 'ambiguity_margin': 0.0, 'create_ms': 0, 'update_ms': 0, 'history_cap': 0, 'defer_steps': 0}
    for item in filter(None, spec.split(',')):
        key, value = item.split('=')
        if key not in rule or key == 'name':
            raise SystemExit(f'unknown rule key {key!r} in {text!r}')
        rule[key] = int(value) if key in ('defer_steps', 'history_cap', 'young', 'merge_young', 'create_ms', 'update_ms') else float(value)
    rule['kind'] = 'candidate' if any(k in spec for k in CANDIDATE_KEYS) else 'production'
    return rule


class Runner:
    def __init__(self, workdir):
        self.exe = spkreplay.Clusterer(workdir).exe

    def runs(self, phrases, jobs, min_new, max_speakers=8):
        """jobs: (rule, order) pairs. Returns [(speaker, reason)] per job, in that job's order."""
        lines = [f"clear {len(phrases[0]['e'])}"]
        lines += ['load %d %s' % (p['samples'], ' '.join('%.7g' % v for v in p['e'])) for p in phrases]
        for r, order in jobs:
            lines.append(' '.join(str(x) for x in (
                'run', r['kind'], repr(r['threshold']), min_new, max_speakers, repr(r['new_below']), r['young'],
                r['merge_young'], repr(r['merge_sim']), repr(r['ambiguity_margin']), r['create_ms'] * 16, r['update_ms'] * 16, r['history_cap'], r['defer_steps'], len(order), *order)))
        out = subprocess.run([str(self.exe)], input='\n'.join(lines) + '\n', capture_output=True, text=True,
                             check=True).stdout.splitlines()
        return [[(int(t.split(':')[0]), t.split(':')[1]) for t in line.split()] for line in out]


def run_metrics(phrases, order, labels):
    keep = [(phrases[i]['ref'], spk) for i, (spk, _) in zip(order, labels)
            if phrases[i]['ref'] is not None and not phrases[i]['mixed']]
    right = best_mapping([k[0] for k in keep], [k[1] for k in keep])[0]
    by_ref, by_label = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for ref, spk in keep:
        if spk >= 0:
            by_ref[ref][spk] += 1
            by_label[spk][ref] += 1
    excess = lambda groups: sum(sum(c.values()) - max(c.values()) for c in groups.values())
    return {'scored': len(keep), 'labelled': sum(1 for _, s in keep if s >= 0), 'right': right,
            'split': excess(by_ref), 'merge': excess(by_label),
            'reasons': collections.Counter(reason for _, reason in labels)}


def empty():
    return {'runs': 0, 'scored': 0, 'labelled': 0, 'right': 0, 'split': 0, 'merge': 0, 'runs_with_split': 0,
            'runs_with_merge': 0, 'reasons': collections.Counter()}


def add(total, m):
    total['runs'] += 1
    for k in ('scored', 'labelled', 'right', 'split', 'merge'):
        total[k] += m[k]
    total['runs_with_split'] += m['split'] > 0
    total['runs_with_merge'] += m['merge'] > 0
    total['reasons'] += m['reasons']


def derive(t):
    per100 = lambda n: round(100 * n / t['scored'], 2) if t['scored'] else None
    return {'runs': t['runs'], 'scored': t['scored'], 'coverage': spkdiag.pct(t['labelled'], t['scored']),
            'accuracy_labelled': spkdiag.pct(t['right'], t['labelled']), 'accuracy': spkdiag.pct(t['right'], t['scored']),
            'split_per_100': per100(t['split']), 'merge_per_100': per100(t['merge']),
            'runs_with_split': spkdiag.pct(t['runs_with_split'], t['runs']),
            'runs_with_merge': spkdiag.pct(t['runs_with_merge'], t['runs']), 'reasons': dict(t['reasons'])}


def compare(sets, rules, min_new, shuffles=0, seed=1, per_set=False):
    if not any(r['name'] == 'production' for r in rules):
        raise SystemExit('the rules must include one named production')
    totals = collections.defaultdict(lambda: collections.defaultdict(lambda: {'all': empty(), 'in_order': empty()}))
    rows = []
    with tempfile.TemporaryDirectory(prefix='spkrules-') as tmp:
        runner = Runner(tmp)
        for k, s in enumerate(sets):
            ph = s['phrases']
            if not ph:
                continue
            rng = random.Random(seed * 1000003 + k)
            orders = [list(range(len(ph)))]
            if not s['group'].startswith('corpus'):
                for _ in range(shuffles):
                    o = list(range(len(ph)))
                    rng.shuffle(o)
                    orders.append(o)
            jobs = [(r, o) for r in rules for o in orders]
            results = runner.runs(ph, jobs, min_new)
            groups = [s['group'], 'all'] + (['corpus'] if s['group'].startswith('corpus') else [])
            row = {'name': s['name'], 'group': s['group'], 'phrases': len(ph), 'rules': {}}
            for (r, o), labels in zip(jobs, results):
                m = run_metrics(ph, o, labels)
                for g in groups:
                    add(totals[g][r['name']]['all'], m)
                    if o is orders[0]:
                        add(totals[g][r['name']]['in_order'], m)
                if o is orders[0]:
                    row['rules'][r['name']] = {k2: m[k2] for k2 in ('scored', 'labelled', 'right', 'split', 'merge')}
            rows.append(row)
    out_groups, versus = {}, {}
    for g, by_rule in totals.items():
        out_groups[g] = {name: {'all_orders': derive(t['all']), 'in_order': derive(t['in_order'])}
                         for name, t in by_rule.items()}
        base = out_groups[g]['production']['all_orders']
        versus[g] = {}
        for name, v in out_groups[g].items():
            if name == 'production':
                continue
            a = v['all_orders']
            diff = lambda key: round(a[key] - base[key], 2) if a[key] is not None and base[key] is not None else None
            versus[g][name] = {'split_per_100': diff('split_per_100'), 'merge_per_100': diff('merge_per_100'),
                               'coverage': diff('coverage'), 'accuracy_labelled': diff('accuracy_labelled'),
                               'meets_criterion': bool(a['split_per_100'] is not None
                                                       and a['split_per_100'] < base['split_per_100']
                                                       and a['merge_per_100'] <= base['merge_per_100'])}
    out = {'rules': {r['name']: {k: r[k] for k in ('kind', 'threshold') + CANDIDATE_KEYS} for r in rules},
           'min_new_samples': min_new, 'shuffles': shuffles, 'seed': seed,
           'sets': collections.Counter(s['group'] for s in sets),
           'criterion': 'fewer split phrases and no more merge phrases per 100 scored phrases than production, '
                        'over all orders of the group',
           'groups': out_groups, 'versus_production': versus}
    if per_set:
        out['per_set_in_order'] = rows
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    e = sub.add_parser('embed', help='write voiceprint sets (needs proto.py)')
    e.add_argument('out')
    e.add_argument('--manifest', action='append', default=[])
    e.add_argument('--session', action='append', default=[])
    e.add_argument('--stores', default='')
    e.add_argument('--convs', type=int, default=30)
    e.add_argument('--turns', type=int, default=24)
    e.add_argument('--seed', type=int, default=20261031)
    e.add_argument('--min-new-ms', type=int, default=2000)
    e.add_argument('--pre-ms', type=int, default=300)
    e.add_argument('--tail-ms', type=int, default=500)
    c = sub.add_parser('compare', help='score rules over voiceprint sets')
    c.add_argument('sets', nargs='+')
    c.add_argument('--rules', default='default', help='"default" or semicolon-separated rule specs')
    c.add_argument('--threshold', type=float, default=0.6)
    c.add_argument('--min-new-ms', type=int, default=2000)
    c.add_argument('--shuffles', type=int, default=200)
    c.add_argument('--seed', type=int, default=1)
    c.add_argument('--sets', dest='per_set', action='store_true', help='also print each set\'s in-order counts')
    a = ap.parse_args()
    min_new = a.min_new_ms * 16
    if a.command == 'embed':
        embed = spkreplay.model_embedder()
        pre, tail = a.pre_ms / 1000, a.tail_ms / 1000
        sets = [clip_set(m, embed, min_new, pre, tail) for m in a.manifest]
        sets += [session_set(s, embed, min_new) for s in a.session]
        for store in filter(None, a.stores.split(',')):
            d, audio = load_store(store)
            convs = corpus_conversations(d, a.convs, a.turns, a.seed)
            sets += corpus_sets(store, d, audio, embed, convs, round((pre + tail) * spkreplay.SR))
        Path(a.out).write_text(json.dumps({'version': 1, 'model': 'proto.py float ResNetSE34L, device front end',
                                           'min_new_samples': min_new, 'sets': sets}))
        print(json.dumps({'out': a.out, 'sets': dict(collections.Counter(s['group'] for s in sets)),
                          'phrases': sum(len(s['phrases']) for s in sets)}))
        return
    sets = [s for path in a.sets for s in json.loads(Path(path).read_text())['sets']]
    specs = DEFAULT_RULES if a.rules == 'default' else [x for x in a.rules.split(';') if x]
    rules = [parse_rule(x, a.threshold) for x in specs]
    print(json.dumps(compare(sets, rules, min_new, a.shuffles, a.seed, a.per_set)))


if __name__ == '__main__':
    main()
