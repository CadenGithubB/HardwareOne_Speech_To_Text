// Deterministic scheduler/frontend replay, not acoustic-model accuracy or timing.
#include "stt/stt_stream.h"
#include <algorithm>
#include <cassert>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <vector>
using namespace hw1::stt;
namespace {
uint64_t hash(const void* data,size_t bytes){
  auto p=static_cast<const unsigned char*>(data);uint64_t h=14695981039346656037ull;
  for(size_t i=0;i<bytes;++i){h^=p[i];h*=1099511628211ull;}return h;
}
struct Replay {
  static constexpr size_t capacity=160000;
  std::vector<int16_t> capture=std::vector<int16_t>(capacity),snapshot=capture;
  std::vector<int16_t> slots[3]={capture,capture,capture},ring=std::vector<int16_t>(65536);
  std::vector<float> rows[2]={std::vector<float>(1000*64),std::vector<float>(1000*64)};
  FrontendWorkspace workspace{};std::mutex mutex;StreamPipeline pipeline;
  uint64_t accepted=0,last_final=0;uint32_t work_count=0;bool features_enabled=true;FILE* payload=nullptr;
  static void lock(void* c){static_cast<Replay*>(c)->mutex.lock();}
  static void unlock(void* c){static_cast<Replay*>(c)->mutex.unlock();}
  Replay(bool x2,bool features,bool trim):features_enabled(features){
    StreamConfig c;c.segmentation.adaptive=false;c.segmentation.rms_threshold=100;
    c.segmentation.min_voice_samples=features?320:160;c.segmentation.min_segment_samples=320;
    c.segmentation.max_segment_samples=capacity;c.segmentation.pre_roll_samples=0;
    c.segmentation.hard_cut_search_samples=32000;
    c.tail_samples=trim?8000:0;c.draft_pacing=x2?DraftPacing::X2FastFirst:DraftPacing::Legacy;
    c.draft_interval_ms=x2?0:1000;
#if TRACE_CLEAR_COMMITTED
    c.clear_committed_features=true;
#endif
    StreamBuffers b;b.capacity=capacity;b.capture=capture.data();b.snapshot=snapshot.data();
    for(size_t i=0;i<3;++i)b.slots[i]=slots[i].data();
    assert(pipeline.begin(c,b,{this,lock,unlock}));
    if(features)assert(pipeline.enableFeatures(ring.data(),ring.size(),rows[0].data(),rows[1].data()));
  }
  uint32_t now()const{return uint32_t(accepted/16);}
  void features(){
    if(!features_enabled)return;StreamFeatureWork w;float row[64];size_t count=0;
    while(pipeline.featureTake(w)){
      assert(++count<10000);
      assert(log_mel_frame_ring(w.ring,511,w.start,w.samples,w.frame,row,&workspace)==Status::Ok);
      pipeline.featureComplete(w,row,true);
    }
  }
  void record(const StreamWork& w){
    // Verify every committed cached row against the actual batch-window frontend.
    float row[64];
    for(size_t i=0;i<w.features.count;++i){
      assert(log_mel_frame(w.pcm,w.samples,i,row,&workspace)==Status::Ok);
      assert(std::memcmp(row,w.features.rows+i*64,sizeof(row))==0);
    }
    if(w.kind==StreamWorkKind::Final){assert(w.sequence>last_final);last_final=w.sequence;}
    printf("{\"type\":\"work\",\"kind\":%u,\"sequence\":%" PRIu64 ",\"start\":%" PRIu64 ",\"samples\":%zu,\"captured\":%zu,\"hard\":%s,\"promoted\":%s,\"canceled\":%s,\"pcm_fnv64\":\"%016" PRIx64 "\",\"cached_rows\":%zu,\"features_fnv64\":\"%016" PRIx64 "\"}\n",
      unsigned(w.kind),w.sequence,w.start_sample,w.samples,w.captured_samples,w.hard_limit?"true":"false",
      w.promoted?"true":"false",pipeline.cancelled(w)?"true":"false",hash(w.pcm,w.samples*2),w.features.count,
      hash(w.features.rows,w.features.count*64*sizeof(float)));
    assert(payload);
    assert(std::fwrite(w.pcm,sizeof(int16_t),w.samples,payload)==w.samples);
    if(w.features.count)assert(std::fwrite(w.features.rows,sizeof(float),w.features.count*64,payload)==w.features.count*64);
    ++work_count;
  }
  void drain(){
    StreamWork w;unsigned count=0;
    while(pipeline.take(w,now())){
      assert(++count<1000);record(w);
      pipeline.complete(w,!pipeline.cancelled(w),"synthetic trace",{},400);
    }
  }
  void feed(size_t samples,bool voice,size_t block=1024,bool run=true,bool cache=true){
    std::vector<int16_t> pcm(block);
    while(samples){
      size_t n=std::min(samples,block);
      for(size_t i=0;i<n;++i){uint64_t at=accepted+i;pcm[i]=voice?int16_t((at&1?1:-1)*(600+(at*17%1000))):0;}
      accepted+=n;assert(pipeline.push(pcm.data(),n,now()));samples-=n;
      if(cache)features();if(run)drain();
    }
  }
  void finish(){assert(pipeline.finish(now()));features();drain();}
  void result(){
    auto c=pipeline.counters();
    printf("{\"type\":\"summary\",\"accepted_samples\":%" PRIu64 ",\"work\":%u,\"drops\":%u,\"drafts\":%u,\"canceled\":%u,\"promotions\":%u,\"feature_overruns\":%u}\n",
      accepted,work_count,c.dropped,c.drafts,c.canceled,c.promotions,c.feature_overruns);
  }
};
}
int main(int argc,char** argv){
  assert(argc==4);const bool x2=std::strcmp(argv[1],"x2f")==0;const int scenario=std::atoi(argv[2]);
  Replay r(x2,scenario!=4,scenario==2);r.payload=std::fopen(argv[3],"wb");assert(r.payload);
  if(scenario==0){r.feed(16000,false,71);r.feed(32000,true,1024);r.feed(9600,false,127);r.feed(1600,true,29);r.feed(9600,false,1024);r.feed(330000,true,1024);r.feed(9600,false,160);r.finish();}
  else if(scenario==1){for(int i=0;i<5;++i){r.feed(16000,true,1024,false);r.feed(9600,false,127,false);}r.drain();r.finish();assert(r.pipeline.counters().dropped==2);}
  else if(scenario==2){r.feed(16000,true,160,false);r.feed(8000,false,160,false);r.drain();r.feed(1600,false,160);r.feed(16000,true,160,false);r.feed(8000,false,160,false);StreamWork w;assert(r.pipeline.take(w,r.now()));r.feed(320,true,160,false);r.record(w);r.pipeline.complete(w,false,"",{},400);r.feed(9600,false,160);r.finish();}
  else if(scenario==3){r.feed(16000,true,160,false);StreamWork w;assert(r.pipeline.take(w,r.now()));r.feed(9600,false,160,false);r.pipeline.cancel();r.record(w);r.pipeline.complete(w,false,"",{},400);assert(!r.pipeline.take(w,r.now()));}
  else if(scenario==4){r.feed(16000,true,31);r.feed(9600,false,79);r.feed(160,true,37);r.finish();}
  else if(scenario==5){r.feed(80000,true,1024,false,false);r.features();r.drain();r.feed(9600,false,79);r.finish();assert(r.pipeline.counters().feature_overruns>0);}
  else std::abort();
  r.result();assert(std::fclose(r.payload)==0);return 0;
}
