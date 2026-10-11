"""Speaker-to-PDM-mic STT test on the P4 over the serial CLI.

Plays held-out clips through the Mac speakers during a continuous `stt start`
session, collects the chunks and scores them. Login comes from P4_USER /
P4_PASS; the password is never printed and is blanked in the saved log.
"""
import json, os, re, subprocess, sys, time
from pathlib import Path
import serial

PORT = os.environ['HW1_P4_PORT']
USER, PASS = os.environ['P4_USER'], os.environ['P4_PASS']
CLIPS = Path(os.path.join(os.environ.get('STT_ROOT', 'stt-data'), 'work/deploy/mic-test'))
OUT = Path(sys.argv[1])
refs = json.loads((CLIPS / 'refs.json').read_text())

s = serial.Serial()
s.port, s.baudrate, s.timeout, s.dtr, s.rts = PORT, 115200, 0.05, False, False
s.open()  # opening the port resets the P4
buf = bytearray()


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        data = s.read(4096)
        if data:
            buf.extend(data)


def cmd(line, wait=2.0, expect=None):
    start = len(buf)
    s.write((line + '\r\n').encode())
    end = time.time() + wait
    while time.time() < end:
        pump(0.05)
        if expect and re.search(expect, bytes(buf[start:])):
            pump(0.15)
            break
    return bytes(buf[start:]).decode('utf-8', 'replace')


def objects(text):
    dec, found, i = json.JSONDecoder(), [], 0
    while (i := text.find('{"', i)) >= 0:
        try:
            obj, end = dec.raw_decode(text, i)
            found.append(obj)
            i = end
        except ValueError:
            i += 2
    return found


def last(text, key):
    objs = [o for o in objects(text) if key in o]
    return objs[-1] if objs else None


def save_log():
    OUT.with_suffix('.log').write_bytes(bytes(buf).replace(PASS.encode(), b'********') if len(PASS) >= 4 else bytes(buf))


result = {'chunks': [], 'events': []}
try:
    end = time.time() + 40
    while time.time() < end and b'Setup complete' not in buf:
        pump(0.5)
    pump(4)
    reply = cmd(f'login {USER} {PASS}', 4, rb'(?i)(logged in|welcome|invalid|fail|denied)')
    who = cmd('whoami', 2, rb'You are')
    assert 'You are' in who, 'login failed'
    result['events'].append('login ok')
    result['micsource'] = cmd('micsource pdm', 2, rb'(?i)(pdm|error)').strip().splitlines()[-1:]
    cmd('sttperf clear', 2); cmd('sttperf stages clear', 2); cmd('sttperf log on', 2)
    cmd('closesr', 2); cmd('closemic', 2)
    started = last(cmd('stt start', 4, rb'"accepted"|Error'), 'accepted')
    assert started, 'stt start failed'
    rid = started['id']
    t0 = time.time()
    for _ in range(60):
        st = last(cmd(f'stt status {rid}', 1.5, rb'"state"'), 'state')
        if st and st['state'] == 'recording':
            break
        time.sleep(0.25)
    result['events'].append(f'recording after {time.time() - t0:.1f}s')

    result['drafts'] = []
    last_draft = [None]
    def drain():
        d = last(cmd(f'stt draft {rid}', 1.0, rb'"version"|Error'), 'version')
        if d and d.get('version') != last_draft[0]:
            last_draft[0] = d.get('version')
            if d.get('sttText'): result['drafts'].append({'t': round(time.time() - t0, 1), 'seq': d.get('sequence'), 'text': d['sttText']})
        while True:
            nxt = last(cmd(f'stt next {rid}', 1.5, rb'"available"'), 'available')
            if not nxt or not nxt['available']:
                return
            result['chunks'].append({k: nxt.get(k) for k in ('sequence', 'startSample', 'endSample', 'sttText')}
                                    | {'received': round(time.time() - t0, 1)})
            cmd(f'stt ack {rid} {nxt["sequence"]}', 1.5, rb'OK|Error')

    plays = []
    for r in refs:
        a = time.time() - t0
        p = subprocess.Popen(['/usr/bin/afplay', str(CLIPS / r['clip'])])
        while p.poll() is None:
            pump(0.5)
            drain()
        plays.append({'clip': r['clip'], 'start': round(a, 1), 'end': round(time.time() - t0, 1)})
        pump(1.5)
    result['plays'] = plays
    pump(3)
    drain()
    cmd(f'stt stop {rid}', 2, rb'OK|Error')
    for _ in range(120):
        drain()
        st = last(cmd(f'stt status {rid}', 1.5, rb'"state"'), 'state')
        if st and not st.get('workerActive') and not st.get('pendingTexts'):
            break
        time.sleep(0.5)
    result['final_status'] = st
    cmd('sttperf stages', 1)  # warm (no-op)
    result['stages'] = cmd('sttperf stages', 4, rb'slowest 40[\s\S]*\n *[0-9]+ +[0-9.]+ +[0-9.]+%[^\n]*\n[\s\S]{600}')
    result['stages_all'] = cmd('sttperf stages all', 4, rb'stages [0-9]+ segments [0-9]+ us:[0-9,]{200}')
    perf = cmd('sttperf', 4, rb'average rtf')
    result['perf'] = [l for l in perf.splitlines() if l.startswith(('seg ', 'STT perf', 'average'))]
    cmd('logout', 2)
finally:
    s.close()
    save_log()

hyp = ' '.join(c['sttText'] or '' for c in result['chunks']).split()
ref = ' '.join(r['ref'] for r in refs).split()
d = list(range(len(hyp) + 1))
for i in range(1, len(ref) + 1):
    prev, d[0] = d[0], i
    for j in range(1, len(hyp) + 1):
        prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ref[i - 1] != hyp[j - 1]))
result['wer'] = round(d[len(hyp)] / len(ref), 3)
result['ref_words'] = len(ref)
log = OUT.with_suffix('.log').read_text('utf-8', 'replace')
result['lm_log'] = [l for l in log.splitlines() if re.search(r'(?i)(\blm\b|meeting\.lm|language model|custom_words)', l)][:10]
OUT.write_text(json.dumps(result, indent=1))
print(json.dumps({k: v for k, v in result.items() if k != 'plays'}, indent=1))
