// Offline bounded-delay prototype driver; no firmware integration.
#include "provisional_clusters.h"
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
using hw1::stt::speaker::ProvisionalClusters;
int main() {
    std::string line,cmd;
    size_t dim=0;
    std::vector<std::vector<float>> embeddings;
    std::vector<size_t> samples;
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);in>>cmd;
        if(cmd=="clear") { in>>dim;embeddings.clear();samples.clear();if(!in || !dim || dim>4096)return 2; }
        else if(cmd=="load" && dim) {
            size_t n;in>>n;std::vector<float> e(dim);for(float& v:e)in>>v;
            if(!in)return 3;
            samples.push_back(n);embeddings.push_back(std::move(e));
        } else if(cmd=="run" && dim) {
            unsigned evidence;size_t window,n;in>>evidence>>window>>n;
            if(!in || (evidence!=2 && evidence!=3) || window<evidence || window>64)return 4;
            ProvisionalClusters clusters(dim,evidence,window);
            for(size_t k=0;k<n;++k) {
                size_t i;in>>i;if(!in || i>=samples.size())return 5;
                clusters.push(embeddings[i].data(),samples[i]);
            }
            clusters.flush();
            for(const auto& a:clusters.labels())std::cout<<a.speaker<<':'<<a.reason<<':'<<a.delay<<' ';
            std::cout<<'\n';
        } else return 6;
    }
}
