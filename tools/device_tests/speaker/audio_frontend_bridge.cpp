// Host-only bridge to the actual portable frontend and opt-in window selector.
#include "speaker_frontend.h"
#include "speaker_window.h"
#include <vector>
using namespace hw1::stt::speaker;
extern "C" int speaker_features(const int16_t* pcm,size_t samples,float* output) {
    FeatureSpec spec;
    std::vector<float> workspace(workspace_floats(spec,samples));
    Frontend frontend;
    return frontend.init(spec,samples,workspace.data()) && frontend.compute(pcm,samples,output);
}
extern "C" int speaker_select(const int16_t* pcm,size_t samples,unsigned policy,
                              size_t* result,float* threshold) {
    std::vector<float> workspace(window_workspace_floats(samples));
    WindowSelection out;
    if(!select_window(pcm,samples,policy,workspace.data(),workspace.size(),out))return 0;
    result[0]=out.start;result[1]=out.samples;result[2]=out.frames;
    result[3]=out.active_frames;result[4]=out.selected_active_frames;
    *threshold=out.threshold_rms;
    return 1;
}

#include "speaker_level.h"
extern "C" float speaker_normalize(int16_t* pcm,size_t samples) {
    return normalize_level(pcm,samples);
}
