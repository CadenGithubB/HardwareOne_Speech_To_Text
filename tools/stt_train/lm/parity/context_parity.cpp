// Host harness: the production decoder (stt/stt_lm.cpp, from the tree given at
// compile time) with phrase context. Reads cases from stdin, one per line:
//   <logits.i8>\t<frames>\t<end_eos 0|1>\t<context text, may be empty>
// and prints one decoded text per line (or "!<status>"). Exponent -2 (P4).
#include "stt/stt_lm.h"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>
namespace lm=hw1::stt::lm;
int main(int argc, char** argv) {
    if(argc<2) { std::fprintf(stderr,"usage: context_parity meeting.lm < cases.tsv\n"); return 2; }
    std::ifstream f(argv[1],std::ios::binary);
    std::vector<uint8_t> blob((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
    lm::Lm model;
    if(model.open(blob.data(),blob.size())!=lm::LoadStatus::Ok) { std::fprintf(stderr,"bad lm\n"); return 1; }
    std::string line;
    std::vector<char> text(4096);
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);
        std::string path, frames, end, context;
        std::getline(in,path,'\t'); std::getline(in,frames,'\t'); std::getline(in,end,'\t'); std::getline(in,context);
        std::ifstream q(path,std::ios::binary);
        std::vector<int8_t> logits((std::istreambuf_iterator<char>(q)),std::istreambuf_iterator<char>());
        const auto start=context.empty() ? lm::DecodeStart{} : lm::DecodeStart::after(model,context.c_str(),end=="1");
        lm::DecodeStart s=start; if(context.empty()) s.endOfSentence=end=="1";
        const auto st=lm::decode(logits.data(),std::stoul(frames),-2,model,nullptr,text.data(),text.size(),{},0,nullptr,s);
        if(st!=lm::DecodeStatus::Ok) std::printf("!%d\n",int(st)); else std::printf("%s\n",text.data());
    }
    return 0;
}
