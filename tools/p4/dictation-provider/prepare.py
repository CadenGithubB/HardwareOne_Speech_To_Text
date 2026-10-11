#!/usr/bin/env python3
"""Stage a reviewable patch; never modify production or access hardware."""
from pathlib import Path
import difflib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # experiments/stt_p4/dictation-provider -> repository root
BASE = ROOT / 'components/hardwareone'
OUT = HERE / 'components/hardwareone'
OUT.mkdir(parents=True, exist_ok=True)

changes = {}
s = (BASE / 'System_Dictation.cpp').read_text()
s = s.replace('#include "System_Microphone.h"', '#include "System_Microphone.h"\n#include "System_ESPSR.h"\n#include "System_STT.h"')
s = s.replace('static constexpr uint32_t kDictationWorkerStackBytes = 3072;', 'static constexpr uint32_t kDictationWorkerStackBytes = ENABLE_LOCAL_STT ? 4096 : 3072;')
marker='static bool dictationWorkerHasWork() {'
s=s.replace(marker,(HERE/'local_provider.inc').read_text()+'\n'+marker,1)
s=s.replace('  work = gDict.published.pending || gDict.cancelEvent.pending ||', '  work =\n#if ENABLE_LOCAL_STT\n         gLocalReadyPending || gLocalDict.exchange != 0 ||\n#endif\n         gDict.published.pending || gDict.cancelEvent.pending ||',1)
s=s.replace('      (void)dictationProcessPublished();','''#if ENABLE_LOCAL_STT
      dictationProcessLocal();
#endif
      (void)dictationProcessPublished();''',1)
marker='  if (!uartLinkIsRunning()) {\n    if (whyNot) *whyNot = "no host link";'
s=s.replace(marker,'''#if ENABLE_LOCAL_STT
  // An enabled local provider never silently exports microphone audio to a
  // host, even if its model is missing or its inference fails.
  return dictationLocalAvailable(whyNot);
#endif
'''+marker,1)
marker='  if (!dictationEnsureWorker()) return false;\n\n  const char* why = nullptr;'
s=s.replace(marker,'''#if ENABLE_LOCAL_STT
  return dictationBeginLocal(displaySource, displayEpoch);
#endif

'''+marker,1)
marker='void dictationRequestStopFor(CommandSource displaySource) {\n'
s=s.replace(marker,marker+'''#if ENABLE_LOCAL_STT
  portENTER_CRITICAL(&gDictMux);
  if (gLocalDict.exchange && gLocalDict.actor.source == displaySource &&
      gDict.owner == gLocalDict.exchange) gLocalDict.stopRequested = true;
  portEXIT_CRITICAL(&gDictMux);
  dictationWakeWorker();
  return;
#endif
''',1)
marker='static void dictationCancelImpl(CommandSource displaySource, bool force) {\n'
s=s.replace(marker,marker+'''#if ENABLE_LOCAL_STT
  dictationCancelLocal(displaySource, force);
  return;
#endif
''',1)
marker='  out.level = (out.state == DictationState::RECORDING) ? getAudioLevel() : 0;\n'
s=s.replace(marker,marker+'''#if ENABLE_LOCAL_STT
  out.bufferedLocal = true;
  LocalDictation local;
  portENTER_CRITICAL(&gDictMux);
  local = gLocalDict;
  portEXIT_CRITICAL(&gDictMux);
  STTSnapshot snap;
  if (local.token && sttSnapshot(local.actor, local.token, &snap)) {
    out.sourceName = sourceLabel(static_cast<AudioSource>(snap.audioSource));
    out.level = snap.level;
    out.preparing = snap.state == STTState::Preparing;
  } else {
    out.level = 0;
    out.preparing = local.beginPending || local.beginInFlight;
  }
#endif
''',1)
marker='void dictationTick() {\n'
s=s.replace(marker,marker+'''#if ENABLE_LOCAL_STT
  // The local worker and broker supervise the capture/engine. Host heartbeat,
  // WAV publication and UART response deadlines do not apply to this provider.
  if (dictationWorkerHasWork()) dictationWakeWorker();
  return;
#endif
''',1)
start=s.index('bool dictationTakeTextFor(');end=s.index('\nbool dictationTakeText(',start)
s=s[:start]+'''bool dictationTakeTextFor(CommandSource displaySource,
                          char* out, size_t outSize) {
  if (!out || outSize == 0) return false;
  out[0] = '\\0';
  TransportSessionEpoch epoch = 0;
  portENTER_CRITICAL(&gDictMux);
  if (gDict.displaySource == displaySource && gDict.textPending)
    epoch = gDict.displayEpoch;
  portEXIT_CRITICAL(&gDictMux);
  if (!epoch) return false;
  if (!displaySessionStillLive(displaySource, epoch)) {
    // This fence applies to BOTH providers: a pending transcript cannot survive
    // logout/re-pair and become the replacement user's next field input.
    portENTER_CRITICAL(&gDictMux);
    if (gDict.displaySource == displaySource && gDict.displayEpoch == epoch) {
      memset(gDict.text, 0, sizeof(gDict.text));
      gDict.textPending = false;
      gDict.state = DictationState::IDLE;
      gDict.micStopPending = gDict.weStartedMic;
    }
    portEXIT_CRITICAL(&gDictMux);
    dictationWakeWorker();
    return false;
  }
  bool took = false;
  portENTER_CRITICAL(&gDictMux);
  if (gDict.displaySource == displaySource && gDict.displayEpoch == epoch &&
      gDict.textPending) {
    snprintf(out, outSize, "%s", gDict.text);
    gDict.textPending = false;
    memset(gDict.text, 0, sizeof(gDict.text));
    gDict.state = DictationState::IDLE;
    gDict.stateEnteredMs = millis();
    gDict.micStopPending = gDict.weStartedMic;
    gDict.displaySource = SOURCE_INTERNAL;
    gDict.displayEpoch = kNoTransportSessionEpoch;
    gDict.requestHostEpoch = 0;
    gDict.requestPushInFlight = false;
    gDict.requestWasPushed = false;
    took = true;
  }
  portEXIT_CRITICAL(&gDictMux);
  if (took) dictationWakeWorker();
  if (!displaySessionStillLive(displaySource, epoch)) {
    memset(out, 0, outSize);
    return false;
  }
  return took;
}
''' + s[end:]
s=s.replace('if (gDict.state == DictationState::WAITING && gDict.owner == id) {','if (gDict.state == DictationState::WAITING && gDict.owner == id &&\n      gDict.requestHostEpoch != 0) {',1)
s=s.replace('matched = (gDict.state == DictationState::WAITING && gDict.owner == id);','matched = (gDict.state == DictationState::WAITING && gDict.owner == id &&\n               gDict.requestHostEpoch != 0);',1)
changes['System_Dictation.cpp']=s

