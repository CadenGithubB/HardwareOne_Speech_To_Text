#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <set>
#include <string>
#include "System_DictationPolicy.h"
#define ENABLE_LOCAL_STT 1
#define ENABLE_ESP_SR 1
#define DICTATION_MAX_TEXT 256
using String=std::string;
using TransportSessionEpoch=uint32_t;
constexpr uint32_t kNoTransportSessionEpoch=0;
enum CommandSource { SOURCE_WEB,SOURCE_SERIAL,SOURCE_INTERNAL,SOURCE_ESPNOW,
 SOURCE_LOCAL_DISPLAY,SOURCE_BLUETOOTH,SOURCE_MQTT,SOURCE_VOICE,SOURCE_G2_GLASSES,SOURCE_UART };
// INSERT_HEADERS
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)x)
#define portEXIT_CRITICAL(x) ((void)x)
enum class DictationState:uint8_t {IDLE,RECORDING,WAITING,FAILED};
// INSERT_CONTROL
static uint32_t nowMs=1;
uint32_t millis(){return nowMs;}
uint32_t esp_random(){return 0x12345678;}
static uint32_t gDictBootNonce=0,gDictCounter=0;
static bool workerOK=true;
static int wakeCount=0;
static bool dictationEnsureWorker(){return workerOK;}
static void dictationWakeWorker(){++wakeCount;}
static std::set<std::pair<CommandSource,uint32_t>> sessions;
static bool displaySessionStillLive(CommandSource s,uint32_t epoch){return sessions.count({s,epoch});}
static bool micBusy=false,srBusy=false;
bool gMicRunning=false;
bool micRecordingBusy(){return micBusy;}
bool isESPSRRunning(){return srBusy;}
static std::string halOwner;
bool audioCaptureOwnedBy(const char* o){return halOwner==o;}
bool audioCaptureBusy(){return !halOwner.empty();}
static bool modelReady=true;
static int readyChecks=0;
bool sttLocalAvailable(char*,size_t){++readyChecks;return modelReady;}
static int beginCalls=0,cancelCalls=0,finishCalls=0;
static bool beginOK=true;
static STTOwner brokerOwner;
static STTSnapshot broker;
static std::string brokerText;
static std::function<void()> beginHook;
bool sttBegin(STTOwner owner,uint32_t ms,STTToken* token,char* error,size_t cap){
 ++beginCalls;assert(ms==20000);if(beginHook)beginHook();
 if(!beginOK){snprintf(error,cap,"run closemic first");return false;}
 brokerOwner=owner;broker=STTSnapshot{};broker.token=42;broker.state=STTState::Preparing;broker.workerActive=true;*token=42;return true;
}
bool sttRunActive(STTToken t){return broker.token==t&&broker.workerActive;}
bool same(STTOwner a,STTOwner b){return a.source==b.source&&a.epoch==b.epoch;}
bool sttCancel(STTOwner o,STTToken t){
 if(!same(o,brokerOwner)||t!=broker.token||!displaySessionStillLive(o.source,o.epoch))return false;
 ++cancelCalls;broker.textReady=false;brokerText.clear();return true;
}
bool sttRequestFinish(STTOwner o,STTToken t){
 if(!same(o,brokerOwner)||t!=broker.token)return false;++finishCalls;return true;
}
bool sttSnapshot(STTOwner o,STTToken t,STTSnapshot* out){
 if(!same(o,brokerOwner)||t!=broker.token||!displaySessionStillLive(o.source,o.epoch))return false;*out=broker;return true;
}
bool sttResult(STTOwner o,STTToken t,char* text,size_t cap){
 if(!same(o,brokerOwner)||t!=broker.token||!broker.textReady||!displaySessionStillLive(o.source,o.epoch))return false;
 snprintf(text,cap,"%s",brokerText.c_str());return true;
}
bool dictationAvailable(const char** why);
void requestStopRecordingOwned(uint64_t,bool){assert(false&&"local must not use WAV recorder");}
// INSERT_LOCAL
bool dictationAvailable(const char** why){return dictationLocalAvailable(why);}
// INSERT_DRAIN
// INSERT_STOP
static STTOwner glasses{SOURCE_G2_GLASSES,3};
static void reset(){
 gDict=DictationControl{};gDict.state=DictationState::IDLE;
 gLocalDict=LocalDictation{};gLocalReadyKnown=gLocalReady=gLocalReadyPending=false;
 gLocalReadyCheckedMs=0;nowMs=1;wakeCount=readyChecks=beginCalls=cancelCalls=finishCalls=0;
 sessions={{SOURCE_G2_GLASSES,3},{SOURCE_LOCAL_DISPLAY,4}};
 workerOK=modelReady=beginOK=true;micBusy=srBusy=gMicRunning=false;halOwner.clear();
 beginHook=nullptr;broker=STTSnapshot{};brokerText.clear();
}
static void ready(){const char* why=nullptr;assert(!dictationAvailable(&why));assert(readyChecks==0);dictationProcessLocal();assert(dictationAvailable(&why));assert(readyChecks==1);}
static void begin(){assert(dictationBeginLocal(glasses.source,glasses.epoch));assert(beginCalls==0);dictationProcessLocal();assert(beginCalls==1&&gLocalDict.token==42);}
static void done(const std::string& text){brokerText=text;broker.state=STTState::Done;broker.workerActive=false;broker.textReady=true;}
int main(){
 reset();ready();for(int i=0;i<100;++i)assert(dictationAvailable(nullptr));assert(readyChecks==1);
 srBusy=true;const char* why=nullptr;assert(!dictationAvailable(&why)&&std::string(why)=="run closesr first");srBusy=false;
 gMicRunning=true;assert(!dictationAvailable(&why)&&std::string(why)=="run closemic first");gMicRunning=false;
 begin();assert(gDict.requestHostEpoch==0&&!gDict.requestWasPushed&&!gDict.cleanupOwner);
 broker.state=STTState::Transcribing;dictationProcessLocal();assert(gDict.state==DictationState::WAITING);
 done(std::string(300,'a'));dictationProcessLocal();
 assert(gDict.textPending&&strlen(gDict.text)==256&&!gLocalDict.exchange&&cancelCalls==1);
 char text[257];assert(!dictationTakeTextFor(SOURCE_LOCAL_DISPLAY,text,sizeof(text)));
 assert(dictationTakeTextFor(SOURCE_G2_GLASSES,text,sizeof(text))&&strlen(text)==256);
 assert(!dictationTakeTextFor(SOURCE_G2_GLASSES,text,sizeof(text)));

 reset();ready();assert(dictationBeginLocal(glasses.source,glasses.epoch));
 dictationCancelLocal(glasses.source,false);assert(!dictationBeginLocal(glasses.source,glasses.epoch));
 dictationProcessLocal();assert(beginCalls==0&&!gLocalDict.exchange&&gDict.state==DictationState::IDLE);

 reset();ready();beginHook=[] {dictationCancelLocal(SOURCE_G2_GLASSES,false);};begin();
 assert(cancelCalls==1&&gLocalDict.exchange&&broker.workerActive);
 assert(!dictationBeginLocal(glasses.source,glasses.epoch));
 done("should not deliver");dictationProcessLocal();assert(!gDict.textPending&&!gLocalDict.exchange);

 reset();ready();begin();dictationCancelLocal(SOURCE_LOCAL_DISPLAY,false);assert(!gLocalDict.cancelled);
 dictationRequestStopFor(SOURCE_LOCAL_DISPLAY);dictationProcessLocal();assert(finishCalls==0);
 dictationRequestStopFor(SOURCE_G2_GLASSES);dictationProcessLocal();assert(finishCalls==1);
 dictationCancelLocal(SOURCE_G2_GLASSES,false);dictationProcessLocal();assert(cancelCalls==1&&gLocalDict.exchange);
 broker.workerActive=false;broker.state=STTState::Cancelled;dictationProcessLocal();assert(!gLocalDict.exchange&&!gDict.textPending);

 reset();ready();begin();sessions.erase({SOURCE_G2_GLASSES,3});dictationProcessLocal();
 assert(gLocalDict.exchange); // Revoked snapshot cannot be used as a join ACK.
 done("old session");dictationProcessLocal();assert(!gLocalDict.exchange&&!gDict.textPending);

 reset();ready();begin();done("delivered before revocation");dictationProcessLocal();
 sessions.erase({SOURCE_G2_GLASSES,3});assert(!dictationTakeTextFor(SOURCE_G2_GLASSES,text,sizeof(text))&&!text[0]&&!gDict.textPending);

 reset();ready();beginOK=false;assert(dictationBeginLocal(glasses.source,glasses.epoch));dictationProcessLocal();
 assert(gDict.state==DictationState::FAILED&&strstr(gDict.failure,"closemic")&&!gLocalDict.exchange);
 reset();ready();begin();done("\n control");dictationProcessLocal();assert(!gDict.textPending&&gDict.state==DictationState::FAILED);
 reset();ready();begin();done("");dictationProcessLocal();assert(!gDict.textPending&&gDict.state==DictationState::FAILED);
 reset();modelReady=false;assert(!dictationAvailable(&why));dictationProcessLocal();assert(!dictationAvailable(&why));assert(!dictationBeginLocal(glasses.source,glasses.epoch)&&beginCalls==0);
 puts("Local Dictation: readiness cache, provider isolation, cancellation debt, once-only text and session fences passed");
}
