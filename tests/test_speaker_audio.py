#!/usr/bin/env python3
"""Actual C++ selector bounds/behavior under sanitizers; disjoint plan fixtures.

Uses synthetic PCM and IDs only. Run with the numerical environment (numpy).
The full C++/Python feature and model parity audit is spkaudioaudit.py.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import array

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/device_tests/speaker'))
import spkwindows


def main():
    with tempfile.TemporaryDirectory(prefix='speaker-audio-test-') as work:
        root=Path(work);cpp=root/'test.cpp';exe=root/'test'
        cpp.write_text(r'''
#include "speaker_window.h"
#include "speaker_frontend.h"
#include <cassert>
#include <vector>
#include <random>
using namespace hw1::stt::speaker;
WindowSelection choose(const std::vector<int16_t>& pcm,unsigned mode) {
  const size_t size=window_workspace_floats(pcm.size());
  std::vector<float> guard(size+2,1234567);WindowSelection result;
  assert(select_window(pcm.data(),pcm.size(),mode,guard.data()+1,size,result));
  assert(guard.front()==1234567 && guard.back()==1234567);
  assert(result.start+result.samples<=pcm.size() && result.samples<=47840 && result.samples);
  return result;
}
int main() {
  std::vector<int16_t> pcm(90000,0);
  auto silent=choose(pcm,2);assert(silent.start==(90000-47840)/2 && silent.active_frames==0);
  for(size_t i=0;i<40000;++i)pcm[i]=int16_t(6000*std::sin(i*.08));
  auto center=choose(pcm,0),activity=choose(pcm,1);
  assert(activity.start<4000 && activity.selected_active_frames>center.selected_active_frames);
  pcm.assign(32000,0);
  for(size_t i=8000;i<24000;++i)pcm[i]=int16_t(6000*std::sin(i*.08));
  auto trimmed=choose(pcm,2);assert(trimmed.start>0 && trimmed.start<8000);
  assert(trimmed.start+trimmed.samples>24000 && trimmed.start+trimmed.samples<32000);
  pcm.assign(80000,1024);assert(choose(pcm,1).start==choose(pcm,0).start);
  assert(choose(pcm,3).start==choose(pcm,0).start);
  pcm.assign(120000,1000);
  for(size_t i=0;i<16000;++i)pcm[i]=16000;
  auto strongest=choose(pcm,3);assert(strongest.start==0);
  // Exact non-grid endpoint remains eligible.
  pcm.assign(90001,0);pcm.back()=30000;
  strongest=choose(pcm,3);assert(strongest.start==pcm.size()-47840);
  std::mt19937 rng(4);
  for(size_t n: {1,159,320,16000,47840,160000}) {
    pcm.resize(n);for(auto& v:pcm)v=int16_t(rng());
    for(unsigned mode=0;mode<4;++mode)choose(pcm,mode);
  }
  WindowSelection result;float w[3];int16_t x=0;
  assert(!select_window(nullptr,1,0,w,3,result));
  assert(!select_window(&x,0,0,w,3,result));
  assert(!select_window(&x,1,4,w,3,result));
  assert(!select_window(&x,1,0,w,2,result));
  // Actual native frontend: guarded workspace and output, including tiny and
  // long inputs. This validates memory bounds, not speaker accuracy.
  FeatureSpec spec;const size_t required=workspace_floats(spec,160000);
  std::vector<float> work(required+2,1234567),out(12002,1234567);
  Frontend frontend;assert(frontend.init(spec,160000,work.data()+1));
  for(size_t n: {1,257,16000,47840,160000}) {
    pcm.resize(n);for(auto& v:pcm)v=int16_t(rng());
    assert(frontend.compute(pcm.data(),pcm.size(),out.data()+1));
    assert(work.front()==1234567 && work.back()==1234567);
    assert(out.front()==1234567 && out.back()==1234567);
    for(size_t k=1;k<=12000;++k)assert(std::isfinite(out[k]));
  }
  assert(!frontend.compute(pcm.data(),160001,out.data()+1));
}
''')
        subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        '-I'+str(ROOT/'firmware/components/hw1_stt/stt'),str(cpp),
                        str(ROOT/'firmware/components/hw1_stt/stt/speaker_frontend.cpp'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)

        # The same ID cannot occur on opposite sides even across source names;
        # paired channel stores preserve the exact speaker partition.
        for name in spkwindows.STORES:
            folder=root/'stores'/name;folder.mkdir(parents=True)
            speakers=[str(i) for i in range(16) for _ in range(15)]
            data={'speakers':speakers,'lengths':[32000]*len(speakers),'offsets':[0]*len(speakers)}
            (folder/'index.json').write_text(json.dumps(data))
        old={'sets':[{'phrases':[{'ref':'0'}]}]}
        a=spkwindows.plan(root,old);b=spkwindows.plan(root,old)
        assert a==b
        dev=set();final=set()
        for store,part in a['partitions'].items():
            dev.update(part['development']);final.update(part['final'])
            assert a['partitions'][store]==a['partitions'][store.removesuffix('-g2')]
        assert not dev&final and '0' not in dev|final
        assert len(dev|final)==15
        # The frozen plan's root must select the audio, regardless of STT_ROOT
        # used for model imports in the surrounding environment.
        audio_path=root/'stores'/spkwindows.STORES[0]/'audio.bin'
        audio_path.write_bytes(array.array('h',[1,-2,300]).tobytes())
        _,audio=spkwindows.load_store(root,spkwindows.STORES[0])
        assert list(audio)==[1,-2,300]
        # Bootstrap direction and zero-effect identity, with channel pairs
        # kept at the same conversation index.
        rows=[]
        for index in range(3):
            for channel in ('fixture','fixture-g2'):
                counts={'scored':24,'labelled':24,'right':24,'split':0,'merge':0}
                rows.append({'group':'corpus:'+channel,'name':channel+'/'+str(index),
                             'counts':{'center':counts,'activity':dict(counts)}})
        ci=spkwindows.bootstrap(rows,'activity',100)
        assert all(v==[0,0] for v in ci.values()),ci
        for row in rows:row['counts']['activity']['merge']=1
        assert spkwindows.bootstrap(rows,'activity',100)['merge_per_100']==[4.167,4.167]
    print('speaker audio: window bounds and disjoint plan ok')


if __name__=='__main__':main()
