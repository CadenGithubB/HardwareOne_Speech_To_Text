#!/usr/bin/env python3
"""Deferred decisions, immutable emissions, expiry and adversarial speakers.

Synthetic embeddings only; no model, audio, private sessions or numpy required.
The fixed two/three-evidence variants are an experiment, not a firmware change.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/device_tests/speaker'))
import spkprovisional as trial


def unit(v):
    norm = sum(x*x for x in v)**.5
    return [x/norm for x in v]


def phrases(vectors, refs=None, samples=48000):
    return [{'id': i, 'e': unit(v), 'samples': samples, 'ref': refs[i] if refs else i,
             'mixed': False} for i, v in enumerate(vectors)]


def main():
    with tempfile.TemporaryDirectory(prefix='test-provisional-') as work:
        runner = trial.Runner(work)
        a = [1, 0, 0]
        other = [0, 0, 1]
        borderline = [.558, (1-.558**2)**.5, 0]
        bridge = unit([x+y for x, y in zip(a, borderline)])
        ph = phrases([a, other, borderline, other, bridge, other, bridge], [1, 2, 1, 2, 1, 2, 1])
        order = list(range(len(ph)))
        for out in runner.runs(ph, [(2, order), (3, order)]):
            assert len({out[i][0] for i in (0, 2, 4, 6)}) == 1 and out[0][0] >= 0, out
            assert out[1][0] == out[3][0] == out[5][0] >= 0 and out[1][0] != out[0][0], out
            assert max(r[2] for r in out) <= 8

        # Similar but distinguishable voices must not be combined; a bridge
        # matching both established profiles remains unknown, even at flush.
        b = [.58, (1-.58**2)**.5, 0]
        both = unit([x+y for x, y in zip(a, b)])
        ph = phrases([a, b, a, b, both], [1, 2, 1, 2, 3])
        out = runner.runs(ph, [(2, list(range(5)))])[0]
        assert out[0][0] == out[2][0] != out[1][0] == out[3][0], out
        assert out[-1][0] == -1 and out[-1][1] == 'end_unknown', out

        # Short phrases cannot seed a profile. No end-of-session forced labels.
        ph = phrases([a]*5, samples=16000)
        assert all(s == -1 for s, _, _ in runner.runs(ph, [(2, list(range(5)))])[0])

        # A single unsupported phrase expires; later evidence cannot relabel it.
        ph = phrases([a]+[other]*8+[a, a], [1]+[2]*8+[1, 1])
        out = runner.runs(ph, [(2, list(range(len(ph))))])[0]
        assert out[0] == (-1, 'expired', 8) and out[-1][0] >= 0, out

        # No method can distinguish different references with identical
        # embeddings. Keep this limitation explicit instead of a false oracle.
        ph = phrases([a, a, a], [1, 2, 1])
        out = runner.runs(ph, [(2, [0, 1, 2])])[0]
        assert len({s for s, _, _ in out}) == 1

        # Validate the actual C++ class under sanitizers, including causality:
        # any emitted label must stay immutable under arbitrary future input.
        cpp = Path(work)/'invariants.cpp'
        cpp.write_text(r'''
#include "provisional_clusters.h"
#include <cassert>
#include <cstring>
#include <limits>
#include <random>
using namespace hw1::stt::speaker;
int main() {
  for(unsigned evidence: {2u,3u}) {
    ProvisionalClusters c(8,evidence);
    std::mt19937 gen(17); std::normal_distribution<float> normal;
    for(int i=0;i<200;++i) {
      const auto prior=c.labels(); float e[8];for(float& v:e)v=normal(gen);
      c.push(e,i%3 ? 48000 : 16000);
      assert(c.pending()<=8);
      for(size_t j=0;j<prior.size();++j)if(std::strcmp(prior[j].reason,"pending")) {
        assert(c.labels()[j].speaker==prior[j].speaker);
        assert(c.labels()[j].delay==prior[j].delay);
        assert(!std::strcmp(c.labels()[j].reason,prior[j].reason));
      }
    }
    c.flush();assert(c.pending()==0);
    for(const auto& a:c.labels())assert(a.delay<=8 && std::strcmp(a.reason,"pending"));
  }
  ProvisionalClusters c(2,2);
  float bad[2]={std::numeric_limits<float>::quiet_NaN(),1}, zero[2]={0,0};
  c.push(bad,32000);c.push(zero,32000);c.flush();
  assert(c.labels()[0].speaker==-1 && c.labels()[1].speaker==-1);
}
''')
        exe = Path(work)/'invariants'
        subprocess.run(['c++', '-std=c++17', '-fsanitize=address,undefined', '-g',
                        '-I'+str(ROOT/'tools/device_tests/speaker'), str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

        # Scoring and CLI schema stay numeric; all variants receive identical
        # input orders and held-out corpus assignment is deterministic.
        conv = {'name': 'fixture/0', 'group': 'corpus:fixture', 'phrases': phrases([a, other]*4, [1, 2]*4)}
        held = dict(conv, name='fixture/1')
        clean = dict(conv, name='fixture', group='clean')
        out = trial.compare([conv, held, clean], shuffles=2, bootstrap=100)
        assert out['groups']['corpus_heldout']['production']['all_orders']['runs'] == 1
        assert out['groups']['clean']['deferred2']['all_orders']['runs'] == 3
        assert out['groups']['clean']['deferred2']['all_orders']['coverage'] == 100
        assert out['paired_bootstrap']['corpus_heldout']['paired_blocks'] == 1
        assert out['paired_bootstrap']['corpus_heldout']['ci95']['deferred2']['merge_per_100'] == [0, 0]
        unscored = dict(clean, phrases=phrases([a, a]))
        for p in unscored['phrases']:
            p['ref'] = None
        no_reference = trial.compare([unscored], shuffles=0, bootstrap=0)
        assert no_reference['groups']['clean']['deferred2']['in_order']['coverage'] is None
        assert not no_reference['versus_production']['clean']['deferred2']['quality_nonregression']
        assert trial.delay_summary({0: 2, 4: 2})['p90'] == 4
        sets = Path(work)/'fixture.json'
        sets.write_text(json.dumps({'sets': [clean]}))
        cli = subprocess.run([sys.executable, str(ROOT/'tools/device_tests/speaker/spkprovisional.py'),
                              str(sets), '--shuffles', '0'], check=True, capture_output=True, text=True)
        assert json.loads(cli.stdout)['config']['pending_limit'] == 8
    print('spkprovisional: deferred labels and bounds ok')


if __name__ == '__main__':
    main()
