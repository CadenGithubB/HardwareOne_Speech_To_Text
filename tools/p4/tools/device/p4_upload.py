"""Upload a file to the P4 over the serial CLI with chunked `filewrite`.

p4_upload.py LOCAL REMOTE_PATH [chunk_bytes]   (P4_USER / P4_PASS from env)
Resyncs on offset mismatch using the size the device reports.
"""
import base64, json, os, re, sys, time
from pathlib import Path
import serial

USER, PASS = os.environ['P4_USER'], os.environ['P4_PASS']
local, remote = Path(sys.argv[1]), sys.argv[2]
chunk = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
data = local.read_bytes()

s = serial.Serial()
s.port, s.baudrate, s.timeout, s.dtr, s.rts = os.environ['HW1_P4_PORT'], 115200, 0.02, False, False
s.open()
buf = bytearray()


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        d = s.read(8192)
        if d:
            buf.extend(d)


def cmd(line, until=None, timeout=5.0):
    start = len(buf)
    s.write((line + '\r\n').encode())
    end = time.time() + timeout
    while time.time() < end:
        d = s.read(8192)
        if d:
            buf.extend(d)
            if until and re.search(until, bytes(buf[start:])):
                break
    return bytes(buf[start:]).decode('utf-8', 'replace')


def reply(text):
    for m in re.finditer(r'\{"success".*?\}', text):
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    return None


end = time.time() + 40
while time.time() < end and b'Setup complete' not in buf:
    pump(0.5)
pump(3)
cmd(f'login {USER} {PASS}', rb'Login successful|failed|Invalid', 5)
cmd('loglevel warn', rb'OK|Error', 3)  # keep debug logging out of the transfer
folder = remote.rsplit('/', 1)[0]
print(cmd(f'mkdir "{folder}"', rb'OK|Error|exists', 5).strip().splitlines()[-1:])
t0 = time.time()
offset, retries = 0, 0
while offset < len(data):
    piece = data[offset:offset + chunk]
    final = ' final' if offset + len(piece) >= len(data) else ''
    b64 = base64.b64encode(piece).decode()
    out = cmd(f'filewrite "{remote}" {offset} {b64}{final}', rb'\{"success"[^\n]*\}', 20)
    r = reply(out)
    if r and r.get('success'):
        offset += len(piece)
    else:
        retries += 1
        size = r.get('size') if r else None
        if isinstance(size, int) and 0 <= size <= len(data):
            offset = size - size % 1  # resync to what the device has
        if retries > 50:
            print('too many retries; last reply:', out[-300:]); break
    if offset and (offset // chunk) % 64 == 0:
        el = time.time() - t0
        print(f'  {offset}/{len(data)} bytes, {offset / el / 1024:.1f} KB/s', flush=True)
el = time.time() - t0
print(json.dumps({'bytes': offset, 'total': len(data), 'seconds': round(el, 1),
                  'kb_per_s': round(offset / el / 1024, 1), 'retries': retries, 'chunk': chunk}))
cmd('loglevel debug', rb'OK|Error', 3)
cmd('logout', None, 1)
s.close()
