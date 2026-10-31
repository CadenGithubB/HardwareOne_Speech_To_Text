#include "product.h"
#include "nvs.h"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <unistd.h>
#include <fcntl.h>
static std::vector<unsigned char> blob;
static int64_t elapsed = 1000000;
int64_t esp_timer_get_time() { return elapsed += 100000; }
uint32_t esp_random() { static uint32_t next = std::getenv("LARGE_RECORD") ? 142 : 42; return ++next; }
int esp_reset_reason() { return 1; }
esp_err_t nvs_flash_init() { return std::getenv("FAIL_NVS") ? 9 : 0; }
esp_err_t nvs_open(const char* name, int, nvs_handle_t* out) { assert(!std::strcmp(name,"hw1_stt_demo")); *out = 1; return 0; }
esp_err_t nvs_get_blob(nvs_handle_t, const char*, void* out, size_t* length) {
 if (blob.empty()) return ESP_ERR_NVS_NOT_FOUND;
 assert(*length >= blob.size()); std::memcpy(out, blob.data(), blob.size()); *length=blob.size(); return 0;
}
esp_err_t nvs_set_blob(nvs_handle_t, const char*, const void* data, size_t n) { const auto* p=static_cast<const unsigned char*>(data);blob.assign(p,p+n);return 0; }
esp_err_t nvs_commit(nvs_handle_t) { return 0; }
void nvs_close(nvs_handle_t) {}
void command(const char* text) {
 int pipefd[2]; assert(pipe(pipefd)==0);
 const int original=dup(0); assert(dup2(pipefd[0],0)>=0); close(pipefd[0]);
 const std::string line=std::string(text)+"\n"; assert(write(pipefd[1],line.data(),line.size())==ssize_t(line.size()));close(pipefd[1]);
 product::poll(); assert(dup2(original,0)>=0); close(original);
}
int main() {
 product::platformBegin(); product::begin();
 if (std::getenv("STREAM_EVENTS")) {
   assert(product::lmStrength()==1.0f);
   command("lm strength 0.75");assert(product::lmStrength()==0.75f);
   for(const char* bad:{"nan","inf","-0.1","1.1","0.5junk",""}) {
     command((std::string("lm strength ")+bad).c_str());assert(product::lmStrength()==0.75f);
   }
   product::draft("preview words");
   product::caption("final words",0,16000,false,0);
   const auto old=product::receipt();command("note stop");
   product::speaker(old,2); // must never label a phrase in the replacement note
   product::caption("new words",16000,32000,false,0);
   product::speaker(product::receipt(),3);
   product::speaker(product::receipt(),8); // outside the configured eight speakers
   product::status("listening");return 0;
 }
 if (std::getenv("FAIL_NVS")) { product::status("error","NVS test");return 0; }
 if (std::getenv("LARGE_RECORD")) {
   const std::string alias(63, '"');
   command(("vocab add "+alias+"|a").c_str());
   std::string raw;
   for (int i=0;i<64;++i) { if(i)raw+=' ';raw+='a'; }
   product::caption(raw.c_str(),0,16000,false,0);
   command("note stop");
   command("note read b00000000000000000001-0000008f-n0000000001.jsonl");
   return 0;
 }
 if (std::getenv("LOAD_ONLY")) { command("vocab list");command("note stop"); return 0; }
 command("vocab add HardwareOne");
 assert(product::customWords() && product::customWords()->contains("hardwareone",11));
 product::caption("i use hardwareone",0,16000,false,0);
 command("vocab add OpenAI");
 command("vocab add Invalid|two words");
 assert(product::customWords()->size()==2);
 product::caption("and i'd like openai",16000,32000,false,0);
 command("vocab remove hardwareone");
 assert(!product::customWords()->contains("hardwareone",11));
 command("note stop");
 product::caption("not saved",32000,48000,false,0);
 command("notes");
 product::platformBegin(); // exercises actual startup-blob roundtrip in the application
 product::status("listening");
}
