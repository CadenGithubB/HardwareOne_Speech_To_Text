#pragma once
// Session speaker labels from phrase embeddings, independent of the embedding
// model (any dimension; embeddings are made unit length here).
//
// Each phrase joins the speaker whose centroid it is most similar to (cosine)
// when that similarity reaches `threshold`. Below it, a phrase long enough to
// trust (`min_new_samples` of audio) starts a new speaker; a shorter one takes
// the closest speaker as a tentative label and does not move that centroid, so
// a mumbled "yeah" neither invents a person nor drags someone's voiceprint.
// The first phrase always starts speaker 0. Past `max_speakers`, phrases join
// the closest speaker.
//
// Storage is caller-provided (max_speakers * dim floats), so the caller decides
// where it lives (PSRAM on the P4). No allocation, no exceptions.
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace hw1::stt::speaker {

struct ClusterConfig {
    float threshold=0.6f;              // cosine similarity to join a speaker
    size_t min_new_samples=2*16000;    // a phrase this long may start a speaker
    uint8_t max_speakers=8;
};

struct Assignment {
    int8_t speaker=-1;      // 0-based session label, -1 = none (bad input)
    float similarity=0;     // to the chosen speaker (1 for a new one)
    bool created=false;     // this phrase started the speaker
    bool tentative=false;   // short phrase below the threshold: closest speaker, centroid untouched
};

class Clusters {
 public:
    // storage: max_speakers * dim floats.
    bool reset(float* storage, size_t dim, const ClusterConfig& config) {
        if(!storage || !dim || !config.max_speakers || !(config.threshold>-1.0f && config.threshold<1.0f))return false;
        sums_=storage; dim_=dim; config_=config; count_=0;
        std::memset(weights_,0,sizeof(weights_));
        return true;
    }
    size_t speakers() const { return count_; }

    // embedding: dim floats (any scale); samples: the phrase's audio length.
    Assignment assign(const float* embedding, size_t samples) {
        Assignment out;
        if(!sums_ || !embedding)return out;
        double norm=0;
        for(size_t i=0;i<dim_;++i)norm+=double(embedding[i])*embedding[i];
        if(!(norm>0))return out;
        const float inv=float(1.0/std::sqrt(norm));
        int best=-1; float bestSim=-2.0f;
        for(size_t s=0;s<count_;++s) {
            const float sim=similarity(s,embedding,inv);
            if(sim>bestSim) { bestSim=sim; best=int(s); }
        }
        const bool canCreate=count_<config_.max_speakers && (count_==0 || samples>=config_.min_new_samples);
        if(best<0 || (bestSim<config_.threshold && canCreate)) {
            const size_t s=count_++;
            float* c=sums_+s*dim_;
            for(size_t i=0;i<dim_;++i)c[i]=embedding[i]*inv;
            weights_[s]=1;
            out.speaker=int8_t(s); out.similarity=1.0f; out.created=true;
            return out;
        }
        out.speaker=int8_t(best); out.similarity=bestSim;
        if(bestSim<config_.threshold) { out.tentative=true; return out; }
        float* c=sums_+size_t(best)*dim_;
        for(size_t i=0;i<dim_;++i)c[i]+=embedding[i]*inv;   // running sum of unit embeddings
        ++weights_[best];
        return out;
    }

 private:
    float similarity(size_t s,const float* e,float inv) const {
        const float* c=sums_+s*dim_;
        double dot=0,cc=0;
        for(size_t i=0;i<dim_;++i) { dot+=double(c[i])*e[i]; cc+=double(c[i])*c[i]; }
        return cc>0 ? float(dot*inv/std::sqrt(cc)) : -1.0f;
    }
    static constexpr size_t kMaxSpeakers=255;
    float* sums_=nullptr;
    size_t dim_=0, count_=0;
    uint32_t weights_[kMaxSpeakers]={};
    ClusterConfig config_;
};

}  // namespace hw1::stt::speaker
