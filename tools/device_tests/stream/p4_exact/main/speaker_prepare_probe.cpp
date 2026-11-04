#include "speaker_prepare_probe.h"
#include "stt/speaker_model.h"
#include "stt/stt_dl_metadata.h"
#include "dl_model_base.hpp"
#include "dl_module_creator.hpp"
#include "dl_module_relu.hpp"
#include "dl_tool_metadata.hpp"
#include "dl_base_conv_args.hpp"
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
#ifdef HW1_SPEAKER_TRACE_REFERENCE
#include HW1_SPEAKER_TRACE_REFERENCE
#endif
#ifdef NDEBUG
#error "Prepare isolation probe requires enabled assertions"
#endif
#if !HW1_STT_SPEAKER_LABELS
#error "Prepare isolation probe requires the existing speaker backend"
#endif
extern "C" int hw1_dl_prepare_mode;
extern "C" uint32_t hw1_dl_prepare_gen;
namespace dl::base { extern int hw1_dl_conv_block_bytes; }
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
void traceFixtureStage(dl::Model* model,int stage,const char* moduleName,bool exactRelu){
#ifdef HW1_SPEAKER_TRACE_REFERENCE
 assert(moduleName);
 for(const auto& point:kSpeakerTracePoints){
  if(std::strcmp(moduleName,point.module))continue;
  auto* tensor=model->get_intermediate(point.tensor);assert(tensor&&tensor->data);
  assert(tensor->dtype==dl::DATA_TYPE_INT16&&size_t(tensor->get_bytes())==point.elements*2&&int(tensor->exponent)==point.exponent);
  const auto* actual=static_cast<const int16_t*>(tensor->data);unsigned over=0;int maxError=0;
  for(unsigned k=0;k<point.count;++k){assert(point.indices[k]<point.elements);int e=std::abs(int(actual[point.indices[k]])-int(point.values[k]));over+=e>1;maxError=std::max(maxError,e);}
  char digest[65];hexSha(tensor->data,tensor->get_bytes(),digest);
  printf("STT_EXACT {\"type\":\"speaker_trace\",\"exact_relu\":%s,\"stage\":%d,\"module\":\"%s\",\"tensor\":\"%s\",\"samples\":%u,\"sample_over_tolerance\":%u,\"sample_max_abs_error\":%d,\"actual_sha256\":\"%s\",\"reference_validated\":false}\n",exactRelu?"true":"false",stage,point.module,point.tensor,point.count,over,maxError,digest);
 }
#else
 (void)model;(void)stage;(void)moduleName;(void)exactRelu;
#endif
}
// Exercise the file's embedded quantized fixture directly, without frontend,
// pooling or clustering. Reload weights for every case: Conv bias setup may
// mutate its private copy. Report all differences rather than stopping at one.
void fixtureMatrix(const char* path,size_t bytes){
 const int savedBlock=dl::base::hw1_dl_conv_block_bytes;
 const bool reluModes[]={false,
#if HW1_SPEAKER_EXACT_RELU_PROBE
 true,
#endif
 };
 for(bool exactRelu:reluModes)for(int block:{0,24*1024})for(bool multi:{false,true}){
#if HW1_SPEAKER_EXACT_RELU_PROBE
  auto* creator=dl::module::ModuleCreator::get_instance();creator->register_dl_modules();
  if(exactRelu)creator->register_module("Relu",[](fbs::FbsModel* source,std::string name)->dl::module::Module*{
   dl::quant_type_t type;source->get_operation_attribute(name,"quant_type",type);
   return new dl::module::Relu(name.c_str(),dl::MODULE_INPLACE_CHANGED_BUFFER,type);
  });
  else creator->register_module("Relu",dl::module::Relu::deserialize);
#endif
  auto* blob=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));assert(blob);
  FILE* file=fopen(path,"rb");assert(file);
  for(size_t offset=0;offset<bytes;){size_t n=fread(blob+offset,1,std::min<size_t>(65536,bytes-offset),file);assert(n);offset+=n;}fclose(file);
  uint32_t offset=0;std::memcpy(&offset,blob+60,sizeof(offset));assert(offset%16==0&&offset<bytes-32);
  dl::base::hw1_dl_conv_block_bytes=block;
  auto* model=new(std::nothrow) dl::Model(reinterpret_cast<const char*>(blob+offset),fbs::MODEL_LOCATION_IN_FLASH_RODATA,0,dl::MEMORY_MANAGER_GREEDY,nullptr,false);assert(model);
  auto* fbs=model->get_fbs_model();assert(fbs);fbs->load_map();
  // Module::name is optional in this SDK. The execution plan is built in this
  // exact topological order; retain the names privately for this diagnostic.
  const auto moduleNames=fbs->topological_sort();assert(moduleNames.size()==size_t(model->module_count()));
  auto& inputs=model->get_inputs();auto& outputs=model->get_outputs();assert(inputs.size()==1&&outputs.size()==1);
  auto* input=inputs.begin()->second;auto* output=outputs.begin()->second;
  auto* testInput=fbs->get_test_input_tensor(inputs.begin()->first);auto* expected=fbs->get_test_output_tensor(outputs.begin()->first);
  assert(testInput&&expected&&input->assign(testInput));
  assert(output->dtype==dl::DATA_TYPE_INT16&&expected->dtype==output->dtype&&output->shape==expected->shape&&output->get_bytes()==expected->get_bytes());
  char inputHash[65];hexSha(input->data,input->get_bytes(),inputHash);
  for(int i=0;i<model->module_count();++i){
   model->run(model->module_count(),i,multi?dl::RUNTIME_MODE_MULTI_CORE:dl::RUNTIME_MODE_SINGLE_CORE);
   if(block==0&&!multi)traceFixtureStage(model,i,moduleNames[i].c_str(),exactRelu);
   vTaskDelay(1);
  }
  const auto* actual=static_cast<const int16_t*>(output->data);const auto* reference=static_cast<const int16_t*>(expected->data);
  size_t unequal=0,overTolerance=0;int maxError=0;uint64_t totalError=0;
  for(size_t i=0;i<output->get_bytes()/sizeof(int16_t);++i){int error=std::abs(int(actual[i])-int(reference[i]));unequal+=error!=0;overTolerance+=error>1;maxError=std::max(maxError,error);totalError+=unsigned(error);}
  char actualHash[65],expectedHash[65];hexSha(output->data,output->get_bytes(),actualHash);hexSha(expected->data,expected->get_bytes(),expectedHash);
  printf("STT_EXACT {\"type\":\"speaker_fixture_matrix\",\"exact_relu\":%s,\"block_bytes\":%d,\"multi_core\":%s,\"input_sha256\":\"%s\",\"output_sha256\":\"%s\",\"expected_sha256\":\"%s\",\"elements\":%u,\"unequal\":%u,\"over_tolerance\":%u,\"max_abs_error\":%d,\"sum_abs_error\":%llu,\"passed\":%s}\n",exactRelu?"true":"false",block,multi?"true":"false",inputHash,actualHash,expectedHash,unsigned(output->get_bytes()/2),unsigned(unequal),unsigned(overTolerance),maxError,(unsigned long long)totalError,overTolerance?"false":"true");
  delete testInput;delete expected;fbs->clear_map();delete model;heap_caps_free(blob);
 }
