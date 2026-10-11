#if ENABLE_LOCAL_STT
// A local exchange never enters the UART/WAV path. This slot survives UI
// cancellation until a late begin/worker has acknowledged the exact token.
struct LocalDictation {
  uint64_t exchange = 0;
  STTOwner actor;
  STTToken token = 0;
  bool beginPending = false;
  bool beginInFlight = false;
  bool stopRequested = false;
  bool cancelled = false;
};
static LocalDictation gLocalDict;
static bool gLocalReadyPending = false;
static bool gLocalReadyKnown = false;
static bool gLocalReady = false;
static uint32_t gLocalReadyCheckedMs = 0;
static bool dictationEnsureWorker();

static void dictationRefreshLocalReady() {
  bool due;
  portENTER_CRITICAL(&gDictMux);
  due = gLocalReadyPending;
  gLocalReadyPending = false;
  portEXIT_CRITICAL(&gDictMux);
  if (!due) return;
  char error[96] = {};
  const bool ready = sttLocalAvailable(error, sizeof(error));
  portENTER_CRITICAL(&gDictMux);
  gLocalReady = ready;
  gLocalReadyKnown = true;
  gLocalReadyCheckedMs = millis();
  portEXIT_CRITICAL(&gDictMux);
}

static bool dictationLocalAvailable(const char** whyNot) {
  if (!dictationEnsureWorker()) {
    if (whyNot) *whyNot = "local worker unavailable";
    return false;
  }
  bool known, ready;
  portENTER_CRITICAL(&gDictMux);
  known = gLocalReadyKnown;
  ready = gLocalReady;
  if (!known || millis() - gLocalReadyCheckedMs >= 5000) gLocalReadyPending = true;
  portEXIT_CRITICAL(&gDictMux);
  dictationWakeWorker();
  const char* why = nullptr;
#if ENABLE_ESP_SR
  if (isESPSRRunning() || audioCaptureOwnedBy("sr")) why = "run closesr first";
#endif
  if (!why && (gMicRunning || micRecordingBusy() || audioCaptureOwnedBy("mic")))
    why = "run closemic first";
  if (!why && audioCaptureBusy() && !audioCaptureOwnedBy("stt")) why = "microphone busy";
  if (!why && !known) why = "checking local model";
  if (!why && !ready) why = "local model unavailable";
  if (whyNot) *whyNot = why;
  return why == nullptr;
}

static bool dictationBeginLocal(CommandSource source, TransportSessionEpoch epoch) {
  const char* why = nullptr;
  if (!dictationAvailable(&why)) return false;
  const uint32_t nonce = esp_random();
  bool admitted = false;
  portENTER_CRITICAL(&gDictMux);
  if (!gLocalDict.exchange &&
      (gDict.state == DictationState::IDLE || gDict.state == DictationState::FAILED) &&
      !gDict.cleanupOwner && !gDict.micStopPending && !gDict.published.pending &&
      !gDict.cancelEvent.pending) {
    if (!gDictBootNonce) gDictBootNonce = nonce ? nonce : 1;
    if (++gDictCounter == 0) ++gDictCounter;
    const uint64_t id = (static_cast<uint64_t>(gDictBootNonce) << 32) | gDictCounter;
    gLocalDict = LocalDictation{};
    gLocalDict.exchange = id;
    gLocalDict.actor = STTOwner{source, epoch};
    gLocalDict.beginPending = true;
    gDict.owner = id;
    gDict.displaySource = source;
    gDict.displayEpoch = epoch;
    gDict.state = DictationState::RECORDING;
    gDict.stateEnteredMs = millis();
    gDict.textPending = false;
    memset(gDict.text, 0, sizeof(gDict.text));
    gDict.failure[0] = '\0';
    gDict.weStartedMic = false;
    gDict.requestHostEpoch = 0;
    gDict.requestPushInFlight = gDict.requestWasPushed = false;
    admitted = true;
  }
  portEXIT_CRITICAL(&gDictMux);
  if (admitted) dictationWakeWorker();
  return admitted;
}

static void dictationCancelLocal(CommandSource source, bool force) {
  portENTER_CRITICAL(&gDictMux);
  if (force || gDict.displaySource == source) {
    if (gLocalDict.exchange) gLocalDict.cancelled = true;
    gDict.owner = 0;
    gDict.state = DictationState::IDLE;
    gDict.stateEnteredMs = millis();
    gDict.displaySource = SOURCE_INTERNAL;
    gDict.displayEpoch = 0;
    gDict.textPending = false;
    memset(gDict.text, 0, sizeof(gDict.text));
    gDict.failure[0] = '\0';
  }
  portEXIT_CRITICAL(&gDictMux);
  dictationWakeWorker();
}

