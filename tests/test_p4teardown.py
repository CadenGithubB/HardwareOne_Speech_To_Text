#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/feature_cache'))
import p4teardown as p
class Reader:
    def __init__(self):self.lock=threading.Lock();self.history=[]
class Device:
    def __init__(self,lines=None,reset=False):
        self.rd=Reader();self.token='1234567890abcdef';self.calls=[];self.reset=reset
        self.lines=lines if lines is not None else [f'TL teardown phase={phase} event=2 ms={i} end' for i,phase in enumerate(p.teardowndiag.PHASES)]
    def command(self,command,pattern,timeout=20):
        self.calls.append(command.split()[1])
        if ' stop ' in command:
            self.rd.history.extend(self.lines);return re.search(pattern,'STT request accepted')
        assert any(p.DONE.search(l) for l in self.rd.history)
        return re.search(pattern,json.dumps({'state':'done','audioOverruns':0}))
    def check_health(self):
        if self.reset:raise RuntimeError('synthetic reset')
d=Device();assert p.stop_after_teardown(d)['state']=='done' and d.calls==['stop','status'] and d.token is None
assert d.teardown_summary['cycles'][0]['heap_checks']==0
for d,timeout in [(Device(reset=True),1),(Device(lines=[]),0)]:
    try:p.stop_after_teardown(d,timeout=timeout)
    except (RuntimeError,ValueError):pass
    else:raise AssertionError('incomplete/faulted stop accepted')
    assert d.calls==['stop'] and d.token is None
d=Device(lines=Device().lines[:2]+Device().lines[3:])
try:p.stop_after_teardown(d,timeout=1)
except p.TeardownEvidenceError:pass
else:raise AssertionError('missing markers accepted')
assert d.calls==['stop','status'] and d.token is None and d.terminal_state['state']=='done'
print('p4 teardown: passive ordering, reset, timeout and incomplete-evidence cases ok')
