#include "stt_lm.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <limits>
#include <new>
#if defined(ESP_PLATFORM)
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "sdkconfig.h"
// The shared exp table below is placed with EXT_RAM_BSS_ATTR; without this option that
// attribute is empty and the 4 KB would silently land in internal RAM.
#if !CONFIG_SPIRAM_ALLOW_BSS_SEG_EXTERNAL_MEMORY
#error "stt_lm.cpp needs CONFIG_SPIRAM_ALLOW_BSS_SEG_EXTERNAL_MEMORY (exp table in PSRAM)"
#endif
#else
#define EXT_RAM_BSS_ATTR
#endif
namespace hw1::stt::lm {
namespace {
constexpr size_t kHeaderBytes=64, kShaBytes=32, kLocal=128, kYieldFrames=32;
#if defined(ESP_PLATFORM)
constexpr int64_t kYieldBlockUs=250000;
#endif
constexpr uint32_t kEmpty=0xffffffffu;
constexpr double kNegInf=-std::numeric_limits<double>::infinity();
constexpr double kLn10=2.302585092994045684017991454684364208;
constexpr char kVocab[]=" abcdefghijklmnopqrstuvwxyz'";
static_assert(sizeof(kVocab)==kClasses && kBlank==kClasses-1 && 2*kMaxBeam<=kLocal);
uint16_t u16(const uint8_t* p) { return uint16_t(p[0]|p[1]<<8); }
int32_t i16(const uint8_t* p) { return int16_t(u16(p)); }
uint32_t u32(const uint8_t* p) { return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24; }
float f32(const uint8_t* p) { const uint32_t v=u32(p); float f; std::memcpy(&f,&v,4); return f; }
uint64_t align4(uint64_t v) { return (v+3)&~uint64_t(3); }
// Byte order of a stored NUL-terminated word against a length-bounded key.
int compareWord(const char* stored, const char* key, size_t length) {
    for(size_t i=0;i<length;++i) {
        const uint8_t a=uint8_t(stored[i]), b=uint8_t(key[i]);
        if(a!=b)return a<b?-1:1;
        if(!a)return -1;
    }
    return stored[length]?1:0;
}
#if !defined(ESP_PLATFORM)
constexpr uint32_t kRound[64]={
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
uint32_t ror(uint32_t x, int n) { return x>>n|x<<(32-n); }
void shaBlock(uint32_t* h, const uint8_t* p) {
    uint32_t w[64];
    for(int i=0;i<16;++i)w[i]=uint32_t(p[4*i])<<24|uint32_t(p[4*i+1])<<16|uint32_t(p[4*i+2])<<8|p[4*i+3];
    for(int i=16;i<64;++i)w[i]=w[i-16]+(ror(w[i-15],7)^ror(w[i-15],18)^(w[i-15]>>3))+w[i-7]
                                   +(ror(w[i-2],17)^ror(w[i-2],19)^(w[i-2]>>10));
    uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],k=h[7];
    for(int i=0;i<64;++i) {
        const uint32_t t1=k+(ror(e,6)^ror(e,11)^ror(e,25))+((e&f)^(~e&g))+kRound[i]+w[i];
        const uint32_t t2=(ror(a,2)^ror(a,13)^ror(a,22))+((a&b)^(a&c)^(b&c));
        k=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=k;
}
#endif
void* allocate(size_t bytes) {
#if defined(ESP_PLATFORM)
    return heap_caps_aligned_alloc(16,bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
#else
    return ::operator new(bytes,std::nothrow);
#endif
}
void release(void* p) {
#if defined(ESP_PLATFORM)
    heap_caps_free(p);
#else
    ::operator delete(p);
#endif
}
// Every kYieldFrames frames (after the cancel poll): like the network's y1
// rule, block for one tick only when kYieldBlockUs passed since the last
// block (IDLE and the priority-1 loop task still run several times a
// second), otherwise a non-blocking yield to equal-priority tasks.
#if defined(ESP_PLATFORM)
void yieldTask(int64_t& lastBlockUs) {
    if(esp_timer_get_time()-lastBlockUs>=kYieldBlockUs) { vTaskDelay(1); lastBlockUs=esp_timer_get_time(); }
    else taskYIELD();
}
#endif
// common.py::normalize_text over one line as a streaming transducer: lower,
// '-' and non-alphabet to space, then the leftmost non-overlapping regex
// "\s+'|'\s+" -> ' ' on the space-padded line, then collapse/strip. finish()
// accepts exactly one resulting word of 1..31 bytes.
class LineWord {
 public:
    void feed(char c) { // c is a-z, apostrophe or space
        switch(state_) {
            case Normal: if(c==' ')state_=Run; else if(c=='\'')state_=Apos; else emit(c); break;
            case Run: if(c==' ')break; emit(' '); if(c!='\'')emit(c); state_=Normal; break; // run+' matched
            case Apos:
                if(c==' ') { emit(' '); state_=Skip; }            // '+run matched
                else if(c=='\'')emit('\'');
                else { emit('\''); emit(c); state_=Normal; }
                break;
            case Skip: if(c==' ')break; if(c=='\'')state_=Apos; else { emit(c); state_=Normal; } break;
        }
    }
    bool finish(char* out, size_t& length) {
        feed(' ');
        std::memcpy(out,word_,length_); out[length_]=0; length=length_;
        return words_==1 && !overflow_ && length_;
    }
 private:
    void emit(char c) {
        if(c==' ') { inWord_=false; return; }
        if(!inWord_) { inWord_=true; ++words_; }
        if(words_!=1)return;
        if(length_<kMaxCustomWordBytes)word_[length_++]=c; else overflow_=true;
    }
    enum State : uint8_t { Normal, Run, Apos, Skip } state_=Run; // leading pad space
    char word_[kMaxCustomWordBytes];
    size_t length_=0, words_=0;
    bool inWord_=false, overflow_=false;
};
// One UTF-8 code point (invalid bytes decode one U+FFFD each, as Python's
// 'replace' does up to repetition, which normalisation makes irrelevant).
size_t utf8(const uint8_t* p, size_t n, uint32_t& cp) {
    const uint8_t b=p[0];
    const size_t length=b<0x80 ? 1 : b>=0xc2 && b<=0xdf ? 2 : b>=0xe0 && b<=0xef ? 3 : b>=0xf0 && b<=0xf4 ? 4 : 0;
    cp=0xfffd;
    if(length==1) { cp=b; return 1; }
    if(!length || length>n)return 1;
    uint32_t v=b&(0x7f>>length);
    for(size_t i=1;i<length;++i) { if((p[i]&0xc0)!=0x80)return 1; v=v<<6|(p[i]&0x3f); }
    constexpr uint32_t kMinimum[5]={0,0,0x80,0x800,0x10000};
    if(v<kMinimum[length] || v>0x10ffff || (v>=0xd800 && v<=0xdfff))return 1;
    cp=v; return length;
}
// Python str.splitlines() boundaries.
bool lineBreak(uint32_t cp) {
    return (cp>=0x0a && cp<=0x0d) || (cp>=0x1c && cp<=0x1e) || cp==0x85 || cp==0x2028 || cp==0x2029;
}
// str.lower() then [^a-z'] -> space. U+0130 and U+212A are the only code
// points whose lowercase contains an ASCII letter.
void feedLower(LineWord& line, uint32_t cp) {
    if(cp>='A' && cp<='Z')cp+=32;
    if((cp>='a' && cp<='z') || cp=='\'')line.feed(char(cp));
    else if(cp==0x130) { line.feed('i'); line.feed(' '); }   // 'i' + U+0307
    else if(cp==0x212a)line.feed('k');                        // KELVIN SIGN
    else line.feed(' ');
}
// Soft-double fast paths. The P4 has a single-precision FPU only, so every
// double +, -, <, == and float<->double conversion is a libgcc call (about
// 25-100 instructions plus the call). These integer versions are exact
// (IEEE binary64/binary32, round to nearest even) on the inputs they accept
// and defer to the compiler's own operation otherwise, so results are
// bit-identical either way. Other targets use the native operations.
#if defined(__GNUC__)
#define HW1_LM_INLINE inline __attribute__((always_inline))
#define HW1_LM_NOINLINE __attribute__((noinline))
#define HW1_LM_LAMBDA_INLINE __attribute__((always_inline))
#else
#define HW1_LM_INLINE inline
#define HW1_LM_NOINLINE
#define HW1_LM_LAMBDA_INLINE
#endif
#if !defined(HW1_LM_SOFT_DOUBLE)
#if defined(__riscv) && (!defined(__riscv_flen) || __riscv_flen<64)
#define HW1_LM_SOFT_DOUBLE 1
#else
#define HW1_LM_SOFT_DOUBLE 0
#endif
#endif
constexpr uint64_t kNegInfBits=0xfff0000000000000ull;
inline uint64_t bitsOf(double v) { uint64_t b; std::memcpy(&b,&v,8); return b; }
[[maybe_unused]] inline double fromBits(uint64_t b) { double v; std::memcpy(&v,&b,8); return v; }
inline bool isNegInf(double v) { return bitsOf(v)==kNegInfBits; }
// a<b for non-NaN doubles (scores are never NaN), on 32-bit words; -0 and
// +0 compare equal as in IEEE.
inline bool dLess(double a, double b) {
#if HW1_LM_SOFT_DOUBLE
    const uint64_t x=bitsOf(a), y=bitsOf(b);
    const uint32_t xh=uint32_t(x>>32), yh=uint32_t(y>>32), xl=uint32_t(x), yl=uint32_t(y);
    if((xh^yh)>>31)return (xh>>31) && ((xh|yh)<<1|xl|yl);
    if(xh>>31)return xh>yh || (xh==yh && xl>yl);
    return xh<yh || (xh==yh && xl<yl);
#else
    return a<b;
#endif
}
// a+b on 32-bit words for normal operands: a 53-bit significand pair plus
// one exact guard word g holding the bits shifted out of the smaller
// operand. Inline: exponents differ by less than 32 with like signs, or by
// 2..31 with unlike signs (at most one normalisation shift), or by 55 or
// more (|b| is below a quarter ulp of a, so the sum rounds to a). Unlike
// signs within one binade cancel and are normalised out of line; any other
// case, and a result that is not normal, defers to a+b.
#if HW1_LM_SOFT_DOUBLE
inline double packAdd(uint32_t signWord, uint32_t e, uint32_t sh, uint32_t sl, uint32_t g, double a, double b) {
    if(g>0x80000000u || (g==0x80000000u && (sl&1))) { if(!++sl)++sh; if(sh>>21) { sl=sl>>1|sh<<31; sh>>=1; ++e; } }
    if(e-1u<2046u)return fromBits(uint64_t((signWord&0x80000000u)|e<<20|(sh&0xfffff))<<32|sl);
    return a+b;
}
// The rarer shapes, out of line (x has the larger exponent, d=ex-ey):
// unlike signs within one binade (exact difference, normalised by the
// leading zeros), or 32<=d<55 (the smaller significand moves a whole word
// down; g keeps the top 32 shifted-out bits with the rest jammed into its
// lowest bit, which still rounds correctly with at most one shift).
HW1_LM_NOINLINE double dAddSlow(double a, double b, uint64_t x, uint64_t y, uint32_t d) {
    uint32_t xh=uint32_t(x>>32), sh=(xh&0xfffff)|0x100000, sl=uint32_t(x);
    uint32_t th=(uint32_t(y>>32)&0xfffff)|0x100000, tl=uint32_t(y), g=0;
    const bool same=!((xh^uint32_t(y>>32))>>31);
    uint32_t e=(xh>>20)&0x7ff;
    if(d>=32) {
        const uint32_t r=d-32;   // 0..22
        g=r ? (th<<(32-r)|tl>>r)|uint32_t((tl<<(32-r))!=0) : tl;
        tl=th>>r; th=0;
        if(same) {
            const uint32_t lo=sl+tl; sh+=(lo<sl); sl=lo;
            if(sh>>21) { g=g>>1|(g&1)|sl<<31; sl=sl>>1|sh<<31; sh>>=1; ++e; }
        } else {
            const uint32_t b0=g!=0, t=tl+b0, b1=(t<tl)|(sl<t);
            g=0u-g; sl-=t; sh-=b1;
            if(!(sh>>20)) { sh=sh<<1|sl>>31; sl=sl<<1|g>>31; g<<=1; --e; }
        }
        return packAdd(xh,e,sh,sl,g,a,b);
    }
    if(!d && (sh<th || (sh==th && sl<tl))) { std::swap(sh,th); std::swap(sl,tl); xh=uint32_t(y>>32); }
    if(d) { g=tl<<31; tl=tl>>1|th<<31; th>>=1; }
    const uint32_t b0=g!=0, t=tl+b0, b1=(t<tl)|(sl<t);
    g=0u-g; sl-=t; sh=sh-th-b1;
    if(!(sh>>20)) {
        if(!sh)return a+b;                                  // 21+ bits cancelled, or zero
        uint32_t v=sh, k=1;                                 // shifts that bring the leading 1 to bit 20
        if(!(v>>4)) { k+=16; v<<=16; }
        if(!(v>>12)) { k+=8; v<<=8; }
        if(!(v>>16)) { k+=4; v<<=4; }
        if(!(v>>18)) { k+=2; v<<=2; }
        if(!(v>>19))k+=1;
        sh=sh<<k|sl>>(32-k); sl=sl<<k|g>>(32-k); g<<=k;
        if(e<=k)return a+b;                                 // subnormal
        e-=k;
    }
    return packAdd(xh,e,sh,sl,g,a,b);
}
HW1_LM_INLINE double dAdd(double a, double b) {
    uint64_t x=bitsOf(a), y=bitsOf(b);
    uint32_t ex=uint32_t(x>>52)&0x7ff, ey=uint32_t(y>>52)&0x7ff;
    if(ex-1u>=2046u || ey-1u>=2046u)return a+b;
    if(ex<ey) { std::swap(x,y); std::swap(ex,ey); }
    const uint32_t d=ex-ey;
    if(d>=55)return fromBits(x);
    const uint32_t xh=uint32_t(x>>32), yh=uint32_t(y>>32);
    const bool same=!((xh^yh)>>31);
    if(d>=32 || (!same && d<2))return dAddSlow(a,b,x,y,d);
    uint32_t sh=(xh&0xfffff)|0x100000, sl=uint32_t(x), th=(yh&0xfffff)|0x100000, tl=uint32_t(y), g=0;
    if(d) { g=tl<<(32-d); tl=tl>>d|th<<(32-d); th>>=d; }
    uint32_t e=ex;
    if(same) {
        const uint32_t lo=sl+tl; sh+=th+(lo<sl); sl=lo;
        if(sh>>21) { g=g>>1|(g&1)|sl<<31; sl=sl>>1|sh<<31; sh>>=1; ++e; }
    } else {   // (sh:sl:0)-(th:tl:g) with d>=2: the leading bit drops at most one place
        const uint32_t b0=g!=0, t=tl+b0, b1=(t<tl)|(sl<t);
        g=0u-g; sl-=t; sh=sh-th-b1;
        if(!(sh>>20)) { sh=sh<<1|sl>>31; sl=sl<<1|g>>31; g<<=1; --e; }
    }
    return packAdd(xh,e,sh,sl,g,a,b);
}
// a*b for normal operands with a normal result: the 106-bit product of
// the significands from four 32x32->64 partial products, then
// round-to-nearest-even at bit 52 or 53.
HW1_LM_INLINE double dMul(double a, double b) {
    const uint64_t x=bitsOf(a), y=bitsOf(b);
    const uint32_t xh=uint32_t(x>>32), yh=uint32_t(y>>32);
    const uint32_t ex=(xh>>20)&0x7ff, ey=(yh>>20)&0x7ff;
    if(ex-1u>=2046u || ey-1u>=2046u)return a*b;
    const uint32_t a1=(xh&0xfffff)|0x100000, a0=uint32_t(x), b1=(yh&0xfffff)|0x100000, b0=uint32_t(y);
    const uint64_t p00=uint64_t(a0)*b0, p01=uint64_t(a0)*b1, p10=uint64_t(a1)*b0, p11=uint64_t(a1)*b1;
    const uint32_t w0=uint32_t(p00);
    const uint64_t mid=(p00>>32)+uint32_t(p01)+uint32_t(p10);            // < 3*2^32
    const uint32_t w1=uint32_t(mid);
    const uint64_t high=(mid>>32)+(p01>>32)+(p10>>32)+p11;              // product>>64, < 2^42
    const uint32_t w2=uint32_t(high), w3=uint32_t(high>>32);
    int32_t e=int32_t(ex+ey)-1023;
    uint32_t mh, ml, round, sticky;
    if(w3>>9) { mh=w3<<11|w2>>21; ml=w2<<11|w1>>21; round=(w1>>20)&1; sticky=(w1&0xfffff)|w0; ++e; }
    else { mh=w3<<12|w2>>20; ml=w2<<12|w1>>20; round=(w1>>19)&1; sticky=(w1&0x7ffff)|w0; }
    if(round && (sticky || (ml&1))) { if(!++ml)++mh; if(mh>>21) { ml=ml>>1|mh<<31; mh>>=1; ++e; } }
    if(e<1 || e>2046)return a*b;
    return fromBits(uint64_t(((xh^yh)&0x80000000u)|uint32_t(e)<<20|(mh&0xfffff))<<32|ml);
}
#else
inline double dAdd(double a, double b) { return a+b; }
[[maybe_unused]] inline double dMul(double a, double b) { return a*b; }
#endif
HW1_LM_INLINE double dSub(double a, double b) {
#if HW1_LM_SOFT_DOUBLE
    return dAdd(a,fromBits(bitsOf(b)^0x8000000000000000ull));   // a-b == a+(-b) exactly
#else
    return a-b;
#endif
}
// Out-of-line forms for the colder call sites, so the always-inline kernel
// is not copied into every one of them (code size, instruction cache).
#if HW1_LM_SOFT_DOUBLE
HW1_LM_NOINLINE double dAddOut(double a, double b) { return dAdd(a,b); }
HW1_LM_NOINLINE double dSubOut(double a, double b) { return dSub(a,b); }
HW1_LM_NOINLINE double dMulOut(double a, double b) { return dMul(a,b); }
#else
[[maybe_unused]] inline double dAddOut(double a, double b) { return a+b; }
[[maybe_unused]] inline double dSubOut(double a, double b) { return a-b; }
[[maybe_unused]] inline double dMulOut(double a, double b) { return a*b; }
#endif
// double(f), exact.
inline double widen(float f) {
#if HW1_LM_SOFT_DOUBLE
    uint32_t b; std::memcpy(&b,&f,4);
    const uint32_t e=(b>>23)&0xff;
    if(e-1u<254u)return fromBits(uint64_t(b>>31)<<63|uint64_t(e+896)<<52|uint64_t(b&0x7fffff)<<29);
#endif
    return double(f);
}
// float(v), round to nearest even, for normal float results.
inline float narrow(double v) {
#if HW1_LM_SOFT_DOUBLE
    const uint64_t b=bitsOf(v);
    const uint32_t e=uint32_t(b>>52)&0x7ff;
    if(e-897u<254u) {
        uint32_t f=uint32_t(b>>63)<<31|(e-896)<<23|(uint32_t(b>>29)&0x7fffff);
        const uint32_t rest=uint32_t(b)&0x1fffffff;
        if(rest>0x10000000u || (rest==0x10000000u && (f&1)))++f;   // a carry into the exponent is correct
        float r; std::memcpy(&r,&f,4); return r;
    }
#endif
    return float(v);
}
// std::log for the per-frame normaliser on the P4. Its newlib (fdlibm,
// __OBSOLETE_MATH) __ieee754_log is a fixed sequence of IEEE double
// operations; this is the same sequence for positive normal x with the
// soft-double kernels above (the one division stays a libgcc call), so it
// returns the same bits about twice as fast. Built only where the C library
// is that newlib; anything else (and any other x) uses std::log.
#if HW1_LM_SOFT_DOUBLE && defined(_NEWLIB_VERSION) && !defined(__PICOLIBC__) && defined(__OBSOLETE_MATH) && __OBSOLETE_MATH
#define HW1_LM_SOFT_LOG 1
HW1_LM_NOINLINE double logOf(double x) {
    constexpr double ln2_hi=6.93147180369123816490e-01, ln2_lo=1.90821492927058770002e-10;
    constexpr double Lg1=6.666666666666735130e-01, Lg2=3.999999999940941908e-01, Lg3=2.857142874366239149e-01,
                     Lg4=2.222219843214978396e-01, Lg5=1.818357216161805012e-01, Lg6=1.531383769920937332e-01,
                     Lg7=1.479819860511658591e-01;
    uint64_t bits=bitsOf(x);
    int32_t hx=int32_t(bits>>32);
    if(hx<0x00100000 || hx>=0x7ff00000)return std::log(x);   // zero, negative, subnormal, inf, NaN
    int32_t k=(hx>>20)-1023;
    hx&=0x000fffff;
    const int32_t i0=(hx+0x95f64)&0x100000;
    x=fromBits(uint64_t(uint32_t(hx|(i0^0x3ff00000)))<<32|uint32_t(bits));   // normalize x or x/2
    k+=(i0>>20);
    const double f=dSubOut(x,1.0);
    if((0x000fffff&(2+hx))<3) {   // |f| < 2**-20
        if(f==0.0) { if(k==0)return 0.0; const double dk=double(k); return dAddOut(dMulOut(dk,ln2_hi),dMulOut(dk,ln2_lo)); }
        const double R=dMulOut(dMulOut(f,f),dSubOut(0.5,dMulOut(0.33333333333333333,f)));
        if(k==0)return dSubOut(f,R);
        const double dk=double(k);
        return dSubOut(dMulOut(dk,ln2_hi),dSubOut(dSubOut(R,dMulOut(dk,ln2_lo)),f));
    }
    const double s=f/dAddOut(2.0,f);
    const double dk=double(k);
    const double z=dMulOut(s,s);
    int32_t i=hx-0x6147a;
    const double w=dMulOut(z,z);
    const int32_t j=0x6b851-hx;
    const double t1=dMulOut(w,dAddOut(Lg2,dMulOut(w,dAddOut(Lg4,dMulOut(w,Lg6)))));
    const double t2=dMulOut(z,dAddOut(Lg1,dMulOut(w,dAddOut(Lg3,dMulOut(w,dAddOut(Lg5,dMulOut(w,Lg7)))))));
    i|=j;
    const double R=dAddOut(t2,t1);
    if(i>0) {
        const double hfsq=dMulOut(dMulOut(0.5,f),f);
        if(k==0)return dSubOut(f,dSubOut(hfsq,dMulOut(s,dAddOut(hfsq,R))));
        return dSubOut(dMulOut(dk,ln2_hi),dSubOut(dSubOut(hfsq,dAddOut(dMulOut(s,dAddOut(hfsq,R)),dMulOut(dk,ln2_lo))),f));
    }
    if(k==0)return dSubOut(f,dMulOut(s,dSubOut(f,R)));
    return dSubOut(dMulOut(dk,ln2_hi),dSubOut(dSubOut(dMulOut(s,dSubOut(f,R)),dMulOut(dk,ln2_lo)),f));
}
#else
#define HW1_LM_SOFT_LOG 0
inline double logOf(double x) { return std::log(x); }
#endif
inline int exponentOf(double v) { return int((bitsOf(v)>>52)&0x7ff)-1023; }
// Scores accumulate in double so tiny log-sum corrections (e.g. an exp(-21)
// alternative alignment) still order prefixes as a float64 reference does;
// only the correction term uses single-precision exp/log1p (P4 has no double
// FPU). Exact ties therefore arise from identical arithmetic, as in the spec.
// Each double operation here is the kernel form of the same operation, and
// lse(a,-inf)=a, lse(-inf,b)=b exactly as the plain version returns them.
//
// Exact shortcut: with x=float(b-a), the correction z=log1pf(expf(x)) is
// below e^x*(1+2^-21)+2^-148 (expf/log1pf within an ulp, log1p(y)<=y). For
// |a| in [2^E,2^(E+1)), E>=-80, a+z rounds back to a whenever z<2^(E-54)
// (half the spacing on either side of a), which x<=(E-57)*ln2 guarantees
// with a factor of 8 to spare; the float threshold's own rounding (~1e-5)
// is far inside that. The result is then bit-identical without calling
// expf/log1pf (about a quarter of the full evaluations on real audio).
inline double lse(double a, double b) {
    if(isNegInf(b))return a;
    if(isNegInf(a))return b;
    if(dLess(a,b))std::swap(a,b);
    const float x=narrow(dSub(b,a));
    const int e=exponentOf(a);
    if(e>=-80 && x<=float(e-57)*0.693147f)return a;
    return dAdd(a,widen(std::log1p(std::exp(x))));
}
// float(v) within 2^-23|v| (+2^-126 near zero) by truncation, without the
// soft-float conversion call on the P4 (no double FPU). Infinity stays
// infinite. Only used for conservative pre-tests that carry a 2^-16 margin.
inline float approxFloat(double v) {
    uint64_t bits; std::memcpy(&bits,&v,8);
    const uint32_t hi=uint32_t(bits>>32), sign=hi&0x80000000u;
    const int e=int((hi>>20)&0x7ff);
    uint32_t f;
    if(e>=1023+128)f=sign|0x7f800000u;         // inf (or beyond float range)
    else if(e<1023-126)f=sign;                  // below the float normal range
    else f=sign|uint32_t(e-1023+127)<<23|(hi&0xfffffu)<<3|uint32_t(bits)>>29;
    float r; std::memcpy(&r,&f,4); return r;
}
// Margin for the float pre-tests: float sums of approxFloat terms are within
// ~4*2^-23 of the exact double result relative to the summed magnitudes, so a
// relative 2^-16 (plus an absolute floor) leaves a factor of 30 to spare.
constexpr float kMarginScale=1.0f/65536.0f, kMarginFloor=7.888609e-31f; // 2^-100
// A conservative slack added to double upper bounds: hundreds of ulps of the
// magnitudes involved, so a bound stays valid whether or not the compiler
// fuses a multiply-add in the bounded expression (host FMA) or not (P4).
inline double slack(double magnitude) { return std::fabs(magnitude)*0x1p-45+0x1p-60; }
size_t pow2(size_t n) { size_t p=1; while(p<n)p<<=1; return p; }
struct Node {
    double lm, spaceLm;                    // spaceLm: after completing this node's partial word
    uint32_t parent, jump;                 // jump: skew-binary ancestor, O(log depth) LCA
    uint16_t ctx2, ctx1, spaceWord, depth; // context (w-2, w-1); id pushed by that completion
    uint8_t ch, wordLen, spaceReady, pad;  // wordLen saturates at 255 (then OOV, not listed)
};
// total = lse(pb, pnb), computed once when the prefix was scored as a
// candidate and carried into the next frame (same function, same inputs).
struct Beam { double pb, pnb, total; uint32_t node, pad; };
// key = float(score): rounding is monotonic, so unequal keys order exactly
// like the doubles and most heap comparisons avoid soft-float on the P4.
struct Cand { double pb, pnb, total, score; uint32_t node, parent; float key; uint8_t ch, fresh, pad[2]; };
static_assert(sizeof(Node)==40 && sizeof(Beam)==32 && sizeof(Cand)==48);
// log_softmax of q*2^exponent: exp(x-max) and (x-max) take only 256 values.
struct ExpTable { double exps[256], steps[256]; };   // exp(-d*2^e), double(-d)*2^e (exact)
void fillExp(ExpTable& t, int exponent) {
    const double scale=std::ldexp(1.0,exponent);
    for(int d=0;d<256;++d) { t.exps[d]=std::exp(-double(d)*scale); t.steps[d]=double(-d)*scale; }
}
// Built once (PSRAM .bss on the P4; it was 1.1M instructions of soft-double
// exp in every decode). Lock-free: the first decode claims and fills it; a decode that
// finds it being built, or built for another exponent, fills its own copy
// in the workspace instead.
EXT_RAM_BSS_ATTR ExpTable gExpTable;
std::atomic<int> gExpState{0};   // 0 empty, 1 filling, exponent+64 ready
const ExpTable& expTable(int exponent, ExpTable& fallback) {
    const int ready=exponent+64;
    int state=gExpState.load(std::memory_order_acquire);
    if(state==ready)return gExpTable;
    if(state==0 && gExpState.compare_exchange_strong(state,1,std::memory_order_acq_rel)) {
        fillExp(gExpTable,exponent); gExpState.store(ready,std::memory_order_release); return gExpTable;
    }
    fillExp(fallback,exponent); return fallback;
}
// Per-decode memo tables for the pure LM functions behind a completion:
// word bytes -> (vocabulary id, hotword listed) and (w2, w1, w) -> log10().
// Distinct prefixes often end in the same word or context. Open addressing
// over a 16-bit index (cleared per decode) into append-only entries; a full
// table simply stops memoising.
constexpr size_t kCachedWordBytes=32;
struct WordEntry { uint32_t hash; int32_t id; uint8_t length, listed, pad[2]; char bytes[kCachedWordBytes]; };
struct GramEntry { uint16_t w2, w1, w, pad; double value; };
static_assert(sizeof(WordEntry)==44 && sizeof(GramEntry)==16);
struct HeapSlot { float key; uint16_t index, pad; };
struct Layout { size_t nodes, table, tableSize, beams, cands, heap, local, slots, exps, fresh, cacheSlots,
                wordIndex, words, gramIndex, grams, bytes, maxNodes; };
bool layout(size_t frames, size_t beam, Layout& l) {
    if(frames>kMaxFrames || !beam || beam>kMaxBeam)return false;
    l.maxNodes=frames*beam+1; // <= beam new prefixes per frame, plus the root
    l.tableSize=pow2(2*l.maxNodes);
    size_t at=0;
    auto take=[&](size_t bytes) { const size_t start=(at+15)&~size_t(15); at=start+bytes; return start; };
    l.nodes=take(sizeof(Node)*l.maxNodes); l.table=take(4*l.tableSize);
    l.beams=take(sizeof(Beam)*beam); l.cands=take(sizeof(Cand)*beam*kClasses);
    l.heap=take(sizeof(HeapSlot)*beam); l.local=take(4*kLocal); l.slots=take(kLocal); l.exps=take(sizeof(ExpTable));
    l.fresh=take(4*beam);
    l.cacheSlots=std::min<size_t>(pow2(std::max<size_t>(256,2*frames)),8192);
    l.wordIndex=take(2*l.cacheSlots); l.words=take(sizeof(WordEntry)*(l.cacheSlots/2));
    l.gramIndex=take(2*l.cacheSlots); l.grams=take(sizeof(GramEntry)*(l.cacheSlots/2));
    l.bytes=at; return true;
}
struct Cursor { uint32_t node; int extra; }; // extra>=0: one virtual child char
// Speed notes. All of it is bit-identical to the plain search (same beams,
// scores, tie-breaks and nodes, in the same order, every frame):
// - a step first settles the live prefixes (they always enter the heap
//   first, as before), then streams the fresh extensions through the heap
//   in the original order; once the heap is full a fresh candidate whose
//   score provably cannot beat the worst kept one (a float pre-test with a
//   2^-16 margin; for a space an upper bound on its word score) is dropped
//   before any double arithmetic or word lookup, which is exactly what
//   select() did after scoring it.
// - lse(pb, pnb) of a kept prefix is carried into the next frame.
// - per frame only the needed log-probabilities are formed, and the
//   char_prune set comes from the monotone (x - max) table.
// - word lookups and n-gram scores are memoised per decode.
// - the final pass scores only beams whose upper bound can still win.
// - on the P4 the double arithmetic runs through the exact integer kernels
//   above instead of libgcc calls, and std::log through its fdlibm sequence.
class Search {
 public:
    Search(const Lm& lm, const CustomWords* words, uint8_t* w, const Layout& l, size_t beam)
        : lm_(lm), words_(words && words->size() ? words : nullptr), alphaLn_(double(lm.alpha())*kLn10),
          nodes_(reinterpret_cast<Node*>(w+l.nodes)), table_(reinterpret_cast<uint32_t*>(w+l.table)),
          beams_(reinterpret_cast<Beam*>(w+l.beams)), cands_(reinterpret_cast<Cand*>(w+l.cands)),
          heap_(reinterpret_cast<HeapSlot*>(w+l.heap)), local_(reinterpret_cast<uint32_t*>(w+l.local)),
          slots_(w+l.slots), fallback_(reinterpret_cast<ExpTable*>(w+l.exps)),
          fresh_(reinterpret_cast<uint32_t*>(w+l.fresh)),
          wordIndex_(reinterpret_cast<uint16_t*>(w+l.wordIndex)), words_cache_(reinterpret_cast<WordEntry*>(w+l.words)),
          gramIndex_(reinterpret_cast<uint16_t*>(w+l.gramIndex)), grams_(reinterpret_cast<GramEntry*>(w+l.grams)),
          cacheMask_(l.cacheSlots-1), cacheCap_(l.cacheSlots/2), mask_(l.tableSize-1), width_(beam) {
        std::fill(table_,table_+l.tableSize,kEmpty);
        std::fill(wordIndex_,wordIndex_+l.cacheSlots,uint16_t(0));
        std::fill(gramIndex_,gramIndex_+l.cacheSlots,uint16_t(0));
        // Root: no character (ch is never compared), context (none, <s>).
        nodes_[0]=Node{0,0,kEmpty,0,kNoWord,lm.bos(),0,0,uint8_t(kBlank),0,0,0};
        count_=1; beams_[0]=Beam{0,kNegInf,0,0,0}; live_=1;   // total=lse(0,-inf)=0
        // Upper bounds of a completion's delta and of the </s> term:
        // alpha*ln10*log10p is monotone in log10p, log10p lies in the LM's
        // [log10Min, log10Max] (or is unkLog10), and the hotword bonus is
        // either added or not. Each bound adds slack() so it holds with or
        // without a fused multiply-add in the bounded expression.
        const double hiNgram=lm.log10Max(), loNgram=lm.log10Min(), unk=double(lm.unkLog10());
        const double termHi=alphaLn_>=0 ? alphaLn_*std::max(hiNgram,unk) : alphaLn_*std::min(loNgram,unk);
        const double bonus=words_ ? std::max(0.0,double(lm.hotwordBonus())) : 0.0;
        const double delta=termHi+double(lm.beta())+bonus;
        deltaUb_=delta+slack(std::fabs(termHi)+std::fabs(double(lm.beta()))+bonus);
        const double eos=alphaLn_>=0 ? alphaLn_*hiNgram : alphaLn_*loNgram;
        eosUb_=eos+slack(eos);
        float f=float(deltaUb_);
        if(double(f)<deltaUb_)f=std::nextafter(f,std::numeric_limits<float>::infinity());
        deltaUbF_=f;   // >= deltaUb_
    }
    DecodeStatus run(const int8_t* logits, size_t frames, int exponent, const DecodeControl& control,
                     char* text, size_t capacity, DecodeStats* stats);
 private:
    uint8_t byte(const Cursor& c) const { return uint8_t(kVocab[c.extra>=0 ? c.extra : nodes_[c.node].ch]); }
    size_t depth(const Cursor& c) const { return nodes_[c.node].depth+(c.extra>=0); }
    // Ancestor of c (inclusive) with the given length, via jump pointers.
    Cursor ancestor(Cursor c, size_t length) const {
        if(c.extra>=0) { if(depth(c)==length)return c; c.extra=-1; }
        uint32_t x=c.node;
        while(nodes_[x].depth>length)x=nodes_[nodes_[x].jump].depth>=length ? nodes_[x].jump : nodes_[x].parent;
        return {x,-1};
    }
    // Prefix byte order without materialising either string: cut both to
    // the shorter length, then climb to the children of their lowest common
    // ancestor. The trie is canonical, so distinct nodes are distinct strings.
    // Exact score ties persist across frames (tied branches that only differ
    // in an early character), so this must not walk whole prefixes.
    int compare(Cursor a, Cursor b) const {
        const size_t la=depth(a), lb=depth(b), length=std::min(la,lb);
        const int shorter=la<lb ? -1 : la>lb ? 1 : 0;
        a=ancestor(a,length); b=ancestor(b,length);
        if(a.node==b.node && a.extra==b.extra)return shorter;
        const uint32_t pa=a.extra>=0 ? a.node : nodes_[a.node].parent, pb=b.extra>=0 ? b.node : nodes_[b.node].parent;
        if(pa==pb)return byte(a)==byte(b) ? shorter : byte(a)<byte(b) ? -1 : 1;
        uint32_t x=pa, y=pb; // distinct real nodes of equal depth
        while(nodes_[x].parent!=nodes_[y].parent) {
            if(nodes_[x].jump!=nodes_[y].jump) { x=nodes_[x].jump; y=nodes_[y].jump; }
            else { x=nodes_[x].parent; y=nodes_[y].parent; }
        }
        return nodes_[x].ch==nodes_[y].ch ? shorter : uint8_t(kVocab[nodes_[x].ch])<uint8_t(kVocab[nodes_[y].ch]) ? -1 : 1;
    }
    Cursor cursor(uint16_t j) const { const Cand& c=cands_[j]; return c.fresh ? Cursor{c.parent,c.ch} : Cursor{c.node,-1}; }
    bool better(uint16_t a, uint16_t b) const {
        if(cands_[a].key!=cands_[b].key)return cands_[a].key>cands_[b].key;
        if(cands_[a].score!=cands_[b].score)return cands_[a].score>cands_[b].score;
        return compare(cursor(a),cursor(b))<0; // ties: prefix bytes ascending
    }
    // Word completion after node id (ends in a letter/apostrophe), computed
    // once per node: alpha*ln10*log10P(word|ctx) + beta (+ hotword bonus).
    void complete(uint32_t id) {
        Node& n=nodes_[id];
        if(n.spaceReady)return;
        char word[256]; const size_t length=n.wordLen;
        int found=-1; bool listed=false;
        if(length<255) {
            uint32_t at=id;
            for(size_t i=length;i>0;--i) { word[i-1]=kVocab[nodes_[at].ch]; at=nodes_[at].parent; }
            lookup(word,length,found,listed);
        }
        // Same operation order as the reference: delta first, then accumulate.
        // (Soft-double targets never fuse a multiply-add, so the kernels give
        // the same bits; elsewhere the expression is kept as written.)
        const double log10p=found<0 ? double(lm_.unkLog10()) : gram(n.ctx2,n.ctx1,uint16_t(found));
#if HW1_LM_SOFT_DOUBLE
        const double delta=dAddOut(dAddOut(dMulOut(alphaLn_,log10p),double(lm_.beta())),listed ? double(lm_.hotwordBonus()) : 0.0);
#else
        const double delta=alphaLn_*log10p+double(lm_.beta())+(listed ? double(lm_.hotwordBonus()) : 0.0);
#endif
        n.spaceLm=dAddOut(n.lm,delta);
        n.spaceWord=found<0 ? lm_.unk() : uint16_t(found); n.spaceReady=1; ++completions_;
    }
    // lm_.find + words_->contains, memoised by the word's bytes.
    void lookup(const char* word, size_t length, int& found, bool& listed) {
        uint32_t hash=2166136261u;
        for(size_t i=0;i<length;++i) { hash^=uint8_t(word[i]); hash*=16777619u; }
        size_t h=hash&cacheMask_;
        if(length<=kCachedWordBytes) {
            for(;wordIndex_[h];h=(h+1)&cacheMask_) {
                const WordEntry& e=words_cache_[wordIndex_[h]-1];
                if(e.hash==hash && e.length==length && !std::memcmp(e.bytes,word,length)) { found=e.id; listed=e.listed; return; }
            }
        }
        found=lm_.find(word,length);
        listed=words_ && words_->contains(word,length);
        if(length<=kCachedWordBytes && wordCount_<cacheCap_) {
            WordEntry& e=words_cache_[wordCount_++];
            e.hash=hash; e.id=found; e.length=uint8_t(length); e.listed=listed; std::memcpy(e.bytes,word,length);
            wordIndex_[h]=uint16_t(wordCount_);
        }
    }
    // lm_.log10(w2, w1, w), memoised.
    double gram(uint16_t w2, uint16_t w1, uint16_t w) {
        uint32_t hash=uint32_t(w2)*0x9e3779b1u^uint32_t(w1)*0x85ebca6bu^uint32_t(w)*0xc2b2ae35u; hash^=hash>>15;
        size_t h=hash&cacheMask_;
        for(;gramIndex_[h];h=(h+1)&cacheMask_) {
            const GramEntry& e=grams_[gramIndex_[h]-1];
            if(e.w2==w2 && e.w1==w1 && e.w==w)return e.value;
        }
        const double value=lm_.log10(w2,w1,w);
        if(gramCount_<cacheCap_) {
            grams_[gramCount_++]=GramEntry{w2,w1,w,0,value};
            gramIndex_[h]=uint16_t(gramCount_);
        }
        return value;
    }
    uint32_t child(uint32_t parent, uint8_t c) {
        const uint32_t key=parent<<5|c;
        uint32_t h=key*0x9e3779b1u; h^=h>>15;
        for(h&=mask_;table_[h]!=kEmpty;h=(h+1)&mask_) {
            const Node& n=nodes_[table_[h]];
            if(n.parent==parent && n.ch==c)return table_[h];
        }
        if(c==kSpace)complete(parent);
        const Node& p=nodes_[parent];
        const uint32_t id=count_++;
        Node& n=nodes_[id];
        n.parent=parent;n.ch=c;n.depth=uint16_t(p.depth+1);n.spaceLm=0;n.spaceWord=0;n.spaceReady=0;n.pad=0;
        const Node& j=nodes_[p.jump]; // Myers' skew-binary jump: depends only on depth
        n.jump=p.depth-j.depth==j.depth-nodes_[j.jump].depth ? j.jump : parent;
        if(c==kSpace) { n.lm=p.spaceLm;n.ctx2=p.ctx1;n.ctx1=p.spaceWord;n.wordLen=0; }
        else { n.lm=p.lm;n.ctx2=p.ctx2;n.ctx1=p.ctx1;n.wordLen=uint8_t(std::min(255,p.wordLen+1)); }
        table_[h]=id; return id;
    }
    uint16_t localFind(uint32_t key) const {
        for(uint32_t h=(key*0x9e3779b1u)>>25;local_[h]!=kEmpty;h=(h+1)&(kLocal-1))
            if(local_[h]==key)return slots_[h];
        return 0xffff;
    }
    void localInsert(uint32_t key, uint8_t slot) {
        uint32_t h=(key*0x9e3779b1u)>>25;
        while(local_[h]!=kEmpty)h=(h+1)&(kLocal-1);
        local_[h]=key; slots_[h]=slot;
    }
    // This frame's log-probability of class c, formed on first use exactly
    // as double(q[c]-top)*scale-lz (the product is exact: steps_[d]).
    HW1_LM_INLINE double lp(size_t c) {
        if(!(ready_>>c&1))formLp(c);
        return lp_[c];
    }
    HW1_LM_NOINLINE void formLp(size_t c) { lp_[c]=dSub(steps_[d_[c]],lz_); lpF_[c]=approxFloat(lp_[c]); ready_|=1u<<c; }
    HW1_LM_INLINE float lpF(size_t c) { lp(c); return lpF_[c]; }
    // better() on heap slots, which carry a copy of the key so most
    // comparisons need no candidate load.
    HW1_LM_INLINE bool slotBetter(const HeapSlot& a, const HeapSlot& b) const {
        if(a.key!=b.key)return a.key>b.key;
        return better(a.index,b.index);
    }
    // Bounded heap, worst kept candidate on top; the order is total (distinct
    // prefixes), so the kept set is exactly the top width_.
    void push(uint16_t j) {
        size_t i=kept_++; heap_[i]=HeapSlot{cands_[j].key,j,0};
        while(i && slotBetter(heap_[(i-1)/2],heap_[i])) { std::swap(heap_[i],heap_[(i-1)/2]); i=(i-1)/2; }
    }
    void sink(size_t i) {
        for(;;) {
            size_t l=2*i+1, r=l+1, m=i;
            if(l<kept_ && slotBetter(heap_[m],heap_[l]))m=l;
            if(r<kept_ && slotBetter(heap_[m],heap_[r]))m=r;
            if(m==i)return;
            std::swap(heap_[i],heap_[m]); i=m;
        }
    }
    void step(const uint8_t* active, size_t count);
    bool hopeless(uint32_t parent, uint8_t c, float baseF);
#if defined(__GNUC__)
    [[gnu::noinline]]
#endif
    void admit(uint32_t parent, uint8_t c, double base);
    const Lm& lm_;
    const CustomWords* words_;
    const double alphaLn_;
    double deltaUb_=0, eosUb_=0;
    float deltaUbF_=0;
    Node* nodes_; uint32_t* table_; Beam* beams_; Cand* cands_; HeapSlot* heap_;
    uint32_t* local_; uint8_t* slots_; ExpTable* fallback_; uint32_t* fresh_;
    uint16_t* wordIndex_; WordEntry* words_cache_; uint16_t* gramIndex_; GramEntry* grams_;
    size_t cacheMask_, cacheCap_, wordCount_=0, gramCount_=0;
    const double* steps_=nullptr;
    double lz_=0, lp_[kClasses];
    float lpF_[kClasses];
    uint8_t d_[kClasses];
    uint32_t ready_=0;
    float lmF_=0;   // approxFloat(lm) of the prefix being extended
    size_t mask_, width_, count_=0, live_=0, kept_=0, candidates_=0, considered_=0, completions_=0;
};
// One fresh candidate (b's prefix + c, value base+lp(c) in p_nb), in the
// reference's creation order. Before the heap is full it is always kept.
// After that, it is kept iff better() than the worst kept one; hopeless()
// rejects early only when key<topKey is certain (the root's key, a copy in
// its heap slot): the float sum is within
// ~4*2^-23 of the double score relative to the magnitudes (plus the
// approxFloat floors), and kMarginScale covers that with ~30x to spare;
// sum+margin<topKey then implies score<=pred(topKey), hence key<topKey.
// For a space whose word is not yet scored the bound deltaUb_ stands in.
HW1_LM_INLINE bool Search::hopeless(uint32_t parent, uint8_t c, float baseF) {
    if(kept_<width_)return false;
    const Node& n=nodes_[parent];
    const float topKey=heap_[0].key;
    float term=lmF_, extra=0;
    if(c==kSpace) { if(n.spaceReady)term=approxFloat(n.spaceLm); else extra=deltaUbF_; }
    const float l=lpF(c);
    const float sum=baseF+l+term+extra;
    const float margin=kMarginScale*(std::fabs(baseF)+std::fabs(l)+std::fabs(term)+std::fabs(extra)+std::fabs(topKey))+kMarginFloor;
    return sum+margin<topKey;
}
void Search::admit(uint32_t parent, uint8_t c, double base) {
    Node& n=nodes_[parent];
    const bool space=c==kSpace;
    const double value=dAdd(base,lp(c));
    if(space)complete(parent);
    const uint16_t j=uint16_t(candidates_);
    Cand& cand=cands_[j];
    cand.pb=kNegInf; cand.pnb=value; cand.total=value;   // lse(-inf, value)
    cand.score=dAdd(value,space ? n.spaceLm : n.lm); cand.key=narrow(cand.score);
    cand.node=0; cand.parent=parent; cand.ch=c; cand.fresh=1;
    if(kept_<width_) { ++candidates_; push(j); }
    else if(slotBetter(HeapSlot{cand.key,j,0},heap_[0])) { ++candidates_; heap_[0]=HeapSlot{cand.key,j,0}; sink(0); }
}
// active: the non-blank classes with lp >= char_prune this frame, ascending.
// The repeat of a prefix's last symbol is never pruned (reference reading of
// FORMAT.md, hw1lm.py): after a space it is blank-like (p_b), after a letter
// it stays in p_nb and doubles the letter from p_b. A leading space is an
// ordinary (pruned) token that is blank-like.
void Search::step(const uint8_t* active, size_t count) {
    std::fill(local_,local_+kLocal,kEmpty);
    for(size_t i=0;i<live_;++i) {
        Cand& c=cands_[i];
        c.pb=kNegInf; c.pnb=kNegInf; c.node=beams_[i].node; c.parent=0; c.ch=0; c.fresh=0;
        if(c.node) { const Node& n=nodes_[c.node]; localInsert(n.parent<<5|n.ch,uint8_t(i)); }
    }
    // 1. Everything that lands in a live prefix, in the reference's order
    // (each lse sees the same operands in the same order); fresh (prefix, c)
    // pairs are only marked. A -inf value (p_b of a fresh prefix) adds
    // nothing, as in extend(); lse(-inf, x) is x.
    const double blank=lp(kBlank);
    for(size_t i=0;i<live_;++i) {
        const Beam& b=beams_[i];
        const int last=b.node ? nodes_[b.node].ch : -1;
        Cand& self=cands_[i];
        uint32_t fresh=0;
        self.pb=dAdd(b.total,blank);
        if(last==int(kSpace))self.pb=lse(self.pb,dAddOut(b.total,lp(kSpace)));
        else if(last>0) {
            const double own=dAdd(b.pnb,lp(size_t(last)));
            self.pnb=isNegInf(self.pnb) ? own : lse(self.pnb,own);
            if(!isNegInf(b.pb)) {
                const uint16_t j=localFind(b.node<<5|uint32_t(last));
                if(j!=0xffff)cands_[j].pnb=lse(cands_[j].pnb,dAddOut(b.pb,lp(size_t(last)))); else fresh|=1u<<last;
            }
        }
        const bool extendable=!isNegInf(b.total);
        for(size_t k=0;k<count;++k) {
            const uint8_t c=active[k];
            if(int(c)==last)continue;
            if(c==kSpace && last<0) { self.pb=lse(self.pb,dAddOut(b.total,lp(c))); continue; }
            if(!extendable)continue;
            const uint16_t j=localFind(b.node<<5|c);
            if(j!=0xffff)cands_[j].pnb=lse(cands_[j].pnb,dAddOut(b.total,lp(c))); else fresh|=1u<<c;
        }
        fresh_[i]=fresh;
    }
    // 2. Score the live prefixes and fill the heap with them (live_<=width_,
    // so all of them enter it, as in select()).
    kept_=0;
    for(size_t i=0;i<live_;++i) {
        Cand& c=cands_[i];
        c.total=lse(c.pb,c.pnb); c.score=dAdd(c.total,nodes_[c.node].lm); c.key=narrow(c.score);
        push(uint16_t(i));
    }
    candidates_=live_; considered_+=live_;
    // 3. Fresh extensions in creation order: per prefix the repeat, then the
    // active classes ascending.
    for(size_t i=0;i<live_;++i) {
        const uint32_t fresh=fresh_[i];
        if(!fresh)continue;
        const Beam& b=beams_[i];
        const int last=b.node ? nodes_[b.node].ch : -1;
        lmF_=approxFloat(nodes_[b.node].lm);
        if(last>0 && (fresh>>last&1)) {
            ++considered_;
            if(!hopeless(b.node,uint8_t(last),approxFloat(b.pb)))admit(b.node,uint8_t(last),b.pb);
        }
        if(fresh&~(last>0 ? 1u<<last : 0u)) {
            const float totalF=approxFloat(b.total);
            for(size_t k=0;k<count;++k) {
                const uint8_t c=active[k];
                if(int(c)==last || !(fresh>>c&1))continue;
                ++considered_;
                if(!hopeless(b.node,c,totalF))admit(b.node,c,b.total);
            }
        }
    }
    for(size_t i=0;i<kept_;++i) {
        const Cand& c=cands_[heap_[i].index];
        beams_[i]=Beam{c.pb,c.pnb,c.total,c.fresh ? child(c.parent,c.ch) : c.node,0};
    }
    live_=kept_;
}
DecodeStatus Search::run(const int8_t* logits, size_t frames, int exponent, const DecodeControl& control,
                         char* text, size_t capacity, DecodeStats* stats) {
    const ExpTable& table=expTable(exponent,*fallback_);
    const double* exps=table.exps;
    steps_=table.steps;
    const double prune=lm_.charPrune();
    // Initial guess for the prune boundary in units of d (verified exactly).
    const float invScale=std::ldexp(1.0f,-exponent), pruneF=lm_.charPrune();
    uint8_t active[kBlank];
#if defined(ESP_PLATFORM)
    // The first yield point (frame 32) blocks once, so the network's own 250 ms
    // no-block window and the decode's do not add up (IDLE and the priority-1
    // loop task get a tick within ~32 frames of the decode starting).
    int64_t lastBlockUs=esp_timer_get_time()-kYieldBlockUs;
#endif
    for(size_t t=0;t<frames;++t) {
        if(!(t%kYieldFrames)) {
            if(control.cancelled && control.cancelled(control.context))return DecodeStatus::Cancelled;
#if defined(ESP_PLATFORM)
            if(t)yieldTask(lastBlockUs);
#endif
        }
        const int8_t* q=logits+t*kClasses;
        int top=q[0];
        for(size_t c=1;c<kClasses;++c)top=std::max(top,int(q[c]));
        // sum in class order as before; 0+x is x for the first (positive) term.
        d_[0]=uint8_t(top-q[0]);
        double sum=exps[d_[0]];
        for(size_t c=1;c<kClasses;++c) { d_[c]=uint8_t(top-q[c]); sum=dAdd(sum,exps[d_[c]]); }
        lz_=logOf(sum); ready_=0;
        // lp(d)=steps_[d]-lz_ is non-increasing in d (steps_ decreases,
        // rounding is monotonic), so {c : lp >= prune} = {c : d_c <= D}.
        // lo/hi bracket D: lp(d)>=prune for d<=lo, lp(d)<prune for d>=hi.
        int lo=-1, hi=256;
        auto activeAt=[&](int d) HW1_LM_LAMBDA_INLINE {
            if(d<=lo)return true;
            if(d>=hi)return false;
            if(!dLess(dSubOut(steps_[d],lz_),prune)) { lo=d; return true; }
            hi=d; return false;
        };
        {
            const float guess=(-approxFloat(lz_)-pruneF)*invScale;
            const int g=guess<-1.0f ? -1 : guess>255.0f ? 255 : int(std::floor(guess));
            if(g>=0)activeAt(g);
            if(g+1<=255)activeAt(g+1);
        }
        size_t count=0;
        for(size_t c=0;c<kBlank;++c)if(activeAt(d_[c]))active[count++]=uint8_t(c);
        step(active,count);
    }
    if(control.cancelled && control.cancelled(control.context))return DecodeStatus::Cancelled;
    // Finish: score any partial word as a completion, then </s>. A beam is
    // scored only while its upper bound (unscored word -> deltaUb_, </s> ->
    // eosUb_, both monotone) is not below the best exact score so far; the
    // best under (score, then prefix ascending) is the same as over all.
    // The candidate array is free now; it holds the bounds and their order.
    struct Bound { double ub; float key; uint8_t order, pad[3]; };
    static_assert(sizeof(Bound)<=sizeof(Cand));
    Bound* bound=reinterpret_cast<Bound*>(cands_);
    for(size_t i=0;i<live_;++i) {
        const Node& n=nodes_[beams_[i].node];
        const double base=!n.wordLen ? n.lm : n.spaceReady ? n.spaceLm : n.lm+deltaUb_;
        const double lm=base+eosUb_;
        const double s=beams_[i].total+lm;
        bound[i].ub=s+slack(std::fabs(beams_[i].total)+std::fabs(base)+std::fabs(eosUb_));
        bound[i].key=approxFloat(bound[i].ub);
        size_t k=i;   // insertion sort, descending approximate bound
        while(k && bound[bound[k-1].order].key<bound[i].key) { bound[k].order=bound[k-1].order; --k; }
        bound[k].order=uint8_t(i);
    }
    size_t best=0; double bestScore=kNegInf; bool any=false;
    for(size_t k=0;k<live_;++k) {
        const size_t i=bound[k].order;
        if(any && bound[i].ub<bestScore)continue;
        const uint32_t id=beams_[i].node;
        double lm; uint16_t w2, w1;
        if(nodes_[id].wordLen) { complete(id); lm=nodes_[id].spaceLm; w2=nodes_[id].ctx1; w1=nodes_[id].spaceWord; }
        else { lm=nodes_[id].lm; w2=nodes_[id].ctx2; w1=nodes_[id].ctx1; }
#if HW1_LM_SOFT_DOUBLE
        lm=dAddOut(lm,dMulOut(alphaLn_,gram(w2,w1,lm_.eos())));
#else
        lm+=alphaLn_*gram(w2,w1,lm_.eos());
#endif
        const double score=dAddOut(beams_[i].total,lm);   // total == lse(pb, pnb)
        if(!any || score>bestScore || (score==bestScore && compare({id,-1},{beams_[best].node,-1})<0)) { best=i; bestScore=score; }
        any=true;
    }
    if(stats) {
        stats->frames=uint32_t(frames); stats->beam=uint32_t(width_); stats->nodes=uint32_t(count_);
        stats->candidates=uint32_t(std::min<size_t>(considered_,UINT32_MAX)); stats->completions=uint32_t(completions_);
    }
    uint32_t at=beams_[best].node;
    size_t length=nodes_[at].depth;
    if(length && nodes_[at].ch==kSpace) { at=nodes_[at].parent; --length; } // no trailing space
    const bool fits=length<capacity;
    for(size_t skip=fits ? 0 : length-(capacity-1);skip;--skip) { at=nodes_[at].parent; --length; }
    text[length]=0;
    for(size_t i=length;i>0;--i) { text[i-1]=kVocab[nodes_[at].ch]; at=nodes_[at].parent; }
    return fits ? DecodeStatus::Ok : DecodeStatus::OutputTooSmall;
}
}

const char* describe(LoadStatus s) {
    switch(s) {
        case LoadStatus::Ok: return "ok";
        case LoadStatus::InvalidArgument: return "invalid argument";
        case LoadStatus::BadSize: return "file size does not match header";
        case LoadStatus::BadMagic: return "not an HW1LM1 file";
        case LoadStatus::BadVersion: return "unsupported version";
        case LoadStatus::BadHeader: return "invalid header field";
        case LoadStatus::BadLayout: return "sections exceed file";
        case LoadStatus::BadPadding: return "non-zero padding";
        case LoadStatus::BadChecksum: return "SHA-256 mismatch";
        case LoadStatus::BadStrings: return "invalid string table";
        case LoadStatus::Unsorted: return "unsorted words or n-grams";
        case LoadStatus::BadWordId: return "n-gram word id out of range";
        case LoadStatus::MissingSpecial: return "missing <s>, </s> or <unk>";
    }
    return "unknown";
}

bool sha256(const void* data, size_t bytes, uint8_t hash[32]) {
    if(!hash || (!data && bytes))return false;
#if defined(ESP_PLATFORM)
    return mbedtls_sha256(static_cast<const unsigned char*>(data),bytes,hash,0)==0;
#else
    uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    auto p=static_cast<const uint8_t*>(data);
    size_t left=bytes;
    for(;left>=64;left-=64,p+=64)shaBlock(h,p);
    uint8_t tail[128]={};
    if(left)std::memcpy(tail,p,left);
    tail[left]=0x80;
    const size_t end=left<56 ? 64 : 128;
    const uint64_t bits=uint64_t(bytes)*8;
    for(int i=0;i<8;++i)tail[end-1-i]=uint8_t(bits>>(8*i));
    shaBlock(h,tail);
    if(end==128)shaBlock(h,tail+64);
    for(int i=0;i<8;++i)for(int k=0;k<4;++k)hash[4*i+k]=uint8_t(h[i]>>(24-8*k));
    return true;
#endif
}

LoadStatus Lm::open(const uint8_t* d, size_t n) {
    *this=Lm{};
    if(!d)return LoadStatus::InvalidArgument;
    if(n<kHeaderBytes+kShaBytes)return LoadStatus::BadSize;
    if(std::memcmp(d,"HW1LM1\0\0",8))return LoadStatus::BadMagic;
    if(u32(d+8)!=1)return LoadStatus::BadVersion;
    if(u32(d+48)!=n)return LoadStatus::BadSize;
    const uint32_t V=u32(d+12), nb=u32(d+16), nt=u32(d+20), sb=u32(d+24), beam=u32(d+40);
    const float alpha=f32(d+28), beta=f32(d+32), unk=f32(d+36), prune=f32(d+44), bonus=f32(d+52);
    bool reserved=false;
    for(size_t i=56;i<kHeaderBytes;++i)reserved|=d[i]!=0;
    if(V<3 || V>65535 || !sb || !beam || beam>kMaxBeam || reserved || !std::isfinite(alpha) || !std::isfinite(beta)
       || !std::isfinite(unk) || !std::isfinite(prune) || !std::isfinite(bonus))return LoadStatus::BadHeader;
    // 64-bit section arithmetic cannot overflow from 32-bit counts.
    const uint64_t sizes[5]={4ull*V,4ull*V,sb,8ull*nb,8ull*nt};
    uint64_t starts[5], end=kHeaderBytes;
    for(int i=0;i<5;++i) { starts[i]=align4(end); end=starts[i]+sizes[i]; }
    const uint64_t digest=align4(end);
    if(digest+kShaBytes!=n)return LoadStatus::BadLayout;
    uint64_t previous=kHeaderBytes;
    for(int i=0;i<=5;++i) {
        const uint64_t start=i<5 ? starts[i] : digest;
        for(uint64_t p=previous;p<start;++p)if(d[p])return LoadStatus::BadPadding;
        if(i<5)previous=start+sizes[i];
    }
    uint8_t hash[32];
    if(!sha256(d,size_t(digest),hash) || std::memcmp(hash,d+digest,32))return LoadStatus::BadChecksum;
    const uint8_t* offsets=d+starts[1]; const char* strings=reinterpret_cast<const char*>(d+starts[2]);
    if(strings[sb-1])return LoadStatus::BadStrings;
    const char* previousWord=nullptr;
    for(uint32_t i=0;i<V;++i) {
        const uint32_t o=u32(offsets+4*i);
        if(o>=sb)return LoadStatus::BadStrings;
        if(previousWord && std::strcmp(previousWord,strings+o)>=0)return LoadStatus::Unsorted;
        previousWord=strings+o;
    }
    // Extremes of every quantised term, for log10Max/log10Min.
    int32_t biP[2]={INT16_MAX,INT16_MIN}, biBo[2]={0,0}, tri[2]={INT16_MAX,INT16_MIN};
    int32_t uniP[2]={INT16_MAX,INT16_MIN}, uniBo[2]={INT16_MAX,INT16_MIN};
    auto extend=[](int32_t (&range)[2], int32_t v) { range[0]=std::min(range[0],v); range[1]=std::max(range[1],v); };
    for(uint32_t i=0, prior=0;i<nb;++i) {
        const uint8_t* p=d+starts[3]+8ull*i;
        if(u16(p)>=V || u16(p+2)>=V)return LoadStatus::BadWordId;
        const uint32_t key=uint32_t(u16(p))<<16|u16(p+2);
        if(i && key<=prior)return LoadStatus::Unsorted;
        prior=key;
        extend(biP,i16(p+4)); extend(biBo,i16(p+6));
    }
    for(uint64_t i=0, prior=0;i<nt;++i) {
        const uint8_t* p=d+starts[4]+8*i;
        if(u16(p)>=V || u16(p+2)>=V || u16(p+4)>=V)return LoadStatus::BadWordId;
        const uint64_t key=uint64_t(u16(p))<<32|uint64_t(u16(p+2))<<16|u16(p+4);
        if(i && key<=prior)return LoadStatus::Unsorted;
        prior=key;
        extend(tri,i16(p+6));
    }
    for(uint32_t i=0;i<V;++i) { extend(uniP,i16(d+starts[0]+4*i)); extend(uniBo,i16(d+starts[0]+4*i+2)); }
    Lm view;
    view.data_=d;view.unigram_=d+starts[0];view.offsets_=offsets;view.strings_=d+starts[2];
    view.bigram_=d+starts[3];view.trigram_=d+starts[4];
    view.vocab_=V;view.bigrams_=nb;view.trigrams_=nt;view.strings_bytes_=sb;view.beam_=beam;
    view.alpha_=alpha;view.beta_=beta;view.unk_=unk;view.prune_=prune;view.bonus_=bonus;
    // log10() returns tri/1000.0, p2d, or (bigram backoff/1000.0 or 0.0) +
    // p2d, with p2d = bi/1000.0 or uniBo/1000.0 + uniP/1000.0. q/1000.0 and
    // the double sums are monotone in each term, so the same operations on
    // the extremes bound every computed value (biBo includes the 0.0 path).
    for(int k=0;k<2;++k) {
        double p2=uniBo[k]/1000.0+uniP[k]/1000.0;
        if(nb)p2=k ? std::max(p2,biP[k]/1000.0) : std::min(p2,biP[k]/1000.0);
        double v=biBo[k]/1000.0+p2;
        v=k ? std::max(v,p2) : std::min(v,p2);
        if(nt)v=k ? std::max(v,tri[k]/1000.0) : std::min(v,tri[k]/1000.0);
        (k ? view.log10Max_ : view.log10Min_)=v;
    }
    const int bos=view.find("<s>",3), eos=view.find("</s>",4), unkId=view.find("<unk>",5);
    if(bos<0 || eos<0 || unkId<0)return LoadStatus::MissingSpecial;
    view.bos_=uint16_t(bos);view.eos_=uint16_t(eos);view.unkId_=uint16_t(unkId);
    *this=view;
    return LoadStatus::Ok;
}
const char* Lm::word(uint16_t id) const {
    return data_ && id<vocab_ ? reinterpret_cast<const char*>(strings_+u32(offsets_+4*id)) : nullptr;
}
int Lm::find(const char* key, size_t length) const {
    if(!strings_ || (!key && length))return -1;
    size_t lo=0, hi=vocab_;
    while(lo<hi) {
        const size_t mid=lo+(hi-lo)/2;
        const int c=compareWord(reinterpret_cast<const char*>(strings_+u32(offsets_+4*mid)),key,length);
        if(!c)return int(mid);
        if(c<0)lo=mid+1; else hi=mid;
    }
    return -1;
}
long Lm::findBigram(uint16_t a, uint16_t b) const {
    const uint32_t key=uint32_t(a)<<16|b;
    size_t lo=0, hi=bigrams_;
    while(lo<hi) {
        const size_t mid=lo+(hi-lo)/2; const uint8_t* p=bigram_+8*mid;
        const uint32_t k=uint32_t(u16(p))<<16|u16(p+2);
        if(k==key)return long(mid);
        if(k<key)lo=mid+1; else hi=mid;
    }
    return -1;
}
long Lm::findTrigram(uint16_t a, uint16_t b, uint16_t c) const {
    const uint64_t key=uint64_t(a)<<32|uint64_t(b)<<16|c;
    size_t lo=0, hi=trigrams_;
    while(lo<hi) {
        const size_t mid=lo+(hi-lo)/2; const uint8_t* p=trigram_+8*mid;
        const uint64_t k=uint64_t(u16(p))<<32|uint64_t(u16(p+2))<<16|u16(p+4);
        if(k==key)return long(mid);
        if(k<key)lo=mid+1; else hi=mid;
    }
    return -1;
}
int32_t Lm::p2(uint16_t b, uint16_t c) const {
    const long i=findBigram(b,c);
    return i>=0 ? i16(bigram_+8*i+4) : i16(unigram_+4*b+2)+i16(unigram_+4*c);
}
// Doubles summed in hw1lm.py's order, each term q/1000.0.
double Lm::p2d(uint16_t b, uint16_t c) const {
    const long i=findBigram(b,c);
    return i>=0 ? i16(bigram_+8*i+4)/1000.0 : i16(unigram_+4*b+2)/1000.0+i16(unigram_+4*c)/1000.0;
}
double Lm::log10(uint16_t w2, uint16_t w1, uint16_t w) const {
    if(!data_ || w1>=vocab_ || w>=vocab_ || (w2!=kNoWord && w2>=vocab_))return std::numeric_limits<double>::quiet_NaN();
    if(w2==kNoWord)return p2d(w1,w);
    const long t=findTrigram(w2,w1,w);
    if(t>=0)return i16(trigram_+8*t+6)/1000.0;
    const long b=findBigram(w2,w1);
    return (b>=0 ? i16(bigram_+8*b+6)/1000.0 : 0.0)+p2d(w1,w);
}
int32_t Lm::score(uint16_t w2, uint16_t w1, uint16_t w) const {
    if(!data_ || w1>=vocab_ || w>=vocab_ || (w2!=kNoWord && w2>=vocab_))return kInvalidScore;
    if(w2==kNoWord)return p2(w1,w);
    const long t=findTrigram(w2,w1,w);
    if(t>=0)return i16(trigram_+8*t+6);
    const long b=findBigram(w2,w1);
    return (b>=0 ? i16(bigram_+8*b+6) : 0)+p2(w1,w);
}

size_t CustomWords::parse(const char* data, size_t bytes) {
    count_=0;
    if(!data)return 0;
    const auto p=reinterpret_cast<const uint8_t*>(data);
    LineWord line;
    for(size_t i=0;i<=bytes && count_<kMaxCustomWords;) {
        uint32_t cp='\n'; // the end of data ends the last line
        i+=i<bytes ? utf8(p+i,bytes-i,cp) : 1;
        if(!lineBreak(cp)) { feedLower(line,cp); continue; }
        char word[kMaxCustomWordBytes+1]; size_t length=0;
        if(line.finish(word,length)) { // sorted insert, first occurrence wins
            size_t lo=0, hi=count_; int c=1;
            while(lo<hi && c) {
                const size_t mid=lo+(hi-lo)/2;
                c=std::strcmp(words_[mid],word);
                if(c<0)lo=mid+1; else if(c>0)hi=mid;
            }
            if(c) {
                std::memmove(words_[lo+1],words_[lo],(count_-lo)*sizeof(words_[0]));
                std::memcpy(words_[lo],word,length+1); ++count_;
            }
        }
        line=LineWord{};
    }
    return count_;
}
bool CustomWords::contains(const char* word, size_t length) const {
    if(!word || !length || length>kMaxCustomWordBytes)return false;
    size_t lo=0, hi=count_;
    while(lo<hi) {
        const size_t mid=lo+(hi-lo)/2;
        const int c=compareWord(words_[mid],word,length);
        if(!c)return true;
        if(c<0)lo=mid+1; else hi=mid;
    }
    return false;
}

size_t workspace_bytes(size_t frames, size_t beam) {
    Layout l; return layout(frames,beam,l) ? l.bytes : 0;
}
DecodeStatus decode(const int8_t* logits, size_t frames, int exponent, const Lm& lm,
                    const CustomWords* words, char* text, size_t capacity,
                    const DecodeControl& control, size_t beam, DecodeStats* stats) {
    if(text && capacity)text[0]=0;
    if(stats)*stats=DecodeStats{};
    if(!beam)beam=lm.beamWidth();
    Layout l;
    if(!text || !capacity || (!logits && frames) || !lm.valid() || exponent<-30 || exponent>30
       || !layout(frames,beam,l))return DecodeStatus::InvalidArgument;
    if(control.cancelled && control.cancelled(control.context))return DecodeStatus::Cancelled;
    auto workspace=static_cast<uint8_t*>(allocate(l.bytes));
    if(!workspace)return DecodeStatus::OutOfMemory;
    DecodeStatus status;
    {
        Search search(lm,words,workspace,l,beam);
        status=search.run(logits,frames,exponent,control,text,capacity,stats);
    }
    release(workspace);
    if(stats)stats->workspaceBytes=l.bytes;
    if(status==DecodeStatus::Cancelled)text[0]=0;
    return status;
}
}
