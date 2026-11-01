#!/usr/bin/env python3
"""Check spkrules.py: candidate rules against the production clusterer, scoring and the embed pieces.

The neutral candidate must reproduce speaker_cluster.h decision for decision on random sequences (with
ambiguity, short phrases and capacity). On the Conversation 1 pattern from test_spkreplay.py, hold must avoid
the duplicate speaker and merge must fold it back. Embedding uses fake embedders; no model, numpy or device.
"""
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools/device_tests/speaker'))
import spkrules  # noqa: E402
import test_spkdiag as logs  # noqa: E402
import test_spkreplay as tones  # noqa: E402


def unit(v):
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def random_phrases(rng, speakers, n, dim=8, spread=0.55):
    means = [unit([rng.gauss(0, 1) for _ in range(dim)]) for _ in range(speakers)]
    out = []
    for _ in range(n):
        s = rng.randrange(speakers)
        e = unit([m + rng.gauss(0, spread) for m in means[s]])
        out.append({'id': len(out), 'ref': s, 'mixed': False, 'samples': rng.choice([20000, 30000, 40000, 64000]),
                    'e': e})
    return out


def equivalence(runner):
    rng, reasons = random.Random(7), set()
    for trial in range(40):
        ph = random_phrases(rng, rng.choice([2, 3, 4, 12]), 40)
        for threshold in (0.45, 0.6):
            prod = spkrules.parse_rule(f'production:threshold={threshold}', threshold)
            neutral = dict(prod, kind='candidate')
            for max_speakers in (8, 3):
                orders = [list(range(len(ph)))] + [rng.sample(range(len(ph)), len(ph)) for _ in range(3)]
                jobs = [(r, o) for o in orders for r in (prod, neutral)]
                out = runner.runs(ph, jobs, 32000, max_speakers)
                for k in range(0, len(out), 2):
                    assert out[k] == out[k + 1], (trial, threshold, max_speakers, out[k], out[k + 1])
                    reasons |= {r for _, r in out[k]}
    assert {'new', 'match', 'short_match', 'ambiguous', 'no_match_short', 'capacity'} <= reasons, reasons


def conversation_one():
    ph = [{'id': i, 'ref': (101, 202)[i % 2], 'mixed': False, 'samples': 52800, 'e': unit(v)}
          for i, v in enumerate(tones.VECTORS)]
    return {'name': 'conv1-like', 'group': 'clean', 'phrases': ph}


