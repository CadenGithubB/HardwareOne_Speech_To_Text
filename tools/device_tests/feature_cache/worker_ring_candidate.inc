// HardwareOne b7598680 worker; DSP entry gated only by host adapter; see LICENSE.hardwareone.md.
static void sttFeatureWorker(void* context) {
  auto& run = *static_cast<StreamRun*>(context);
  bool stop = false;
  // DSP reads at most 321 PCM samples per stable row. This private ring
  // preserves its absolute indexing without changing frontend arithmetic.
  int16_t window[kFeWindowSamples];
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
      // Incremental DSP never uses conditioned internally. Stage this whole
      // batch in its existing worker-owned scratch, so retirement cannot wipe
      // memory while the DSP writes it. No additional stack/heap row buffer.
      static_assert(sizeof(hw1::stt::FrontendWorkspace::conditioned) >=
                    kFeBatchRows * kFeRowFloats * sizeof(float));
      float* const pending = run.feWork->conditioned;
      bool computed = safe;
      if (safe) {
        for (size_t r = done; r < end; ++r) {
          if (!sttFeatureSnapshot(run, idx, gen, start, r, window) ||
              observed_log_mel_frame_ring(window, kFeWindowSamples - 1, start, len, r,
                                         pending + (r - done) * kFeRowFloats, run.feWork) != hw1::stt::Status::Ok) {
            computed = false;
            break;
          }
        }
      }
      portENTER_CRITICAL(&gSTTMux);
      FeCache& c = run.fe[idx];
      if (c.gen == gen && c.state == FeState::Live) {
        // Keep the existing conservative overwrite guard for batch admission.
        if (computed && lo + kFeRingSamples >= run.feRingHead + kStreamReadSamples) {
          // Publish bytes and committed length together, only for this still
          // live generation. Orphan/attached retirement can never race a write.
          memcpy(c.rows + done * kFeRowFloats, pending, (end - done) * kFeRowFloats * sizeof(float));
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
