#pragma once
// Test-only HW1LM1 writer and an independent, map-based double-precision
// reference of the FORMAT.md decoder. It deliberately shares no scoring or
// search code with stt/stt_lm.cpp (only lm::sha256 for writing trailers).
#include "stt/stt_lm.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace lmtest {
using Words2=std::pair<std::string,std::string>;
using Words3=std::tuple<std::string,std::string,std::string>;
struct Spec {
    std::map<std::string,std::pair<int,int>> unigrams;   // word -> (log10*1000, backoff*1000)
    std::map<Words2,std::pair<int,int>> bigrams;
    std::map<Words3,int> trigrams;
    float alpha=1, beta=0, unk=-6, prune=-5, bonus=0;
    uint32_t beam=8;
    Spec& uni(const std::string& w, int q, int bo=0) { unigrams[w]={q,bo}; return *this; }
    Spec& bi(const std::string& a, const std::string& b, int q, int bo=0) { bigrams[{a,b}]={q,bo}; return *this; }
    Spec& tri(const std::string& a, const std::string& b, const std::string& c, int q) { trigrams[{a,b,c}]=q; return *this; }
};
inline void put16(std::vector<uint8_t>& b, uint32_t v) { b.push_back(uint8_t(v)); b.push_back(uint8_t(v>>8)); }
inline void put32(std::vector<uint8_t>& b, uint32_t v) { for(int i=0;i<4;++i)b.push_back(uint8_t(v>>(8*i))); }
inline void set32(std::vector<uint8_t>& b, size_t at, uint32_t v) { for(int i=0;i<4;++i)b[at+i]=uint8_t(v>>(8*i)); }
inline uint32_t get32(const std::vector<uint8_t>& b, size_t at) { uint32_t v=0; for(int i=0;i<4;++i)v|=uint32_t(b[at+i])<<(8*i); return v; }
inline uint32_t bits(float f) { uint32_t v; std::memcpy(&v,&f,4); return v; }
inline void pad4(std::vector<uint8_t>& b) { while(b.size()%4)b.push_back(0); }
// Section offsets of a built file, for targeted corruption.
struct Offsets { size_t unigram, offsets, strings, bigram, trigram, digest; };
inline Offsets offsets(const std::vector<uint8_t>& b) {
    const uint64_t V=get32(b,12), nb=get32(b,16), nt=get32(b,20), sb=get32(b,24);
    auto a4=[](uint64_t v) { return size_t((v+3)&~uint64_t(3)); };
    Offsets o; o.unigram=64; o.offsets=a4(o.unigram+4*V); o.strings=a4(o.offsets+4*V);
    o.bigram=a4(o.strings+sb); o.trigram=a4(o.bigram+8*nb); o.digest=a4(o.trigram+8*nt); return o;
}
inline void reseal(std::vector<uint8_t>& b) {
    uint8_t hash[32]; assert(b.size()>=32);
    const bool hashed=hw1::stt::lm::sha256(b.data(),b.size()-32,hash); assert(hashed); (void)hashed;
    std::memcpy(b.data()+b.size()-32,hash,32);
}
inline std::vector<uint8_t> build(const Spec& s) {
    std::vector<std::string> words; std::map<std::string,uint32_t> id;
    for(const auto& item:s.unigrams) { id[item.first]=uint32_t(words.size()); words.push_back(item.first); }
    std::string strings; std::vector<uint32_t> offs;
    for(const auto& w:words) { offs.push_back(uint32_t(strings.size())); strings+=w; strings.push_back('\0'); }
    std::vector<uint8_t> b(64,0);
    std::memcpy(b.data(),"HW1LM1\0\0",8);
    set32(b,8,1); set32(b,12,uint32_t(words.size())); set32(b,16,uint32_t(s.bigrams.size()));
    set32(b,20,uint32_t(s.trigrams.size())); set32(b,24,uint32_t(strings.size()));
    set32(b,28,bits(s.alpha)); set32(b,32,bits(s.beta)); set32(b,36,bits(s.unk)); set32(b,40,s.beam);
    set32(b,44,bits(s.prune)); set32(b,52,bits(s.bonus));
    for(const auto& w:words) { put16(b,uint16_t(int16_t(s.unigrams.at(w).first))); put16(b,uint16_t(int16_t(s.unigrams.at(w).second))); }
    pad4(b); for(uint32_t o:offs)put32(b,o);
    pad4(b); b.insert(b.end(),strings.begin(),strings.end());
    pad4(b);
    for(const auto& g:s.bigrams) { // std::map string order == id order
        put16(b,id.at(g.first.first)); put16(b,id.at(g.first.second));
        put16(b,uint16_t(int16_t(g.second.first))); put16(b,uint16_t(int16_t(g.second.second)));
    }
    pad4(b);
    for(const auto& g:s.trigrams) {
        put16(b,id.at(std::get<0>(g.first))); put16(b,id.at(std::get<1>(g.first))); put16(b,id.at(std::get<2>(g.first)));
        put16(b,uint16_t(int16_t(g.second)));
    }
    pad4(b);
    set32(b,48,uint32_t(b.size()+32));
    b.resize(b.size()+32); reseal(b);
    return b;
}