s=(BASE/'System_Dictation.h').read_text()
header_start=s.index('// This is the firmware half')
header_end=s.index('//   1. wearer',header_start)
s=s[:header_start]+"""// An OLED/G2 keyboard input method with one provider latched per exchange.
// ENABLE_LOCAL_STT builds use the shared local broker with bounded raw-HAL
// capture and final text. Other builds retain the CM5 adapter and owned VAD
// WAV capture. Both accept PDM or G2 audio through the same HAL. Local failure
// never falls back to exporting audio to a host.
//
// ESP-SR provides fixed commands, not arbitrary dictation. The legacy CM5
// provider performs free-text transcription on Linux with this round trip:
//
"""+s[header_end:]
s=s.replace('  char failure[40];\n};','  char failure[40];\n  bool bufferedLocal = false; // Local capture has a duration cap, not host VAD.\n  bool preparing = false;    // Do not prompt SPEAK NOW before HAL capture.\n};',1)
s=s.replace('WAITING,      // WAV closed, request pushed, host is transcribing','WAITING,      // provider is transcribing; final text awaits a one-time drain')
changes['System_Dictation.h']=s

s=(BASE/'System_STT.h').read_text()
s=s.replace('bool sttRequestFinish(', '// Internal join predicate: contains no transcript/session data and remains\n// usable after revocation. Unknown or terminal tokens are inactive.\nbool sttRunActive(STTToken token);\nbool sttRequestFinish(',1)
changes['System_STT.h']=s
s=(BASE/'System_STT.cpp').read_text()
s=s.replace('bool sttRequestFinish(','''bool sttRunActive(STTToken token) {
  portENTER_CRITICAL(&gSTTMux);
  const bool active = token && gSTT.snapshot.token == token && gSTT.snapshot.workerActive;
  portEXIT_CRITICAL(&gSTTMux);
  return active;
}

bool sttRequestFinish(''',1)
changes['System_STT.cpp']=s

s=(BASE/'G2_Glasses.cpp').read_text()
s=s.replace('''        line1 = "SPEAK NOW";
        line2 = "STOP SPEAKING TO END TRANSMISSION";
        footer = "AUTO-STOPS AFTER SILENCE";''','''        line1 = snap.preparing ? "GET READY" : "SPEAK NOW";
        line2 = snap.preparing ? "STARTING MICROPHONE"
                : snap.bufferedLocal ? "TAP MIC TO FINISH"
                                     : "STOP SPEAKING TO END TRANSMISSION";
        footer = snap.bufferedLocal ? "LOCAL RECORDING / 20 SEC MAX"
                                   : "AUTO-STOPS AFTER SILENCE";''',1)
s=s.replace('        line1 = "TRANSCRIBING";','        line1 = snap.bufferedLocal ? "LOCAL STT" : "TRANSCRIBING";',1)
changes['G2_Glasses.cpp']=s
s=(BASE/'OLED_Utils.cpp').read_text()
s=s.replace('      case DictationState::RECORDING: {\n        // Filled dot', '      case DictationState::RECORDING: {\n        if (snap.preparing) {\n          display->setCursor(0, micY);\n          display->print("Starting mic...");\n          break;\n        }\n        // Filled dot',1)
s=s.replace('        display->print("Transcribing");','        display->print(snap.bufferedLocal ? "Local STT" : "Transcribing");',1)
changes['OLED_Utils.cpp']=s

s=(BASE/'System_BuildConfig.h').read_text()
start=s.index('// The CM5 host link that actually performs the transcription')
end=s.index('// Dictation needs a mic and a KEYBOARD',start)
s=s[:start]+'''// ENABLE_LOCAL_STT selects local buffered transcription without a UART host.
// Otherwise the authenticated CM5 adapter remains the runtime requirement.
// Provider choice is latched per exchange; local failures never silently send
// audio to a remote host. The capture source stays shared (PDM or G2).
'''+s[end:]
changes['System_BuildConfig.h']=s

patch=[]
for name,text in changes.items():
    original=(BASE/name).read_text()
    (OUT/name).write_text(text)
    patch.extend(difflib.unified_diff(original.splitlines(True),text.splitlines(True),
        fromfile='a/components/hardwareone/'+name,tofile='b/components/hardwareone/'+name))
(HERE/'local-dictation.patch').write_text(''.join(patch))
print('Staged',len(changes),'files; production unchanged')
