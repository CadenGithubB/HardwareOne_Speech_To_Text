"""Actual promotion predicate rejects stale/partial snapshots and forced redecode."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(r'''
#include "speculative_final_policy.h"
#include <cassert>
using hw1::stt::promote_speculative;
int main() {
 for(unsigned requested:{0u,1u,2u})for(unsigned completed:{0u,1u,2u})
 for(size_t cached:{size_t(0),size_t(319),size_t(320),size_t(640)})
 for(size_t final:{size_t(320),size_t(640)}) {
  bool original=requested && requested==completed && cached==final;
  assert(promote_speculative(requested,completed,cached,final)==original);
  assert(!promote_speculative(requested,completed,cached,final,true));
 }
}
'''.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>'))
 subprocess.run(['c++','-std=c++17','-fsanitize=address,undefined','-I'+str(root/'firmware/components/hw1_stt/stt'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('speculative promotion checks passed')
