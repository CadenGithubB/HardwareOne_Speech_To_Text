// Unchanged production wipe and orphan/attached retirement helpers.
static void sttWipe(void* memory, size_t bytes) {
  if (!memory) return;
  volatile uint8_t* p = static_cast<volatile uint8_t*>(memory);
  while (bytes--) *p++ = 0;
}
static void sttFeatureRetireOrphans(StreamRun& run) {
  for (int i = 0; i < kFeCaches; ++i) {
    size_t used = 0;
    portENTER_CRITICAL(&gSTTMux);
    const bool orphan = run.fe[i].state == FeState::Orphan;
    if (orphan) used = run.fe[i].frames;
    portEXIT_CRITICAL(&gSTTMux);
    if (!orphan) continue;
    sttWipe(run.fe[i].rows, std::min(used + kFeBatchRows, kFeMaxRows) * kFeRowFloats * sizeof(float));
    portENTER_CRITICAL(&gSTTMux);
    run.fe[i].state = FeState::Free; ++run.fe[i].gen;
    portEXIT_CRITICAL(&gSTTMux);
  }
}
static void sttFeatureRelease(StreamRun& run, int idx, uint32_t gen) {
  if (idx < 0) return;
  size_t used = 0;
  portENTER_CRITICAL(&gSTTMux);
  const bool mine = run.fe[idx].gen == gen && run.fe[idx].state == FeState::Attached;
  if (mine) used = run.fe[idx].frames;
  portEXIT_CRITICAL(&gSTTMux);
  if (!mine) return;
  sttWipe(run.fe[idx].rows, std::min(used + kFeBatchRows, kFeMaxRows) * kFeRowFloats * sizeof(float));
  portENTER_CRITICAL(&gSTTMux);
  run.fe[idx].state = FeState::Free; ++run.fe[idx].gen;
  portEXIT_CRITICAL(&gSTTMux);
}
