"""Capped bonus can resolve weak acoustics without overriding strong controls."""
from pathlib import Path
import tempfile,subprocess
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(r'''
#include "stt_lm_testlib.h"
#include <cassert>
#include <cstring>
namespace lm=hw1::stt::lm;
std::string decode(lm::Lm& m,lmtest::Logits& x,const lm::CustomWords* words) {
 char text[512]={};lm::DecodeStats stats;
 auto status=lm::decode(x.q.data(),x.q.size()/29,-2,m,words,text,sizeof(text),{},0,&stats);
 assert(status==lm::DecodeStatus::Ok);return text;
}
int main() {
 lmtest::Spec s;s.alpha=0;s.beta=0;s.unk=0;s.prune=-8;s.bonus=20;s.beam=8;
 s.uni("</s>",0).uni("<s>",0).uni("<unk>",0);
 auto blob=lmtest::build(s);lm::Lm m;assert(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
 lm::CustomWords words;assert(words.parse("kat\n",4)==1);
 lmtest::Logits weak;weak.frame({{'c',31},{'k',30}});weak.pattern("_a_t__");
 assert(decode(m,weak,nullptr)=="cat");assert(decode(m,weak,&words)=="kat");
 lmtest::Logits strong;strong.frame({{'c',40},{'k',20}});strong.pattern("_a_t__");
 assert(decode(m,strong,nullptr)=="cat");assert(decode(m,strong,&words)=="cat");
 lmtest::Logits target;target.frame({{'k',40},{'c',20}});target.pattern("_a_t__");
 assert(decode(m,target,&words)=="kat");
}
''')
 subprocess.run(['clang++','-std=c++17','-O2','-DHW1_STT_HOTWORD_BONUS_CAP=1.5','-fsanitize=address,undefined','-I'+str(root/'tests'),'-I'+str(root/'firmware/components/hw1_stt'),str(p/'test.cpp'),str(root/'firmware/components/hw1_stt/stt/stt_lm.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('bounded vocabulary checks passed')