def main():
    with tempfile.TemporaryDirectory(prefix='hw1-spkrules-') as tmp:
        root = Path(tmp)
        runner = spkrules.Runner(root)
        equivalence(runner)

        # Rules on the Conversation 1 pattern: clip 2 is 0.558 from speaker 101's first phrase.
        conv = conversation_one()
        rules = {r['name']: r for r in map(lambda t: spkrules.parse_rule(t, 0.6), spkrules.DEFAULT_RULES)}
        order = list(range(10))
        labels = dict(zip(rules, runner.runs(conv['phrases'], [(r, order) for r in rules.values()], 32000)))
        assert [s for s, _ in labels['production']] == [0, 1, 2, 1, -1, 1, -1, 1, -1, 1], labels['production']
        assert [s for s, _ in labels['hold_0.50']] == [0, 1, -1, 1, 0, 1, 0, 1, 0, 1], labels['hold_0.50']
        assert labels['hold_0.50'][2][1] == 'hold' and labels['hold_0.45'][2][1] == 'hold'
        assert [s for s, _ in labels['merge_young3']] == [0, 1, 2, 1, 0, 1, 0, 1, 0, 1], labels['merge_young3']
        assert labels['merge_young3'][4][1] == 'merge'
        # Their centroids are 0.558 alike, so a 0.6 similarity floor keeps them apart.
        floor = spkrules.parse_rule('floor:merge_young=3,merge_sim=0.6', 0.6)
        assert runner.runs(conv['phrases'], [(floor, order)], 32000)[0] == labels['production']
        m = {name: spkrules.run_metrics(conv['phrases'], order, lab) for name, lab in labels.items()}
        assert (m['production']['labelled'], m['production']['split'], m['production']['merge']) == (7, 1, 0)
        assert (m['hold_0.50']['labelled'], m['hold_0.50']['split'], m['hold_0.50']['right']) == (9, 0, 9)
        assert (m['merge_young3']['labelled'], m['merge_young3']['split']) == (10, 1)   # clip 2 keeps label 2
        lumped = spkrules.run_metrics(conv['phrases'], order, [(0, 'match')] * 10)
        assert (lumped['split'], lumped['merge'], lumped['right']) == (0, 5, 5)

        # Corpus sampler: 2, 3, 4 speakers in turn, no utterance twice in a conversation.
        d = {'speakers': [f's{k // 14}' for k in range(70)], 'lengths': [32000 + 800 * (k % 14) for k in range(70)]}
        d['offsets'] = [sum(d['lengths'][:k]) for k in range(70)]
        convs = spkrules.corpus_conversations(d, 6, 24, seed=3)
        assert [len({s for s, _ in c}) for c in convs] == [2, 3, 4, 2, 3, 4], convs
        assert all(len(c) == len({i for _, i in c}) and len(c) <= 24 for c in convs)
        audio = [0] * d['offsets'][-1] + [0] * d['lengths'][-1]
        for k in range(70):
            audio[d['offsets'][k]] = 1000 * (int(d['speakers'][k][1:]) + 1)
        seen = []
        speaker_vector = lambda x: (seen.append(len(x)), [1.0 if j == round(x[0] * 32.768) - 1 else 0.05 for j in range(5)])[1]
        corpus = spkrules.corpus_sets('fake', d, audio, speaker_vector, convs, 12800)
        assert [s['group'] for s in corpus] == ['corpus:fake'] * 6 and corpus[0]['phrases'][0]['samples'] == \
            d['lengths'][corpus[0]['phrases'][0]['id']] + 12800
        assert seen[0] == d['lengths'][convs[0][0][1]]

        # Clip and session sets from the tone playlist, with its fake embedder.
        man_path, man = tones.playlist(root)
        clean = spkrules.clip_set(man_path, tones.fake_embedder([]), 32000, 0.3, 0.5)
        assert [p['ref'] for p in clean['phrases']] == [101, 202] * 5 and clean['phrases'][2]['samples'] == 52800
        assert abs(sum(a * b for a, b in zip(clean['phrases'][0]['e'], clean['phrases'][2]['e'])) - 0.558) < 1e-3
        plan = [([i], logs.decision(0, 'match', i % 2, 2, samples=48000), True) for i in range(10)]
        session = logs.write_session(root, '2026-device', man_path, man, plan, True, 'submitted=10 labelled=10 skipped=0')
        dev = spkrules.session_set(session, tones.fake_embedder([]), 32000)
        assert dev['group'] == 'session' and dev['uncut'] == 0 and len(dev['phrases']) == 10

        # compare: the clean group, a corpus group, and their pooled summaries.
        chosen = [rules[n] for n in ('production', 'hold_0.50', 'merge_young3')]
        out = spkrules.compare([conv] + corpus, chosen, 32000, shuffles=0)
        clean_cmp = out['versus_production']['clean']
        assert clean_cmp['hold_0.50']['meets_criterion'] and clean_cmp['hold_0.50']['split_per_100'] == -10.0, clean_cmp
        assert not clean_cmp['merge_young3']['meets_criterion'], clean_cmp
        prod = out['groups']['clean']['production']['in_order']
        assert (prod['coverage'], prod['accuracy_labelled'], prod['split_per_100']) == (70.0, 85.7, 10.0), prod
        assert set(out['groups']) == {'clean', 'corpus:fake', 'corpus', 'all'}
        assert out['groups']['corpus']['production']['all_orders']['runs'] == 6
        shuffled = spkrules.compare([conv], chosen, 32000, shuffles=20, per_set=True)
        assert shuffled['groups']['clean']['production']['all_orders']['runs'] == 21
        assert shuffled['per_set_in_order'][0]['rules']['production']['split'] == 1

        # The command line reads sets files and prints JSON only.
        sets_path = root / 'sets.json'
        sets_path.write_text(json.dumps({'version': 1, 'sets': [conv]}))
        import subprocess
        cli = subprocess.run([sys.executable, str(ROOT / 'tools/device_tests/speaker/spkrules.py'), 'compare',
                              str(sets_path), '--shuffles', '5', '--rules', 'production;hold_0.50:new_below=0.5'],
                             check=True, capture_output=True, text=True).stdout
        assert json.loads(cli)['groups']['clean']['hold_0.50']['all_orders']['runs'] == 6
    print('spkrules: rules and scoring ok')


if __name__ == '__main__':
    main()
