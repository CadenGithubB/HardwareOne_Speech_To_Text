#include "quartznet_runtime.h"
#include "esp_littlefs.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstring>
#include <sys/stat.h>
extern const uint8_t fixture0_start[] asm("_binary_fixture0_pcm_start");
extern const uint8_t fixture0_end[] asm("_binary_fixture0_pcm_end");
extern const uint8_t fixture1_start[] asm("_binary_fixture1_pcm_start");
extern const uint8_t fixture1_end[] asm("_binary_fixture1_pcm_end");
struct Reader { FILE* file; size_t bytes=0; };
static size_t readModel(void* f,void* p,size_t n){auto& r=*static_cast<Reader*>(f);size_t got=fread(p,1,n,r.file);r.bytes+=got;return got;}
static void progress(void*,STTLocalPhase p){printf("STT_PHASE phase=%u ms=%lld\n",unsigned(p),esp_timer_get_time()/1000);fflush(stdout);}
static void hash(const char* key,const uint8_t* h){printf("%s=",key);for(size_t i=0;i<32;++i)printf("%02x",h[i]);}
static bool run(int number,const uint8_t* start,const uint8_t* end,hw1::stt::ModelCache* cache=nullptr,bool expectReuse=false){
    const size_t before=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    const char* path="/storage/STT Models/quartznet5x5.p4.stt";
    struct stat info{};if(stat(path,&info)){puts("STT_FAIL reason=model_missing");return false;}
    FILE* file=fopen(path,"rb");if(!file){puts("STT_FAIL reason=model_open");return false;}
    char text[512]={},error[128]={};STTLocalStats stats;hw1::stt::Diagnostics diagnostics;
    STTLocalControl control{};control.progress=progress;
    printf("STT_BEGIN fixture=%d samples=%u psram=%u internal=%u\n",number,unsigned((end-start)/2),unsigned(before),unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)));fflush(stdout);
    Reader reader{file};
    bool ok=hw1::stt::transcribe({&reader,size_t(info.st_size),readModel},reinterpret_cast<const int16_t*>(start),(end-start)/2,text,sizeof(text),control,stats,error,sizeof(error),&diagnostics,cache);
    fclose(file);
    const bool intact=!cache || cache->verify();
    ok=ok && intact && stats.weightsReused==expectReuse;
    printf("STT_CACHE fixture=%d reused=%d integrity=%d read_bytes=%u\n",number,stats.weightsReused,intact,unsigned(reader.bytes));
    printf("STT_RESULT fixture=%d passed=%d samples=%lu features=%lu outputs=%lu load_ms=%lu frontend_ms=%lu inference_ms=%lu decode_ms=%lu psram_during=%u internal_during=%u arena_psram=%u arena_internal=%u psram_after=%u\n",number,ok,stats.samples,stats.featureFrames,stats.outputFrames,stats.loadMs,stats.frontendMs,stats.inferenceMs,stats.decodeMs,unsigned(diagnostics.freePsramAtInference),unsigned(diagnostics.freeInternalAtInference),unsigned(diagnostics.activationPsramBytes),unsigned(diagnostics.activationInternalBytes),unsigned(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
    printf("STT_HASH fixture=%d ",number);hash("input",diagnostics.inputSha);printf(" ");hash("output",diagnostics.outputSha);puts("");
    // This standalone probe emits only public, synthetic test fixtures.
    printf("STT_TEXT fixture=%d text=%s\n",number,text);if(!ok)printf("STT_FAIL reason=%s\n",error);fflush(stdout);return ok;
}
extern "C" void app_main(){
    esp_vfs_littlefs_conf_t conf{};conf.base_path="/storage";conf.partition_label="littlefs";conf.format_if_mount_failed=false;conf.read_only=true;
    const esp_err_t err=esp_vfs_littlefs_register(&conf);
    if(err!=ESP_OK){printf("STT_FAIL mount=%d\n",int(err));puts("STT_PROBE_DONE passed=0");return;}
    const size_t before=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    bool ok=true;
    {
        hw1::stt::ModelCache cache;
        ok=run(0,fixture0_start,fixture0_end,&cache,false)&&ok;
        ok=run(1,fixture1_start,fixture1_end,&cache,true)&&ok;
        ok=run(2,fixture0_start,fixture0_end,&cache,true)&&ok;
        cache.reset();
        const size_t after=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        printf("STT_CACHE_RELEASE before=%u after=%u\n",unsigned(before),unsigned(after));
        ok=(before==after)&&ok;
        // Reload into the same owner after explicit reset, then check RAII too.
        ok=run(3,fixture0_start,fixture0_end,&cache,false)&&ok;
    }
    const size_t finalFree=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    printf("STT_CACHE_FINAL before=%u after=%u\n",unsigned(before),unsigned(finalFree));
    ok=(before==finalFree)&&ok;
    esp_vfs_littlefs_unregister("littlefs");printf("STT_PROBE_DONE passed=%d\n",ok);fflush(stdout);
}