#if HW1_SPEAKER_EXACT_RELU_PROBE
 dl::module::ModuleCreator::get_instance()->register_module("Relu",dl::module::Relu::deserialize);
#endif
 dl::base::hw1_dl_conv_block_bytes=savedBlock;
}
#if HW1_SPEAKER_PREPARE_FAILURE_PROBE
#if !CONFIG_HW1_STT_MODEL_LOCAL_PREPARE
#error "Prepare failure probe requires model-local preparation"
#endif
// Quiescent diagnostic only: preserve the installed allocator's placement and
// free contract, rejecting only large Module requests during prepare_args().
// The fixed speaker graph's temporary args/factors are below this threshold;
// its optional Prepared blocks include two args plus a 16-byte header.
const dl::tool::MetadataAllocator* failureDelegate=nullptr;
static_assert(sizeof(void*)==4,"Prepared-block threshold is for the P4 ABI");
constexpr size_t kPreparedMinimum=(16+2*sizeof(dl::base::ConvArgsType)+15)&~size_t(15);
unsigned prepareRejections=0;
void* refusePrepared(size_t size,size_t align,dl::tool::MetadataKind kind){
 if(kind==dl::tool::MetadataKind::Module&&size>=kPreparedMinimum){++prepareRejections;return nullptr;}
 return failureDelegate->alloc(size,align,kind);
}
void delegateFree(void* ptr){failureDelegate->free(ptr);}
const dl::tool::MetadataAllocator failureAllocator{refusePrepared,delegateFree};
void prepareFailureProbe(dl::Model* model,const char* modelSha){
 auto* graph=model->get_fbs_model();assert(graph);graph->load_map();auto& inputs=model->get_inputs();auto& outputs=model->get_outputs();assert(inputs.size()==1&&outputs.size()==1);
 auto* fixture=graph->get_test_input_tensor(inputs.begin()->first);assert(fixture);
 auto* input=inputs.begin()->second;auto* output=outputs.begin()->second;assert(input&&output&&input->data&&output->data&&input->assign(fixture));
 // Greedy arenas may reuse the input's storage after its last reader. Restore
 // the fixture before EVERY inference rather than assuming run preserves it.
 auto run=[&](){assert(input->assign(fixture));for(int i=0;i<model->module_count();++i){model->run(model->module_count(),i,dl::RUNTIME_MODE_MULTI_CORE);vTaskDelay(1);}};
 run();char baseline[65],inputBefore[65],outputBefore[65],after[65];hexSha(output->data,output->get_bytes(),baseline);
 assert(input->assign(fixture));hexSha(input->data,input->get_bytes(),inputBefore);hexSha(output->data,output->get_bytes(),outputBefore);
 failureDelegate=dl::tool::get_metadata_allocator();assert(failureDelegate&&failureDelegate!=&failureAllocator);prepareRejections=0;
 dl::tool::set_metadata_allocator(&failureAllocator);
 model->prepare_args(dl::RUNTIME_MODE_MULTI_CORE);
 dl::tool::set_metadata_allocator(failureDelegate);
 assert(prepareRejections>0);
 hexSha(input->data,input->get_bytes(),after);assert(!std::strcmp(inputBefore,after));
 hexSha(output->data,output->get_bytes(),after);assert(!std::strcmp(outputBefore,after));
 run();hexSha(output->data,output->get_bytes(),after);assert(!std::strcmp(baseline,after));
 model->prepare_args(dl::RUNTIME_MODE_MULTI_CORE);run();hexSha(output->data,output->get_bytes(),after);assert(!std::strcmp(baseline,after));
 printf("STT_EXACT {\"type\":\"prepare_failure_fallback\",\"model_sha256\":\"%s\",\"rejected_optional_allocations\":%u,\"threshold_bytes\":%u,\"failed_prepare_activation_unchanged\":true,\"fallback_output_equal\":true,\"normal_prepare_recovery_equal\":true,\"output_sha256\":\"%s\",\"scope\":\"Quiescent allocator-policy rejection; not real heap exhaustion or RAM-fit qualification\"}\n",modelSha,prepareRejections,unsigned(kPreparedMinimum),baseline);
 delete fixture;graph->clear_map();
}
#endif
}
void speaker_prepare_probe(){
 assert(hw1_dl_prepare_mode==0&&hw1::stt::installDlMetadataAllocator());
 struct stat info{};constexpr const char* path="/sd/STT Models/speaker.spk";assert(stat(path,&info)==0&&info.st_size>192);
 const size_t bytes=size_t(info.st_size);auto* blob=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));assert(blob);
 FILE* file=fopen(path,"rb");assert(file);
 for(size_t offset=0;offset<bytes;){size_t n=fread(blob+offset,1,std::min<size_t>(65536,bytes-offset),file);assert(n);offset+=n;}fclose(file);
 char raw[65];hexSha(blob,bytes,raw); // identity of the file before model construction
 fixtureMatrix(path,bytes);
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
 unsigned otherPrepareCalls=0;
