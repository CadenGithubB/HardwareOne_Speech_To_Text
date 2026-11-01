// HardwareOne b7598680 producer, locking its PCM copy; see LICENSE.hardwareone.md.
static void sttFeatureRingWrite(StreamRun& run, int16_t* ring, const int16_t* block, size_t count) {
  const uint64_t base = run.segmenter.samples_seen();
  const size_t at = static_cast<size_t>(base & (kFeRingSamples - 1));
  const size_t first = std::min(count, kFeRingSamples - at);
  // Serialize every PCM byte with the feature worker's stable-row snapshot.
  portENTER_CRITICAL(&gSTTMux);
  memcpy(ring + at, block, first * sizeof(int16_t));
  if (count > first) memcpy(ring, block + first, (count - first) * sizeof(int16_t));
  if (!run.feRingStarted) { run.feRingStarted = true; run.feRingStart = base; }
  run.feRingHead = base + count;
  portEXIT_CRITICAL(&gSTTMux);
}
