// Replays phrase embeddings through the production speaker clusterer
// (firmware/components/hw1_stt/stt/speaker_cluster.h) for spkreplay.py.
//
// stdin, one command per line:
//   config DIM THRESHOLD MIN_NEW_SAMPLES MAX_SPEAKERS   (starts a session)
//   phrase SAMPLES V1 ... VDIM                         (one assignment)
//   reset                                              (new session, same config; echoed)
// stdout, one line per phrase:
//   SPEAKER REASON MATCHES BEST BEST_SIM SECOND SECOND_SIM CREATED UPDATED
#include "speaker_cluster.h"
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

int main() {
    using namespace hw1::stt::speaker;
    std::string line, command;
    size_t dim = 0;
    ClusterConfig config;
    std::vector<float> storage, embedding;
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
        } else {
            std::fprintf(stderr, "unexpected command\n");
            return 4;
        }
    }
    return 0;
}
