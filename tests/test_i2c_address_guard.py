#!/usr/bin/env python3
"""Source-bound sanitizer reproduction; candidate stays out of the installed SDK."""
import argparse,difflib,hashlib,json,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('hardwareone',type=Path);ap.add_argument('--evidence',type=Path);ap.add_argument('--patch',type=Path);a=ap.parse_args()
relative=Path('components/arduino/cores/esp32/esp32-hal-i2c-ng.c');original_bytes=(a.hardwareone/relative).read_bytes();source=original_bytes.decode()
def function(text,signature):
 start=text.index(signature);brace=text.index('{',start);depth=1;i=brace+1
 while depth:
  depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[start:i]
helper=function(source,'static esp_err_t i2cAddDeviceIfNeeded(')
assert 'address >= 128' not in helper and 'address>=128' not in helper,'source already guards addresses: audit this test before reuse'
for signature in ['esp_err_t i2cRead(','esp_err_t i2cWriteReadNonStop(']:
 body=function(source,signature)
 assert 'i2cAddDeviceIfNeeded(i2c_num, address)' in body and 'address >= 128' not in body
assert 'address >= 128' in function(source,'esp_err_t i2cWrite(')
fixed=helper.replace('{','{\n  if (address >= 128) {\n    return ESP_ERR_INVALID_ARG;\n  }',1)
typedef_start=source.index('typedef volatile struct {');typedef_end=source.index('} i2c_bus_t;',typedef_start)+len('} i2c_bus_t;')
types=source[typedef_start:typedef_end]
prefix='''#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#define CONFIG_DISABLE_HAL_LOCKS 0
#define SOC_I2C_NUM 3
#define ESP_OK 0
#define ESP_ERR_INVALID_ARG 0x102
#define I2C_ADDR_BIT_LEN_7 0
#define log_e(...) ((void)0)
#define log_v(...) ((void)0)
typedef int esp_err_t;
typedef void* SemaphoreHandle_t;
typedef void* i2c_master_bus_handle_t;
typedef void* i2c_master_dev_handle_t;
typedef struct {int dev_addr_length;uint16_t device_address;uint32_t scl_speed_hz,scl_wait_us;struct {unsigned disable_ack_check;} flags;} i2c_device_config_t;
'''+types+'''
static i2c_bus_t bus[SOC_I2C_NUM];
static unsigned calls;
static esp_err_t i2c_master_bus_add_device(void* b,const i2c_device_config_t* config,void** out){(void)b;assert(config->device_address<128);++calls;*out=(void*)(uintptr_t)(config->device_address+1);return ESP_OK;}
'''
main='''
int main(int argc,char** argv){
 (void)argv;bus[0].initialized=true;bus[0].frequency=100000;
 if(argc>1){assert(i2cAddDeviceIfNeeded(0,128)==ESP_ERR_INVALID_ARG);return 0;}
 const uint16_t invalid[]={128,129,255,256,65535};
 for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);++i){assert(i2cAddDeviceIfNeeded(0,invalid[i])==ESP_ERR_INVALID_ARG);assert(calls==0);}
 assert(i2cAddDeviceIfNeeded(0,0)==ESP_OK && calls==1 && bus[0].dev_handles[0]==(void*)1);
 assert(i2cAddDeviceIfNeeded(0,127)==ESP_OK && calls==2 && bus[0].dev_handles[127]==(void*)128);
 assert(i2cAddDeviceIfNeeded(0,127)==ESP_OK && calls==2);
}
'''
with tempfile.TemporaryDirectory(prefix='i2c-address-guard-') as tmp:
 root=Path(tmp);results={}
 for name,body in [('original_default',helper),('original',helper),('candidate',fixed)]:
  path=root/(name+'.c');path.write_text(prefix+body+main)
  flags=['-fstrict-flex-arrays=3'] if name!='original_default' else []
  subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',*flags,str(path),'-o',str(root/name)],check=True)
  result=subprocess.run([str(root/name),'bad'] if name.startswith('original') else [str(root/name)],capture_output=True,text=True)
  results[name]=result
 original=results['original'];candidate=results['candidate']
 assert original.returncode!=0 and 'index 128 out of bounds' in original.stderr,'original did not reproduce the expected bounds error'
 assert candidate.returncode==0 and not candidate.stderr,'candidate failed sanitizer/behavior checks'
 assert (a.hardwareone/relative).read_bytes()==original_bytes,'SDK file changed during the test'
 report={'source_sha256':hashlib.sha256(original_bytes).hexdigest(),'helper_sha256':hashlib.sha256(helper.encode()).hexdigest(),'original_bounds_failure':True,'default_bounds_diagnostic':'index 128 out of bounds' in results['original_default'].stderr,'strict_flex_arrays':3,'invalid_address':128,'candidate_invalid_cases':5,'candidate_valid_boundary_cases':2,'candidate_cached_handle_reuse_cases':1,'candidate_returncode':0,'sdk_changed':False}
 if a.evidence:
  a.evidence.mkdir(parents=True,exist_ok=False,mode=0o700)
  (a.evidence/'original-default-sanitizer.log').write_text(results['original_default'].stderr);(a.evidence/'original-sanitizer.log').write_text(original.stderr);(a.evidence/'numeric-report.json').write_text(json.dumps(report,indent=2))
 if a.patch:
  changed=source.replace(helper,fixed,1)
  a.patch.write_text(''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),fromfile='a/'+str(relative),tofile='b/'+str(relative))))
 print('i2c address guard: original bounds failure reproduced; 8 candidate boundary/cache cases passed; SDK unchanged')
