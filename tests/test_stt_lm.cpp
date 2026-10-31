// Host tests for the production HW1LM1 view, custom words and beam decoder
// (stt/stt_lm.cpp compiled unchanged, host SHA/allocation path). Every LM here
// is written by the test; the fixture parity check lives in
// test_stt_lm_parity.py. Randomised cases compare against the independent
// double-precision reference in stt_lm_testlib.h.
#include "stt_lm_testlib.h"
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <random>
#include <string>
#include <vector>

#define CHECK(x) do { if(!(x)) { std::fprintf(stderr,"%s:%d: CHECK(%s) failed\n",__FILE__,__LINE__,#x); std::abort(); } } while(0)

namespace lm=hw1::stt::lm;
using lmtest::Logits;
using lmtest::Spec;

namespace {
std::string hex(const uint8_t* h) { std::string s; char b[3]; for(int i=0;i<32;++i) { std::snprintf(b,3,"%02x",h[i]); s+=b; } return s; }
std::string sha(const std::vector<uint8_t>& v) { uint8_t h[32]; CHECK(lm::sha256(v.data(),v.size(),h)); return hex(h); }

void shaVectors() {
    // Portable host path; ESP-IDF builds use mbedTLS. Values from hashlib.
    std::vector<uint8_t> abc={'a','b','c'};
    CHECK(sha(abc)=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    const std::pair<size_t,const char*> cases[]={
        {0,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
        {3,"6ab0dba1f4f1dfbb37b4f9eeb092c09fca4900ad32bdcd147d8dde35d6c87c35"},
        {55,"e7313d333c272e639f790978283f9eb392e843d0f29b7016828bb1daa4aac70b"},
        {56,"4324d65f3c103567f5589c710bc08f8523f929a9272e3af36fc968e52abc6c27"},
        {63,"81c80242132f230c3bd41b3e63bbcff16107339549214a99614ff26664625055"},
        {64,"39e3d7b6b5d075d37d053ad89b24b41bef4f3c29760c84447cab3f3be1882241"},
        {65,"aacca6ff74fdbb296d165a45cecfa04e5127bc008770fbbdd48006f2d2fae95e"},
        {119,"9ce7368e4daf32341631b492e80359dc9f594b48453cd0dd5bf0b19279cc177e"},
        {120,"7836b787757e95e58b3ca5aec90b1b004e8deba1e50e9675af9cabf1a13a04b5"},
        {1000,"1e9bc38cbf860b9ec31918b065f9b52476c549a782e0e7990bed8ce3868d2371"}};
    for(const auto& c:cases) {
        std::vector<uint8_t> v(c.first); for(size_t i=0;i<v.size();++i)v[i]=uint8_t(i*7+3);
        CHECK(sha(v)==c.second);
    }
    uint8_t h[32]; CHECK(!lm::sha256(nullptr,1,h));
}

Spec scoring() {
    Spec s; s.alpha=0.75f; s.beta=1.5f; s.unk=-4.25f; s.prune=-7.5f; s.bonus=3.25f; s.beam=5;
    s.uni("</s>",-1200).uni("<s>",-32768,-200).uni("<unk>",-5000,-50)
     .uni("a",-1000,-300).uni("b",-1500,-200).uni("c",-2000,-100);
    s.bi("<s>","a",-500,-250).bi("a","b",-400,-150).bi("b","c",-700,0).bi("a","</s>",-900);
    s.tri("<s>","a","b",-100).tri("a","b","</s>",-50);
    return s;
}

void openAndScore() {
    const Spec s=scoring();
    auto blob=lmtest::build(s);
    lm::Lm m;
    CHECK(!m.valid() && m.find("a",1)<0 && m.score(lm::kNoWord,0,1)==lm::kInvalidScore);
    CHECK(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok && m.valid());
    CHECK(m.vocab()==6 && m.bigrams()==4 && m.trigrams()==2 && m.beamWidth()==5);
    CHECK(m.alpha()==0.75f && m.beta()==1.5f && m.unkLog10()==-4.25f && m.charPrune()==-7.5f && m.hotwordBonus()==3.25f);
    // Byte order: "</s>" < "<s>" < "<unk>" < "a" < "b" < "c"; id = index.
    const char* order[]={"</s>","<s>","<unk>","a","b","c"};
    for(int i=0;i<6;++i) { CHECK(m.find(order[i],std::strlen(order[i]))==i); CHECK(!std::strcmp(m.word(uint16_t(i)),order[i])); }
    CHECK(m.word(6)==nullptr && m.eos()==0 && m.bos()==1 && m.unk()==2);
    CHECK(m.find("",0)<0 && m.find("aa",2)<0 && m.find("<s",2)<0 && m.find("d",1)<0 && m.find("ab",1)==3);
    const uint16_t S=m.bos(), E=m.eos(), A=3, B=4, C=5, N=lm::kNoWord;
    CHECK(m.score(N,S,A)==-500);          // bigram present
    CHECK(m.score(N,S,B)==-200-1500);     // backoff1(<s>) + p1(b)
    CHECK(m.score(S,A,B)==-100);          // trigram present
    CHECK(m.score(A,B,C)==-150-700);      // backoff2(a,b) + bigram(b,c)
    CHECK(m.score(B,C,A)==0-100-1000);    // bigram(b,c) backoff 0; backoff1(c) + p1(a)
    CHECK(m.score(C,A,B)==0-400);         // (c,a) absent: backoff2 = 0, then bigram(a,b)
    CHECK(m.score(B,A,C)==0-300-2000);    // full backoff chain
    CHECK(m.score(A,B,E)==-50 && m.score(N,A,E)==-900 && m.score(S,A,E)==-250-900);
    CHECK(m.score(N,6,A)==lm::kInvalidScore && m.score(6,A,B)==lm::kInvalidScore && m.score(N,A,6)==lm::kInvalidScore);
    // Decoder values: doubles summed per term in the host reference's order.
    CHECK(m.log10(N,S,A)==-500/1000.0 && m.log10(S,A,B)==-100/1000.0);
    CHECK(m.log10(N,S,B)==-200/1000.0+-1500/1000.0);
    CHECK(m.log10(A,B,C)==-150/1000.0+-700/1000.0);
    CHECK(m.log10(B,A,C)==0.0+(-300/1000.0+-2000/1000.0));
    CHECK(std::isnan(m.log10(N,6,A)) && std::isnan(m.log10(6,A,B)));
}

lm::LoadStatus load(const std::vector<uint8_t>& blob) { lm::Lm m; const auto r=m.open(blob.data(),blob.size()); CHECK(m.valid()==(r==lm::LoadStatus::Ok)); return r; }

void corrupted() {
    using S=lm::LoadStatus;
    const Spec base=scoring();
    const auto good=lmtest::build(base);
    const auto at=lmtest::offsets(good);
    CHECK(load(good)==S::Ok);
    lm::Lm m; CHECK(m.open(nullptr,0)==S::InvalidArgument);
    auto mutate=[&](auto edit, bool reseal=true) { auto b=good; edit(b); if(reseal)lmtest::reseal(b); return load(b); };
    CHECK(load(std::vector<uint8_t>(good.begin(),good.begin()+95))==S::BadSize);
    CHECK(load(std::vector<uint8_t>(good.begin(),good.end()-1))==S::BadSize);
    { auto b=good; b.push_back(0); CHECK(load(b)==S::BadSize); }
    CHECK(mutate([](auto& b) { b[0]='X'; })==S::BadMagic);
    CHECK(mutate([](auto& b) { b[7]=1; })==S::BadMagic);
    CHECK(mutate([](auto& b) { lmtest::set32(b,8,2); })==S::BadVersion);
    CHECK(mutate([](auto& b) { lmtest::set32(b,48,uint32_t(b.size()+4)); })==S::BadSize);
    CHECK(mutate([](auto& b) { lmtest::set32(b,12,2); })==S::BadHeader);
    CHECK(mutate([](auto& b) { lmtest::set32(b,12,65536); })==S::BadHeader);
    CHECK(mutate([](auto& b) { lmtest::set32(b,40,0); })==S::BadHeader);
    CHECK(mutate([](auto& b) { lmtest::set32(b,40,65); })==S::BadHeader);
    CHECK(mutate([](auto& b) { lmtest::set32(b,24,0); })==S::BadHeader);
    CHECK(mutate([](auto& b) { lmtest::set32(b,28,0x7fc00000u); })==S::BadHeader);   // NaN alpha
    CHECK(mutate([](auto& b) { lmtest::set32(b,44,0xff800000u); })==S::BadHeader);   // -inf prune
    CHECK(mutate([](auto& b) { b[63]=1; })==S::BadHeader);
    // Section counts that run past (or stop short of) the trailer.
    CHECK(mutate([](auto& b) { lmtest::set32(b,16,lmtest::get32(b,16)+1); })==S::BadLayout);
    CHECK(mutate([](auto& b) { lmtest::set32(b,20,0xffffffffu); })==S::BadLayout);
    CHECK(mutate([](auto& b) { lmtest::set32(b,24,0xfffffff0u); })==S::BadLayout);
    CHECK(mutate([](auto& b) { lmtest::set32(b,12,65535); })==S::BadLayout);
    CHECK(mutate([](auto& b) { lmtest::set32(b,20,lmtest::get32(b,20)-1); })==S::BadLayout);
    // Strings are 21 bytes here, so three padding bytes precede the bigrams.
    const uint32_t sb=lmtest::get32(good,24);
    CHECK(sb==21 && at.bigram-(at.strings+sb)==3);
    CHECK(mutate([&](auto& b) { b[at.bigram-1]=1; })==S::BadPadding);
    // Integrity: any unsealed byte change, including the trailer itself.
    CHECK(mutate([&](auto& b) { b[at.unigram]^=1; },false)==S::BadChecksum);
    CHECK(mutate([&](auto& b) { b[at.trigram+7]^=0x80; },false)==S::BadChecksum);
    CHECK(mutate([&](auto& b) { b[at.digest]^=1; },false)==S::BadChecksum);
    // Structure behind a valid digest.
    CHECK(mutate([&](auto& b) { b[at.strings+sb-1]='x'; })==S::BadStrings);        // last string byte not NUL
    CHECK(mutate([&](auto& b) { lmtest::set32(b,at.offsets+4,sb); })==S::BadStrings);
    CHECK(mutate([&](auto& b) { const uint32_t x=lmtest::get32(b,at.offsets+12), y=lmtest::get32(b,at.offsets+16);
                                lmtest::set32(b,at.offsets+12,y); lmtest::set32(b,at.offsets+16,x); })==S::Unsorted);
    CHECK(mutate([&](auto& b) { lmtest::set32(b,at.offsets+16,lmtest::get32(b,at.offsets+12)); })==S::Unsorted); // duplicate
    CHECK(mutate([&](auto& b) { b[at.strings+15]='b'; })==S::Unsorted);            // "a" -> "b" duplicates "b"
    CHECK(mutate([&](auto& b) { std::swap_ranges(b.begin()+at.bigram,b.begin()+at.bigram+8,b.begin()+at.bigram+8); })==S::Unsorted);
    CHECK(mutate([&](auto& b) { std::copy(b.begin()+at.bigram,b.begin()+at.bigram+4,b.begin()+at.bigram+8); })==S::Unsorted);
    CHECK(mutate([&](auto& b) { std::swap_ranges(b.begin()+at.trigram,b.begin()+at.trigram+8,b.begin()+at.trigram+8); })==S::Unsorted);
    CHECK(mutate([&](auto& b) { b[at.bigram+24+2]=6; })==S::BadWordId);             // last bigram's w2 = V
    CHECK(mutate([&](auto& b) { b[at.trigram+8+4]=0xff; })==S::BadWordId);
    Spec missing=base; missing.unigrams.erase("<unk>");
    auto noUnk=lmtest::build(missing); CHECK(load(noUnk)==S::MissingSpecial);
    // A failed open empties a previously valid view.
    lm::Lm view; CHECK(view.open(good.data(),good.size())==S::Ok);
    auto bad=good; bad[0]='X'; CHECK(view.open(bad.data(),bad.size())==S::BadMagic && !view.valid());
    for(auto s:{S::Ok,S::BadSize,S::BadChecksum,S::MissingSpecial})CHECK(std::strlen(lm::describe(s))>1);
}

void customWords() {
    auto words=std::make_unique<lm::CustomWords>();
    const std::string text=
        "Kubernetes\r\n  gRPC \nnew york\n\n'twas\ndon't\n''word''\nrock'n'roll\no''clock\n'\nx'\ncaf\xc3\xa9\n"
        "na\xc3\xafve\ne-mail\nABC123\n  '  hello  '  \nit's'\n\tTab\t\nkubernetes\nKUBERNETES\n"
        "abcdefghijklmnopqrstuvwxyzabcde\nabcdefghijklmnopqrstuvwxyzabcdef\nlast";
    CHECK(words->parse(text.data(),text.size())==15);
    const char* expected[]={"'word'","abc","abcdefghijklmnopqrstuvwxyzabcde","caf","don't","grpc","hello","it's",
                            "kubernetes","last","o''clock","rock'n'roll","tab","twas","x"};
    CHECK(words->size()==15);
    std::vector<std::string> got; for(size_t i=0;i<words->size();++i)got.push_back(words->word(i));
    CHECK(std::is_sorted(got.begin(),got.end()));
    for(const char* w:expected)CHECK(words->contains(w,std::strlen(w)));
    CHECK(!words->contains("new",3) && !words->contains("york",4) && !words->contains("e",1) && !words->contains("mail",4));
    CHECK(!words->contains("naive",5) && !words->contains("na",2) && !words->contains("kubernete",9) && !words->contains("",0));
    CHECK(!words->contains("abcdefghijklmnopqrstuvwxyzabcdef",32) && words->word(words->size())==nullptr);
    CHECK(words->contains("abc",3)); // "ABC123" -> "abc"
    // Capacity: first 256 distinct words win; duplicates never consume a slot.
    std::string many;
    for(int i=0;i<300;++i) { std::string w; for(int k=i;;k/=26) { w.push_back(char('a'+k%26)); if(k<26)break; } many+=w+"\n"+w+"\n"; }
    CHECK(words->parse(many.data(),many.size())==256 && words->contains("a",1) && words->contains("vj",2));
    CHECK(!words->contains("wj",2)); // word 256 (0-based) is rejected
    // Python str.splitlines() boundaries and str.lower() on UTF-8 (values
    // from hw1lm.parse_custom_words): CR, VT, FF, FS, U+2028, U+0085 split;
    // U+212A lowers to k; U+0130 lowers to i + combining dot (two words).
    std::string lines="alpha\rbeta\x0bgamma\x0c" "delta\x1c" "epsilon\xe2\x80\xa8zeta\xc2\x85" "eta\r\n"
                      "\xc4\xb0stanbul\n\xe2\x84\xaa" "elvin\n";
    for(int i=0;i<300;++i)lines+="' ";
    lines+="x\n\xe2\x80 bad\n\xff\xfeok\n\xe0\x82\x85overlong";
    CHECK(words->parse(lines.data(),lines.size())==12);
    for(const char* w:{"alpha","bad","beta","delta","epsilon","eta","gamma","kelvin","ok","overlong","x","zeta"})
        CHECK(words->contains(w,std::strlen(w)));
    CHECK(!words->contains("stanbul",7) && !words->contains("i",1));
    CHECK(words->parse(nullptr,5)==0 && words->size()==0);
    CHECK(words->parse("solo",4)==1 && words->contains("solo",4));
}

std::vector<uint8_t> decodeSpecBlob() {
    Spec s; s.alpha=1; s.beta=0; s.unk=-6; s.prune=-5; s.bonus=20; s.beam=8;
    s.uni("</s>",-1000).uni("<s>",-32768,-200).uni("<unk>",-6000,-1000)
     .uni("cat",-1500,-300).uni("dog",-3000,-300).uni("dot",-1000,-300).uni("hello",-2000,-300);
    s.bi("<unk>","dog",-100,0);
    return lmtest::build(s);
}
struct Decoded { lm::DecodeStatus status; std::string text; };
Decoded run(const lm::Lm& m, const Logits& x, const lm::CustomWords* words=nullptr, size_t capacity=512,
            size_t beam=0, const lm::DecodeControl& control={}, float strength=1.0f, lm::DecodeStats* stats=nullptr) {
    std::vector<char> text(capacity+1,'#');
    const auto status=lm::decode(x.q.data(),x.frames(),-2,m,words,text.data(),capacity,control,beam,stats,strength);
    CHECK(std::memchr(text.data(),0,capacity));
    return {status,text.data()};
}

void decodeBasics() {
    const auto blob=decodeSpecBlob(); lm::Lm m; CHECK(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
    using D=lm::DecodeStatus;
    auto r=run(m,Logits().pattern("______")); CHECK(r.status==D::Ok && r.text.empty());
    { char t[4]="xx"; CHECK(lm::decode(nullptr,0,-2,m,nullptr,t,sizeof(t))==D::Ok && !t[0]); }
    CHECK(run(m,Logits().pattern("_cc__a_tt__")).text=="cat");
    CHECK(run(m,Logits().pattern("cat")).text=="cat");
    CHECK(run(m,Logits().pattern("hh_e_ll_ll_oo__")).text=="hello");
    CHECK(run(m,Logits().pattern("bb_e_llll_oo")).text=="belo");  // both OOV: acoustics decide
    // In-vocab "hello" is worth one blank at -10 nats over OOV "helo".
    CHECK(run(m,Logits().pattern("hh_e_llll_oo")).text=="hello");
    // Leading and repeated spaces never create prefixes; trailing space is not emitted.
    CHECK(run(m,Logits().pattern("  __cc_a_t__  __  d_oo_g  ")).text=="cat dog");
    CHECK(run(m,Logits().pattern(" ")).text.empty());
    // Capacity keeps the leading bytes and reports truncation.
    const Logits two=Logits().pattern("cat dog");
    r=run(m,two,nullptr,8); CHECK(r.status==D::Ok && r.text=="cat dog");
    r=run(m,two,nullptr,7); CHECK(r.status==D::OutputTooSmall && r.text=="cat do");
    r=run(m,two,nullptr,4); CHECK(r.status==D::OutputTooSmall && r.text=="cat");
    r=run(m,two,nullptr,1); CHECK(r.status==D::OutputTooSmall && r.text.empty());
    // A >255-letter partial word saturates to OOV without overrunning.
    std::string longWord; for(int i=0;i<300;++i)longWord.push_back(i%2 ? 'b' : 'a');
    r=run(m,Logits().pattern(longWord.c_str())); CHECK(r.status==D::Ok && r.text==longWord);
    r=run(m,Logits().pattern((longWord+" cat").c_str()),nullptr,700); CHECK(r.status==D::Ok && r.text==longWord+" cat");
    // Two OOV words cost more LM than one blank frame: the search joins them.
    r=run(m,Logits().pattern((longWord+" "+longWord).c_str()),nullptr,700); CHECK(r.status==D::Ok && r.text==longWord+longWord);
    // Beam 1 is still a valid search; determinism across calls and widths.
    CHECK(run(m,Logits().pattern("_cc__a_tt__"),nullptr,512,1).text=="cat");
    CHECK(run(m,two,nullptr,512,64).text=="cat dog");
}

void decodeLanguageModel() {
    const auto blob=decodeSpecBlob(); lm::Lm m; CHECK(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
    // Acoustics prefer "kat" by 0.25 nats; the LM (cat known, kat OOV) wins.
    Logits ck; ck.frame({{'c',30},{'k',31}}); ck.pattern("_a_t__");
    CHECK(run(m,ck).text=="cat");
    Spec plain; plain.alpha=0; plain.beta=0; plain.prune=-5;
    plain.uni("</s>",0).uni("<s>",0).uni("<unk>",0);
    auto flat=lmtest::build(plain); lm::Lm acoustic; CHECK(acoustic.open(flat.data(),flat.size())==lm::LoadStatus::Ok);
    CHECK(run(acoustic,ck).text=="kat");
    // Hotword bonus (20 nats) outweighs the OOV penalty; unlisted/empty lists do not.
    lm::CustomWords hot; CHECK(hot.parse("Kat\n",4)==1);
    CHECK(run(m,ck,&hot).text=="kat");
    lm::CustomWords other; CHECK(other.parse("dog\n",4)==1);
    CHECK(run(m,ck,&other).text=="cat");
    lm::CustomWords none; CHECK(run(m,ck,&none).text=="cat");
    // OOV words score unk_log10 and enter the context as <unk>: bigram
    // (<unk>, dog) must beat the acoustically preferred, unigram-likelier "dot".
    Logits unk; unk.pattern("_zz_q_  _dd_oo_"); unk.frame({{'g',30},{'t',31}}); unk.pattern("__");
    CHECK(run(m,unk).text=="zq dog");
    Logits known; known.pattern("_cc_a_tt_  _dd_oo_"); known.frame({{'g',30},{'t',31}}); known.pattern("__");
    CHECK(run(m,known).text=="cat dot");
    // Exact ties break by prefix bytes ascending: ' (0x27) before a (0x61),
    // although class order would put a (1) before ' (27).
    Spec tie; tie.alpha=1; tie.beta=5; tie.unk=-0.5f; tie.prune=-5;
    tie.uni("</s>",-100).uni("<s>",0).uni("<unk>",-100);
    auto tb=lmtest::build(tie); lm::Lm tl; CHECK(tl.open(tb.data(),tb.size())==lm::LoadStatus::Ok);
    CHECK(run(tl,Logits().frame({{'x',40},{'q',40}})).text=="q");
    CHECK(run(tl,Logits().frame({{'a',40},{'\'',40}})).text=="'");
    CHECK(run(tl,Logits().frame({{'b',40},{'a',40}}).pattern("__").frame({{'z',40},{'y',40}})).text=="ay");
}

void decodeContextIsolation() {
    const auto blob=decodeSpecBlob(), before=blob;
    const auto beforeHash=sha(blob);
    lm::Lm m, fresh;
    CHECK(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
    CHECK(fresh.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
    lm::DecodeStats stats;
    CHECK(stats.startHistoryWords==UINT8_MAX && stats.endHistoryWords==UINT8_MAX);
    auto observed=[&](const Logits& x, const char* expected, uint8_t history) {
        const auto r=run(m,x,nullptr,512,0,{},1.0f,&stats);
        if(r.text!=expected)std::fprintf(stderr,"context fixture: expected '%s', got '%s'\n",expected,r.text.c_str());
        CHECK(r.status==lm::DecodeStatus::Ok && r.text==expected);
        CHECK(stats.startHistoryWords==0 && stats.endHistoryWords==history);
        CHECK(stats.frames==x.frames() && stats.workspaceBytes==lm::workspace_bytes(x.frames(),m.beamWidth()));
        CHECK(run(m,x).text==r.text); // collecting metadata cannot change the chosen text
    };
    Logits ambiguous; ambiguous.pattern("_dd_oo_"); ambiguous.frame({{'g',30},{'t',31}}); ambiguous.pattern("__");
    Logits joined; joined.pattern("_zz_q_  _dd_oo_"); joined.frame({{'g',30},{'t',31}}); joined.pattern("__");
    CHECK(run(fresh,ambiguous).text=="dot");
    // The same LM changes dog/dot based on context within one decode. Its
    // ending <unk> or known-word history must not leak into a following call.
    for(int i=0;i<3;++i) {
        observed(Logits().pattern("_zz_q_"),"zq",1);
        observed(ambiguous,"dot",1);
        observed(joined,"zq dog",2);
        observed(ambiguous,"dot",1);
        observed(Logits().pattern("cat"),"cat",1);
        observed(ambiguous,"dot",1);
    }
    observed(Logits(),"",0);
    observed(Logits().pattern("______"),"",0);
    observed(Logits().pattern("cat "),"cat",1);
    observed(Logits().pattern("cat dog cat"),"cat dog cat",2);
    // End context is from the full winner, not the truncated display string.
    const auto cut=run(m,Logits().pattern("cat dog"),nullptr,4,0,{},1.0f,&stats);
    CHECK(cut.status==lm::DecodeStatus::OutputTooSmall && cut.text=="cat");
    CHECK(stats.startHistoryWords==0 && stats.endHistoryWords==2);
    char text[16]="stale";
    CHECK(lm::decode(nullptr,1,-2,m,nullptr,text,sizeof(text),{},0,&stats)==lm::DecodeStatus::InvalidArgument);
    CHECK(!text[0] && stats.startHistoryWords==UINT8_MAX && stats.endHistoryWords==UINT8_MAX);
    struct Counter { int calls=0, cancelAt=0; static bool poll(void* c) { auto& s=*static_cast<Counter*>(c); return ++s.calls>=s.cancelAt; } };
    Counter beforeStart{0,1};
    CHECK(run(m,ambiguous,nullptr,512,0,{&beforeStart,Counter::poll},1.0f,&stats).status==lm::DecodeStatus::Cancelled);
    CHECK(stats.startHistoryWords==UINT8_MAX && stats.endHistoryWords==UINT8_MAX && !stats.workspaceBytes);
    Logits longer; for(int i=0;i<8;++i)longer.pattern("_cc_a_t__ ");
    Counter during{0,3};
    CHECK(run(m,longer,nullptr,512,0,{&during,Counter::poll},1.0f,&stats).status==lm::DecodeStatus::Cancelled);
    CHECK(stats.startHistoryWords==0 && stats.endHistoryWords==UINT8_MAX && stats.workspaceBytes);
    observed(ambiguous,"dot",1); // a cancelled search cannot contaminate the next call either
    CHECK(blob==before && sha(blob)==beforeHash && load(blob)==lm::LoadStatus::Ok);
    std::puts("stt_lm context: same-Lm consecutive calls start fresh; within-call context, bounded history, unavailable stages and immutable LM passed");
}

void decodeStrength() {
    // Controlled conflict: acoustics favor b by 2 nats; the LM favors a by
    // ln(10). Full strength wins with a, 0.75 lets the acoustics choose b.
    Spec spec; spec.alpha=1; spec.beta=0; spec.bonus=0; spec.unk=-5; spec.prune=-8;
    spec.uni("</s>",0).uni("<s>",0).uni("<unk>",-5000).uni("a",0).uni("b",-1000).uni("ab",0);
    Logits conflict; conflict.frame({{'a',30},{'b',38}},-128);
    const auto blob=lmtest::build(spec), before=blob;
    const auto beforeHash=sha(blob);
    lm::Lm m; CHECK(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
    char implicit[32], explicitOne[32]; lm::DecodeStats oldStats, oneStats;
    CHECK(lm::decode(conflict.q.data(),1,-2,m,nullptr,implicit,sizeof(implicit),{},0,&oldStats)==lm::DecodeStatus::Ok);
    CHECK(lm::decode(conflict.q.data(),1,-2,m,nullptr,explicitOne,sizeof(explicitOne),{},0,&oneStats,1.0f)==lm::DecodeStatus::Ok);
    CHECK(!std::strcmp(implicit,"a") && !std::strcmp(implicit,explicitOne));
    CHECK(std::tie(oldStats.frames,oldStats.beam,oldStats.nodes,oldStats.candidates,oldStats.completions,oldStats.workspaceBytes,
                   oldStats.startHistoryWords,oldStats.endHistoryWords)==
          std::tie(oneStats.frames,oneStats.beam,oneStats.nodes,oneStats.candidates,oneStats.completions,oneStats.workspaceBytes,
                   oneStats.startHistoryWords,oneStats.endHistoryWords));
    CHECK(run(m,conflict,nullptr,512,0,{},0.75f).text=="b");
    CHECK(run(m,conflict,nullptr,512,0,{},0.0f).text=="b");
    CHECK(run(m,conflict).text=="a"); // lower-strength calls do not mutate cached policy
    CHECK(blob==before && sha(blob)==beforeHash && load(blob)==lm::LoadStatus::Ok);
    CHECK(m.alpha()==spec.alpha && m.beta()==spec.beta && m.hotwordBonus()==spec.bonus);

    // Custom-word and insertion scores must scale with alpha. Holding either
    // fixed would retain an independent push toward words after reducing LM.
    spec.alpha=0; spec.bonus=2.25f;
    const auto hotBlob=lmtest::build(spec); lm::Lm hotLm;
    CHECK(hotLm.open(hotBlob.data(),hotBlob.size())==lm::LoadStatus::Ok);
    lm::CustomWords hot; CHECK(hot.parse("a\n",2)==1);
    CHECK(run(hotLm,conflict,&hot).text=="a");
    CHECK(run(hotLm,conflict,&hot,512,0,{},0.75f).text=="b");
    CHECK(run(hotLm,conflict,&hot,512,0,{},0.0f).text=="b");

    spec.bonus=0; spec.beta=2.25f;
    const auto wordBlob=lmtest::build(spec); lm::Lm wordLm;
    CHECK(wordLm.open(wordBlob.data(),wordBlob.size())==lm::LoadStatus::Ok);
    Logits spacing; spacing.pattern("a").frame({{' ',30},{'_',38}},-128).pattern("b");
    CHECK(run(wordLm,spacing).text=="a b");
    CHECK(run(wordLm,spacing,nullptr,512,0,{},0.75f).text=="ab");
    CHECK(run(wordLm,spacing,nullptr,512,0,{},0.0f).text=="ab");

    for(float bad:{-0.01f,1.01f,std::numeric_limits<float>::infinity(),
                   -std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}) {
        char text[8]="stale"; lm::DecodeStats stats; stats.frames=99;
        CHECK(lm::decode(conflict.q.data(),1,-2,m,nullptr,text,sizeof(text),{},0,&stats,bad)==lm::DecodeStatus::InvalidArgument);
        CHECK(!text[0] && !stats.frames && blob==before && m.alpha()==1.0f);
    }
    std::puts("stt_lm strength: default/1 parity, 0.75 acoustic conflict, coupled word/hotword scores, invalid factors and immutable LM passed");
}

void decodeControlAndArguments() {
    const auto blob=decodeSpecBlob(); lm::Lm m; CHECK(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
    using D=lm::DecodeStatus;
    Logits x; for(int i=0;i<20;++i)x.pattern("_cc__a_tt__ ");
    struct Counter { int calls=0, cancelAt=0; static bool poll(void* c) { auto& s=*static_cast<Counter*>(c); return ++s.calls>=s.cancelAt; } };
    Counter now{0,1}; auto r=run(m,x,nullptr,512,0,{&now,Counter::poll}); CHECK(r.status==D::Cancelled && r.text.empty() && now.calls==1);
    Counter later{0,4}; r=run(m,x,nullptr,512,0,{&later,Counter::poll}); CHECK(r.status==D::Cancelled && r.text.empty() && later.calls==4);
    Counter never{0,1000}; r=run(m,x,nullptr,512,0,{&never,Counter::poll}); CHECK(r.status==D::Ok);
    CHECK(never.calls==2+int((x.frames()+31)/32)); // pre-check, one per 32 frames, and at finish
    char t[8]="x";
    CHECK(lm::decode(x.q.data(),x.frames(),-2,m,nullptr,nullptr,8)==D::InvalidArgument);
    CHECK(lm::decode(x.q.data(),x.frames(),-2,m,nullptr,t,0)==D::InvalidArgument && t[0]=='x');
    CHECK(lm::decode(nullptr,1,-2,m,nullptr,t,8)==D::InvalidArgument && !t[0]);
    CHECK(lm::decode(x.q.data(),x.frames(),-2,m,nullptr,t,8,{},65)==D::InvalidArgument);
    CHECK(lm::decode(x.q.data(),x.frames(),31,m,nullptr,t,8)==D::InvalidArgument);
    std::vector<int8_t> huge((lm::kMaxFrames+1)*29,0);
    CHECK(lm::decode(huge.data(),lm::kMaxFrames+1,-2,m,nullptr,t,8)==D::InvalidArgument);
    lm::Lm empty; CHECK(lm::decode(x.q.data(),x.frames(),-2,empty,nullptr,t,8)==D::InvalidArgument);
    // Footprint formula documented in stt_lm.h (16-byte aligned sections).
    for(size_t frames:{size_t(0),size_t(1),size_t(1000),size_t(1500)})for(size_t beam:{size_t(1),size_t(16),size_t(32),size_t(64)}) {
        const size_t nodes=frames*beam+1; size_t table=1; while(table<2*nodes)table<<=1;
        size_t memo=256; while(memo<2*frames)memo<<=1; if(memo>8192)memo=8192;
        const size_t sum=40*nodes+4*table+44*beam+48*29*beam+512+128+4096+34*memo;
        CHECK(lm::workspace_bytes(frames,beam)>=sum && lm::workspace_bytes(frames,beam)<=sum+13*16);
    }
    CHECK(lm::workspace_bytes(1,0)==0 && lm::workspace_bytes(1,65)==0 && lm::workspace_bytes(lm::kMaxFrames+1,1)==0);
}

// Random small cases against the independent reference. Inactive classes sit
// at -32 nats (always pruned); active ones cover blank, space, a, b and '.
void randomisedOracle(float strength=1.0f) {
    std::mt19937 rng(1234);
    auto uniform=[&](int lo, int hi) { return std::uniform_int_distribution<int>(lo,hi)(rng); };
    const char* vocab[]={"a","b","ab","ba","aab","b'a","bb"};
    const int active[]={0,1,2,27,28};
    size_t compared=0, skipped=0, ties=0;
    for(int n=0;n<3000;++n) {
        // Continuous weights: exact ties then come from equal logits (structural),
        // rarely from coincidences; every 5th case uses round values to stress those.
        auto real=[&](double lo, double hi) { return float(n%5 ? std::uniform_real_distribution<double>(lo,hi)(rng) : uniform(int(lo*10),int(hi*10))/10.0); };
        Spec s; s.alpha=real(0,2); s.beta=real(-2,2); s.unk=-real(0,5);
        s.prune=-float(uniform(2,9)); s.bonus=real(0,4); s.beam=uint32_t(uniform(1,6)); if(n%7==0)s.beam=16;
        s.uni("</s>",-uniform(0,3000),0).uni("<s>",-uniform(0,3000),-uniform(0,800)).uni("<unk>",-uniform(0,5000),-uniform(0,800));
        for(const char* w:vocab)if(uniform(0,3))s.uni(w,-uniform(0,4000),-uniform(0,1000));
        std::vector<std::string> known; for(const auto& u:s.unigrams)known.push_back(u.first);
        for(int k=uniform(0,10);k>0;--k)s.bi(known[size_t(uniform(0,int(known.size())-1))],known[size_t(uniform(0,int(known.size())-1))],-uniform(0,3000),-uniform(0,800));
        for(int k=uniform(0,10);k>0;--k)s.tri(known[size_t(uniform(0,int(known.size())-1))],known[size_t(uniform(0,int(known.size())-1))],known[size_t(uniform(0,int(known.size())-1))],-uniform(0,3000));
        const auto blob=lmtest::build(s); lm::Lm m; CHECK(m.open(blob.data(),blob.size())==lm::LoadStatus::Ok);
        lmtest::Reference ref{s,{}}; ref.strength=strength;
        lm::CustomWords words; std::string list;
        for(const char* w:{"ab","bb","a'b","ba"})if(!uniform(0,2)) { list+=w; list+="\n"; ref.hot.insert(w); }
        words.parse(list.data(),list.size());
        const int exponent=uniform(-3,-1);
        Logits x; const int frames=uniform(0,24);
        for(int t=0;t<frames;++t) { int8_t* f=x.add(-128); for(int c:active)f[c]=int8_t(uniform(-60,60)); if(!uniform(0,4))f[1]=f[2]; }
        // Zero strength must equal the existing acoustic-only beam path,
        // including its tie behavior, without changing the original LM view.
        if(strength==1.0f) {
            Spec flat=s; flat.alpha=flat.beta=flat.bonus=0;
            const auto flatBlob=lmtest::build(flat); lm::Lm flatLm;
            CHECK(flatLm.open(flatBlob.data(),flatBlob.size())==lm::LoadStatus::Ok);
            char scaledZero[64], originalZero[64];
            CHECK(lm::decode(x.q.data(),x.frames(),exponent,m,&words,scaledZero,sizeof(scaledZero),{},0,nullptr,0.0f)==lm::DecodeStatus::Ok);
            CHECK(lm::decode(x.q.data(),x.frames(),exponent,flatLm,&words,originalZero,sizeof(originalZero))==lm::DecodeStatus::Ok);
            CHECK(!std::strcmp(scaledZero,originalZero));
        }
        const std::string expected=ref.decode(x.q,x.frames(),exponent,s.beam);
        if(ref.minGap<1e-6) { ++skipped; continue; } // float log1p(exp) error is <1e-7
        char text[64];
        const auto status=lm::decode(x.q.data(),x.frames(),exponent,m,&words,text,sizeof(text),{},0,nullptr,strength);
        CHECK(status==lm::DecodeStatus::Ok);
        if(expected!=text) { std::fprintf(stderr,"case %d: expected '%s' got '%s'\n",n,expected.c_str(),text); std::abort(); }
        ++compared; ties+=ref.exactTies ? 1 : 0;
    }
    std::printf("stt_lm oracle strength %.2f: %zu compared (%zu decided exact ties by prefix bytes), %zu skipped:"
                " a rank decision within 1e-6 nats that is not a structural tie\n",double(strength),compared,ties,skipped);
    CHECK(compared>=2000 && ties>=100);
}
}

int main() {
    shaVectors();
    openAndScore();
    corrupted();
    customWords();
    decodeBasics();
    decodeLanguageModel();
    decodeContextIsolation();
    decodeStrength();
    decodeControlAndArguments();
    randomisedOracle();
    randomisedOracle(0.75f);
    std::printf("stt_lm tests passed\n");
}
