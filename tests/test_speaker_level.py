"""Actual C++ normalizer: gain limits, silence, output bounds and invalid targets."""
from pathlib import Path
import tempfile,subprocess
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(r'''
#include "speaker_level.h"
#include <cassert>
#include <limits>
using hw1::stt::speaker::normalize_level;
int main() {
 int16_t zero[]={0,0};assert(normalize_level(zero,2)==1 && zero[0]==0);
 int16_t quiet[]={100,-100};assert(normalize_level(quiet,2)==4 && quiet[0]==400 && quiet[1]==-400);
 int16_t steady[]={500,-500};assert(normalize_level(steady,2)==2 && steady[0]==1000);
 int16_t loud[]={20000,-20000};assert(normalize_level(loud,2)==.25f && loud[0]==5000);
 int16_t sparse[1024]={};sparse[0]=32767;sparse[1]=-32768;
 const float gain=normalize_level(sparse,1024,3000);assert(gain>1);
 assert(sparse[0]==32767 && sparse[1]==-32768);
 int16_t x=42;assert(normalize_level(&x,1,std::numeric_limits<float>::quiet_NaN())==1 && x==42);
 assert(normalize_level(&x,1,-1)==1 && x==42);
 assert(normalize_level(nullptr,1)==1);
}
''')
 subprocess.run(['c++','-std=c++17','-fsanitize=address,undefined','-I'+str(root/'firmware/components/hw1_stt/stt'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('speaker level checks passed')
