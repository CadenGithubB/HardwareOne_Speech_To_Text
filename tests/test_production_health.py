"""Test actual command/drain functions with synthetic serial/reader events.

Extract only these stdlib functions so this unit test needs no serial device or
pyserial installation; no implementation is re-created in the test.
"""
import ast
import json
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
source=ast.parse((root/'tools/device_tests/speaker/run_session.py').read_text())
nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('production_command','production_drain_one')]
assert len(nodes)==2
ns={'time':time,'re':re,'json':json}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual production command functions>','exec'),ns)
reader=SimpleNamespace(lock=threading.Lock(),history=[],reset=False)
class Serial:
    def __init__(self,reply,reset=False):self.reply=reply;self.reset=reset;self.sent=[]
    def write(self,data):
        self.sent.append(data)
        with reader.lock:
            reader.history.append(self.reply);reader.reset=self.reset
ser=Serial('ready')
assert ns['production_command'](ser,reader,'probe','ready').group(0)=='ready'
def health():
    if reader.reset:raise RuntimeError('synthetic reboot')
reader.reset=False;ser=Serial('ready',True)
try:ns['production_command'](ser,reader,'probe','ready',health_check=health)
except RuntimeError as e:assert str(e)=='synthetic reboot'
else:raise AssertionError('accepted a reply after reset')
reader.reset=False;ser=Serial('{"available":false}')
assert ns['production_drain_one'](ser,reader,'test',health_check=health)==0
reader.reset=False
class AckReset(Serial):
    def write(self,data):
        self.reply='{"available":true,"sequence":7}' if b' next ' in data else 'STT chunk acknowledged'
        self.reset=b' ack ' in data
        super().write(data)
ser=AckReset('')
try:ns['production_drain_one'](ser,reader,'test',health_check=health)
except RuntimeError:assert len(ser.sent)==2
else:raise AssertionError('ack bypassed lifecycle checking')
print('production health: reset during command/ack rejected; normal drain ok')