static void dictationProcessLocal() {
  dictationRefreshLocalReady();
  LocalDictation run;
  portENTER_CRITICAL(&gDictMux);
  run = gLocalDict;
  if (run.beginPending) {
    gLocalDict.beginPending = false;
    gLocalDict.beginInFlight = true;
  }
  portEXIT_CRITICAL(&gDictMux);
  if (!run.exchange) return;

  if (run.beginPending) {
    STTToken token = 0;
    char error[96] = {};
    const bool accepted = !run.cancelled &&
        displaySessionStillLive(run.actor.source, run.actor.epoch) &&
        sttBegin(run.actor, STT_MAX_CAPTURE_MS, &token, error, sizeof(error));
    portENTER_CRITICAL(&gDictMux);
    if (gLocalDict.exchange == run.exchange) {
      gLocalDict.beginInFlight = false;
      if (accepted) gLocalDict.token = token;
      if (!accepted) {
        if (gDict.owner == run.exchange) {
          gDict.owner = 0;
          gDict.state = DictationState::FAILED;
          gDict.stateEnteredMs = millis();
          snprintf(gDict.failure, sizeof(gDict.failure), "%s",
                   error[0] ? error : "session changed");
        }
        gLocalDict = LocalDictation{};
      }
      run = gLocalDict;
    }
    portEXIT_CRITICAL(&gDictMux);
    if (!accepted) return;
  }
  if (!run.token) return;

  // This check uses the original actor even when cancellation has cleared the
  // UI owner. An expired session self-cancels inside STT; metadata-only join
  // checking below remains possible without resurrecting its authority.
  const bool live = displaySessionStillLive(run.actor.source, run.actor.epoch);
  if (run.cancelled || !live) (void)sttCancel(run.actor, run.token);
  else if (run.stopRequested) (void)sttRequestFinish(run.actor, run.token);
  const bool active = sttRunActive(run.token);
  STTSnapshot snap;
  const bool hasSnapshot = live && sttSnapshot(run.actor, run.token, &snap);
  if (active) {
    portENTER_CRITICAL(&gDictMux);
    if (gDict.owner == run.exchange && !gLocalDict.cancelled && hasSnapshot) {
      const DictationState state = (snap.state == STTState::Preparing ||
                                   snap.state == STTState::Recording)
                                      ? DictationState::RECORDING : DictationState::WAITING;
      if (gDict.state != state) {
        gDict.state = state;
        gDict.stateEnteredMs = millis();
      }
    }
    portEXIT_CRITICAL(&gDictMux);
    return;
  }

  char text[STT_MAX_TEXT + 1] = {};
  const bool ready = !run.cancelled && hasSnapshot && snap.state == STTState::Done &&
      sttResult(run.actor, run.token, text, sizeof(text));
  const size_t len = strlen(text);
  const bool printable = ready && dictationPrintableAscii(text, len, false);
  const bool stillLive = displaySessionStillLive(run.actor.source, run.actor.epoch);
  portENTER_CRITICAL(&gDictMux);
  if (gLocalDict.exchange == run.exchange && gDict.owner == run.exchange &&
      !gLocalDict.cancelled && gDict.displaySource == run.actor.source &&
      gDict.displayEpoch == run.actor.epoch) {
    gDict.owner = 0;
    gDict.stateEnteredMs = millis();
    if (printable && stillLive) {
      // Keep the keyboard's established 256-byte contract. The broker's CLI
      // uses its separate 512-byte limit; field maxLength wins at append time.
      snprintf(gDict.text, sizeof(gDict.text), "%.*s", DICTATION_MAX_TEXT, text);
      gDict.textPending = true;
      gDict.state = DictationState::WAITING;
    } else {
      gDict.state = DictationState::FAILED;
      snprintf(gDict.failure, sizeof(gDict.failure), "%s",
               !stillLive ? "session changed"
               : (hasSnapshot && snap.error[0]) ? snap.error
               : ready ? "no printable speech recognized" : "local transcription failed");
    }
  }
  portEXIT_CRITICAL(&gDictMux);
  // Drop the broker's retained copy only after the terminal join and copy.
  (void)sttCancel(run.actor, run.token);
  memset(text, 0, sizeof(text));
  portENTER_CRITICAL(&gDictMux);
  if (gLocalDict.exchange == run.exchange) gLocalDict = LocalDictation{};
  portEXIT_CRITICAL(&gDictMux);
}
#endif // ENABLE_LOCAL_STT
