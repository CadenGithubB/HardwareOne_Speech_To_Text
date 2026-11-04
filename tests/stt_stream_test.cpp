#include "stt/stt_stream.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <vector>
#include <thread>
#include <atomic>
#include <cstdlib>
#include <new>
using namespace hw1::stt;
namespace {
thread_local bool watch_allocations=false;
thread_local size_t watched_allocations=0;
}
void* operator new(size_t bytes){
    if(watch_allocations)++watched_allocations;
    if(void* p=std::malloc(bytes?bytes:1))return p;
    throw std::bad_alloc();
}
void* operator new[](size_t bytes){return ::operator new(bytes);}
void operator delete(void* p) noexcept {std::free(p);}
void operator delete[](void* p) noexcept {std::free(p);}
struct Fixture {
    std::vector<int16_t> capture=std::vector<int16_t>(32000),snapshot=capture;
    std::vector<int16_t> pcm[3]={capture,capture,capture},ring=std::vector<int16_t>(65536);
    std::vector<float> rows[2]={std::vector<float>(200*64),std::vector<float>(200*64)};
    StreamPipeline pipeline;FrontendWorkspace workspace{};uint32_t now=0;
    std::mutex mutex;
    uint32_t tagged_calls[kStreamOperations]{};
    StreamOperation current_operation=StreamOperation::Status;
    static void taggedLock(void* p,StreamOperation op){auto& f=*static_cast<Fixture*>(p);f.mutex.lock();++f.tagged_calls[size_t(op)];f.current_operation=op;}
    static void taggedUnlock(void* p,StreamOperation op){auto& f=*static_cast<Fixture*>(p);assert(f.current_operation==op);f.mutex.unlock();}
    static void lock(void* p){static_cast<Fixture*>(p)->mutex.lock();}
    static void unlock(void* p){static_cast<Fixture*>(p)->mutex.unlock();}
    Fixture(bool trim=false,bool features=true,size_t ringSize=65536,
            DraftPacing pacing=DraftPacing::Legacy,uint32_t interval=1000,bool tagged=false,bool clearPrefix=false){
        StreamConfig c;c.segmentation.adaptive=false;c.segmentation.rms_threshold=100;
        c.segmentation.max_segment_samples=32000;c.segmentation.min_segment_samples=320;
        c.segmentation.min_voice_samples=320;c.segmentation.pre_roll_samples=0;
        c.tail_samples=trim?8000:0;c.draft_interval_ms=interval;c.draft_pacing=pacing;c.clear_committed_features=clearPrefix;
        StreamBuffers b;b.capacity=32000;b.capture=capture.data();b.snapshot=snapshot.data();
        for(int i=0;i<3;++i)b.slots[i]=pcm[i].data();
        StreamLock synchronization{this,lock,unlock};
        if(tagged){synchronization.tagged_lock=taggedLock;synchronization.tagged_unlock=taggedUnlock;}
        assert(pipeline.begin(c,b,synchronization));
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
void guarded_features(Fixture& f,size_t ringSize=65536){
    for(auto& rows:f.rows){rows.assign(200*64+16,7.75f);}
    assert(f.pipeline.enableFeatures(f.ring.data(),ringSize,f.rows[0].data()+8,f.rows[1].data()+8));
}
void cache_zero_and_guards(const Fixture& f){
    for(const auto& rows:f.rows){
        for(size_t i=0;i<8;++i)assert(rows[i]==7.75f&&rows[rows.size()-1-i]==7.75f);
        for(size_t i=8;i<8+200*64;++i)assert(rows[i]==0);
    }
}
void no_hot_allocations_and_null_lock(bool prefix,bool features,bool snapshot){
    Fixture storage(false,false);StreamPipeline p;StreamConfig c;
    c.segmentation.adaptive=false;c.segmentation.rms_threshold=100;
    c.segmentation.max_segment_samples=32000;c.segmentation.min_segment_samples=320;
    c.segmentation.min_voice_samples=320;c.segmentation.pre_roll_samples=0;
    c.clear_committed_features=prefix;
    StreamBuffers b;b.capacity=32000;b.capture=storage.capture.data();b.snapshot=snapshot?storage.snapshot.data():nullptr;
    for(int i=0;i<3;++i)b.slots[i]=storage.pcm[i].data();
    watched_allocations=0;watch_allocations=true;
    assert(p.begin(c,b));
    if(features)assert(p.enableFeatures(storage.ring.data(),storage.ring.size(),storage.rows[0].data(),storage.rows[1].data()));
    int16_t block[160];float row[64];StreamFeatureWork f;StreamWork w;unsigned finals=0;
    for(unsigned step=0;step<165;++step){
        for(unsigned i=0;i<160;++i)block[i]=step<100?(i&1?1000:-1000):0;
        assert(p.push(block,160,step*10));
        while(p.featureTake(f)){
            assert(log_mel_frame_ring(f.ring,511,f.start,f.samples,f.frame,row,&storage.workspace)==Status::Ok);
            p.featureComplete(f,row,true);
        }
        if(p.take(w,step*10)){finals+=w.kind==StreamWorkKind::Final;p.complete(w,true,"fixed",{},100);}
    }
    assert(p.finish(1650));while(p.take(w,1650)){finals+=w.kind==StreamWorkKind::Final;p.complete(w,true,"fixed",{},100);}
    p.cancel();watch_allocations=false;assert(watched_allocations==0&&finals==1);
    for(const auto& rows:storage.rows)for(float value:rows)assert(value==0);
}
void committed_prefix_clearing(){
    for(bool prefix:{false,true})for(bool features:{false,true})for(bool snapshot:{false,true})
        no_hot_allocations_and_null_lock(prefix,features,snapshot);
    Fixture f(false,false,65536,DraftPacing::Legacy,1000,false,true);guarded_features(f);cache_zero_and_guards(f);
    f.feed(320,true,false);f.pipeline.cancel();cache_zero_and_guards(f);
#if HW1_STT_STREAM_METRICS
    assert(f.pipeline.memoryDiagnostics(StreamMemoryOperation::CacheClear).metric.bytes==0);
#endif
    Fixture one(false,false,65536,DraftPacing::Legacy,1000,false,true);guarded_features(one);
    one.feed(320,true,false);StreamFeatureWork first;float row[64];assert(one.pipeline.featureTake(first));
    assert(log_mel_frame_ring(first.ring,511,first.start,first.samples,first.frame,row,&one.workspace)==Status::Ok);
    one.pipeline.featureComplete(first,row,true);one.pipeline.cancel();cache_zero_and_guards(one);
#if HW1_STT_STREAM_METRICS
    assert(one.pipeline.memoryDiagnostics(StreamMemoryOperation::CacheClear).metric.bytes==64*sizeof(float));
#endif
    Fixture overrun(false,false,512,DraftPacing::Legacy,1000,false,true);guarded_features(overrun,512);
    overrun.feed(640,true);overrun.feed(16000,true,false);overrun.features();assert(overrun.pipeline.counters().feature_overruns==1);
    overrun.feed(9600,false);StreamWork fallback;assert(overrun.pipeline.take(fallback,overrun.now));
    assert(fallback.features.count==4);overrun.done(fallback);cache_zero_and_guards(overrun);
    Fixture repeated(false,false,65536,DraftPacing::Legacy,1000,false,true);guarded_features(repeated);
    for(int pass=0;pass<6;++pass){
        const size_t voice=pass%2?32000:16000;repeated.feed(voice,true);
        if(voice<32000)repeated.feed(9600,false);
        StreamWork w;assert(repeated.pipeline.take(w,repeated.now)&&w.kind==StreamWorkKind::Final);
        if(voice==32000)assert(w.features.count==199); // maximum committed prefix before hard close
        assert(w.features.count>0);bool dirty=false;
        for(size_t i=8;i<8+200*64;++i)dirty|=repeated.rows[0][i]!=0||repeated.rows[1][i]!=0;
        assert(dirty);repeated.done(w);cache_zero_and_guards(repeated);
    }
    Fixture trimmed(true,false,65536,DraftPacing::Legacy,1000,false,true);guarded_features(trimmed);
    trimmed.feed(16000,true);trimmed.feed(8000,false);StreamWork spec;
    assert(trimmed.pipeline.take(spec,trimmed.now)&&spec.kind==StreamWorkKind::Speculative);
    const size_t used_rows=spec.features.count;trimmed.feed(1600,false);trimmed.done(spec);
    StreamWork final;assert(trimmed.pipeline.take(final,trimmed.now)&&final.promoted);
    assert(final.features.count==used_rows&&used_rows==150);
#if HW1_STT_STREAM_METRICS
    const auto before=trimmed.pipeline.diagnostics();assert(before.frames[0]==159&&before.pins[0]==1);
#endif
    trimmed.done(final);cache_zero_and_guards(trimmed);
#if HW1_STT_STREAM_METRICS
    assert(trimmed.pipeline.memoryDiagnostics(StreamMemoryOperation::CacheClear).metric.bytes==159*64*4);
#endif
    Fixture pinned(false,false,65536,DraftPacing::Legacy,1000,false,true);guarded_features(pinned);
    pinned.feed(16000,true);assert(pinned.pipeline.take(spec,pinned.now));
    const auto retained=std::vector<float>(spec.features.rows,spec.features.rows+spec.features.count*64);
    pinned.feed(9600,false);pinned.pipeline.cancel();pinned.pipeline.cancel();assert(pinned.pipeline.cancelled(spec));
    assert(!std::memcmp(retained.data(),spec.features.rows,retained.size()*sizeof(float)));
    pinned.done(spec,false);cache_zero_and_guards(pinned);
    Fixture stale(false,false,65536,DraftPacing::Legacy,1000,false,true);guarded_features(stale);
    stale.feed(320,true,false);StreamFeatureWork old;assert(stale.pipeline.featureTake(old));
    stale.feed(9600,false,false);assert(stale.pipeline.take(final,stale.now));stale.done(final);cache_zero_and_guards(stale);
    stale.feed(320,true,false);float foreign[64];std::fill(foreign,foreign+64,99.f);
    stale.pipeline.featureComplete(old,foreign,true);cache_zero_and_guards(stale);
    stale.features();assert(stale.pipeline.take(final,stale.now)==false);stale.pipeline.cancel();cache_zero_and_guards(stale);
    // With a reader pinned and one feature row in flight, exercise all mutex
    // serialization orders of finish, cancel and late feature publication.
    for(bool prefix:{false,true}){
        int order[3]={0,1,2};
        do{
            Fixture terminal(false,false,65536,DraftPacing::Legacy,1000,false,prefix);guarded_features(terminal);
            terminal.feed(16000,true);StreamWork reader;assert(terminal.pipeline.take(reader,terminal.now));
            std::vector<float> kept(reader.features.rows,reader.features.rows+reader.features.count*64);
            terminal.feed(320,true,false);StreamFeatureWork pending;assert(terminal.pipeline.featureTake(pending));
            float value[64];assert(log_mel_frame_ring(pending.ring,511,pending.start,pending.samples,pending.frame,value,&terminal.workspace)==Status::Ok);
            for(int action:order){
                if(action==0)(void)terminal.pipeline.finish(terminal.now);
                else if(action==1)terminal.pipeline.cancel();
                else terminal.pipeline.featureComplete(pending,value,true);
            }
            assert(terminal.pipeline.cancelled(reader));
            assert(!std::memcmp(kept.data(),reader.features.rows,kept.size()*sizeof(float)));
            terminal.done(reader,false);cache_zero_and_guards(terminal);
            assert(!terminal.pipeline.take(reader,terminal.now));
        }while(std::next_permutation(order,order+3));
    }
}
void tagged_lock_contract(){
    Fixture f(false,false,65536,DraftPacing::Legacy,1000,true);
    f.feed(16000,true);StreamWork w;assert(f.pipeline.take(w,f.now));f.done(w);
    assert(f.tagged_calls[size_t(StreamOperation::Push)]==100);
    assert(f.tagged_calls[size_t(StreamOperation::Take)]==1&&f.tagged_calls[size_t(StreamOperation::Complete)]==1);
    StreamConfig c;c.segmentation.adaptive=false;c.segmentation.max_segment_samples=32000;
    c.segmentation.min_segment_samples=c.segmentation.min_voice_samples=320;c.segmentation.pre_roll_samples=0;
    StreamBuffers b;b.capture=f.capture.data();b.capacity=f.capture.size();for(int i=0;i<3;++i)b.slots[i]=f.pcm[i].data();
    StreamPipeline bad;StreamLock missing{&f,Fixture::lock,Fixture::unlock,Fixture::taggedLock,nullptr};
    assert(!bad.begin(c,b,missing));missing.tagged_unlock=Fixture::taggedUnlock;missing.unlock=nullptr;
    assert(!bad.begin(c,b,missing));missing.unlock=Fixture::unlock;assert(bad.begin(c,b,missing));
    (void)bad.level();assert(f.tagged_calls[size_t(StreamOperation::Status)]==1);
}
void metrics_accounting(){
    StreamTimeHistogram h;
    for(uint64_t n:{0ull,1ull,2ull,10ull,11ull,500ull,501ull,2000ull,4001ull,16001ull})h.add(n);
    assert(h.count==10&&h.max_us==16001&&h.buckets[0]==2&&h.buckets[1]==2&&h.buckets[11]==1);
    uint64_t sum=0;for(auto n:h.buckets)sum+=n;assert(sum==h.count);
    h.buckets[0]=UINT32_MAX;h.add(0);assert(h.saturated&&h.buckets[0]==UINT32_MAX);
    StreamTimeHistogram scaled;scaled.add(64,64);scaled.add(65,64);scaled.add(64000,64);scaled.add(64001,64);
    assert(scaled.buckets[0]==1&&scaled.buckets[1]==1&&scaled.buckets[6]==1&&scaled.buckets[7]==1);
    assert(scaled.max_us==64001&&scaled.total_us==128130);
#if HW1_STT_STREAM_METRICS
    Fixture f(false,true,65536,DraftPacing::Legacy,1000,true);auto d=f.pipeline.diagnostics();
    assert(d.memory[size_t(StreamMemoryOperation::StartupClear)].bytes==131072+2*51200);
    f.feed(16000,true);StreamWork w;assert(f.pipeline.take(w,f.now));
    d=f.pipeline.diagnostics();assert(d.accepted_samples==16000&&d.pins[0]==1);
    assert(d.memory[size_t(StreamMemoryOperation::FeatureRow)].bytes==100*64*4);
    assert(d.memory[size_t(StreamMemoryOperation::SnapshotCopy)].bytes==32000);
    assert(d.bytes_by_caller[size_t(StreamOperation::Take)][size_t(StreamMemoryOperation::SnapshotCopy)]==32000);
    auto page=f.pipeline.memoryDiagnostics(StreamMemoryOperation::SnapshotCopy);
    assert(page.metric.bytes==32000&&page.bytes_by_caller[size_t(StreamOperation::Take)]==32000);
    assert(f.pipeline.memoryDiagnostics(StreamMemoryOperation::Count).metric.bytes==0);
    f.done(w);f.feed(9600,false);assert(f.pipeline.take(w,f.now)&&w.kind==StreamWorkKind::Final);f.done(w);
    d=f.pipeline.diagnostics();assert(d.ready_high_water==1&&d.free_slots==3&&d.running==0&&d.ready==0);
    assert(d.memory[size_t(StreamMemoryOperation::CacheClear)].bytes==51200);
    for(const auto& rows:f.rows)for(float value:rows)assert(value==0);
    auto state=f.pipeline.diagnosticsState();assert(state.accepted_samples==25600&&state.free_caches==2);
#endif
}
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
void concurrent_ownership(DraftPacing pacing=DraftPacing::Legacy,bool clearPrefix=false){
    Fixture f(false,true,65536,pacing,0,false,clearPrefix);std::atomic<bool> done{false};
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
int main(){committed_prefix_clearing();tagged_lock_contract();metrics_accounting();draft_pacing_and_phrase_reset();concurrent_ownership();concurrent_ownership(DraftPacing::X2FastFirst);concurrent_ownership(DraftPacing::Legacy,true);concurrent_ownership(DraftPacing::X2FastFirst,true);features_and_draft_preemption();features_and_draft_preemption(DraftPacing::X2FastFirst);exact_promotion_and_resumed_speech();hard_cut_finish_and_cancel();queue_overflow_and_stale_features();puts("Streaming: bit-exact cached features, draft preemption, exact promotion, resumed speech, hard cuts, stop/cancel, overflow and stale generations passed");}
