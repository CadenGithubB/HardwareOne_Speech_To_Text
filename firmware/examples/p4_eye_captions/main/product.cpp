#include "capture_diagnostics.h"
#include "product.h"
#include <cstdio>
#include <cstring>
#include <ctime>
#include <cerrno>
#include <cinttypes>
#include <cstdlib>
#include <cmath>
#include <sys/time.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include "cJSON.h"
#include "esp_timer.h"
#include "esp_attr.h"
#include "esp_system.h"
#include "esp_random.h"
#include "nvs.h"
#include "nvs_flash.h"
#if defined(ESP_PLATFORM)
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#endif

namespace product {
namespace {
#ifndef HW1_PRODUCT_SD_ROOT
#define HW1_PRODUCT_SD_ROOT "/sd"
#endif
constexpr const char* kWords = HW1_PRODUCT_SD_ROOT "/STT Models/user_vocab.tsv";
constexpr const char* kFolder = HW1_PRODUCT_SD_ROOT "/STT Notes";
EXT_RAM_BSS_ATTR hw1::transcript::Vocabulary vocabulary, staged;
EXT_RAM_BSS_ATTR hw1::stt::lm::CustomWords hotwords;
hw1::transcript::BootIdentity boot;
uint32_t resetReason = 0, nonce = 0, noteNumber = 0, phrase = 0;
uint64_t generation = 0;
uint64_t noteStarted = 0;
char noteId[96]{}, notePath[160]{}, title[160]{}, startedUtc[32]{};
bool clockKnown = false;
bool saving = false, paragraphStart = true;
const char* currentState = "preparing";
char currentDetail[128]{};
char command[256]{};
size_t commandBytes = 0;
bool commandOverflow = false;
float languageStrength = 1.0f;
uint32_t draftVersion = 0;
bool draftActive = false;
bool (*commandHook)(const char*) = nullptr;

uint64_t nowMs() { return uint64_t(esp_timer_get_time()) / 1000; }
void number(cJSON* obj, const char* name, uint64_t value) {
  // IDs/order counters are decimal strings: JSON numbers lose integer precision.
  char digits[32]; std::snprintf(digits, sizeof(digits), "%" PRIu64, value);
  cJSON_AddStringToObject(obj, name, digits);
}
cJSON* event(const char* kind) {
  cJSON* obj = cJSON_CreateObject();
  if (obj) { cJSON_AddNumberToObject(obj, "schema", 1); cJSON_AddStringToObject(obj, "type", kind); }
  return obj;
}
void emit(cJSON* obj) {
  if (!obj) return;
  char* line = cJSON_PrintUnformatted(obj);
  if (line) { std::printf("STT_EVENT %s\n", line); cJSON_free(line); }
  cJSON_Delete(obj);
}
void message(const char* text, bool ok = true) {
  cJSON* obj = event("message"); if (!obj) return;
  cJSON_AddBoolToObject(obj, "ok", ok); cJSON_AddStringToObject(obj, "text", text); emit(obj);
}
bool saveEvent(cJSON* obj, bool first = false) {
  if (!obj) return false;
  char* line = cJSON_PrintUnformatted(obj);
  struct stat existing{};
  const bool present = first || stat(notePath, &existing) == 0;
  FILE* file = line && present ? std::fopen(notePath, first ? "wx" : "a") : nullptr;
  // Never continue a recording whose existing file has disappeared.
  bool ok = file && std::fputs(line, file) >= 0 && std::fputc('\n', file) != EOF;
  if (file) { if (std::fflush(file) || fsync(fileno(file))) ok = false; if (std::fclose(file)) ok = false; }
  cJSON_free(line);
  if (!ok) { saving = false; message("Recording save failed; captions continue", false); }
  return ok;
}
void identity(cJSON* obj) {
  cJSON_AddStringToObject(obj, "sessionId", noteId[0] ? noteId : "startup");
  cJSON_AddBoolToObject(obj, "bootDurable", boot.durable);
  number(obj, "bootNumber", boot.boot); number(obj, "powerCycleNumber", boot.powerOn);
  number(obj, "sessionNumber", noteNumber); cJSON_AddNumberToObject(obj, "resetReason", resetReason);
  char token[32]; std::snprintf(token, sizeof(token), "%08" PRIx32, nonce);
  cJSON_AddStringToObject(obj, "bootNonce", token);
  std::snprintf(token, sizeof(token), "%016" PRIx64, generation);
  cJSON_AddStringToObject(obj, "orderingDomain", token);
}
void counters() {
  resetReason = uint32_t(esp_reset_reason()); nonce = esp_random();
  // Do not use the common erase-and-reinitialize sample pattern: this partition
  // may also contain the firmware owner's settings.
  if (nvs_flash_init() != ESP_OK) { message("NVS unavailable; persistent boot ordering unavailable", false); return; }
  nvs_handle_t handle;
  if (nvs_open("hw1_stt_demo", NVS_READWRITE, &handle) != ESP_OK) return;
  struct Persisted { uint64_t magic, boot, power, generation; } data{};
  size_t length = sizeof(data);
  const esp_err_t result = nvs_get_blob(handle, "startup", &data, &length);
  hw1::transcript::BootIdentity previous;
  if (result == ESP_OK && length == sizeof(data) && data.magic == 0x535454424f4f5431ULL) {
    previous.boot = data.boot; previous.powerOn = data.power; generation = data.generation;
  } else if (result != ESP_ERR_NVS_NOT_FOUND) {
    nvs_close(handle); message("Invalid startup record; ordering unavailable (storage preserved)", false); return;
  }
  if (hw1::transcript::nextBoot(previous, resetReason == ESP_RST_POWERON, boot)) {
    if (!generation) generation = (uint64_t(esp_random()) << 32) | esp_random();
    data = {0x535454424f4f5431ULL, boot.boot, boot.powerOn, generation};
    boot.durable = nvs_set_blob(handle, "startup", &data, sizeof(data)) == ESP_OK && nvs_commit(handle) == ESP_OK;
  }
  nvs_close(handle);
  if (!boot.durable) { boot = {}; message("Boot counter commit failed; persistent ordering unavailable", false); }
}
void buildHotwords() {
  static char text[hw1::transcript::kMaxWords * (hw1::transcript::kSpokenBytes + 1) + 1];
  size_t used = 0;
  for (size_t i = 0; i < vocabulary.count(); ++i) {
    const char* spoken = vocabulary.at(i).spoken; const size_t n = std::strlen(spoken);
    std::memcpy(text + used, spoken, n); used += n; text[used++] = '\n';
  }
  text[used] = 0; hotwords.parse(text, used);
}
bool loadVocabulary() {
  char backup[160]; std::snprintf(backup, sizeof(backup), "%s.bak", kWords);
  // Recover an interrupted rename without overwriting a surviving main file.
  struct stat st{};
  if (stat(kWords, &st) && !stat(backup, &st)) rename(backup, kWords);
  FILE* file = std::fopen(kWords, "r");
  if (!file) { if (errno == ENOENT) { vocabulary.clear(); buildHotwords(); return true; } return false; }
  staged.clear(); char line[160], error[128]; bool ok = true;
  size_t rows = 0;
  while (std::fgets(line, sizeof(line), file)) {
    if (++rows > 256 || (!std::strchr(line, '\n') && !std::feof(file))) { ok = false; break; }
    line[std::strcspn(line, "\r\n")] = 0;
    if (!line[0]) continue;
    char* spoken = std::strchr(line, '\t'); if (spoken) *spoken++ = 0;
    if (!staged.put(line, spoken, error, sizeof(error))) { ok = false; break; }
  }
  if (std::ferror(file)) ok = false;
  std::fclose(file);
  if (ok) { vocabulary = staged; buildHotwords(); }
  return ok;
}
bool commitVocabulary() {
  char temp[160], backup[160]; std::snprintf(temp, sizeof(temp), "%s.tmp", kWords);
  std::snprintf(backup, sizeof(backup), "%s.bak", kWords);
  FILE* file = std::fopen(temp, "w"); bool ok = file;
  for (size_t i = 0; ok && i < staged.count(); ++i) {
    const auto& w = staged.at(i); ok = std::fprintf(file, "%s\t%s\n", w.display, w.spoken) > 0;
  }
  if (file) { if (std::fflush(file) || fsync(fileno(file))) ok = false; if (std::fclose(file)) ok = false; }
  if (!ok) return false;
  struct stat st{}; const bool exists = stat(kWords, &st) == 0;
  if (exists) { unlink(backup); if (rename(kWords, backup)) return false; }
  if (rename(temp, kWords)) { if (exists) rename(backup, kWords); return false; }
  // Keep the previous version as recovery evidence until the next edit.
  vocabulary = staged; buildHotwords(); return true;
}
void finish() {
  if (!saving) return;
  cJSON* obj = event("end"); if (!obj) return;
  identity(obj); number(obj, "durationMs", nowMs() - noteStarted);
  cJSON_AddNumberToObject(obj, "phrases", phrase); cJSON_AddStringToObject(obj, "outcome", "done");
  const bool ok = saveEvent(obj);
  if (ok) { cJSON_AddBoolToObject(obj, "saved", true); emit(obj); } else cJSON_Delete(obj);
  saving = false;
}
void start(bool save = true) {
  finish();
  if (noteNumber == UINT32_MAX) { message("Per-boot session number exhausted", false); return; }
  ++noteNumber; draftActive = false; phrase = 0; title[0] = 0; paragraphStart = true; noteStarted = nowMs();
  std::snprintf(noteId, sizeof(noteId), "b%020" PRIu64 "-%08" PRIx32 "-n%010" PRIu32, boot.boot, nonce, noteNumber);
  std::snprintf(notePath, sizeof(notePath), "%s/%s.jsonl", kFolder, noteId);
  cJSON* obj = event("start"); if (!obj) return;
  identity(obj); number(obj, "startedUptimeMs", noteStarted);
  const time_t now = std::time(nullptr); clockKnown = now >= 1577836800LL && now < 4102444800LL;
  startedUtc[0] = 0;
  cJSON_AddBoolToObject(obj, "clockKnown", clockKnown);
  if (clockKnown) { struct tm utc{}; gmtime_r(&now, &utc); std::strftime(startedUtc, sizeof(startedUtc), "%Y-%m-%dT%H:%M:%SZ", &utc); cJSON_AddStringToObject(obj, "startedUtc", startedUtc); }
  else cJSON_AddNullToObject(obj, "startedUtc");
  cJSON_AddStringToObject(obj, "source", "local-pdm");
  struct stat st{}; const bool folder = !stat(kFolder, &st) ? S_ISDIR(st.st_mode) : mkdir(kFolder, 0770) == 0;
  saving = save && folder && saveEvent(obj, true);
  cJSON_AddBoolToObject(obj, "saved", saving); emit(obj);
  if (save && !saving) message("Cannot create recording; captions continue", false);
}
void readNote(char* name) {
  long offset = 0;
  if (char* number = std::strchr(name, ' ')) {
    *number++ = 0;
    char* end = nullptr; errno = 0; offset = std::strtol(number, &end, 10);
    if (errno || end == number || *end || offset < 0 || offset > 64 * 1024 * 1024) { message("Invalid page offset", false); return; }
  }
  const size_t n = std::strlen(name);
  if (n < 7 || n > 100 || std::strcmp(name + n - 6, ".jsonl")) { message("Expected a recording .jsonl filename", false); return; }
  for (const char* p = name; *p; ++p) if (!((*p >= 'a' && *p <= 'z') || (*p >= '0' && *p <= '9') || *p == '-' || *p == '.')) { message("Invalid filename", false); return; }
  char path[220]; std::snprintf(path, sizeof(path), "%s/%.100s", kFolder, name);
  FILE* file = std::fopen(path, "r"); if (!file) { message("Recording unavailable", false); return; }
  if (std::fseek(file, offset, SEEK_SET)) { std::fclose(file); message("Invalid recording offset", false); return; }
  // Bounded page; serial transfer never monopolizes the recognizer for a whole
  // large recording. The USB library normally imports a card file directly.
  static char line[16384]; size_t count = 0; // formatted aliases can double in JSON escaping
  while (count < 8 && std::fgets(line, sizeof(line), file)) {
    cJSON* saved = cJSON_Parse(line);
    if (!saved) { message("Incomplete recording line", false); break; }
    cJSON* obj = event("archive"); if (!obj) { cJSON_Delete(saved); break; }
    cJSON_AddItemToObject(obj, "record", saved); emit(obj); ++count;
  }
  const long next = std::ftell(file);
  const int peek = std::fgetc(file);
  const bool eof = peek == EOF; std::fclose(file);
  cJSON* page = event("archivePage"); if (!page) return;
  cJSON_AddStringToObject(page, "file", name); cJSON_AddBoolToObject(page, "eof", eof);
  cJSON_AddNumberToObject(page, "nextOffset", next); emit(page);
}
void run(char* cmd) {
#if HW1_STT_STREAM_METRICS
  if (!std::strcmp(cmd, "perf dump")) { captions_perf::request(); return; }
#endif
  if (commandHook && commandHook(cmd)) return;
  if (!std::strcmp(cmd, "help")) message("vocab list | vocab add DISPLAY[|spoken] | vocab remove spoken | vocab reload | note start | note stop | notes | note read FILENAME [OFFSET] | clock set EPOCH | lm strength 0..1 | status. Stop saves accepted results through this command; microphone/captions continue.");
  else if (!std::strcmp(cmd, "vocab list")) {
    cJSON* obj = event("vocabulary"); if (!obj) return; cJSON* rows = cJSON_AddArrayToObject(obj, "words");
    for (size_t i = 0; i < vocabulary.count(); ++i) { cJSON* row = cJSON_CreateObject(); cJSON_AddStringToObject(row, "display", vocabulary.at(i).display); cJSON_AddStringToObject(row, "spoken", vocabulary.at(i).spoken); cJSON_AddItemToArray(rows, row); }
    emit(obj);
  } else if (!std::strncmp(cmd, "vocab add ", 10)) {
    char* shown = cmd + 10; char* spoken = std::strchr(shown, '|'); if (spoken) *spoken++ = 0;
    staged = vocabulary; char error[160];
    if (!staged.put(shown, spoken, error, sizeof(error))) message(error, false);
    else { const bool ok = commitVocabulary(); message(ok ? "Vocabulary saved and active for the next phrase" : "Vocabulary save failed; previous vocabulary remains active", ok); }
  } else if (!std::strncmp(cmd, "vocab remove ", 13)) {
    staged = vocabulary;
    if (!staged.remove(cmd + 13)) message("Word not found", false);
    else { const bool ok = commitVocabulary(); message(ok ? "Word removed" : "Save failed; previous vocabulary remains active", ok); }
  } else if (!std::strcmp(cmd, "vocab reload")) { const bool ok = loadVocabulary(); message(ok ? "Vocabulary loaded" : "Invalid/unreadable vocabulary; previous entries retained", ok); }
  else if (!std::strcmp(cmd, "note start")) start();
  else if (!std::strcmp(cmd, "note stop")) { finish(); start(false); message("Recording closed; microphone/captions continue. Use note start to save again."); }
  else if (!std::strcmp(cmd, "notes")) {
    DIR* dir = opendir(kFolder); cJSON* obj = event("files"); if (!obj) { if (dir) closedir(dir); return; }
    cJSON* names = cJSON_AddArrayToObject(obj, "files"); size_t count = 0; bool more = false;
    if (dir) { struct dirent* entry; while ((entry = readdir(dir))) { const size_t n = std::strlen(entry->d_name); if (n < 7 || std::strcmp(entry->d_name + n - 6, ".jsonl")) continue; if (count++ >= 128) { more = true; break; } cJSON_AddItemToArray(names, cJSON_CreateString(entry->d_name)); } closedir(dir); }
    cJSON_AddBoolToObject(obj, "truncated", more); emit(obj);
  } else if (!std::strncmp(cmd, "note read ", 10)) readNote(cmd + 10);
  else if (!std::strncmp(cmd, "clock set ", 10)) {
    char* end = nullptr; errno = 0; const long long epoch = std::strtoll(cmd + 10, &end, 10);
    if (errno || end == cmd + 10 || *end || epoch < 1577836800LL || epoch >= 4102444800LL) message("Invalid UTC epoch", false);
    else { struct timeval time = {static_cast<time_t>(epoch), 0}; const bool ok = settimeofday(&time, nullptr) == 0; message(ok ? "Clock set; applies to the next recording" : "Clock set failed", ok); }
  }
  else if (!std::strncmp(cmd, "lm strength ", 12)) {
    char* end=nullptr; errno=0;const float value=std::strtof(cmd+12,&end);
    if(errno||end==cmd+12||*end||!std::isfinite(value)||value<0||value>1)message("LM strength must be finite in [0,1]",false);
    else {languageStrength=value;message("LM strength updated for the next inference");}
  }
  else if (!std::strcmp(cmd, "status")) status(currentState, currentDetail);
  else if (*cmd) message("Unknown command; type help", false);
}
}
void platformBegin() {
#if defined(ESP_PLATFORM)
  if (!usb_serial_jtag_is_driver_installed()) {
    usb_serial_jtag_driver_config_t config = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    config.rx_buffer_size = 1024; config.tx_buffer_size = 4096;
    if (usb_serial_jtag_driver_install(&config) != ESP_OK) message("USB command driver unavailable", false);
  }
  if (usb_serial_jtag_is_driver_installed()) usb_serial_jtag_vfs_use_driver();
#endif
  counters();
  const int flags = fcntl(STDIN_FILENO, F_GETFL, 0); if (flags >= 0) fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
}
void begin() {
  if (!loadVocabulary()) message("Vocabulary file rejected; using no user words", false);
  start(); status("preparing");
}
void poll() {
  unsigned char bytes[128]; const ssize_t n = ::read(STDIN_FILENO, bytes, sizeof(bytes));
  for (ssize_t i = 0; i < n; ++i) {
    const char ch = char(bytes[i]);
    if (ch == '\n' || ch == '\r') {
      if (commandOverflow) message("Command too long", false);
      else if (commandBytes) { command[commandBytes] = 0; run(command); }
      commandBytes = 0; commandOverflow = false;
    } else if (ch >= 32 && ch <= 126) {
      if (commandBytes + 1 < sizeof(command)) command[commandBytes++] = ch; else commandOverflow = true;
    }
  }
}
const hw1::stt::lm::CustomWords* customWords() { return hotwords.size() ? &hotwords : nullptr; }
void caption(const char* raw, uint64_t startSample, uint64_t endSample, bool forced, uint32_t dropped) {
  clearDraft();
  static char shown[4096];
  const bool formatted = hw1::transcript::format(raw, vocabulary, paragraphStart, shown, sizeof(shown));
  if (!formatted) std::snprintf(shown, sizeof(shown), "%s", raw);
  paragraphStart = false;
  cJSON* obj = event("final"); if (!obj) return;
  identity(obj); cJSON_AddNumberToObject(obj, "sequence", ++phrase);
  cJSON_AddStringToObject(obj, "rawText", raw); cJSON_AddStringToObject(obj, "text", shown);
  number(obj, "startSample", startSample); number(obj, "endSample", endSample);
  cJSON_AddBoolToObject(obj, "forcedBoundary", forced); cJSON_AddNumberToObject(obj, "droppedPhrases", dropped);
  cJSON_AddBoolToObject(obj, "formatted", formatted);
  if (!title[0]) {
    size_t i = 0, words = 1;
    for (; shown[i] && i + 4 < sizeof(title); ++i) { if (shown[i] == ' ' && ++words > 10) break; title[i] = shown[i]; }
    title[i] = 0; if (shown[i]) std::strcat(title, "...");
  }
  cJSON_AddStringToObject(obj, "title", title);
  const bool saved = saving && saveEvent(obj);
  cJSON_AddBoolToObject(obj, "saved", saved); emit(obj);
}
Receipt receipt(){return {noteNumber,phrase};}
void speaker(Receipt receipt,int8_t label){
  // A delayed label never attaches to a different recording after note start/stop.
  if(receipt.note!=noteNumber||!receipt.sequence||receipt.sequence>phrase||label< -1||label>7)return;
  cJSON* obj=event("speaker");if(!obj)return;identity(obj);
  cJSON_AddNumberToObject(obj,"sequence",receipt.sequence);cJSON_AddNumberToObject(obj,"speaker",label);
  cJSON_AddBoolToObject(obj,"ready",true);
  if(saving)saveEvent(obj);
  emit(obj);
}
void setCommandHook(bool (*hook)(const char*)) { commandHook = hook; }
void reply(const char* text, bool ok) { message(text, ok); }
uint64_t bootNumber() { return boot.boot; }
void overlap(Receipt receipt,bool flag,float fraction,uint32_t frames){
  // Same guards as speaker(): never attach to another recording or a future phrase.
  if(receipt.note!=noteNumber||!receipt.sequence||receipt.sequence>phrase)return;
  cJSON* obj=event("overlap");if(!obj)return;identity(obj);
  cJSON_AddNumberToObject(obj,"sequence",receipt.sequence);cJSON_AddBoolToObject(obj,"overlap",flag);
  cJSON_AddNumberToObject(obj,"fraction",double(int(fraction*10000.0f+0.5f))/10000.0);
  cJSON_AddNumberToObject(obj,"frames",frames);cJSON_AddBoolToObject(obj,"ready",true);
  if(saving)saveEvent(obj);
  emit(obj);
}
float lmStrength() { return languageStrength; }
void draft(const char* raw) {
  draftActive=raw&&*raw;
  cJSON* obj=event("draft");if(!obj)return;identity(obj);
  cJSON_AddNumberToObject(obj,"sequence",phrase+1);cJSON_AddNumberToObject(obj,"version",++draftVersion);
  cJSON_AddStringToObject(obj,"text",raw);emit(obj); // previews are never saved as final records
}
void clearDraft(){if(draftActive)draft("");}
void status(const char* state, const char* detail) {
  currentState = state;
  if (detail != currentDetail) std::snprintf(currentDetail, sizeof(currentDetail), "%s", detail);
  cJSON* obj = event("status"); if (!obj) return; identity(obj);
  cJSON_AddStringToObject(obj, "state", state); cJSON_AddStringToObject(obj, "detail", currentDetail);
  cJSON_AddBoolToObject(obj, "saving", saving); cJSON_AddNumberToObject(obj, "customWords", hotwords.size());
  cJSON_AddBoolToObject(obj, "clockKnown", clockKnown);
  cJSON_AddNumberToObject(obj,"lmStrength",languageStrength);
  if (clockKnown) cJSON_AddStringToObject(obj, "startedUtc", startedUtc); else cJSON_AddNullToObject(obj, "startedUtc");
  cJSON_AddStringToObject(obj, "title", title); cJSON_AddStringToObject(obj, "source", "local-pdm");
  number(obj, "startedUptimeMs", noteStarted); emit(obj);
}
}
