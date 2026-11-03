// Replays phrase embeddings through the production speaker clusterer
// (firmware/components/hw1_stt/stt/speaker_cluster.h) for spkreplay.py, and
// through it or the offline candidate rules (cluster_candidates.h) for
// spkrules.py.
//
// stdin, one command per line:
//   config DIM THRESHOLD MIN_NEW_SAMPLES MAX_SPEAKERS   (starts a session)
//   phrase SAMPLES V1 ... VDIM                         (one assignment)
//   reset                                              (new session, same config; echoed)
//   clear DIM                                          (empties the stored phrase set)
//   load SAMPLES V1 ... VDIM                           (stores one phrase)
//   run KIND THRESHOLD MIN_NEW MAX_SPEAKERS NEW_BELOW YOUNG MERGE_YOUNG MERGE_SIM AMBIGUITY_MARGIN CREATE_MIN UPDATE_MIN HISTORY_CAP N I1 ... IN
//                                                      (a session over stored phrases in that order;
//                                                       KIND production or candidate)
// stdout: per phrase command
//   SPEAKER REASON MATCHES BEST BEST_SIM SECOND SECOND_SIM CREATED UPDATED
// and per run one line of SPEAKER:REASON tokens, in run order.
#include "speaker_cluster.h"
#include "cluster_candidates.h"
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace hw1::stt::speaker;

static bool run(std::istringstream& in, size_t dim, const std::vector<float>& stored,
                const std::vector<size_t>& samples) {
    std::string kind;
    CandidateConfig c;
    unsigned maxSpeakers = 0;
    size_t n = 0;
    in >> kind >> c.threshold >> c.min_new_samples >> maxSpeakers >> c.new_below >> c.young >> c.merge_young
       >> c.merge_sim >> c.ambiguity_margin >> c.create_min_samples >> c.update_min_samples >> c.history_cap >> n;
    c.max_speakers = uint8_t(maxSpeakers);
    std::vector<size_t> order(n);
    for (auto& i : order) in >> i;
    if (!in || !dim) return false;
    for (size_t i : order) if (i >= samples.size()) return false;
    std::string line;
    if (kind == "production") {
        ClusterConfig config;
        config.threshold = c.threshold; config.min_new_samples = c.min_new_samples; config.max_speakers = c.max_speakers;
        std::vector<float> storage(size_t(maxSpeakers) * dim);
        Clusters clusters;
        if (!clusters.reset(storage.data(), dim, config)) return false;
        for (size_t i : order) {
            const Assignment a = clusters.assign(&stored[i * dim], samples[i]);
            line += std::to_string(a.speaker) + ':' + assignmentReasonName(a.reason) + ' ';
        }
    } else if (kind == "candidate") {
        CandidateClusters clusters;
        if (!clusters.reset(dim, c)) return false;
        for (size_t i : order) {
            const CandidateResult a = clusters.assign(&stored[i * dim], samples[i]);
            line += std::to_string(a.speaker) + ':' + a.reason + ' ';
        }
    } else {
        return false;
    }
    std::puts(line.c_str());
    return true;
}

int main() {
    std::string line, command;
    size_t dim = 0, storedDim = 0;
    ClusterConfig config;
    std::vector<float> storage, embedding, stored;
    std::vector<size_t> storedSamples;
    Clusters clusters;
    bool ready = false;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        if (!(in >> command)) continue;
        if (command == "config") {
            unsigned maxSpeakers = 0;
            in >> dim >> config.threshold >> config.min_new_samples >> maxSpeakers;
            config.max_speakers = uint8_t(maxSpeakers);
            storage.assign(size_t(maxSpeakers) * dim, 0.0f);
            embedding.assign(dim, 0.0f);
            ready = in && clusters.reset(storage.data(), dim, config);
            if (!ready) { std::fprintf(stderr, "invalid config\n"); return 2; }
        } else if (command == "reset" && ready) {
            clusters.reset(storage.data(), dim, config);
            std::puts("reset");
        } else if (command == "phrase" && ready) {
            size_t samples = 0;
            in >> samples;
            for (auto& v : embedding) in >> v;
            if (!in) { std::fprintf(stderr, "bad phrase line\n"); return 3; }
            const Assignment a = clusters.assign(embedding.data(), samples);
            std::printf("%d %s %u %d %.6f %d %.6f %d %d\n", int(a.speaker), assignmentReasonName(a.reason),
                        unsigned(a.matches), int(a.bestSpeaker), double(a.bestSimilarity), int(a.secondSpeaker),
                        double(a.secondSimilarity), a.created ? 1 : 0, a.centroidUpdated ? 1 : 0);
        } else if (command == "clear") {
            in >> storedDim;
            stored.clear(); storedSamples.clear();
            if (!in || !storedDim) { std::fprintf(stderr, "bad clear line\n"); return 5; }
        } else if (command == "load" && storedDim) {
            size_t samples = 0;
            in >> samples;
            const size_t at = stored.size();
            stored.resize(at + storedDim);
            for (size_t i = 0; i < storedDim; ++i) in >> stored[at + i];
            if (!in) { std::fprintf(stderr, "bad load line\n"); return 6; }
            storedSamples.push_back(samples);
        } else if (command == "run") {
            if (!run(in, storedDim, stored, storedSamples)) { std::fprintf(stderr, "bad run line\n"); return 7; }
        } else {
            std::fprintf(stderr, "unexpected command\n");
            return 4;
        }
    }
    return 0;
}
