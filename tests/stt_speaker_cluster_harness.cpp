#include "speaker_cluster.h"
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <utility>
#include <vector>

using hw1::stt::speaker::Assignment;
using hw1::stt::speaker::AssignmentReason;
using hw1::stt::speaker::assignmentReasonName;
using hw1::stt::speaker::ClusterConfig;
using hw1::stt::speaker::Clusters;

static size_t checks=0;
#define CHECK(value) do { ++checks; if(!(value)) { \
    std::fprintf(stderr,"line %d: %s\n",__LINE__,#value); std::exit(1); } } while(false)

static void unknown(const Assignment& a,bool uncertain=true) {
    CHECK(a.speaker==-1);
    CHECK(!a.created);
    CHECK(a.tentative==uncertain);
}

static void evidence_and_capacity() {
    std::array<float,8> storage{}; // two 3-D centroids, with untouched sentinels
    storage.front()=storage.back()=12345.0f;
    ClusterConfig config; config.max_speakers=2;
    Clusters clusters;
    CHECK(clusters.reset(storage.data()+1,3,config));
    const float a[]={1,0,0}, b[]={0,1,0}, c[]={0,0,1};
    const float shortMatch[]={0.8f,0.6f,0};
    unknown(clusters.assign(a,config.min_new_samples-1));
    CHECK(clusters.speakers()==0);
    auto result=clusters.assign(a,config.min_new_samples);
    CHECK(result.speaker==0 && result.created && !result.tentative);
    CHECK(clusters.speakers()==1);
    const auto before=storage;

    // A brief established match can be displayed, but cannot alter its voiceprint.
    for(int i=0;i<100;++i) {
        result=clusters.assign(shortMatch,1);
        CHECK(result.speaker==0 && !result.created && !result.tentative);
    }
    CHECK(storage==before);
    // A brief different voice cannot be attributed to the only known person.
    unknown(clusters.assign(b,config.min_new_samples-1));
    CHECK(clusters.speakers()==1 && storage==before);
    result=clusters.assign(b,config.min_new_samples);
    CHECK(result.speaker==1 && result.created);
    const auto atCapacity=storage;
    unknown(clusters.assign(c,config.min_new_samples));
    CHECK(clusters.speakers()==2 && storage==atCapacity);
    result=clusters.assign(a,config.min_new_samples);
    CHECK(result.speaker==0 && !result.created && !result.tentative);
    CHECK(storage[1]==2.0f); // sufficiently long unique matches still update
    CHECK(storage.front()==12345.0f && storage.back()==12345.0f);
}

static void ambiguity() {
    const float a[]={1,0}, b[]={0,1};
    // Both above the existing 0.6 threshold, with unequal scores: this is not
    // just a numerical tie. No extra, uncalibrated margin is introduced.
    const float ambiguous[]={0.75f,0.66f};
    const float clearA[]={0.95f,0.3f};
    for(bool reverse:{false,true}) {
        std::array<float,4> storage{};
        ClusterConfig config; config.max_speakers=2;
        Clusters clusters; CHECK(clusters.reset(storage.data(),2,config));
        CHECK(clusters.assign(reverse?b:a,32000).created);
        CHECK(clusters.assign(reverse?a:b,32000).created);
        const auto before=storage;
        for(size_t samples:{size_t(1),size_t(32000)})
            unknown(clusters.assign(ambiguous,samples));
        CHECK(clusters.speakers()==2 && storage==before);
        const auto result=clusters.assign(clearA,32000);
        CHECK(result.speaker==(reverse?1:0));
        CHECK(!result.created && !result.tentative);
        CHECK(storage!=before);
    }
}

static void model_policy_and_invalid_input() {
    std::array<float,4> storage{};
    ClusterConfig config; config.threshold=0.9f; config.min_new_samples=500; config.max_speakers=2;
    Clusters clusters; CHECK(clusters.reset(storage.data(),2,config));
    const float a[]={1,0}, below[]={0.8f,0.6f};
    unknown(clusters.assign(a,499));
    CHECK(clusters.assign(a,500).created);
    unknown(clusters.assign(below,499)); // honors metadata threshold, not 0.6 default
    CHECK(clusters.assign(below,500).speaker==1);
    const auto before=storage;
    const float zero[]={0,0};
    const float nan[]={std::numeric_limits<float>::quiet_NaN(),0};
    const float infinity[]={0,std::numeric_limits<float>::infinity()};
    for(const float* embedding:{zero,nan,infinity})unknown(clusters.assign(embedding,500),false);
    unknown(clusters.assign(nullptr,500),false);
    unknown(clusters.assign(a,0),false);
    CHECK(clusters.speakers()==2 && storage==before);

    // The class promises scale-independent embeddings, including finite float
    // extremes. Invalid input must never poison later valid assignments.
    for(float scale:{1.0e-40f,std::numeric_limits<float>::max()}) {
        const float scaled[]={scale,0};
        const auto result=clusters.assign(scaled,1);
        CHECK(result.speaker==0 && !result.tentative);
        CHECK(std::isfinite(result.similarity) && result.similarity>0.999f);
    }
    CHECK(storage==before);
    CHECK(clusters.reset(storage.data(),2,config));
    CHECK(clusters.speakers()==0);
    unknown(clusters.assign(a,499));
    CHECK(clusters.assign(below,500).speaker==0); // independent new session
}

static void configuration_and_id_bounds() {
    Clusters clusters;
    float small[2]={};
    const float a[]={1,0};
    unknown(clusters.assign(a,32000),false);
    ClusterConfig config;
    CHECK(!clusters.reset(nullptr,2,config));
    CHECK(!clusters.reset(small,0,config));
    config.max_speakers=0; CHECK(!clusters.reset(small,2,config));
    config.max_speakers=129; CHECK(!clusters.reset(small,2,config));
    config.max_speakers=1;
    config.min_new_samples=0; CHECK(!clusters.reset(small,2,config));
    config.min_new_samples=1;
    for(float threshold:{-1.0f,1.0f,std::numeric_limits<float>::quiet_NaN()}) {
        config.threshold=threshold; CHECK(!clusters.reset(small,2,config));
    }
    // Exercise the signed ID boundary against the real header, with guards on
    // caller-provided storage. No wrapped negative ID may be emitted as known.
    config.threshold=0.6f; config.max_speakers=128;
    constexpr size_t dim=129;
    std::vector<float> storage(128*dim+2,12345.0f), embedding(dim,0);
    CHECK(clusters.reset(storage.data()+1,dim,config));
    for(size_t s=0;s<128;++s) {
        embedding[s]=1;
        const auto result=clusters.assign(embedding.data(),1);
        CHECK(result.created && result.speaker==static_cast<int>(s));
        embedding[s]=0;
    }
    embedding[128]=1;
    unknown(clusters.assign(embedding.data(),1));
    CHECK(clusters.speakers()==128);
    CHECK(storage.front()==12345.0f && storage.back()==12345.0f);
}

// The diagnostic fields describe pre-assignment profiles; they must not
// change admission, matching, or whether existing centroid storage is written.
static void evidence(const Assignment& a,unsigned before,unsigned after,int best,int second,
                     unsigned matches,AssignmentReason reason,bool updated=false) {
    CHECK(a.profilesBefore==before && a.profilesAfter==after);
    CHECK(a.bestSpeaker==best && a.secondSpeaker==second);
    CHECK(a.matches==matches && a.matches<=a.profilesBefore);
    CHECK(a.reason==reason && a.centroidUpdated==updated);
    CHECK(std::isfinite(a.bestSimilarity) && std::isfinite(a.secondSimilarity));
    CHECK(best>=-1 && (best<0 || unsigned(best)<before));
    CHECK(second>=-1 && (second<0 || (unsigned(second)<before && second!=best)));
    if(best<0)CHECK(a.bestSimilarity==0.0f);
    if(second<0)CHECK(a.secondSimilarity==0.0f);
}
static void explanatory_assignments() {
    using R=AssignmentReason;
    const std::pair<R,const char*> names[]={
        {R::Invalid,"invalid"},{R::New,"new"},{R::Match,"match"},
        {R::ShortMatch,"short_match"},{R::Ambiguous,"ambiguous"},
        {R::NoMatchShort,"no_match_short"},{R::Capacity,"capacity"},
    };
    for(const auto& name:names)CHECK(!std::strcmp(assignmentReasonName(name.first),name.second));
    CHECK(!std::strcmp(assignmentReasonName(static_cast<R>(255)),"invalid"));
    evidence(Assignment{},0,0,-1,-1,0,R::Invalid);

    std::array<float,6> storage{};
    ClusterConfig config; config.max_speakers=2; config.min_new_samples=500;
    Clusters clusters; CHECK(clusters.reset(storage.data(),3,config));
    const float a[]={1,0,0}, b[]={0,1,0}, c[]={0,0,1};
    auto result=clusters.assign(a,499);
    unknown(result);evidence(result,0,0,-1,-1,0,R::NoMatchShort);
    result=clusters.assign(a,500);
    evidence(result,0,1,-1,-1,0,R::New);CHECK(result.created&&result.speaker==0&&result.similarity==1);
    result=clusters.assign(b,500);
    evidence(result,1,2,0,-1,0,R::New);
    // Creation keeps the old similarity=1 contract, while the new candidate
    // similarity still reports the real pre-existing (orthogonal) profile.
    CHECK(result.created&&result.speaker==1&&result.similarity==1&&result.bestSimilarity==0);
    const auto before=storage;
    const float shortA[]={0.8f,0.6f,0.1f};
    result=clusters.assign(shortA,499);
    evidence(result,2,2,0,1,1,R::ShortMatch);
    CHECK(result.speaker==0&&!result.created&&!result.tentative);
    const double scale=1/std::sqrt(1.01);
    CHECK(std::fabs(result.bestSimilarity-float(0.8*scale))<1e-6f);
    CHECK(std::fabs(result.secondSimilarity-float(0.6*scale))<1e-6f);
    CHECK(result.similarity==result.bestSimilarity);
    CHECK(std::memcmp(storage.data(),before.data(),sizeof(storage))==0);
    const float both[]={0.75f,0.66f,0};
    for(size_t samples:{size_t(1),size_t(500)}) {
        result=clusters.assign(both,samples);
        unknown(result);evidence(result,2,2,0,1,2,R::Ambiguous);
        CHECK(result.bestSimilarity>result.secondSimilarity&&result.secondSimilarity>=config.threshold);
        CHECK(std::memcmp(storage.data(),before.data(),sizeof(storage))==0);
    }
    // Duration takes precedence over capacity for an unmatched short phrase.
    result=clusters.assign(c,499);unknown(result);evidence(result,2,2,0,1,0,R::NoMatchShort);
    result=clusters.assign(c,500);unknown(result);evidence(result,2,2,0,1,0,R::Capacity);
    CHECK(result.bestSimilarity==0&&result.secondSimilarity==0); // exact ties keep profile order
    CHECK(std::memcmp(storage.data(),before.data(),sizeof(storage))==0);
    const float zero[]={0,0,0}, nan[]={1,std::numeric_limits<float>::quiet_NaN(),0};
    const float infinity[]={0,0,std::numeric_limits<float>::infinity()};
    for(const float* input:{zero,nan,infinity,static_cast<const float*>(nullptr)}) {
        result=clusters.assign(input,500);unknown(result,false);evidence(result,2,2,-1,-1,0,R::Invalid);
        CHECK(std::memcmp(storage.data(),before.data(),sizeof(storage))==0);
    }
    result=clusters.assign(a,0);unknown(result,false);evidence(result,2,2,-1,-1,0,R::Invalid);
    CHECK(std::memcmp(storage.data(),before.data(),sizeof(storage))==0);
    result=clusters.assign(b,500);evidence(result,2,2,1,0,1,R::Match,true);
    CHECK(result.speaker==1&&!result.created&&!result.tentative);
    CHECK(result.bestSimilarity==1&&result.secondSimilarity==0);
    CHECK(storage[0]==1&&storage[4]==2); // only the selected existing centroid changed
    CHECK(clusters.reset(storage.data(),3,config));
    result=clusters.assign(a,500);evidence(result,0,1,-1,-1,0,R::New); // diagnostics are run-local too
}
static void diagnostic_count_bounds() {
    using R=AssignmentReason;
    constexpr size_t dim=128;
    ClusterConfig config;config.max_speakers=128;config.min_new_samples=1;config.threshold=0.01f;
    std::vector<float> storage(dim*128),embedding(dim,0);
    Clusters clusters;CHECK(clusters.reset(storage.data(),dim,config));
    for(size_t i=0;i<dim;++i) {
        embedding[i]=1;
        const auto result=clusters.assign(embedding.data(),1);
        CHECK(result.reason==R::New&&result.profilesBefore==i&&result.profilesAfter==i+1);
        CHECK(!result.matches&&!result.centroidUpdated&&result.speaker==int(i));
        embedding[i]=0;
    }
    const auto before=storage;
    for(auto& v:embedding)v=1;
    const auto result=clusters.assign(embedding.data(),1);
    unknown(result);evidence(result,128,128,0,1,128,R::Ambiguous);
    CHECK(result.bestSimilarity==result.secondSimilarity&&result.bestSimilarity>config.threshold);
    CHECK(std::memcmp(storage.data(),before.data(),storage.size()*sizeof(float))==0);
}

int main() {
    evidence_and_capacity();
    ambiguity();
    model_policy_and_invalid_input();
    configuration_and_id_bounds();
    explanatory_assignments();
    diagnostic_count_bounds();
    std::printf("speaker cluster: %zu checks passed\n",checks);
}
