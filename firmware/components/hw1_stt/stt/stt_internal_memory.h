#pragma once
#include <cstddef>
#include <cstdint>

namespace hw1::stt {
// One task's allocations during a single transcribe call, not a system-heap
// subtraction. Incomplete/failed observations never relax admission.
struct InternalMemorySample {
    size_t peak = 0, largest = 0;
    bool complete = false;
};
struct InternalMemoryBudget { size_t total, contiguous; };
InternalMemoryBudget internalMemoryBudget(bool resident);
class InternalMemoryScope {
 public:
    InternalMemoryScope();
    ~InternalMemoryScope();
    void success(bool resident);
    InternalMemoryScope(const InternalMemoryScope&) = delete;
    InternalMemoryScope& operator=(const InternalMemoryScope&) = delete;
 private:
    bool active_ = false;
};
}
