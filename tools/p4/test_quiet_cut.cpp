// Host test for SegmenterConfig::hard_cut_search_samples (quiet-point hard cut).
//   clang++ -std=c++17 -Wall -Wextra -Werror -I<tree>/components/hardwareone \
//     experiments/stt_p4/test_quiet_cut.cpp -o /tmp/test_quiet_cut && /tmp/test_quiet_cut
// Synthetic speech: 230 ms tone bursts with 70 ms gaps (too short to end a
// phrase), so only the 20 s limit can close a segment.
#include "stt/stt_segmenter.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <vector>

using namespace hw1::stt;
namespace {
constexpr size_t R=kSegmentSampleRate;
// Burst/gap speech starting after `quiet` samples of near-silence; optional
// silence after `speech` samples of speech.
std::vector<int16_t> make_audio(size_t quiet, size_t speech, size_t trailing_silence) {
    std::vector<int16_t> a;
    uint32_t noise=12345;
    auto hiss=[&]() { noise=noise*1103515245u+12345u; return int16_t(int((noise>>16)%21)-10); };
    for(size_t i=0;i<quiet;++i)a.push_back(hiss());
    for(size_t i=0;i<speech;++i) {
        const size_t phase=i%(R*3/10);                       // 300 ms period
        const bool burst=phase<R*23/100;                     // 230 ms burst, 70 ms gap
        a.push_back(burst ? int16_t(6000*std::sin(2*M_PI*220.0*double(i)/R)) : hiss());
    }
    for(size_t i=0;i<trailing_silence;++i)a.push_back(hiss());
    return a;
}
bool in_gap(uint64_t absolute, size_t quiet) {
    if(absolute<quiet)return true;
    const size_t phase=size_t(absolute-quiet)%(R*3/10);
    return phase>=R*23/100;
}
struct Run { std::vector<SpeechSegment> segs; std::vector<std::vector<int16_t>> pcm; };
Run run(const std::vector<int16_t>& audio, size_t search, bool finish_with_pending=false) {
    SegmenterConfig c;
    c.adaptive=true; c.min_segment_samples=4*R; c.noise_percentile=25;
    c.silence_blip_samples=3*kSegmentAnalysisSamples; c.hard_cut_search_samples=search;
    static std::vector<int16_t> buffer(kSegmentMaximumSamples);
    Segmenter s; assert(s.reset(buffer.data(),buffer.size(),c));
    Run out;
    size_t at=0;
    while(at<audio.size()) {
        const auto r=s.push(audio.data()+at,audio.size()-at);
        at+=r.consumed;
        if(r.status==SegmentStatus::Ready) {
            if(finish_with_pending && s.segment()->end==SegmentEnd::HardLimit) {
                assert(s.finish()==SegmentStatus::Ready);
                out.segs.push_back(*s.segment());
                out.pcm.emplace_back(s.segment()->pcm,s.segment()->pcm+s.segment()->samples);
                assert(s.release());
                return out;
            }
            out.segs.push_back(*s.segment());
            out.pcm.emplace_back(s.segment()->pcm,s.segment()->pcm+s.segment()->samples);
            assert(s.release());
        } else assert(r.status==SegmentStatus::Ok);
    }
    if(s.finish()==SegmentStatus::Ready) {
        out.segs.push_back(*s.segment());
        out.pcm.emplace_back(s.segment()->pcm,s.segment()->pcm+s.segment()->samples);
        assert(s.release());
    }
    return out;
}
// Every delivered sample equals the input at its absolute offset; continuations
// start exactly where the previous segment ended.
void check_exact(const Run& r, const std::vector<int16_t>& audio) {
    for(size_t k=0;k<r.segs.size();++k) {
        const auto& g=r.segs[k];
        assert(g.end_sample-g.start_sample==g.samples);
        assert(g.overlap_before_samples==0);
        for(size_t i=0;i<g.samples;++i)assert(r.pcm[k][i]==audio[g.start_sample+i]);
        if(k && g.continuation)assert(g.start_sample==r.segs[k-1].end_sample);
    }
}
}  // namespace

