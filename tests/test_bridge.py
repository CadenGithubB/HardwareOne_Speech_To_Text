#!/usr/bin/env python3
"""No hardware: bridge history overflow and loopback HTTP checks."""
import importlib.util
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge', ROOT / 'tools/transcript/serve.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
events = module.Events()
for i in range(1100): events.append({'i':i})
assert len(events.since(0)['events']) == 1024
assert events.since(1)['gap'] and not events.since(1099)['gap']
port = 18765
process = subprocess.Popen([sys.executable, str(ROOT / 'tools/transcript/serve.py'), '--http-port', str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
url = f'http://127.0.0.1:{port}'
try:
    for _ in range(50):
        try:
            with urllib.request.urlopen(url + '/api/events?after=0', timeout=1) as response: data = json.load(response)
            break
        except urllib.error.URLError: time.sleep(.1)
    else: raise AssertionError('Viewer did not start')
    assert data['events'] == [] and not data['usb']
    with urllib.request.urlopen(url) as response: assert b'Speech notes' in response.read()
    def rejected(request, code):
        try: urllib.request.urlopen(request)
        except urllib.error.HTTPError as error: assert error.code == code, error.code
        else: raise AssertionError('Request unexpectedly accepted')
    rejected(urllib.request.Request(url+'/api/command', data=b'{"command":"note start"}', headers={'Content-Type':'application/json'}),403)
    rejected(urllib.request.Request(url+'/api/command', data=b'{"command":"note start"}', headers={'Content-Type':'application/json','Origin':url}),409)
    rejected(urllib.request.Request(url, headers={'Host':'evil.test'}),403)
    rejected(url+'/not-a-file',404)
    print('bridge ring gap, loopback assets, origin/host checks and no-device handling passed')
finally:
    process.terminate(); process.communicate(timeout=5)
