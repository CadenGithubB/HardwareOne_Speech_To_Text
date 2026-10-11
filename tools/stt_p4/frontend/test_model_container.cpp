#include "stt_model_container.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include <vector>
using namespace hw1::stt;
struct Reader {
    std::vector<uint8_t> bytes;
    size_t position=0,chunk=96,calls=0;
    bool oversized=false;
    static size_t read(void* opaque,void* output,size_t wanted) {
        auto& self=*static_cast<Reader*>(opaque);++self.calls;
        if(self.oversized)return wanted+1;
        size_t n=std::min({wanted,self.chunk,self.bytes.size()-self.position});
        if(n)std::memcpy(output,self.bytes.data()+self.position,n);
        self.position+=n;return n;
    }
};
int main(int argc,char**argv) {
    if(argc!=2)return 2;
    std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
    if(!input)return 3;
    const auto length=input.tellg();if(length<0)return 4;
    size_t bytes=static_cast<size_t>(length);
    std::vector<uint8_t> header(container::kHeaderBytes);input.seekg(0);
    input.read(reinterpret_cast<char*>(header.data()),header.size());if(!input)return 5;
    assert(container::valid_size(bytes));
    assert(container::valid_header(header.data(),header.size(),bytes));
    for(size_t chunk: {size_t(1),size_t(7),size_t(96)}) {
        Reader reader{header};reader.chunk=chunk;
        assert(container::read_header(&reader,bytes,Reader::read));
        assert(reader.position==96);
    }
    // Every envelope byte is checked, including both complete SHA256 identities.
    for(size_t offset=0;offset<header.size();++offset)for(unsigned bit=0;bit<8;++bit) {
        Reader reader{header};reader.bytes[offset]^=uint8_t(1u<<bit);
        assert(!container::read_header(&reader,bytes,Reader::read));
    }
    for(size_t have=0;have<header.size();++have) {
        Reader reader{std::vector<uint8_t>(header.begin(),header.begin()+have)};reader.chunk=7;
        assert(!container::read_header(&reader,bytes,Reader::read));
        // Incomplete in-memory headers must be rejected before any byte access.
        uint8_t tiny=0;
        assert(!container::valid_header(&tiny,have,bytes));
    }
    for(size_t bad: {size_t(0),size_t(95),size_t(96),bytes-1,bytes+1,std::numeric_limits<size_t>::max()}) {
        Reader reader{header};assert(!container::read_header(&reader,bad,Reader::read));
        assert(reader.calls==0); // Wrong total size is rejected before touching the stream.
    }
    Reader oversized{header};oversized.oversized=true;
    assert(!container::read_header(&oversized,bytes,Reader::read));
    assert(!container::read_header(nullptr,bytes,nullptr));
    assert(!container::valid_header(nullptr,96,bytes));
    assert(!container::valid_header(header.data(),97,bytes));
    puts("Real pinned envelope accepted; all768 one-bit mutations,96 truncations, invalid totals/readers rejected before decompression/parser");
}