#if CONFIG_HW1_STT_MODEL_LOCAL_PREPARE
 // Exercise the new API on a real, independent model while B executes. Keep
 // its weights separate so bias setup cannot be mistaken for shared input.
 auto* otherBlob=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));assert(otherBlob);
 file=fopen(path,"rb");assert(file);
 for(size_t offset=0;offset<bytes;){size_t n=fread(otherBlob+offset,1,std::min<size_t>(65536,bytes-offset),file);assert(n);offset+=n;}fclose(file);
 char otherRaw[65];hexSha(otherBlob,bytes,otherRaw);assert(!std::strcmp(raw,otherRaw));
 uint32_t trunkOffset=0;std::memcpy(&trunkOffset,otherBlob+60,sizeof(trunkOffset));assert(trunkOffset%16==0&&trunkOffset<bytes-32);
 auto* otherModel=new(std::nothrow) dl::Model(reinterpret_cast<const char*>(otherBlob+trunkOffset),fbs::MODEL_LOCATION_IN_FLASH_RODATA,0,dl::MEMORY_MANAGER_GREEDY,nullptr,false);assert(otherModel);
#if HW1_SPEAKER_PREPARE_FAILURE_PROBE
 // The independent speaker worker is blocked on work.start here; no other
 // model uses metadata while this temporary diagnostic allocator is installed.
 prepareFailureProbe(otherModel,raw);
