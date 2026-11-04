#include "stt/stt_stream.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <vector>
#include <thread>
#include <atomic>
using namespace hw1::stt;
struct Fixture {
    std::vector<int16_t> capture=std::vector<int16_t>(32000),snapshot=capture;
    std::vector<int16_t> pcm[3]={capture,capture,capture},ring=std::vector<int16_t>(65536);
    std::vector<float> rows[2]={std::vector<float>(200*64),std::vector<float>(200*64)};
    StreamPipeline pipeline;FrontendWorkspace workspace{};uint32_t now=0;
    std::mutex mutex;
    static void lock(void* p){static_cast<Fixture*>(p)->mutex.lock();}
    static void unlock(void* p){static_cast<Fixture*>(p)->mutex.unlock();}
    Fixture(bool trim=false,bool features=true,size_t ringSize=65536,
            DraftPacing pacing=DraftPacing::Legacy,uint32_t interval=1000){
        StreamConfig c;c.segmentation.adaptive=false;c.segmentation.rms_threshold=100;
        c.segmentation.max_segment_samples=32000;c.segmentation.min_segment_samples=320;
        c.segmentation.min_voice_samples=320;c.segmentation.pre_roll_samples=0;
        c.tail_samples=trim?8000:0;c.draft_interval_ms=interval;c.draft_pacing=pacing;
        StreamBuffers b;b.capacity=32000;b.capture=capture.data();b.snapshot=snapshot.data();
        for(int i=0;i<3;++i)b.slots[i]=pcm[i].data();
        assert(pipeline.begin(c,b,{this,lock,unlock}));
        if(features)assert(pipeline.enableFeatures(ring.data(),ringSize,rows[0].data(),rows[1].data()));
    }
    void features(){StreamFeatureWork f;float row[64];size_t count=0;while(pipeline.featureTake(f)){
        assert(++count<=10000);
        assert(log_mel_frame_ring(f.ring,511,f.start,f.samples,f.frame,row,&workspace)==Status::Ok);
        pipeline.featureComplete(f,row,true);
    }}
    void feed(size_t n,bool voice,bool cache=true){
        int16_t block[160];for(size_t i=0;i<160;++i)block[i]=voice?(i&1?1000:-1000):0;
        for(size_t i=0;i<n;i+=160){now+=10;assert(pipeline.push(block,std::min<size_t>(160,n-i),now));if(cache)features();}
    }
    void done(StreamWork& w,bool ok=true,const char* text="words"){pipeline.complete(w,ok,text,{},100);}
};
void draft_pacing_and_phrase_reset(){
    Fixture f(false,false,65536,DraftPacing::X2FastFirst,0);StreamWork w;
    f.feed(9600,true);assert(!f.pipeline.take(w,f.now)); // retain the 1 s audio floor
    f.feed(6400,true);assert(f.pipeline.take(w,f.now)&&w.kind==StreamWorkKind::Draft);
    f.pipeline.complete(w,true,"first",{},400);
    f.feed(12640,true);assert(!f.pipeline.take(w,f.now));
    f.feed(160,true);assert(f.pipeline.take(w,f.now)&&w.kind==StreamWorkKind::Draft);
    assert(w.samples==28800); // 16,000 + 400 ms * 2 * 16 samples/ms
    f.pipeline.complete(w,true,"slow draft",{},5000);
    f.feed(3200,true);assert(f.pipeline.take(w,f.now)&&w.kind==StreamWorkKind::Final);
    assert(w.hard_limit);f.done(w);
    f.feed(16000,true);assert(f.pipeline.take(w,f.now)&&w.kind==StreamWorkKind::Draft);
    assert(w.sequence==2&&w.samples==16000); // no 5 s carryover into the first preview
    f.pipeline.complete(w,true,"new phrase",{},(1u<<27));
    f.feed(9600,true);assert(!f.pipeline.take(w,f.now)); // x32 would wrap to zero in 32-bit arithmetic
    f.feed(6400,true);assert(f.pipeline.take(w,f.now)&&w.kind==StreamWorkKind::Final);f.done(w);

    Fixture floor(false,false,65536,DraftPacing::X2FastFirst,0);
    floor.feed(16000,true);assert(floor.pipeline.take(w,floor.now));floor.done(w);
    floor.feed(9440,true);assert(!floor.pipeline.take(w,floor.now));
    floor.feed(160,true);assert(floor.pipeline.take(w,floor.now)&&w.samples==25600);floor.done(w);

    Fixture gated(false,false,65536,DraftPacing::X2FastFirst,2000);
    gated.feed(16000,true);assert(!gated.pipeline.take(w,gated.now)); // explicit wall floor still honored
    gated.now=2000;assert(gated.pipeline.take(w,gated.now));gated.done(w);

    Fixture legacy(false,false);legacy.feed(16000,true);assert(legacy.pipeline.take(w,legacy.now));
    legacy.pipeline.complete(w,true,"legacy",{},5000);legacy.feed(16000,true);
    assert(legacy.pipeline.take(w,legacy.now)&&w.kind==StreamWorkKind::Final);legacy.done(w);
    legacy.feed(16000,true);assert(!legacy.pipeline.take(w,legacy.now)); // default policy retained
}
void features_and_draft_preemption(DraftPacing pacing=DraftPacing::Legacy){
    Fixture f(false,true,65536,pacing,0);f.feed(16000,true);StreamWork draft;
    assert(f.pipeline.take(draft,f.now));assert(draft.kind==StreamWorkKind::Draft&&draft.features.count==100);
    // Exact raw rows and CMVN must match the production batch frontend.
    std::vector<float> batch(100*64),cached(draft.features.rows,draft.features.rows+100*64);
    FrontendWorkspace ws{};assert(compute_features(draft.pcm,draft.samples,batch.data(),batch.size(),&ws,kDitherSeed,false)==Status::Ok);
    assert(normalize_features(cached.data(),100,&ws)==Status::Ok);
    assert(!std::memcmp(batch.data(),cached.data(),batch.size()*sizeof(float)));
    f.feed(9600,false);assert(f.pipeline.cancelled(draft));f.done(draft,false);
    StreamWork final;assert(f.pipeline.take(final,f.now));assert(final.kind==StreamWorkKind::Final);
    assert(!final.promoted&&final.samples==final.captured_samples&&final.sequence==1);
    assert(final.features.count>=100);f.done(final);assert(!f.pipeline.take(final,f.now));
}
void exact_promotion_and_resumed_speech(){
    Fixture f(true);f.feed(16000,true);f.feed(8000,false);StreamWork spec;
    assert(f.pipeline.take(spec,f.now));assert(spec.kind==StreamWorkKind::Speculative);
    const size_t inferred=spec.samples;f.feed(1600,false);assert(!f.pipeline.cancelled(spec));
    f.done(spec,true,"early words");StreamWork final;assert(f.pipeline.take(final,f.now));
    assert(final.promoted&&final.samples==inferred&&final.captured_samples>inferred);
    assert(!std::strcmp(final.promoted_text,"early words"));assert(f.pipeline.counters().promotions==1);f.done(final);
    Fixture resumed(true);resumed.feed(16000,true);resumed.feed(8000,false);
    assert(resumed.pipeline.take(spec,resumed.now));assert(spec.kind==StreamWorkKind::Speculative);
    resumed.feed(320,true);assert(resumed.pipeline.cancelled(spec));resumed.done(spec);
    resumed.feed(9600,false);assert(resumed.pipeline.take(final,resumed.now));
    assert(final.kind==StreamWorkKind::Final&&!final.promoted);resumed.done(final);
}
void hard_cut_finish_and_cancel(){
    Fixture f(true);f.feed(32000,true);StreamWork work;assert(f.pipeline.take(work,f.now));
    assert(work.kind==StreamWorkKind::Final&&work.hard_limit&&!work.promoted&&work.samples==32000);f.done(work);
    Fixture end(true);end.feed(16000,true);end.feed(8000,false);StreamWork spec;
    assert(end.pipeline.take(spec,end.now)&&spec.kind==StreamWorkKind::Speculative);
    assert(end.pipeline.finish(end.now));assert(end.pipeline.cancelled(spec));end.done(spec);
    assert(end.pipeline.take(work,end.now)&&work.kind==StreamWorkKind::Final&&!work.promoted);end.done(work);
    assert(!end.pipeline.take(work,end.now));
    Fixture canceled;canceled.feed(16000,true);assert(canceled.pipeline.take(work,canceled.now));
    canceled.pipeline.cancel();assert(canceled.pipeline.cancelled(work));canceled.done(work,false);
    assert(!canceled.pipeline.take(work,canceled.now));assert(!canceled.pipeline.push(nullptr,0,0));
}
void queue_overflow_and_stale_features(){
    Fixture f;for(int i=0;i<4;++i){f.feed(16000,true);f.feed(9600,false);}
    assert(f.pipeline.counters().dropped==1);StreamWork w;uint64_t sequence=0;
    while(f.pipeline.take(w,f.now)){assert(w.sequence>sequence);sequence=w.sequence;f.done(w);}
    assert(sequence==3);
    Fixture late;late.feed(320,true,false);StreamFeatureWork pending;assert(late.pipeline.featureTake(pending));
    late.feed(9600,false,false);float row[64]{};late.pipeline.featureComplete(pending,row,true);
    assert(late.pipeline.take(w,late.now));assert(w.features.count==0);late.done(w);
    late.feed(16000,true);late.pipeline.featureComplete(pending,row,true); // old cache generation is harmless
    assert(late.pipeline.take(w,late.now));assert(w.kind==StreamWorkKind::Draft&&w.features.count>0);late.done(w);
    Fixture overrun(false,true,512);overrun.feed(16000,true,false);overrun.features();
    assert(overrun.pipeline.counters().feature_overruns==1);assert(overrun.pipeline.take(w,overrun.now));
    assert(!w.features.count);overrun.done(w);
}
void concurrent_ownership(DraftPacing pacing=DraftPacing::Legacy){
    Fixture f(false,true,65536,pacing,0);std::atomic<bool> done{false};
    std::thread producer([&]{for(int i=0;i<30;++i){f.feed(16000,true,false);f.feed(9600,false,false);}assert(f.pipeline.finish(f.now));done=true;});
    std::thread features([&]{while(!done){f.features();std::this_thread::yield();}});
    uint64_t last=0;size_t finals=0;FrontendWorkspace workspace{};float row[64];
    for(;;){
        StreamWork w;
        if(!f.pipeline.take(w,100000)) {if(done)break;std::this_thread::yield();continue;}
        for(size_t n=0;n<w.features.count;++n){
            assert(log_mel_frame(w.pcm,w.samples,n,row,&workspace)==Status::Ok);
            assert(!std::memcmp(row,w.features.rows+n*64,sizeof(row)));
        }
        if(w.kind==StreamWorkKind::Final){assert(w.sequence>last);last=w.sequence;++finals;}
        f.done(w);
    }
    producer.join();features.join();assert(finals>0);
    assert(finals+f.pipeline.counters().dropped==30);
}
int main(){draft_pacing_and_phrase_reset();concurrent_ownership();concurrent_ownership(DraftPacing::X2FastFirst);features_and_draft_preemption();features_and_draft_preemption(DraftPacing::X2FastFirst);exact_promotion_and_resumed_speech();hard_cut_finish_and_cancel();queue_overflow_and_stale_features();puts("Streaming: bit-exact cached features, draft preemption, exact promotion, resumed speech, hard cuts, stop/cancel, overflow and stale generations passed");}
