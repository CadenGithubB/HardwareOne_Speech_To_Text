"""Noise-freeze opt-in preserves floor through a quiet intra-utterance gap."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(r'''
#include "stt/stt_segmenter.h"
#include <cassert>
#include <vector>
using namespace hw1::stt;
unsigned trial(bool freeze) {
 SegmenterConfig c;c.adaptive=true;c.freeze_noise_during_speech=freeze;
 std::vector<int16_t> buffer(c.max_segment_samples);Segmenter s;
 assert(s.reset(buffer.data(),buffer.size(),c));
 auto feed=[&](int amplitude,int frames) {
  int16_t pcm[160];for(int i=0;i<160;++i)pcm[i]=(i&1)?amplitude:-amplitude;
  for(int i=0;i<frames;++i) {auto r=s.push(pcm,160);assert(r.consumed==160);}
 };
 feed(60,50);assert(s.noise_rms()==60);
 feed(1000,100);assert(s.noise_rms()==60);
 feed(5,5);return s.noise_rms();
}
int main(){assert(trial(false)==5);assert(trial(true)==60);}
''')
 subprocess.run(['c++','-std=c++17','-fsanitize=address,undefined','-I'+str(root/'firmware/components/hw1_stt'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('segmenter noise freeze checks passed')
