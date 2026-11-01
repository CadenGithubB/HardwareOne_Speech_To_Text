// HardwareOne b7598680 stable-row snapshot; see LICENSE.hardwareone.md.
constexpr size_t kFeWindowSamples = 512;
static bool sttFeatureSnapshot(StreamRun& run, int idx, uint32_t gen, uint64_t start,
                               size_t row, int16_t (&window)[kFeWindowSamples]) {
  static_assert(kFeWindowSamples >= 321 && (kFeWindowSamples & (kFeWindowSamples - 1)) == 0 &&
                kFeRingSamples % kFeWindowSamples == 0);
  const size_t rowLo = row * 160 > 161 ? row * 160 - 161 : 0;
  const size_t rowHi = row ? row * 160 + 160 : 161;
  const uint64_t source = start + rowLo;
  const size_t to = static_cast<size_t>(source & (kFeWindowSamples - 1));
  const size_t from = static_cast<size_t>(source & (kFeRingSamples - 1));
  const size_t count = rowHi - rowLo;
  const size_t first = std::min(count, kFeWindowSamples - to);
  bool copied = false;
  portENTER_CRITICAL(&gSTTMux);
  const FeCache& current = run.fe[idx];
  if (current.gen == gen && current.state == FeState::Live &&
      source + kFeRingSamples >= run.feRingHead + kStreamReadSamples) {
    // The producer copies and publishes its head under this same lock.
    // The two ring sizes are powers of two and the larger is a multiple
    // of the smaller, so a private-window span cannot cross the source
    // ring's end before it crosses the private window's end.
    memcpy(window + to, run.feRing + from, first * sizeof(int16_t));
    if (count > first)
      memcpy(window, run.feRing + ((from + first) & (kFeRingSamples - 1)),
             (count - first) * sizeof(int16_t));
    copied = true;
  }
  portEXIT_CRITICAL(&gSTTMux);
  return copied;
}
