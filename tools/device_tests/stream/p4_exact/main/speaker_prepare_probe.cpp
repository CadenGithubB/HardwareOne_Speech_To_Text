#include "speaker_prepare_probe.h"
#include "stt/speaker_model.h"
#include "stt/stt_dl_metadata.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "mbedtls/sha256.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <new>
#include <sys/stat.h>
#ifdef NDEBUG
#error "Prepare isolation probe requires enabled assertions"
#endif
#if !HW1_STT_SPEAKER_LABELS
#error "Prepare isolation probe requires the existing speaker backend"
#endif
extern "C" int hw1_dl_prepare_mode;
extern "C" uint32_t hw1_dl_prepare_gen;
namespace {
using hw1::stt::speaker::Model;
void* memory(size_t n){void* p=heap_caps_malloc(n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);assert(p);return p;}
void hexSha(const void* p,size_t n,char* output){
 unsigned char bytes[32];assert(mbedtls_sha256(static_cast<const unsigned char*>(p),n,bytes,0)==0);
 for(unsigned i=0;i<32;++i){std::sprintf(output+2*i,"%02x",bytes[i]);}
 output[64]=0;
}
struct Work {Model* model;const int16_t* pcm;size_t samples;float* result;SemaphoreHandle_t start,done;bool ok=false;};
void worker(void* p){
 auto& work=*static_cast<Work*>(p);
 for(;;){
  assert(xSemaphoreTake(work.start,portMAX_DELAY)==pdTRUE);
  work.ok=work.model->embed(work.pcm,work.samples,work.result);xSemaphoreGive(work.done);
 }
}
float cosine(const float* a,const float* b,size_t n){
 double dot=0,aa=0,bb=0;for(size_t i=0;i<n;++i){if(!std::isfinite(a[i])||!std::isfinite(b[i]))return NAN;dot+=double(a[i])*b[i];aa+=double(a[i])*a[i];bb+=double(b[i])*b[i];}
 return aa>0&&bb>0?float(dot/std::sqrt(aa*bb)):NAN;
}
}
void speaker_prepare_probe(){
 assert(hw1_dl_prepare_mode==0&&hw1::stt::installDlMetadataAllocator());
 struct stat info{};constexpr const char* path="/sd/STT Models/speaker.spk";assert(stat(path,&info)==0&&info.st_size>192);
 const size_t bytes=size_t(info.st_size);auto* blob=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));assert(blob);
 FILE* file=fopen(path,"rb");assert(file);
 for(size_t offset=0;offset<bytes;){size_t n=fread(blob+offset,1,std::min<size_t>(65536,bytes-offset),file);assert(n);offset+=n;}fclose(file);
 char raw[65];hexSha(blob,bytes,raw); // identity of the file before model construction
 auto* model=new(memory(sizeof(Model))) Model;Model::setLoadSelfTest(true);
 assert(model->load(blob,bytes,160000,hw1::stt::sttPsramAlloc,hw1::stt::sttPsramFree)==hw1::stt::speaker::LoadStatus::Ok);
 Model::setLoadSelfTest(false);const int fixtureResult=model->loadReport().testResult;
 printf("STT_EXACT {\"type\":\"speaker_fixture\",\"model_sha256\":\"%s\",\"status\":%d,\"passed\":%s}\n",raw,fixtureResult,fixtureResult==0?"true":"false");
 // Keep the fixture failure as a failed contract, then use a fresh model for
 // the independent repeatability/isolation experiment. No memory-fit claim
 // can be made from this diagnostic, including SDK self-test allocations.
 model->reset();file=fopen(path,"rb");assert(file);
 for(size_t offset=0;offset<bytes;){size_t n=fread(blob+offset,1,std::min<size_t>(65536,bytes-offset),file);assert(n);offset+=n;}fclose(file);
 char fresh[65];hexSha(blob,bytes,fresh);assert(!std::strcmp(raw,fresh));
 assert(model->load(blob,bytes,160000,hw1::stt::sttPsramAlloc,hw1::stt::sttPsramFree)==hw1::stt::speaker::LoadStatus::Ok);
 model->setMultiCore(false);
 const size_t samples=std::min<size_t>(160000,size_t(model->info().features.window_frames-1)*model->info().features.hop),dim=model->info().dim;assert(samples&&dim);
 auto* pcmA=static_cast<int16_t*>(memory(samples*sizeof(int16_t)));auto* pcmB=static_cast<int16_t*>(memory(samples*sizeof(int16_t)));
 uint32_t random=0x51a7b209;
 for(size_t i=0;i<samples;++i){pcmA[i]=int16_t((i&1?1:-1)*(600+(i*17%1000)));random=random*1664525u+1013904223u;pcmB[i]=int16_t(int(random>>19)-4096);}
 auto* vectors=static_cast<float*>(memory(5*dim*sizeof(float)));float* a=vectors;float* b=a+dim;float* repeatedA=b+dim;float* contended=repeatedA+dim;float* recovered=contended+dim;
 assert(model->embed(pcmA,samples,a));assert(model->embed(pcmB,samples,b));assert(model->embed(pcmA,samples,repeatedA));
 assert(!memcmp(a,repeatedA,dim*sizeof(float))&&memcmp(a,b,dim*sizeof(float))!=0);
 Work work{model,pcmB,samples,contended,xSemaphoreCreateBinary(),xSemaphoreCreateBinary()};assert(work.start&&work.done);TaskHandle_t task=nullptr;
 assert(xTaskCreatePinnedToCore(worker,"prepare_probe",8192,&work,1,&task,1)==pdPASS);
 // Negative control: task/core selection alone must preserve B's embedding.
 xSemaphoreGive(work.start);assert(xSemaphoreTake(work.done,pdMS_TO_TICKS(30000))==pdTRUE);
 assert(work.ok&&!memcmp(b,contended,dim*sizeof(float)));
 assert(model->embed(pcmA,samples,repeatedA)&&!memcmp(a,repeatedA,dim*sizeof(float)));
 std::fill(contended,contended+dim,0.f);
 const uint32_t savedGen=hw1_dl_prepare_gen;if(++hw1_dl_prepare_gen==0)++hw1_dl_prepare_gen;
 // The parent owns the prepare flag. The independent speaker worker must not
 // interpret that flag as permission to skip its own normal inference stages.
 hw1_dl_prepare_mode=1;xSemaphoreGive(work.start);assert(xSemaphoreTake(work.done,pdMS_TO_TICKS(30000))==pdTRUE);
 hw1_dl_prepare_mode=0;vTaskDelete(task);vSemaphoreDelete(work.start);vSemaphoreDelete(work.done);
 assert(model->embed(pcmB,samples,recovered));assert(!memcmp(b,recovered,dim*sizeof(float)));
 const bool altered=!work.ok||memcmp(b,contended,dim*sizeof(float))!=0,staleA=work.ok&&!memcmp(a,contended,dim*sizeof(float));
 char normal[65],during[65],after[65];hexSha(b,dim*sizeof(float),normal);hexSha(contended,dim*sizeof(float),during);hexSha(recovered,dim*sizeof(float),after);
 const float similarity=cosine(b,contended,dim);char similarityText[32];if(std::isfinite(similarity))std::snprintf(similarityText,sizeof(similarityText),"%.9f",double(similarity));else std::snprintf(similarityText,sizeof(similarityText),"null");
 printf("STT_EXACT {\"type\":\"prepare_isolation\",\"forced_other_task_flag\":true,\"model_sha256\":\"%s\",\"baseline_repeat_equal\":true,\"worker_normal_equal\":true,\"different_inputs_differ\":true,\"forced_embed_ok\":%s,\"altered\":%s,\"isolation_passed\":%s,\"stale_previous_embedding\":%s,\"normal_sha256\":\"%s\",\"forced_sha256\":\"%s\",\"recovered_sha256\":\"%s\",\"normal_vs_forced_cosine\":%s,\"recovered_equal\":true,\"limits\":\"Forced flag exposure proves a mechanism only; it does not establish overlap in acoustic captures\"}\n",
 raw,work.ok?"true":"false",altered?"true":"false",altered?"false":"true",staleA?"true":"false",normal,during,after,similarityText);
 model->~Model();heap_caps_free(model);heap_caps_free(vectors);heap_caps_free(pcmA);heap_caps_free(pcmB);heap_caps_free(blob);hw1_dl_prepare_gen=savedGen;
}
