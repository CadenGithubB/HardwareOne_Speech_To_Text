// Positive/negative control for memory-copy access visibility, synthetic only.
#include <atomic>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <thread>
int16_t shared[1024]={};
volatile int16_t observed=0;
int main(int argc,char**) {
    const bool locked=argc>1;
    std::mutex mutex;
    std::atomic<bool> started{false},done{false};
    std::thread producer([&] {
        int16_t block[1024];
        for(unsigned i=0;i<1024;++i)block[i]=int16_t(i);
        started.store(true,std::memory_order_release);
        while(!done.load(std::memory_order_acquire)) {
            ++block[17];
            if(locked)mutex.lock();
            std::memcpy(shared,block,sizeof(block));
            if(locked)mutex.unlock();
        }
    });
    while(!started.load(std::memory_order_acquire))std::this_thread::yield();
    for(unsigned i=0;i<1000000;++i) {
        if(locked)mutex.lock();
        observed=static_cast<volatile int16_t*>(shared)[17];
        if(locked)mutex.unlock();
    }
    done.store(true,std::memory_order_release);
    producer.join();
}
