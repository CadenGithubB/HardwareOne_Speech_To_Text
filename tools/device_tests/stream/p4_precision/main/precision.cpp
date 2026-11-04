// Isolated fixture/RAM experiment. Do not enter the product loop or start PDM,
// speaker workers, LM loading, network connections, or transcript persistence.
#define app_main unused_precision_captions_app_main
#include "main.cpp"
#undef app_main
#include "model_delta.h"
#include "stt_model_container.h"
#include "stt_dl_metadata.h"
#include "dl_model_base.hpp"
#include "mbedtls/sha256.h"
#include "esp_attr.h"
#include "esp_rom_sys.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <new>
#ifdef NDEBUG
#error "Precision probe requires assertions"
#endif
#if !CONFIG_HW1_STT_MODEL_LOCAL_PREPARE
#error "Precision probe requires the reviewed model-local preparation path"
#endif
extern const uint8_t deltaStart[] asm("_binary_precision_delta_start");
extern const uint8_t deltaEnd[] asm("_binary_precision_delta_end");

namespace {
namespace identity=hw1::stt::identity;
constexpr size_t kCandidateBytes=20153904;
constexpr size_t kDeltaBytes=670133;
constexpr uint8_t kCandidateSha[]={0x43,0x2c,0xa0,0xf4,0x9f,0x64,0xb2,0xc3,0x2b,0x97,0x29,0xcf,0xf4,0x6f,0xb5,0x1d,0xd0,0x42,0x10,0xb7,0xe5,0x0d,0xfa,0x82,0x88,0xfc,0x84,0x07,0x2e,0x2d,0x0c,0x26};
constexpr uint32_t kInternal=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT;
constexpr uint32_t kExternal=MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT;
DRAM_ATTR uint32_t phase=0;
static const DRAM_ATTR char kFailureFormat[]="STT_PRECISION_ALLOC_FAIL bytes=%u caps=%u phase=%u\n";
static_assert(__atomic_always_lock_free(sizeof(uint32_t),nullptr),"Failure phase must not need a lock");
void setPhase(uint32_t value){__atomic_store_n(&phase,value,__ATOMIC_RELAXED);}
void IRAM_ATTR allocationFailed(size_t bytes,uint32_t caps,const char*) {
    // ROM output, integer fields only: no allocation or heap traversal in the
    // failure callback. A failed request needs one contiguous block; this does
    // not distinguish fragmentation from insufficient total capacity.
    esp_rom_printf(kFailureFormat,
                   unsigned(bytes),unsigned(caps),unsigned(__atomic_load_n(&phase,__ATOMIC_RELAXED)));
}
struct Regions {intptr_t starts[32]{};size_t count=0;bool overflow=false;};
bool countRegion(walker_heap_into_t heap,walker_block_info_t,void* context) {
    auto& regions=*static_cast<Regions*>(context);
    for(size_t i=0;i<regions.count;++i)if(regions.starts[i]==heap.start)return false;
    if(regions.count==32){regions.overflow=true;return false;}
    regions.starts[regions.count++]=heap.start;return false;
}
Regions internalRegions,externalRegions;
size_t deltaLength() {
    const uintptr_t first=reinterpret_cast<uintptr_t>(deltaStart),last=reinterpret_cast<uintptr_t>(deltaEnd);
    assert(last>=first);return size_t(last-first);
}
struct HeapWindow {
    const char* model;const char* operation;unsigned iteration,frames;int64_t start;
    HeapWindow(const char* m,const char* op,unsigned it,unsigned f=663):model(m),operation(op),iteration(it),frames(f) {
        assert(heap_caps_monitor_local_minimum_free_size_start()==ESP_OK);
        start=esp_timer_get_time();
    }
    void finish(int numericalGate) {
        const int64_t elapsed=esp_timer_get_time()-start;
        // Query BEFORE stop restores the lifetime minima. Allocator-maintained
        // per-region minima observe transient events between stage checkpoints.
        const size_t internalTotal=heap_caps_get_total_size(kInternal);
        const size_t externalTotal=heap_caps_get_total_size(kExternal);
        const size_t internalMin=heap_caps_get_minimum_free_size(kInternal);
        const size_t externalMin=heap_caps_get_minimum_free_size(kExternal);
        const size_t internalLargest=heap_caps_get_largest_free_block(kInternal);
        const size_t externalLargest=heap_caps_get_largest_free_block(kExternal);
        assert(heap_caps_monitor_local_minimum_free_size_stop()==ESP_OK);
        printf("STT_PRECISION {\"type\":\"memory_window\",\"model\":\"%s\",\"operation\":\"%s\",\"iteration\":%u,\"frames\":%u,\"elapsed_us\":%lld,\"numerical_gate_passed\":%s,\"internal_peak_used_upper_bytes\":%u,\"psram_peak_used_upper_bytes\":%u,\"internal_peak_exact\":%s,\"psram_peak_exact\":%s,\"internal_largest_at_end\":%u,\"psram_largest_at_end\":%u,\"internal_heap_total_bytes\":%u,\"psram_heap_total_bytes\":%u,\"internal_min_free_bytes\":%u,\"psram_min_free_bytes\":%u}\n",
               model,operation,iteration,frames,(long long)elapsed,numericalGate<0?"null":numericalGate?"true":"false",
               unsigned(internalTotal-internalMin),unsigned(externalTotal-externalMin),
               internalRegions.count==1&&!internalRegions.overflow?"true":"false",
               externalRegions.count==1&&!externalRegions.overflow?"true":"false",
               unsigned(internalLargest),unsigned(externalLargest),
               unsigned(internalTotal),unsigned(externalTotal),unsigned(internalMin),unsigned(externalMin));
    }
};
void digest(const void* data,size_t bytes,uint8_t* hash) {
    assert(mbedtls_sha256(static_cast<const unsigned char*>(data),bytes,hash,0)==0);
}
void hex(const uint8_t* hash,char* out) {
    constexpr char digits[]="0123456789abcdef";
    for(unsigned i=0;i<32;++i){out[i*2]=digits[hash[i]>>4];out[i*2+1]=digits[hash[i]&15];}out[64]=0;
}
size_t readBase(void* context,size_t offset,void* destination,size_t bytes) {
    FILE* f=static_cast<FILE*>(context);
    if(offset>identity::kRawBytes||bytes>identity::kRawBytes-offset)return 0;
    if(fseek(f,long(hw1::stt::container::kHeaderBytes+offset),SEEK_SET))return 0;
    return fread(destination,1,bytes,f);
}
void yield(){vTaskDelay(1);}
void verifyBase(FILE* file) {
    static_assert(identity::kCodec==0,"Only the pinned stored envelope is supported");
    struct stat info{};assert(fstat(fileno(file),&info)==0);ModelFile source{file};
    assert(hw1::stt::container::read_header(&source,size_t(info.st_size),readModel));
    auto* chunk=static_cast<uint8_t*>(heap_caps_malloc(65536,kExternal));assert(chunk);
    mbedtls_sha256_context sha;mbedtls_sha256_init(&sha);assert(mbedtls_sha256_starts(&sha,0)==0);
    for(size_t at=0;at<identity::kRawBytes;) {
        const size_t n=std::min<size_t>(65536,identity::kRawBytes-at);
        assert(readBase(file,at,chunk,n)==n);assert(mbedtls_sha256_update(&sha,chunk,n)==0);at+=n;yield();
    }
    uint8_t hash[32];assert(mbedtls_sha256_finish(&sha,hash)==0);mbedtls_sha256_free(&sha);
    heap_caps_free(chunk);assert(!std::memcmp(hash,identity::kRawSha,32));
}
bool fixture(dl::Model* model,const char* name,unsigned iteration, bool prepare,
             dl::runtime_mode_t mode) {
    auto* graph=model->get_fbs_model();assert(graph);graph->load_map();
    auto& inputs=model->get_inputs();auto& outputs=model->get_outputs();
    assert(inputs.size()==1&&outputs.size()==1);
    const auto tests=graph->get_test_outputs_name();
    assert(tests.size()==1&&tests[0]==outputs.begin()->first);
    auto* input=inputs.begin()->second;auto* output=outputs.begin()->second;
    auto* testInput=graph->get_test_input_tensor(inputs.begin()->first);
    auto* expected=graph->get_test_output_tensor(outputs.begin()->first);
    assert(input&&output&&testInput&&expected&&input->assign(testInput));
    assert(input->dtype==dl::DATA_TYPE_INT8&&input->shape==std::vector<int>({1,663,1,64}));
    assert(testInput->dtype==input->dtype&&testInput->shape==input->shape);
    assert(input->exponent.is_valid()&&!input->exponent.is_per_channel()&&int(input->exponent)==-4);
    assert(output->dtype==dl::DATA_TYPE_INT8&&expected->dtype==output->dtype&&output->shape==expected->shape&&output->get_bytes()==expected->get_bytes());
    assert(output->shape==std::vector<int>({1,332,1,29}));
    assert(output->exponent.is_valid()&&!output->exponent.is_per_channel()&&int(output->exponent)==-1);
    assert(expected->exponent.is_valid()&&!expected->exponent.is_per_channel()&&int(expected->exponent)==-1);
    uint8_t inputHash[32];digest(input->data,input->get_bytes(),inputHash);
    HeapWindow window(name,"prepare_and_infer",iteration);
#ifdef HW1_PRECISION_TRACE
    const auto names=graph->topological_sort();
    assert(names.size()==size_t(model->module_count()));
#endif
    setPhase(100);
    if(prepare)model->prepare_args(mode);
    for(int stage=0;stage<model->module_count();++stage) {
        setPhase(1000+unsigned(stage));model->run(model->module_count(),stage,mode);
#ifdef HW1_PRECISION_TRACE
        if(iteration==0) {
            std::vector<std::string> sources,targets;
            assert(graph->get_operation_inputs_and_outputs(names[stage],sources,targets)==ESP_OK);
            for(const auto& target:targets) {
                auto* tensor=model->get_intermediate(target);
                assert(tensor&&tensor->data);
                uint8_t bytes[32];char sha[65];
                digest(tensor->data,tensor->get_bytes(),bytes);hex(bytes,sha);
                printf("STT_TENSOR %s %d %d %d %s %s\n",name,int(prepare),int(mode),stage,target.c_str(),sha);
            }
        }
#endif
        yield();
    }
    // Exact own-fixture comparison, no tolerance expansion to obtain a pass.
    const bool equal=!std::memcmp(output->data,expected->data,output->get_bytes());
    window.finish(equal);
    size_t unequal=0;int maximum=0;const auto* actual=static_cast<const int8_t*>(output->data);
    const auto* reference=static_cast<const int8_t*>(expected->data);
    for(size_t i=0;i<size_t(output->get_bytes());++i){const int error=std::abs(int(actual[i])-int(reference[i]));unequal+=error!=0;maximum=std::max(maximum,error);}
    char in[65],out[65],ref[65];uint8_t hash[32];hex(inputHash,in);digest(output->data,output->get_bytes(),hash);hex(hash,out);digest(expected->data,expected->get_bytes(),hash);hex(hash,ref);
    printf("STT_PRECISION {\"type\":\"fixture\",\"model\":\"%s\",\"iteration\":%u,\"frames\":663,\"modules\":%u,\"input_sha256\":\"%s\",\"output_sha256\":\"%s\",\"expected_sha256\":\"%s\",\"unequal\":%u,\"max_abs_error\":%d,\"passed\":%s}\n",name,iteration,unsigned(model->module_count()),in,out,ref,unsigned(unequal),maximum,equal?"true":"false");
    delete testInput;delete expected;graph->clear_map();return equal;
}
bool oneModel(FILE* file,const char* name,bool candidate,bool workloads=false,
              bool prepare=true,dl::runtime_mode_t mode=dl::RUNTIME_MODE_MULTI_CORE) {
    const size_t bytes=candidate?kCandidateBytes:identity::kRawBytes;
    printf("STT_PRECISION {\"type\":\"model_begin\",\"model\":\"%s\",\"bytes\":%u}\n",name,unsigned(bytes));
    setPhase(candidate?20:10);HeapWindow load(name,workloads?"workload_raw_load":"raw_load",0,workloads?0:663);
    auto* raw=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,bytes,kExternal));assert(raw);
    if(candidate) {
        hw1::diagnostic::ModelDelta delta;
        assert(hw1::diagnostic::parseModelDelta(deltaStart,deltaLength(),identity::kRawBytes,identity::kRawSha,kCandidateSha,bytes,delta));
        assert(hw1::diagnostic::applyModelDelta(delta,readBase,file,raw,bytes,yield));
    } else for(size_t at=0;at<bytes;) {
        const size_t n=std::min<size_t>(65536,bytes-at);assert(readBase(file,at,raw+at,n)==n);at+=n;yield();
    }
    uint8_t hash[32];digest(raw,bytes,hash);assert(!std::memcmp(hash,candidate?kCandidateSha:identity::kRawSha,32));
    load.finish(workloads?1:-1);
    if(workloads) {
        bool stable=true;
        for(unsigned frames:{100u,1000u,2000u}) {
            printf("STT_PRECISION {\"type\":\"workload_begin\",\"model\":\"%s\",\"frames\":%u}\n",name,frames);
            setPhase(candidate?21:11);HeapWindow build(name,"workload_construct",0,frames);
            const std::map<std::string,std::vector<int>> shapes{{identity::kInputName,{1,int(frames),1,64}}};
            auto* model=new(std::nothrow) dl::Model(reinterpret_cast<const char*>(raw),fbs::MODEL_LOCATION_IN_FLASH_RODATA,0,dl::MEMORY_MANAGER_GREEDY,nullptr,false,shapes);assert(model);
            build.finish(1);
            auto& inputs=model->get_inputs();auto& outputs=model->get_outputs();assert(inputs.size()==1&&outputs.size()==1);
            auto* input=inputs.begin()->second;auto* output=outputs.begin()->second;assert(input&&output&&input->data&&output->data);
            assert(input->dtype==dl::DATA_TYPE_INT8&&input->shape==std::vector<int>({1,int(frames),1,64}));
            assert(output->dtype==dl::DATA_TYPE_INT8&&output->shape==std::vector<int>({1,int((frames+1)/2),1,29}));
            assert(input->exponent.is_valid()&&!input->exponent.is_per_channel()&&int(input->exponent)==-4);
            assert(output->exponent.is_valid()&&!output->exponent.is_per_channel()&&int(output->exponent)==-1);
            uint8_t cold[32]{};
            for(unsigned iteration=0;iteration<3;++iteration) {
                auto* values=static_cast<int8_t*>(input->data);
                for(size_t i=0;i<size_t(input->get_bytes());++i)values[i]=int8_t(int((i*17+3)%127)-63);
                uint8_t inHash[32],outHash[32];digest(input->data,input->get_bytes(),inHash);
                HeapWindow inference(name,"workload_prepare_and_infer",iteration,frames);
                setPhase(100);model->prepare_args(dl::RUNTIME_MODE_MULTI_CORE);
                for(int stage=0;stage<model->module_count();++stage) {
                    setPhase(1000+unsigned(stage));model->run(model->module_count(),stage,dl::RUNTIME_MODE_MULTI_CORE);yield();
                }
                inference.finish(1);digest(output->data,output->get_bytes(),outHash);
                if(!iteration)std::memcpy(cold,outHash,32);
                const bool equal=!std::memcmp(cold,outHash,32);stable=stable&&equal;
                char in[65],out[65];hex(inHash,in);hex(outHash,out);
                printf("STT_PRECISION {\"type\":\"workload\",\"model\":\"%s\",\"frames\":%u,\"iteration\":%u,\"input_sha256\":\"%s\",\"output_sha256\":\"%s\",\"cold_warm_equal\":%s}\n",name,frames,iteration,in,out,equal?"true":"false");
            }
            delete model;
        }
        heap_caps_free(raw);setPhase(0);return stable;
    }
    setPhase(candidate?21:11);HeapWindow build(name,"model_construct",0);
    auto* model=new(std::nothrow) dl::Model(reinterpret_cast<const char*>(raw),fbs::MODEL_LOCATION_IN_FLASH_RODATA,0,dl::MEMORY_MANAGER_GREEDY,nullptr,false);assert(model);
    build.finish(-1);
    bool passed=true;
    for(unsigned iteration=0;iteration<3;++iteration)passed=fixture(model,name,iteration,prepare,mode)&&passed;
    delete model;
    heap_caps_free(raw);setPhase(0);return passed;
}
}
extern "C" void app_main() {
    printf("STT_PRECISION {\"type\":\"begin\",\"scope\":\"Isolated fixed-length own-fixture cold/warm probe; no LM/PDM/speaker worker; memory remains uninterpreted if fixture fails\"}\n");
    assert(mountCard());vTaskPrioritySet(nullptr,2);assert(hw1::stt::installDlMetadataAllocator());
    assert(deltaLength()==kDeltaBytes);
    assert(heap_caps_register_failed_alloc_callback(allocationFailed)==ESP_OK);
    heap_caps_walk(kInternal,countRegion,&internalRegions);heap_caps_walk(kExternal,countRegion,&externalRegions);
    assert(!internalRegions.overflow&&!externalRegions.overflow&&internalRegions.count&&externalRegions.count);
    printf("STT_PRECISION {\"type\":\"heap_regions\",\"internal\":%u,\"psram\":%u,\"internal_caps\":%u,\"psram_caps\":%u,\"embedded_delta_bytes\":%u,\"aggregate_peak_rule\":\"exact only for a single verified physical heap; otherwise sum-of-minima upper bound\"}\n",unsigned(internalRegions.count),unsigned(externalRegions.count),unsigned(kInternal),unsigned(kExternal),unsigned(deltaLength()));
    FILE* file=fopen(kModelPath,"rb");assert(file);verifyBase(file);
    bool control=true,candidate=true,stable=false;
#ifdef HW1_PRECISION_TRACE
    // A constructor may rewrite private bias storage. Reconstruct model bytes
    // for each arm so ordinary and prepared calls have independent cold starts.
    for(bool mixed:{false,true})for(bool prepare:{false,true})for(auto mode:{dl::RUNTIME_MODE_SINGLE_CORE,dl::RUNTIME_MODE_MULTI_CORE}) {
        const char* name=mixed?"block14":"control";
        printf("STT_MODE %s %d %d\n",name,int(prepare),int(mode));
        const bool passed=oneModel(file,name,mixed,false,prepare,mode);
        if(mixed)candidate=candidate&&passed;else control=control&&passed;
    }
    constexpr bool workloads=false;
#else
    control=oneModel(file,"control",false);
    candidate=oneModel(file,"block14",true);
    const bool workloads=control&&candidate;
    if(workloads) {stable=oneModel(file,"control",false,true);stable=oneModel(file,"block14",true,true)&&stable;}
#endif
    fclose(file);
    printf("STT_PRECISION {\"type\":\"complete\",\"control_fixture_passed\":%s,\"candidate_fixture_passed\":%s,\"workloads_ran\":%s,\"workloads_cold_warm_stable\":%s,\"production_ram_fit_qualified\":false}\n",control?"true":"false",candidate?"true":"false",workloads?"true":"false",stable?"true":"false");
    for(;;)vTaskDelay(pdMS_TO_TICKS(1000));
}
