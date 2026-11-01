// HardwareOne aa6508fd/c6252b6e worker; only the DSP call is intercepted for scheduling.
static void sttFeatureWorker(void* context) {
  auto& run = *static_cast<StreamRun*>(context);
  bool stop = false;
  while (!stop) {
    (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(20));
    for (;;) {
      int idx = -1;
      uint32_t gen = 0;
      uint64_t start = 0, head = 0;
      size_t done = 0, len = 0;
      portENTER_CRITICAL(&gSTTMux);
      stop = run.feStop;
      if (run.feLive >= 0 && run.fe[run.feLive].state == FeState::Live && !run.fe[run.feLive].overrun) {
        idx = run.feLive;
        gen = run.fe[idx].gen; start = run.fe[idx].start; done = run.fe[idx].frames;
        len = run.feLiveLen;
      }
      head = run.feRingHead;
      portEXIT_CRITICAL(&gSTTMux);
      if (stop || idx < 0) break;
      const size_t stable = len >= 320 ? std::min(len / 160, kFeMaxRows) : 0;
      if (done >= stable) break;
      const size_t end = std::min(stable, done + kFeBatchRows);
      // Oldest sample this batch reads (row r: [r*160-161, r*160+160)).
      const uint64_t lo = start + (done * 160 > 161 ? done * 160 - 161 : 0);
      const bool safe = lo + kFeRingSamples >= head + kStreamReadSamples;
      if (safe)
        for (size_t r = done; r < end; ++r)
          (void)observed_log_mel_frame_ring(run.feRing, kFeRingSamples - 1, start, len, r,
                                             run.fe[idx].rows + r * kFeRowFloats, run.feWork);
      portENTER_CRITICAL(&gSTTMux);
      FeCache& c = run.fe[idx];
      if (c.gen == gen && c.state == FeState::Live) {
        // The capture task writes at most one block past the published head.
        if (safe && lo + kFeRingSamples >= run.feRingHead + kStreamReadSamples) {
          c.frames = end;
          run.feRowsComputed += static_cast<uint32_t>(end - done);
        } else {
          c.overrun = true;
          ++run.feOverruns;
        }
      }
      portEXIT_CRITICAL(&gSTTMux);
    }
  }
  portENTER_CRITICAL(&gSTTMux);
  run.feRunning = false;
  portEXIT_CRITICAL(&gSTTMux);
  vTaskDelete(nullptr);
}