int main() {
    const size_t quiet=R;  // 1 s room tone (calibration + idle)
    // 1. 50 s of unbroken speech: quiet cuts land in gaps, delivery is exact.
    {
        const auto audio=make_audio(quiet,50*R,2*R);
        const auto r=run(audio,2*R);
        assert(r.segs.size()>=3);
        check_exact(r,audio);
        size_t hard=0;
        for(const auto& g:r.segs) if(g.end==SegmentEnd::HardLimit) {
            ++hard;
            assert(g.samples<=kSegmentMaximumSamples && g.samples>=kSegmentMaximumSamples-2*R);
            assert(in_gap(g.end_sample,quiet));          // between "words"
        }
        assert(hard>=2);
        // Nothing of the speech is missing: union of segments covers it.
        assert(r.segs.front().start_sample<=quiet && r.segs.back().end_sample>=quiet+50*R);
        std::printf("PASS quiet cuts in gaps, exact contiguous delivery (%zu segments, %zu hard)\n",r.segs.size(),hard);
    }
    // 2. Default (search 0): exact-limit cuts, as before the option existed.
    {
        const auto audio=make_audio(quiet,50*R,2*R);
        const auto r=run(audio,0);
        check_exact(r,audio);
        for(const auto& g:r.segs) if(g.end==SegmentEnd::HardLimit) assert(g.samples==kSegmentMaximumSamples);
        std::printf("PASS search 0 keeps exact-limit cuts\n");
    }
    // 3. Speech stops ~1 s after the limit: the carried tail is still delivered.
    {
        const size_t speech=20*R+R;  // limit reached, then 1 s more speech, then silence
        const auto audio=make_audio(quiet,speech,3*R);
        const auto r=run(audio,2*R);
        check_exact(r,audio);
        assert(r.segs.size()==2 && r.segs[0].end==SegmentEnd::HardLimit && r.segs[1].continuation);
        assert(r.segs[1].end_sample>=quiet+speech-R/10);  // last burst included
        std::printf("PASS carried tail delivered when speech stops after a cut\n");
    }
    // 4. finish() while a quiet cut is pending delivers the carry too.
    {
        const auto audio=make_audio(quiet,25*R,0);
        const auto r=run(audio,2*R,true);
        assert(r.segs.size()==1);
        assert(r.segs[0].samples==kSegmentMaximumSamples);  // whole buffer, cut undone
        check_exact(r,audio);
        std::printf("PASS finish with a pending cut keeps the carry\n");
    }
    // 5. Invalid settings are rejected.
    {
        std::vector<int16_t> b(kSegmentMaximumSamples);
        Segmenter s; SegmenterConfig c;
        c.hard_cut_search_samples=2*R; c.forced_overlap_samples=kSegmentAnalysisSamples;
        assert(!s.reset(b.data(),b.size(),c));
        c.forced_overlap_samples=0; c.hard_cut_search_samples=2*R+1;
        assert(!s.reset(b.data(),b.size(),c));
        c.hard_cut_search_samples=11*R;
        assert(!s.reset(b.data(),b.size(),c));
        std::printf("PASS invalid quiet-cut settings rejected\n");
    }
    // 6. Stress: irregular speech (random burst/gap lengths, some long pauses)
    //    pushed in random chunk sizes; delivery stays exact and in bounds.
    {
        uint32_t rng=7;
        auto next=[&](uint32_t n) { rng=rng*1664525u+1013904223u; return (rng>>8)%n; };
        std::vector<int16_t> audio(quiet,0);
        while(audio.size()<180*R) {
            const size_t burst=R/20+next(R/2), gap=next(80)<79 ? R/100+next(R/10) : R+next(R);
            for(size_t i=0;i<burst;++i)audio.push_back(int16_t(5000*std::sin(2*M_PI*180.0*double(audio.size())/R)));
            for(size_t i=0;i<gap;++i)audio.push_back(int16_t(int(next(21))-10));
        }
        SegmenterConfig c;
        c.adaptive=true; c.min_segment_samples=4*R; c.noise_percentile=25;
        c.silence_blip_samples=3*kSegmentAnalysisSamples; c.hard_cut_search_samples=2*R;
        std::vector<int16_t> buffer(kSegmentMaximumSamples);
        Segmenter s; assert(s.reset(buffer.data(),buffer.size(),c));
        Run r; size_t at=0;
        while(at<audio.size()) {
            const size_t want=1+next(4000);
            const size_t n=want<audio.size()-at ? want : audio.size()-at;
            size_t done=0;
            while(done<n) {
                const auto res=s.push(audio.data()+at+done,n-done);
                done+=res.consumed;
                if(res.status==SegmentStatus::Ready) {
                    r.segs.push_back(*s.segment());
                    r.pcm.emplace_back(s.segment()->pcm,s.segment()->pcm+s.segment()->samples);
                    assert(s.release());
                } else assert(res.status==SegmentStatus::Ok);
            }
            at+=n;
        }
        if(s.finish()==SegmentStatus::Ready) {
            r.segs.push_back(*s.segment());
            r.pcm.emplace_back(s.segment()->pcm,s.segment()->pcm+s.segment()->samples);
            assert(s.release());
        }
        check_exact(r,audio);
        size_t hard=0;
        for(const auto& g:r.segs) { assert(g.samples<=kSegmentMaximumSamples); hard+=g.end==SegmentEnd::HardLimit; }
        std::printf("PASS stress: %zu segments (%zu quiet cuts), random chunks, exact and in bounds\n",r.segs.size(),hard);
    }
    std::printf("quiet-cut segmenter tests passed\n");
}