// Frame helpers: '_' blank, ' ' space, '\'' apostrophe, 'a'..'z'.
inline int cls(char c) { return c=='_' ? 28 : c==' ' ? 0 : c=='\'' ? 27 : c-'a'+1; }
inline char sym(int c) { return " abcdefghijklmnopqrstuvwxyz'_"[c]; }
struct Logits {
    std::vector<int8_t> q;
    size_t frames() const { return q.size()/29; }
    int8_t* add(int base=0) { q.insert(q.end(),29,int8_t(base)); return &q[q.size()-29]; }
    Logits& pattern(const char* s, int hi=40) { for(;*s;++s)add()[cls(*s)]=int8_t(hi); return *this; }
    // One frame with several symbols at chosen values, others at base.
    Logits& frame(std::initializer_list<std::pair<char,int>> values, int base=0) {
        int8_t* f=add(base); for(const auto& v:values)f[cls(v.first)]=int8_t(v.second); return *this;
    }
};

// Straightforward FORMAT.md decoder over strings and std::map, in double.
struct Reference {
    const Spec& spec;
    std::set<std::string> hot;
    double strength=1.0; // external-score multiplier, independent of search implementation
    // Closest rank decision at any beam cut or the final pick. Only ties with
    // identical LM parts (identical arithmetic, e.g. equal logits) count as
    // exact; real-arithmetic coincidences via different paths round by ULPs
    // differently in any two implementations and are reported as gap 0.
    double minGap=std::numeric_limits<double>::infinity();
    static constexpr double kInf=std::numeric_limits<double>::infinity();
    static double lse(double a, double b) { if(a<b)std::swap(a,b); return b==-kInf ? a : a+std::log1p(std::exp(b-a)); }
    bool known(const std::string& w) const { return spec.unigrams.count(w)!=0; }
    double uni(const std::string& w, bool backoff) const { auto& u=spec.unigrams.at(w); return (backoff ? u.second : u.first)/1000.0; }
    double p2(const std::string& b, const std::string& c) const {
        auto it=spec.bigrams.find({b,c});
        return it!=spec.bigrams.end() ? it->second.first/1000.0 : uni(b,true)+uni(c,false);
    }
    double p(const std::string& a, const std::string& b, const std::string& c) const {
        if(a.empty())return p2(b,c);
        auto t=spec.trigrams.find(Words3{a,b,c});
        if(t!=spec.trigrams.end())return t->second/1000.0;
        auto g=spec.bigrams.find({a,b});
        return (g!=spec.bigrams.end() ? g->second.second/1000.0 : 0.0)+p2(b,c);
    }
    struct State { double lm=0; std::string c2, c1="<s>"; };
    void complete(State& s, const std::string& w) const {
        const double log10p=known(w) ? p(s.c2,s.c1,w) : double(spec.unk);
        s.lm+=strength*(double(spec.alpha)*std::log(10.0)*log10p+double(spec.beta)+(hot.count(w) ? double(spec.bonus) : 0.0));
        s.c2=s.c1; s.c1=known(w) ? w : "<unk>";
    }
    State state(const std::string& prefix, std::string* partial) const {
        State s; std::string word;
        for(char c:prefix) { if(c==' ') { complete(s,word); word.clear(); } else word.push_back(c); }
        if(partial)*partial=word;
        return s;
    }
    double lmOf(const std::string& prefix) const { return state(prefix,nullptr).lm; }
    double finalLm(const std::string& prefix) const {
        std::string partial; State s=state(prefix,&partial);
        if(!partial.empty())complete(s,partial);
        return s.lm+strength*(double(spec.alpha)*std::log(10.0)*p(s.c2,s.c1,"</s>"));
    }
    size_t exactTies=0; // structural ties decided by prefix bytes
    void cut(double sa, double la, double sb, double lb) {
        const double d=std::fabs(sa-sb);
        if(d>0 || la!=lb)minGap=std::min(minGap,d); else ++exactTies;
    }
    std::string decode(const std::vector<int8_t>& q, size_t frames, int exponent, size_t width) {
        using Pair=std::pair<double,double>;
        std::map<std::string,Pair> beams{{"",{0.0,-kInf}}};
        for(size_t t=0;t<frames;++t) {
            double x[29], top=-kInf, sum=0, lp[29];
            for(int c=0;c<29;++c) { x[c]=std::ldexp(double(q[t*29+c]),exponent); top=std::max(top,x[c]); }
            for(int c=0;c<29;++c)sum+=std::exp(x[c]-top);
            for(int c=0;c<29;++c)lp[c]=x[c]-top-std::log(sum);
            std::map<std::string,Pair> next;
            auto acc=[&](const std::string& prefix, bool blank, double v) {
                if(v==-kInf)return;
                auto it=next.emplace(prefix,Pair{-kInf,-kInf}).first;
                double& slot=blank ? it->second.first : it->second.second; slot=lse(slot,v);
            };
            // The repeat of the last symbol is exempt from char_prune (the
            // reading hw1lm.py documents); everything else non-blank is pruned.
            for(const auto& [prefix,pr]:beams) {
                const double total=lse(pr.first,pr.second);
                const int last=prefix.empty() ? -1 : cls(prefix.back());
                acc(prefix,true,total+lp[28]);
                if(last==0)acc(prefix,true,total+lp[0]);
                else if(last>0) { acc(prefix,false,pr.second+lp[last]); acc(prefix+sym(last),false,pr.first+lp[last]); }
                for(int c=0;c<28;++c) {
                    if(!(lp[c]>=double(spec.prune)) || c==last)continue;
                    if(c==0 && prefix.empty()) { acc(prefix,true,total+lp[c]); continue; }
                    acc(prefix+sym(c),false,total+lp[c]);
                }
            }
            std::vector<std::pair<double,std::string>> ranked;
            for(const auto& [prefix,pr]:next)ranked.push_back({lse(pr.first,pr.second)+lmOf(prefix),prefix});
            std::sort(ranked.begin(),ranked.end(),[](const auto& a, const auto& b) {
                return a.first!=b.first ? a.first>b.first : a.second<b.second; });
            if(ranked.size()>width)cut(ranked[width-1].first,lmOf(ranked[width-1].second),ranked[width].first,lmOf(ranked[width].second));
            beams.clear();
            for(size_t i=0;i<std::min(width,ranked.size());++i)beams[ranked[i].second]=next[ranked[i].second];
        }
        std::vector<std::pair<double,std::string>> ranked;
        for(const auto& [prefix,pr]:beams)ranked.push_back({lse(pr.first,pr.second)+finalLm(prefix),prefix});
        std::sort(ranked.begin(),ranked.end(),[](const auto& a, const auto& b) {
            return a.first!=b.first ? a.first>b.first : a.second<b.second; });
        if(ranked.size()>1)cut(ranked[0].first,finalLm(ranked[0].second),ranked[1].first,finalLm(ranked[1].second));
        std::string text=ranked[0].second;
        if(!text.empty() && text.back()==' ')text.pop_back();
        return text;
    }
};
}
