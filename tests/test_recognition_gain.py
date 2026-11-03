"""Exhaustively validate gain rounding, saturation and monotonicity over int16."""
from pathlib import Path
import tempfile,subprocess
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(r'''
#include "pcm_gain.h"
#include <cassert>
#include <cmath>
#include <algorithm>
int main() {
 int previous=-32768;
 for(int sample=-32768;sample<=32767;++sample) {
  const int expected=std::max(-32768,std::min(32767,int(std::round(sample*1.25))));
  const int actual=hw1::stt::recognition_gain_125(int16_t(sample));
  assert(actual==expected);assert(actual>=previous);previous=actual;
 }
}
''')
 subprocess.run(['c++','-std=c++17','-fsanitize=address,undefined','-I'+str(root/'firmware/components/hw1_stt/stt'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('recognition gain exhaustive checks passed')
