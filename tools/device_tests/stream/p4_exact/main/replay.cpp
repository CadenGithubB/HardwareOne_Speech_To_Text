// Exact on-device equality, not an acoustic quality or timing benchmark.
// Reuse the real card/model/LM adapters without starting the microphone, feature
// worker, note-saving app loop or production speaker worker. The separate-task
// speaker probe is explicit; only app_main below is entered.
#define app_main unused_captions_app_main
#include "main.cpp"
#undef app_main
#include "mbedtls/sha256.h"
#include <cassert>
#include <new>
#include "speaker_prepare_probe.h"
#ifdef NDEBUG
#error "Exact replay requires enabled assertions"
#endif
static_assert(HW1_STT_RUNTIME_DIAGNOSTICS==1,"Neural input/output hashing must be compiled in");

namespace {
struct Result {
  uint8_t pcm[32]{},features[32]{},input[32]{},output[32]{},text[32]{};
  size_t samples=0,cached=0;
};
Result expected[6];
void sha(const void* data,size_t bytes,uint8_t* out){
  assert(mbedtls_sha256(static_cast<const unsigned char*>(data),bytes,out,0)==0);
}
void hex(const uint8_t* hash,char* out){
  constexpr char digits[]="0123456789abcdef";
  for(unsigned i=0;i<32;++i){out[i*2]=digits[hash[i]>>4];out[i*2+1]=digits[hash[i]&15];}out[64]=0;
}
void* allocate(size_t bytes){
  void* p=heap_caps_malloc(bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);assert(p);return p;
}
void oneCall(hw1::stt::StreamPipeline& pipeline,hw1::stt::StreamWork& work,bool prefix,unsigned caseId){
  Result result;result.samples=work.samples;result.cached=work.features.count;
  assert(work.kind==hw1::stt::StreamWorkKind::Final&&work.features.count>0);
  sha(work.pcm,work.samples*sizeof(int16_t),result.pcm);
  sha(work.features.rows,work.features.count*64*sizeof(float),result.features);
  FILE* file=fopen(kModelPath,"rb");assert(file);struct stat info{};assert(fstat(fileno(file),&info)==0);
  ModelFile source{file};hw1::stt::ModelReader reader{&source,size_t(info.st_size),readModel};
  hw1::stt::Diagnostics diagnostics;STTLocalStats stats{};char text[kMaxText+1]{},error[128]{};
  const bool ok=hw1::stt::transcribe(reader,work.pcm,work.samples,text,sizeof(text),{},stats,error,sizeof(error),&diagnostics,&gWeights,&gDecoder,&work.features);
  fclose(file);
  if(!ok)printf("STT_EXACT failure case=%u error=%s\n",caseId,error);
  assert(ok&&stats.lmUsed&&gLm.view.valid()&&stats.featureCachedFrames==work.features.count&&gWeights.verify());
  memcpy(result.input,diagnostics.inputSha,32);memcpy(result.output,diagnostics.outputSha,32);sha(text,strlen(text),result.text);
  uint8_t after[32];sha(work.features.rows,work.features.count*64*sizeof(float),after);assert(!memcmp(after,result.features,32));
  if(!prefix)expected[caseId]=result;
  else {
    const auto& control=expected[caseId];
    assert(control.samples==result.samples&&control.cached==result.cached);
    assert(!memcmp(control.pcm,result.pcm,32)&&!memcmp(control.features,result.features,32));
    assert(!memcmp(control.input,result.input,32)&&!memcmp(control.output,result.output,32)&&!memcmp(control.text,result.text,32));
  }
  char input[65],output[65],decoded[65];hex(result.input,input);hex(result.output,output);hex(result.text,decoded);
  printf("STT_EXACT {\"type\":\"run\",\"case\":%u,\"prefix\":%s,\"samples\":%u,\"cached_rows\":%u,\"input_sha256\":\"%s\",\"output_sha256\":\"%s\",\"text_sha256\":\"%s\",\"equal\":true}\n",
    caseId,prefix?"true":"false",unsigned(result.samples),unsigned(result.cached),input,output,decoded);
  pipeline.complete(work,true,text,stats,100);
}
}

