#pragma once
// Offline candidate speaker-labelling rules beside the production clusterer
// (firmware/components/hw1_stt/stt/speaker_cluster.h), for spkrules.py. Not
// used by firmware. The arithmetic copies the production class (float running
// sums of unit embeddings, double accumulation), so with new_below >= threshold
// and merge_young == 0 it makes the production decisions; tests/test_spkrules.py
// checks that on random sequences.
//
//   hold   A long phrase that matches no speaker starts a new one only if its
//          best similarity is below new_below. Between new_below and the
//          threshold it is unknown ("hold") and changes nothing. young > 0
//          applies this only while that closest speaker holds fewer than
//          `young` phrases.
//   merge  A phrase matching exactly two speakers, when the smaller holds
//          fewer than merge_young phrases and the two centroids' similarity is
//          at least merge_sim, merges the smaller into the larger (the older on
//          a tie). The phrase takes the surviving label and, if long enough,
//          updates it ("merge"). Labels already given to the merged speaker are
//          not rewritten, as captions already shown keep theirs.
// IDs stay those of creation; capacity counts the speakers still active.
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <utility>
#include <vector>

namespace hw1::stt::speaker {

struct CandidateConfig {
    float threshold=0.6f;
    size_t min_new_samples=2*16000;
    uint8_t max_speakers=8;
    float new_below=2.0f;    // >= threshold: production creation
    unsigned young=0;        // 0: hold regardless of the closest speaker's size
    unsigned merge_young=0;  // 0: never merge
    float merge_sim=-2.0f;
    size_t create_min_samples=0; // zero inherits min_new_samples
    size_t update_min_samples=0; // independently gate centroid adaptation
    unsigned defer_steps=0; // replay-only revision window in subsequent phrases
    unsigned history_cap=0; // zero: unbounded; otherwise exponentially forget after cap
    float ambiguity_margin=0.0f; // zero disables; label only, never adapt centroid
};

struct CandidateResult {
    int speaker=-1;
    const char* reason="invalid";
};

class CandidateClusters {
 public:
    bool reset(size_t dim, const CandidateConfig& config) {
        if((config.history_cap && config.merge_young) || !dim || !config.max_speakers || !config.min_new_samples ||
           !(config.threshold>-1.0f && config.threshold<1.0f))return false;
        dim_=dim; config_=config; ids_.clear(); phrases_.clear(); sums_.clear(); next_=0;
        return true;
    }

