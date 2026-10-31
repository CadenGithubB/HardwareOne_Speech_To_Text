#pragma once
// Session speaker labels from phrase embeddings, independent of the embedding
// model (any dimension; embeddings are made unit length here).
//
// A phrase joins a speaker only when exactly one centroid meets the model's
// cosine `threshold`. Multiple qualifying centroids are ambiguous: abstain
// rather than inventing a second margin or breaking the tie by cluster order.
// With no match, `min_new_samples` of audio are required to start any speaker,
// including the first. At capacity, or with insufficient audio, return unknown.
// Short phrases may match a known speaker but never move its centroid.
//
// This favors attribution precision over label coverage. Unknown phrases are
// not reassigned later. `samples` is duration supplied by the caller, not a
// measure of voiced audio; the caller must reject empty/non-speech evidence.
//
// Storage is caller-provided (max_speakers * dim floats), so the caller decides
// where it lives (PSRAM on the P4). No allocation, no exceptions.
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace hw1::stt::speaker {

struct ClusterConfig {
    float threshold=0.6f;              // cosine similarity to join a speaker
    size_t min_new_samples=2*16000;    // minimum duration to seed/update a centroid
    uint8_t max_speakers=8;
};

enum class AssignmentReason : uint8_t {
    Invalid, New, Match, ShortMatch, Ambiguous, NoMatchShort, Capacity
};

inline const char* assignmentReasonName(AssignmentReason reason) {
    switch(reason) {
        case AssignmentReason::New: return "new";
        case AssignmentReason::Match: return "match";
        case AssignmentReason::ShortMatch: return "short_match";
        case AssignmentReason::Ambiguous: return "ambiguous";
        case AssignmentReason::NoMatchShort: return "no_match_short";
        case AssignmentReason::Capacity: return "capacity";
        case AssignmentReason::Invalid: return "invalid";
    }
    return "invalid";
}

struct Assignment {
    int8_t speaker=-1;      // 0-based session label, -1 = unknown or invalid input
    float similarity=0;     // best existing match (1 for a new speaker)
    bool created=false;     // this phrase started the speaker
    bool tentative=false;   // valid evidence but no defensible label; centroid untouched
    // Decision evidence from the profiles BEFORE this assignment. Similarity
    // is zero when the corresponding candidate ID is absent; exact ties retain
    // profile order. No embeddings or additional profile storage are exposed.
    uint8_t profilesBefore=0, profilesAfter=0; // stored profile counts across the assignment
    uint8_t matches=0; // pre-assignment profiles meeting the model threshold
    int8_t bestSpeaker=-1, secondSpeaker=-1;
    float bestSimilarity=0, secondSimilarity=0;
    bool centroidUpdated=false; // an EXISTING centroid accumulated this phrase; creation uses created
    AssignmentReason reason=AssignmentReason::Invalid;
};

class Clusters {
 public:
    // storage: max_speakers * dim floats.
    bool reset(float* storage, size_t dim, const ClusterConfig& config) {
        if(!storage || !dim || !config.max_speakers || config.max_speakers>kMaxSpeakers ||
           !config.min_new_samples || !(config.threshold>-1.0f && config.threshold<1.0f))return false;
        sums_=storage; dim_=dim; config_=config; count_=0;
        return true;
    }
    size_t speakers() const { return count_; }

    // embedding: dim floats (any scale); samples: the phrase's audio length.
    Assignment assign(const float* embedding, size_t samples) {
        Assignment out;
        out.profilesBefore=out.profilesAfter=uint8_t(count_);
        if(!sums_ || !embedding || !samples)return out;
        double norm=0;
        for(size_t i=0;i<dim_;++i) {
            if(!std::isfinite(embedding[i]))return out;
            norm+=double(embedding[i])*embedding[i];
        }
        if(!(norm>0) || !std::isfinite(norm))return out;
        const double inv=1.0/std::sqrt(norm);
        int best=-1, second=-1; float bestSim=-2.0f, secondSim=-2.0f; size_t matches=0;
        for(size_t s=0;s<count_;++s) {
            const float sim=similarity(s,embedding,inv);
            if(sim>bestSim) {
                second=best; secondSim=bestSim;
                bestSim=sim; best=int(s);
            } else if(sim>secondSim) { secondSim=sim; second=int(s); }
            if(sim>=config_.threshold)++matches;
        }
        const bool longEnough=samples>=config_.min_new_samples;
        out.similarity=best<0 ? 0.0f : bestSim;
        out.bestSpeaker=int8_t(best); out.secondSpeaker=int8_t(second);
        out.bestSimilarity=best<0 ? 0.0f : bestSim;
        out.secondSimilarity=second<0 ? 0.0f : secondSim;
        out.matches=uint8_t(matches);
        if(!matches && longEnough && count_<config_.max_speakers) {
            const size_t s=count_++;
            float* c=sums_+s*dim_;
            for(size_t i=0;i<dim_;++i)c[i]=float(double(embedding[i])*inv);
            out.speaker=int8_t(s); out.similarity=1.0f; out.created=true;
            out.profilesAfter=uint8_t(count_); out.reason=AssignmentReason::New;
            return out;
        }
        if(matches!=1) {
            out.tentative=true;
            out.reason=matches>1 ? AssignmentReason::Ambiguous :
                       !longEnough ? AssignmentReason::NoMatchShort : AssignmentReason::Capacity;
            return out;
        }
        out.speaker=int8_t(best);
        if(!longEnough) { out.reason=AssignmentReason::ShortMatch; return out; }
        float* c=sums_+size_t(best)*dim_;
        for(size_t i=0;i<dim_;++i)c[i]+=float(double(embedding[i])*inv); // running sum of unit embeddings
        out.centroidUpdated=true; out.reason=AssignmentReason::Match;
        return out;
    }

 private:
    float similarity(size_t s,const float* e,double inv) const {
        const float* c=sums_+s*dim_;
        double dot=0,cc=0;
        for(size_t i=0;i<dim_;++i) { dot+=double(c[i])*e[i]; cc+=double(c[i])*c[i]; }
        return cc>0 ? float(dot*inv/std::sqrt(cc)) : -1.0f;
    }
    static constexpr size_t kMaxSpeakers=128; // IDs 0..127 fit Assignment::speaker.
    float* sums_=nullptr;
    size_t dim_=0, count_=0;
    ClusterConfig config_;
};

}  // namespace hw1::stt::speaker