extern "C" void app_main(){
  printf("STT_EXACT {\"type\":\"begin\",\"scope\":\"Six synthetic recognition pairs plus forced separate-task speaker isolation probe; no microphone capture or acoustic playback\"}\n");
  assert(mountCard());vTaskPrioritySet(nullptr,2);speaker_prepare_probe();
  gLm.tried=true;loadLanguageModel(gLm);assert(gLm.view.valid()&&product::lmStrength()==1);
  hw1::stt::StreamBuffers buffers;buffers.capacity=kPhraseSamples;
  buffers.capture=static_cast<int16_t*>(allocate(kPhraseSamples*sizeof(int16_t)));
  buffers.snapshot=static_cast<int16_t*>(allocate(kPhraseSamples*sizeof(int16_t)));
  for(auto& slot:buffers.slots)slot=static_cast<int16_t*>(allocate(kPhraseSamples*sizeof(int16_t)));
  auto* ring=static_cast<int16_t*>(allocate(kRingSamples*sizeof(int16_t)));
  float* rows[2]={static_cast<float*>(allocate(1000*64*sizeof(float))),static_cast<float*>(allocate(1000*64*sizeof(float)))};
  auto* workspace=new(allocate(sizeof(hw1::stt::FrontendWorkspace))) hw1::stt::FrontendWorkspace{};
  // Both arms start with cold model state and the same already-loaded LM. Each
  // first call builds the normal resident graph; later calls exercise warm reuse.
  for(bool prefix:{false,true}){
    gWeights.reset();hw1::stt::StreamPipeline pipeline;hw1::stt::StreamConfig config;
    config.clear_committed_features=prefix;config.drafts=false;config.speculative=false;
    config.segmentation.adaptive=false;config.segmentation.rms_threshold=100;
    config.segmentation.min_segment_samples=config.segmentation.min_voice_samples=320;
    config.segmentation.pre_roll_samples=0;config.segmentation.max_segment_samples=kPhraseSamples;
    assert(pipeline.begin(config,buffers));assert(pipeline.enableFeatures(ring,kRingSamples,rows[0],rows[1]));
    uint32_t now=0;unsigned caseId=0;
    for(unsigned pass=0;pass<2;++pass)for(size_t voice:{size_t(16000),size_t(64000),size_t(160000)}){
      int16_t block[160];
      for(size_t at=0;at<voice+9600;at+=160){
        for(size_t i=0;i<160;++i)block[i]=at<voice?int16_t(((at+i)&1?1:-1)*(600+((at+i)*17%1000))):0;
        now+=10;assert(pipeline.push(block,160,now));hw1::stt::StreamFeatureWork feature;float row[64];
        while(pipeline.featureTake(feature)){
          assert(hw1::stt::log_mel_frame_ring(feature.ring,511,feature.start,feature.samples,feature.frame,row,workspace)==hw1::stt::Status::Ok);
          pipeline.featureComplete(feature,row,true);
        }
        hw1::stt::StreamWork work;
        if(pipeline.take(work,now)){
          assert(caseId<6);oneCall(pipeline,work,prefix,caseId++);
          for(auto* cache:rows)for(size_t k=0;k<1000*64;++k)assert(cache[k]==0);
        }
      }
    }
    assert(caseId==6&&pipeline.counters().dropped==0&&pipeline.counters().feature_overruns==0);
    assert(pipeline.finish(now));pipeline.cancel();gWeights.reset();
  }
  printf("STT_EXACT {\"type\":\"complete\",\"matched_pairs\":6,\"recognition_pairs_passed\":true}\n");
  // Keep the exclusive test controller's Console alive until it restores the app.
  for(;;)vTaskDelay(pdMS_TO_TICKS(1000));
}
