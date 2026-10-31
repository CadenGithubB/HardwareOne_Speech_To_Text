#pragma once
// Offline experiment only. Confirm speakers with a complete-link group of
// distinct long phrases, then reconsider bounded pending phrases. Published
// labels are immutable. Resolving a pending phrase does not train the centroid.
#include <cmath>
#include <cstddef>
#include <utility>
#include <vector>

namespace hw1::stt::speaker {

struct DeferredLabel {
    int speaker=-1;
    const char* reason="pending";
    size_t delay=0;
};

class ProvisionalClusters {
 public:
    ProvisionalClusters(size_t dim, unsigned evidence, size_t window=8,
                        float threshold=0.6f, size_t minimum=32000, size_t capacity=8)
        : dim_(dim), evidence_(evidence), window_(window), threshold_(threshold),
          minimum_(minimum), capacity_(capacity) {}

    void push(const float* embedding, size_t samples) {
        const size_t now=labels_.size();
        labels_.push_back({});
        // An expired phrase cannot be resurrected by arbitrarily late evidence.
        for(size_t i=0;i<pending_.size();) {
            if(now-pending_[i].at>=window_) finish(i,now,"expired"); else ++i;
        }
        double norm=0;
        for(size_t i=0;i<dim_;++i) {
            if(!std::isfinite(embedding[i])) { labels_.back().reason="invalid"; return; }
            norm+=double(embedding[i])*embedding[i];
        }
        if(!(norm>0) || !std::isfinite(norm) || !samples) {
            labels_.back().reason="invalid"; return;
        }
        std::vector<float> e(dim_);
        for(size_t i=0;i<dim_;++i)e[i]=float(embedding[i]/std::sqrt(norm));
        const int match=unique(e);
        if(match>=0) {
            labels_.back()={match,samples>=minimum_ ? "match" : "short_match",0};
            if(samples>=minimum_)for(size_t i=0;i<dim_;++i)sums_[size_t(match)][i]+=e[i];
        } else pending_.push_back({now,samples,std::move(e)});
        resolve(now);
        while(sums_.size()<capacity_) {
            const auto group=confirmation();
            if(group.empty())break;
            std::vector<float> sum(dim_,0);
            for(size_t p:group)for(size_t j=0;j<dim_;++j)sum[j]+=pending_[p].e[j];
            const int id=int(sums_.size());
            sums_.push_back(std::move(sum));
            for(auto it=group.rbegin();it!=group.rend();++it) {
                const auto& p=pending_[*it];
                labels_[p.at]={id,"confirmed",now-p.at};
                pending_.erase(pending_.begin()+long(*it));
            }
            resolve(now);
        }
        // Both phrase count and age are bounded; overflow finalizes as unknown.
        while(pending_.size()>window_)finish(0,now,"overflow");
    }

    void flush() {
        if(labels_.empty())return;
        const size_t now=labels_.size()-1;
        resolve(now);
        while(!pending_.empty())finish(0,now,"end_unknown");
    }
    const std::vector<DeferredLabel>& labels() const { return labels_; }
    size_t pending() const { return pending_.size(); }

 private:
    struct Pending { size_t at,samples; std::vector<float> e; };
    float cosine(const std::vector<float>& a,const std::vector<float>& b) const {
        double dot=0,aa=0,bb=0;
        for(size_t i=0;i<dim_;++i) { dot+=double(a[i])*b[i];aa+=double(a[i])*a[i];bb+=double(b[i])*b[i]; }
        return aa>0 && bb>0 ? float(dot/std::sqrt(aa*bb)) : -1;
    }
    // -1: none, -2: ambiguous. Only confirmed speakers are considered.
    int unique(const std::vector<float>& e) const {
        int best=-1;
        for(size_t s=0;s<sums_.size();++s)if(cosine(e,sums_[s])>=threshold_) {
            if(best>=0)return -2;
            best=int(s);
        }
        return best;
    }
    void resolve(size_t now) {
        for(size_t i=0;i<pending_.size();) {
            const int m=unique(pending_[i].e);
            if(m<0) { ++i;continue; }
            // No centroid update: delayed labels must not bootstrap their own evidence.
            labels_[pending_[i].at]={m,"resolved",now-pending_[i].at};
            pending_.erase(pending_.begin()+long(i));
        }
    }
    void finish(size_t i,size_t now,const char* why) {
        const auto& p=pending_[i];
        labels_[p.at]={-1,why,now-p.at};
        pending_.erase(pending_.begin()+long(i));
    }
    std::vector<size_t> confirmation() const {
        // A complete-link pair/triple must be mutually similar and currently
        // match no confirmed speaker. Lexicographic order breaks ties causally.
        for(size_t a=0;a<pending_.size();++a) {
            if(!eligible(a))continue;
            for(size_t b=a+1;b<pending_.size();++b) {
                if(!eligible(b) || cosine(pending_[a].e,pending_[b].e)<threshold_)continue;
                if(evidence_==2)return {a,b};
                for(size_t c=b+1;c<pending_.size();++c)if(eligible(c) &&
                    cosine(pending_[a].e,pending_[c].e)>=threshold_ &&
                    cosine(pending_[b].e,pending_[c].e)>=threshold_)return {a,b,c};
            }
        }
        return {};
    }
    bool eligible(size_t p) const { return pending_[p].samples>=minimum_ && unique(pending_[p].e)==-1; }
    size_t dim_;
    unsigned evidence_;
    size_t window_;
    float threshold_;
    size_t minimum_,capacity_;
    std::vector<DeferredLabel> labels_;
    std::vector<Pending> pending_;
    std::vector<std::vector<float>> sums_;
};
} // namespace hw1::stt::speaker
