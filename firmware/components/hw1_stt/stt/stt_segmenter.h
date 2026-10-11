#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include "../Audio_VadPolicy.h"

namespace hw1::stt {
inline constexpr size_t kSegmentSampleRate=16000;
inline constexpr size_t kSegmentAnalysisSamples=160; // 10 ms, independent of push chunk size.
inline constexpr size_t kSegmentMaximumSamples=20*kSegmentSampleRate;
inline constexpr size_t kSegmentNoiseWindowFrames=500; // At most five seconds of 10 ms levels.

// Simple fixed/adaptive energy endpointing, not a neural voice-activity detector. All
// durations are samples and must be multiples of the 10 ms analysis frame.
struct SegmenterConfig {
    size_t max_segment_samples=kSegmentMaximumSamples;
    size_t min_segment_samples=8*kSegmentSampleRate;
    size_t pre_roll_samples=4800;
    size_t end_silence_samples=9600;
    size_t min_voice_samples=3200;
    size_t forced_overlap_samples=0;
    uint16_t rms_threshold=400; // Fixed mode, DC-removed RMS in native int16 PCM units.
    bool adaptive=false; // Opt in per consumer; existing fixed-mode behavior is unchanged.
    size_t calibration_samples=8000; // Initial 500 ms is ambient only, never admitted as speech.
    size_t noise_window_frames=kSegmentNoiseWindowFrames;
    // Raw-RMS defaults separate measured P4 room noise (3..31) from speech.
    // Callers may tune these for other microphones or acoustic conditions.
    uint16_t adaptive_speech_floor=45;
    uint16_t adaptive_silence_floor=16;
    // Opt-in for microphones with a jittery noise floor (e.g. the G2 glasses
    // mic, whose quiet frames swing ~21..60+ RMS). 0 keeps the minimum of the
    // window; 25 uses its lower quartile, which tracks the real background
    // instead of its quietest 10 ms frame.
    uint8_t noise_percentile=0;
    // Opt-in: louder runs up to this long do not restart the end-silence
    // count (a click or codec blip is not speech). 0 keeps the strict rule.
    size_t silence_blip_samples=0;
    // Opt-in: when a segment reaches max_segment_samples without a pause, cut
    // in the middle of the quietest 10 ms frame within its last N samples
    // (usually a gap between words) instead of at the exact limit. Samples
    // after the cut start the continuation as fresh audio (not overlap), so
    // every sample is still delivered exactly once. 0 cuts at the limit.
    // Requires forced_overlap_samples == 0.
    size_t hard_cut_search_samples=0;
    // Opt-in: a phrase still shorter than min_segment_samples also closes
    // once its pause reaches this many samples (>= end_silence_samples), so a
    // short reply is not held back by the minimum length. 0 keeps the strict
    // minimum length.
    size_t short_close_silence_samples=0;
};
enum class SegmentEnd : uint8_t { Pause, HardLimit, SessionEnd };
enum class SegmentStatus : uint8_t { Ok, Ready, Finished, InvalidArgument, NotInitialized, CounterOverflow };
struct SegmentPushResult { size_t consumed; SegmentStatus status; };
struct SpeechSegment {
    const int16_t* pcm=nullptr;
    size_t samples=0;
    uint64_t start_sample=0, end_sample=0; // Absolute session offsets, end exclusive.
    uint64_t fresh_start_sample=0; // Samples before this offset are explicit overlap.
    size_t overlap_before_samples=0;
    size_t next_overlap_samples=0; // Planned context if a hard-cut continuation is emitted.
    size_t new_voiced_samples=0; // Classified voiced samples, excluding retained overlap.
    SegmentEnd end=SegmentEnd::Pause;
    bool continuation=false;
    // Offset from start_sample of the end of the last ambient-voiced run
    // (level >= trimCut = max(silence floor, 2 x noise floor), the gate that
    // keeps quiet word tails) longer than silence_blip_samples, so 30 ms
    // clicks do not count. 0: no such run in this segment. Reported only; the
    // segment's samples are unchanged.
    size_t voiced_end_samples=0;
};

// Single-owner, no heap or platform dependencies. Buffer must remain valid and
// have at least config.max_segment_samples elements. Input must not alias it.
// push stops at one Ready result; only `consumed` samples belong to this call.
// Copy/queue segment()->pcm before release(), then push the unconsumed suffix.
// A ready segment is immutable until release/reset. Idle/noise gaps are skipped
// deliberately; absolute offsets identify them. Raw PCM is never filtered.
class Segmenter {
public:
    bool reset(int16_t* buffer,size_t capacity,const SegmenterConfig& config=SegmenterConfig{}) {
        if(!buffer || !valid(config) || capacity<config.max_segment_samples)return false;
        buffer_=buffer;config_=config;initialized_=true;reset_session();return true;
    }
    void reset_session() {
        seen_=start_=fresh_start_=0;used_=head_=history_=voice_=silence_=0;loud_run_=0;
        cut_=carry_voice_=0;
        voiced_run_=0;voiced_end_abs_=0;
        frame_count_=0;frame_sum_=0;frame_square_=0;
        active_=continuation_=ready_=finishing_=finished_=false;segment_={};
        calibrated_=!config_.adaptive;heard_speech_=false;calibration_seen_=0;
        noise_head_=noise_count_=0;current_rms_=noise_rms_=peak_rms_=0;
        threshold_rms_=config_.adaptive?config_.adaptive_speech_floor:config_.rms_threshold;
        std::memset(noise_window_,0,sizeof(noise_window_));
    }
    uint64_t samples_seen() const { return seen_; }
    bool calibrated() const { return initialized_ && calibrated_; }
    uint16_t current_rms() const { return current_rms_; }
    uint16_t noise_rms() const { return noise_rms_; }
    uint16_t threshold_rms() const { return threshold_rms_; }
    uint16_t peak_rms() const { return peak_rms_; }
    const SpeechSegment* segment() const { return ready_?&segment_:nullptr; }
    // Live view of the utterance still being captured (pre-roll included),
    // for draft transcription. Valid only on the pushing thread, until the
    // next push/release/reset. False while idle or before enough voice.
    bool in_progress(const int16_t** pcm,size_t* samples) const {
        if(!initialized_||!active_||ready_||!eligible()||!used_)return false;
        *pcm=buffer_;*samples=used_;return true;
    }
    // The open phrase's absolute start and length, from its first sample
    // (before it qualifies as eligible), so features can be computed while it
    // is captured. Pushing thread only.
    bool live_view(uint64_t* start,size_t* samples) const {
        if(!initialized_||!active_||ready_)return false;
        *start=start_;*samples=used_;return true;
    }
    // The in-progress phrase's final input if the current pause goes on to
    // close it. True once the phrase's voiced end (voiced_end_samples) plus
    // `tail` samples has been captured and that pause would close it as an
    // ordinary Pause below the hard limit: eligible, and at
    // end_silence_samples the minimum length reached by then or, with
    // short_close_silence_samples, at the short close or on reaching the
    // minimum, whichever comes first.
    // start/voiced_end/samples describe exactly the prefix the broker's
    // trailing-silence trim would infer. Same thread and lifetime rules as
    // in_progress().
    bool speculation(size_t tail,uint64_t* start,size_t* voiced_end_out,size_t* samples) const {
        if(!initialized_||!active_||ready_||finishing_||finished_||!eligible()||!silence_)return false;
        const size_t ve=voiced_end(used_);
        if(!ve || ve+tail>used_)return false;
        const size_t remaining=silence_<config_.end_silence_samples?config_.end_silence_samples-silence_:0;
        // Below the minimum length a continuing pause still closes the phrase
        // as a Pause, at short_close_silence_samples or on reaching the
        // minimum, whichever comes first (the evaluate_frame rule).
        size_t need=remaining;
        if(used_+remaining<config_.min_segment_samples) {
            if(!config_.short_close_silence_samples)return false;
            const size_t to_min=config_.min_segment_samples-used_;
            const size_t to_short=silence_<config_.short_close_silence_samples?config_.short_close_silence_samples-silence_:0;
            need=std::max(remaining,std::min(to_min,to_short));
        }
        if(used_+need>config_.max_segment_samples)return false;
        *start=start_;*voiced_end_out=ve;*samples=ve+tail;return true;
    }
    SegmentPushResult push(const int16_t* pcm,size_t count) {
        if(!initialized_)return {0,SegmentStatus::NotInitialized};
        if(ready_)return {0,SegmentStatus::Ready};
        if(finished_ || finishing_)return {0,SegmentStatus::Finished};
        if(!pcm && count)return {0,SegmentStatus::InvalidArgument};
        if(count>std::numeric_limits<uint64_t>::max()-seen_)return {0,SegmentStatus::CounterOverflow};
        size_t consumed=0;
        while(consumed<count) {
            const int16_t sample=pcm[consumed++];
            // Calibration advances absolute positions but cannot become pre-roll
            // or model input, even if it contains loud audio or ends mid-push.
            if(calibrated_) {
                if(active_)buffer_[used_++]=sample;
                else append_history(sample);
            }
            ++seen_;++frame_count_;frame_sum_+=sample;
            frame_square_+=static_cast<uint64_t>(static_cast<int64_t>(sample)*sample);
            if(frame_count_==kSegmentAnalysisSamples) {
                evaluate_frame(false);clear_frame();
                if(ready_)return {consumed,SegmentStatus::Ready};
            }
        }
        return {consumed,SegmentStatus::Ok};
    }
    // End the session. Flush qualified voiced tails even below the minimum
    // wall span; no empty/silence-only continuation is emitted. Calling finish
    // while a segment is ready keeps that view and seals the session on release.
    SegmentStatus finish() {
        if(!initialized_)return SegmentStatus::NotInitialized;
        finishing_=true;
        if(ready_) {
            // A pending quiet-point cut would leave its carry behind when the
            // session seals on release: deliver the whole buffer instead.
            if(cut_) { segment_.samples=used_;segment_.end_sample=seen_;cut_=carry_voice_=0;segment_.voiced_end_samples=voiced_end(used_); }
            return SegmentStatus::Ready;
        }
        if(finished_)return SegmentStatus::Finished;
        if(frame_count_) { evaluate_frame(true);clear_frame(); }
        if(active_ && eligible()) { publish(SegmentEnd::SessionEnd);return SegmentStatus::Ready; }
        finished_=true;active_=false;return SegmentStatus::Finished;
    }
    bool release() {
        if(!ready_)return false;
        ready_=false;
        if(finishing_) { active_=false;finished_=true;return true; }
        if(segment_.end==SegmentEnd::HardLimit && cut_) {
            // Quiet-point cut: the samples after the cut were never delivered,
            // so they open the continuation as fresh audio.
            const size_t keep=used_-cut_;
            if(keep)std::memmove(buffer_,buffer_+cut_,keep*sizeof(int16_t));
            used_=keep;start_=seen_-keep;fresh_start_=start_;
            voice_=carry_voice_;silence_=0;active_=true;continuation_=true;
            cut_=carry_voice_=0;
        } else if(segment_.end==SegmentEnd::HardLimit) {
            const size_t keep=config_.forced_overlap_samples;
            if(keep)std::memmove(buffer_,buffer_+used_-keep,keep*sizeof(int16_t));
            used_=keep;start_=seen_-keep;fresh_start_=seen_;
            voice_=0;active_=true;continuation_=true;
        } else {
            // Already-delivered trailing silence must not become a new segment's
            // pre-roll: the default zero-overlap mode is exactly nonoverlapping.
            used_=head_=history_=voice_=silence_=0;loud_run_=0;active_=continuation_=false;
            voiced_run_=0;voiced_end_abs_=0;
            reset_utterance_levels();
        }
        segment_={};return true;
    }
private:
    static bool aligned(size_t n) { return n%kSegmentAnalysisSamples==0; }
    static bool valid(const SegmenterConfig& c) {
        return c.max_segment_samples>=2*kSegmentAnalysisSamples && c.max_segment_samples<=kSegmentMaximumSamples
            && c.min_segment_samples>0 && c.min_segment_samples<=c.max_segment_samples
            && c.pre_roll_samples<=c.max_segment_samples-kSegmentAnalysisSamples
            && c.end_silence_samples>0 && c.end_silence_samples<=c.max_segment_samples
            && c.min_voice_samples>0 && c.min_voice_samples<=c.max_segment_samples-c.pre_roll_samples
            && c.forced_overlap_samples<c.max_segment_samples && c.rms_threshold>0 && c.rms_threshold<=32767
            && aligned(c.max_segment_samples) && aligned(c.min_segment_samples) && aligned(c.pre_roll_samples)
            && aligned(c.end_silence_samples) && aligned(c.min_voice_samples) && aligned(c.forced_overlap_samples)
            && (!c.adaptive || (c.noise_window_frames>0 && c.noise_window_frames<=kSegmentNoiseWindowFrames
                && c.calibration_samples>=kSegmentAnalysisSamples
                && c.calibration_samples<=kSegmentNoiseWindowFrames*kSegmentAnalysisSamples && aligned(c.calibration_samples)
                && c.adaptive_speech_floor>0 && c.adaptive_speech_floor<=32767
                && c.adaptive_silence_floor>0 && c.adaptive_silence_floor<=c.adaptive_speech_floor))
            && c.noise_percentile<=50 && aligned(c.silence_blip_samples)
            && c.silence_blip_samples<c.end_silence_samples
            && aligned(c.hard_cut_search_samples) && c.hard_cut_search_samples<=c.max_segment_samples/2
            && (!c.hard_cut_search_samples || !c.forced_overlap_samples)
            && aligned(c.short_close_silence_samples)
            && (!c.short_close_silence_samples || (c.short_close_silence_samples>=c.end_silence_samples
                && c.short_close_silence_samples<=c.max_segment_samples));
    }
    size_t history_capacity() const { return config_.pre_roll_samples+kSegmentAnalysisSamples; }
    void append_history(int16_t sample) {
        const size_t capacity=history_capacity();
        if(history_==capacity) { buffer_[head_]=sample;head_=(head_+1)%capacity; }
        else { buffer_[(head_+history_)%capacity]=sample;++history_; }
    }
    void reverse(size_t begin,size_t end) {
        while(begin<end) { --end;if(begin>=end)break;int16_t v=buffer_[begin];buffer_[begin++]=buffer_[end];buffer_[end]=v; }
    }
    void begin_segment() {
        // A full ring contains pre-roll plus the triggering analysis frame.
        if(head_) { reverse(0,head_);reverse(head_,history_);reverse(0,history_); }
        used_=history_;start_=seen_-used_;fresh_start_=start_;
        head_=history_=voice_=silence_=0;loud_run_=0;active_=true;continuation_=false;
    }
    bool eligible() const { return voice_>0 && (continuation_ || voice_>=config_.min_voice_samples); }
    void clear_frame() { frame_count_=0;frame_sum_=0;frame_square_=0; }
    void evaluate_frame(bool finalizing) {
        const uint64_t n=frame_count_;
        const uint64_t centered=frame_square_*n-static_cast<uint64_t>(frame_sum_*frame_sum_);
        // Integer floor(sqrt(variance)) is reproducible across hosts and chips;
        // the fixed-mode comparison below retains its original exact arithmetic.
        current_rms_=integer_sqrt(static_cast<uint32_t>(centered/(n*n)));
        bool voiced=false, silent=false;
        if(config_.adaptive) {
            const int32_t floor_before=noise_count_?noise_rms_:-1;
            const uint16_t window_min=track_noise(current_rms_);
            if(!calibrated_) {
                noise_rms_=window_min;calibration_seen_+=frame_count_;
                if(calibration_seen_>=config_.calibration_samples)calibrated_=true;
                threshold_rms_=onset_threshold();
                return;
            }
            // A sustained voice can fill the entire window. Do not learn it as
            // its own ambient floor after five seconds; retain the utterance's
            // seed while permitting quieter evidence to lower it. Natural
            // endpoints resume upward adaptation. A noise jump that resembles
            // speech is inherently ambiguous to this energy-only detector.
            if(!active_ || window_min<noise_rms_)noise_rms_=window_min;
            // No utterance exists while idle: an old ambient peak must not
            // prevent a quiet voice after the room/source becomes quieter.
            if(!active_ || current_rms_>peak_rms_)peak_rms_=current_rms_;
            const auto decision=hw1::audio::adaptiveVadDecision(current_rms_,floor_before,noise_rms_,peak_rms_,
                heard_speech_,{config_.adaptive_speech_floor,config_.adaptive_silence_floor});
            threshold_rms_=static_cast<uint16_t>(heard_speech_?decision.stopCut:
                (decision.stopCut>config_.adaptive_speech_floor?decision.stopCut:config_.adaptive_speech_floor));
            heard_speech_=decision.heardSpeech;
            // Peak-relative stop timing must never remove quiet word tails.
            // All admitted raw samples stay in the segment; floor-relative
            // evidence counts toward minimum voice duration independently.
            voiced=heard_speech_ && !decision.trimSilent;
            silent=decision.stopSilent;
        } else {
            if(current_rms_>peak_rms_)peak_rms_=current_rms_;
            const uint64_t threshold=uint64_t(config_.rms_threshold)*config_.rms_threshold*n*n;
            voiced=centered>=threshold;silent=!voiced;
        }
        if(!active_ && voiced)begin_segment();
        if(!active_)return;
        if(voiced)voice_+=frame_count_;
        // End of the last ambient-voiced run longer than the blip limit
        // (absolute samples, so it survives a quiet-cut continuation).
        if(voiced) { voiced_run_+=frame_count_; if(voiced_run_>config_.silence_blip_samples)voiced_end_abs_=seen_; }
        else voiced_run_=0;
        if(silent) { silence_+=frame_count_; loud_run_=0; }
        else {
            loud_run_+=frame_count_;
            if(loud_run_>config_.silence_blip_samples)silence_=0;
        }
        if(finalizing)return;
        // Below the minimum length a pause closes the phrase only once it
        // reaches short_close_silence_samples; at or above it, end_silence.
        const bool pause=silence_>=config_.end_silence_samples &&
            (used_>=config_.min_segment_samples ||
             (config_.short_close_silence_samples && silence_>=config_.short_close_silence_samples));
        if(pause || used_>=config_.max_segment_samples) {
            if(!eligible())discard_candidate();
            else if(pause || !config_.hard_cut_search_samples)publish(pause?SegmentEnd::Pause:SegmentEnd::HardLimit);
            else publish_quiet_cut();
        }
    }
    static uint16_t integer_sqrt(uint32_t value) {
        uint32_t result=0,bit=uint32_t(1)<<30;
        while(bit>value)bit>>=2;
        while(bit) {
            if(value>=result+bit) { value-=result+bit;result=(result>>1)+bit; }
            else result>>=1;
            bit>>=2;
        }
        return static_cast<uint16_t>(result);
    }
    uint16_t track_noise(uint16_t level) {
        noise_window_[noise_head_]=level;
        noise_head_=(noise_head_+1)%config_.noise_window_frames;
        if(noise_count_<config_.noise_window_frames)++noise_count_;
        return window_floor();
    }
    // Minimum (default) or a low percentile of the ambient window. Percentiles
    // use a 2-RMS-wide histogram (0..190, larger levels in the last bin): no
    // copy of the window and 192 bytes of stack on the real-time capture task.
    uint16_t window_floor() const {
        if(!noise_count_)return 0;
        if(!config_.noise_percentile) {
            uint16_t minimum=noise_window_[0];
            for(size_t i=1;i<noise_count_;++i)if(noise_window_[i]<minimum)minimum=noise_window_[i];
            return minimum;
        }
        constexpr size_t kBins=96, kWidth=2;
        uint16_t bins[kBins]{};
        for(size_t i=0;i<noise_count_;++i) {
            const size_t bin=noise_window_[i]/kWidth;
            ++bins[bin<kBins?bin:kBins-1];
        }
        const size_t rank=noise_count_*config_.noise_percentile/100;
        size_t seen=0;
        for(size_t b=0;b<kBins;++b) {
            seen+=bins[b];
            if(seen>rank)return static_cast<uint16_t>(b*kWidth);
        }
        return static_cast<uint16_t>((kBins-1)*kWidth);
    }
    uint16_t onset_threshold() const {
        uint16_t threshold=static_cast<uint16_t>(2*noise_rms_);
        if(threshold<config_.adaptive_speech_floor)threshold=config_.adaptive_speech_floor;
        return threshold;
    }
    void reset_utterance_levels() {
        heard_speech_=false;peak_rms_=0;
        if(config_.adaptive) {
            if(noise_count_) {
                noise_rms_=window_floor();
            }
            threshold_rms_=onset_threshold();
        }
    }
    void publish(SegmentEnd end) {
        segment_={buffer_,used_,start_,seen_,fresh_start_,static_cast<size_t>(fresh_start_-start_),
                  end==SegmentEnd::HardLimit?config_.forced_overlap_samples:0,voice_,end,continuation_};
        segment_.voiced_end_samples=voiced_end(used_);
        ready_=true;
    }
    // Voiced end as an offset into the current segment, clamped to its first
    // `samples` samples; 0 when the last qualifying run ended before it.
    size_t voiced_end(size_t samples) const {
        if(voiced_end_abs_<=start_)return 0;
        const uint64_t offset=voiced_end_abs_-start_;
        return offset<samples?static_cast<size_t>(offset):samples;
    }
    // Hard limit with hard_cut_search_samples: find the analysis frame with the
    // least DC-removed energy in the last N samples (latest wins ties: the
    // shorter carry) and cut at its START, so the phrase ends in the quiet and
    // the carry stays a whole number of frames. Cuts must stay on the stream's
    // frame grid: limits are only checked at frame ends, and a carry of a
    // fractional frame would let the next phrase overrun the buffer (found by
    // ASan, 2026-10-02). Frames after the cut above the current threshold count
    // as the carry's voice, so a word right after the cut is not dropped as
    // silence if speech stops. Once per hard limit: N/160 frames of integer math.
    void publish_quiet_cut() {
        constexpr size_t F=kSegmentAnalysisSamples;
        // Buffer index i is a frame start when (start_+i) is on the grid.
        const size_t phase=static_cast<size_t>((F-start_%F)%F);
        const size_t search=config_.hard_cut_search_samples;
        size_t first=used_>search ? used_-search : 0;
        if(first<phase)first=phase;
        first+=(F-(first-phase)%F)%F;
        size_t best=0;   // 0: no candidate, cut at the limit
        uint64_t best_energy=std::numeric_limits<uint64_t>::max();
        for(size_t at=first; at+F<=used_; at+=F) {
            if(!at)continue;  // never an empty phrase
            const uint64_t e=frame_energy(at);
            if(e<=best_energy) { best_energy=e; best=at; }
        }
        if(!best) { publish(SegmentEnd::HardLimit); return; }
        cut_=best;
        carry_voice_=0;
        const uint64_t limit=uint64_t(threshold_rms_)*threshold_rms_*F*F;
        for(size_t at=best; at+F<=used_; at+=F)
            if(frame_energy(at)>=limit)carry_voice_+=F;
        segment_={buffer_,cut_,start_,start_+cut_,fresh_start_,static_cast<size_t>(fresh_start_-start_),
                  0,voice_,SegmentEnd::HardLimit,continuation_};
        segment_.voiced_end_samples=voiced_end(cut_);
        ready_=true;
    }
    // n^2 * variance of one analysis frame (same scale as evaluate_frame).
    uint64_t frame_energy(size_t at) const {
        int64_t sum=0; uint64_t square=0;
        for(size_t i=0;i<kSegmentAnalysisSamples;++i) {
            const int32_t v=buffer_[at+i];
            sum+=v; square+=static_cast<uint64_t>(static_cast<int64_t>(v)*v);
        }
        return square*kSegmentAnalysisSamples-static_cast<uint64_t>(sum*sum);
    }
    void discard_candidate() {
        const size_t fresh=static_cast<size_t>(seen_-fresh_start_);
        size_t keep=used_<history_capacity()?used_:history_capacity();
        // A rejected forced continuation may contain retained, already-delivered
        // context. Only fresh samples may seed a subsequent ordinary pre-roll.
        if(keep>fresh)keep=fresh;
        if(keep)std::memmove(buffer_,buffer_+used_-keep,keep*sizeof(int16_t));
        history_=keep;head_=used_=voice_=silence_=0;loud_run_=0;active_=continuation_=false;
        voiced_run_=0;voiced_end_abs_=0;
        reset_utterance_levels();
    }
    int16_t* buffer_=nullptr;
    SegmenterConfig config_{};
    SpeechSegment segment_{};
    uint64_t seen_=0,start_=0,fresh_start_=0;
    size_t used_=0,head_=0,history_=0,voice_=0,silence_=0,loud_run_=0;
    size_t cut_=0,carry_voice_=0;  // pending quiet-point cut (publish_quiet_cut -> release)
    size_t voiced_run_=0;          // current ambient-voiced run (samples)
    uint64_t voiced_end_abs_=0;    // end of the last run longer than the blip limit
    int64_t frame_sum_=0;
    uint64_t frame_square_=0;
    uint16_t frame_count_=0;
    uint16_t noise_window_[kSegmentNoiseWindowFrames]{};
    size_t noise_head_=0,noise_count_=0,calibration_seen_=0;
    uint16_t current_rms_=0,noise_rms_=0,threshold_rms_=0,peak_rms_=0;
    bool calibrated_=false,heard_speech_=false;
    bool initialized_=false,active_=false,continuation_=false,ready_=false,finishing_=false,finished_=false;
};
} // namespace hw1::stt
