#include "stt/stt_segmenter.h"
#include <cassert>
#include <cstdio>
#include <random>
#include <vector>
using namespace hw1::stt;

// Exercise the production segmenter with caller chunk sizes unrelated to its
// 160-sample analysis grid. Samples and offsets, rather than transcript text,
// are the oracle. Intentional idle/rejected short speech is not a lost sample.
struct Result {
    uint64_t start, end, fresh;
    size_t overlap, next_overlap, voice, voiced_end;
    SegmentEnd reason;
    bool continuation;
    bool operator==(const Result& b) const {
        return start==b.start && end==b.end && fresh==b.fresh &&
            overlap==b.overlap && next_overlap==b.next_overlap &&
            voice==b.voice && voiced_end==b.voiced_end &&
            reason==b.reason && continuation==b.continuation;
    }
};
std::vector<Result> run(const std::vector<int16_t>& pcm, const SegmenterConfig& c,
                        size_t chunk, bool random_chunks, uint32_t seed) {
    std::vector<int16_t> buffer(c.max_segment_samples);
    Segmenter s; assert(s.reset(buffer.data(),buffer.size(),c));
    std::vector<Result> out; std::mt19937 rng(seed);
    auto collect=[&] {
        const auto* p=s.segment(); assert(p);
        assert(p->samples && p->samples<=c.max_segment_samples);
        assert(p->end_sample-p->start_sample==p->samples);
        assert(p->end_sample<=pcm.size());
        assert(p->fresh_start_sample>=p->start_sample && p->fresh_start_sample<=p->end_sample);
        assert(p->overlap_before_samples==p->fresh_start_sample-p->start_sample);
        assert(p->voiced_end_samples<=p->samples);
        for(size_t i=0;i<p->samples;++i) assert(p->pcm[i]==pcm[p->start_sample+i]);
        if(!out.empty()) {
            // Only explicit configured overlap may redeliver previous audio.
            assert(p->fresh_start_sample>=out.back().end);
            if(p->continuation) assert(p->fresh_start_sample==out.back().end);
        }
        out.push_back({p->start_sample,p->end_sample,p->fresh_start_sample,
            p->overlap_before_samples,p->next_overlap_samples,p->new_voiced_samples,
            p->voiced_end_samples,p->end,p->continuation});
        assert(s.release());
    };
    size_t at=0;
    while(at<pcm.size()) {
        const size_t n=std::min(pcm.size()-at,random_chunks?size_t(1+rng()%4096):chunk);
        size_t used=0;
        while(used<n) {
            const auto r=s.push(pcm.data()+at+used,n-used);
            assert(r.consumed>0); used+=r.consumed;
            assert(r.status==SegmentStatus::Ok || r.status==SegmentStatus::Ready);
            if(r.status==SegmentStatus::Ready) collect();
        }
        at+=n;
    }
    assert(s.samples_seen()==pcm.size());
    auto status=s.finish();
    if(status==SegmentStatus::Ready) collect();
    else assert(status==SegmentStatus::Finished);
    assert(s.finish()==SegmentStatus::Finished);
    assert(s.push(pcm.data(),1).status==SegmentStatus::Finished);
    return out;
}

int main() {
    size_t comparisons=0,segments=0;
    // Fixed and adaptive endpoints, forced overlap, quiet-point hard cuts,
    // percentile noise, blip tolerance and short closes; no tuning is applied
    // to a production profile by this synthetic test.
    for(unsigned mode=0;mode<6;++mode) for(unsigned seed=1;seed<=20;++seed) {
        SegmenterConfig c;
        c.max_segment_samples=16000;c.min_segment_samples=3200;
        c.min_voice_samples=320;c.pre_roll_samples=480;
        c.end_silence_samples=1600;c.rms_threshold=100;
        if(mode==1) c.forced_overlap_samples=640;
        if(mode==2) c.hard_cut_search_samples=3200;
        if(mode>=3) {c.adaptive=true;c.calibration_samples=1600;c.noise_window_frames=50;}
        if(mode==4) {c.noise_percentile=25;c.silence_blip_samples=320;}
        if(mode==5) {c.hard_cut_search_samples=3200;c.short_close_silence_samples=3200;}
        std::mt19937 rng(seed);
        std::vector<int16_t> pcm;
        // Long speech runs force hard limits, with short gaps and quiet word
        // tails between them. Every run has its own noise/DC fingerprint.
        for(unsigned block=0;block<18;++block) {
            const size_t n=block==0?1600:size_t(1+rng()%23000);
            const int amp=block==0?3:(block%3==0?4:(block%3==1?800:55));
            const int dc=int(rng()%1500)-750;
            for(size_t i=0;i<n;++i) pcm.push_back(int16_t(dc+(i&1?amp:-amp)));
        }
        const auto reference=run(pcm,c,160,false,seed);segments+=reference.size();
        for(size_t chunk:{size_t(1),size_t(159),size_t(161),size_t(257),size_t(4096)}) {
            assert(reference==run(pcm,c,chunk,false,seed));++comparisons;
        }
        assert(reference==run(pcm,c,0,true,seed));++comparisons;
    }
    // Continuous qualified voice must survive every hard-cut continuation and
    // a non-frame-aligned session end exactly once, excluding explicit overlap.
    for(bool quiet:{false,true}) {
        SegmenterConfig c;c.max_segment_samples=3200;c.min_segment_samples=320;
        c.min_voice_samples=160;c.pre_roll_samples=0;c.end_silence_samples=160;
        c.hard_cut_search_samples=quiet?1600:0;
        std::vector<int16_t> pcm(3200*9+79);
        for(size_t i=0;i<pcm.size();++i) pcm[i]=int16_t(i&1?1000:-1000);
        const auto out=run(pcm,c,257,false,1);
        uint64_t end=0;
        for(const auto& r:out) {assert(r.start==end);end=r.end;}
        assert(end==pcm.size());
    }
    // Stopping while a quiet-point cut is ready must deliver its entire
    // buffered suffix: no subsequent release/push can deliver the carry.
    {
        SegmenterConfig c;c.max_segment_samples=3200;c.min_segment_samples=320;
        c.min_voice_samples=160;c.pre_roll_samples=0;c.end_silence_samples=160;
        c.hard_cut_search_samples=1600;
        std::vector<int16_t> pcm(3200),buffer(3200);
        for(size_t i=0;i<pcm.size();++i) pcm[i]=int16_t(i&1?1000:-1000);
        Segmenter s;assert(s.reset(buffer.data(),buffer.size(),c));
        const auto r=s.push(pcm.data(),pcm.size());
        assert(r.status==SegmentStatus::Ready && r.consumed==pcm.size());
        assert(s.segment()->samples<pcm.size());
        assert(s.finish()==SegmentStatus::Ready);
        assert(s.segment()->samples==pcm.size() && s.segment()->end_sample==pcm.size());
        for(size_t i=0;i<pcm.size();++i) assert(s.segment()->pcm[i]==pcm[i]);
        assert(s.release() && s.finish()==SegmentStatus::Finished);
    }
    std::printf("segmenter: %zu chunk comparisons, %zu reference segments; exact source samples and continuous-voice conservation ok\n",comparisons,segments);
}
