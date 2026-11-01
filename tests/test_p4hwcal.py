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
