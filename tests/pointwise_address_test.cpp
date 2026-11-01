// Call-level proof for the real extracted tiled loops. This substitutes only
// the assembly body and argument container; it does not emulate PIE arithmetic.
#include <algorithm>
#include <atomic>
#include <array>
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>
enum { Linear, ReLU, Other };
struct ConvArgsType {
    int input_channel=512,output_channel=512,c_remainder=0,n_remainder=0;
    int activation_type=Linear,mac_shift=0,n_div_x=0;
    int input_stride_y_offset=512,input_stride_x_offset=512;
    int output_y_offset=512,output_x_offset=512;
    void *filter_element=nullptr,*bias_element=nullptr,*tie_filter_channel_factor=nullptr;
    int filter_width=1,filter_height=1;
    std::array<int,4> untouched{{13,71,-9,12345}};
};
using conv_pie_fn_t=void(*)(void*,void*,void*);
bool conv_is_1x1(const ConvArgsType& a) {return a.filter_width==1 && a.filter_height==1;}
void* conv_ptr_add(void* p,int n,int bytes) {return static_cast<char*>(p)+size_t(n)*size_t(bytes);}
std::atomic<int> hw1_pointwise_scan{1};
std::atomic<uint32_t> hw1_pointwise_calls{0},hw1_pointwise_width1{0},hw1_pointwise_512{0};
namespace reference {
#include "pointwise_tiled_reference.inc"
}
namespace candidate {
#include "pointwise_tiled_candidate.inc"
}
using Record=std::array<int64_t,18>;
std::vector<Record> calls;
void* ibase;void* obase;void* fbase;void* bbase;void* qbase;
int64_t offset(void* p,void* base) {return p?int64_t(reinterpret_cast<uintptr_t>(p)-reinterpret_cast<uintptr_t>(base)):-1;}
void body(void* out,void* in,void* ptr) {
    const auto& a=*static_cast<ConvArgsType*>(ptr);
    calls.push_back({offset(in,ibase),offset(out,obase),offset(a.filter_element,fbase),
        offset(a.bias_element,bbase),offset(a.tie_filter_channel_factor,qbase),
        a.input_channel,a.output_channel,a.n_div_x,a.mac_shift,a.activation_type,
        a.input_stride_x_offset,a.input_stride_y_offset,a.output_x_offset,a.output_y_offset,
        a.untouched[0],a.untouched[1],a.untouched[2],a.untouched[3]});
}
struct Aligned {
    std::vector<char> data;void* pointer;
    explicit Aligned(size_t n):data(n+32),pointer(reinterpret_cast<void*>((reinterpret_cast<uintptr_t>(data.data())+15)&~uintptr_t(15))) {}
};
int main() {
    std::mt19937 rng(20261101);size_t cases=0,accepted=0,single_column=0,body_calls=0;
    for(unsigned trial=0;trial<600;++trial) {
        const int hvals[]={1,2,3,31,63,64,65,127};
        const int wvals[]={1,1,1,2,3,7};
        int height=hvals[rng()%8],width=wvals[rng()%6];
        const int feat_bytes=trial&1?1:2,filt_bytes=trial%3?1:2;
        ConvArgsType a;const int channels[]={64,128,256,512,1024};
        a.input_channel=channels[rng()%5];a.output_channel=channels[rng()%5];
        a.input_stride_x_offset=a.input_channel*(1+int(rng()%2));
        a.input_stride_y_offset=width*a.input_stride_x_offset+16*int(rng()%3);
        a.output_x_offset=a.output_channel+16*int(rng()%3);
        a.output_y_offset=width*a.output_x_offset+16*int(rng()%3);
        a.mac_shift=trial%2?INT_MIN:3;a.activation_type=trial%2?Linear:ReLU;
        Aligned in(size_t(height)*a.input_stride_y_offset*feat_bytes+16),
                out(size_t(height)*a.output_y_offset*feat_bytes+16),
                filter(size_t(a.input_channel)*a.output_channel*filt_bytes+16),
                bias(size_t(a.output_channel)*8+16),quant(size_t(a.output_channel)*feat_bytes+16);
        ibase=in.pointer;obase=out.pointer;fbase=filter.pointer;bbase=bias.pointer;qbase=quant.pointer;
        a.filter_element=fbase;a.bias_element=trial%3?bbase:nullptr;
        a.tie_filter_channel_factor=trial%3?qbase:nullptr;
        void* input=static_cast<char*>(ibase)+16*int(rng()%3);
        void* output=static_cast<char*>(obase)+16*int(rng()%3);
        // Fallback conditions and arbitrary body-rectangle origins/strides.
        if(trial%19==0) a.filter_width=3;
        if(trial%23==0) a.c_remainder=1;
        if(trial%29==0) a.n_remainder=1;
        if(trial%31==0) a.activation_type=Other;
        if(trial%37==0) input=static_cast<char*>(input)+1;
        if(trial%41==0) output=static_cast<char*>(output)+1;
        const int body_height=trial%43?height:0,body_width=trial%47?width:0;
        const auto kernel=trial%53?body:nullptr;
        calls.clear();const bool old=reference::conv_loop_pie_tiled(a,kernel,feat_bytes,filt_bytes,input,output,body_height,body_width);
        const auto original=calls;calls.clear();
        const bool now=candidate::conv_loop_pie_tiled(a,kernel,feat_bytes,filt_bytes,input,output,body_height,body_width);
        assert(old==now && calls==original);
        hw1_pointwise_scan=0;calls.clear();
        const bool control=candidate::conv_loop_pie_tiled(a,kernel,feat_bytes,filt_bytes,input,output,body_height,body_width);
        assert(old==control && calls==original);hw1_pointwise_scan=1;
        ++cases;body_calls+=calls.size();
        if(now) {++accepted;if(width==1)++single_column;}
    }
    assert(accepted>100 && single_column>50 && body_calls>10000);
    std::printf("pointwise address: %zu cases, %zu accepted, %zu single-column, %zu identical ordered body calls ok\n",cases,accepted,single_column,body_calls);
}