#endif
 auto inputs=otherModel->get_inputs(),outputs=otherModel->get_outputs();assert(inputs.size()==1&&outputs.size()==1);
 auto* input=inputs.begin()->second;auto* output=outputs.begin()->second;assert(input&&output&&input->data&&output->data);
 std::memset(input->data,0x37,input->get_bytes());std::memset(output->data,0x51,output->get_bytes());
 char inputBefore[65],outputBefore[65];hexSha(input->data,input->get_bytes(),inputBefore);hexSha(output->data,output->get_bytes(),outputBefore);
#endif
 const uint32_t savedGen=hw1_dl_prepare_gen;if(++hw1_dl_prepare_gen==0)++hw1_dl_prepare_gen;
 // The parent owns the prepare flag. The independent speaker worker must not
 // interpret that flag as permission to skip its own normal inference stages.
 hw1_dl_prepare_mode=1;xSemaphoreGive(work.start);
#if CONFIG_HW1_STT_MODEL_LOCAL_PREPARE
 const TickType_t deadline=xTaskGetTickCount()+pdMS_TO_TICKS(30000);
 while(xSemaphoreTake(work.done,0)!=pdTRUE){
  otherModel->prepare_args(dl::RUNTIME_MODE_MULTI_CORE);++otherPrepareCalls;vTaskDelay(1);
  assert(int32_t(deadline-xTaskGetTickCount())>0);
 }
 assert(otherPrepareCalls>0);
 char unchanged[65];hexSha(input->data,input->get_bytes(),unchanged);assert(!std::strcmp(inputBefore,unchanged));
 hexSha(output->data,output->get_bytes(),unchanged);assert(!std::strcmp(outputBefore,unchanged));
#else
 assert(xSemaphoreTake(work.done,pdMS_TO_TICKS(30000))==pdTRUE);
#endif
 hw1_dl_prepare_mode=0;vTaskDelete(task);vSemaphoreDelete(work.start);vSemaphoreDelete(work.done);
#if CONFIG_HW1_STT_MODEL_LOCAL_PREPARE
 delete otherModel;heap_caps_free(otherBlob);
#endif
 assert(model->embed(pcmB,samples,recovered));assert(!memcmp(b,recovered,dim*sizeof(float)));
 const bool altered=!work.ok||memcmp(b,contended,dim*sizeof(float))!=0,staleA=work.ok&&!memcmp(a,contended,dim*sizeof(float));
 char normal[65],during[65],after[65];hexSha(b,dim*sizeof(float),normal);hexSha(contended,dim*sizeof(float),during);hexSha(recovered,dim*sizeof(float),after);
 const float similarity=cosine(b,contended,dim);char similarityText[32];if(std::isfinite(similarity))std::snprintf(similarityText,sizeof(similarityText),"%.9f",double(similarity));else std::snprintf(similarityText,sizeof(similarityText),"null");
 printf("STT_EXACT {\"type\":\"prepare_isolation\",\"forced_other_task_flag\":true,\"other_model_prepare_calls\":%u,\"model_sha256\":\"%s\",\"baseline_repeat_equal\":true,\"worker_normal_equal\":true,\"different_inputs_differ\":true,\"forced_embed_ok\":%s,\"altered\":%s,\"isolation_passed\":%s,\"stale_previous_embedding\":%s,\"normal_sha256\":\"%s\",\"forced_sha256\":\"%s\",\"recovered_sha256\":\"%s\",\"normal_vs_forced_cosine\":%s,\"recovered_equal\":true,\"limits\":\"Forced flag exposure proves a mechanism only; it does not establish overlap in acoustic captures\"}\n",
 otherPrepareCalls,raw,work.ok?"true":"false",altered?"true":"false",altered?"false":"true",staleA?"true":"false",normal,during,after,similarityText);
 model->~Model();heap_caps_free(model);heap_caps_free(vectors);heap_caps_free(pcmA);heap_caps_free(pcmB);heap_caps_free(blob);hw1_dl_prepare_gen=savedGen;
}
