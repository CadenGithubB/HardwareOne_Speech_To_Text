#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache'))
from p4hwcal import summarize
trap='''TL hwcal_armed core=0 address=1343225856 data1=553648330 data2=1343225857 control=136 end
TL hwcal_probe core=0 read_adjacent_ok=1 value=324508639 end
Guru Meditation Error: Core  0 panic'ed (Breakpoint).
MEPC : 0x4ff22cd0 MCAUSE : 0x00000003
'''
recovery='''TL hwcal_recovery core=0 phase=2 address=1343225856 word=324508639 adjacent=610839776 released=1 idle=1 data1=553648128 data2=0 control=0 end\n'''
assert summarize(trap.replace('core=0','core=1').replace('Core  0','Core  1'),recovery.replace('core=0','core=1'),1,0x4ff22cd0)['core']==1
r=summarize(trap,recovery,0,0x4ff22cd0);assert r['post_reset_slot0_reset_shape'] and r['word_unchanged']
owned=recovery.replace('data1=553648128 data2=0 control=0','data1=554696906 data2=1343225857 control=128')
assert not summarize(trap,owned,0,0x4ff22cd0)['post_reset_slot0_reset_shape']
cases=[(trap.replace('value=324508639','value=0'),recovery),(trap.replace('0x00000003','0x00000005'),recovery),
 (trap.replace('0x4ff22cd0','0x4ff22cd2'),recovery),(trap.replace('Core  0','Core  1'),recovery),
 (trap+trap,recovery),(trap,recovery.replace('idle=1','idle=0')),(trap,recovery.replace('word=324508639','word=137')),
 (trap.replace(' end','',1),recovery),(trap,recovery.replace('phase=2','phase=1')),(trap,recovery+'Task watchdog got triggered\n'),
 (trap+'TL hwcal_failed core=0 released=1 end\n',recovery),(trap,recovery.replace('data1=553648128','data1=1')),
 (trap,recovery.replace('address=1343225856','address=1343225860'))]
for t,r in cases:
 try:summarize(t,r,0,0x4ff22cd0)
 except ValueError:pass
 else:raise AssertionError('damaged calibration accepted')
assert 'PRIVATE' not in str(summarize(trap+'PRIVATE text\n',recovery,0,0x4ff22cd0))
print('P4 watch calibration: expected trap, negative controls, recovery and damaged cases ok')
from p4hwcal import summarize_dual
lines=trap.splitlines()
dual='\n'.join([lines[0],lines[0].replace('core=0','core=1'),lines[1],lines[1].replace('core=0','core=1'),'TL hwcal_ready cores=2 phase=2 verified=1 end',*lines[2:]])+'\n'
dual_recovery=recovery+recovery.replace('core=0','core=1')
r=summarize_dual(dual,dual_recovery,0,0x4ff22cd0);assert r['armed_cores']==2 and r['peer_core']==1 and r['both_post_reset_slot0_reset_shape']
retained_peer=recovery+owned.replace('core=0','core=1')
r=summarize_dual(dual,retained_peer,0,0x4ff22cd0)
assert r['cores'][0]['post_reset_slot0_reset_shape'] and not r['cores'][1]['post_reset_slot0_reset_shape']
assert not r['both_post_reset_slot0_reset_shape']
for t,r in [(trap,dual_recovery),(dual,recovery),(dual.replace('verified=1','verified=0'),dual_recovery),
 (dual.replace('core=1 address=1343225856','core=1 address=1343225860'),dual_recovery),(dual,dual_recovery+recovery),
 (dual.replace('TL hwcal_probe core=1','TL hwcal_probe core=2'),dual_recovery)]:
 try:summarize_dual(t,r,0,0x4ff22cd0)
 except ValueError:pass
 else:raise AssertionError('damaged dual calibration accepted')
print('P4 dual calibration: both leases, peer recovery, missing/changed evidence ok')

from p4hwcal import summarize_psram
psram=('TL hwcal_target kind=1 bytes=8 address=1343225856 external=1 end\n'+dual).replace('1343225856','1207963648').replace('1343225857','1207963649')
psram_recovery=dual_recovery.replace('1343225856','1207963648').replace('1343225857','1207963649').replace('hwcal_recovery','hwcal_psram_recovery').replace(' word=',' probe_word=').replace(' adjacent=',' probe_adjacent=')
r=summarize_psram(psram,psram_recovery,0,0x4ff22cd0)
assert r['external_verified']==1 and r['allocated_payload_bytes']==8 and not r['post_reset_target_read']
assert all('word_unchanged' not in c for c in r['cores'])
for t,r in [(dual,psram_recovery),(psram,dual_recovery),(psram.replace('external=1','external=0'),psram_recovery),
 (psram.replace('bytes=8','bytes=4'),psram_recovery),(psram,psram_recovery.replace('probe_word=324508639','probe_word=0')),
 (psram.replace('kind=1','kind=0'),psram_recovery),(psram.replace('TL hwcal_target kind=1 bytes=8 address=1207963648','TL hwcal_target kind=1 bytes=8 address=1207963652'),psram_recovery)]:
 try:summarize_psram(t,r,0,0x4ff22cd0)
 except ValueError:pass
 else:raise AssertionError('damaged PSRAM evidence accepted')
print('P4 PSRAM calibration: target kind, pre-trap provenance, both recovery rows and damaged cases ok')

try:summarize_psram(psram.replace('1207963648','1343225856').replace('1207963649','1343225857'),psram_recovery.replace('1207963648','1343225856'),0,0x4ff22cd0)
except ValueError:pass
else:raise AssertionError('RTC address masquerading as external RAM accepted')