    CandidateResult assign(const float* embedding, size_t samples) {
        CandidateResult out;
        if(!embedding || !samples)return out;
        double norm=0;
        for(size_t i=0;i<dim_;++i) {
            if(!std::isfinite(embedding[i]))return out;
            norm+=double(embedding[i])*embedding[i];
        }
        if(!(norm>0) || !std::isfinite(norm))return out;
        const double inv=1.0/std::sqrt(norm);
        int best=-1, second=-1; float bestSim=-2.0f, secondSim=-2.0f; size_t matches=0;
        for(size_t s=0;s<ids_.size();++s) {
            const float sim=similarity(&sums_[s*dim_],embedding,inv);
            if(sim>bestSim) { second=best; secondSim=bestSim; bestSim=sim; best=int(s); }
            else if(sim>secondSim) { secondSim=sim; second=int(s); }
            if(sim>=config_.threshold)++matches;
        }
        const bool createEnough=samples>=(config_.create_min_samples ? config_.create_min_samples : config_.min_new_samples);
        const bool updateEnough=samples>=(config_.update_min_samples ? config_.update_min_samples : config_.min_new_samples);
        if(!matches && createEnough && ids_.size()<config_.max_speakers) {
            const bool hold=best>=0 && bestSim>=config_.new_below &&
                (!config_.young || phrases_[size_t(best)]<config_.young);
            if(hold) { out.reason="hold"; return out; }
            ids_.push_back(next_++); phrases_.push_back(1);
            sums_.resize(ids_.size()*dim_);
            float* c=&sums_[(ids_.size()-1)*dim_];
            for(size_t i=0;i<dim_;++i)c[i]=float(double(embedding[i])*inv);
            out.speaker=ids_.back(); out.reason="new";
            return out;
        }
        if(matches==2 && config_.merge_young && secondSim>=config_.threshold) {
            size_t keep=size_t(best), drop=size_t(second);
            if(phrases_[drop]>phrases_[keep] || (phrases_[drop]==phrases_[keep] && ids_[drop]<ids_[keep]))
                std::swap(keep,drop);
            if(phrases_[drop]<config_.merge_young && centroidSimilarity(keep,drop)>=config_.merge_sim) {
                float* k=&sums_[keep*dim_]; const float* d=&sums_[drop*dim_];
                for(size_t i=0;i<dim_;++i)k[i]+=d[i];
                phrases_[keep]+=phrases_[drop];
                const int survivor=ids_[keep];
                erase(drop);
                const size_t s=index(survivor);
                if(updateEnough) {
                    float* c=&sums_[s*dim_];
                    for(size_t i=0;i<dim_;++i)c[i]+=float(double(embedding[i])*inv);
                    ++phrases_[s];
                }
                out.speaker=survivor; out.reason="merge";
                return out;
            }
        }
        if(matches>1 && config_.ambiguity_margin>0 &&
           bestSim-secondSim>=config_.ambiguity_margin) {
            out.speaker=ids_[size_t(best)]; out.reason="ambiguous_margin";
            return out;
        }
        if(matches!=1) {
            out.reason=matches>1 ? "ambiguous" : !createEnough ? "no_match_short" : "capacity";
            return out;
        }
        out.speaker=ids_[size_t(best)];
        if(!updateEnough) { out.reason="short_match"; return out; }
        float* c=&sums_[size_t(best)*dim_];
        if(config_.history_cap && phrases_[size_t(best)]>=config_.history_cap) {
            const float retain=float(config_.history_cap-1)/float(config_.history_cap);
            for(size_t i=0;i<dim_;++i)c[i]*=retain;
        }
        for(size_t i=0;i<dim_;++i)c[i]+=float(double(embedding[i])*inv);
        ++phrases_[size_t(best)];
        out.reason="match";
        return out;
    }

    // Query current profiles without creating or adapting one. Only unique matches resolve.
    int resolve(const float* embedding) const {
        if(!embedding)return -1;
        double norm=0;
        for(size_t i=0;i<dim_;++i) {
            if(!std::isfinite(embedding[i]))return -1;
            norm+=double(embedding[i])*embedding[i];
        }
        if(!(norm>0) || !std::isfinite(norm))return -1;
        const double inv=1.0/std::sqrt(norm);
        int winner=-1; unsigned matches=0;
        for(size_t s=0;s<ids_.size();++s)
            if(similarity(&sums_[s*dim_],embedding,inv)>=config_.threshold) {
                winner=ids_[s];++matches;
            }
        return matches==1 ? winner : -1;
    }

 private:
    float similarity(const float* c,const float* e,double inv) const {
        double dot=0,cc=0;
        for(size_t i=0;i<dim_;++i) { dot+=double(c[i])*e[i]; cc+=double(c[i])*c[i]; }
        return cc>0 ? float(dot*inv/std::sqrt(cc)) : -1.0f;
    }
    float centroidSimilarity(size_t a,size_t b) const {
        const float* x=&sums_[a*dim_]; const float* y=&sums_[b*dim_];
        double dot=0,xx=0,yy=0;
        for(size_t i=0;i<dim_;++i) { dot+=double(x[i])*y[i]; xx+=double(x[i])*x[i]; yy+=double(y[i])*y[i]; }
        return xx>0 && yy>0 ? float(dot/std::sqrt(xx*yy)) : -1.0f;
    }
    void erase(size_t s) {
        ids_.erase(ids_.begin()+long(s)); phrases_.erase(phrases_.begin()+long(s));
        sums_.erase(sums_.begin()+long(s*dim_),sums_.begin()+long((s+1)*dim_));
    }
    size_t index(int id) const {
        for(size_t s=0;s<ids_.size();++s) if(ids_[s]==id) return s;
        return 0;
    }
    size_t dim_=0;
    CandidateConfig config_;
    std::vector<int> ids_;
    std::vector<unsigned> phrases_;
    std::vector<float> sums_;
    int next_=0;
};

}  // namespace hw1::stt::speaker
